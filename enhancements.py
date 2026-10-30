"""Shared pins, explicit catch-up cursors, action ownership and beta operations."""
import json,time
from flask import abort,g,jsonify,request,send_file
import io
from PIL import Image

SCHEMA='''
CREATE TABLE IF NOT EXISTS room_pins(room_id TEXT NOT NULL,kind TEXT NOT NULL,asset_id TEXT NOT NULL,pinned_by TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(room_id,kind,asset_id));
CREATE TABLE IF NOT EXISTS room_reads(room_id TEXT NOT NULL,user_id TEXT NOT NULL,message_id INTEGER NOT NULL DEFAULT 0,action_id INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(room_id,user_id));
CREATE TABLE IF NOT EXISTS action_items(id TEXT PRIMARY KEY,room_id TEXT NOT NULL,title TEXT NOT NULL,owner_id TEXT NOT NULL,due REAL NOT NULL,status TEXT NOT NULL DEFAULT 'proposed',created REAL NOT NULL,created_by TEXT NOT NULL,reminder_id TEXT);
CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,room_id TEXT,summary TEXT NOT NULL,detail TEXT NOT NULL,page TEXT NOT NULL,version TEXT NOT NULL,device TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS feedback_images(feedback_id TEXT PRIMARY KEY,content BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS client_diagnostics(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,room_id TEXT,kind TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS ai_usage(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL,model TEXT NOT NULL,input_tokens INTEGER NOT NULL,output_tokens INTEGER NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS platform_limits(id INTEGER PRIMARY KEY CHECK(id=1),daily_jobs INTEGER NOT NULL DEFAULT 500,ai_paused INTEGER NOT NULL DEFAULT 0);
INSERT OR IGNORE INTO platform_limits(id) VALUES(1);
'''

def check_ai_budget(db):
 row=db.execute('SELECT * FROM platform_limits WHERE id=1').fetchone()
 if row and row['ai_paused']:abort(503,'AI is paused by the administrator. Team chat and saved work remain available.')
 if row and db.execute("SELECT count(*) FROM jobs WHERE created>? AND status!='chat_only'",(time.time()-86400,)).fetchone()[0]>=row['daily_jobs']:abort(429,'The workspace reached its AI request limit for the past 24 hours. Team chat remains available.')

