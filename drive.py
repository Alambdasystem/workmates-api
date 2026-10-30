"""Google OAuth and group-scoped Drive mounts. Tokens never leave the server."""
import base64
import hashlib
import io
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.fernet import Fernet
from documents import export_document, import_document

SCHEMA = '''
CREATE TABLE IF NOT EXISTS integration_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drive_connections(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),label TEXT NOT NULL,token TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS drive_states(state TEXT PRIMARY KEY,user_id TEXT NOT NULL,session TEXT NOT NULL,verifier TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS drive_mounts(id TEXT PRIMARY KEY,room_id TEXT NOT NULL REFERENCES rooms(id),connection_id TEXT NOT NULL REFERENCES drive_connections(id),folder_id TEXT NOT NULL,name TEXT NOT NULL,created REAL NOT NULL);
'''
FOLDER = 'application/vnd.google-apps.folder'


class Drive:
    def __init__(self, store, config):
        self.store, self.config = store, config
        keyfile = Path(store.path).parent / '.integration-key'
        try:
            with keyfile.open('xb') as out:
                os.chmod(keyfile, 0o600); out.write(Fernet.generate_key())
        except FileExistsError:
            pass
        self.cipher = Fernet(keyfile.read_bytes())
        with store.connect() as db:
            db.executescript(SCHEMA)

    def seal(self, value):
        return self.cipher.encrypt(json.dumps(value).encode()).decode()

    def unseal(self, value):
        return json.loads(self.cipher.decrypt(value.encode()))

    def credentials(self):
        with self.store.connect() as db:
            row = db.execute("SELECT value FROM integration_settings WHERE key='google_oauth'").fetchone()
        if row:
            return self.unseal(row['value'])
        return {'client_id': self.config.get('GOOGLE_CLIENT_ID', ''), 'client_secret': self.config.get('GOOGLE_CLIENT_SECRET', ''),
                'origin': self.config.get('PUBLIC_APP_URL', 'https://workmates-core.onrender.com')}

    def configure(self, client_id, client_secret, origin):
        parsed = urllib.parse.urlparse(origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('Use the HTTPS Workmates frontend origin, without a path.')
        if not client_id.endswith('.apps.googleusercontent.com') or not 10 <= len(client_secret) <= 500:
            raise ValueError('Use a Google Web application OAuth client ID and secret.')
        with self.store.connect() as db:
            if db.execute('SELECT 1 FROM drive_connections LIMIT 1').fetchone():
                raise ValueError('Disconnect Google accounts before replacing the OAuth application.')
            db.execute("INSERT OR REPLACE INTO integration_settings VALUES('google_oauth',?)", (self.seal(dict(client_id=client_id, client_secret=client_secret, origin=origin.rstrip('/'))),))

    def status(self, user_id):
        creds = self.credentials()
        with self.store.connect() as db:
            connections = [dict(r) for r in db.execute('SELECT id,label,created FROM drive_connections WHERE user_id=?', (user_id,))]
        return dict(configured=bool(creds['client_id'] and creds['client_secret']), connections=connections,
                    callback=creds['origin'].rstrip('/') + '/api/integrations/google/callback')

    def start(self, user_id, session):
        creds = self.credentials()
        if not creds['client_id'] or not creds['client_secret']:
            raise ValueError('Set up a Google OAuth application before connecting an account.')
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        with self.store.connect() as db:
            db.execute('DELETE FROM drive_states WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO drive_states VALUES(?,?,?,?,?)', (hashlib.sha256(state.encode()).hexdigest(), user_id, session, verifier, time.time() + 600))
        query = dict(client_id=creds['client_id'], redirect_uri=creds['origin'] + '/api/integrations/google/callback', response_type='code',
                     scope='https://www.googleapis.com/auth/drive', access_type='offline', prompt='consent select_account', state=state,
                     code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(), code_challenge_method='S256')
        return 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(query)

    def http(self, url, method='GET', body=None, headers=None, raw=False):
        req = urllib.request.Request(url, method=method, data=body, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                value = response.read(8 * 1024 * 1024 + 1)
                if len(value) > 8 * 1024 * 1024:
                    raise ValueError('The Drive file is larger than 8 MB.')
                return value if raw else json.loads(value)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'Google Drive returned HTTP {exc.code}. Check account permissions or reconnect the account.') from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError('Google Drive could not be reached.') from None

    def token_request(self, payload):
        creds = self.credentials()
        return self.http('https://oauth2.googleapis.com/token', 'POST', urllib.parse.urlencode({**payload, 'client_id': creds['client_id'], 'client_secret': creds['client_secret']}).encode(), {'Content-Type': 'application/x-www-form-urlencoded'})

    def complete(self, state, code):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT d.* FROM drive_states d JOIN sessions s ON s.token=d.session JOIN users u ON u.id=d.user_id WHERE d.state=? AND d.expires>? AND s.expires>? AND u.role=\'admin\'', (hashlib.sha256(state.encode()).hexdigest(), time.time(), time.time())).fetchone()
            if not row:
                raise ValueError('Google connection expired or was already used. Start again in Workmates.')
            db.execute('DELETE FROM drive_states WHERE state=?', (row['state'],))
        token = self.token_request(dict(code=code, code_verifier=row['verifier'], grant_type='authorization_code', redirect_uri=self.credentials()['origin'] + '/api/integrations/google/callback'))
        if not token.get('refresh_token') or 'https://www.googleapis.com/auth/drive' not in token.get('scope', '').split():
            raise ValueError('Google did not grant persistent Drive access. Reconnect and allow Drive access.')
        about = self.http('https://www.googleapis.com/drive/v3/about?fields=user(emailAddress,displayName)', headers={'Authorization': 'Bearer ' + token['access_token']})
        connection_id = secrets.token_hex(12)
        with self.store.connect() as db:
            db.execute('INSERT INTO drive_connections VALUES(?,?,?,?,?)', (connection_id, row['user_id'], about['user'].get('emailAddress', 'Google account'), self.seal({'refresh_token': token['refresh_token']}), time.time()))
        return connection_id

    def connection(self, connection_id):
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM drive_connections WHERE id=?', (connection_id,)).fetchone()
        if not row:
            raise ValueError('Google account not connected.')
        return dict(row)

    def api(self, connection_id, path, method='GET', payload=None, params=None, raw=False, media=None, media_mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'):
        connection = self.connection(connection_id)
        token = self.token_request(dict(grant_type='refresh_token', refresh_token=self.unseal(connection['token'])['refresh_token']))
        headers = {'Authorization': 'Bearer ' + token['access_token']}
        body = None
        base = 'https://www.googleapis.com/drive/v3/'
        if media is not None:
            base = 'https://www.googleapis.com/upload/drive/v3/'
            boundary = 'wm-' + secrets.token_hex(12)
            headers['Content-Type'] = 'multipart/related; boundary=' + boundary
            body = ('--' + boundary + '\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n' + json.dumps(payload) + '\r\n--' + boundary + '\r\nContent-Type: ' + media_mime + '\r\n\r\n').encode() + media + ('\r\n--' + boundary + '--\r\n').encode()
        elif payload is not None:
            headers['Content-Type'] = 'application/json'; body = json.dumps(payload).encode()
        return self.http(base + path + '?' + urllib.parse.urlencode(params or {}), method, body, headers, raw)

    @staticmethod
    def valid_id(value):
        if not isinstance(value, str) or not re_id(value):
            raise ValueError('Use a Google Drive file or folder ID.')
        return value

    def metadata(self, cid, file_id):
        return self.api(cid, 'files/' + self.valid_id(file_id), params={'supportsAllDrives': 'true', 'fields': 'id,name,mimeType,parents,trashed,webViewLink'})

    def mount(self, room_id, connection_id, folder_id, name):
        meta = self.metadata(connection_id, folder_id)
        if meta['mimeType'] != FOLDER or meta.get('trashed'):
            raise ValueError('Choose an accessible Drive folder.')
        mount_id = secrets.token_hex(12)
        with self.store.connect() as db:
            db.execute('INSERT INTO drive_mounts VALUES(?,?,?,?,?,?)', (mount_id, room_id, connection_id, meta['id'], name or meta['name'], time.time()))
        return mount_id

    def mounts(self, room_id):
        with self.store.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,name,folder_id,created FROM drive_mounts WHERE room_id=? ORDER BY created', (room_id,))]

    def mounted(self, room_id, mount_id):
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM drive_mounts WHERE id=? AND room_id=?', (mount_id, room_id)).fetchone()
        if not row:
            raise ValueError('This Drive folder is not connected to this group.')
        return dict(row)

    def within(self, mount, file_id):
        # Validate the remote ancestry on every request; cached IDs never bypass scope.
        meta = self.metadata(mount['connection_id'], file_id)
        current = meta
        seen = set()
        for _ in range(50):
            if current.get('trashed'):
                break
            if current['id'] == mount['folder_id']:
                return meta
            if current['id'] in seen or not current.get('parents'):
                break
            seen.add(current['id'])
            current = self.metadata(mount['connection_id'], current['parents'][0])
        raise ValueError('That file is outside the folder connected to this group.')

    def list_files(self, room_id, mount_id, folder_id=None, page_token=''):
        mount = self.mounted(room_id, mount_id)
        folder = folder_id or mount['folder_id']
        if self.within(mount, folder)['mimeType'] != FOLDER:
            raise ValueError('Choose a folder.')
        return self.api(mount['connection_id'], 'files', params=dict(q="'" + self.valid_id(folder) + "' in parents and trashed=false", supportsAllDrives='true', includeItemsFromAllDrives='true', pageSize=50, pageToken=page_token, fields='nextPageToken,files(id,name,mimeType,webViewLink)', orderBy='folder,name'))

    def read_file(self, room_id, mount_id, file_id):
        mount = self.mounted(room_id, mount_id); meta = self.within(mount, file_id)
        if meta['mimeType'] == 'application/vnd.google-apps.document':
            content = self.api(mount['connection_id'], 'files/' + file_id + '/export', params={'mimeType': 'text/plain'}, raw=True)
            text = import_document('document.txt', content)
        else:
            content = self.api(mount['connection_id'], 'files/' + file_id, params={'alt': 'media', 'supportsAllDrives': 'true'}, raw=True)
            text = import_document(meta['name'], content)
        return dict(title=meta['name'], body=text)

    def save(self, room_id, mount_id, folder_id, title, body):
        mount = self.mounted(room_id, mount_id)
        folder = folder_id or mount['folder_id']
        if self.within(mount, folder)['mimeType'] != FOLDER:
            raise ValueError('Choose a folder.')
        return self.api(mount['connection_id'], 'files', 'POST', {'name': title, 'mimeType': 'application/vnd.google-apps.document', 'parents': [folder]},
                        {'uploadType': 'multipart', 'supportsAllDrives': 'true', 'fields': 'id,name,webViewLink'}, media=export_document(title, body, 'docx'))

    def branch(self, room_id, mount_id, parent_id, name):
        mount = self.mounted(room_id, mount_id); parent = parent_id or mount['folder_id']
        if self.within(mount, parent)['mimeType'] != FOLDER:
            raise ValueError('Choose a folder.')
        return self.api(mount['connection_id'], 'files', 'POST', {'name': name, 'mimeType': FOLDER, 'parents': [parent]}, {'supportsAllDrives': 'true', 'fields': 'id,name,webViewLink'})

    def save_binary(self, room_id, mount_id, folder_id, filename, mime, content):
        mount=self.mounted(room_id,mount_id);folder=folder_id or mount['folder_id']
        if self.within(mount,folder)['mimeType']!=FOLDER:raise ValueError('Choose a folder.')
        return self.api(mount['connection_id'],'files','POST',{'name':filename,'mimeType':mime,'parents':[folder]},
                        {'uploadType':'multipart','supportsAllDrives':'true','fields':'id,name,webViewLink'},media=content,media_mime=mime)

    def copy_asset(self,room_id,mount_id,folder_id,asset):
        result=self.save_binary(room_id,mount_id,folder_id,asset['filename'],asset['mime'],asset['content'])
        url=result.get('webViewLink','');parsed=urllib.parse.urlparse(url)
        if parsed.scheme!='https' or parsed.hostname not in ('drive.google.com','docs.google.com'):url=''
        with self.store.connect() as db:
            db.execute('INSERT INTO file_drive_copies VALUES(?,?,?,?,?,?)',(secrets.token_hex(12),asset['id'],mount_id,result['id'],url,time.time()))
        return {'saved':True,'id':result['id'],'url':url}


def re_id(value):
    import re
    return re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value)
