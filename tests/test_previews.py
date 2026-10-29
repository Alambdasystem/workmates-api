import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import create_app
from previews import sanitize_svg


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(dict(DB_PATH=self.temp.name+'/db', ADMIN_EMAIL='a@example.com', ADMIN_PASSWORD='long-preview-password', COOKIE_SECURE=False, OPENAI_API_KEY='test'), start_worker=False)
        self.c = self.app.test_client(); self.c.post('/api/login', json={'email':'a@example.com','password':'long-preview-password'})
        self.h = {'X-CSRF-Token': self.c.get('/api/me').json['csrf']}
        self.rid = self.c.post('/api/rooms', json={'name':'Preview','description':''}, headers=self.h).json['id']
        self.p = '/api/rooms/'+self.rid
        self.c.patch(self.p+'/workmate', json=dict(agent_name='REIGN', prompt='Help.', enabled=True, mode='mention', tools=['save_document','image_generation']), headers=self.h)
        self.c.post(self.p+'/messages', json={'content':'REIGN, make a Word document','request_id':'generate'}, headers=self.h)
        self.agent=self.app.extensions['agent']; self.store=self.app.extensions['store']
    def tearDown(self): self.temp.cleanup()
    def save_file(self, name, content):
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET status='running'")
            job=dict(db.execute('SELECT * FROM jobs LIMIT 1').fetchone())
        return self.agent.save_artifact(job,name,'application/octet-stream',content)
    def test_saved_document_is_associated_with_triggering_message(self):
        outputs=iter([{'output':[{'type':'function_call','call_id':'doc','name':'save_document','arguments':json.dumps({'title':'Plan','body':'## Goal\nA real document.'})}]}, {'output':[{'type':'message','content':[{'type':'output_text','text':'Saved.'}]}]}])
        self.agent.provider=lambda p,k:next(outputs);self.agent.process_one()
        room=self.c.get(self.p).json; output=room['generated_documents'][0]
        self.assertEqual(output['message_id'],room['messages'][0]['id'])
        self.assertEqual(output['document_id'],room['documents'][0]['id'])
        self.assertEqual(output['job_id'],room['jobs'][0]['id'])
    def test_inline_raster_preview_and_original_download_are_distinct(self):
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==')
        f=self.save_file('image.png',png)
        preview=self.c.get(self.p+'/files/'+f['id']+'/preview');download=self.c.get(self.p+'/files/'+f['id'])
        self.assertEqual(preview.mimetype,'image/png');self.assertEqual(preview.data,png)
        self.assertIn('inline;',preview.headers['Content-Disposition']);self.assertIn('attachment;',download.headers['Content-Disposition'])
        self.assertIn('sandbox',preview.headers['Content-Security-Policy'])
        file=self.c.get(self.p).json['files'][0];self.assertIn('message_id',file);self.assertIn('job_id',file)
        self.assertEqual(self.app.test_client().get(self.p+'/files/'+f['id']+'/preview').status_code,401)
        other=self.c.post('/api/rooms',json={'name':'Other','description':''},headers=self.h).json['id']
        self.assertEqual(self.c.get('/api/rooms/'+other+'/files/'+f['id']+'/preview').status_code,404)
    def test_svg_keeps_diagram_shapes_but_removes_scripts_and_external_resources(self):
        svg=b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100" onload="alert(1)"><script>alert(1)</script><image href="https://evil.example/image"/><style>@import 'https://evil.example/style';</style><defs><marker id="arrow"><path d="M0 0L4 4"/></marker></defs><rect x="1" y="1" width="80" height="40" fill="#abc"/><path marker-end="url(#arrow)" d="M1 1L100 50"/><text x="10" y="20">Team</text><a href="javascript:alert(1)"><text>bad link</text></a></svg>'''
        f=self.save_file('diagram.svg',svg);r=self.c.get(self.p+'/files/'+f['id']+'/preview')
        self.assertEqual(r.mimetype,'image/svg+xml');self.assertIn(b'Team',r.data);self.assertIn(b'url(#arrow)',r.data)
        for unsafe in (b'<script',b'onload',b'https://evil',b'javascript:',b'href='):self.assertNotIn(unsafe,r.data)
        self.assertEqual(self.c.get(self.p+'/files/'+f['id']).data,svg)
        with self.assertRaises(ValueError):sanitize_svg(b'<!DOCTYPE svg [<!ENTITY x "unsafe">]><svg/>')
        label=sanitize_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><g><foreignObject width="160" height="40"><div xmlns="http://www.w3.org/1999/xhtml">Team decision</div></foreignObject></g></svg>')
        self.assertIn(b'Team decision',label);self.assertNotIn(b'foreignObject',label);self.assertIn(b'<text',label)
    def test_text_preview_is_bounded_and_unknown_files_have_download_fallback(self):
        f=self.save_file('data.csv',b'row,value\nteam,60\n'+b'x'*40000)
        r=self.c.get(self.p+'/files/'+f['id']+'/preview').json
        self.assertEqual(r['kind'],'text');self.assertEqual(len(r['body']),20000)
        f=self.save_file('unknown.bin',b'\x00\xffbinary')
        self.assertEqual(self.c.get(self.p+'/files/'+f['id']+'/preview').json['kind'],'file')
    def test_running_job_is_not_lost_behind_recent_team_chat(self):
        for n in range(10):self.c.post(self.p+'/messages',json={'content':'Team update','request_id':str(n)},headers=self.h)
        room=self.c.get(self.p).json
        self.assertTrue(any(j['status']=='queued' and j['message_id']==room['messages'][0]['id'] for j in room['jobs']))


if __name__=='__main__':unittest.main()
