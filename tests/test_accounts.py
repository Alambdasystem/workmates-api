import tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import create_app
class AccountTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=create_app({'DB_PATH':self.tmp.name+'/db','ADMIN_EMAIL':'root@example.com','ADMIN_PASSWORD':'long-root-password','COOKIE_SECURE':False},start_worker=False)
 def tearDown(self):self.tmp.cleanup()
 def signup(self,email):
  c=self.app.test_client();r=c.post('/api/signup',json={'email':email,'name':'Owner','password':'long-user-password','role':'admin'});self.assertEqual(r.status_code,200);me=c.get('/api/me').json;self.assertEqual(me['role'],'member');return c,{'X-CSRF-Token':me['csrf']}
 def test_self_signup_ownership_and_invites(self):
  a,h=self.signup('one@example.com');b,bh=self.signup('two@example.com')
  rid=a.post('/api/rooms',json={'name':'My room','description':''},headers=h).json['id'];p='/api/rooms/'+rid
  self.assertTrue(a.get(p).json['can_manage']);self.assertEqual(b.get(p).status_code,404)
  settings={'agent_name':'REIGN','prompt':'Help us.','enabled':False,'mode':'mention','tools':[]}
  self.assertEqual(a.patch(p+'/workmate',json=settings,headers=h).status_code,200)
  invite=a.post(p+'/invites',json={'email':'two@example.com'},headers=h).json
  self.assertEqual(b.post('/api/join',json={'email':'two@example.com','name':'Two','password':'long-user-password','token':invite['token']}).status_code,200)
  self.assertFalse(b.get(p).json['can_manage']);bh={'X-CSRF-Token':b.get('/api/me').json['csrf']}
  self.assertEqual(b.patch(p+'/workmate',json=settings,headers=bh).status_code,403)
  phone=b.post(p+'/invites',json={'channel':'phone'},headers=bh).json
  other,oh=self.signup('three@example.com')
  self.assertEqual(other.post('/api/invites/accept',json={'token':phone['token']},headers=oh).status_code,200)
  self.assertEqual(other.post('/api/invites/accept',json={'token':phone['token']},headers=oh).status_code,400)
  a.post('/api/logout',json={},headers=h);self.assertEqual(a.post('/api/login',json={'email':'one@example.com','password':'long-user-password'}).status_code,200);self.assertEqual(a.get('/api/rooms').json[0]['id'],rid)
 def test_duplicate_and_invalid_signup_do_not_change_accounts(self):
  c,h=self.signup('one@example.com')
  self.assertEqual(c.post('/api/signup',json={'email':'one@example.com','name':'Other','password':'other-long-password'}).status_code,409)
  self.assertEqual(c.post('/api/signup',json={'email':'bad','name':'X','password':'short'}).status_code,400)
