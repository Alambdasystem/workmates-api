import json
import tempfile
import unittest
from pathlib import Path
from server import create_app

class WorkmatesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = dict(DB_PATH=str(Path(self.temp.name)/'test.db'), ADMIN_EMAIL='admin@example.com', ADMIN_PASSWORD='a-long-admin-password', COOKIE_SECURE=False, OPENAI_API_KEY='test-key', TESTING=True)
        self.calls = []
        self.provider = lambda p,k: self.reply('Ready.')
        def dispatch(p,k):
            self.calls.append(json.loads(json.dumps(p)))
            return self.provider(p,k)
        self.app = create_app(self.config,start_worker=False,provider=dispatch)
        self.admin = self.app.test_client()
        self.admin.post('/api/login',json={'email':'admin@example.com','password':'a-long-admin-password'})
        self.ac = self.admin.get('/api/me').json['csrf']
        self.rid = self.post('/rooms',{'name':'Product','description':'Build together'}).json['id']
        self.agent = self.app.extensions['agent']
    def tearDown(self): self.temp.cleanup()
    def reply(self,text): return {'output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}
    def tool(self,name,args): return {'output':[{'type':'function_call','name':name,'arguments':json.dumps(args),'call_id':name}]}
    def post(self,route,payload,client=None,csrf=None,method='POST'):
        return (client or self.admin).open('/api'+route,method=method,json=payload,headers={'X-CSRF-Token':csrf or self.ac})
    def settings(self,enabled=True,tools=None):
        return self.post('/rooms/'+self.rid+'/workmate',dict(agent_name='REIGN',prompt='You are a helpful teammate.',enabled=enabled,mode='mention',tools=tools if tools is not None else ['create_task','save_document']),method='PATCH')
    def message(self,content='@REIGN help',nonce='1',client=None,csrf=None):
        return self.post('/rooms/'+self.rid+'/messages',dict(content=content,request_id=nonce),client,csrf)
    def room(self): return self.admin.get('/api/rooms/'+self.rid).json
    def member(self):
        invite = self.post('/rooms/'+self.rid+'/invites',{'email':'member@example.com'}).json
        c = self.app.test_client()
        r = c.post('/api/join',json=dict(email='member@example.com',name='Member',password='a-long-member-password',token=invite['token']))
        self.assertEqual(r.status_code,200)
        return c,c.get('/api/me').json['csrf'],invite
    def test_only_admin_creates_groups_and_configures_agent(self):
        c,csrf,_ = self.member()
        self.assertEqual(self.post('/rooms',{'name':'Denied','description':''},c,csrf).status_code,403)
        self.assertEqual(self.post('/rooms/'+self.rid+'/workmate',{},c,csrf,method='PATCH').status_code,403)
        self.assertEqual(self.post('/rooms/'+self.rid+'/invites',{'email':'other@example.com'},c,csrf).status_code,403)
        self.assertNotIn('prompt',c.get('/api/rooms/'+self.rid).json)
    def test_room_isolation_and_revocation(self):
        c,csrf,_ = self.member()
        other = self.post('/rooms',{'name':'Private','description':''}).json['id']
        self.assertEqual(c.get('/api/rooms/'+other).status_code,404)
        self.assertEqual(self.post('/rooms/'+other+'/messages',{'content':'intrusion','request_id':'x'},c,csrf).status_code,404)
        self.assertEqual(len(c.get('/api/rooms').json),1)
        mid = c.get('/api/me').json['id']
        self.post('/rooms/'+self.rid+'/members/'+mid,{},method='DELETE')
        self.assertEqual(c.get('/api/rooms/'+self.rid).status_code,404)
        self.assertEqual(self.message('hello','new',c,csrf).status_code,404)
    def test_invitation_single_use_and_bound_email(self):
        c,csrf,invite = self.member()
        d = dict(email='member@example.com',name='M',password='a-long-member-password',token=invite['token'])
        self.assertEqual(self.app.test_client().post('/api/join',json=d).status_code,400)
        d['email']='attacker@example.com'
        self.assertEqual(self.app.test_client().post('/api/join',json=d).status_code,400)
    def test_off_preserves_chat_without_provider(self):
        self.assertEqual(self.message().status_code,201)
        self.assertFalse(self.agent.process_one())
        self.assertEqual(len(self.room()['messages']),1)
        self.assertEqual(self.calls,[])
    def test_mentions_and_idempotent_send(self):
        self.settings(); self.message('hello team','a')
        self.assertFalse(self.agent.process_one())
        self.message('@workmate help','b'); self.message('@workmate help','b')
        self.assertEqual(len(self.room()['messages']),2)
        self.assertTrue(self.agent.process_one())
        self.assertEqual(self.room()['messages'][-1]['kind'],'agent')
        self.assertEqual(len(self.calls),1)
    def test_allowed_tools_save_real_work(self):
        self.settings(); self.message()
        results = iter([self.tool('create_task',{'title':'Ship prototype','assignee':'James'}), self.tool('save_document',{'title':'Brief','body':'Build, test, ship.'}), self.reply('Saved both.')])
        self.provider=lambda p,k:next(results)
        self.agent.process_one()
        r=self.room()
        self.assertEqual(r['tasks'][0]['title'],'Ship prototype')
        self.assertEqual(r['documents'][0]['body'],'Build, test, ship.')
        self.assertEqual(r['jobs'][0]['status'],'completed')
        self.assertTrue(any(i.get('type')=='function_call_output' for i in self.calls[1]['input']))
    def test_unallowed_tool_cannot_execute(self):
        self.settings(tools=[]); self.message()
        results=iter([self.tool('create_task',{'title':'Forbidden','assignee':''}),self.reply('Tool unavailable.')])
        self.provider=lambda p,k:next(results)
        self.agent.process_one()
        self.assertEqual(self.room()['tasks'],[])
        self.assertEqual(len(self.calls),2)
    def test_disable_cancels_inflight_tools_and_queued_jobs(self):
        self.settings(); self.message()
        def provider(p,k):
            self.settings(False)
            return self.tool('create_task',{'title':'Late task','assignee':''})
        self.provider=provider
        self.agent.process_one()
        r=self.room()
        self.assertEqual(r['tasks'],[])
        self.assertEqual(len(r['messages']),1)
        self.assertEqual(r['jobs'][0]['status'],'canceled')
        self.settings(True); self.message(nonce='2'); self.settings(False)
        self.assertFalse(self.agent.process_one())
    def test_disable_discards_inflight_text(self):
        self.settings(); self.message()
        def provider(p,k):
            self.settings(False)
            return self.reply('Too late.')
        self.provider=provider; self.agent.process_one()
        self.assertEqual(len(self.room()['messages']),1)
    def test_csrf_origin_and_auth_guards(self):
        self.assertEqual(self.admin.post('/api/rooms',json={'name':'bad'}).status_code,403)
        r=self.admin.post('/api/rooms',json={'name':'bad'},headers={'X-CSRF-Token':self.ac,'Origin':'https://evil.example'})
        self.assertEqual(r.status_code,403)
        self.assertEqual(self.app.test_client().get('/api/rooms').status_code,401)
    def test_persistence_across_restart(self):
        self.message('Persist this')
        second=create_app(self.config,start_worker=False)
        c=second.test_client(); c.post('/api/login',json={'email':'admin@example.com','password':'a-long-admin-password'})
        self.assertEqual(c.get('/api/rooms/'+self.rid).json['messages'][0]['content'],'Persist this')
    def test_missing_api_key_is_visible_failure(self):
        self.app.config['OPENAI_API_KEY']=''
        self.settings(); self.message(); self.agent.process_one()
        self.assertEqual(self.room()['jobs'][0]['status'],'failed')
        self.assertIn('not connected',self.room()['jobs'][0]['error'])
    def test_provider_context_excludes_other_rooms(self):
        other=self.post('/rooms',{'name':'Secret','description':''}).json['id']
        self.post('/rooms/'+other+'/messages',dict(content='ULTRA_PRIVATE_OTHER_ROOM',request_id='private'))
        self.settings(); self.message(); self.agent.process_one()
        self.assertEqual(len(self.calls),1)
        self.assertNotIn('ULTRA_PRIVATE_OTHER_ROOM',json.dumps(self.calls))
    def test_password_change_and_security_headers(self):
        self.assertEqual(self.post('/password',dict(current='a-long-admin-password',password='a-new-long-password')).status_code,200)
        self.assertEqual(self.admin.post('/api/login',json={'email':'admin@example.com','password':'a-long-admin-password'}).status_code,401)
        self.assertEqual(self.admin.post('/api/login',json={'email':'admin@example.com','password':'a-new-long-password'}).status_code,200)
        self.assertEqual(self.admin.get('/').headers['X-Frame-Options'],'DENY')

if __name__=='__main__': unittest.main()
