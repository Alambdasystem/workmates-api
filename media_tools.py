"""Persistent group assets, visual context and real composition tools."""
import base64
import io
import json
from PIL import Image, ImageOps
from compositions import image_data, export_assets, make_word, make_presentation, make_slideshow, MIMES


def definition(name, description, properties):
    return {'type':'function','name':name,'description':description,'strict':True,'parameters':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}


STRING={'type':'string'}
TOOLS={
 'list_saved_files':definition('list_saved_files','Find real files saved in this group, including images from older messages. Empty query lists recent files. Use exact IDs, not guessed paths.',{'query':STRING}),
 'read_saved_image':definition('read_saved_image','Look at a saved image by its exact file ID. Its actual pixels are supplied for the next response.',{'file_id':STRING}),
 'create_image_document':definition('create_image_document','Create a real Word DOCX embedding up to ten saved images in order, with captions. Originals remain saved.',{'title':STRING,'introduction':STRING,'images':{'type':'array','items':{'type':'object','properties':{'file_id':STRING,'caption':STRING},'required':['file_id','caption'],'additionalProperties':False}}}),
 'create_presentation':definition('create_presentation','Create a real PowerPoint PPTX using saved images. layout background places the selected image behind readable text; image places it beside the text; none is text-only. Reuse the same ID for repeated backgrounds.',{'title':STRING,'slides':{'type':'array','items':{'type':'object','properties':{'title':STRING,'body':STRING,'image_id':STRING,'layout':{'type':'string','enum':['background','image','none']}},'required':['title','body','image_id','layout'],'additionalProperties':False}}}),
 'create_slideshow':definition('create_slideshow','Create a playable MP4 from up to ten saved images in order, with actual transitions. 1–8 seconds per image; 0.2–1 second transitions no longer than half the image duration.',{'title':STRING,'image_ids':{'type':'array','items':STRING},'seconds_per_image':{'type':'number'},'transition':{'type':'string','enum':['fade','slide','wipe','dissolve']},'transition_seconds':{'type':'number'}}),
 'generate_images':definition('generate_images','Generate and persist a batch of two to ten images from individual prompts. Use this for a multi-image request before composing a document, presentation or video. Partial failures retain successful images; never silently retry them.',{'title':STRING,'prompts':{'type':'array','items':STRING}}),
}


def valid_text(value, maximum=200, empty=False):
    if not isinstance(value,str) or len(value)>maximum or (not empty and not value.strip()):
        raise ValueError('Use valid text within the tool size limits.')
    return value.strip()


def catalog(store, room_id, message_id, job_id, query=''):
    with store.connect() as db:
        rows=db.execute("SELECT a.id,a.filename,a.mime,a.meta,a.created,j.message_id FROM artifacts a JOIN jobs j ON j.id=a.job_id WHERE a.room_id=? AND (j.message_id<=? OR a.job_id=?) AND (?='' OR instr(lower(a.filename||' '||coalesce(json_extract(a.meta,'$.prompt'),'')),lower(?))>0) ORDER BY a.created DESC LIMIT 100",(room_id,message_id,job_id,query,query)).fetchall()
    values=[]
    for row in rows:
        meta=json.loads(row['meta']); value={k:row[k] for k in ('id','filename','mime','created','message_id')};value['prompt']=meta.get('prompt','')[:500]
        if meta.get('batch'):value.update(batch=meta['batch'],batch_position=meta['batch_position'])
        values.append(value)
    return values


def assets_for(store, job, ids):
    if not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids) or len(set(ids))>10:
        raise ValueError('Choose one to ten saved image IDs.')
    values={}
    with store.connect() as db:
        for aid in dict.fromkeys(ids):
            row=db.execute('SELECT a.* FROM artifacts a JOIN jobs j ON j.id=a.job_id WHERE a.id=? AND a.room_id=? AND (j.message_id<=? OR a.job_id=?)',(aid,job['room_id'],job['message_id'],job['id'])).fetchone()
            if not row:raise ValueError('A selected file is not available in this chat at this point in the conversation.')
            values[aid]=dict(row)
    return values


