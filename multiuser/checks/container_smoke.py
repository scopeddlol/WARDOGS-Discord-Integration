"""HTTP-only integration smoke for a running dry-run container (no Discord)."""
import argparse
import io
import httpx
from PIL import Image

parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:18080');parser.add_argument('--token',required=True);args=parser.parse_args()
client=httpx.Client(base_url=args.url,headers={'Authorization':'Bearer '+args.token},timeout=10)
assert client.get('/healthz').json()=={'ok':True}
for i in range(10):
    name='Smoke player '+str(i)
    pin=client.post('/api/admin/pairings',json={'username':name}).json()['pin']
    paired=client.post('/api/v1/pair',json={'username':name,'pin':pin}).json()
    headers={'Authorization':'Bearer '+paired['token']}
    session=client.post('/api/v1/session',headers=headers).json()['session_id']
    response=client.put('/api/v1/status',headers=headers,json={'session_id':session,'sequence':1,'activity':'match','details':'East #1 · ID 123456','team':'Lonestar','scores':[100,200,300]})
    response.raise_for_status()
state=client.get('/api/admin/state').json();assert len(state['agents'])==10
assert state['preview']['shown']==10 and len(state['preview']['embed']['fields'])==10
image=io.BytesIO();Image.new('RGB',(20,20),'blue').save(image,format='PNG')
asset=client.post('/api/admin/assets',content=image.getvalue()).json()['reference']
layout=state['layout'];layout['image']=asset;layout['author_name']='Smoke squad';layout['custom_fields']=[{'name':'Notice','value':'Ten players, one message','inline':False,'position':'before'}]
response=client.put('/api/admin/layout',json=layout);response.raise_for_status()
assert response.json()['preview']['embed']['image']['url']==asset
print('Container API: ten agents, one embed, image upload and saved layout passed.')
