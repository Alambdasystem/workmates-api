"""Self-service accounts and room ownership, without platform-role escalation."""
import time
import sqlite3
from flask import abort,g,jsonify,request
from werkzeug.security import generate_password_hash

SCHEMA='CREATE TABLE IF NOT EXISTS room_owners(room_id TEXT PRIMARY KEY REFERENCES rooms(id),owner_id TEXT NOT NULL REFERENCES users(id));'

def initialize_owners(store):
    with store.connect() as db:
        db.executescript(SCHEMA)
        admin=db.execute("SELECT id FROM users WHERE role='admin' ORDER BY rowid LIMIT 1").fetchone()
        if admin:
            db.execute('INSERT OR IGNORE INTO room_owners SELECT id,? FROM rooms WHERE id NOT IN (SELECT room_id FROM solo_rooms)',(admin['id'],))

def can_manage(db,room_id,user):
    return user['role']=='admin' or bool(db.execute('SELECT 1 FROM room_owners WHERE room_id=? AND owner_id=?',(room_id,user['id'])).fetchone()) or bool(db.execute('SELECT 1 FROM solo_rooms WHERE room_id=? AND owner_id=?',(room_id,user['id'])).fetchone())

def register_accounts(app,store,data,field,email_field,throttle,uid,digest,login_response):
    @app.post('/api/signup')
    def signup():
        throttle('signup-ip:'+request.remote_addr,5,3600)
        d=data();name=field(d,'name',80);email=email_field(d);password=field(d,'password',256,14)
        user_id=uid()
        try:
            with store.connect() as db:
                db.execute('INSERT INTO users VALUES(?,?,?,?,?)',(user_id,email,name,generate_password_hash(password),'member'))
        except sqlite3.IntegrityError:abort(409,'An account already uses this email. Sign in instead.')
        return login_response(user_id)

    @app.post('/api/invites/accept')
    def accept_shared_link():
        d=data();token=field(d,'token',100)
        throttle('accept-invite:'+g.user['id'],20,3600)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            invite=db.execute("SELECT * FROM invites WHERE token=? AND (email='' OR email=?) AND used=0 AND expires>?",(digest(token),g.user['email'],time.time())).fetchone()
            if not invite:abort(400,'This invitation is invalid, expired or belongs to another email.')
            db.execute('INSERT OR IGNORE INTO members VALUES(?,?)',(invite['room_id'],g.user['id']))
            db.execute('UPDATE invites SET used=1 WHERE token=?',(digest(token),))
            store.audit(db,invite['room_id'],g.user['name'],'member_joined','Accepted shared invitation link')
        return jsonify(ok=True,room_id=invite['room_id'])
