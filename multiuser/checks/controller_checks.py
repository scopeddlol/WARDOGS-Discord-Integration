"""Explicitly invoked checks, kept out of the standalone project's test discovery."""
import io
import json
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
import pytest
from PIL import Image
from fastapi.testclient import TestClient
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller.app import Config,create_app
from controller.models import Layout,Report
from controller.render import render,sample_players,units,embed_units
from controller.store import Store,Denied

ADMIN='a'*40

@pytest.fixture
def client(tmp_path):
    app=create_app(Config(tmp_path,ADMIN,'bot-token','123456789012345678',worker=False))
    with TestClient(app) as result:yield result


def headers(token=ADMIN):return {'Authorization':'Bearer '+token}


def pair(client,name='Scout'):
    response=client.post('/api/admin/pairings',headers=headers(),json={'username':name})
    assert response.status_code==200,response.text
    pin=response.json()['pin']
    response=client.post('/api/v1/pair',json={'username':name,'pin':pin})
    assert response.status_code==200,response.text
    return response.json(),pin


def report(client,identity,details='East #1 · ID 123456',activity='match'):
    auth=headers(identity['token'])
    session=client.post('/api/v1/session',headers=auth).json()['session_id']
    payload={'session_id':session,'sequence':1,'activity':activity,'details':details,'team':'Lonestar','scores':[1,2,3]}
    result=client.put('/api/v1/status',headers=auth,json=payload)
    assert result.status_code==200,result.text
    return payload


def test_admin_and_agent_boundaries(client):
    assert client.get('/api/admin/state').status_code==401
    identity,_=pair(client)
    assert client.get('/api/admin/state',headers=headers(identity['token'])).status_code==401
    assert client.post('/api/v1/session',headers=headers()).status_code==403
    assert 'token_hash' not in client.get('/api/admin/state',headers=headers()).text


def test_pair_once_name_bound_and_rotation(client):
    identity,pin=pair(client)
    assert client.post('/api/v1/pair',json={'username':'Scout','pin':pin}).status_code==403
    newer,_=pair(client,'SCOUT')
    assert newer['agent_id']==identity['agent_id']
    assert client.post('/api/v1/session',headers=headers(identity['token'])).status_code==403
    assert client.post('/api/v1/session',headers=headers(newer['token'])).status_code==200


def test_pin_expiry_attempt_limit_and_atomic_redemption(tmp_path):
    now=[1000.]
    store=Store(tmp_path/'data.sqlite3',ADMIN,lambda:now[0])
    invite=store.create_pin('Scout')
    for _ in range(5):
        with pytest.raises(Denied):store.redeem('Scout','wrong')
    with pytest.raises(Denied):store.redeem('Scout',invite['pin'])
    invite=store.create_pin('Scout');now[0]+=601
    with pytest.raises(Denied):store.redeem('Scout',invite['pin'])
    invite=store.create_pin('Scout')
    def attempt(_):
        try:store.redeem('Scout',invite['pin']);return True
        except Denied:return False
    with ThreadPoolExecutor(max_workers=2) as executor:assert sum(executor.map(attempt,range(2)))==1


def test_sessions_sequences_disable_revoke(client):
    identity,_=pair(client);payload=report(client,identity)
    auth=headers(identity['token'])
    stale=dict(payload,details='Stale')
    assert client.put('/api/v1/status',headers=auth,json=stale).json()=={'accepted':False}
    assert client.app.state.store.roster()[0]['status']['details']!='Stale'
    client.post('/api/v1/session',headers=auth)
    assert client.put('/api/v1/status',headers=auth,json=dict(payload,sequence=2)).status_code==403
    client.put('/api/admin/agents/'+identity['agent_id'],headers=headers(),json={'enabled':False})
    assert client.post('/api/v1/session',headers=auth).status_code==403
    client.put('/api/admin/agents/'+identity['agent_id'],headers=headers(),json={'enabled':True})
    assert client.post('/api/v1/session',headers=auth).status_code==200
    client.delete('/api/admin/agents/'+identity['agent_id']+'/credential',headers=headers())
    assert client.post('/api/v1/session',headers=auth).status_code==403


