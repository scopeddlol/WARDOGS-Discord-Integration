"""Independent Windows agent UI: no bot token, channel or Discord client."""
import argparse
from dataclasses import replace
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import sys
import threading

from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QIcon,QFontDatabase
from PySide6.QtNetwork import QLocalServer,QLocalSocket
from PySide6.QtWidgets import (QApplication,QCheckBox,QComboBox,QFormLayout,QHBoxLayout,QLabel,
    QLineEdit,QMainWindow,QMenu,QMessageBox,QPlainTextEdit,QPushButton,QScrollArea,QSpinBox,
    QSystemTrayIcon,QTabWidget,QVBoxLayout,QWidget)

from . import config,engine,reporter
from .capture import CaptureDialog
from .style import STYLE
from .transport import ControllerClient


def label(text,name=None):
    result=QLabel(text);result.setWordWrap(True);result.setTextFormat(Qt.PlainText)
    if name:result.setObjectName(name)
    return result


def button(text,callback,primary=False):
    result=QPushButton(text);result.clicked.connect(callback)
    if primary:result.setObjectName('primary')
    return result


def ocr_path():
    bundled=config.resources()/'tesseract'/'tesseract.exe'
    return bundled if bundled.exists() else Path(os.getenv('WARDOGS_AGENT_TESSERACT',str(config.resources()/'vendor'/'tesseract'/'tesseract.exe')))


