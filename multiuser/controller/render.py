"""One bounded renderer shared by the builder preview and Discord publisher."""
from datetime import datetime, timezone
import re


def units(value):
    return len(value.encode('utf-16-le')) // 2


def clip(value, limit):
    if units(value) <= limit:
        return value
    return value.encode('utf-16-le')[:(limit - 1) * 2].decode('utf-16-le', errors='ignore') + '…'


def safe(value):
    return re.sub(r'([\\*_~`|>\[\]])', r'\\\1', str(value)).replace('@', '@\u200b')


def timestamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime('%H:%M UTC') if epoch else 'Never'


def fill(template, values):
    return '\n'.join(line for line in template.format_map(values).splitlines() if line.strip()).strip()


def embed_units(embed):
    return sum(units(v) for v in (embed.get('title', ''), embed.get('description', ''),
        embed.get('author', {}).get('name', ''), embed.get('footer', {}).get('text', ''))) + sum(
            units(f['name']) + units(f['value']) for f in embed.get('fields', []))


def render(layout, agents, now):
    connected = lambda p: p.get('connection') == 'connected'
    headers = dict(total=len(agents), online=sum(connected(p) for p in agents),
                   playing=sum(connected(p) and p['status']['activity'] == 'match' for p in agents), updated=timestamp(now))
    warnings = []
    def limited(text, maximum):
        result = clip(text, maximum)
        if result != text and 'Some expanded text was shortened to fit a Discord field limit.' not in warnings:
            warnings.append('Some expanded text was shortened to fit a Discord field limit.')
        return result
    embed = {'title': limited(fill(layout.title, headers), 256),
             'description': limited(fill(layout.description, headers), 4096), 'color': int(layout.color[1:], 16)}
    if layout.url:
        embed['url'] = layout.url
    if layout.timestamp:
        embed['timestamp'] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    if layout.author_name:
        embed['author'] = {'name': limited(fill(layout.author_name, headers), 256)}
        if layout.author_url:
            embed['author']['url'] = layout.author_url
        if layout.author_icon:
            embed['author']['icon_url'] = layout.author_icon
    if layout.footer:
        embed['footer'] = {'text': limited(fill(layout.footer, headers), 2048)}
        if layout.footer_icon:
            embed['footer']['icon_url'] = layout.footer_icon
    for key in ('thumbnail', 'image'):
        if getattr(layout, key):
            embed[key] = {'url': getattr(layout, key)}
    before, after = [], []
    for field in layout.custom_fields:
        value = {'name': limited(fill(field.name, headers), 256) or '\u200b',
                 'value': limited(fill(field.value, headers), 1024) or '\u200b', 'inline': field.inline}
        (before if field.position == 'before' else after).append(value)
    embed['fields'] = before + after
    used = embed_units(embed)
    if used > 5500:
        raise ValueError('The fixed embed content uses more than 5,500 characters. Shorten the text or custom fields to leave room for players.')
    candidates = [p for p in agents if layout.include_offline or connected(p)]
    if layout.order == 'name':
        candidates.sort(key=lambda p: p['username'].casefold())
    elif layout.order == 'recent':
        candidates.sort(key=lambda p: (-p.get('last_seen', 0), p['username'].casefold()))
    else:
        candidates.sort(key=lambda p: (not connected(p), p['status']['activity'] != 'match', p['username'].casefold()))
    player_fields, visible = [], []
    for player in candidates[:layout.max_players]:
        state = player['status']
        scores = state.get('scores')
        connection = player.get('connection', 'disconnected')
        values = {'username': safe(player['username']), 'status': safe(state.get('details') or state['activity'].capitalize()),
                  'team': safe(state.get('team') or ''), 'scores': '🔵 {}  🔴 {}  🟢 {}'.format(*scores) if scores else '',
                  'connection': connection.replace('_', ' ').capitalize(), 'updated': timestamp(player.get('last_seen')),
                  'icon': '🟢' if connection == 'connected' else '⚫'}
        details = state.get('details', '')
        server_id = re.search(r'ID ([0-9 -]+)', details)
        queued = re.search(r'position (\d+) of (\d+)', details)
        server = re.sub(r'\s*· ID [0-9 -]+$', '', details) if state['activity'] == 'match' else ''
        queue_server = re.search(r'^Queued for (.*?) \(position', details)
        if queue_server:
            server = queue_server.group(1)
        values.update(activity=state['activity'].capitalize(), server=safe(server),
                      server_id=safe(server_id.group(1).strip()) if server_id else '',
                      queue_position=queued.group(1) if queued else '', queue_total=queued.group(2) if queued else '',
                      lonestar_score=str(scores[0]) if scores else '', valkyra_score=str(scores[1]) if scores else '',
                      manticore_score=str(scores[2]) if scores else '')
        title = limited(fill(layout.player_title, values), 256) or safe(player['username'])
        body = limited(fill(layout.player_body, values), 1024) or 'No shared details'
        if layout.mode == 'cards':
            cost = units(title) + units(body)
            if len(before + player_fields + after) >= 24 or used + cost + 220 > 6000:
                break
            player_fields.append({'name': title, 'value': body, 'inline': layout.inline})
        else:
            line = '\n\n**' + title + '**\n' + body
            cost = units(line)
            if units(embed['description']) + cost + 220 > 4096 or used + cost + 220 > 6000:
                break
            embed['description'] += line
        used += cost
        visible.append(player['id'])
    omitted = len(candidates) - len(visible)
    if omitted:
        notice = f'{omitted} more player(s) do not fit. Use Compact, shorter templates, or a higher player limit. Full roster is in the controller.'
        warnings.append(notice)
        # A custom description can already be near 4096; put overflow in a reserved field.
        player_fields.append({'name': 'Additional players', 'value': notice, 'inline': False})
    if not candidates:
        player_fields.append({'name': 'Squad roster', 'value': 'No players to display. Pair an agent or include disconnected players.', 'inline': False})
    embed['fields'] = before + player_fields + after
    if not embed['fields']:
        embed.pop('fields')
    if not embed['title']:
        embed.pop('title')
    if not embed['description']:
        embed.pop('description')
    count = embed_units(embed)
    if count > 6000 or len(embed.get('fields', [])) > 25:
        raise ValueError('This layout exceeds Discord limits. Shorten fixed content and try again.')
    return {'embed': embed, 'characters': count, 'limit': 6000, 'shown': len(visible), 'total': len(agents),
            'omitted': omitted, 'hidden': len(agents) - len(candidates), 'warnings': warnings}


