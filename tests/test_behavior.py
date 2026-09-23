"""Behavior tests; no live Discord requests or screenshots."""
from dataclasses import replace
import json
import threading
from unittest.mock import Mock
import pytest

from desktop_config import Settings, load_settings, save_settings
from broadcast_policy import filter_status
import wardogs_status_bot as bot

VALID = Settings(token="example-token", channel="123456789012345678", name="Scout")
OFFLINE = "Scout is not in a game"
MATCH = "Lonestar · East #145 · ID 469618"


def test_private_details_cannot_leak_from_saved_match():
    settings = replace(VALID, server=False, team=False, scores=False)
    assert filter_status(MATCH, (10, 20, 30), settings, OFFLINE) == ("In a match", None)


@pytest.mark.parametrize("text", ["Queued for East #145 (position 2 of 8)", "Queued (ID 123-456, position 2 of 8)"])
def test_queue_respects_server_privacy(text):
    assert filter_status(text, None, replace(VALID, server=False), OFFLINE) == ("Queued (position 2 of 8)", None)
    assert filter_status(text, None, replace(VALID, queue=False), OFFLINE) == ("WARDOGS is running", None)


def test_id_and_offline_filters():
    assert "469618" not in filter_status(MATCH, None, replace(VALID, server_id=False), OFFLINE)[0]
    assert filter_status("Queued (ID 123-456, position 2 of 8)", None, replace(VALID, server_id=False), OFFLINE)[0] == "Queued (position 2 of 8)"
    assert filter_status(OFFLINE, (1, 2, 3), replace(VALID, offline=False), OFFLINE) == ("Offline", None)


@pytest.mark.parametrize("changes", [{"channel": "abc"}, {"channel": "123"}, {"token": "with spaces"},
    {"name": ""}, {"poll_seconds": 0}, {"score_seconds": 1}, {"capture_region": "0,0,0,0"},
    {"capture_region": "nan,0,1,1"}])
def test_invalid_settings_rejected(changes):
    with pytest.raises(ValueError):
        replace(VALID, **changes).validate()


def test_token_is_encrypted_and_settings_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(VALID, path)
    assert VALID.token not in path.read_text()
    assert "\"token\"" not in path.read_text()
    assert load_settings(path) == VALID


def test_malformed_settings_not_silently_overwritten(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"auto_start": "false"}')
    with pytest.raises(ValueError):
        load_settings(path)
    assert '"false"' in path.read_text()


