"""HTTP interface shared by local development, tests and Gunicorn."""
import hmac
import os
import secrets
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, request, jsonify, send_file, redirect
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
    from server.services import Platform
    from server.identity import install_identity
    from server.admin_editorial import install_editorial
    from server.publishing import bootstrap
    platform = Platform(store)
    bootstrap(platform)
    app.extensions['platform'] = platform
    owner_session, owner_trusted, owner_page = install_identity(app,platform,key,origin,secure)
    install_editorial(app,platform,owner_session,owner_trusted,owner_page)

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
        if request.path.startswith(('/admin','/oauth/','.well-known')):response.headers['Cache-Control']='no-store'
        if request.method=='GET' and response.status_code==200 and (request.path in {'/','/index.html','/magazine','/magazine.html','/enclave.html'} or request.path.startswith('/magazine/')):
            from datetime import date
            ref=urlsplit(request.headers.get('Referer','')).hostname or 'direct'
            if ref==request.host.split(':')[0]:ref='internal'
            with store.connect() as db:db.execute('INSERT INTO analytics_daily VALUES(?,?,?,1) ON CONFLICT(day,path,source) DO UPDATE SET count=count+1',(date.today().isoformat(),request.path[:200],ref[:200]))
        if production: response.headers['Strict-Transport-Security']='max-age=31536000'
        return response
    @app.before_request
    def validate_write():
        if request.path.startswith('/admin/editorial/'):request.max_content_length=120000
        if request.method=='GET' and not request.path.startswith(('/admin','/api/','/oauth/','.well-known')):
            import json
            with store.connect() as db:row=db.execute("SELECT data FROM entities WHERE kind='redirect' AND json_extract(data,'$.source')=? AND status!='archived' LIMIT 1",(request.path,)).fetchone()
            if row:return redirect(json.loads(row[0])['destination'],308)
        if request.path.startswith(('/admin','/oauth/','/unsubscribe/','/newsletter/confirm/')): return None
        if request.path.startswith('/api/media-upload/'):
            return None
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
    @app.get('/api/community-config')
    def community_config():
        from server.tools import dispatch
        return jsonify(dispatch(platform,'community_get_guidelines',{}, {'id':'public','scopes':['read']}))
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
        limits=store.abuse_limits()
        if store.limited(request.remote_addr or 'unknown','write',limits['network_limit'],3600) or store.limited(token(),'write',limits['session_limit'],600): return error('Please pause before posting again.',429)
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
    @app.post('/api/newsletter/subscribe')
    def subscribe():
        import re
        from server.services import now,ident
        if not os.environ.get('MENCLAVE_SMTP_HOST') or not os.environ.get('MENCLAVE_SMTP_FROM') or not origin.startswith('https://'):
            return error('Newsletter subscriptions are not active. No email has been stored.',503)
        if store.limited(request.remote_addr or 'unknown','subscribe',5,3600):return error('Please try again later.',429)
        data=request.get_json(silent=True) or {};email=data.get('email','')
        if not isinstance(email,str) or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):return error('Enter a valid email address.',400)
        email=email.strip().lower()
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM config WHERE key=?',('suppression:'+store.digest(email),)).fetchone():
                row=db.execute('SELECT * FROM audience WHERE email=?',(email,)).fetchone()
                if not row:
                    id=ident();db.execute('INSERT INTO audience VALUES(?,?,0,0,?)',(id,email,now()))
                else:id=row['id']
                if not row or not row['consent'] and not row['suppressed']:
                    pending=db.execute('SELECT 1 FROM pending_subscriptions WHERE audience=? AND expires>?',(id,now())).fetchone()
                    if not pending:
                        token=secrets.token_urlsafe(32);db.execute('INSERT INTO pending_subscriptions VALUES(?,?,?)',(store.digest(token),id,now()+86400))
                        platform.enqueue(db,'optin',{'audience':id,'token':token})
        return jsonify(message='If eligible, you will receive a confirmation email. Please confirm before expecting newsletters.')
    @app.route('/newsletter/confirm/<confirmation>',methods=['GET','POST'])
    def confirm_subscription(confirmation):
        from server.services import now
        with store.connect() as db:
            row=db.execute('SELECT * FROM pending_subscriptions WHERE digest=? AND expires>?',(store.digest(confirmation),now())).fetchone()
            if not row:return error('Confirmation is unavailable or expired.',404)
            if request.method=='GET':return owner_page('Confirm your subscription','<form method="post"><button class="button">Confirm subscription</button></form>')
            db.execute('UPDATE audience SET consent=1 WHERE id=? AND suppressed=0',(row['audience'],));db.execute('DELETE FROM pending_subscriptions WHERE audience=?',(row['audience'],))
        return owner_page('Subscription confirmed','<p>Your Menclave letter subscription is confirmed.</p>')
    @app.route('/unsubscribe/<subscriber_id>/<signature>',methods=['GET','POST'])
    def unsubscribe(subscriber_id,signature):
        if not hmac.compare_digest(signature,store.digest('unsubscribe:'+subscriber_id)):return error('Invalid unsubscribe link.',403)
        if request.method=='GET':return owner_page('Unsubscribe','<p>Stop receiving the Menclave letter?</p><form method="post"><button class="button">Unsubscribe</button></form>')
        with store.connect() as db:db.execute('UPDATE audience SET suppressed=1 WHERE id=?',(subscriber_id,))
        return owner_page('You are unsubscribed','<p>No further newsletters will be sent to this subscription.</p>')
    @app.get('/theme.css')
    def theme():
        import json,re
        with store.connect() as db:row=db.execute("SELECT data FROM entities WHERE id='site'").fetchone()
        data=json.loads(row[0]) if row else {}
        colors={k:v for k,v in data.items() if k in {'accent','paper','ink'} and isinstance(v,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',v)}
        return app.response_class(':root{'+''.join('--'+k+':'+v+';' for k,v in colors.items())+'}',mimetype='text/css')
    @app.get('/magazine')
    def magazine_archive():
        from server.publishing import archive
        return archive(platform)
    @app.get('/magazine/<slug>')
    def magazine_story(slug):
        from server.publishing import article
        result,status=article(platform,slug)
        return (result,status) if status else error('Story unavailable.',404)
    @app.get('/sitemap.xml')
    @app.get('/feed.xml')
    def publication_feed():
        from server.publishing import feed
        return app.response_class(feed(platform,request.path=='/feed.xml'),mimetype='application/xml')
    @app.get('/media/<name>')
    def image_asset(name):
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,60}\.webp',name):return error('Not found.',404)
        path=platform.media_dir/name
        if not path.is_file():return error('Not found.',404)
        return send_file(path,mimetype='image/webp')
    @app.put('/api/media-upload/<upload_id>')
    def upload_image(upload_id):
        import io
        from PIL import Image,ImageOps,UnidentifiedImageError
        from server.services import now
        value=request.headers.get('Authorization','')
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM media_uploads WHERE id=?',(upload_id,)).fetchone()
            if not row or row['expires']<=now() or row['uploaded'] or not value.startswith('Bearer ') or not hmac.compare_digest(store.digest(value[7:]),row['token_hash']):return error('Upload unavailable.',403)
            if request.mimetype!=row['mime']:return error('Image type mismatch.',415)
            request.max_content_length=10000000
            raw=request.get_data()
            if len(raw)>10000000:return error('Image too large.',413)
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    if image.width*image.height>20000000:return error('Image dimensions too large.',400)
                    image=ImageOps.exif_transpose(image).convert('RGB')
                    image.thumbnail((4000,4000))
                    image.save(platform.media_dir/(upload_id+'.webp'),'WEBP',quality=85)
            except (UnidentifiedImageError,OSError,Image.DecompressionBombError):return error('Invalid image.',400)
            db.execute('UPDATE media_uploads SET uploaded=1 WHERE id=?',(upload_id,))
        return jsonify(uploaded=True)
    @app.get('/')
    @app.get('/<path:name>')
    def asset(name='index.html'):
        if '/' in name or name.startswith('.') or not (name.endswith(('.html','.css','.js')) or name=='select-chevron.svg'): return error('Not found.',404)
        from server.publishing import home, archive, article
        if name=='index.html':return home(platform)
        if name=='magazine.html':return archive(platform)
        if name.endswith('.html'):
            rendered,status=article(platform,name[:-5])
            if status:return rendered,status
        path=ROOT / name
        if not path.is_file(): return error('Not found.',404)
        return send_file(path,conditional=True)
    return app
