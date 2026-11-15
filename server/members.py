"""Private member accounts; public community posts remain anonymous."""
import re
import secrets
import time
from urllib.parse import urlencode
from flask import request,redirect,jsonify
from werkzeug.security import generate_password_hash,check_password_hash

NAV='<div class="account-nav" aria-label="Your account"><a href="/sign-in">Sign in</a><a href="/create-account" class="account-create">Create account</a></div>'

def current_member(store):
    token=request.cookies.get('menclave_member','')
    if not re.fullmatch(r'[0-9a-f]{64}',token):return None
    with store.connect() as db:
        row=db.execute('SELECT a.id,a.email FROM member_sessions s JOIN member_accounts a ON a.id=s.account WHERE s.digest=? AND s.expires>? AND a.disabled=0',(store.digest(token),int(time.time()))).fetchone()
        return dict(row) if row else None

def destination(value):return value if isinstance(value,str) and re.fullmatch(r'/(?!/)[A-Za-z0-9/_-]*',value) else '/conversations'

def install_members(app,platform,secure,owner_session,owner_page):
    from server.publishing import shell
    store=platform.store
    dummy=generate_password_hash('unused-random-'+secrets.token_hex(32))
    def form_page(create=False,error='',status=200):
        member=current_member(store)
        if member:return redirect(destination(request.values.get('next')))
        token=request.cookies.get('enclave_session','')
        if not re.fullmatch(r'[0-9a-f]{64}',token):token=secrets.token_hex(32)
        next_path=destination(request.values.get('next'))
        body='''<section class="member-page"><p class="eyebrow">MENCLAVE</p><h1>{{'Create your anonymous account.' if create else 'Welcome back.'}}</h1><p class="member-intro">{{'A private account. An honest conversation.' if create else 'Sign in to join the conversation.'}}</p>{% if error %}<p class="member-error" role="alert">{{error}}</p>{% endif %}<form method="post"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="next" value="{{next_path}}"><label for="member-email">Email address</label><input id="member-email" name="email" type="email" autocomplete="email" maxlength="254" required value="{{email}}"><label for="member-password">Password</label><input id="member-password" name="password" type="password" autocomplete="{{'new-password' if create else 'current-password'}}" minlength="{{12 if create else 1}}" maxlength="128" required>{% if create %}<p class="form-hint">Use at least 12 characters.</p>{% endif %}<button class="button" type="submit">{{'Create account' if create else 'Sign in'}}</button></form><p class="member-switch">{{'Already have an account?' if create else 'New here?'}} <a href="{{switch_url}}">{{'Sign in' if create else 'Create account'}}</a></p><p class="member-privacy">Your identity is hidden from other readers. Your account is private; your approved posts and replies are public.</p></section>'''
        response=app.make_response((shell(platform,'Create account' if create else 'Sign in','Your private Menclave account.',body,create=create,error=error,email=request.form.get('email','')[:254],csrf=store.digest('csrf:'+token),next_path=next_path,switch_url=('/sign-in' if create else '/create-account')+'?'+urlencode({'next':next_path}),story={'noindex':True}),status))
        response.set_cookie('enclave_session',token,max_age=2592000,httponly=True,samesite='Strict',secure=secure,path='/')
        return response
    def login_response(account):
        token=secrets.token_hex(32);expires=int(time.time())+2592000
        with store.connect() as db:
            db.execute('DELETE FROM member_sessions WHERE expires<?',(int(time.time()),))
            db.execute('INSERT INTO member_sessions VALUES(?,?,?)',(store.digest(token),account,expires))
        response=redirect(destination(request.form.get('next')))
        response.set_cookie('menclave_member',token,max_age=2592000,httponly=True,samesite='Strict',secure=secure,path='/')
        return response
    @app.route('/create-account',methods=['GET','POST'])
    def create_account():
        if request.method=='GET':return form_page(True)
        if current_member(store):return redirect('/account')
        if store.limited(request.remote_addr or 'unknown','signup',5,3600):return form_page(True,'Please try again later.',429)
        email=request.form.get('email','').strip().lower();password=request.form.get('password','')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254 or not 12<=len(password)<=128:return form_page(True,'Enter a valid email and a password of 12–128 characters.',400)
        password_hash=generate_password_hash(password);account=secrets.token_urlsafe(20)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM member_accounts WHERE email=?',(email,)).fetchone():return form_page(True,'Unable to create that account. Try signing in instead.',400)
            db.execute('INSERT INTO member_accounts VALUES(?,?,?,?,0)',(account,email,password_hash,int(time.time())))
        return login_response(account)
    @app.route('/sign-in',methods=['GET','POST'])
    def sign_in():
        if request.method=='GET':return form_page()
        email=request.form.get('email','').strip().lower()[:254];password=request.form.get('password','')
        if store.limited(request.remote_addr or 'unknown','signin',30,600) or store.limited(email,'signin',10,600):return form_page(False,'Too many attempts. Please try again later.',429)
        with store.connect() as db:row=db.execute('SELECT * FROM member_accounts WHERE email=?',(email,)).fetchone()
        valid=check_password_hash(row['password_hash'] if row else dummy,password[:128])
        if not row or not valid or row['disabled'] or len(password)>128:return form_page(False,'Email or password is incorrect.',400)
        return login_response(row['id'])
    @app.get('/api/member')
    def member_status():return jsonify(signed_in=bool(current_member(store)))
    @app.get('/account')
    def account_page():
        member=current_member(store)
        if not member:return redirect('/sign-in?next=/account')
        token=request.cookies.get('enclave_session','')
        # Signed-in users can obtain the public CSRF session if their cookie expired.
        if not re.fullmatch(r'[0-9a-f]{64}',token):return form_page()
        return shell(platform,'Your account','Your private account.','''<section class="member-page"><p class="eyebrow">YOUR ACCOUNT</p><h1>You’re signed in.</h1><p>{{email}}</p><p>Your identity is hidden from other readers.</p><a class="back-link" href="/conversations">Go to conversations →</a><form method="post" action="/sign-out"><input type="hidden" name="csrf" value="{{csrf}}"><button class="button" type="submit">Sign out</button></form></section>''',email=member['email'],csrf=store.digest('csrf:'+token),story={'noindex':True})
    @app.post('/sign-out')
    def sign_out():
        with store.connect() as db:db.execute('DELETE FROM member_sessions WHERE digest=?',(store.digest(request.cookies.get('menclave_member','')),))
        response=redirect('/');response.delete_cookie('menclave_member',path='/');return response
    @app.route('/contact.html',methods=['GET','POST'])
    def contact():
        token=request.cookies.get('enclave_session','')
        if not re.fullmatch(r'[0-9a-f]{64}',token):token=secrets.token_hex(32)
        error='';sent=False
        if request.method=='POST':
            name=request.form.get('name','').strip();email=request.form.get('email','').strip().lower();message=request.form.get('message','').strip()
            if store.limited(request.remote_addr or 'unknown','contact',5,3600):error='Please try again later.'
            elif not 1<=len(name)<=100 or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or not 20<=len(message)<=5000:error='Check your name, email and message (20–5,000 characters).'
            else:
                with store.connect() as db:db.execute('INSERT INTO contact_messages VALUES(?,?,?,?,?)',(secrets.token_urlsafe(20),name,email,message,int(time.time())))
                sent=True
        response=app.make_response(shell(platform,'Contact us','Get in touch with Menclave.','''<section class="member-page"><p class="eyebrow">GET IN TOUCH</p><h1>Contact us.</h1><p>Story ideas, corrections, partnerships or a note to the editors. We’d like to hear from you.</p>{% if sent %}<p role="status">Your message has been received. Thank you for getting in touch.</p>{% else %}{% if error %}<p class="member-error" role="alert">{{error}}</p>{% endif %}<form method="post"><input type="hidden" name="csrf" value="{{csrf}}"><label for="contact-name">Name</label><input id="contact-name" name="name" autocomplete="name" maxlength="100" required><label for="contact-email">Email address</label><input id="contact-email" type="email" name="email" autocomplete="email" maxlength="254" required><label for="contact-message">Your message</label><textarea id="contact-message" name="message" rows="6" minlength="20" maxlength="5000" required></textarea><p class="form-hint">Your message is private. We’ll use your email to respond to your enquiry.</p><button class="button" type="submit">Send message</button></form>{% endif %}</section>''',sent=sent,error=error,csrf=store.digest('csrf:'+token)))
        response.set_cookie('enclave_session',token,max_age=2592000,httponly=True,samesite='Strict',secure=secure,path='/');return response
    @app.get('/admin/contact')
    def contact_inbox():
        if not owner_session():return redirect('/admin')
        with store.connect() as db:messages=[dict(row) for row in db.execute('SELECT * FROM contact_messages ORDER BY created DESC LIMIT 100')]
        return owner_page('Contact inbox','''<a href="/admin">Owner control room</a>{% for item in messages %}<article class="moderation-item"><h2>{{item.name}}</h2><p>{{item.email}}</p><div class="post-body">{{item.message}}</div></article>{% else %}<p>No messages yet.</p>{% endfor %}''',messages=messages)
