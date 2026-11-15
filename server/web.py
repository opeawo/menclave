"""HTTP interface shared by local development, tests and Gunicorn."""
import hmac
import os
import secrets
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, request, jsonify, send_file
from werkzeug.exceptions import HTTPException
from server.app import Store, ROOT

CSP = "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' https://images.unsplash.com; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"

def create_app(store=None, admin_key=None):
    production = os.environ.get('ENCLAVE_ENV') == 'production' and store is None
    origin = os.environ.get('ENCLAVE_ORIGIN','').rstrip('/')
    key = os.environ.get('ENCLAVE_ADMIN_KEY','') if admin_key is None else admin_key
    secure = production or os.environ.get('ENCLAVE_SECURE_COOKIE') == '1'
    db_path = Path(os.environ.get('ENCLAVE_DB',str(ROOT / '.local' / 'enclave.sqlite3')))
    if production:
        parsed = urlsplit(origin)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('Production requires ENCLAVE_ORIGIN as an exact HTTPS origin.')
        if len(key) < 32: raise ValueError('Production requires a strong ENCLAVE_ADMIN_KEY of at least 32 characters.')
        if 'ENCLAVE_DB' not in os.environ or not db_path.is_absolute(): raise ValueError('Set ENCLAVE_DB to an absolute persistent-volume path.')
    if key and len(key) < 32: raise ValueError('Use a moderator key of at least 32 characters.')
    if store is None:
        db_path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        store = Store(db_path)
        os.chmod(db_path,0o600)
    app = Flask(__name__,static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=20000,PROPAGATE_EXCEPTIONS=False)
    app.extensions['enclave_store'] = store

    def token():
        value = request.cookies.get('enclave_session','')
        if len(value) != 64 or any(c not in '0123456789abcdef' for c in value): return ''
        return value
    def authorized():
        return bool(key) and hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+key)
    def error(message,code): return jsonify(error=message),code
    @app.after_request
    def protect(response):
        response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Content-Security-Policy':CSP,'Cache-Control':'no-store' if request.path.startswith('/api/') else 'no-cache'})
        if production: response.headers['Strict-Transport-Security']='max-age=31536000'
        return response
    @app.before_request
    def validate_write():
        if request.method != 'POST': return None
        if request.headers.get('Origin') != (origin or request.host_url.rstrip('/')): return error('Request origin rejected.',403)
        value = token()
        if not value or not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),store.digest('csrf:'+value)): return error('Refresh this page before submitting.',403)
        if not request.is_json: return error('JSON required.',415)
    @app.errorhandler(HTTPException)
    def http_error(exception): return error(exception.description,exception.code)
    @app.errorhandler(sqlite3.Error)
    def database_error(exception): return error('Unable to save right now. Please try again.',503)
    @app.get('/api/health')
    def health():
        with store.connect() as db: db.execute('SELECT 1').fetchone()
        return jsonify(status='ok')
    @app.get('/api/session')
    def session():
        value = token() or secrets.token_hex(32)
        response = jsonify(csrf=store.digest('csrf:'+value))
        response.set_cookie('enclave_session',value,max_age=2592000,httponly=True,samesite='Strict',secure=secure,path='/')
        return response
    @app.get('/api/threads')
    def threads(): return jsonify(threads=store.listing(request.args.get('q','')[:200],request.args.get('topic','')))
    @app.get('/api/threads/<post_id>')
    def thread(post_id):
        post = store.thread(post_id)
        return jsonify(post) if post else error('Conversation unavailable.',404)
    @app.route('/api/moderation',methods=['GET','POST'])
    def moderation():
        if store.limited(request.remote_addr or 'unknown','admin',60,600): return error('Too many requests. Try again later.',429)
        if not authorized(): return error('Moderator key required.',401)
        if request.method == 'GET': return jsonify(store.queue())
        data=request.get_json()
        if not isinstance(data,dict): return error('Invalid request.',400)
        try: store.moderate(data,store.digest('moderator:'+key))
        except (ValueError,TypeError): return error('Invalid moderation action or unavailable post.',400)
        return jsonify(ok=True)
    @app.post('/api/<action>')
    def submit(action):
        if action not in ['threads','replies','reports']: return error('Not found.',404)
        if store.limited(request.remote_addr or 'unknown','write',30,3600) or store.limited(token(),'write',10,600): return error('Please pause before posting again.',429)
        data=request.get_json()
        if not isinstance(data,dict): return error('Invalid request.',400)
        owner=store.digest('owner:'+token())
        try:
            if action == 'reports':
                store.report(data,owner)
                return jsonify(message='Report received for moderator review.'),201
            if action == 'replies' and not data.get('parent'): return error('Choose a conversation.',400)
            if action == 'threads': data.pop('parent',None)
            post_id=store.submit(data,owner)
            return jsonify(id=post_id,message='Received. Your post is awaiting moderator approval.'),201
        except (ValueError,TypeError): return error('Check the topic, title and message lengths, then try again.',400)
    @app.get('/')
    @app.get('/<path:name>')
    def asset(name='index.html'):
        if '/' in name or name.startswith('.') or not name.endswith(('.html','.css','.js')): return error('Not found.',404)
        path=ROOT / name
        if not path.is_file(): return error('Not found.',404)
        return send_file(path,conditional=True)
    return app
