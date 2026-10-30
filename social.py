"""Shared voice notes, recipient-scoped invites/notifications, and personal themes."""
import io
import json
import os
import time
import hmac
import hashlib
import urllib.request
from urllib.parse import quote
from flask import abort, g, jsonify, request, send_file, current_app
from PIL import Image, ImageOps

SCHEMA='''
CREATE TABLE IF NOT EXISTS voice_notes(id TEXT PRIMARY KEY,room_id TEXT NOT NULL REFERENCES rooms(id),user_id TEXT NOT NULL REFERENCES users(id),message_id INTEGER NOT NULL REFERENCES messages(id),mime TEXT NOT NULL,content BLOB NOT NULL,duration REAL NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),room_id TEXT NOT NULL REFERENCES rooms(id),title TEXT NOT NULL,invite_hash TEXT,seen INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS notification_events(notification_id TEXT PRIMARY KEY REFERENCES notifications(id),actor_id TEXT NOT NULL,kind TEXT NOT NULL,call_id TEXT);
CREATE TABLE IF NOT EXISTS personal_themes(user_id TEXT PRIMARY KEY REFERENCES users(id),preset TEXT NOT NULL DEFAULT 'none',opacity REAL NOT NULL DEFAULT 0.15,image BLOB,updated REAL NOT NULL);
'''

def deliver_invite(config,email,inviter,room_name,url):
    relay=config.get('MAIL_RELAY_URL') or os.getenv('MAIL_RELAY_URL','')
    secret=config.get('MAIL_RELAY_SECRET') or os.getenv('MAIL_RELAY_SECRET','')
    if not relay or not secret:return 'not_configured'
    payload=json.dumps({'to':email,'inviter':inviter,'group':room_name,'url':url}).encode()
    stamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),stamp.encode()+b'.'+payload,hashlib.sha256).hexdigest()
    req=urllib.request.Request(relay,data=payload,headers={'Content-Type':'application/json','X-Workmates-Time':stamp,'X-Workmates-Signature':signature})
    try:
        with urllib.request.urlopen(req,timeout=15) as r:value=json.load(r)
        return 'submitted' if value.get('accepted') else 'failed'
    except Exception:return 'failed'

def notify_room_join(db,room_id,actor_id,actor_name,kind,uid,call_id=None):
    if db.execute('SELECT 1 FROM solo_rooms WHERE room_id=?',(room_id,)).fetchone():return
    room=db.execute('SELECT name FROM rooms WHERE id=?',(room_id,)).fetchone()
    if not room:return
    title=actor_name+(' joined the call in ' if kind=='call_joined' else ' joined ')+room['name']
    for member in db.execute('SELECT user_id FROM members WHERE room_id=? AND user_id!=?',(room_id,actor_id)).fetchall():
        prior=db.execute('SELECT 1 FROM notifications n JOIN notification_events e ON e.notification_id=n.id WHERE n.user_id=? AND n.room_id=? AND e.actor_id=? AND e.kind=? AND n.created>?',(member['user_id'],room_id,actor_id,kind,time.time()-60)).fetchone()
        if prior:continue
        nid=uid();db.execute('INSERT INTO notifications(id,user_id,room_id,title,created) VALUES(?,?,?,?,?)',(nid,member['user_id'],room_id,title,time.time()))
        db.execute('INSERT INTO notification_events VALUES(?,?,?,?)',(nid,actor_id,kind,call_id))
        mailer=current_app.extensions.get('mailer')
        if mailer:mailer.notification(db,member['user_id'],nid,title,room_id)

