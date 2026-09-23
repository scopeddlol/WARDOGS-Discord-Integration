"""HTTPS-proxy-ready API and same-origin controller administration."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import hmac
import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .assets import Assets, MAX_BYTES, MIMES
from .models import Layout, Pairing, Preview, Redeem, Report, Toggle
from .publisher import Publisher
from .render import render, sample_players, asset_names
from .store import Denied, Store, digest


@dataclass
class Config:
    data_dir: Path
    admin_token: str
    bot_token: str
    channel_id: str
    dry_run: bool = False
    publish_interval: int = 15
    stale_seconds: int = 90
    worker: bool = True

    @classmethod
    def from_env(cls):
        config = cls(Path(os.getenv('CONTROLLER_DATA_DIR', '/data')), os.getenv('CONTROLLER_ADMIN_TOKEN', ''),
                     os.getenv('DISCORD_BOT_TOKEN', ''), os.getenv('DISCORD_CHANNEL_ID', ''),
                     os.getenv('DISCORD_DRY_RUN', '0') == '1',
                     int(os.getenv('PUBLISH_INTERVAL_SECONDS', '15')), int(os.getenv('AGENT_TIMEOUT_SECONDS', '90')))
        if len(config.admin_token) < 32 or config.admin_token.startswith('CHANGE_'):
            raise ValueError('Set CONTROLLER_ADMIN_TOKEN to a unique secret of at least 32 characters.')
        if not config.dry_run and (not config.bot_token or not config.channel_id.isdigit()):
            raise ValueError('Configure the controller Discord bot token and text channel ID.')
        if config.publish_interval < 5 or config.stale_seconds < 45:
            raise ValueError('Publish interval must be at least 5 seconds; agent timeout at least 45 seconds.')
        return config


def create_app(config=None):
    config = config or Config.from_env()
    store = Store(config.data_dir / 'controller.sqlite3', config.admin_token)
    assets = Assets(config.data_dir / 'assets')
    publisher = Publisher(store, assets, config.bot_token, config.channel_id,
                          config.publish_interval, config.stale_seconds, config.dry_run)

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()
        async def run():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(publisher.tick)
                except Exception:
                    logging.getLogger("controller").exception("Publishing worker failed; retrying")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1)
                except TimeoutError:
                    pass
        task = asyncio.create_task(run()) if config.worker else None
        yield
        stop.set()
        if task:
            await task
        publisher.client.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.publisher, app.state.assets = store, publisher, assets

    @app.exception_handler(Denied)
    async def denied(request, error):
        return JSONResponse({'detail': str(error)}, status_code=403)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({'detail': str(error)}, status_code=422)

    @app.middleware('http')
    async def guard(request, call_next):
        maximum = MAX_BYTES if request.url.path == '/api/admin/assets' else 65_536
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > maximum:
                return JSONResponse({'detail': 'Request body too large.'}, status_code=413)
            data.extend(chunk)
        request._body = bytes(data)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    def bearer(request):
        value = request.headers.get('Authorization', '')
        if not value.startswith('Bearer ') or len(value) > 256:
            raise HTTPException(401, 'Authentication required.')
        return value[7:]

    def admin(request: Request):
        if not hmac.compare_digest(digest(bearer(request)), digest(config.admin_token)):
            key = 'admin:' + (request.client.host if request.client else 'unknown')
            if store.limited(key, 30):
                raise HTTPException(429, 'Too many unsuccessful sign-ins; wait a minute.')
            raise HTTPException(401, 'Admin key was rejected.')

    @app.get('/healthz')
    def health():
        with store.db() as db:
            db.execute('SELECT 1').fetchone()
        return {'ok': True}

    @app.post('/api/v1/pair')
    def pair(body: Redeem, request: Request):
        key = 'pair:' + (request.client.host if request.client else 'unknown')
        if store.limited(key):
            raise HTTPException(429, 'Too many pairing attempts; wait a minute.')
        return store.redeem(body.username, body.pin)

    @app.post('/api/v1/session')
    def session(request: Request):
        return store.start(bearer(request))

    @app.put('/api/v1/status')
    def report(body: Report, request: Request):
        return store.report(bearer(request), body)

    @app.get('/api/admin/state', dependencies=[Depends(admin)])
    def current():
        store.expire(config.stale_seconds)
        board = store.snapshot()
        preview = render(board['layout'], board['agents'], store.clock())
        return {'agents': board['agents'], 'layout': board['layout'], 'preview': preview,
                'delivery': {'error': board['error'], 'last_sent': board['sent_at'],
                             'pending': board['revision'] != board['published'], 'dry_run': config.dry_run,
                             'message_id': board['message_id'], 'channel_id': config.channel_id}}

    @app.post('/api/admin/pairings', dependencies=[Depends(admin)])
    def invite(body: Pairing):
        return store.create_pin(body.username)

    @app.put('/api/admin/agents/{agent_id}', dependencies=[Depends(admin)])
    def toggle(agent_id: str, body: Toggle):
        try:
            store.control(agent_id, enabled=body.enabled)
        except KeyError:
            raise HTTPException(404, 'Player not found.')
        return {'ok': True}

    @app.delete('/api/admin/agents/{agent_id}/credential', dependencies=[Depends(admin)])
    def revoke(agent_id: str):
        try:
            store.control(agent_id, revoke=True)
        except KeyError:
            raise HTTPException(404, 'Player not found.')
        return {'ok': True}

    def validate_assets(preview):
        total = sum(assets.file(name).stat().st_size for name in asset_names(preview['embed']))
        if total > MAX_BYTES:
            raise ValueError('Uploaded images in one message must total at most 8 MB. Use smaller images or HTTPS image URLs.')

    @app.post('/api/admin/preview', dependencies=[Depends(admin)])
    def preview(body: Preview):
        now = store.clock()
        players = store.roster() if body.sample_count is None else sample_players(body.sample_count, now)
        result = render(body.layout, players, now)
        validate_assets(result)
        return result

    @app.put('/api/admin/layout', dependencies=[Depends(admin)])
    def save_layout(body: Layout):
        result = render(body, store.roster(), store.clock())
        validate_assets(result)
        store.save_layout(body)
        return {'ok': True, 'preview': result}

    @app.post('/api/admin/assets', dependencies=[Depends(admin)])
    async def upload(request: Request):
        return await asyncio.to_thread(assets.add, await request.body())

    @app.get('/api/admin/assets/{name}', dependencies=[Depends(admin)])
    def asset(name: str):
        try:
            path = assets.file(name)
        except ValueError:
            raise HTTPException(404, 'Image not found.')
        return FileResponse(path, media_type=MIMES[name.rsplit('.', 1)[1]])

    static = Path(__file__).parent / 'static'
    app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/')
    def dashboard():
        return FileResponse(static / 'index.html')

    return app
