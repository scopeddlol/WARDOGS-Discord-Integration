"""Validated wire protocol and the editable, bounded Discord layout."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re
import string
import unicodedata


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


def clean_username(value):
    value = unicodedata.normalize('NFKC', value).strip()
    if not 1 <= len(value) <= 40 or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('Use a player name of 1–40 printable characters.')
    return value


class Pairing(StrictModel):
    username: str
    _name = field_validator('username')(clean_username)


class Redeem(Pairing):
    pin: str = Field(pattern=r'^\d{8}$')


class Report(StrictModel):
    session_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    sequence: int = Field(ge=1, le=2**53)
    activity: Literal['waiting', 'menu', 'match', 'queue', 'paused']
    details: str = Field(default='', max_length=240)
    team: Literal['Lonestar', 'Valkyra', 'Manticore'] | None = None
    scores: tuple[int, int, int] | None = None

    @field_validator('scores')
    @classmethod
    def valid_scores(cls, value):
        if value is not None and any(not 0 <= score <= 999 for score in value):
            raise ValueError('Scores must be between 0 and 999.')
        return value

    @field_validator('details')
    @classmethod
    def plain_details(cls, value):
        if any(unicodedata.category(c).startswith('C') for c in value):
            raise ValueError('Status details must be a single line of printable text.')
        return value.strip()


PLAYER_VARIABLES = {'username', 'status', 'team', 'scores', 'connection', 'updated', 'icon', 'activity', 'server', 'server_id', 'queue_position', 'queue_total', 'lonestar_score', 'valkyra_score', 'manticore_score'}
HEADER_VARIABLES = {'total', 'online', 'playing', 'updated'}


def validate_template(value, allowed):
    for _, field, spec, conversion in string.Formatter().parse(value):
        if field is not None and (field not in allowed or spec or conversion):
            raise ValueError('Available placeholders: ' + ', '.join('{' + v + '}' for v in sorted(allowed)))
    return value


def image_reference(value):
    if not value:
        return value
    if re.fullmatch(r'attachment://[a-f0-9]{64}\.(png|jpg|gif|webp)', value):
        return value
    from urllib.parse import urlsplit
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use an HTTPS image URL or an image uploaded in the builder.')
    return value


def web_link(value):
    if value:
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Links must use HTTPS and have no embedded credentials.')
    return value


class CustomField(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    value: str = Field(min_length=1, max_length=1024)
    inline: bool = False
    position: Literal['before', 'after'] = 'after'

    @field_validator('name', 'value')
    @classmethod
    def template(cls, value):
        return validate_template(value, HEADER_VARIABLES)


class Layout(StrictModel):
    title: str = Field(default='WARDOGS · Squad status', max_length=256)
    description: str = Field(default='{online} connected · {playing} in a match · {total} players', max_length=4096)
    footer: str = Field(default='Live squad status · WARDOGS Controller', max_length=2048)
    color: str = Field(default='#d9ef61', pattern=r'^#[0-9a-fA-F]{6}$')
    mode: Literal['cards', 'compact'] = 'cards'
    inline: bool = True
    order: Literal['name', 'activity', 'recent'] = 'activity'
    include_offline: bool = True
    max_players: int = Field(default=24, ge=1, le=100)
    player_title: str = Field(default='{icon} {username}', min_length=1, max_length=256)
    player_body: str = Field(default='{status}\n{team}\n{scores}', min_length=1, max_length=1024)
    url: str = Field(default='', max_length=1000)
    author_name: str = Field(default='', max_length=256)
    author_url: str = Field(default='', max_length=1000)
    author_icon: str = Field(default='', max_length=1500)
    footer_icon: str = Field(default='', max_length=1500)
    image: str = Field(default='', max_length=1500)
    thumbnail: str = Field(default='', max_length=1500)
    timestamp: bool = True
    custom_fields: list[CustomField] = Field(default_factory=list, max_length=20)

    _images = field_validator('image', 'thumbnail', 'author_icon', 'footer_icon')(image_reference)
    _links = field_validator('url', 'author_url')(web_link)

    @field_validator('title', 'description', 'footer', 'author_name')
    @classmethod
    def header_template(cls, value):
        return validate_template(value, HEADER_VARIABLES)

    @field_validator('player_title', 'player_body')
    @classmethod
    def player_template(cls, value):
        return validate_template(value, PLAYER_VARIABLES)


class Preview(StrictModel):
    layout: Layout
    sample_count: int | None = Field(default=None, ge=0, le=100)


class Toggle(StrictModel):
    enabled: bool
