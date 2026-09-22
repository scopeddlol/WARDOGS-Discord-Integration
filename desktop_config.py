"""Per-user settings; Windows DPAPI protects the bot token at rest."""
from dataclasses import asdict, dataclass, fields
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys


def data_dir():
    path = Path(os.environ["WARDOGS_DATA_DIR"]) if "WARDOGS_DATA_DIR" in os.environ else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WARDOGS Discord"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resources():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def protect_token(value, decrypt=False):
    if not value:
        return ""
    if sys.platform != "win32":
        raise OSError("Token storage requires Windows.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    raw = base64.b64decode(value, validate=True) if decrypt else value.encode("utf-8")
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    method = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    method.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    method.restype = wintypes.BOOL
    if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        output = ctypes.string_at(result.data, result.size)
        return output.decode("utf-8") if decrypt else base64.b64encode(output).decode("ascii")
    finally:
        kernel.LocalFree(result.data)


@dataclass
class Settings:
    token: str = ""
    channel: str = ""
    name: str = "Player"
    monitor: int = 1
    poll_seconds: int = 4
    score_seconds: int = 30
    server: bool = True
    server_id: bool = True
    queue: bool = True
    team: bool = True
    scores: bool = True
    offline: bool = True
    launch_at_login: bool = False
    auto_start: bool = False
    capture_region: str = "0,0.65,1,1"
    team_region: str = "0.960,0.925,0.990,0.965"
    score_region: str = "0.0169,0.9139,0.1497,0.9514"

    def validate(self):
        if not self.token.strip() or any(c.isspace() for c in self.token):
            raise ValueError("Paste a bot token from Discord's Developer Portal (without spaces).")
        if not self.channel.isascii() or not self.channel.isdigit() or not 17 <= len(self.channel) <= 20:
            raise ValueError("Enter a Discord text channel ID (17–20 digits).")
        if not 1 <= len(self.name.strip()) <= 60:
            raise ValueError("Your display name must contain 1–60 characters.")
        if not 2 <= self.poll_seconds <= 60 or not 15 <= self.score_seconds <= 600:
            raise ValueError("Scan interval must be 2–60 seconds; score updates 15–600 seconds.")
        if self.monitor < 1:
            raise ValueError("Choose a display before starting.")
        for value in (self.capture_region, self.team_region, self.score_region):
            try:
                left, top, right, bottom = map(float, value.split(","))
                valid = 0 <= left < right <= 1 and 0 <= top < bottom <= 1
            except (ValueError, AttributeError):
                valid = False
            if not valid:
                raise ValueError("Capture boxes are invalid. Reset them in Capture settings.")


def load_settings(path=None):
    path = path or data_dir() / "settings.json"
    if not path.exists():
        return Settings()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Settings must be a JSON object.")
    defaults = Settings()
    values = {}
    for field in fields(Settings):
        if field.name == "token":
            continue
        value = raw.get(field.name, getattr(defaults, field.name))
        if type(value) is not type(getattr(defaults, field.name)):
            raise ValueError(f"Invalid setting: {field.name}")
        values[field.name] = value
    values["token"] = protect_token(raw.get("protected_token", ""), decrypt=True)
    return Settings(**values)


def save_settings(settings, path=None):
    settings.validate()
    path = path or data_dir() / "settings.json"
    raw = asdict(settings)
    raw["protected_token"] = protect_token(raw.pop("token"))
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    temporary.replace(path)


def configure_startup(enabled):
    import winreg
    executable = Path(sys.executable)
    command = f'"{executable}" --background' if getattr(sys, "frozen", False) else (
        f'"{executable.with_name("pythonw.exe")}" "{resources() / "desktop_app.py"}" --background'
    )
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            winreg.SetValueEx(key, "WARDOGSDiscord", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "WARDOGSDiscord")
            except FileNotFoundError:
                pass
