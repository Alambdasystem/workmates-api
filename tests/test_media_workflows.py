import base64
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image
import imageio_ffmpeg
from server import create_app, AVAILABLE_TOOLS
from compositions import make_slideshow,export_assets


def png(color):
    out=io.BytesIO();Image.new('RGB',(160,90),color).save(out,format='PNG');return out.getvalue()


class MediaWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.uploads=[];self.calls=[]
        self.config=dict(DB_PATH=self.temp.name+'/db',ADMIN_EMAIL='admin@example.com',ADMIN_PASSWORD='long-media-password',COOKIE_SECURE=False,OPENAI_API_KEY='test',TESTING=True)
        def upload(asset,key):self.uploads.append(asset['id']);return 'file-'+asset['id']
        self.app=create_app(self.config,start_worker=False,file_uploader=upload);self.c=self.app.test_client()
        self.c.post('/api/login',json=dict(email='admin@example.com',password='long-media-password'));self.h={'X-CSRF-Token':self.c.get('/api/me').json['csrf']}
        self.rid=self.post('/rooms',{'name':'Media','description':''}).json['id'];self.p='/rooms/'+self.rid
        self.agent=self.app.extensions['agent'];self.store=self.app.extensions['store'];self.settings(['image_generation','generate_images','create_presentation','create_image_document','create_slideshow','read_saved_image','list_saved_files'])
    def tearDown(self):self.temp.cleanup()
    def post(self,path,data,method='POST'):return self.c.open('/api'+path,json=data,method=method,headers=self.h)
    def room(self):return self.c.get('/api'+self.p).json
    def settings(self,tools):self.post(self.p+'/workmate',dict(agent_name='REIGN',prompt='Help the group.',enabled=True,mode='mention',tools=tools),'PATCH')
    def message(self,text='REIGN, help',nonce='work',ids=None):return self.post(self.p+'/messages',dict(content=text,request_id=nonce,attachment_ids=ids or []))
    def seed(self,count=1):
        self.message('REIGN, make images','seed')
        with self.store.connect() as db:
            job=dict(db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 1').fetchone());db.execute("UPDATE jobs SET status='running' WHERE id=?",(job['id'],))
        files=[]
        for index in range(count):
            content=png((index*23%256,index*47%256,(255-index*17)%256))
            files.append({**self.agent.save_artifact(job,f'Skyline {index+1}.png','image/png',content,{'prompt':f'Skyline scene {index+1}'}),'content':content})
        with self.store.connect() as db:db.execute("UPDATE jobs SET status='completed' WHERE id=?",(job['id'],))
        return files
    @staticmethod
    def reply(text='Saved.'):return {'output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}
    @staticmethod
    def tool(name,args):return {'output':[{'type':'function_call','name':name,'call_id':name,'arguments':json.dumps(args)}]}
    def run_tools(self,responses):
        iterator=iter(responses)
        def provider(payload,key):self.calls.append(json.loads(json.dumps(payload)));return next(iterator)
        self.agent.provider=provider;self.assertTrue(self.agent.process_one());self.assertEqual(self.room()['jobs'][0]['status'],'completed',self.room()['jobs'][0])
    def test_later_request_receives_actual_pixels_catalog_and_explicit_selection_after_restart(self):
        images=self.seed(2);self.message('REIGN, use this image as the presentation background','later',[images[0]['id']])
        self.run_tools([self.reply()]);payload=self.calls[0]
        self.assertIn(images[0]['id'],payload['instructions']);self.assertIn('authoritative',payload['instructions'])
        parts=payload['input'][-1]['content'];self.assertTrue(any(p['type']=='input_image' and p['image_url'].startswith('data:image/jpeg;base64,') for p in parts))
        self.assertIn(images[0]['id'],parts[0]['text'])
        user=next(m for m in self.room()['messages'] if m['kind']=='human' and m['content'].endswith('background'))
        self.assertEqual(user['attachments'][0]['id'],images[0]['id'])
        self.message('REIGN put this same image inside Word','followup')
        self.run_tools([self.reply()]);followup=self.calls[-1]['input'][-1]['content']
        self.assertIn(images[0]['id'],followup[0]['text']);self.assertFalse(any(images[1]['id'] in p.get('text','') for p in followup))
        restarted=create_app(self.config,start_worker=False)
        with restarted.extensions['store'].connect() as db:
            row=db.execute('SELECT content,meta FROM artifacts WHERE id=?',(images[0]['id'],)).fetchone()
            self.assertEqual(row['content'],images[0]['content']);self.assertIn('Skyline scene 1',row['meta'])
    def test_foreign_group_attachment_is_rejected(self):
        image=self.seed()[0];other=self.post('/rooms',{'name':'Other','description':''}).json['id']
        response=self.post('/rooms/'+other+'/messages',{'content':'REIGN use this','request_id':'foreign','attachment_ids':[image['id']]})
        self.assertEqual(response.status_code,404)
    def test_future_file_is_not_in_older_request_context_or_composition(self):
        self.seed();self.message('REIGN use the current image','older');self.message('REIGN make a later image','newer')
        with self.store.connect() as db:
            later=dict(db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 1').fetchone());db.execute("UPDATE jobs SET status='running' WHERE id=?",(later['id'],))
        future=self.agent.save_artifact(later,'Future.png','image/png',png('orange'))
        with self.store.connect() as db:db.execute("UPDATE jobs SET status='completed' WHERE id=?",(later['id'],))
        self.run_tools([self.tool('create_image_document',dict(title='Must not use future',introduction='',images=[dict(file_id=future['id'],caption='Future')])),self.reply('That file is not available to this request.')])
        self.assertNotIn(future['id'],self.calls[0]['instructions'])
        result=json.loads(next(i['output'] for i in self.calls[1]['input'] if i.get('type')=='function_call_output'))
        self.assertIn('not available',result['error']);self.assertFalse(any(f['filename'].endswith('.docx') for f in self.room()['files']))
    def test_exact_images_embed_in_ten_image_word_and_presentation_background(self):
        images=self.seed(10);ids=[i['id'] for i in images]
        self.message('REIGN make a Word document and a presentation from these','exports',ids)
        self.run_tools([self.tool('create_image_document',dict(title='Ten saved images',introduction='Reuse the original images.',images=[dict(file_id=i['id'],caption=f'Image {n+1}') for n,i in enumerate(images)])),self.tool('create_presentation',dict(title='Skyline deck',slides=[dict(title='Launch',body='Use the selected skyline as the background.',image_id=ids[0],layout='background')])),self.reply()])
        files=self.room()['files'];word=next(f for f in files if f['filename'].endswith('.docx'));slides=next(f for f in files if f['filename'].endswith('.pptx'))
        with zipfile.ZipFile(io.BytesIO(self.c.get('/api'+self.p+'/files/'+word['id']).data)) as archive:
            embedded=[archive.read(n) for n in archive.namelist() if n.startswith('word/media/')]
            self.assertEqual(len(embedded),10)
            self.assertEqual({hashlib.sha256(b).hexdigest() for b in embedded},{hashlib.sha256(i['content']).hexdigest() for i in images})
        ppt=self.c.get('/api'+self.p+'/files/'+slides['id']).data
        with zipfile.ZipFile(io.BytesIO(ppt)) as archive:
            self.assertEqual(archive.read('ppt/media/image1.png'),images[0]['content'])
            xml=archive.read('ppt/slides/slide1.xml');self.assertIn(b'Launch',xml);self.assertIn(b'72000',xml)
        preview=self.c.get('/api'+self.p+'/files/'+slides['id']+'/preview').json
        self.assertEqual(preview['kind'],'presentation');self.assertEqual(preview['meta']['slides'][0]['image_id'],ids[0])
        self.assertEqual(word['meta']['source_ids'],ids)
    def test_oversized_office_image_sets_use_copies_without_changing_originals(self):
        original=png('red')+b'\0'*(3*1024*1024)
        assets={str(i):{'id':str(i),'content':original} for i in range(10)}
        copies,optimized=export_assets(assets)
        self.assertTrue(optimized);self.assertEqual(assets['0']['content'],original)
        self.assertLess(sum(len(a['content']) for a in copies.values()),2*1024*1024)
        with Image.open(io.BytesIO(copies['0']['content'])) as image:self.assertGreater(image.getpixel((50,40))[0],245)
    def test_code_workspace_receives_selected_original_file_and_caches_upload(self):
        image=self.seed()[0];self.settings(['code_interpreter']);self.message('REIGN inspect this file','code1',[image['id']]);self.run_tools([self.reply()])
        tool=self.calls[0]['tools'][0];self.assertEqual(tool['container']['file_ids'],['file-'+image['id']]);self.assertEqual(self.uploads,[image['id']])
        self.message('REIGN use it again','code2',[image['id']]);self.run_tools([self.reply()]);self.assertEqual(self.uploads,[image['id']])
    def test_ten_generated_fixture_images_compose_in_one_request(self):
        self.message('REIGN generate ten images and put them in Word, PowerPoint and MP4','batch');outer=[0];inner=[];batch_files=[]
        def provider(payload,key):
            if payload.get('tool_choice'):
                index=len(inner);inner.append(payload['input']);return {'output':[{'type':'image_generation_call','id':'image-'+str(index),'result':base64.b64encode(png((index*23,20,200))).decode()}]}
            outer[0]+=1
            if outer[0]==1:return self.tool('generate_images',dict(title='Batch',prompts=['Scene '+str(i) for i in range(10)]))
            if outer[0]==2:
                saved=json.loads(next(i['output'] for i in payload['input'] if i.get('type')=='function_call_output'))['files']
                batch_files.extend(saved)
                return self.tool('create_image_document',dict(title='Batch book',introduction='Ten generated scenes.',images=[{'file_id':f['id'],'caption':str(n+1)} for n,f in enumerate(saved)]))
            if outer[0]==3:return self.tool('create_presentation',dict(title='Batch slides',slides=[{'title':'A generated scene','body':'The saved image is the background.','image_id':batch_files[0]['id'],'layout':'background'}]))
            if outer[0]==4:return self.tool('create_slideshow',dict(title='Batch video',image_ids=[f['id'] for f in batch_files],seconds_per_image=1,transition='fade',transition_seconds=.3))
            return self.reply('Ten images are saved and embedded in the Word document.')
        self.agent.provider=provider;self.agent.process_one();room=self.room()
        self.assertEqual(room['jobs'][0]['status'],'completed');self.assertEqual(len(inner),10)
        self.assertEqual(len([f for f in room['files'] if f['mime']=='image/png']),10)
        word=next(f for f in room['files'] if f['filename'].endswith('.docx'));self.assertEqual(len(word['meta']['source_ids']),10)
        self.assertTrue(any(f['filename'].endswith('.pptx') for f in room['files']));self.assertEqual(len(next(f for f in room['files'] if f['filename'].endswith('.mp4'))['meta']['source_ids']),10)
        with zipfile.ZipFile(io.BytesIO(self.c.get('/api'+self.p+'/files/'+word['id']).data)) as archive:self.assertEqual(len([n for n in archive.namelist() if n.startswith('word/media/')]),10)
    def test_partial_batch_keeps_saved_images_and_cannot_silently_repeat(self):
        self.message('REIGN generate three images','partial');outer=[0];inner=[0]
        def provider(payload,key):
            if payload.get('tool_choice'):
                inner[0]+=1
                if inner[0]==3:raise RuntimeError('Provider failed')
                return {'output':[{'type':'image_generation_call','result':base64.b64encode(png((inner[0]*60,20,20))).decode()}]}
            outer[0]+=1
            if outer[0]<=2:return self.tool('generate_images',dict(title='Partial',prompts=['A','B','C']))
            result=json.loads([i['output'] for i in payload['input'] if i.get('type')=='function_call_output'][-1]);self.assertIn('already attempted',result['error']);return self.reply('Two images were saved; the third failed.')
        self.agent.provider=provider;self.agent.process_one();self.assertEqual(inner[0],3);self.assertEqual(len(self.room()['files']),2)
    def test_mp4_transitions_decode_real_frames_with_expected_duration(self):
        assets=[{'content':png('red')},{'content':png('green')}]
        for effect in ('fade','slide','wipe','dissolve'):
            content=make_slideshow(assets,1,effect,.4,size=(160,90),fps=10)
            path=Path(self.temp.name)/(effect+'.mp4');path.write_bytes(content)
            decoder=imageio_ffmpeg.read_frames(str(path),pix_fmt='rgb24');metadata=next(decoder);frames=list(decoder)
            self.assertEqual(metadata['size'],(160,90));self.assertAlmostEqual(metadata['duration'],1.6,delta=.2);self.assertGreaterEqual(len(frames),15)
            def mean(frame,c):return sum(frame[c::3])/(160*90)
            self.assertGreater(mean(frames[0],0),220);self.assertGreater(mean(frames[-1],1),100)
            middle=frames[8];self.assertGreater(mean(middle,0),30);self.assertGreater(mean(middle,1),25)
    def test_canceled_video_render_exits_without_returning_a_file(self):
        checks=[0]
        def canceled():
            checks[0]+=1
            if checks[0]>=3:raise RuntimeError('Workmate stopped')
        with self.assertRaisesRegex(RuntimeError,'Workmate stopped'):
            make_slideshow([{'content':png('red')},{'content':png('blue')}],4,'fade',.5,canceled,size=(320,180),fps=10)
    def test_ten_images_render_through_chat_tool_to_playable_mp4(self):
        images=self.seed(10);self.message('REIGN make a ten-image MP4 slideshow','video',[i['id'] for i in images])
        self.run_tools([self.tool('create_slideshow',dict(title='Ten scene video',image_ids=[i['id'] for i in images],seconds_per_image=1,transition='fade',transition_seconds=.3)),self.reply()])
        file=next(f for f in self.room()['files'] if f['mime']=='video/mp4');response=self.c.get('/api'+self.p+'/files/'+file['id']+'/preview')
        self.assertEqual(response.mimetype,'video/mp4');self.assertEqual(response.data[4:8],b'ftyp')
        path=Path(self.temp.name)/'ten.mp4';path.write_bytes(response.data);reader=imageio_ffmpeg.read_frames(str(path));meta=next(reader);first=next(reader);reader.close()
        self.assertEqual(meta['size'],(1280,720));self.assertAlmostEqual(meta['duration'],7.3,delta=.2);self.assertTrue(first)
    def test_drive_image_copy_preserves_original_and_tracks_only_confirmed_success(self):
        image=self.seed()[0];drive=self.app.extensions['drive'];uid=self.c.get('/api/me').json['id']
        with self.store.connect() as db:
            db.execute('INSERT INTO drive_connections VALUES(?,?,?,?,?)',('c',uid,'Google',drive.seal({'refresh_token':'test'}),1))
            db.execute('INSERT INTO drive_mounts VALUES(?,?,?,?,?,?)',('m',self.rid,'c','folder','Images',1))
        drive.within=lambda m,f:{'id':f,'mimeType':'application/vnd.google-apps.folder'};seen=[]
        def api(*a,**k):seen.append(k);return {'id':'remote','name':'Skyline.png','webViewLink':'https://drive.google.com/file/d/remote/view'}
        drive.api=api
        response=self.post(self.p+'/drive/save-file',{'file_id':image['id'],'mount_id':'m'})
        self.assertEqual(response.status_code,201);self.assertEqual(seen[0]['media'],image['content']);self.assertEqual(seen[0]['media_mime'],'image/png')
        self.assertEqual(len(self.room()['drive_copies']),1);self.assertEqual(self.c.get('/api'+self.p+'/files/'+image['id']).data,image['content'])
        self.assertEqual(self.c.post('/api'+self.p+'/drive/save-file',json={'file_id':image['id'],'mount_id':'m'}).status_code,403)
        def fail(*a,**k):raise RuntimeError('Drive failed')
        drive.api=fail;self.assertEqual(self.post(self.p+'/drive/save-file',{'file_id':image['id'],'mount_id':'m'}).status_code,400);self.assertEqual(len(self.room()['drive_copies']),1)


if __name__=='__main__':unittest.main()
