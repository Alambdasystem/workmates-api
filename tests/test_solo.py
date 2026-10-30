import unittest
import test_social as fixture

class SoloTests(unittest.TestCase):
 setUp=fixture.SocialTests.setUp
 tearDown=fixture.SocialTests.tearDown
 member=fixture.SocialTests.member
 def test_private_room_is_hidden_even_from_other_admins_and_not_invitable(self):
  result=self.m.post(self.p+'/solo',json={},headers=self.mh);self.assertEqual(result.status_code,201);rid=result.json['id'];path='/api/rooms/'+rid
  self.assertEqual(self.m.post(self.p+'/solo',json={},headers=self.mh).json['id'],rid)
  own=self.m.get(path).json;self.assertTrue(own['private']);self.assertEqual(len(own['members']),1)
  self.assertEqual(self.a.get(path).status_code,404)
  self.assertNotIn(rid,[r['id'] for r in self.a.get('/api/rooms').json])
  self.assertIn(rid,[r['id'] for r in self.m.get('/api/rooms').json])
  self.assertEqual(self.m.post(path+'/invites',json={'channel':'phone'},headers=self.mh).status_code,403)
 def test_live_handshake_and_transcripts_are_owner_only(self):
  rid=self.m.post(self.p+'/solo',json={},headers=self.mh).json['id'];path='/api/rooms/'+rid
  self.app.config['OPENAI_API_KEY']='server-only-test-key'
  calls=[]
  def transport(config,sdp,instructions,safety):calls.append((sdp,instructions,safety));return {'sdp':'v=0\r\nanswer','model':'gpt-realtime-2.1'}
  self.app.extensions['realtime_offer']=transport
  response=self.m.post(path+'/live',json={'sdp':'v=0\r\noffer'},headers=self.mh)
  self.assertEqual(response.status_code,200);self.assertNotIn('server-only',response.text);self.assertEqual(len(calls),1)
  self.assertEqual(self.a.post(path+'/live',json={'sdp':'v=0\r\noffer'},headers=self.h).status_code,404)
  self.assertEqual(self.m.post(self.p+'/live',json={'sdp':'v=0\r\noffer'},headers=self.mh).status_code,404)
  for role,text in [('user','Hello REIGN'),('assistant','Hello there')]:
   body={'role':role,'text':text,'event_id':role+'1'}
   self.assertEqual(self.m.post(path+'/live/transcript',json=body,headers=self.mh).status_code,201)
   self.assertEqual(self.m.post(path+'/live/transcript',json=body,headers=self.mh).status_code,200)
  self.assertEqual(len(self.m.get(path).json['messages']),2)
  self.assertEqual(len(self.m.get(self.p).json['messages']),0)
  self.assertEqual(self.a.post(path+'/live/transcript',json={'role':'user','text':'Intrusion','event_id':'other'},headers=self.h).status_code,404)
