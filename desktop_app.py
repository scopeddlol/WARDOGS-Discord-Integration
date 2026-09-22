"""Windows desktop entry point. All screen reading and HTTP work runs off the UI thread."""
import argparse
from dataclasses import replace
import logging
import os
from pathlib import Path
import queue
import sys
import threading

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QDesktopServices, QIcon, QFontDatabase
from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSystemTrayIcon, QTabWidget, QVBoxLayout, QWidget)

from desktop_config import Settings, configure_startup, data_dir, load_settings, resources, save_settings

# Set paths before importing the legacy engine. Nothing writes into Program Files.
os.environ["WARDOGS_DATA_DIR"] = str(data_dir())
import wardogs_status_bot as bot
from desktop_capture import CaptureDialog

STYLE = """
QWidget { background: #111820; color: #e9eef5; font: 10pt 'Segoe UI'; }
QMainWindow { background: #111820; }
QLabel#eyebrow { color: #d9ef61; font-size: 9pt; font-weight: 700; }
QLabel#heading { font-size: 27pt; font-weight: 700; }
QLabel#muted { color: #9eafc1; }
QLabel#status { background: #202c38; border-radius: 8px; padding: 15px; font-size: 12pt; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit { background: #0b1219; border: 1px solid #364555;
    border-radius: 5px; padding: 8px; selection-background-color: #516322; }
QPushButton { background: #253240; border: 1px solid #405064; border-radius: 5px; padding: 10px 16px; }
QPushButton:hover { background: #344657; }
QPushButton#primary { color: #15200a; background: #d9ef61; border: 0; font-weight: 700; }
QPushButton:disabled, QWidget:disabled { color: #697988; }
QTabWidget::pane { border: 1px solid #2d3c4b; border-radius: 6px; }
QTabBar::tab { background: #192430; padding: 12px 20px; }
QTabBar::tab:selected { color: #d9ef61; border-bottom: 2px solid #d9ef61; }
QCheckBox { spacing: 12px; padding: 3px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #6e8194; border-radius: 3px; background: #0b1219; }
QCheckBox::indicator:checked { background: #d9ef61; image: url(); border: 3px solid #516322; }
"""


def label(text, name=None):
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.PlainText)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    if primary:
        widget.setObjectName("primary")
    return widget


def ocr_path():
    bundled = resources() / "tesseract" / "tesseract.exe"
    return bundled if bundled.exists() else Path(os.environ.get("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"))


class ActivityHandler(logging.Handler):
    def __init__(self, events):
        super().__init__()
        self.events = events

    def emit(self, record):
        message = self.format(record)
        if bot.DISCORD_BOT_TOKEN:
            message = message.replace(bot.DISCORD_BOT_TOKEN, "[token hidden]")
        self.events.put(("log", message))