def register_social(app,store,accessible,data,uid,digest,throttle,field):
    with store.connect() as db:db.executescript(SCHEMA)

    @app.post('/api/rooms/<room_id>/voice')
    def save_voice(room_id):
        with store.connect() as db:accessible(db,room_id)
        throttle('voice:'+g.user['id'],20,60)
        mime=request.mimetype
        raw=request.get_data()
        if mime not in ('audio/webm','audio/mp4','audio/ogg','audio/mpeg','audio/wav'):abort(415,'Unsupported voice format.')
        if not raw or len(raw)>6*1024*1024:abort(413,'Voice notes must be under 6 MB.')
        valid=(mime=='audio/webm' and raw.startswith(b'\x1aE\xdf\xa3') or mime=='audio/mp4' and raw[4:8]==b'ftyp' or mime=='audio/ogg' and raw.startswith(b'OggS') or mime=='audio/wav' and raw.startswith(b'RIFF') and raw[8:12]==b'WAVE' or mime=='audio/mpeg' and (raw.startswith(b'ID3') or raw.startswith(b'\xff')))
        if not valid:abort(400,'The recording does not match its audio format.')
        nonce=request.headers.get('X-Request-ID','')
        if not 1<=len(nonce)<=64:abort(400,'A stable recording request ID is required.')
        try:duration=float(request.headers.get('X-Audio-Duration','0'))
        except ValueError:abort(400,'Invalid recording duration.')
        if not 0<duration<=180:abort(400,'Record up to three minutes.')
        nid=digest(g.user['id']+':'+room_id+':voice:'+nonce)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');accessible(db,room_id)
            if db.execute('SELECT 1 FROM voice_notes WHERE id=?',(nid,)).fetchone():return jsonify(id=nid,ok=True)
            total=db.execute('SELECT coalesce(sum(length(content)),0) FROM voice_notes WHERE room_id=?',(room_id,)).fetchone()[0]+db.execute('SELECT coalesce(sum(length(content)),0) FROM artifacts WHERE room_id=?',(room_id,)).fetchone()[0]
            if total+len(raw)>128*1024*1024:abort(413,'This group has reached its saved-file storage limit.')
            attachment={'id':nid,'type':'voice','mime':mime,'duration':duration,'url':f'/api/rooms/{room_id}/voice/{nid}'}
            mid=db.execute('INSERT INTO messages(room_id,user_id,author,kind,content,created,attachments) VALUES(?,?,?,?,?,?,?)',(room_id,g.user['id'],g.user['name'],'human','Voice message',time.time(),json.dumps([attachment]))).lastrowid
            db.execute('INSERT INTO voice_notes VALUES(?,?,?,?,?,?,?,?)',(nid,room_id,g.user['id'],mid,mime,raw,duration,time.time()))
            store.audit(db,room_id,g.user['name'],'voice_sent','Shared a voice message')
        return jsonify(id=nid,ok=True),201

    @app.get('/api/rooms/<room_id>/voice/<note_id>')
    def play_voice(room_id,note_id):
        with store.connect() as db:
            accessible(db,room_id)
            note=db.execute('SELECT * FROM voice_notes WHERE room_id=? AND id=?',(room_id,note_id)).fetchone()
        if not note:abort(404,'Voice message not found.')
        ext={'audio/webm':'webm','audio/mp4':'m4a','audio/ogg':'ogg','audio/wav':'wav','audio/mpeg':'mp3'}[note['mime']]
        return send_file(io.BytesIO(note['content']),mimetype=note['mime'],as_attachment=False,download_name='Voice message.'+ext,conditional=True)

    @app.get('/api/notifications')
    def list_notifications():
        with store.connect() as db:
            rows=db.execute("SELECT n.id,n.room_id,n.title,n.seen,n.created,i.used,i.expires,coalesce(e.kind,'invitation') AS kind,e.call_id FROM notifications n LEFT JOIN invites i ON i.token=n.invite_hash LEFT JOIN notification_events e ON e.notification_id=n.id WHERE n.user_id=? ORDER BY n.created DESC LIMIT 50",(g.user['id'],)).fetchall()
        return jsonify([dict(r,can_accept=r['used']==0 and (r['expires'] or 0)>time.time()) for r in rows])

    @app.post('/api/notifications/<notification_id>/read')
    def read_notification(notification_id):
        with store.connect() as db:
            row=db.execute('SELECT id FROM notifications WHERE id=? AND user_id=?',(notification_id,g.user['id'])).fetchone()
            if not row:abort(404,'Notification not found.')
            db.execute('UPDATE notifications SET seen=1 WHERE id=?',(notification_id,))
        return jsonify(ok=True)

    @app.post('/api/notifications/<notification_id>/accept')
    def accept_notification(notification_id):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT n.room_id,n.invite_hash,i.email,i.used,i.expires FROM notifications n JOIN invites i ON i.token=n.invite_hash WHERE n.id=? AND n.user_id=?',(notification_id,g.user['id'])).fetchone()
            if not row or row['email']!=g.user['email']:abort(404,'Invitation not found.')
            if row['used'] or row['expires']<=time.time():abort(400,'This invitation is expired or has already been accepted.')
            inserted=db.execute('INSERT OR IGNORE INTO members VALUES(?,?)',(row['room_id'],g.user['id'])).rowcount
            if inserted:notify_room_join(db,row['room_id'],g.user['id'],g.user['name'],'member_joined',uid)
            db.execute('UPDATE invites SET used=1 WHERE token=?',(row['invite_hash'],))
            db.execute('UPDATE notifications SET seen=1 WHERE id=?',(notification_id,))
            store.audit(db,row['room_id'],g.user['name'],'member_joined','Accepted group invitation')
        return jsonify(ok=True,room_id=row['room_id'])

    def theme_row():
        with store.connect() as db:return db.execute('SELECT * FROM personal_themes WHERE user_id=?',(g.user['id'],)).fetchone()

    @app.get('/api/preferences/background')
    def get_theme():
        row=theme_row()
        return jsonify(preset=row['preset'] if row else 'none',opacity=row['opacity'] if row else .15,has_image=bool(row and row['image']),updated=row['updated'] if row else 0)

    @app.post('/api/preferences/background')
    def set_theme():
        d=data();preset=field(d,'preset',20)
        if preset not in ('none','cosmic','aurora','sunset','upload'):abort(400,'Choose a background style.')
        opacity=d.get('opacity',.15)
        if type(opacity) not in (int,float) or not 0<=opacity<=.45:abort(400,'Choose a fade from 0 to 45%.')
        with store.connect() as db:
            row=db.execute('SELECT image FROM personal_themes WHERE user_id=?',(g.user['id'],)).fetchone()
            image=row['image'] if row else None
            if preset=='upload' and not image:abort(400,'Upload an image first.')
            db.execute('INSERT INTO personal_themes VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET preset=excluded.preset,opacity=excluded.opacity,updated=excluded.updated',(g.user['id'],preset,opacity,image,time.time()))
        return jsonify(ok=True)

    @app.put('/api/preferences/background/image')
    def upload_theme():
        throttle('background:'+g.user['id'],10,60)
        raw=request.get_data()
        if len(raw)>6*1024*1024:abort(413,'Use an image under 6 MB.')
        try:
            with Image.open(io.BytesIO(raw)) as original:
                if original.format not in ('PNG','JPEG','WEBP') or original.width*original.height>20000000:raise ValueError()
                image=ImageOps.exif_transpose(original).convert('RGB');image.thumbnail((1600,1600));out=io.BytesIO();image.save(out,format='JPEG',quality=85)
        except Exception:abort(400,'Choose a PNG, JPEG or WebP image under 20 megapixels.')
        with store.connect() as db:
            db.execute("INSERT INTO personal_themes VALUES(?,'upload',.15,?,?) ON CONFLICT(user_id) DO UPDATE SET image=excluded.image,preset='upload',updated=excluded.updated",(g.user['id'],out.getvalue(),time.time()))
        return jsonify(ok=True)

    @app.get('/api/preferences/background/image')
    def background_image():
        row=theme_row()
        if not row or not row['image']:abort(404,'Background not found.')
        return send_file(io.BytesIO(row['image']),mimetype='image/jpeg')

    @app.delete('/api/preferences/background/image')
    def delete_background():
        with store.connect() as db:db.execute("UPDATE personal_themes SET image=NULL,preset='none',updated=? WHERE user_id=?",(time.time(),g.user['id']))
        return jsonify(ok=True)
