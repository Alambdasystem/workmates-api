"""Public interest capture, email ownership, password recovery and personal reminders."""
import csv,io,secrets,time
from flask import abort,g,jsonify,request,Response
from werkzeug.security import generate_password_hash
from mailing import Mailer

def register_growth(app,store,accessible,data,field,email_field,throttle,uid,digest,admin,start_worker):
    mailer=Mailer(store,app.config);app.extensions['mailer']=mailer
    @app.post('/api/waitlist')
    def waitlist():
        throttle('waitlist-ip:'+request.remote_addr,5,3600);d=data()
        if d.get('website'):return jsonify(ok=True),202
        name=field(d,'name',80);email=email_field(d);company=field(d,'company',120,0);interest=field(d,'interest',2000,0)
        if d.get('consent') is not True:abort(400,'Confirm that we may contact you about Workmates.')
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM waitlist WHERE email=?',(email,)).fetchone():
                lead=uid();db.execute('INSERT INTO waitlist VALUES(?,?,?,?,?,?,?)',(lead,email,name,company,interest,1,time.time()))
                owner=db.execute("SELECT email FROM users WHERE role='admin' ORDER BY rowid LIMIT 1").fetchone()
                if owner:mailer.enqueue(db,owner['email'],'waitlist','New Workmates waiting-list signup',f'Name: {name}\nEmail: {email}\nCompany: {company}\nInterested in: {interest}\nConsent: contact about Workmates early access',app.config['PUBLIC_APP_URL'].rstrip('/')+'/app',key='lead:'+lead)
                mailer.enqueue(db,email,'waitlist_confirm','You are on the Workmates waiting list',f'Hi {name},\nThanks for your interest in Workmates. We saved your request for early-access updates. If you did not request this, ignore this email.',app.config['PUBLIC_APP_URL'],key='lead-confirm:'+lead)
        return jsonify(ok=True),202
    @app.get('/api/admin/waitlist')
    def list_waitlist():
        admin()
        with store.connect() as db:rows=db.execute('SELECT * FROM waitlist ORDER BY created DESC LIMIT 1000').fetchall()
        return jsonify([dict(r) for r in rows])
    @app.get('/api/admin/waitlist.csv')
    def export_waitlist():
        admin();output=io.StringIO();writer=csv.writer(output);writer.writerow(['Name','Email','Company','Interest','Contact consent','Joined UTC'])
        with store.connect() as db:
            for row in db.execute('SELECT * FROM waitlist ORDER BY created DESC'):
                safe=lambda v:"'"+str(v) if str(v).startswith(('=','+','-','@','\t','\r')) else str(v)
                writer.writerow([safe(row[k]) for k in ['name','email','company','interest']]+['Yes',time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime(row['created']))])
        return Response(output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="Workmates_Waiting_List.csv"'})
    @app.post('/api/password/forgot')
    def forgot():
        d=data();email=email_field(d);throttle('forgot-ip:'+request.remote_addr,5,3600);throttle('forgot-email:'+digest(email),3,3600)
        with store.connect() as db:
            row=db.execute('SELECT id,name FROM users WHERE email=?',(email,)).fetchone()
            if row:
                token,expires=mailer.token(db,row['id'],'reset')
                mailer.enqueue(db,email,'reset','Reset your Workmates password','Use the secure link below to choose a new password. It expires in 30 minutes and works once. If you did not request a reset, ignore this message.',app.config['PUBLIC_APP_URL'].rstrip('/')+'/#reset='+token,expires=expires)
        return jsonify(ok=True,message='If an account uses this email, a password reset link will be sent.')
    @app.post('/api/password/reset')
    def reset():
        d=data();token=field(d,'token',100);password=field(d,'password',256,14);throttle('reset-ip:'+request.remote_addr,10,3600)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute("SELECT * FROM account_tokens WHERE token=? AND purpose='reset' AND used=0 AND expires>?",(digest(token),time.time())).fetchone()
            if not row:abort(400,'This reset link is invalid or expired. Request a new one.')
            db.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(password),row['user_id']))
            db.execute('UPDATE account_tokens SET used=1 WHERE user_id=?',(row['user_id'],));db.execute('DELETE FROM sessions WHERE user_id=?',(row['user_id'],))
            user=db.execute('SELECT email FROM users WHERE id=?',(row['user_id'],)).fetchone()
            mailer.enqueue(db,user['email'],'security','Your Workmates password changed','Your password was changed and existing sessions were signed out. If this was not you, request another password reset immediately.',app.config['PUBLIC_APP_URL'].rstrip('/')+'/app')
        return jsonify(ok=True)
    @app.post('/api/email/verify')
    def verify():
        d=data();token=field(d,'token',100);throttle('verify-ip:'+request.remote_addr,10,3600)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute("SELECT * FROM account_tokens WHERE token=? AND purpose='verify' AND used=0 AND expires>?",(digest(token),time.time())).fetchone()
            if not row:abort(400,'This email verification link is invalid or expired.')
            db.execute('INSERT INTO email_preferences(user_id,verified) VALUES(?,1) ON CONFLICT(user_id) DO UPDATE SET verified=1',(row['user_id'],))
            db.execute('UPDATE account_tokens SET used=1 WHERE token=?',(digest(token),))
        return jsonify(ok=True)
    @app.get('/api/preferences/email')
    def get_email():
        with store.connect() as db:row=db.execute('SELECT * FROM email_preferences WHERE user_id=?',(g.user['id'],)).fetchone()
        return jsonify(enabled=bool(row and row['enabled']),verified=bool(row and row['verified']),email=g.user['email'])
    @app.post('/api/preferences/email')
    def set_email():
        d=data()
        if type(d.get('enabled')) is not bool:abort(400,'Choose an email preference.')
        with store.connect() as db:
            row=db.execute('SELECT verified FROM email_preferences WHERE user_id=?',(g.user['id'],)).fetchone()
            if d['enabled'] and not (row and row['verified']):abort(400,'Verify your email before enabling notification emails.')
            db.execute('INSERT INTO email_preferences(user_id,enabled) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled',(g.user['id'],int(d['enabled'])))
            if not d['enabled']:db.execute("UPDATE email_outbox SET status='cancelled',payload='' WHERE recipient=? AND kind='notification' AND status='queued'",(g.user['email'],))
        return jsonify(ok=True)
    @app.post('/api/preferences/email/verify')
    def request_verification():
        data();throttle('verify-email:'+g.user['id'],3,3600)
        with store.connect() as db:mailer.verify_email(db,g.user['id'],g.user['email'],g.user['name'])
        return jsonify(ok=True,message='Verification email queued. Check your inbox and spam folder.')
    @app.post('/api/rooms/<room_id>/reminders')
    def reminder(room_id):
        d=data();title=field(d,'title',200);due=d.get('due_at')
        if type(due) not in (int,float) or not time.time()+30<=due<=time.time()+366*86400:abort(400,'Choose a future reminder within one year.')
        throttle('reminder:'+g.user['id'],20,3600)
        with store.connect() as db:
            accessible(db,room_id);rid=uid();db.execute('INSERT INTO personal_reminders VALUES(?,?,?,?,?,0)',(rid,g.user['id'],room_id,title,due))
        return jsonify(id=rid),201
    @app.get('/api/admin/mail')
    def mail_status():
        admin()
        with store.connect() as db:rows=db.execute('SELECT id,recipient,kind,status,attempts,created,error FROM email_outbox ORDER BY created DESC LIMIT 100').fetchall()
        return jsonify([dict(row) for row in rows])
    @app.post('/api/admin/mail/test')
    def mail_test():
        data();admin();throttle('mail-test:'+g.user['id'],3,3600)
        with store.connect() as db:mid=mailer.enqueue(db,g.user['email'],'test','Workmates email delivery test','This is a real delivery test requested by your Workmates administrator. Confirm receipt in your inbox.',app.config['PUBLIC_APP_URL'])
        return jsonify(id=mid,status='queued'),202
    if start_worker:mailer.start()
