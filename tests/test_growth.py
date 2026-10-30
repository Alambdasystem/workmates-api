import unittest
import test_social as fixture
class GrowthTests(unittest.TestCase):
 setUp=fixture.SocialTests.setUp;tearDown=fixture.SocialTests.tearDown;member=fixture.SocialTests.member
 def test_waitlist_persists_once_and_is_admin_only(self):
  public=self.app.test_client();payload={'name':'New customer','email':'new@example.com','company':'Example','interest':'Shared work','consent':True}
  self.assertEqual(public.post('/api/waitlist',json=payload).status_code,202)
  self.assertEqual(public.post('/api/waitlist',json=payload).status_code,202)
  response=self.a.get('/api/admin/waitlist');self.assertEqual(response.status_code,200);self.assertEqual(len(response.json),1)
  self.assertEqual(public.get('/api/admin/waitlist').status_code,401)
 def test_reset_request_does_not_expose_user_or_token(self):
  public=self.app.test_client()
  known=public.post('/api/password/forgot',json={'email':'a@example.com'})
  unknown=public.post('/api/password/forgot',json={'email':'none@example.com'})
  self.assertEqual(known.status_code,200);self.assertEqual(known.json,unknown.json);self.assertNotIn('token',known.json)
 def test_email_preferences_default_off_and_require_verification(self):
  response=self.a.get('/api/preferences/email');self.assertEqual(response.status_code,200);self.assertFalse(response.json['enabled'])
  self.assertEqual(self.a.post('/api/preferences/email',json={'enabled':True},headers=self.h).status_code,400)
 def test_reset_is_single_use_and_revokes_sessions(self):
  mailer=self.app.extensions['mailer'];store=self.app.extensions['store'];user=self.a.get('/api/me').json['id']
  with store.connect() as db:token,_=mailer.token(db,user,'reset')
  public=self.app.test_client();payload={'token':token,'password':'a-new-long-local-test-password'}
  self.assertEqual(public.post('/api/password/reset',json=payload).status_code,200)
  self.assertEqual(self.a.get('/api/me').status_code,401)
  self.assertEqual(public.post('/api/password/reset',json=payload).status_code,400)
  self.assertEqual(public.post('/api/login',json={'email':'a@example.com','password':'a-new-long-local-test-password'}).status_code,200)
 def test_verified_opt_in_and_encrypted_mail_queue(self):
  from unittest.mock import patch
  mailer=self.app.extensions['mailer'];store=self.app.extensions['store'];user=self.a.get('/api/me').json['id']
  with store.connect() as db:
   token,_=mailer.token(db,user,'verify');mid=mailer.enqueue(db,'a@example.com','test','Test','private body',key='one')
   self.assertNotIn('private body',db.execute('SELECT payload FROM email_outbox WHERE id=?',(mid,)).fetchone()['payload'])
  self.assertEqual(self.app.test_client().post('/api/email/verify',json={'token':token}).status_code,200)
  self.assertEqual(self.a.post('/api/preferences/email',json={'enabled':True},headers=self.h).status_code,200)
  with patch('mailing.relay_send',return_value='submitted'):self.assertTrue(mailer.tick())
  with store.connect() as db:
   row=db.execute('SELECT status,payload FROM email_outbox WHERE id=?',(mid,)).fetchone();self.assertEqual(row['status'],'submitted');self.assertEqual(row['payload'],'')
 def test_expired_reset_and_future_reminder_validation(self):
  import time
  mailer=self.app.extensions['mailer'];store=self.app.extensions['store'];user=self.a.get('/api/me').json['id']
  with store.connect() as db:
   token,_=mailer.token(db,user,'reset');db.execute('UPDATE account_tokens SET expires=?',(time.time()-1,))
  self.assertEqual(self.app.test_client().post('/api/password/reset',json={'token':token,'password':'long-enough-test-password'}).status_code,400)
  self.assertEqual(self.a.post(self.p+'/reminders',json={'title':'Check demo','due_at':time.time()-1},headers=self.h).status_code,400)
  self.assertEqual(self.a.post(self.p+'/reminders',json={'title':'Check demo','due_at':time.time()+600},headers=self.h).status_code,201)