class Window(QMainWindow):
    def __init__(self,smoke=False):
        super().__init__()
        self.events=queue.Queue();self.stop_event=threading.Event();self.worker=None;self.busy=False;self.quitting=False;self.tray=None
        error=None
        try:self.settings=config.Settings() if smoke else config.load()
        except (ValueError,TypeError,OSError) as exc:self.settings=config.Settings();error='Saved settings could not be loaded. Pair again. '+str(exc)
        self.setWindowTitle('WARDOGS Agent');self.setWindowIcon(QIcon(str(config.resources()/'agent'/'tray_icon.png')))
        self.resize(860,800);self.setMinimumSize(740,700)
        root=QWidget();layout=QVBoxLayout(root);layout.setContentsMargins(28,22,28,22);layout.setSpacing(14)
        layout.addWidget(label('WARDOGS / CONNECTED AGENT','eyebrow'))
        layout.addWidget(label('Your squad. One connection.','heading'))
        layout.addWidget(label('Pair with your host. Choose your stats. Your controller handles Discord.','muted'))
        self.status=label('Reporting is off','status');layout.addWidget(self.status)
        controls=QHBoxLayout();self.start_button=button('Start reporting',self.start,True);self.stop_button=button('Stop',self.stop);self.stop_button.setEnabled(False)
        self.save_button=button('Save settings',self.save)
        controls.addWidget(self.start_button);controls.addWidget(self.stop_button);controls.addStretch();controls.addWidget(self.save_button);layout.addLayout(controls)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1);self.pages=[];self.inputs={}
        self.connection_page();self.share_page();self.capture_page()
        self.activity=QPlainTextEdit();self.activity.setReadOnly(True);self.activity.setMaximumBlockCount(300);self.tabs.addTab(self.activity,'Activity')
        layout.addWidget(label('Only your chosen text stats go to the controller. No automatic screenshot uploads.\nClosing keeps the agent in the tray. Stop pauses reporting; the controller updates the shared message.','muted'))
        self.setCentralWidget(root)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(100)
        if not smoke and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray=QSystemTrayIcon(self.windowIcon(),self);menu=QMenu(self)
            menu.addAction('Open settings',self.show_window);self.tray_start=menu.addAction('Start reporting',self.start);self.tray_stop=menu.addAction('Stop reporting',self.stop);self.tray_stop.setEnabled(False)
            menu.addSeparator();menu.addAction('Quit',self.quit_app);self.tray.setContextMenu(menu);self.tray.setToolTip('WARDOGS Agent · reporting off')
            self.tray.activated.connect(lambda reason:self.show_window() if reason==QSystemTrayIcon.DoubleClick else None);self.tray.show()
        self.sync_pairing()
        if error:QTimer.singleShot(0,lambda:self.error(error))
        elif not smoke and self.settings.auto_start:QTimer.singleShot(0,self.start)

    def page(self,title):
        widget=QWidget();layout=QVBoxLayout(widget);layout.setContentsMargins(20,18,20,18);layout.setSpacing(12)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget);self.tabs.addTab(scroll,title);self.pages.append(widget)
        return layout

    def field(self,form,name,title,secret=False):
        widget=QLineEdit(getattr(self.settings,name));widget.setAccessibleName(title)
        if secret:widget.setEchoMode(QLineEdit.Password)
        form.addRow(title,widget);self.inputs[name]=widget;return widget

    def check(self,layout,name,title):
        widget=QCheckBox(title);widget.setChecked(getattr(self.settings,name));layout.addWidget(widget);self.inputs[name]=widget;return widget

    def connection_page(self):
        layout=self.page('Controller');layout.addWidget(label('01  PAIR WITH YOUR HOST','eyebrow'))
        layout.addWidget(label('Ask your host for the controller URL, your player username, and an 8-digit PIN.\nThe PIN works once and expires after 10 minutes. You do not need a Discord bot or any open ports.','muted'))
        form=QFormLayout();form.setSpacing(12)
        self.field(form,'url','Controller URL').setPlaceholderText('https://wardogs.example.com')
        self.field(form,'username','Player username').setPlaceholderText('The exact name paired by your host')
        self.pin=QLineEdit();self.pin.setMaxLength(8);self.pin.setEchoMode(QLineEdit.Password);self.pin.setAccessibleName('Pairing PIN');self.pin.setPlaceholderText('8-digit PIN');form.addRow('Pairing PIN',self.pin)
        layout.addLayout(form);row=QHBoxLayout();self.pair_button=button('Pair agent',self.pair,True);self.forget_button=button('Forget pairing',self.forget)
        row.addWidget(self.pair_button);row.addWidget(self.forget_button);row.addStretch();layout.addLayout(row)
        self.identity=label('Not paired','muted');layout.addWidget(self.identity);layout.addStretch()
        layout.addWidget(label('Your agent credential is encrypted for this Windows account. The bot token stays on the controller.','muted'))

    def share_page(self):
        layout=self.page('Share');layout.addWidget(label('02  CHOOSE WHAT TO REPORT','eyebrow'))
        for key,title in [('server','Server name / region'),('server_id','Server ID'),('queue','Queue position'),('team','Faction / team'),('scores','Live team scores'),('offline','Not-in-game status')]:self.check(layout,key,title)
        self.inputs['server'].toggled.connect(self.inputs['server_id'].setEnabled);self.inputs['server_id'].setEnabled(self.settings.server)
        layout.addWidget(label('Disabled details are removed before they leave this PC. Your host controls the shared embed layout.','muted'));layout.addStretch()
        self.check(layout,'launch_at_login','Open the agent when I sign in to Windows');self.check(layout,'auto_start','Start reporting automatically when the agent opens')

    def capture_page(self):
        layout=self.page('Capture');layout.addWidget(label('03  GAME DETECTION','eyebrow'))
        layout.addWidget(label('Open the pause menu briefly after joining a match. Set Interface → Faction to Always On for faction detection. Automatic reading pauses when WARDOGS is in the background.','muted'))
        form=QFormLayout();self.monitor=QComboBox()
        try:
            import mss
            with mss.MSS() as capture:
                for i,m in enumerate(capture.monitors[1:],1):self.monitor.addItem(f'Display {i} · {m["width"]} × {m["height"]}',i)
        except Exception:self.monitor.addItem('No display available',0)
        self.monitor.setCurrentIndex(max(0,self.monitor.findData(self.settings.monitor)));form.addRow('Game display',self.monitor)
        interval=QSpinBox();interval.setRange(2,60);interval.setValue(self.settings.poll_seconds);self.inputs['poll_seconds']=interval;form.addRow('Scan every (seconds)',interval);layout.addLayout(form)
        layout.addWidget(button('Adjust capture boxes…',self.calibrate));layout.addWidget(button('Read screen in 5 seconds',self.preview))
        self.preview_result=label('Local test only. Nothing is sent to the controller.','muted');layout.addWidget(self.preview_result);layout.addStretch()
        layout.addWidget(label('OCR engine: '+('Ready' if ocr_path().exists() else 'Missing — use the agent installer'),'muted'))

    def sync_pairing(self):
        paired=bool(self.settings.token)
        self.inputs['url'].setEnabled(not paired);self.inputs['username'].setEnabled(not paired)
        self.pin.setEnabled(not paired);self.pair_button.setEnabled(not paired);self.forget_button.setEnabled(paired)
        self.identity.setText('Paired as '+self.settings.username+' · '+self.settings.agent_id if paired else 'Not paired')

    def collect(self):
        result=replace(self.settings)
        for key,widget in self.inputs.items():
            value=widget.isChecked() if isinstance(widget,QCheckBox) else widget.value() if isinstance(widget,QSpinBox) else widget.text().strip()
            setattr(result,key,value)
        result.monitor=self.monitor.currentData() or 0
        return result

    def error(self,text):
        self.status.setText(text);self.show_window();QMessageBox.warning(self,'WARDOGS Agent',text)

    def save(self):
        try:
            settings=self.collect();settings.validate();config.save(settings);config.startup(settings.launch_at_login);self.settings=settings
            self.status.setText('Settings saved · reporting is off');return True
        except (ValueError,OSError) as error:self.error(str(error));return False

    def lock(self,active):
        for page in self.pages:page.setEnabled(not active)
        self.start_button.setEnabled(not active);self.save_button.setEnabled(not active);self.stop_button.setEnabled(active and self.worker is not None)
        if self.tray:self.tray_start.setEnabled(not active);self.tray_stop.setEnabled(active and self.worker is not None)
        if not active:self.sync_pairing()

    def background(self,operation):
        if self.worker or self.busy:return
        self.busy=True;self.lock(True)
        def run():
            try:operation()
            except Exception as error:self.events.put(('error',str(error)))
            finally:self.events.put(('idle',None))
        threading.Thread(target=run,daemon=True).start()

    def pair(self):
        try:
            settings=self.collect();settings.validate();pin=self.pin.text().strip()
            if len(pin)!=8 or not pin.isascii() or not pin.isdigit():raise ValueError('Enter the 8-digit PIN supplied by your controller host.')
        except ValueError as error:self.error(str(error));return
        self.status.setText('Pairing with controller…')
        def work():
            client=ControllerClient(settings.url)
            try:result=client.pair(settings.username,pin)
            finally:client.close()
            settings.token=result['token'];settings.agent_id=result['agent_id'];settings.username=result['username']
            try:config.save(settings)
            except OSError as error:raise ValueError('Pairing succeeded but Windows could not save the credential. Ask your host for a new PIN and try again.') from error
            self.events.put(('paired',settings))
        self.background(work)

    def forget(self):
        if QMessageBox.question(self,'Forget pairing','Remove this PC’s saved credential? The host must issue a new PIN to pair again. This does not revoke the credential on the controller.')!=QMessageBox.Yes:return
        settings=self.collect();settings.token='';settings.agent_id='';settings.auto_start=False
        try:config.save(settings)
        except (ValueError,OSError) as error:self.error(str(error));return
        self.settings=settings;self.inputs['auto_start'].setChecked(False);self.pin.clear();self.sync_pairing();self.status.setText('Pairing forgotten on this PC')

    def start(self):
        if self.worker or self.busy:return
        try:self.collect().validate(paired=True)
        except ValueError as error:self.error(str(error));return
        if not ocr_path().exists():self.error('OCR is missing. Reinstall using WARDOGS-Agent-Setup.exe.');return
        if not self.save():return
        self.stop_event.clear()
        def work():
            try:reporter.run(self.settings,ocr_path(),self.stop_event,lambda message:self.events.put(('status',message)))
            except Exception as error:self.events.put(('error','Reporting stopped: '+type(error).__name__))
            finally:self.events.put(('stopped',None))
        self.worker=threading.Thread(target=work,daemon=True);self.lock(True);self.worker.start();self.status.setText('Connecting to controller…')

    def stop(self):
        if self.worker:self.stop_event.set();self.stop_button.setEnabled(False);self.status.setText('Stopping · finishing the current read/request…')

    def calibrate(self):
        settings=self.collect();dialog=CaptureDialog(settings,self)
        if dialog.exec():
            for key in ('capture_region','team_region','score_region'):setattr(self.settings,key,getattr(settings,key))
            self.status.setText('Capture boxes updated · save settings to keep them')

    def preview(self):
        if not ocr_path().exists():self.error('Install the bundled agent OCR engine first.');return
        settings=self.collect();self.stop_event.clear();self.preview_result.setText('Switch to the game now. Reading in 5 seconds…')
        def work():
            if self.stop_event.wait(5):return
            engine.configure(settings,ocr_path());_,status,team,scores=engine.capture_and_parse()
            self.events.put(('preview',f'Status: {status or "Not detected — open the pause menu"}\nTeam: {team or "Not detected"}\nScores: {scores or "Not detected"}'))
        self.background(work)

    def tick(self):
        while not self.events.empty():
            kind,value=self.events.get_nowait()
            if kind=='status':
                self.activity.appendPlainText(value)
                if not self.stop_event.is_set():self.status.setText(value)
                if self.tray:self.tray.setToolTip(('WARDOGS Agent · '+value)[:127])
            elif kind=='preview':self.preview_result.setText(value)
            elif kind=='paired':
                self.settings=value;self.inputs['username'].setText(value.username);self.inputs['url'].setText(value.url);self.pin.clear();self.sync_pairing();self.status.setText('Paired successfully · choose your stats and Start reporting')
            elif kind=='error':
                if not self.quitting:self.error(value)
            elif kind=='idle':self.busy=False;self.lock(False)
            elif kind=='stopped':
                self.worker=None;self.lock(False);self.status.setText('Reporting is off · check Activity for the last connection status')
                if self.tray:self.tray.setToolTip('WARDOGS Agent · reporting off')
        if self.quitting and not self.worker and not self.busy:
            if self.tray:self.tray.hide()
            QApplication.instance().quit()

    def show_window(self):self.showNormal();self.raise_();self.activateWindow()
    def quit_app(self):self.quitting=True;self.stop_event.set();self.stop()
    def closeEvent(self,event):
        event.ignore()
        if self.tray:self.hide()
        else:self.quit_app()