def test_disconnect_removes_old_scores_and_restart_persists(tmp_path):
    now=[1000.];path=tmp_path/'db.sqlite3';store=Store(path,ADMIN,lambda:now[0])
    invite=store.create_pin('Scout');identity=store.redeem('Scout',invite['pin']);session=store.start(identity['token'])
    store.report(identity['token'],Report(session_id=session['session_id'],sequence=1,activity='match',details='In game',scores=(1,2,3)))
    now[0]+=91;store.expire(90)
    row=Store(path,ADMIN,lambda:now[0]).roster()[0]
    assert row['connection']=='disconnected' and row['status']['scores'] is None
    store.report(identity['token'],Report(session_id=session['session_id'],sequence=2,activity='match',details='Back'))
    assert store.roster()[0]['connection']=='connected'


def test_ten_agents_use_one_message_and_edit_after_restart(client):
    for i in range(10):identity,_=pair(client,'Player '+str(i));report(client,identity)
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={'id':'shared-message','attachments':[]})
    publisher=client.app.state.publisher
    publisher.client=httpx.Client(transport=httpx.MockTransport(respond))
    publisher.interval=0
    publisher.tick()
    assert len(calls)==1 and calls[0].method=='POST'
    body=json.loads(calls[0].content)
    assert len(body['embeds'])==1 and len(body['embeds'][0]['fields'])==10
    assert body['allowed_mentions']=={'parse':[]}
    store=client.app.state.store;store.save_layout(Layout(title='New title'))
    publisher.tick()
    assert calls[-1].method=='PATCH' and calls[-1].url.path.endswith('/shared-message')
    assert store.snapshot()['published']==store.snapshot()['revision']


def test_deleted_message_and_rate_limit(client):
    publisher=client.app.state.publisher;publisher.interval=0
    store=client.app.state.store;store.published(0,'deleted',publisher.channel,{})
    calls=[]
    def respond(request):
        calls.append(request.method)
        return httpx.Response(404,json={'code':10008}) if request.method=='PATCH' else httpx.Response(429,json={'retry_after':30})
    publisher.client=httpx.Client(transport=httpx.MockTransport(respond))
    publisher.tick();publisher.tick()
    assert calls==['PATCH','POST']
    assert store.snapshot()['retry_at']>store.clock()


@pytest.mark.parametrize('count',[0,10,25,50,100])
@pytest.mark.parametrize('mode',['cards','compact'])
def test_render_bounds_and_explicit_overflow(count,mode):
    result=render(Layout(mode=mode,max_players=100),sample_players(count,1000),1000)
    embed=result['embed']
    assert embed_units(embed)<=6000 and len(embed.get('fields',[]))<=25
    assert units(embed.get('description',''))<=4096
    assert result['shown']+result['omitted']==count
    if result['omitted']:assert result['warnings']


def test_templates_reject_attribute_access_and_full_fields_render():
    with pytest.raises(ValueError):Layout(player_body='{username.__class__}')
    with pytest.raises(ValueError):Layout(title='{total:999999}')
    layout=Layout(author_name='Squad {total}',author_url='https://example.com',author_icon='https://example.com/icon.png',
        url='https://example.com/game',image='https://example.com/banner.png',thumbnail='https://example.com/thumb.png',
        footer_icon='https://example.com/footer.png',custom_fields=[{'name':'Note','value':'Hello {online}','inline':False,'position':'before'}])
    embed=render(layout,sample_players(10,1000),1000)['embed']
    assert embed['author']['name']=='Squad 10' and embed['fields'][0]['name']=='Note'
    assert embed['image']['url'].endswith('banner.png') and embed['footer']['icon_url']


def test_preview_never_changes_live_roster(client):
    result=client.post('/api/admin/preview',headers=headers(),json={'layout':Layout().model_dump(),'sample_count':10})
    assert result.status_code==200,result.text
    assert result.json()['shown']==10
    assert client.app.state.store.roster()==[]
    assert client.app.state.store.snapshot()['message_id'] is None


