"""Owner-controlled sessions, client grants and OAuth authorization-code PKCE."""
import base64
import hashlib
import hmac
import json
import re
import secrets
from urllib.parse import urlsplit, urlencode
from flask import request, jsonify, make_response, redirect, render_template_string
from server.services import SCOPES, canonical, now, ident

PAGE='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Menclave administration</title><link rel="stylesheet" href="/styles.css"></head><body><main id="main" class="moderator-page"><a href="/">MENCLAVE /</a><h1>{{title}}</h1>{{body|safe}}</main></body></html>'''

def install_identity(app,platform,key,origin,secure):
    store=platform.store
    with store.connect() as db:
        digest=store.digest(key) if key else ''
        previous=db.execute("SELECT value FROM config WHERE key='owner_key_digest'").fetchone()
        if not previous or previous[0]!=digest:
            db.execute('DELETE FROM admin_sessions')
            db.execute("INSERT OR REPLACE INTO config VALUES('owner_key_digest',?)",(digest,))
    def csrf_session():
        token=request.cookies.get('menclave_owner','')
        with store.connect() as db:
            row=db.execute('SELECT * FROM admin_sessions WHERE digest=? AND expires>?',(store.digest(token),now())).fetchone()
            return dict(row) if row else None
    def page(title,body,**values):return render_template_string(PAGE,title=title,body=render_template_string(body,**values))
    def trusted():
        session=csrf_session()
        return bool(session) and hmac.compare_digest(request.form.get('csrf',''),session['csrf']) and request.headers.get('Origin')==(origin or request.host_url.rstrip('/'))
    def form_csrf(session):return session['csrf']
    @app.get('/admin')
    def admin():
        session=csrf_session()
        if not session:
            # Login CSRF token is signed and short-lived; no key is put in a URL.
            value=secrets.token_urlsafe(24);response=make_response(page('Owner access','''<form method="post" action="/admin/login"><input type="hidden" name="csrf" value="{{csrf}}"><label>Owner key<input name="key" type="password" autocomplete="off" required></label><button class="button">Sign in</button></form>''',csrf=store.digest('login:'+value)))
            response.set_cookie('menclave_login',value,max_age=600,httponly=True,secure=secure,samesite='Strict');return response
        with store.connect() as db:
            plans=[dict(r) for r in db.execute("SELECT id,actor,tool,args,summary,expires,state FROM change_plans WHERE state IN ('pending','approved') AND expires>? ORDER BY expires LIMIT 50",(now(),)).fetchall()]
            requests=[{'id':r['id'],**json.loads(r['data'])} for r in db.execute("SELECT * FROM entities WHERE kind='access_request' AND status='draft' ORDER BY created LIMIT 50").fetchall()]
            clients=[dict(r) for r in db.execute('SELECT id,name,scopes,expires,revoked FROM assistant_clients ORDER BY expires DESC LIMIT 100').fetchall()]
        return page('Menclave control room','''<p><a href="/admin/editorial">Editorial studio</a> · <a href="/moderation.html">Community moderation</a></p><h2>Connect an assistant</h2><form method="post" action="/admin/clients"><input type="hidden" name="csrf" value="{{csrf}}"><label>Name<input name="name" maxlength="100" required></label><fieldset><legend>Permissions</legend>{% for scope in scopes %}<label><input type="checkbox" name="scopes" value="{{scope}}">{{scope}}</label><br>{% endfor %}</fieldset><label>Expires in days<input type="number" name="days" min="1" max="365" value="30"></label><button class="button">Issue token</button></form><h2 id="approvals">Pending approvals</h2>{% for plan in plans %}<article class="moderation-item"><h3>{{plan.tool}}</h3><p>Client: {{plan.actor}}</p><pre>{{plan.summary}}</pre><pre>{{plan.args}}</pre><p>Expires: {{plan.expires}}</p><form method="post" action="/admin/approve"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="plan_id" value="{{plan.id}}"><button name="decision" value="approve">Approve exact change</button><button name="decision" value="reject">Reject</button></form>{% if plan.state=='approved' and plan.actor=='owner-ui' %}<form method="post" action="/admin/commit"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="plan_id" value="{{plan.id}}"><button>Apply approved change</button></form>{% endif %}</article>{% else %}<p>No pending approvals.</p>{% endfor %}<h2>Access requests</h2>{% for grant in requests %}<article class="moderation-item"><p>Client: {{grant.client_id}}</p><p>Requested scopes: {{grant.requested_scopes}}</p><form method="post" action="/admin/grant"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="request_id" value="{{grant.id}}"><button>Grant exact scopes and revoke old tokens</button></form></article>{% endfor %}<h2>Assistant clients</h2>{% for client in clients %}<p>{{client.name}} · {{client.scopes}} · revoked={{client.revoked}}</p><form method="post" action="/admin/revoke"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="id" value="{{client.id}}"><button>Revoke access</button></form>{% endfor %}<form method="post" action="/admin/logout"><input type="hidden" name="csrf" value="{{csrf}}"><button>Sign out</button></form>''',csrf=session['csrf'],scopes=sorted(SCOPES),plans=plans,clients=clients,requests=requests)
    @app.post('/admin/login')
    def login():
        if store.limited(request.remote_addr or 'unknown','owner-login',10,600):return jsonify(error='Try again later.'),429
        if request.headers.get('Origin')!=(origin or request.host_url.rstrip('/')):return jsonify(error='Invalid origin.'),403
        expected=store.digest('login:'+request.cookies.get('menclave_login',''))
        if not request.cookies.get('menclave_login') or not hmac.compare_digest(expected,request.form.get('csrf','')):return jsonify(error='Refresh the login page.'),403
        supplied=request.form.get('key','')
        if not key or not hmac.compare_digest(supplied.encode(),key.encode()):return jsonify(error='Owner key required.'),401
        token=secrets.token_urlsafe(40);csrf=secrets.token_urlsafe(32)
        with store.connect() as db:
            db.execute('DELETE FROM admin_sessions WHERE expires<?',(now(),))
            db.execute('INSERT INTO admin_sessions VALUES(?,?,?)',(store.digest(token),csrf,now()+3600))
        response=redirect('/admin');response.set_cookie('menclave_owner',token,max_age=3600,secure=secure,httponly=True,samesite='Strict');response.delete_cookie('menclave_login');return response
    @app.post('/admin/logout')
    def logout():
        if not trusted():return jsonify(error='Owner session required.'),403
        with store.connect() as db:db.execute('DELETE FROM admin_sessions WHERE digest=?',(store.digest(request.cookies.get('menclave_owner','')),))
        response=redirect('/admin');response.delete_cookie('menclave_owner');return response
    @app.post('/admin/clients')
    def issue():
        if not trusted():return jsonify(error='Owner session required.'),403
        from server.services import DomainError
        try:result=platform.issue_client(request.form.get('name',''),request.form.getlist('scopes'),int(request.form.get('days','30')))
        except (DomainError,ValueError):return jsonify(error='Check client name, expiry and permissions.'),400
        response=make_response(page('Save your assistant token','''<p>Copy this token into your assistant’s secure MCP configuration. It is shown only here; it cannot be retrieved later.</p><pre>{{token}}</pre><p>Endpoint: {{endpoint}}</p><a href="/admin">Return to administration</a>''',token=result['token'],endpoint=(origin or request.host_url.rstrip('/'))+'/mcp'))
        response.headers['Cache-Control']='no-store';return response
    @app.post('/admin/grant')
    def grant_scopes():
        if not trusted():return jsonify(error='Owner session required.'),403
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM entities WHERE id=? AND kind='access_request' AND status='draft'",(request.form.get('request_id'),)).fetchone()
            if not row:return jsonify(error='Request unavailable.'),404
            data=json.loads(row['data']);scopes=data['requested_scopes']
            if not set(scopes)<=SCOPES:return jsonify(error='Unknown permissions.'),400
            client=db.execute('SELECT * FROM assistant_clients WHERE id=? AND revoked=0 AND expires>?',(data['client_id'],now())).fetchone()
            if not client:return jsonify(error='Client unavailable.'),404
            token='mcv_'+secrets.token_urlsafe(40)
            db.execute('UPDATE assistant_clients SET scopes=? WHERE id=?',(canonical(scopes),client['id']))
            db.execute('UPDATE assistant_tokens SET revoked=1 WHERE client=?',(client['id'],))
            db.execute('INSERT INTO assistant_tokens VALUES(?,?,?,?,0)',(store.digest(token),client['id'],canonical(scopes),client['expires']))
            db.execute("UPDATE entities SET status='archived' WHERE id=?",(row['id'],));platform.audit(db,'owner','access_grant_request',client['id'])
        return page('Save the replacement token','<p>Old tokens are revoked. Install this replacement in the approved assistant.</p><pre>{{token}}</pre><a href="/admin">Return</a>',token=token)
    @app.post('/admin/revoke')
    def revoke():
        if not trusted():return jsonify(error='Owner session required.'),403
        with store.connect() as db:
            db.execute('UPDATE assistant_clients SET revoked=1 WHERE id=?',(request.form.get('id'),));platform.audit(db,'owner','access_revoke_client',request.form.get('id'))
        return redirect('/admin')
    @app.post('/admin/approve')
    def approve():
        if not trusted():return jsonify(error='Owner session required.'),403
        decision=request.form.get('decision');id=request.form.get('plan_id')
        if decision not in {'approve','reject'}:return jsonify(error='Invalid decision.'),400
        with store.connect() as db:
            count=db.execute("UPDATE change_plans SET state=? WHERE id=? AND state='pending' AND expires>?",('approved' if decision=='approve' else 'rejected',id,now())).rowcount
            if not count:return jsonify(error='Plan expired or unavailable.'),409
            platform.audit(db,'owner','approve_plan' if decision=='approve' else 'reject_plan',id)
        return redirect('/admin#approvals')
    @app.get('/.well-known/oauth-protected-resource')
    @app.get('/.well-known/oauth-protected-resource/mcp')
    def resource_metadata():
        base=origin or request.host_url.rstrip('/')
        return jsonify(resource=base+'/mcp',authorization_servers=[base],scopes_supported=sorted(SCOPES),bearer_methods_supported=['header'])
    @app.get('/.well-known/oauth-authorization-server')
    def oauth_metadata():
        base=origin or request.host_url.rstrip('/')
        return jsonify(issuer=base,authorization_endpoint=base+'/oauth/authorize',token_endpoint=base+'/oauth/token',registration_endpoint=base+'/oauth/register',revocation_endpoint=base+'/oauth/revoke',response_types_supported=['code'],grant_types_supported=['authorization_code'],code_challenge_methods_supported=['S256'],token_endpoint_auth_methods_supported=['none'],scopes_supported=sorted(SCOPES))
    @app.post('/oauth/register')
    def register():
        if store.limited(request.remote_addr or 'unknown','oauth-register',10,3600):return jsonify(error='rate_limited'),429
        data=request.get_json(silent=True) or {};redirects=data.get('redirect_uris',[])
        if not isinstance(redirects,list) or not 1<=len(redirects)<=5:return jsonify(error='invalid_redirect_uri'),400
        for uri in redirects:
            if not isinstance(uri,str):return jsonify(error='invalid_redirect_uri'),400
            parsed=urlsplit(uri)
            if parsed.fragment or parsed.username or not parsed.netloc or not (parsed.scheme=='https' or parsed.scheme=='http' and parsed.hostname in {'127.0.0.1','localhost','::1'}):return jsonify(error='invalid_redirect_uri'),400
        id=ident();name=str(data.get('client_name','MCP assistant'))[:100]
        with store.connect() as db:db.execute('INSERT INTO assistant_clients(id,name,scopes,redirects,expires) VALUES(?,?,?,?,?)',(id,name,canonical(sorted(SCOPES)),canonical(redirects),now()+365*86400))
        return jsonify(client_id=id,client_name=name,redirect_uris=redirects,token_endpoint_auth_method='none',grant_types=['authorization_code'],response_types=['code']),201
    def authorization_parameters(values):
        with store.connect() as db:client=db.execute('SELECT * FROM assistant_clients WHERE id=? AND revoked=0 AND expires>?',(values.get('client_id'),now())).fetchone()
        if not client:return None
        scopes=values.get('scope','read').split();redirect_uri=values.get('redirect_uri','');resource=values.get('resource','')
        if redirect_uri not in json.loads(client['redirects']) or not set(scopes)<=set(json.loads(client['scopes'])) or not scopes:return None
        base=origin or request.host_url.rstrip('/')
        if resource!=base+'/mcp' or values.get('response_type')!='code' or values.get('code_challenge_method')!='S256' or not re.fullmatch('[A-Za-z0-9_-]{43}',values.get('code_challenge','')):return None
        return dict(client),scopes,redirect_uri,resource
    @app.get('/oauth/authorize')
    def authorize():
        values=request.args.to_dict();result=authorization_parameters(values)
        if not result:return jsonify(error='invalid_request'),400
        session=csrf_session()
        if not session:return page('Sign in first','<p>Open <a href="/admin" target="_blank" rel="noopener">owner administration</a>, sign in, then refresh this authorization page. No assistant gets access without your consent.</p>'),401
        client,scopes,uri,resource=result
        return page('Authorize this assistant','''<p>{{name}} requests access to Menclave:</p><ul>{% for scope in scopes %}<li>{{scope}}</li>{% endfor %}</ul><p>Redirect: {{uri}}</p><form method="post" action="/oauth/authorize"><input type="hidden" name="csrf" value="{{csrf}}">{% for k,v in values.items() %}<input type="hidden" name="{{k}}" value="{{v}}">{% endfor %}<button class="button">Authorize for one hour</button></form>''',name=client['name'],scopes=scopes,uri=uri,values=values,csrf=session['csrf'])
    @app.post('/oauth/authorize')
    def consent():
        if not trusted():return jsonify(error='access_denied'),403
        values=request.form.to_dict();result=authorization_parameters(values)
        if not result:return jsonify(error='invalid_request'),400
        client,scopes,uri,resource=result
        code=secrets.token_urlsafe(40)
        with store.connect() as db:
            db.execute('INSERT INTO oauth_codes VALUES(?,?,?,?,?,?,?)',(store.digest(code),client['id'],uri,values['code_challenge'],canonical(scopes),resource,now()+120));platform.audit(db,'owner','oauth_consent',client['id'])
        params={'code':code}
        if values.get('state'):params['state']=values['state']
        return redirect(uri+('&' if '?' in uri else '?')+urlencode(params))
    @app.post('/oauth/token')
    def exchange():
        if store.limited(request.remote_addr or 'unknown','oauth-token',30,600):return jsonify(error='rate_limited'),429
        if request.form.get('grant_type')!='authorization_code':return jsonify(error='unsupported_grant_type'),400
        verifier=request.form.get('code_verifier','')
        if not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',verifier):return jsonify(error='invalid_grant'),400
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM oauth_codes WHERE digest=?',(store.digest(request.form.get('code','')),)).fetchone()
            if not row or row['expires']<=now() or row['client']!=request.form.get('client_id') or row['redirect']!=request.form.get('redirect_uri') or row['resource']!=request.form.get('resource') or not hmac.compare_digest(row['challenge'],challenge):return jsonify(error='invalid_grant'),400
            client=db.execute('SELECT revoked,expires FROM assistant_clients WHERE id=?',(row['client'],)).fetchone()
            if not client or client['revoked'] or client['expires']<=now():return jsonify(error='invalid_grant'),400
            db.execute('DELETE FROM oauth_codes WHERE digest=?',(row['digest'],))
            token='mcv_'+secrets.token_urlsafe(40)
            db.execute('INSERT INTO assistant_tokens VALUES(?,?,?,?,0)',(store.digest(token),row['client'],row['scopes'],now()+3600))
        response=jsonify(access_token=token,token_type='Bearer',expires_in=3600,scope=' '.join(json.loads(row['scopes'])))
        response.headers['Cache-Control']='no-store';return response
    @app.post('/oauth/revoke')
    def revoke_oauth():
        with store.connect() as db:db.execute('UPDATE assistant_tokens SET revoked=1 WHERE digest=?',(store.digest(request.form.get('token','')),))
        return '',200
    return csrf_session,trusted,page
