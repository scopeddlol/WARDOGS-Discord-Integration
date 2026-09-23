"""Single-message, coalescing publisher. Agents never call Discord."""
import json
import hashlib
import httpx
from .render import render, asset_names


class Publisher:
    def __init__(self, store, assets, token, channel, interval=15, stale_seconds=90, dry_run=False, client=None):
        self.store, self.assets, self.channel = store, assets, channel
        self.interval, self.stale_seconds, self.dry_run = interval, stale_seconds, dry_run
        self.client = client or httpx.Client(timeout=10, follow_redirects=False,
            headers={'Authorization': 'Bot ' + token, 'User-Agent': 'WARDOGS-Controller/1.0'})

    def payload(self, embed, previous):
        body = {'content': '', 'embeds': [embed], 'allowed_mentions': {'parse': []}, 'attachments': []}
        files = {}
        for name in asset_names(embed):
            if name in previous:
                body['attachments'].append({'id': previous[name], 'filename': name})
            else:
                number = len(files)
                data, mime = self.assets.read(name)
                body['attachments'].append({'id': number, 'filename': name})
                files[f'files[{number}]'] = (name, data, mime)
        return body, files

    def send(self, board, embed, create=False):
        message_id = None if create or board['channel_id'] != self.channel else board['message_id']
        body, files = self.payload(embed, board['attachments'] if message_id else {})
        url = f'https://discord.com/api/v10/channels/{self.channel}/messages'
        if message_id:
            url += '/' + message_id
        else:
            # Discord deduplicates a retried creation if the first response was lost.
            identity = board['create_nonce'] + self.channel + (board['message_id'] or '')
            body.update(nonce=hashlib.sha256(identity.encode()).hexdigest()[:24], enforce_nonce=True)
        kwargs = {'data': {'payload_json': json.dumps(body)}, 'files': files} if files else {'json': body}
        response = self.client.request('PATCH' if message_id else 'POST', url, **kwargs)
        if response.status_code == 404 and message_id and response.json().get('code') == 10008:
            return self.send(board, embed, create=True)
        return response

    def tick(self):
        self.store.expire(self.stale_seconds)
        board, now = self.store.snapshot(), self.store.clock()
        if now < board['retry_at'] or now - board['sent_at'] < self.interval:
            return
        if board['revision'] == board['published'] and board['channel_id'] == self.channel and now - board['sent_at'] < 300:
            return
        try:
            preview = render(board['layout'], board['agents'], now)
            if self.dry_run:
                self.store.published(board['revision'], 'dry-run', self.channel, {})
                return
            response = self.send(board, preview['embed'])
            if response.status_code == 429:
                delay = max(1, min(float(response.json().get('retry_after', 5)), 3600))
                self.store.failed('Discord rate limit; retry scheduled.', delay)
            elif response.is_success:
                data = response.json()
                attachments = {a['filename']: a['id'] for a in data.get('attachments', [])}
                self.store.published(board['revision'], data['id'], self.channel, attachments)
            else:
                reason = {401: 'Discord rejected the controller bot token.',
                          403: 'Allow View Channel, Send Messages, Embed Links and Attach Files for the bot.',
                          404: 'Discord channel not found. Check the controller channel ID.'}.get(
                              response.status_code, f'Discord returned HTTP {response.status_code}; retry scheduled.')
                self.store.failed(reason, 30)
        except (httpx.HTTPError, ValueError, KeyError, OSError):
            self.store.failed('Publishing failed. Check connectivity, the layout, and uploaded images.', 30)
