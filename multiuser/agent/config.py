"""Separate agent settings, paths, startup identity and encrypted credentials."""
from dataclasses import dataclass, asdict, fields
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit, urlunsplit
from .credential_store import protect_token


def data_dir():
    path = Path(os.environ.get('WARDOGS_AGENT_DATA_DIR', str(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'WARDOGS Agent')))
    path.mkdir(parents=True, exist_ok=True)
    return path


def resources():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))


def normalize_url(value):
    value = value.strip().rstrip('/')
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or any(c.isspace() for c in value):
        raise ValueError('Enter your controller URL without credentials, a query, or a fragment.')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('Use an HTTPS controller URL. Plain HTTP is allowed only for local testing.')
    try:
        parsed.port
    except ValueError:
        raise ValueError('The controller URL has an invalid port.')
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), '', ''))


@dataclass
class Settings:
    url: str = ''
    username: str = ''
    agent_id: str = ''
    token: str = ''
    monitor: int = 1
    poll_seconds: int = 4
    server: bool = True
    server_id: bool = True
    queue: bool = True
    team: bool = True
    scores: bool = True
    offline: bool = True
    launch_at_login: bool = True
    reporting_enabled: bool = False
    start_when_game_runs: bool = True
    capture_region: str = '0,0.65,1,1'
    team_region: str = '0.960,0.925,0.990,0.965'
    score_region: str = '0.0169,0.9139,0.1497,0.9514'

    def validate(self, paired=False):
        self.url = normalize_url(self.url)
        if not 1 <= len(self.username.strip()) <= 40:
            raise ValueError('Enter the exact player username supplied by your controller host.')
        if paired and (not self.token or not self.agent_id):
            raise ValueError('Pair with your controller first.')
        if not 2 <= self.poll_seconds <= 60 or self.monitor < 1:
            raise ValueError('Choose a display and a scan interval between 2 and 60 seconds.')
        for region in (self.capture_region, self.team_region, self.score_region):
            try:
                l,t,r,b=map(float,region.split(','))
                valid=0<=l<r<=1 and 0<=t<b<=1
            except ValueError:
                valid=False
            if not valid:
                raise ValueError('Reset invalid capture boxes before continuing.')


def load(path=None):
    path = path or data_dir() / 'settings.json'
    if not path.exists():
        return Settings()
    raw=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(raw,dict):
        raise ValueError('Saved agent settings are invalid.')
    values={}
    defaults=Settings()
    for field in fields(Settings):
        if field.name=='token':continue
        # Older agents used auto_start for the saved on/off choice.
        value=raw.get(field.name,raw.get('auto_start',False) if field.name=='reporting_enabled' else getattr(defaults,field.name))
        if type(value) is not type(getattr(defaults,field.name)):
            raise ValueError('Invalid saved setting: '+field.name)
        values[field.name]=value
    values['token']=protect_token(raw.get('protected_token',''),decrypt=True)
    return Settings(**values)


def save(settings,path=None):
    settings.validate()
    path=path or data_dir()/'settings.json'
    raw=asdict(settings)
    raw['protected_token']=protect_token(raw.pop('token'))
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(raw,indent=2),encoding='utf-8')
    temporary.replace(path)


def startup(enabled):
    import winreg
    command=f'"{sys.executable}" --background' if getattr(sys,'frozen',False) else f'"{Path(sys.executable).with_name("pythonw.exe")}" "{resources()/"run_agent.py"}" --background'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:winreg.SetValueEx(key,'WARDOGSAgent',0,winreg.REG_SZ,command)
        else:
            try:winreg.DeleteValue(key,'WARDOGSAgent')
            except FileNotFoundError:pass
