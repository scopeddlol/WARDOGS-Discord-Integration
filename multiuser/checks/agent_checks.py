"""Agent contract, privacy, reconnection, and desktop controls."""
import os
from pathlib import Path
import sys
import threading
from dataclasses import replace
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['QT_QPA_PLATFORM']='offscreen'
from agent import config,engine,reporter
from agent.transport import ControllerClient,AccessDenied

@pytest.mark.parametrize('url',['http://example.com','https://name:secret@example.com','https://example.com?key=x','https://example.com/#fragment','file:///etc/passwd'])
def test_url_rejects_unsafe_targets(url):
    with pytest.raises(ValueError):config.normalize_url(url)


def test_url_supports_https_prefix_and_local_development():
    assert config.normalize_url('https://example.com/wardogs/')=='https://example.com/wardogs'
    assert config.normalize_url('http://127.0.0.1:8765/')=='http://127.0.0.1:8765'


def test_no_redirects_and_no_discord_credentials():
    session=Mock();session.request.return_value=Mock(status_code=307,ok=False)
    client=ControllerClient('https://controller.example/prefix','agent-token',session)
    with pytest.raises(ValueError):client.start()
    call=session.request.call_args
    assert call.args[1]=='https://controller.example/prefix/api/v1/session'
    assert call.kwargs['headers']=={'Authorization':'Bearer agent-token'}
    assert call.kwargs['allow_redirects'] is False
    assert 'verify' not in call.kwargs


def test_private_data_filtered_before_transport():
    settings=config.Settings(server=False,team=False,scores=False)
    result=reporter.filtered(settings,'East #12 · ID 123456','Lonestar',(1,2,3))
    assert result==dict(activity='match',details='In a match',team=None,scores=None)
    result=reporter.filtered(replace(settings,queue=False),'Queued for East #12 (position 2 of 4)')
    assert 'East' not in result['details'] and '2' not in result['details']


def test_stop_sends_one_offline_status(monkeypatch):
    stop=threading.Event();client=Mock();client.start.return_value='a'*32
    monkeypatch.setattr(engine,'configure',Mock())
    monkeypatch.setattr(reporter.Detector,'read',lambda self: (stop.set() or {'activity':'match','details':'Private status','team':None,'scores':None}))
    reporter.run(config.Settings(url='https://example.com',token='token'),'ocr',stop,lambda message:None,lambda *args:client)
    assert client.report.call_count==1
    assert client.report.call_args.args[2]['activity']=='offline'
    client.close.assert_called_once()


def test_revoked_agent_does_not_keep_retrying(monkeypatch):
    client=Mock();client.start.side_effect=AccessDenied('Revoked');messages=[]
    monkeypatch.setattr(engine,'configure',Mock())
    reporter.run(config.Settings(url='https://example.com',token='token'),'ocr',threading.Event(),messages.append,lambda *args:client)
    client.start.assert_called_once();client.report.assert_not_called();assert messages==['Revoked']


def test_dpapi_settings_are_separate_and_encrypted(tmp_path):
    settings=config.Settings(url='https://example.com',username='Scout',agent_id='uuid',token='private-agent-token')
    path=tmp_path/'settings.json';config.save(settings,path)
    assert settings.token not in path.read_text()
    assert config.load(path)==settings


def test_window_capture_unavailable_keeps_last_match_until_game_closes(monkeypatch):
    from agent.window_capture import CaptureUnavailable
    detector=reporter.Detector(config.Settings());detector.latest={'activity':'match','details':'East #12','team':'Lonestar','scores':[13,90,42]}
    monkeypatch.setattr(engine,'is_game_running',lambda:True)
    monkeypatch.setattr(engine,'capture_and_parse',lambda: (_ for _ in ()).throw(CaptureUnavailable('Minimized')))
    assert detector.read()==detector.latest
    monkeypatch.setattr(engine,'is_game_running',lambda:False)
    assert detector.read()['activity']=='menu'


def test_score_hud_marks_match_without_pause_menu(monkeypatch):
    detector=reporter.Detector(config.Settings())
    monkeypatch.setattr(engine,'is_game_running',lambda:True)
    monkeypatch.setattr(engine,'capture_and_parse',lambda: ('',None,'Lonestar',(13,90,42)))
    detector.read();detector.read()
    result=detector.read()
    assert result==dict(activity='match',details='In a match',team='Lonestar',scores=[13,90,42])


