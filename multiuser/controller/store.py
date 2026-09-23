"""Transactional pairing, agent sessions and one durable Discord message."""
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

from .models import Layout


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def state(activity, details):
    return json.dumps({'activity': activity, 'details': details, 'team': None, 'scores': None}, sort_keys=True)


class Denied(Exception):
    pass


class Store:
    def __init__(self, path, secret, clock=time.time):
        self.path, self.secret, self.clock = Path(path), secret, clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS agents (
              id TEXT PRIMARY KEY, username TEXT NOT NULL, name_key TEXT UNIQUE NOT NULL,
              token_hash TEXT UNIQUE, enabled INTEGER NOT NULL DEFAULT 1,
              session_id TEXT, sequence INTEGER NOT NULL DEFAULT 0,
              last_seen REAL NOT NULL DEFAULT 0, status TEXT NOT NULL,
              connection TEXT NOT NULL DEFAULT 'unpaired');
            CREATE TABLE IF NOT EXISTS pairings (
              name_key TEXT PRIMARY KEY, pin_hash TEXT NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, window REAL NOT NULL, count INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS board (
              id INTEGER PRIMARY KEY CHECK(id=1), layout TEXT NOT NULL,
              revision INTEGER NOT NULL DEFAULT 1, published INTEGER NOT NULL DEFAULT 0,
              message_id TEXT, channel_id TEXT, attachments TEXT NOT NULL DEFAULT '{}',
              create_nonce TEXT NOT NULL,
              sent_at REAL NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0,
              error TEXT NOT NULL DEFAULT '');
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(board)')}
            if 'create_nonce' not in columns:
                db.execute("ALTER TABLE board ADD COLUMN create_nonce TEXT NOT NULL DEFAULT ''")
                db.execute('UPDATE board SET create_nonce=?', (uuid.uuid4().hex[:24],))
            db.execute('INSERT OR IGNORE INTO board(id, layout, create_nonce) VALUES(1,?,?)',
                       (Layout().model_dump_json(), uuid.uuid4().hex[:24]))

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def pin_hash(self, key, pin):
        return hmac.new(self.secret.encode(), (key + ':' + pin).encode(), hashlib.sha256).hexdigest()

    def limited(self, key, maximum=100, period=60):
        now = self.clock()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM limits WHERE window<?', (now - period,))
            row = db.execute('SELECT * FROM limits WHERE key=?', (key,)).fetchone()
            if row and row['count'] >= maximum:
                return True
            db.execute('INSERT INTO limits VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET count=count+1', (key, now))
        return False

    def create_pin(self, username):
        key, pin = username.casefold(), f'{secrets.randbelow(100_000_000):08d}'
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM agents').fetchone()[0] >= 100 and not db.execute('SELECT 1 FROM agents WHERE name_key=?', (key,)).fetchone():
                raise ValueError('This controller supports up to 100 paired players.')
            db.execute('INSERT OR IGNORE INTO agents(id,username,name_key,status) VALUES(?,?,?,?)',
                       (str(uuid.uuid4()), username, key, state('waiting', 'Waiting for pairing')))
            db.execute('INSERT OR REPLACE INTO pairings VALUES(?,?,?,0)', (key, self.pin_hash(key, pin), self.clock() + 600))
            db.execute('UPDATE board SET revision=revision+1 WHERE id=1')
        return {'username': username, 'pin': pin, 'expires_in': 600}

    def redeem(self, username, pin):
        key, now = username.casefold(), self.clock()
        result = None
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM pairings WHERE name_key=?', (key,)).fetchone()
            if row and row['expires'] > now and row['attempts'] < 5:
                if hmac.compare_digest(row['pin_hash'], self.pin_hash(key, pin)):
                    token = secrets.token_urlsafe(32)
                    db.execute('UPDATE agents SET token_hash=?,enabled=1,session_id=NULL,sequence=0,connection=?,status=? WHERE name_key=?',
                               (digest(token), 'paired', state('waiting', 'Paired · reporting is off'), key))
                    db.execute('DELETE FROM pairings WHERE name_key=?', (key,))
                    agent = db.execute('SELECT id,username FROM agents WHERE name_key=?', (key,)).fetchone()
                    result = {'agent_id': agent['id'], 'username': agent['username'], 'token': token, 'heartbeat_seconds': 15}
                    db.execute('UPDATE board SET revision=revision+1 WHERE id=1')
                else:
                    db.execute('UPDATE pairings SET attempts=attempts+1 WHERE name_key=?', (key,))
        if result is None:
            raise Denied('Pairing failed. Check your username and PIN, or ask the host for a new PIN.')
        return result

    def authenticate(self, db, token):
        row = db.execute('SELECT * FROM agents WHERE token_hash=?', (digest(token),)).fetchone()
        if not row or not row['enabled']:
            raise Denied('Agent access was revoked or disabled. Contact the controller host.')
        return row

    def start(self, token):
        session = uuid.uuid4().hex
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.authenticate(db, token)
            db.execute('UPDATE agents SET session_id=?,sequence=0,last_seen=?,connection=?,status=? WHERE id=?',
                       (session, self.clock(), 'connected', state('waiting', 'Waiting for WARDOGS'), row['id']))
            db.execute('UPDATE board SET revision=revision+1 WHERE id=1')
        return {'session_id': session, 'heartbeat_seconds': 15}

    def report(self, token, report):
        payload = report.model_dump(exclude={'session_id', 'sequence'})
        if payload['activity'] != 'match':
            payload['team'], payload['scores'] = None, None
        status = json.dumps(payload, sort_keys=True)
        connection = 'paused' if report.activity == 'paused' else 'connected'
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.authenticate(db, token)
            if row['session_id'] != report.session_id:
                raise Denied('This reporting session was replaced. Start the agent again.')
            if report.sequence <= row['sequence']:
                return {'accepted': False}  # Retried / delayed packets cannot overwrite a newer status.
            db.execute('UPDATE agents SET sequence=?,last_seen=?,connection=?,status=?,session_id=? WHERE id=?',
                       (report.sequence, self.clock(), connection, status,
                        None if report.activity == 'paused' else report.session_id, row['id']))
            if status != row['status'] or connection != row['connection']:
                db.execute('UPDATE board SET revision=revision+1 WHERE id=1')
        return {'accepted': True}

    def control(self, agent_id, enabled=None, revoke=False):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM agents WHERE id=?', (agent_id,)).fetchone()
            if not row:
                raise KeyError(agent_id)
            if revoke:
                db.execute('UPDATE agents SET token_hash=NULL,session_id=NULL,connection=?,status=? WHERE id=?',
                           ('revoked', state('revoked', 'Agent access revoked'), agent_id))
                db.execute('DELETE FROM pairings WHERE name_key=?', (row['name_key'],))
            else:
                db.execute('UPDATE agents SET enabled=?,session_id=NULL,connection=?,status=? WHERE id=?',
                           (int(enabled), 'paused', state('paused', 'Ready to reconnect' if enabled else 'Paused by controller host'), agent_id))
            db.execute('UPDATE board SET revision=revision+1 WHERE id=1')

    def expire(self, seconds):
        with self.db() as db:
            cursor = db.execute('UPDATE agents SET connection=?,status=? WHERE connection=? AND last_seen<?',
                                ('disconnected', state('disconnected', 'Agent disconnected'), 'connected', self.clock() - seconds))
            if cursor.rowcount:
                db.execute('UPDATE board SET revision=revision+1 WHERE id=1')

    def roster(self, db=None):
        if db is None:
            with self.db() as db:
                return self.roster(db)
        return [{'id': r['id'], 'username': r['username'], 'enabled': bool(r['enabled']),
                 'connection': r['connection'], 'last_seen': r['last_seen'], 'status': json.loads(r['status'])}
                for r in db.execute('SELECT * FROM agents ORDER BY name_key')]

    def snapshot(self):
        with self.db() as db:
            db.execute('BEGIN')
            board = dict(db.execute('SELECT * FROM board WHERE id=1').fetchone())
            board['layout'] = Layout.model_validate_json(board['layout'])
            board['attachments'] = json.loads(board['attachments'])
            board['agents'] = self.roster(db)
            return board

    def save_layout(self, layout):
        with self.db() as db:
            db.execute('UPDATE board SET layout=?,revision=revision+1 WHERE id=1', (layout.model_dump_json(),))

    def published(self, revision, message_id, channel_id, attachments):
        with self.db() as db:
            db.execute('UPDATE board SET published=?,message_id=?,channel_id=?,attachments=?,sent_at=?,retry_at=0,error=? WHERE id=1',
                       (revision, message_id, channel_id, json.dumps(attachments), self.clock(), ''))

    def failed(self, reason, delay):
        with self.db() as db:
            db.execute('UPDATE board SET error=?,retry_at=? WHERE id=1', (reason, self.clock() + delay))