def smoke(window,directory):
    from PIL import Image,ImageDraw,ImageFont
    import pytesseract
    directory.mkdir(parents=True,exist_ok=True);window.grab().save(str(directory/'agent.png'))
    try:
        pytesseract.pytesseract.tesseract_cmd=str(ocr_path());image=Image.new('RGB',(800,120),'white')
        ImageDraw.Draw(image).text((20,20),'WARDOGS 123456',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',48),fill='black')
        reading=pytesseract.image_to_string(image,timeout=20).strip()
        if '123456' not in reading:raise ValueError('Bundled OCR failed its reading test.')
        result={'ok':True,'ocr':reading};code=0
    except Exception as error:result={'ok':False,'error':str(error)};code=1
    (directory/'smoke.json').write_text(json.dumps(result),encoding='utf-8');QApplication.instance().exit(code)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--background',action='store_true');parser.add_argument('--smoke-test',type=Path)
    args=parser.parse_args();app=QApplication(sys.argv);app.setApplicationName('WARDOGS Agent');app.setStyle('Fusion');app.setStyleSheet(STYLE);app.setQuitOnLastWindowClosed(False)
    if args.smoke_test:
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf');QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeuib.ttf')
    logging.basicConfig(level=logging.INFO,handlers=[RotatingFileHandler(config.data_dir()/'agent.log',maxBytes=1_000_000,backupCount=2,encoding='utf-8')])
    server=QLocalServer()
    if not args.smoke_test:
        name='WARDOGS-Agent-'+hashlib.sha256(str(config.data_dir()).encode()).hexdigest()[:16]
        socket=QLocalSocket();socket.connectToServer(name)
        if socket.waitForConnected(500):socket.write(b'show');socket.waitForBytesWritten(500);return 0
        QLocalServer.removeServer(name)
        if not server.listen(name):QMessageBox.warning(None,'WARDOGS Agent','Another agent is starting. Try again.');return 1
    window=Window(smoke=bool(args.smoke_test))
    def connected():
        client=server.nextPendingConnection()
        if client:client.disconnectFromServer();client.deleteLater()
        window.show_window()
    server.newConnection.connect(connected)
    if not args.background or not window.tray or not window.settings.token:window.show()
    if args.smoke_test:window.show();QTimer.singleShot(300,lambda:smoke(window,args.smoke_test))
    return app.exec()
