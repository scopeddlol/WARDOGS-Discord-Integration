"""Outbound HTTPS only; redirects and credential forwarding are never followed."""
import requests
from .config import normalize_url


class AccessDenied(Exception):
    pass


class ControllerClient:
    def __init__(self,url,token='',session=None):
        self.url=normalize_url(url)
        self.token=token
        self.http=session or requests.Session()

    def request(self,method,path,body=None):
        headers={'Authorization':'Bearer '+self.token} if self.token else {}
        try:
            response=self.http.request(method,self.url+'/api/v1/'+path,json=body,headers=headers,
                                       timeout=(5,10),allow_redirects=False)
        except requests.RequestException as error:
            raise ConnectionError('Controller unreachable. Check the URL, HTTPS certificate, and network.') from error
        if response.status_code in (401,403):
            raise AccessDenied('Access was rejected. Check your pairing PIN, or contact the controller host.')
        if 300<=response.status_code<400:
            raise ValueError('The controller redirected the request. Enter its final HTTPS URL, including any path prefix.')
        if response.status_code==429:
            raise ConnectionError('Controller rate limit. Wait a moment before retrying.')
        if not response.ok:
            raise ValueError(f'Controller returned HTTP {response.status_code}. Check the URL and settings.')
        try:return response.json()
        except ValueError as error:raise ValueError('This URL did not return a controller response.') from error

    def pair(self,username,pin):
        result=self.request('POST','pair',{'username':username,'pin':pin})
        if not all(isinstance(result.get(key),str) and result[key] for key in ('token','agent_id','username')):
            raise ValueError('The controller returned an invalid pairing response.')
        return result

    def start(self):
        result=self.request('POST','session')
        if not isinstance(result.get('session_id'),str) or len(result['session_id'])!=32:
            raise ValueError('The controller returned an invalid session.')
        return result['session_id']

    def report(self,session_id,sequence,payload):
        return self.request('PUT','status',dict(payload,session_id=session_id,sequence=sequence))

    def offline(self):
        return self.request('POST','offline')

    def close(self):
        self.http.close()
