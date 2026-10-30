import unittest
import test_social as fixture
class JoinAlerts(unittest.TestCase):
 setUp=fixture.SocialTests.setUp;tearDown=fixture.SocialTests.tearDown;member=fixture.SocialTests.member
 def test_member_join_alerts_existing_members_once(self):
  self.member('mayur@example.com',self.rid)
  alerts=self.a.get('/api/notifications').json
  matches=[x for x in alerts if x.get('kind')=='member_joined' and 'mayur@example.com' in x['title']]
  self.assertEqual(len(matches),1)
  self.assertEqual(matches[0]['room_id'],self.rid)
  self.assertTrue(any(x.get('kind')=='member_joined' for x in self.m.get('/api/notifications').json))
 def test_call_join_alert_is_scoped_deduplicated_and_no_self_alert(self):
  call=self.a.post(self.p+'/calls',json={},headers=self.h).json
  before=len(self.m.get('/api/notifications').json)
  self.a.post(self.p+'/calls',json={},headers=self.h)
  self.assertEqual(len(self.m.get('/api/notifications').json),before)
  alert=next(x for x in self.m.get('/api/notifications').json if x.get('kind')=='call_joined')
  self.assertEqual(alert['call_id'],call['id'])
  self.assertFalse(any(x.get('call_id')==call['id'] for x in self.a.get('/api/notifications').json))
  self.assertEqual(self.app.test_client().get('/api/notifications').status_code,401)
