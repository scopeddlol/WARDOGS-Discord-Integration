import threading
from dataclasses import replace
from unittest.mock import Mock
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFontDatabase, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import desktop_app
from desktop_capture import CaptureCanvas
from desktop_config import Settings


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    instance.setStyleSheet(desktop_app.STYLE)
    return instance


@pytest.fixture
def window(app):
    widget = desktop_app.Window(smoke=True)
    yield widget
    widget.stop_event.set()
    widget.timer.stop()
    desktop_app.bot.log.removeHandler(widget.handler)
    widget.deleteLater()
    app.processEvents()


def test_settings_roundtrip_through_controls(window):
    window.inputs['name'].setText('Scout')
    window.inputs['server'].setChecked(False)
    window.inputs['scores'].setChecked(False)
    settings = window.collect()
    assert settings.name == 'Scout'
    assert not settings.server and not settings.scores
    assert not window.inputs['server_id'].isEnabled()


def test_start_stop_locks_settings_until_worker_finishes(window, monkeypatch):
    monkeypatch.setattr(window, 'save', lambda: True)
    monkeypatch.setattr(desktop_app, 'ocr_path', lambda: Mock(is_file=lambda: True))
    monkeypatch.setattr(desktop_app.bot, 'configure_desktop', Mock())
    def loop(dry_run, stop, callback):
        stop.wait(2)
    monkeypatch.setattr(desktop_app.bot, 'run_loop', loop)
    window.start()
    first_worker = window.worker
    window.start()
    assert window.worker is first_worker
    assert not window.save_button.isEnabled()
    assert not window.pages[0].isEnabled()
    window.stop()
    first_worker.join(2)
    window.tick()
    assert window.worker is None
    assert window.start_button.isEnabled()
    assert window.pages[0].isEnabled()


def test_connection_check_only_reads_discord(window, monkeypatch):
    window.inputs['token'].setText('fake-token')
    window.inputs['channel'].setText('123456789012345678')
    response = Mock(status_code=200, json=lambda: {'type': 0, 'name': 'test-channel'})
    get = Mock(return_value=response)
    import requests
    monkeypatch.setattr(requests, 'get', get)
    monkeypatch.setattr(window, 'background', lambda work: work())
    window.check_connection()
    window.tick()
    assert get.call_count == 2
    assert 'No message sent' in window.status.text()


def test_capture_selection_uses_image_coordinates(app):
    settings = Settings()
    canvas = CaptureCanvas(settings)
    canvas.resize(800, 500)
    canvas.pixmap = QPixmap(800, 400)
    canvas.show()
    app.processEvents()
    QTest.mousePress(canvas, Qt.LeftButton, pos=QPoint(80, 90))
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(400, 250))
    left, top, right, bottom = map(float, settings.capture_region.split(','))
    assert (left, top, right, bottom) == pytest.approx((0.1, 0.1, 0.5, 0.5))
    canvas.hide()
    canvas.deleteLater()

def test_invite_requires_only_token_and_minimum_permissions(window, monkeypatch):
    window.inputs['token'].setText('fake-token')
    window.inputs['channel'].setText('')
    import requests
    monkeypatch.setattr(requests, 'get', Mock(return_value=Mock(status_code=200, json=lambda: {'id': '123456789012345678'})))
    monkeypatch.setattr(window, 'background', lambda work: work())
    opened = []
    monkeypatch.setattr(desktop_app.QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()))
    window.invite_bot()
    window.tick()
    assert opened == ['https://discord.com/oauth2/authorize?client_id=123456789012345678&scope=bot&permissions=19456']