def asset_names(embed):
    refs = [embed.get(key, {}).get('url', '') for key in ('thumbnail', 'image')]
    refs += [embed.get(key, {}).get('icon_url', '') for key in ('author', 'footer')]
    return sorted({ref.removeprefix('attachment://') for ref in refs if ref.startswith('attachment://')})


def sample_players(count, now):
    names = ['Scout', 'Blade', 'Nova', 'Echo', 'Rook', 'Viper', 'Atlas', 'Ghost', 'Juno', 'Wolf']
    players = []
    for i in range(count):
        activity = ['match', 'match', 'queue', 'match', 'menu'][i % 5]
        online = i % 7 != 6
        status = {'activity': activity if online else 'disconnected',
                  'details': ('East #145 · ID 469-618' if activity == 'match' else
                              'Queued for Central #1 (position 3 of 12)' if activity == 'queue' else 'In the main menu') if online else 'Agent disconnected',
                  'team': ['Lonestar', 'Valkyra', 'Manticore'][i % 3] if activity == 'match' and online else None,
                  'scores': [125, 108, 94] if activity == 'match' and online else None}
        players.append({'id': str(i), 'username': names[i] if i < len(names) else f'Player {i+1}',
                        'status': status, 'connection': 'connected' if online else 'disconnected', 'last_seen': now - i * 4})
    return players
