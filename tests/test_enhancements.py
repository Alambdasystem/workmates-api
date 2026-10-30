import time,unittest
import test_social as fixture
class EnhancementTests(unittest.TestCase):
 setUp=fixture.SocialTests.setUp;tearDown=fixture.SocialTests.tearDown;member=fixture.SocialTests.member
 def test_pins_are_shared_scoped_and_real(self):
  did=self.a.post(self.p+'/documents',json={'title':'Launch','body':'Real saved work'},headers=self.h).json['id']
  self.assertEqual(self.a.post(self.p+'/pins',json={'kind':'document','asset_id':did},headers=self.h).status_code,201)
  self.assertEqual(self.m.get(self.p+'/pins').json[0]['asset_id'],did)
  self.assertEqual(self.m.post(self.p+'/pins',json={'kind':'document','asset_id':'missing'},headers=self.mh).status_code,404)
  other=self.a.post('/api/rooms',json={'name':'Other','description':''},headers=self.h).json['id'];outsider=self.member('o@example.com',other)
  self.assertEqual(outsider.get(self.p+'/pins').status_code,404)
 def test_catchup_personal_explicit_read(self):
  self.a.post(self.p+'/messages',json={'content':'A new plan','request_id':'catchup-test'},headers=self.h)
  before=self.m.get(self.p+'/catch-up');self.assertEqual(before.status_code,200);self.assertGreater(len(before.json['messages']),0)
  self.assertEqual(len(self.m.get(self.p+'/catch-up').json['messages']),len(before.json['messages']))
  self.assertEqual(self.m.post(self.p+'/catch-up/read',json={},headers=self.mh).status_code,200)
  self.assertEqual(self.m.get(self.p+'/catch-up').json['messages'],[])
 def test_feedback_admin_only(self):
  payload={'summary':'Call failed','detail':'Microphone denied on test device','room_id':self.rid,'page':'chat','version':'test','device':'test browser'}
  self.assertEqual(self.m.post('/api/feedback',json=payload,headers=self.mh).status_code,201)
  self.assertEqual(len(self.a.get('/api/admin/feedback').json),1)
  self.assertEqual(self.m.get('/api/admin/feedback').status_code,403)
 def test_task_acceptance_due_permissions(self):
  user=self.m.get('/api/me').json['id']
  r=self.a.post(self.p+'/action-items',json={'title':'Review launch','owner_id':user,'due_at':time.time()+600},headers=self.h);self.assertEqual(r.status_code,201);tid=r.json['id']
  self.assertEqual(self.a.patch(self.p+'/action-items/'+tid,json={'status':'accepted'},headers=self.h).status_code,403)
  self.assertEqual(self.m.patch(self.p+'/action-items/'+tid,json={'status':'accepted'},headers=self.mh).status_code,200)
  self.assertEqual(self.m.patch(self.p+'/action-items/'+tid,json={'status':'done'},headers=self.mh).status_code,200)
  self.assertEqual(self.m.get(self.p+'/action-items').json[0]['status'],'done')
 def test_admin_controls_private_validated(self):
  self.assertEqual(self.m.get('/api/admin/operations').status_code,403)
  self.assertEqual(self.a.get('/api/admin/operations').status_code,200)
  self.assertEqual(self.a.post('/api/admin/limits',json={'daily_jobs':-1,'ai_paused':False},headers=self.h).status_code,400)
  self.assertEqual(self.a.post('/api/admin/limits',json={'daily_jobs':20,'ai_paused':True},headers=self.h).status_code,200)
 def test_ai_pause_blocks_new_invocation_but_allows_plain_chat(self):
  room=self.a.get(self.p).json
  self.assertEqual(self.a.patch(self.p+'/workmate',json={**room,'enabled':True,'mode':'mention'},headers=self.h).status_code,200)
  self.a.post('/api/admin/limits',json={'daily_jobs':20,'ai_paused':True},headers=self.h)
  self.assertEqual(self.m.post(self.p+'/messages',json={'content':'REIGN help','request_id':'paused-ai'},headers=self.mh).status_code,503)
  self.assertEqual(self.m.post(self.p+'/messages',json={'content':'Team hello','request_id':'plain-chat'},headers=self.mh).status_code,201)
 def test_feedback_screenshot_is_reporter_upload_admin_read(self):
  import io
  from PIL import Image
  fid=self.m.post('/api/feedback',json={'summary':'Screenshot','detail':'Test'},headers=self.mh).json['id'];buf=io.BytesIO();Image.new('RGB',(10,10),'green').save(buf,format='PNG')
  path='/api/feedback/'+fid+'/image';self.assertEqual(self.a.put(path,data=buf.getvalue(),content_type='image/png',headers=self.h).status_code,404)
  self.assertEqual(self.m.put(path,data=buf.getvalue(),content_type='image/png',headers=self.mh).status_code,200)
  self.assertEqual(self.m.get('/api/admin/feedback/'+fid+'/image').status_code,403)
  self.assertEqual(self.a.get('/api/admin/feedback/'+fid+'/image').mimetype,'image/jpeg')
 def test_reign_proposes_real_owner_and_records_usage(self):
  import json
  room=self.a.get(self.p).json;self.a.patch(self.p+'/workmate',json={**room,'enabled':True,'mode':'mention'},headers=self.h)
  self.app.config['OPENAI_API_KEY']='local-test-key';owner=self.m.get('/api/me').json['id'];agent=self.app.extensions['agent'];seen=[]
  def provider(payload,key):
   seen.append(payload['instructions'])
   if len(seen)==1:return {'usage':{'input_tokens':10,'output_tokens':5},'output':[{'type':'function_call','call_id':'test-action','name':'propose_action_item','arguments':json.dumps({'title':'Review demo','owner_id':owner,'due_at':time.time()+600})}]}
   return {'usage':{'input_tokens':20,'output_tokens':7},'output':[{'type':'message','content':[{'type':'output_text','text':'Action proposed; awaiting acceptance.'}]}]}
  agent.provider=provider
  self.assertEqual(self.a.post(self.p+'/messages',json={'content':'REIGN propose an action','request_id':'agent-action-test'},headers=self.h).status_code,201)
  self.assertTrue(agent.process_one());rows=self.m.get(self.p+'/action-items').json;self.assertEqual(len(rows),1);self.assertEqual(rows[0]['owner_id'],owner);self.assertEqual(rows[0]['status'],'proposed')
  self.assertIn(owner,seen[0]);usage=self.a.get('/api/admin/operations').json['usage'];self.assertEqual(usage[0]['input_tokens'],30)