def test_image_upload_auth_validation_and_attachments(client):
    image=io.BytesIO();Image.new('RGB',(20,20),'red').save(image,format='PNG');data=image.getvalue()
    assert client.post('/api/admin/assets',content=data).status_code==401
    assert client.post('/api/admin/assets',headers=headers(),content=b'<svg/>').status_code==422
    result=client.post('/api/admin/assets',headers=headers(),content=data)
    assert result.status_code==200,result.text
    reference=result.json()['reference'];name=result.json()['name']
    assert client.get('/api/admin/assets/'+name).status_code==401
    assert client.get('/api/admin/assets/'+name,headers=headers()).content==data
    layout=Layout(image=reference,thumbnail=reference)
    embed=render(layout,sample_players(1,1000),1000)['embed']
    body,files=client.app.state.publisher.payload(embed,{})
    assert len(files)==1 and len(body['attachments'])==1
    body,files=client.app.state.publisher.payload(embed,{name:'existing'})
    assert not files and body['attachments'][0]['id']=='existing'
    assert client.app.state.publisher.payload(render(Layout(),[],1000)['embed'],{name:'existing'})[0]['attachments']==[]


def test_request_size_and_unknown_fields(client):
    assert client.post('/api/v1/pair',content=b'x'*70000).status_code==413
    identity,_=pair(client);payload=report(client,identity)
    assert client.put('/api/v1/status',headers=headers(identity['token']),json=dict(payload,username='Impersonation')).status_code==422


def test_unicode_budget_and_fixed_content_rejection():
    players=sample_players(100,1000)
    for p in players:p['username']='😀'*40;p['status']['details']='😀'*240
    result=render(Layout(max_players=100),players,1000)
    assert result['characters']<=6000 and result['omitted']>0
    layout=Layout(custom_fields=[{'name':'Big','value':'x'*1024} for _ in range(6)])
    with pytest.raises(ValueError):render(layout,[],1000)

def test_retried_creation_keeps_nonce(client):
    publisher=client.app.state.publisher
    requests=[]
    def respond(request):
        requests.append(json.loads(request.content))
        raise httpx.ReadTimeout('lost response')
    publisher.client=httpx.Client(transport=httpx.MockTransport(respond))
    board=client.app.state.store.snapshot()
    for _ in range(2):
        with pytest.raises(httpx.ReadTimeout):publisher.send(board,render(board['layout'],[],1000)['embed'])
    assert requests[0]['enforce_nonce'] is True
    assert requests[0]['nonce']==requests[1]['nonce']


def test_individual_stats_and_optional_title():
    layout=Layout(title='',player_body='{server}|{server_id}|{lonestar_score}|{valkyra_score}|{manticore_score}|{queue_position}|{queue_total}')
    result=render(layout,sample_players(3,1000),1000)
    assert 'title' not in result['embed']
    assert any('East #145|469-618|125|108|94' in f['value'] for f in result['embed']['fields'])
    assert any('Central #1|||||3|12' in f['value'] for f in result['embed']['fields'])


def test_combined_uploaded_image_budget(client,monkeypatch):
    from controller import app as module
    image=io.BytesIO();Image.new('RGB',(20,20),'red').save(image,format='PNG')
    first=client.post('/api/admin/assets',headers=headers(),content=image.getvalue()).json()['reference']
    second_image=io.BytesIO();Image.new('RGB',(20,20),'blue').save(second_image,format='PNG')
    second=client.post('/api/admin/assets',headers=headers(),content=second_image.getvalue()).json()['reference']
    monkeypatch.setattr(module,'MAX_BYTES',max(len(image.getvalue()),len(second_image.getvalue())))
    response=client.put('/api/admin/layout',headers=headers(),json=Layout(image=first,thumbnail=second).model_dump())
    assert response.status_code==422
    assert client.app.state.store.snapshot()['layout'].image==''
    response=client.put('/api/admin/layout',headers=headers(),json=Layout(image=first,thumbnail=first).model_dump())
    assert response.status_code==200