class Window(QMainWindow):
    def __init__(self, smoke=False):
        super().__init__()
        self.smoke = smoke
        self.events = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()
        self.quitting = False
        self.busy = False
        self.tray = None
        self.startup_error = None
        try:
            self.settings = Settings() if smoke else load_settings()
        except (ValueError, OSError, TypeError) as error:
            self.settings = Settings()
            self.startup_error = "Your saved settings could not be loaded. Re-enter them and Save settings. " + str(error)
        self.setWindowTitle("WARDOGS Discord")
        self.setWindowIcon(QIcon(str(resources() / "tray_icon.png")))
        self.resize(880, 780)
        self.setMinimumSize(740, 700)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(14)
        layout.addWidget(label("WARDOGS  /  DISCORD COMPANION", "eyebrow"))
        layout.addWidget(label("Your squad. In the loop.", "heading"))
        layout.addWidget(label("One live Discord message. You choose what it shares.", "muted"))
        self.status = label("Broadcast is off", "status")
        layout.addWidget(self.status)
        controls = QHBoxLayout()
        self.start_button = button("Start broadcasting", self.start, True)
        self.stop_button = button("Stop", self.stop)
        self.stop_button.setEnabled(False)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addStretch()
        self.save_button = button("Save settings", self.save)
        controls.addWidget(self.save_button)
        layout.addLayout(controls)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.pages = []
        self.inputs = {}
        self.connection_page()
        self.broadcast_page()
        self.capture_page()
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(500)
        self.tabs.addTab(self.activity, "Activity")
        layout.addWidget(label("Screen text is processed on this PC. Only the selected status details go to Discord.\n"
                               "Closing this window keeps the app in the tray. Use Stop to disable broadcasting.", "muted"))
        self.setCentralWidget(central)
        self.handler = ActivityHandler(self.events)
        self.handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%H:%M:%S"))
        bot.log.addHandler(self.handler)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        if not smoke and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            menu = QMenu(self)
            menu.addAction("Open settings", self.show_window)
            self.tray_start = menu.addAction("Start broadcasting", self.start)
            self.tray_stop = menu.addAction("Stop broadcasting", self.stop)
            self.tray_stop.setEnabled(False)
            menu.addSeparator()
            menu.addAction("Quit", self.quit_app)
            self.tray.setContextMenu(menu)
            self.tray.setToolTip("WARDOGS Discord — broadcast off")
            self.tray.activated.connect(lambda reason: self.show_window() if reason == QSystemTrayIcon.DoubleClick else None)
            self.tray.show()
        if self.startup_error:
            QTimer.singleShot(0, lambda: self.error(self.startup_error))
        elif not smoke and self.settings.auto_start:
            QTimer.singleShot(0, self.start)

    def page(self, title):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, title)
        self.pages.append(page)
        return layout

    def field(self, form, key, title, password=False):
        widget = QLineEdit(str(getattr(self.settings, key)))
        widget.setAccessibleName(title)
        if password:
            widget.setEchoMode(QLineEdit.Password)
        form.addRow(title, widget)
        self.inputs[key] = widget
        return widget

    def check(self, layout, key, title):
        widget = QCheckBox(title)
        widget.setChecked(getattr(self.settings, key))
        self.inputs[key] = widget
        layout.addWidget(widget)
        return widget

    def connection_page(self):
        layout = self.page("Connection")
        layout.addWidget(label("01  CONNECT YOUR DISCORD BOT", "eyebrow"))
        layout.addWidget(label("Create an application in Discord, open Bot and copy its token. Paste the token below, then click "
                               "Invite bot to server. The invite requests only the three permissions it needs.", "muted"))
        row = QHBoxLayout()
        row.addWidget(button("Open Developer Portal", lambda: QDesktopServices.openUrl(QUrl("https://discord.com/developers/applications"))))
        row.addWidget(button("Invite bot to server", self.invite_bot))
        row.addWidget(button("Setup guide", lambda: QDesktopServices.openUrl(QUrl("https://github.com/scopeddlol/WARDOGS-Discord-Integration/blob/master/docs/SETUP.md"))))
        row.addStretch()
        layout.addLayout(row)
        form = QFormLayout()
        form.setSpacing(12)
        self.field(form, "name", "Your display name")
        token = self.field(form, "token", "Bot token", True)
        token.setPlaceholderText("Stored with Windows encryption")
        show = QCheckBox("Show token")
        show.toggled.connect(lambda checked: token.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password))
        form.addRow("", show)
        self.field(form, "channel", "Text channel ID").setPlaceholderText("Right-click a Discord channel → Copy Channel ID")
        layout.addLayout(form)
        layout.addWidget(label("To copy IDs, turn on Discord Settings → Advanced → Developer Mode.", "muted"))
        row = QHBoxLayout()
        row.addWidget(button("Check connection", self.check_connection))
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()

    def broadcast_page(self):
        layout = self.page("Broadcast")
        layout.addWidget(label("02  CHOOSE WHAT TO SHARE", "eyebrow"))
        for key, title in [("server", "Server name and region"), ("server_id", "Server ID — lets friends find your match"),
                           ("queue", "Queue position"), ("team", "Faction / team"),
                           ("scores", "Live team scores"), ("offline", "Not-in-game status")]:
            self.check(layout, key, title)
        self.inputs["server"].toggled.connect(self.inputs["server_id"].setEnabled)
        self.inputs["server_id"].setEnabled(self.settings.server)
        layout.addWidget(label("Disabled details are removed on the next update. With server or queue details off, "
                               "a generic activity message is shown. Stop leaves the last Discord message in place.", "muted"))
        layout.addStretch()
        self.check(layout, "launch_at_login", "Open the app when I sign in to Windows")
        self.check(layout, "auto_start", "Start broadcasting automatically when the app opens")

    def capture_page(self):
        layout = self.page("Capture")
        layout.addWidget(label("03  GAME DETECTION", "eyebrow"))
        layout.addWidget(label("Server details are read from the pause menu. Open it briefly after joining. "
                               "For faction detection, set the game's Interface → Faction to Always On.", "muted"))
        form = QFormLayout()
        self.monitor = QComboBox()
        try:
            import mss
            with mss.MSS() as capture:
                for index, monitor in enumerate(capture.monitors[1:], 1):
                    self.monitor.addItem(f"Display {index} · {monitor['width']} × {monitor['height']}", index)
        except Exception:
            self.monitor.addItem("No displays available", 0)
        self.monitor.setAccessibleName("Game display")
        self.monitor.setCurrentIndex(max(0, self.monitor.findData(self.settings.monitor)))
        form.addRow("Game display", self.monitor)
        for key, title, minimum, maximum in [("poll_seconds", "Scan every (seconds)", 2, 60),
                                              ("score_seconds", "Update scores every (seconds)", 15, 600)]:
            widget = QSpinBox()
            widget.setRange(minimum, maximum)
            widget.setValue(getattr(self.settings, key))
            form.addRow(title, widget)
            self.inputs[key] = widget
        layout.addLayout(form)
        layout.addWidget(button("Adjust capture boxes…", self.calibrate))
        self.read_button = button("Read screen in 5 seconds", self.preview)
        layout.addWidget(self.read_button)
        self.preview_result = label("Test a reading here before broadcasting. No Discord message is sent.", "muted")
        layout.addWidget(self.preview_result)
        layout.addStretch()
        layout.addWidget(label("OCR engine: " + ("Bundled and ready" if ocr_path().exists() else "Missing — use the Windows installer"), "muted"))

    def collect(self):
        settings = replace(self.settings)
        for key, widget in self.inputs.items():
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                value = widget.value()
            else:
                value = widget.text().strip()
            setattr(settings, key, value)
        settings.monitor = self.monitor.currentData() or 0
        return settings

    def error(self, text):
        self.status.setText(text)
        self.show_window()
        QMessageBox.warning(self, "WARDOGS Discord", text)

    def save(self):
        try:
            settings = self.collect()
            save_settings(settings)
            configure_startup(settings.launch_at_login)
            self.settings = settings
            self.status.setText("Settings saved · broadcast is off")
            return True
        except (ValueError, OSError) as error:
            self.error(str(error))
            return False

    def lock(self, active):
        for page in self.pages:
            page.setEnabled(not active)
        self.start_button.setEnabled(not active)
        self.save_button.setEnabled(not active)
        self.stop_button.setEnabled(active and self.worker is not None)
        if self.tray:
            self.tray_start.setEnabled(not active)
            self.tray_stop.setEnabled(active and self.worker is not None)

    def start(self):
        if self.worker or self.busy:
            return
        if not ocr_path().is_file():
            self.error("OCR engine is missing. Reinstall using WARDOGS-Discord-Setup.exe.")
            return
        if not self.save():
            return
        bot.configure_desktop(self.settings, ocr_path())
        self.stop_event.clear()
        self.worker = threading.Thread(target=self.run_worker, daemon=True)
        self.lock(True)
        self.status.setText("Broadcast enabled · watching for WARDOGS")
        self.worker.start()
        if self.tray:
            self.tray.setToolTip("WARDOGS Discord — broadcasting enabled")

    def run_worker(self):
        try:
            bot.run_loop(False, self.stop_event, lambda text: self.events.put(("status", text)))
        except BaseException as error:
            self.events.put(("error", f"Broadcast stopped: {type(error).__name__}. See Activity for details."))
        finally:
            self.events.put(("stopped", None))

    def stop(self):
        if self.worker:
            self.stop_event.set()
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping · finishing the current read or request…")

    def background(self, work):
        if self.worker or self.busy:
            return
        self.busy = True
        self.lock(True)
        def run():
            try:
                work()
            except Exception as error:
                # Do not put HTTP request objects or credentials into the UI/log.
                self.events.put(("error", str(error) if isinstance(error, ValueError) else
                                 f"Operation failed ({type(error).__name__}). Check your connection and settings."))
            finally:
                self.events.put(("idle", None))
        threading.Thread(target=run, daemon=True).start()

    def invite_bot(self):
        token = self.inputs["token"].text().strip()
        if not token or any(char.isspace() for char in token):
            self.error("Paste your bot token first, then click Invite bot to server.")
            return
        def work():
            import requests
            response = requests.get("https://discord.com/api/v10/users/@me",
                                    headers={"Authorization": f"Bot {token}"}, timeout=10)
            if response.status_code != 200:
                raise ValueError("Discord could not verify this bot token. Check it and try again.")
            bot_id = response.json().get("id", "")
            if not bot_id.isdigit():
                raise ValueError("Discord did not return a valid bot identity.")
            self.events.put(("invite", "https://discord.com/oauth2/authorize?client_id=" + bot_id
                             + "&scope=bot&permissions=19456"))
        self.background(work)

    def check_connection(self):
        try:
            settings = self.collect()
            settings.validate()
        except ValueError as error:
            self.error(str(error))
            return
        self.status.setText("Checking Discord connection…")
        def work():
            import requests
            headers = {"Authorization": f"Bot {settings.token}"}
            for route in ("users/@me", f"channels/{settings.channel}"):
                response = requests.get("https://discord.com/api/v10/" + route, headers=headers, timeout=10)
                if response.status_code != 200:
                    descriptions = {401: "Discord rejected the bot token.", 403: "The bot cannot access this channel.",
                                    404: "Channel not found. Check its ID and bot access.", 429: "Discord is rate limiting requests. Try again shortly."}
                    raise ValueError(descriptions.get(response.status_code, f"Discord returned HTTP {response.status_code}. Try again."))
                result = response.json()
            if result.get("type") != 0:
                raise ValueError("Choose a regular server text channel, not a forum, voice channel, or thread.")
            self.events.put(("notice", f"Connected to #{result.get('name', 'channel')}. No message sent. Allow Send Messages and Embed Links before starting."))
        self.background(work)

    def calibrate(self):
        settings = self.collect()
        dialog = CaptureDialog(settings, self)
        if dialog.exec():
            for key in ("capture_region", "team_region", "score_region"):
                setattr(self.settings, key, getattr(settings, key))
            self.status.setText("Capture boxes adjusted · click Save settings to keep them")

    def preview(self):
        if not ocr_path().exists():
            self.error("OCR engine is missing. Use the Windows installer.")
            return
        settings = self.collect()
        self.preview_result.setText("Switch to WARDOGS now. Reading in 5 seconds…")
        def work():
            if self.stop_event.wait(5):
                return
            bot.configure_desktop(settings, ocr_path())
            _, status, team, scores = bot.capture_and_parse()
            self.events.put(("preview", f"Server: {status or 'Not detected — open the pause menu'}\n"
                             f"Faction: {team or 'Not detected'}\nScores: {scores or 'Not detected'}"))
        self.stop_event.clear()
        self.background(work)

    def tick(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == "log":
                self.activity.appendPlainText(value)
                if "ERROR" in value and self.worker and not self.stop_event.is_set():
                    self.status.setText("Broadcast needs attention · see Activity")
            elif kind == "status" and value and not self.stop_event.is_set():
                self.status.setText("Broadcast enabled · status updated")
            elif kind == "invite":
                QDesktopServices.openUrl(QUrl(value))
                self.status.setText("Choose your server in the browser, then enter its text channel ID below.")
            elif kind == "notice":
                self.status.setText(value)
            elif kind == "preview":
                self.preview_result.setText(value)
            elif kind == "error":
                self.error(value)
            elif kind == "idle":
                self.busy = False
                self.lock(False)
            elif kind == "stopped":
                self.worker = None
                self.lock(False)
                self.status.setText("Broadcast is off · last Discord message kept")
                if self.tray:
                    self.tray.setToolTip("WARDOGS Discord — broadcast off")
        if self.quitting and not self.worker and not self.busy:
            if self.tray:
                self.tray.hide()
            QApplication.instance().quit()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self.quitting = True
        self.stop_event.set()
        self.stop()
        self.status.setText("Quitting · waiting for the current operation to finish…")

    def closeEvent(self, event):
        event.ignore()
        if self.tray:
            self.hide()
        else:
            self.quit_app()


def smoke_test(window, output):
    """Exercise the packaged GUI and actual bundled OCR without Discord or user settings."""
    import json
    from PIL import Image, ImageDraw, ImageFont
    import pytesseract
    output.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(output / "desktop.png"))
    try:
        pytesseract.pytesseract.tesseract_cmd = str(ocr_path())
        test = Image.new("RGB", (800, 120), "white")
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 48)
        ImageDraw.Draw(test).text((20, 20), "WARDOGS 123456", font=font, fill="black")
        reading = pytesseract.image_to_string(test, timeout=20).strip()
        if "123456" not in reading:
            raise RuntimeError("Bundled OCR did not read the test image: " + reading)
        (output / "smoke.json").write_text(json.dumps({"ok": True, "ocr": reading}), encoding="utf-8")
        QApplication.instance().exit(0)
    except Exception as error:
        (output / "smoke.json").write_text(json.dumps({"ok": False, "error": str(error)}), encoding="utf-8")
        QApplication.instance().exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--smoke-test", type=Path, metavar="OUTPUT_DIRECTORY")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    if args.smoke_test:
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeuib.ttf")
    app.setApplicationName("WARDOGS Discord")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    server = QLocalServer()
    if not args.smoke_test:
        # A second shortcut click opens the running app instead of posting duplicate messages.
        import hashlib
        name = "WARDOGSDiscord-" + hashlib.sha256(str(data_dir()).encode()).hexdigest()[:16]
        socket = QLocalSocket()
        socket.connectToServer(name)
        if socket.waitForConnected(500):
            socket.write(b"show")
            socket.waitForBytesWritten(500)
            return 0
        QLocalServer.removeServer(name)
        if not server.listen(name):
            QMessageBox.warning(None, "WARDOGS Discord", "Another copy of the app is starting. Try opening it again.")
            return 1
    window = Window(smoke=bool(args.smoke_test))
    def connected():
        client = server.nextPendingConnection()
        if client:
            client.disconnectFromServer()
            client.deleteLater()
        window.show_window()
    server.newConnection.connect(connected)
    if not args.background or not window.tray or not window.settings.token:
        window.show()
    if args.smoke_test:
        window.show()
        QTimer.singleShot(300, lambda: smoke_test(window, args.smoke_test))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
