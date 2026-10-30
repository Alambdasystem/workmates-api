"""Authenticated document, Canvas, artifact and Drive routes."""
import io
import re
import time
from urllib.parse import unquote
from flask import abort, g, jsonify, request, redirect, send_file
from documents import MIMES, export_document, import_document
from previews import file_preview


def register_workspace(app, store, drive, accessible, admin, data, uid, digest, throttle, field):
    def document(db, room_id, doc_id):
        accessible(db, room_id)
        row = db.execute('SELECT * FROM documents WHERE id=? AND room_id=?', (doc_id, room_id)).fetchone()
        if not row:
            abort(404, 'Document not found.')
        return row

    @app.get('/api/rooms/<room_id>/documents/<doc_id>')
    def get_document(room_id, doc_id):
        with store.connect() as db:
            value = dict(document(db, room_id, doc_id))
            value['history'] = [dict(r) for r in db.execute('SELECT version,title,body,actor,created FROM document_versions WHERE document_id=? ORDER BY version DESC LIMIT 30', (doc_id,))]
        return jsonify(value)

    @app.post('/api/rooms/<room_id>/documents')
    def create_document(room_id):
        d = data(); title, body = field(d, 'title', 200), field(d, 'body', 40000)
        doc_id = uid()
        with store.connect() as db:
            accessible(db, room_id)
            db.execute('INSERT INTO documents(id,room_id,title,body,created) VALUES(?,?,?,?,?)', (doc_id, room_id, title, body, time.time()))
            store.audit(db, room_id, g.user['name'], 'document_created', title)
        return jsonify(id=doc_id), 201

    @app.patch('/api/rooms/<room_id>/documents/<doc_id>')
    def edit_document(room_id, doc_id):
        d = data(); title, body = field(d, 'title', 200), field(d, 'body', 40000)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE'); current = document(db, room_id, doc_id)
            if type(d.get('version')) is not int or d['version'] != current['version']:
                abort(409, 'This document changed. Your draft is still here. Reload the saved version or branch your draft.')
            db.execute('INSERT OR IGNORE INTO document_versions VALUES(?,?,?,?,?,?)', (doc_id, current['version'], current['title'], current['body'], g.user['name'], time.time()))
            db.execute('UPDATE documents SET title=?,body=?,version=version+1 WHERE id=?', (title, body, doc_id))
            store.audit(db, room_id, g.user['name'], 'document_updated', title)
        return jsonify(ok=True, version=current['version'] + 1)

    @app.post('/api/rooms/<room_id>/documents/<doc_id>/branch')
    def branch_document(room_id, doc_id):
        d = data(); title = field(d, 'title', 200); branch_id = uid()
        with store.connect() as db:
            current = document(db, room_id, doc_id)
            body = d.get('body', current['body'])
            if not isinstance(body, str) or not 1 <= len(body.strip()) <= 40000:
                abort(400, 'Use a document body up to 40000 characters.')
            db.execute('INSERT INTO documents(id,room_id,title,body,created,parent_id) VALUES(?,?,?,?,?,?)', (branch_id, room_id, title, body, time.time(), doc_id))
            store.audit(db, room_id, g.user['name'], 'document_branched', title)
        return jsonify(id=branch_id), 201

    @app.get('/api/rooms/<room_id>/documents/<doc_id>/download/<fmt>')
    def download_document(room_id, doc_id, fmt):
        if fmt not in MIMES:
            abort(404, 'Download format not found.')
        with store.connect() as db:
            current = document(db, room_id, doc_id)
        content = export_document(current['title'], current['body'], fmt)
        filename = re.sub(r'[\x00-\x1f/\\]', '-', current['title'])[:160] or 'Document'
        return send_file(io.BytesIO(content), mimetype=MIMES[fmt], as_attachment=True, download_name=filename + '.' + fmt)

    @app.post('/api/rooms/<room_id>/documents/import')
    def upload_document(room_id):
        with store.connect() as db:
            accessible(db, room_id)
        throttle('import:' + g.user['id'], 20, 60)
        filename = unquote(request.headers.get('X-File-Name', ''))[:200]
        try:
            body = import_document(filename, request.get_data())
        except Exception as exc:
            abort(400, str(exc) if isinstance(exc, ValueError) else 'Could not read that document. Use an unencrypted Word, text PDF, Markdown or text file.')
        title = filename.rsplit('.', 1)[0].replace('/', '-') or 'Imported document'; doc_id = uid()
        with store.connect() as db:
            accessible(db, room_id)
            db.execute('INSERT INTO documents(id,room_id,title,body,created) VALUES(?,?,?,?,?)', (doc_id, room_id, title, body, time.time()))
            store.audit(db, room_id, g.user['name'], 'document_imported', title)
        return jsonify(id=doc_id), 201

    @app.get('/api/rooms/<room_id>/files/<file_id>')
    def download_file(room_id, file_id):
        with store.connect() as db:
            accessible(db, room_id)
            file = db.execute('SELECT * FROM artifacts WHERE room_id=? AND id=?', (room_id, file_id)).fetchone()
        if not file:
            abort(404, 'File not found.')
        return send_file(io.BytesIO(file['content']), mimetype=file['mime'], as_attachment=True, download_name=file['filename'])

    @app.get('/api/rooms/<room_id>/files/<file_id>/preview')
    def preview_file(room_id, file_id):
        with store.connect() as db:
            accessible(db, room_id)
            file = db.execute('SELECT filename,content,mime,meta FROM artifacts WHERE room_id=? AND id=?', (room_id, file_id)).fetchone()
        if not file:
            abort(404, 'File not found.')
        import json
        meta=json.loads(file['meta'])
        if meta.get('kind') in ('presentation','image_document'):
            return jsonify(kind=meta['kind'],title=meta.get('title',file['filename']),meta=meta)
        if file['mime']=='video/mp4' and file['content'][4:8]==b'ftyp':
            return send_file(io.BytesIO(file['content']),mimetype='video/mp4',as_attachment=False,download_name='preview.mp4')
        try:
            kind, mime, content = file_preview(file['filename'], file['content'])
        except ValueError:
            return jsonify(kind='file', title=file['filename'], body='A visual preview is unavailable for this file. You can still download the original.')
        if kind == 'image':
            response = send_file(io.BytesIO(content), mimetype=mime, as_attachment=False, download_name='preview' + ('.svg' if mime == 'image/svg+xml' else ''))
            # Also sandbox direct navigation to SVG; the UI displays it only as an image.
            response.headers['Content-Security-Policy'] = "sandbox; default-src 'none'; style-src 'unsafe-inline'"
            return response
        return jsonify(kind=kind, title=file['filename'], body=content)

    @app.get('/api/integrations/google')
    def google_status():
        admin()
        return jsonify(drive.status(g.user['id']))

    @app.post('/api/integrations/google/configure')
    def google_configure():
        admin(); d = data()
        try:
            drive.configure(field(d, 'client_id', 500), field(d, 'client_secret', 500), field(d, 'origin', 500))
        except ValueError as exc:
            abort(400, str(exc))
        return jsonify(ok=True)

    @app.post('/api/integrations/google/connect')
    def google_connect():
        admin(); throttle('drive-connect:' + g.user['id'], 10, 600)
        try:
            url = drive.start(g.user['id'], digest(request.cookies.get('wm_session', '')))
        except ValueError as exc:
            abort(400, str(exc))
        return jsonify(url=url)

    @app.get('/api/integrations/google/callback')
    def google_callback():
        # The one-time state is bound to the initiating, still-live admin session.
        try:
            drive.complete(request.args.get('state', ''), request.args.get('code', ''))
        except (ValueError, RuntimeError):
            return redirect('/#drive=failed')
        return redirect('/#drive=connected')

    @app.delete('/api/integrations/google/<connection_id>')
    def google_disconnect(connection_id):
        admin()
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM drive_connections WHERE id=? AND user_id=?', (connection_id, g.user['id'])).fetchone():
                abort(404, 'Google account not found.')
            affected = [r[0] for r in db.execute('SELECT room_id FROM drive_mounts WHERE connection_id=?', (connection_id,))]
            db.execute('DELETE FROM drive_mounts WHERE connection_id=?', (connection_id,))
            db.execute('DELETE FROM drive_connections WHERE id=?', (connection_id,))
            for rid in affected:
                db.execute('UPDATE rooms SET revision=revision+1 WHERE id=?', (rid,))
                db.execute("UPDATE jobs SET status='canceled',error='Google account disconnected.' WHERE room_id=? AND status IN ('queued','running')", (rid,))
                store.audit(db, rid, g.user['name'], 'drive_disconnected', 'Google credentials removed from Workmates')
        return jsonify(ok=True)

    @app.post('/api/rooms/<room_id>/drive/mounts')
    def mount_drive(room_id):
        admin(); d = data()
        with store.connect() as db:
            accessible(db, room_id)
        try:
            cid = field(d, 'connection_id', 100)
            if drive.connection(cid)['user_id'] != g.user['id']:
                abort(404, 'Google account not found.')
            mid = drive.mount(room_id, cid, field(d, 'folder_id', 200), field(d, 'name', 200, 0))
        except (ValueError, RuntimeError) as exc:
            abort(400, str(exc))
        with store.connect() as db:
            store.audit(db, room_id, g.user['name'], 'drive_mounted', 'Folder shared with this group')
        return jsonify(id=mid), 201

    @app.delete('/api/rooms/<room_id>/drive/mounts/<mount_id>')
    def unmount_drive(room_id, mount_id):
        admin()
        with store.connect() as db:
            accessible(db, room_id)
            db.execute('DELETE FROM drive_mounts WHERE id=? AND room_id=?', (mount_id, room_id))
            db.execute('UPDATE rooms SET revision=revision+1 WHERE id=?', (room_id,))
            db.execute("UPDATE jobs SET status='canceled',error='Drive folder disconnected.' WHERE room_id=? AND status IN ('queued','running')", (room_id,))
            store.audit(db, room_id, g.user['name'], 'drive_unmounted', 'Folder removed from group')
        return jsonify(ok=True)

    @app.post('/api/rooms/<room_id>/drive/browse')
    def browse_drive(room_id):
        d = data()
        with store.connect() as db:
            accessible(db, room_id)
        try:
            value = drive.list_files(room_id, field(d, 'mount_id', 100), d.get('folder_id'), d.get('page_token', ''))
        except (ValueError, RuntimeError) as exc:
            abort(400, str(exc))
        return jsonify(value)

    @app.post('/api/rooms/<room_id>/drive/import')
    def import_drive(room_id):
        d = data()
        with store.connect() as db:
            accessible(db, room_id)
        try:
            value = drive.read_file(room_id, field(d, 'mount_id', 100), field(d, 'file_id', 200))
        except (ValueError, RuntimeError) as exc:
            abort(400, str(exc))
        doc_id = uid()
        with store.connect() as db:
            accessible(db, room_id)
            db.execute('INSERT INTO documents(id,room_id,title,body,created) VALUES(?,?,?,?,?)', (doc_id, room_id, value['title'][:200], value['body'], time.time()))
            store.audit(db, room_id, g.user['name'], 'drive_imported', value['title'])
        return jsonify(id=doc_id), 201

    @app.post('/api/rooms/<room_id>/drive/save')
    def save_drive(room_id):
        d = data()
        with store.connect() as db:
            current = document(db, room_id, field(d, 'document_id', 100))
        try:
            value = drive.save(room_id, field(d, 'mount_id', 100), d.get('folder_id'), current['title'], current['body'])
        except (ValueError, RuntimeError) as exc:
            abort(400, str(exc))
        with store.connect() as db:
            store.audit(db, room_id, g.user['name'], 'drive_saved', current['title'])
        return jsonify(value), 201

    @app.post('/api/rooms/<room_id>/drive/save-file')
    def save_file_drive(room_id):
        d=data()
        with store.connect() as db:
            accessible(db,room_id)
            file=db.execute('SELECT * FROM artifacts WHERE id=? AND room_id=?',(field(d,'file_id',100),room_id)).fetchone()
            if not file:abort(404,'File not found in this chat.')
        try:value=drive.copy_asset(room_id,field(d,'mount_id',100),d.get('folder_id'),file)
        except (ValueError,RuntimeError) as exc:abort(400,str(exc))
        with store.connect() as db:
            accessible(db,room_id)
            store.audit(db,room_id,g.user['name'],'file_copied_to_drive',file['filename'])
        return jsonify(value),201

    @app.post('/api/rooms/<room_id>/drive/branch')
    def branch_drive(room_id):
        d = data()
        with store.connect() as db:
            accessible(db, room_id)
        try:
            value = drive.branch(room_id, field(d, 'mount_id', 100), d.get('parent_id'), field(d, 'name', 200))
        except (ValueError, RuntimeError) as exc:
            abort(400, str(exc))
        with store.connect() as db:
            store.audit(db, room_id, g.user['name'], 'drive_branched', value['name'])
        return jsonify(value), 201
