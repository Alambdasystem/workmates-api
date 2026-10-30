import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import create_app

class SocialTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.config=dict(DB_PATH=self.tmp.name+'/db',ADMIN_EMAIL='a@example.com',ADMIN_PASSWORD='long-admin-password',COOKIE_SECURE=False)
  self.app=create_app(self.config,start_worker=False);self.a=self.app.test_client();self.a.post('/api/login',json={'email':'a@example.com','password':'long-admin-password'});self.h={'X-CSRF-Token':self.a.get('/api/me').json['csrf']}
  self.rid=self.a.post('/api/rooms',json={'name':'Shared voice','description':''},headers=self.h).json['id'];self.p='/api/rooms/'+self.rid
  self.m=self.member('m@example.com',self.rid);self.mh={'X-CSRF-Token':self.m.get('/api/me').json['csrf']}
 def tearDown(self):self.tmp.cleanup()
 def member(self,email,room):
  token=self.a.post('/api/rooms/'+room+'/invites',json={'email':email},headers=self.h).json['token'];c=self.app.test_client();self.assertEqual(c.post('/api/join',json={'email':email,'name':email,'password':'long-member-password','token':token}).status_code,200);return c
 def test_voice_is_durable_shared_idempotent_and_private(self):
  audio=b'\x1aE\xdf\xa3'+b'audio'*100
  headers={**self.h,'X-Request-ID':'note','X-Audio-Duration':'12'}
  response=self.a.post(self.p+'/voice',data=audio,content_type='audio/webm',headers=headers);self.assertEqual(response.status_code,201);nid=response.json['id']
  self.assertEqual(self.a.post(self.p+'/voice',data=audio,content_type='audio/webm',headers=headers).status_code,200)
  messages=self.m.get(self.p).json['messages'];self.assertEqual(len(messages),1);self.assertEqual(messages[0]['attachments'][0]['type'],'voice')
  url=self.p+'/voice/'+nid;self.assertEqual(self.m.get(url).data,audio)
  partial=self.m.get(url,headers={'Range':'bytes=0-3'});self.assertEqual(partial.status_code,206);self.assertEqual(partial.data,audio[:4])
  self.assertEqual(self.app.test_client().get(url).status_code,401)
  other=self.a.post('/api/rooms',json={'name':'Other','description':''},headers=self.h).json['id'];outsider=self.member('o@example.com',other)
  self.assertEqual(outsider.get(url).status_code,404)
  self.assertEqual(self.a.post(self.p+'/voice',data=audio,content_type='audio/webm').status_code,403)
  self.assertEqual(self.a.post(self.p+'/voice',data=b'<script>',content_type='audio/webm',headers=headers).status_code,400)
  restarted=create_app(self.config,start_worker=False);self.assertEqual(restarted.extensions['store'].connect().__class__.__name__,'_GeneratorContextManager')
  with restarted.extensions['store'].connect() as db:self.assertEqual(db.execute('SELECT content FROM voice_notes WHERE id=?',(nid,)).fetchone()['content'],audio)
 def test_notifications_belong_to_recipient_and_accept_group(self):
  other=self.a.post('/api/rooms',json={'name':'New team','description':''},headers=self.h).json['id']
  with patch('server.deliver_invite',return_value='submitted') as mail:
   r=self.a.post('/api/rooms/'+other+'/invites',json={'email':'m@example.com'},headers=self.h).json
   self.assertEqual(r['email_status'],'submitted');mail.assert_called_once()
  notice=self.m.get('/api/notifications').json[0];self.assertTrue(notice['can_accept']);self.assertFalse(notice['seen'])
  self.assertEqual(self.m.get('/api/rooms/'+other).status_code,404)
  self.assertEqual(self.a.post('/api/notifications/'+notice['id']+'/accept',json={},headers=self.h).status_code,404)
  self.assertEqual(self.m.post('/api/notifications/'+notice['id']+'/accept',json={},headers=self.mh).status_code,200)
  self.assertEqual(self.m.get('/api/rooms/'+other).status_code,200)
  self.assertEqual(self.m.post('/api/notifications/'+notice['id']+'/accept',json={},headers=self.mh).status_code,400)
  self.assertTrue(self.m.get('/api/notifications').json[0]['seen'])
 def test_phone_invite_single_use_and_email_bound_invite(self):
  r=self.m.post(self.p+'/invites',json={'channel':'phone'},headers=self.mh);self.assertEqual(r.status_code,200);token=r.json['token']
  c=self.app.test_client();payload={'email':'phone@example.com','name':'Phone user','password':'long-phone-password','token':token}
  self.assertEqual(c.post('/api/join',json=payload).status_code,200);self.assertEqual(c.post('/api/join',json=payload).status_code,400)
  r=self.m.post(self.p+'/invites',json={'email':'intended@example.com'},headers=self.mh).json
  payload.update(email='wrong@example.com',token=r['token']);self.assertEqual(c.post('/api/join',json=payload).status_code,400)
 def test_background_persistence_validation_and_isolation(self):
  buf=io.BytesIO();Image.new('RGB',(20,20),'purple').save(buf,format='PNG');raw=buf.getvalue()
  self.assertEqual(self.a.put('/api/preferences/background/image',data=raw,content_type='image/png',headers=self.h).status_code,200)
  self.assertEqual(self.m.get('/api/preferences/background/image').status_code,404)
  theme=self.a.get('/api/preferences/background').json;self.assertTrue(theme['has_image']);self.assertEqual(theme['preset'],'upload')
  self.assertEqual(self.a.post('/api/preferences/background',json={'preset':'upload','opacity':.3},headers=self.h).status_code,200)
  self.assertEqual(self.a.get('/api/preferences/background/image').mimetype,'image/jpeg')
  self.assertEqual(self.a.post('/api/preferences/background',json={'preset':'cosmic','opacity':1},headers=self.h).status_code,400)
  self.assertEqual(self.a.put('/api/preferences/background/image',data=b'<svg/>',content_type='image/png',headers=self.h).status_code,400)
  self.assertEqual(self.a.delete('/api/preferences/background/image',headers=self.h).status_code,200)
  self.assertFalse(self.a.get('/api/preferences/background').json['has_image'])