def test_changed_channel_does_not_reuse_message(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(bot, "DISCORD_STATUS_CHANNEL_ID", "first")
    bot.save_state("old match", "old-message")
    assert bot.load_state()[1] == "old-message"
    monkeypatch.setattr(bot, "DISCORD_STATUS_CHANNEL_ID", "second")
    assert bot.load_state() == (None, None, None)


def test_deleted_message_recreated(monkeypatch):
    patch = Mock(return_value=Mock(status_code=404, json=lambda: {"code": 10008}))
    post = Mock(return_value=Mock(status_code=200, ok=True, json=lambda: {"id": "new"}))
    monkeypatch.setattr(bot.requests, "patch", patch)
    monkeypatch.setattr(bot.requests, "post", post)
    assert bot.set_status_message("In a match", "deleted") == (True, None, "new")
    assert post.call_args.kwargs["json"]["allowed_mentions"] == {"parse": []}


def test_rate_limit_retains_message(monkeypatch):
    monkeypatch.setattr(bot.requests, "patch", Mock(return_value=Mock(status_code=429, json=lambda: {"retry_after": 12})))
    assert bot.set_status_message("In a match", "existing") == (False, 12, "existing")


def test_stop_during_capture_prevents_send(monkeypatch):
    stop = threading.Event()
    monkeypatch.setattr(bot, "DISCORD_BOT_TOKEN", "token")
    monkeypatch.setattr(bot, "DISCORD_STATUS_CHANNEL_ID", "channel")
    monkeypatch.setattr(bot, "load_state", lambda: (None, None, None))
    monkeypatch.setattr(bot, "is_game_running", lambda: True)
    monkeypatch.setattr(bot, "is_game_foreground", lambda: True)
    def capture(**kwargs):
        stop.set()
        return "", "East #1 · ID 123456", "Lonestar", None
    monkeypatch.setattr(bot, "capture_and_parse", capture)
    send = Mock()
    monkeypatch.setattr(bot, "set_status_message", send)
    bot.run_loop(False, stop)
    send.assert_not_called()


def test_restart_does_not_publish_saved_match(monkeypatch):
    stop = threading.Event()
    monkeypatch.setattr(bot, "DISCORD_BOT_TOKEN", "token")
    monkeypatch.setattr(bot, "DISCORD_STATUS_CHANNEL_ID", "channel")
    monkeypatch.setattr(bot, "load_state", lambda: ("Old server · ID 123456", "id", 0))
    monkeypatch.setattr(bot, "is_game_running", lambda: False)
    monkeypatch.setattr(bot, "save_state", Mock())
    sent = []
    def send(text, message_id, scores):
        sent.append(text)
        stop.set()
        return True, None, message_id
    monkeypatch.setattr(bot, "set_status_message", send)
    bot.run_loop(False, stop)
    assert sent == [bot.NOT_IN_GAME]


def test_ocr_parsing_regression():
    assert bot.parse_server("CURRENT SERVER WARDOGS (East) #145\nSERVER ID 469-618") == "East #145 · ID 469-618"
    assert bot.parse_queue("IN SERVER QUEUE Position 2 of 8 (East) #145") == "Queued for East #145 (position 2 of 8)"
    assert bot.determine_status("SERVER BROWSER") == bot.NOT_IN_GAME

def test_app_process_does_not_count_as_game(monkeypatch):
    monkeypatch.setattr(bot, 'GAME_PROCESS_SUBSTRING', 'wardogsclient')
    monkeypatch.setattr(bot.psutil, 'process_iter', lambda attrs: [Mock(pid=1, info={'name': 'WARDOGS Discord.exe'})])
    assert not bot.is_game_running()
    monkeypatch.setattr(bot.psutil, 'process_iter', lambda attrs: [Mock(pid=1, info={'name': 'WardogsClient-Win64-Shipping.exe'})])
    assert bot.is_game_running()


def test_background_game_uses_window_capture(monkeypatch):
    stop = threading.Event()
    monkeypatch.setattr(bot, 'DISCORD_BOT_TOKEN', 'token')
    monkeypatch.setattr(bot, 'DISCORD_STATUS_CHANNEL_ID', 'channel')
    monkeypatch.setattr(bot, 'load_state', lambda: (None, None, None))
    monkeypatch.setattr(bot, 'is_game_running', lambda: True)
    monkeypatch.setattr(bot, 'is_game_foreground', lambda: False)
    capture = Mock(side_effect=lambda **kwargs: (stop.set(), ('', None, None, None))[1])
    monkeypatch.setattr(bot, 'capture_and_parse', capture)
    bot.run_loop(False, stop)
    capture.assert_called_once_with(require_foreground=False)


def test_focus_loss_between_regions_discards_reading(monkeypatch):
    capture = Mock()
    capture.monitors = [{}, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
    context = Mock()
    context.__enter__ = Mock(return_value=capture)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(bot.mss, "MSS", lambda: context)
    monkeypatch.setattr(bot, "MONITOR_INDEX", 1)
    monkeypatch.setattr(bot, "is_game_foreground", lambda: False)
    with pytest.raises(bot.CaptureInterrupted):
        bot.grab_region("0,0,1,1", require_foreground=True)
    capture.grab.assert_not_called()


def test_malformed_runtime_state_recovers(monkeypatch, tmp_path):
    path = tmp_path / "last_status.json"
    path.write_text("[]")
    monkeypatch.setattr(bot, "STATE_FILE", str(path))
    assert bot.load_state() == (None, None, None)


def test_standalone_steam_author_and_hud_match(monkeypatch):
    settings = replace(VALID, steam_url='https://steamcommunity.com/id/scout')
    monkeypatch.setattr(bot, 'DESKTOP_SETTINGS', settings)
    monkeypatch.setattr(bot, 'DISPLAY_NAME', 'Scout')
    monkeypatch.setattr(bot, 'NOT_IN_GAME', OFFLINE)
    embed = bot._build_embed('In a match', (13, 90, 42))
    assert embed['author'] == {'name': 'Scout', 'url': settings.steam_url}
    assert 'In a match' in embed['description']
    assert bot._build_embed(OFFLINE)['description'] == 'Offline'