def visual_parts(asset):
    content,_=image_data(asset['content'])
    with Image.open(io.BytesIO(content)) as image:
        image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((1024,1024))
        out=io.BytesIO();image.save(out,format='JPEG',quality=85)
    return [{'type':'input_text','text':'Saved group image '+asset['id']+' — '+asset['filename']+'. This is an actual saved file, not a hypothetical image.'},
            {'type':'input_image','image_url':'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode(),'detail':'auto'}]


def execute_media(agent, job, name, args):
    with agent.store.connect() as db:
        room=agent.current(db,job)
        if name not in json.loads(room['tools']):return {'error':'Tool is not enabled by the admin.'}
    if name=='list_saved_files':
        return {'files':catalog(agent.store,job['room_id'],job['message_id'],job['id'],valid_text(args.get('query'),200,True))}
    if name=='read_saved_image':
        asset=assets_for(agent.store,job,[args.get('file_id')])[args['file_id']];image_data(asset['content'])
        return {'id':asset['id'],'filename':asset['filename'],'saved':True}
    title=valid_text(args.get('title'))
    def check():
        with agent.store.connect() as db:agent.current(db,job)
    def complete_sources(assets):
        if not any(json.loads(a['meta']).get('batch')==job['id'] for a in assets.values()):return
        with agent.store.connect() as db:
            batch=db.execute('SELECT requested FROM image_batches WHERE job_id=?',(job['id'],)).fetchone()
            count=sum(json.loads(row['meta']).get('batch')==job['id'] for row in db.execute('SELECT meta FROM artifacts WHERE job_id=?',(job['id'],)))
        if batch and count<batch['requested']:raise ValueError('The image batch is incomplete. Ask which saved images to use before composing a partial result.')
    if name=='generate_images':
        prompts=args.get('prompts')
        if not isinstance(prompts,list) or not 2<=len(prompts)<=10:raise ValueError('Use two to ten individual image prompts.')
        prompts=[valid_text(p,4000) for p in prompts];files=[]
        with agent.store.connect() as db:
            current=agent.current(db,job)
            if 'image_generation' not in json.loads(current['tools']):raise ValueError('Image generation must also be enabled by the administrator.')
            if db.execute('SELECT 1 FROM image_batches WHERE job_id=?',(job['id'],)).fetchone():
                return {'error':'This request already attempted its image batch. Saved images remain available. Ask the user before starting a new batch.'}
            db.execute('INSERT INTO image_batches VALUES(?,?)',(job['id'],len(prompts)))
        for index,prompt in enumerate(prompts):
            check()
            agent.progress(job,f'Generating image {index+1} of {len(prompts)} · {len(files)} saved')
            try:
                payload={'model':agent.config['OPENAI_MODEL'],'instructions':'Generate exactly one image for this prompt. No unrelated outputs.','input':prompt,'tools':[{'type':'image_generation','output_format':'png'}],'tool_choice':{'type':'image_generation'},'parallel_tool_calls':False,'store':False,'max_output_tokens':4000}
                if agent.config['OPENAI_MODEL'].startswith('gpt-6'):payload['reasoning']={'effort':'low'}
                result=agent.provider(payload,agent.config['OPENAI_API_KEY'])
                generated=next((o for o in result.get('output',[]) if o.get('type')=='image_generation_call' and o.get('result')),None)
                if not generated:raise RuntimeError('The provider returned no image.')
                files.append(agent.save_artifact(job,f'{title} {index+1}.png','image/png',base64.b64decode(generated['result'],validate=True),{'prompt':prompt,'batch':job['id'],'batch_position':index}))
            except Exception:
                check()
                return {'files':files,'error':f'Image {index+1} of {len(prompts)} did not finish. Earlier images remain saved. Do not regenerate them without a new user request.'}
        return {'saved':True,'files':files}
    if name=='create_image_document':
        agent.progress(job,'Building your Word document from saved images')
        entries=args.get('images')
        if not isinstance(entries,list) or not 1<=len(entries)<=10:raise ValueError('Choose one to ten images.')
        ids=[e['file_id'] for e in entries];assets=assets_for(agent.store,job,ids)
        complete_sources(assets)
        assets,optimized=export_assets(assets)
        introduction=valid_text(args.get('introduction'),4000,True)
        entries=[(assets[e['file_id']],valid_text(e['caption'],1000,True)) for e in entries]
        content=make_word(title,introduction,entries);extension='docx'
        meta={'kind':'image_document','optimized_images':optimized,'introduction':introduction,'images':[{'file_id':a['id'],'caption':caption} for a,caption in entries]}
    elif name=='create_presentation':
        agent.progress(job,'Building your PowerPoint with the saved image backgrounds')
        slides=args.get('slides')
        if not isinstance(slides,list) or not 1<=len(slides)<=20:raise ValueError('Use one to twenty slides.')
        ids=[s['image_id'] for s in slides if s.get('image_id')]
        assets=assets_for(agent.store,job,ids) if ids else {}
        complete_sources(assets)
        assets,optimized=export_assets(assets)
        prepared=[]
        for slide in slides:
            slide={**slide,'title':valid_text(slide.get('title'),120),'body':valid_text(slide.get('body'),600,True)}
            if slide['layout'] not in ('background','image','none'):raise ValueError('Use a supported slide layout.')
            if slide['layout']!='none' and not slide.get('image_id'):raise ValueError('Choose a saved image for this slide.')
            prepared.append((slide,assets.get(slide.get('image_id'))))
        content=make_presentation(title,prepared);extension='pptx';meta={'kind':'presentation','optimized_images':optimized,'slides':[s for s,_ in prepared]}
    elif name=='create_slideshow':
        agent.progress(job,'Rendering your MP4 slideshow and transitions')
        ids=args.get('image_ids');assets=assets_for(agent.store,job,ids)
        complete_sources(assets)
        if len(ids)>10:raise ValueError('Use up to ten images.')
        content=make_slideshow([assets[i] for i in ids],args.get('seconds_per_image'),args.get('transition'),args.get('transition_seconds'),check)
        extension='mp4';meta={'kind':'slideshow','transition':args['transition'],'seconds_per_image':args['seconds_per_image'],'transition_seconds':args['transition_seconds']}
    else:raise ValueError('Unknown media tool.')
    check();meta.update(title=title,source_ids=ids)
    file=agent.save_artifact(job,title+'.'+extension,MIMES[extension],content,meta)
    return {'saved':True,'file':file,'download_url':file['url'],'source_ids':ids,'optimized_images':meta.get('optimized_images',False)}
