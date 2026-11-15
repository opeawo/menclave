import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server.app import Store
from server.web import create_app

class MemberTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        env=patch.dict(os.environ,{'MENCLAVE_SAMPLE_THREADS':'1','ENCLAVE_ORIGIN':'','MENCLAVE_WORKER':'0'});env.start();self.addCleanup(env.stop)
        self.store=Store(Path(temp.name)/'db.sqlite3');self.web=create_app(self.store,'test-owner-password-with-at-least-32-chars');self.http=self.web.test_client()
    def form(self,path='/create-account',email='reader@example.test',password='a-long-private-password'):
        page=self.http.get(path);csrf=re.search('name="csrf" value="([^"]+)"',page.text)[1]
        return self.http.post(path,data={'csrf':csrf,'email':email,'password':password,'next':'/conversations/sample-reading'},headers={'Origin':'http://localhost'})
    def test_signup_private_account_and_moderated_reply(self):
        page=self.http.get('/conversations/sample-reading');self.assertIn('Sign in to reply',page.text);self.assertNotIn('id="reply-form"',page.text)
        response=self.form();self.assertEqual(response.status_code,302,response.text);self.assertEqual(response.headers['Location'],'/conversations/sample-reading')
        self.assertIn('HttpOnly',response.headers['Set-Cookie']);self.assertIn('SameSite=Strict',response.headers['Set-Cookie'])
        page=self.http.get('/conversations/sample-reading');self.assertIn('id="reply-form"',page.text);self.assertNotIn('reader@example.test',page.text)
        csrf=self.http.get('/api/session').json['csrf']
        result=self.http.post('/api/replies',json={'parent':'sample-reading','body':'This book helped me think about responsibility differently.'},headers={'Origin':'http://localhost','X-CSRF-Token':csrf});self.assertEqual(result.status_code,201,result.text)
        self.assertNotIn('This book helped',self.http.get('/conversations/sample-reading').text)
        self.store.moderate({'id':result.json['id'],'action':'approve'})
        page=self.http.get('/conversations/sample-reading');self.assertIn('This book helped',page.text);self.assertNotIn('reader@example.test',page.text)
        with self.store.connect() as db:
            account=db.execute('SELECT * FROM member_accounts').fetchone();self.assertNotIn('a-long-private-password',account['password_hash'])
            owner=db.execute('SELECT owner FROM posts WHERE id=?',(result.json['id'],)).fetchone()[0]
            self.assertEqual(owner,self.store.digest('member:'+account['id']))
    def test_signin_logout_and_session_revocation(self):
        self.form();csrf=self.http.get('/api/session').json['csrf']
        self.assertEqual(self.http.post('/sign-out',data={'csrf':csrf},headers={'Origin':'http://localhost'}).status_code,302)
        self.assertFalse(self.http.get('/api/member').json['signed_in'])
        self.assertEqual(self.form('/sign-in',password='wrong').status_code,400)
        self.assertEqual(self.form('/sign-in').status_code,302)
        self.assertTrue(self.http.get('/api/member').json['signed_in'])
        with self.store.connect() as db:db.execute('UPDATE member_accounts SET disabled=1')
        self.assertFalse(self.http.get('/api/member').json['signed_in'])
    def test_csrf_auth_and_open_redirect_protection(self):
        self.assertEqual(self.http.post('/create-account',data={'email':'reader@example.test','password':'a-long-private-password'}).status_code,403)
        self.http.get('/api/session');self.assertEqual(self.http.post('/api/replies',json={'parent':'sample-reading','body':'An unauthenticated reply with enough detail.'},headers={'Origin':'http://localhost','X-CSRF-Token':self.http.get('/api/session').json['csrf']}).status_code,401)
        page=self.http.get('/create-account?next=//evil.test');self.assertIn('name="next" value="/conversations"',page.text)
        self.assertEqual(self.form(password='short').status_code,400)
    def test_contact_and_footer(self):
        page=self.http.get('/contact.html');csrf=re.search('name="csrf" value="([^"]+)"',page.text)[1]
        response=self.http.post('/contact.html',data={'csrf':csrf,'name':'A Reader','email':'private@example.test','message':'A private editorial enquiry with enough detail.'},headers={'Origin':'http://localhost'})
        self.assertIn('Your message has been received',response.text)
        self.assertEqual(self.http.get('/admin/contact').status_code,302)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM contact_messages').fetchone()[0],1)
        with self.http.get('/about.html') as response:about=response.text
        self.assertIn('Prosperity Tech',about);self.assertIn('do not reflect the opinions',about)
        footer=about[about.index('<footer'):];self.assertNotIn('Conversations',footer);self.assertIn('All rights reserved',footer)
    def test_complete_book_list_is_searchable_and_numbered(self):
        html=self.http.get('/magazine/top-100-books').text
        self.assertEqual(len(re.findall('class="book-entry"',html)),100)
        self.assertEqual(len(re.findall('class="book-shelf"',html)),10)
        self.assertIn('id="book-100"',html);self.assertIn('The Little Prince',html)
        self.assertIn('top-100-books',self.http.get('/search?q=Aristotle').text)
        self.assertIn('href="/conversations/sample-reading"',html)
