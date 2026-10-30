import unittest
import test_social as fixture
class CallWorkspaceTests(unittest.TestCase):
 setUp=fixture.SocialTests.setUp;tearDown=fixture.SocialTests.tearDown;member=fixture.SocialTests.member
 def start(self):
  response=self.a.post(self.p+'/calls',json={},headers=self.h);self.assertEqual(response.status_code,201);return response.json
 def test_members_join_and_sync_but_outsiders_cannot(self):
  call=self.start();url=self.p+'/calls/'+call['id']
  join=self.m.post(url+'/join',json={},headers=self.mh);self.assertEqual(join.status_code,200)
  did=self.a.post(self.p+'/documents',json={'title':'Walkthrough','body':'## Purpose\nExplain this.\n\n## Decision\nApprove the launch.'},headers=self.h).json['id']
  change=self.a.patch(url+'/stage',json={'version':0,'kind':'document','asset_id':did,'page':0,'highlight':'block:0'},headers=self.h);self.assertEqual(change.status_code,200)
  shared=self.m.get(url).json;self.assertEqual(shared['stage']['asset_id'],did);self.assertEqual(shared['stage']['highlight'],'block:0')
  self.assertEqual(self.m.patch(url+'/stage',json={'version':1,'page':1},headers=self.mh).status_code,403)
  self.assertEqual(self.a.patch(url+'/stage',json={'version':0,'page':1},headers=self.h).status_code,409)
  self.assertEqual(self.app.test_client().get(url).status_code,401)
  other=self.a.post('/api/rooms',json={'name':'Other','description':''},headers=self.h).json['id'];outsider=self.member('outside@example.com',other)
  self.assertEqual(outsider.get(url).status_code,404)
 def test_signaling_is_scoped_and_recording_requires_everyone(self):
  call=self.start();url=self.p+'/calls/'+call['id'];host=call['participant_id']
  guest=self.m.post(url+'/join',json={},headers=self.mh).json['participant_id']
  self.assertEqual(self.a.post(url+'/signals',json={'participant_id':host,'target':guest,'payload':{'description':{'type':'offer','sdp':'v=0 offer'}}},headers=self.h).status_code,201)
  signals=self.m.post(url+'/poll',json={'participant_id':guest,'after':0},headers=self.mh).json['signals'];self.assertEqual(len(signals),1)
  self.assertEqual(self.m.post(url+'/signals',json={'participant_id':host,'target':guest,'payload':{}},headers=self.mh).status_code,404)
  self.assertEqual(self.a.post(url+'/recording',json={'participant_id':host,'recording':True},headers=self.h).status_code,409)
  for client,headers,pid in [(self.a,self.h,host),(self.m,self.mh,guest)]:
   self.assertEqual(client.post(url+'/consent',json={'participant_id':pid,'allow':True},headers=headers).status_code,200)
  self.assertEqual(self.a.post(url+'/recording',json={'participant_id':host,'recording':True},headers=self.h).status_code,200)
 def test_reign_tools_change_shared_stage_and_save_real_records(self):
  call=self.start();url=self.p+'/calls/'+call['id'];pid=call['participant_id']
  did=self.a.post(self.p+'/documents',json={'title':'Plan','body':'## Start\nDiscuss.\n\n## Finish\nDecide.'},headers=self.h).json['id']
  result=self.a.post(url+'/agent-action',json={'participant_id':pid,'call_id':'tool-1','name':'show_workspace_item','arguments':{'kind':'document','asset_id':did,'page':1}},headers=self.h)
  self.assertEqual(result.status_code,200);self.assertEqual(self.m.get(url).json['stage']['page'],1)
  body={'participant_id':pid,'call_id':'tool-2','name':'save_call_record','arguments':{'decisions':['Ship Friday'],'actions':[{'title':'Review deck','assignee':'Mayur'}]}}
  self.assertEqual(self.a.post(url+'/agent-action',json=body,headers=self.h).status_code,200)
  self.assertEqual(self.a.post(url+'/agent-action',json=body,headers=self.h).status_code,200)
  room=self.m.get(self.p).json;self.assertEqual(len(room['tasks']),1);self.assertTrue(any('Ship Friday' in d['body'] for d in room['documents']))
 def test_nonexistent_image_field_cannot_be_highlighted(self):
  call=self.start();url=self.p+'/calls/'+call['id']
  did=self.a.post(self.p+'/documents',json={'title':'Text only','body':'No image.'},headers=self.h).json['id']
  self.assertEqual(self.a.patch(url+'/stage',json={'version':0,'kind':'document','asset_id':did,'page':0,'highlight':'image'},headers=self.h).status_code,400)
 def test_dashboard_summaries_use_real_room_activity(self):
  self.a.post(self.p+'/messages',json={'content':'Latest group update','request_id':'dash-test'},headers=self.h)
  summary=next(r for r in self.m.get('/api/rooms').json if r['id']==self.p.split('/')[-1])
  self.assertEqual(summary['last_message']['content'],'Latest group update')
  self.assertGreater(summary['last_activity'],0)
  self.assertGreaterEqual(summary['member_count'],2)
 def test_only_one_presenter_and_room_scope(self):
  call=self.start();url=self.p+'/calls/'+call['id'];host=call['participant_id']
  guest=self.m.post(url+'/join',json={},headers=self.mh).json['participant_id']
  response=self.m.post(url+'/presentation',json={'participant_id':guest,'sharing':True,'stream_id':'screen-guest'},headers=self.mh)
  self.assertEqual(response.status_code,200)
  self.assertEqual(self.a.get(url).json['presentation']['participant_id'],guest)
  self.assertEqual(self.a.post(url+'/presentation',json={'participant_id':host,'sharing':True,'stream_id':'screen-host'},headers=self.h).status_code,409)
  self.assertEqual(self.a.post(url+'/presentation',json={'participant_id':guest,'sharing':False},headers=self.h).status_code,404)
  self.assertEqual(self.m.post(url+'/presentation',json={'participant_id':guest,'sharing':False},headers=self.mh).status_code,200)
  self.assertIsNone(self.a.get(url).json['presentation'])
  self.assertEqual(self.app.test_client().get(url).status_code,401)
 def test_call_file_context_is_scoped_to_room(self):
  did=self.a.post(self.p+'/documents',json={'title':'Call brief','body':'Discuss this budget.'},headers=self.h).json['id']
  url=self.p+'/call-item?kind=document&asset_id='+did
  self.assertEqual(self.m.get(url).json['pages'][0]['blocks'][0],'Discuss this budget.')
  other=self.a.post('/api/rooms',json={'name':'Other','description':''},headers=self.h).json['id']
  self.assertEqual(self.a.get('/api/rooms/'+other+'/call-item?kind=document&asset_id='+did).status_code,404)
  self.assertEqual(self.app.test_client().get(url).status_code,401)
 def test_voice_file_search_finds_real_saved_work(self):
  did=self.a.post(self.p+'/documents',json={'title':'Launch brief','body':'Discuss launch.'},headers=self.h).json['id']
  response=self.m.get('/api/call-files?q=launch')
  self.assertEqual(response.status_code,200);self.assertTrue(any(x['asset_id']==did for x in response.json['items']))
  other=self.a.post('/api/rooms',json={'name':'Secret','description':''},headers=self.h).json['id']
  secret=self.a.post('/api/rooms/'+other+'/documents',json={'title':'Launch secret','body':'Private'},headers=self.h).json['id']
  self.assertFalse(any(x['asset_id']==secret for x in self.m.get('/api/call-files?q=launch').json['items']))
