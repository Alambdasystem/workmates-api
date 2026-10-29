"""Minimal cookie-session client. Never sends an OpenAI key to the application API."""
import argparse
import getpass
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

class WorkmatesClient:
    def __init__(self, base_url):
        parsed=urllib.parse.urlparse(base_url)
        if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')):
            raise ValueError('Use HTTPS, except for local development.')
        self.base=base_url.rstrip('/')
        self.csrf=''
        self.http=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(self, path, method='GET', body=None):
        if not path.startswith('/api/') or '?' in path or '#' in path:
            raise ValueError('Use a same-server API path.')
        headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf}
        req=urllib.request.Request(self.base+path,method=method,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        try:
            with self.http.open(req,timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'Workmates request failed: HTTP {error.code}') from None
    def login(self,email,password):
        self.request('/api/login','POST',{'email':email,'password':password})
        me=self.request('/api/me')
        self.csrf=me['csrf']
        return {k:v for k,v in me.items() if k!='csrf'}
    def groups(self): return self.request('/api/rooms')
    def send(self,room_id,content,request_id=None):
        safe_id=urllib.parse.quote(room_id,safe='')
        return self.request('/api/rooms/'+safe_id+'/messages','POST',{'content':content,'request_id':request_id or str(uuid.uuid4())})
    def logout(self):
        result=self.request('/api/logout','POST',{})
        self.csrf=''
        return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Sign in and list groups. Does not send messages.')
    parser.add_argument('base_url')
    args=parser.parse_args()
    client=WorkmatesClient(args.base_url)
    client.login(input('Email: '),getpass.getpass('Password: '))
    try:
        for group in client.groups():
            print(group['id'],group['name'])
    finally:
        client.logout()
