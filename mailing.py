"""Encrypted durable transactional mail outbox. No credentials or reset links in logs."""
import base64,hashlib,hmac,json,os,secrets,threading,time,urllib.request
from pathlib import Path
from cryptography.fernet import Fernet

SCHEMA='''
CREATE TABLE IF NOT EXISTS email_outbox(id TEXT PRIMARY KEY,recipient TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',attempts INTEGER NOT NULL DEFAULT 0,available REAL NOT NULL,created REAL NOT NULL,expires REAL,error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS email_preferences(user_id TEXT PRIMARY KEY REFERENCES users(id),verified INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS account_tokens(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),purpose TEXT NOT NULL,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS waitlist(id TEXT PRIMARY KEY,email TEXT NOT NULL UNIQUE,name TEXT NOT NULL,company TEXT NOT NULL,interest TEXT NOT NULL,consent INTEGER NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS personal_reminders(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),room_id TEXT NOT NULL REFERENCES rooms(id),title TEXT NOT NULL,due REAL NOT NULL,notified INTEGER NOT NULL DEFAULT 0);
'''
def relay_send(config,payload):
    url=config.get('MAIL_RELAY_URL') or os.getenv('MAIL_RELAY_URL','')
    key=config.get('MAIL_RELAY_SECRET') or os.getenv('MAIL_RELAY_SECRET','')
    if not url or not key:return 'not_configured'
    raw=json.dumps(payload).encode();stamp=str(int(time.time()))
    signature=hmac.new(key.encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    req=urllib.request.Request(url,data=raw,headers={'Content-Type':'application/json','X-Workmates-Time':stamp,'X-Workmates-Signature':signature})
    try:
        with urllib.request.urlopen(req,timeout=15) as response:value=json.load(response)
        return 'submitted' if value.get('accepted') else 'failed'
    except Exception:return 'failed'

class Mailer:
    def __init__(self,store,config):
        self.store,self.config=store,config
        with store.connect() as db:db.executescript(SCHEMA)
        path=Path(config['DB_PATH']).resolve().parent/'mail-outbox.key'
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as file:file.write(Fernet.generate_key())
        except FileExistsError:pass
        self.cipher=Fernet(path.read_bytes())
    def enqueue(self,db,email,kind,subject,body,url='',key=None,expires=None):
        now=time.time();mid=hashlib.sha256((key or secrets.token_urlsafe(24)).encode()).hexdigest()
        payload=self.cipher.encrypt(json.dumps(dict(to=email,type=kind,subject=subject[:160],body=body[:12000],url=url)).encode()).decode()
        db.execute('INSERT OR IGNORE INTO email_outbox(id,recipient,kind,payload,available,created,expires) VALUES(?,?,?,?,?,?,?)',(mid,email,kind,payload,now,now,expires))
        return mid
    def token(self,db,user_id,purpose):
        token=secrets.token_urlsafe(32);expires=time.time()+1800
        db.execute('UPDATE account_tokens SET used=1 WHERE user_id=? AND purpose=?',(user_id,purpose))
        db.execute('INSERT INTO account_tokens VALUES(?,?,?,?,0)',(hashlib.sha256(token.encode()).hexdigest(),user_id,purpose,expires))
        return token,expires
    def verify_email(self,db,user_id,email,name):
        db.execute('INSERT OR IGNORE INTO email_preferences(user_id) VALUES(?)',(user_id,))
        token,expires=self.token(db,user_id,'verify')
        return self.enqueue(db,email,'verify','Verify your Workmates email',f'Hi {name},\nConfirm your email to enable optional Workmates notification and reminder emails. This link expires in 30 minutes. If you did not request this, ignore it.',self.config['PUBLIC_APP_URL'].rstrip('/')+'/#verify='+token,expires=expires)
    def notification(self,db,user_id,nid,title,room_id):
        row=db.execute('SELECT u.email,p.enabled,p.verified FROM users u JOIN email_preferences p ON p.user_id=u.id WHERE u.id=?',(user_id,)).fetchone()
        if row and row['enabled'] and row['verified']:
            self.enqueue(db,row['email'],'notification','Workmates: '+title,title+'\nOpen Workmates to continue. You can disable notification emails under Email & reminders.',self.config['PUBLIC_APP_URL'].rstrip('/')+'/#room='+room_id,key='notification:'+nid)
    def due_reminders(self,db):
        rows=db.execute('SELECT r.*,u.name FROM personal_reminders r JOIN users u ON u.id=r.user_id WHERE r.notified=0 AND r.due<=? LIMIT 20',(time.time(),)).fetchall()
        for row in rows:
            member=db.execute('SELECT 1 FROM members WHERE room_id=? AND user_id=?',(row['room_id'],row['user_id'])).fetchone()
            if member:
                nid=secrets.token_hex(12);title='Reminder: '+row['title']
                db.execute('INSERT INTO notifications(id,user_id,room_id,title,created) VALUES(?,?,?,?,?)',(nid,row['user_id'],row['room_id'],title,time.time()))
                db.execute('INSERT INTO notification_events VALUES(?,?,?,NULL)',(nid,row['user_id'],'reminder'))
                self.notification(db,row['user_id'],nid,title,row['room_id'])
            db.execute('UPDATE personal_reminders SET notified=1 WHERE id=?',(row['id'],))
    def tick(self):
        now=time.time()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');self.due_reminders(db)
            db.execute("UPDATE email_outbox SET status='queued' WHERE status='processing' AND available<?",(now-180,))
            db.execute("UPDATE email_outbox SET status='expired',payload='' WHERE expires IS NOT NULL AND expires<? AND status IN ('queued','processing')",(now,))
            row=db.execute("SELECT * FROM email_outbox WHERE status='queued' AND available<=? ORDER BY created LIMIT 1",(now,)).fetchone()
            if not row:return False
            db.execute("UPDATE email_outbox SET status='processing',available=? WHERE id=?",(now,row['id']))
        try:status=relay_send(self.config,json.loads(self.cipher.decrypt(row['payload'].encode())))
        except Exception:status='failed'
        attempt=row['attempts']+1;retry=status!='submitted' and attempt<5
        with self.store.connect() as db:
            db.execute('UPDATE email_outbox SET status=?,attempts=?,available=?,error=?,payload=? WHERE id=?',('queued' if retry else status,attempt,now+min(1800,60*2**attempt),'' if status=='submitted' else status,row['payload'] if retry else '',row['id']))
        return True
    def start(self):
        def loop():
            while True:
                try:worked=self.tick()
                except Exception:worked=False
                time.sleep(.3 if worked else 5)
        threading.Thread(target=loop,daemon=True,name='workmates-mail').start()