def test_gui_pairing_locks_identity_and_collects_privacy(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from agent.app import Window
    app=QApplication.instance() or QApplication([])
    window=Window(smoke=True)
    window.settings=config.Settings(url='https://example.com',username='Scout',agent_id='uuid',token='test')
    window.sync_pairing()
    assert not window.inputs['url'].isEnabled() and not window.pair_button.isEnabled()
    window.inputs['scores'].setChecked(False)
    assert not window.collect().scores
    window.timer.stop();window.deleteLater();app.processEvents()

def test_game_watcher_starts_only_when_enabled_and_stops_on_exit(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from agent.app import Window
    app=QApplication.instance() or QApplication([])
    window=Window(smoke=True)
    starts=[]
    monkeypatch.setattr(window,'launch_worker',lambda:starts.append('start'))
    monkeypatch.setattr(engine,'is_game_running',lambda:True)
    window.check_game(force=True)
    assert starts==[]
    window.settings.reporting_enabled=True
    window.check_game(force=True)
    assert starts==['start']
    window.worker=object()
    monkeypatch.setattr(engine,'is_game_running',lambda:False)
    window.check_game(force=True)
    assert window.stop_event.is_set()
    window.worker=None
    window.settings.reporting_enabled=False
    window.stop_event.clear()
    window.check_game(force=True)
    assert starts==['start'] and not window.stop_event.is_set()
    window.timer.stop();window.deleteLater();app.processEvents()


def test_idle_offline_request_uses_agent_credential():
    session=Mock();session.request.return_value=Mock(status_code=200,ok=True,json=lambda:{'ok':True})
    client=ControllerClient('https://controller.example','agent-token',session)
    assert client.offline()=={'ok':True}
    args,kwargs=session.request.call_args
    assert args[:2]==('POST','https://controller.example/api/v1/offline')
    assert kwargs['headers']=={'Authorization':'Bearer agent-token'}

def test_old_auto_start_setting_migrates_to_enabled_game_detection(tmp_path):
    import json
    settings=config.Settings(url='https://example.com',username='Scout',agent_id='uuid',token='credential')
    path=tmp_path/'settings.json'
    config.save(settings,path)
    raw=json.loads(path.read_text(encoding='utf-8'))
    raw.pop('reporting_enabled')
    raw.pop('start_when_game_runs')
    raw['auto_start']=True
    path.write_text(json.dumps(raw),encoding='utf-8')
    loaded=config.load(path)
    assert loaded.reporting_enabled and loaded.start_when_game_runs
    assert loaded.token=='credential'


def test_original_hud_boxes_migrate_without_overwriting_custom_boxes(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(config,'protect_token',lambda value,decrypt=False:value)
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'score_region':'0.0169,0.9139,0.1497,0.9514',
                                'team_region':'0.960,0.925,0.990,0.965'}),encoding='utf-8')
    loaded=config.load(path)
    assert loaded.score_region==config.Settings().score_region
    assert loaded.team_region==config.Settings().team_region
    path.write_text(json.dumps({'score_region':'0.1,0.2,0.3,0.4'}),encoding='utf-8')
    assert config.load(path).score_region=='0.1,0.2,0.3,0.4'


def test_gui_enable_waits_for_game_and_disable_stops_worker(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from agent import app as desktop
    app=QApplication.instance() or QApplication([])
    window=desktop.Window(smoke=True)
    settings=config.Settings(url='https://example.com',username='Scout',agent_id='uuid',token='credential')
    monkeypatch.setattr(window,'collect',lambda:settings)
    monkeypatch.setattr(window,'save',lambda:True)
    monkeypatch.setattr(desktop,'ocr_path',lambda:Path(__file__))
    monkeypatch.setattr(config,'save',lambda settings:None)
    startup=[]
    monkeypatch.setattr(config,'startup',startup.append)
    monkeypatch.setattr(engine,'is_game_running',lambda:False)
    offline=[]
    monkeypatch.setattr(window,'notify_offline',lambda:offline.append(True))
    window.start()
    assert window.settings.reporting_enabled and window.worker is None
    window.stop()
    assert not window.settings.reporting_enabled and offline==[True]
    assert startup==[True,False]
    window.timer.stop();window.deleteLater();app.processEvents()
