"""Local OCR, debounce, filtering and reconnecting controller reports."""
import re
import time
from .transport import AccessDenied,ControllerClient
from . import engine


def filtered(settings,status,team=None,scores=None):
    if status==engine.NOT_IN_GAME:
        return dict(activity='menu' if settings.offline else 'waiting',details='Not in a game' if settings.offline else 'Waiting for a match',team=None,scores=None)
    if status.startswith('Queued'):
        if not settings.queue:status='WARDOGS is running'
        elif not settings.server:
            match=re.search(r'position \d+ of \d+',status)
            status='Queued'+(' ('+match[0]+')' if match else '')
        elif not settings.server_id:status=re.sub(r'ID [\d -]+, ','',status)
        return dict(activity='queue' if settings.queue else 'waiting',details=status,team=None,scores=None)
    if not settings.server:status='In a match'
    elif not settings.server_id:status=re.sub(r'\s*· ID [\d -]+$','',status)
    return dict(activity='match',details=status,team=team if settings.team else None,scores=list(scores) if scores and settings.scores else None)


class Detector:
    def __init__(self,settings):
        self.settings=settings
        self.server=self.team=self.scores=None
        self.pending=None
        self.count=0
        self.score_pending=None
        self.score_count=0
        self.latest=dict(activity='waiting',details='Waiting for a readable game screen',team=None,scores=None)

    def read(self):
        if not engine.is_game_running():
            self.server=self.team=self.scores=None
            self.pending=self.score_pending=None
            self.count=self.score_count=0
            self.latest=filtered(self.settings,engine.NOT_IN_GAME)
            return self.latest
        if not engine.is_game_foreground():
            return dict(activity='waiting',details='Game in background · detection paused',team=None,scores=None)
        try:_,server,team,scores=engine.capture_and_parse(require_foreground=True)
        except engine.CaptureInterrupted:
            return dict(activity='waiting',details='Game in background · detection paused',team=None,scores=None)
        if server is not None and server!=self.server:
            self.server=server;self.team=None;self.scores=None;self.score_pending=None;self.score_count=0
        if team is not None:self.team=team
        if scores is not None:
            self.score_count=self.score_count+1 if scores==self.score_pending else 1
            self.score_pending=scores
            if self.score_count>=2:self.scores=scores
        if self.server is not None:
            candidate=filtered(self.settings,self.server,self.team,self.scores)
            self.count=self.count+1 if candidate==self.pending else 1
            self.pending=candidate
            if self.count>=2:self.latest=candidate
        return self.latest


def run(settings,ocr,stop,emit,client_factory=ControllerClient):
    engine.configure(settings,ocr)
    detector=Detector(settings)
    client=client_factory(settings.url,settings.token)
    session=None;sequence=0;next_send=0;backoff=2
    payload=detector.latest
    try:
        while not stop.is_set():
            try:
                if session is None:
                    session=client.start();sequence=0;next_send=0
                    emit('Reporting enabled · connected to controller')
                try:payload=detector.read()
                except Exception:
                    payload=dict(activity='waiting',details='Screen reading unavailable',team=None,scores=None)
                    emit('Screen reading failed. Check capture settings and the OCR engine.')
                if stop.is_set():break
                if time.monotonic()>=next_send:
                    sequence+=1
                    client.report(session,sequence,payload)
                    emit('Reporting · '+payload['details'])
                    next_send=time.monotonic()+15
                backoff=2
                stop.wait(settings.poll_seconds)
            except AccessDenied as error:
                emit(str(error));return
            except (ConnectionError,ValueError) as error:
                emit(str(error)+' Reconnecting…')
                stop.wait(backoff);backoff=min(backoff*2,30)
                # Keep the same session after network loss, so delayed responses cannot
                # overwrite newer reports. A server restart also preserves sessions.
    finally:
        if session and stop.is_set():
            try:client.report(session,sequence+1,dict(activity='paused',details='Reporting paused by player',team=None,scores=None))
            except (AccessDenied,ConnectionError,ValueError):pass
        client.close()