def register_enhancements(app,store,accessible,admin,data,field,uid,throttle):
 with store.connect() as db:
  db.executescript(SCHEMA)
  if not db.execute("SELECT 1 FROM feature_migrations WHERE name='owned-actions-v1'").fetchone():
   for row in db.execute('SELECT id,tools FROM rooms').fetchall():
    tools=json.loads(row['tools'])
    if 'create_task' in tools and 'propose_action_item' not in tools:
     tools.append('propose_action_item');db.execute('UPDATE rooms SET tools=? WHERE id=?',(json.dumps(tools),row['id']))
   db.execute("INSERT INTO feature_migrations VALUES('owned-actions-v1')")
 store.mailer=app.extensions['mailer']
 def notify(db,user,rid,title,kind='action_item'):
  nid=uid();db.execute('INSERT INTO notifications(id,user_id,room_id,title,created) VALUES(?,?,?,?,?)',(nid,user,rid,title,time.time()));db.execute('INSERT INTO notification_events VALUES(?,?,?,NULL)',(nid,user,kind))
  app.extensions['mailer'].notification(db,user,nid,title,rid)
 @app.get('/api/rooms/<room_id>/pins')
 def pins(room_id):
  with store.connect() as db:
   accessible(db,room_id);rows=db.execute("SELECT p.*,coalesce(d.title,a.filename) AS title FROM room_pins p LEFT JOIN documents d ON p.kind='document' AND d.id=p.asset_id AND d.room_id=p.room_id LEFT JOIN artifacts a ON p.kind='file' AND a.id=p.asset_id AND a.room_id=p.room_id WHERE p.room_id=? AND (d.id IS NOT NULL OR a.id IS NOT NULL) ORDER BY p.created DESC",(room_id,)).fetchall()
  return jsonify([dict(r) for r in rows])
 @app.post('/api/rooms/<room_id>/pins')
 def pin(room_id):
  d=data();kind=field(d,'kind',20);aid=field(d,'asset_id',100)
  if kind not in ('document','file'):abort(400,'Choose a saved document or file.')
  with store.connect() as db:
   accessible(db,room_id);table='documents' if kind=='document' else 'artifacts'
   if not db.execute(f'SELECT 1 FROM {table} WHERE id=? AND room_id=?',(aid,room_id)).fetchone():abort(404,'That saved work is not in this room.')
   if db.execute('SELECT count(*) FROM room_pins WHERE room_id=?',(room_id,)).fetchone()[0]>=30:abort(400,'This room already has 30 pins.')
   db.execute('INSERT OR IGNORE INTO room_pins VALUES(?,?,?,?,?)',(room_id,kind,aid,g.user['id'],time.time()))
   store.audit(db,room_id,g.user['name'],'work_pinned',aid)
  return jsonify(ok=True),201
 @app.delete('/api/rooms/<room_id>/pins/<kind>/<asset_id>')
 def unpin(room_id,kind,asset_id):
  data()
  with store.connect() as db:accessible(db,room_id);db.execute('DELETE FROM room_pins WHERE room_id=? AND kind=? AND asset_id=?',(room_id,kind,asset_id))
  return jsonify(ok=True)
 @app.get('/api/rooms/<room_id>/catch-up')
 def catch_up(room_id):
  with store.connect() as db:
   accessible(db,room_id);cursor=db.execute('SELECT * FROM room_reads WHERE room_id=? AND user_id=?',(room_id,g.user['id'])).fetchone();mid=cursor['message_id'] if cursor else 0;aid=cursor['action_id'] if cursor else 0
   messages=[dict(r) for r in db.execute('SELECT id,author,kind,content,created FROM messages WHERE room_id=? AND id>? ORDER BY id LIMIT 100',(room_id,mid))]
   actions=[dict(r) for r in db.execute('SELECT id,actor,action,detail,created FROM actions WHERE room_id=? AND id>? ORDER BY id LIMIT 100',(room_id,aid))]
   tasks=[dict(r) for r in db.execute("SELECT id,title,status,due FROM action_items WHERE room_id=? AND owner_id=? AND status NOT IN ('done','declined') ORDER BY due",(room_id,g.user['id']))]
  return jsonify(messages=messages,changes=actions,assigned=tasks,truncated=len(messages)==100 or len(actions)==100,message_cursor=max([mid]+[m['id'] for m in messages]),action_cursor=max([aid]+[a['id'] for a in actions]))
 @app.post('/api/rooms/<room_id>/catch-up/read')
 def catch_up_read(room_id):
  d=data()
  with store.connect() as db:
   accessible(db,room_id)
   latest=lambda table:db.execute(f'SELECT coalesce(max(id),0) FROM {table} WHERE room_id=?',(room_id,)).fetchone()[0]
   mid,aid=d.get('message_cursor',latest('messages')),d.get('action_cursor',latest('actions'))
   if type(mid) is not int or type(aid) is not int or mid<0 or aid<0 or mid>latest('messages') or aid>latest('actions'):abort(400,'Invalid read cursor.')
   db.execute('INSERT INTO room_reads VALUES(?,?,?,?) ON CONFLICT(room_id,user_id) DO UPDATE SET message_id=max(message_id,excluded.message_id),action_id=max(action_id,excluded.action_id)',(room_id,g.user['id'],mid,aid))
  return jsonify(ok=True)
 @app.get('/api/rooms/<room_id>/action-items')
 def action_items(room_id):
  with store.connect() as db:accessible(db,room_id);rows=db.execute('SELECT a.*,u.name AS owner FROM action_items a JOIN users u ON u.id=a.owner_id WHERE room_id=? ORDER BY created DESC LIMIT 100',(room_id,)).fetchall()
  return jsonify([dict(r) for r in rows])
 @app.post('/api/rooms/<room_id>/action-items')
 def propose_action(room_id):
  d=data();title=field(d,'title',200);owner=field(d,'owner_id',100);due=d.get('due_at')
  if type(due) not in (int,float) or not time.time()+30<=due<=time.time()+366*86400:abort(400,'Choose a future due date within one year.')
  throttle('actions:'+g.user['id'],30,3600);tid=uid()
  with store.connect() as db:
   accessible(db,room_id)
   if not db.execute("SELECT 1 FROM users WHERE id=? AND (role='admin' OR id IN (SELECT user_id FROM members WHERE room_id=?))",(owner,room_id)).fetchone():abort(400,'Choose a current room member.')
   db.execute('INSERT INTO action_items(id,room_id,title,owner_id,due,created,created_by) VALUES(?,?,?,?,?,?,?)',(tid,room_id,title,owner,due,time.time(),g.user['id']))
   notify(db,owner,room_id,'Action proposed: '+title);store.audit(db,room_id,g.user['name'],'action_proposed',title)
  return jsonify(id=tid),201
 @app.patch('/api/rooms/<room_id>/action-items/<task_id>')
 def accept_action(room_id,task_id):
  d=data();status=d.get('status')
  if status not in ('accepted','declined','done'):abort(400,'Choose accepted, declined or done.')
  with store.connect() as db:
   db.execute('BEGIN IMMEDIATE');accessible(db,room_id);row=db.execute('SELECT * FROM action_items WHERE id=? AND room_id=?',(task_id,room_id)).fetchone()
   if not row:abort(404,'Action item not found.')
   if row['owner_id']!=g.user['id']:abort(403,'Only the assigned person can accept or complete this action.')
   if status=='done' and row['status']!='accepted':abort(409,'Accept the action before marking it done.')
   if row['status'] in ('done','declined') and row['status']!=status:abort(409,'This action is already closed.')
   reminder=row['reminder_id']
   if status=='accepted' and not reminder:
    reminder=uid();db.execute('INSERT INTO personal_reminders VALUES(?,?,?,?,?,0)',(reminder,g.user['id'],room_id,'Due: '+row['title'],row['due']))
   if status in ('done','declined') and reminder:db.execute('UPDATE personal_reminders SET notified=1 WHERE id=?',(reminder,))
   db.execute('UPDATE action_items SET status=?,reminder_id=? WHERE id=?',(status,reminder,task_id));store.audit(db,room_id,g.user['name'],'action_'+status,row['title'])
  return jsonify(ok=True)
 @app.post('/api/feedback')
 def feedback():
  d=data();throttle('feedback:'+g.user['id'],10,3600);fid=uid();rid=d.get('room_id');summary=field(d,'summary',200);detail=field(d,'detail',4000,0)
  with store.connect() as db:
   if rid:accessible(db,rid)
   db.execute('INSERT INTO feedback(id,user_id,room_id,summary,detail,page,version,device,created) VALUES(?,?,?,?,?,?,?,?,?)',(fid,g.user['id'],rid,summary,detail,str(d.get('page',''))[:40],str(d.get('version',''))[:80],str(d.get('device',''))[:300],time.time()))
  return jsonify(id=fid),201
 @app.put('/api/feedback/<feedback_id>/image')
 def feedback_image(feedback_id):
  if request.mimetype not in ('image/png','image/jpeg','image/webp'):abort(415,'Choose a PNG, JPEG or WebP screenshot.')
  raw=request.get_data()
  if len(raw)>2*1024*1024:abort(400,'Choose a screenshot below 2 MB.')
  with store.connect() as db:
   if not db.execute('SELECT 1 FROM feedback WHERE id=? AND user_id=?',(feedback_id,g.user['id'])).fetchone():abort(404,'Report not found.')
   try:
    image=Image.open(io.BytesIO(raw))
    if image.width*image.height>12000000:raise ValueError()
    image=image.convert('RGB');image.thumbnail((2000,2000));output=io.BytesIO();image.save(output,format='JPEG',quality=85)
   except Exception:abort(400,'Could not read that screenshot.')
   db.execute('INSERT OR REPLACE INTO feedback_images VALUES(?,?)',(feedback_id,output.getvalue()))
  return jsonify(ok=True)
 @app.get('/api/admin/feedback/<feedback_id>/image')
 def feedback_admin_image(feedback_id):
  admin()
  with store.connect() as db:row=db.execute('SELECT content FROM feedback_images WHERE feedback_id=?',(feedback_id,)).fetchone()
  if not row:abort(404,'No screenshot attached.')
  return send_file(io.BytesIO(row['content']),mimetype='image/jpeg',download_name='feedback.jpg')
 @app.get('/api/admin/feedback')
 def feedback_admin():
  admin()
  with store.connect() as db:rows=db.execute('SELECT f.*,u.name,u.email,EXISTS(SELECT 1 FROM feedback_images i WHERE i.feedback_id=f.id) AS has_image FROM feedback f JOIN users u ON u.id=f.user_id ORDER BY created DESC LIMIT 100').fetchall()
  return jsonify([dict(r) for r in rows])
 @app.patch('/api/admin/feedback/<feedback_id>')
 def feedback_status(feedback_id):
  admin();d=data();status=d.get('status')
  if status not in ('open','investigating','resolved'):abort(400,'Invalid issue status.')
  with store.connect() as db:
   if not db.execute('UPDATE feedback SET status=? WHERE id=?',(status,feedback_id)).rowcount:abort(404,'Report not found.')
  return jsonify(ok=True)
 @app.post('/api/diagnostics')
 def diagnostics():
  d=data();throttle('diagnostics:'+g.user['id'],60,3600);kind=d.get('kind');state=d.get('state');rid=d.get('room_id')
  if kind not in ('group_call','solo_call') or state not in ('connecting','connected','failed','ended','microphone_denied','playback_blocked'):abort(400,'Invalid diagnostic event.')
  with store.connect() as db:
   if rid:accessible(db,rid)
   db.execute('INSERT INTO client_diagnostics VALUES(?,?,?,?,?,?)',(uid(),g.user['id'],rid,kind,state,time.time()))
  return jsonify(ok=True),201
 @app.post('/api/admin/limits')
 def limits():
  admin();d=data();limit=d.get('daily_jobs');paused=d.get('ai_paused')
  if type(limit) is not int or not 1<=limit<=10000 or type(paused) is not bool:abort(400,'Set a request limit from 1 to 10000 and an AI pause setting.')
  with store.connect() as db:db.execute('UPDATE platform_limits SET daily_jobs=?,ai_paused=? WHERE id=1',(limit,int(paused)))
  return jsonify(ok=True)
 @app.get('/api/admin/operations')
 def operations():
  admin();since=time.time()-86400
  with store.connect() as db:
   counts=lambda table,column:[dict(r) for r in db.execute(f'SELECT {column},count(*) AS count FROM {table} WHERE created>? GROUP BY {column}',(since,))]
   value={'limits':dict(db.execute('SELECT daily_jobs,ai_paused FROM platform_limits WHERE id=1').fetchone()),'active_users':db.execute('SELECT count(DISTINCT user_id) FROM sessions WHERE expires>?',(time.time(),)).fetchone()[0],'jobs':counts('jobs','status'),'calls':counts('client_diagnostics','state'),'email':counts('email_outbox','status'),'usage':[dict(r) for r in db.execute('SELECT model,sum(input_tokens) AS input_tokens,sum(output_tokens) AS output_tokens,count(*) AS responses FROM ai_usage WHERE created>? GROUP BY model',(since,))],'recent_failures':[dict(r) for r in db.execute("SELECT id,room_id,error,created FROM jobs WHERE status='failed' ORDER BY created DESC LIMIT 20")],'feedback_open':db.execute("SELECT count(*) FROM feedback WHERE status!='resolved'").fetchone()[0]}
  return jsonify(value)
