import os
from unittest.mock import patch
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.app import Store
from server.web import create_app
from werkzeug.serving import make_server
from werkzeug.serving import WSGIRequestHandler

class QuietHandler(WSGIRequestHandler):
    def log(self,*args,**kwargs): pass

class CommunityTests(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'MENCLAVE_SAMPLE_THREADS':'0'});env.start();self.addCleanup(env.stop)
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.sqlite3')
        self.key='test-only-moderator-key-not-a-real-secret'
        self.server=make_server('127.0.0.1',0,create_app(self.store,self.key),threaded=True,request_handler=QuietHandler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_port
        self.cookie='';self.csrf=''
        status,data,headers=self.request('GET','/api/session')
        self.assertEqual(status,200)
        self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=data['csrf']
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,method,path,data=None,admin=False,origin=True,csrf=True):
        client=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        headers={'Cookie':self.cookie,'Content-Type':'application/json'}
        if origin:headers['Origin']=f'http://127.0.0.1:{self.port}'
        if csrf:headers['X-CSRF-Token']=self.csrf
        if admin:headers['Authorization']='Bearer '+self.key
        client.request(method,path,json.dumps(data) if data is not None else None,headers)
        response=client.getresponse();raw=response.read();headers=dict(response.getheaders());status=response.status;client.close()
        try:result=json.loads(raw)
        except ValueError:result=raw.decode()
        return status,result,headers
    def question(self):
        status,data,_=self.request('POST','/api/threads',{'title':'How do you make space for rest?','topic':'Faith & Purpose','body':'A test question about making time for reflection and rest.'})
        self.assertEqual(status,201);return data['id']
    def approve(self,id):
        self.assertEqual(self.request('POST','/api/moderation',{'id':id,'action':'approve'},admin=True)[0],200)
    def test_full_moderated_lifecycle_and_privacy(self):
        id=self.question()
        self.assertEqual(self.request('GET','/api/threads')[1]['threads'],[])
        self.assertEqual(self.request('GET','/api/threads/'+id)[0],404)
        self.assertEqual(self.request('GET','/api/moderation')[0],401)
        queue=self.request('GET','/api/moderation',admin=True)[1]
        self.assertEqual(queue['pending'][0]['id'],id)
        self.approve(id)
        public=self.request('GET','/api/threads')[1]['threads'][0]
        self.assertNotIn('owner',public);self.assertNotIn('reporter',json.dumps(public));self.assertNotIn('status',public)
        status,reply,_=self.request('POST','/api/replies',{'parent':id,'body':'A thoughtful test reply with enough detail to be useful.'})
        self.assertEqual(status,201)
        self.assertEqual(self.request('GET','/api/threads/'+id)[1]['replies'],[])
        self.approve(reply['id'])
        self.assertEqual(len(self.request('GET','/api/threads/'+id)[1]['replies']),1)
        self.assertEqual(self.request('POST','/api/reports',{'post':reply['id'],'reason':'Identifying information'})[0],201)
        self.assertEqual(len(self.request('GET','/api/moderation',admin=True)[1]['reports']),1)
        self.assertEqual(self.request('POST','/api/moderation',{'id':id,'action':'remove'},admin=True)[0],200)
        self.assertEqual(self.request('GET','/api/threads/'+id)[0],404)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM posts WHERE body != ""').fetchone()[0],0)
        self.assertEqual(self.request('GET','/api/moderation',admin=True)[1]['reports'],[])
    def test_csrf_origin_validation_and_private_assets(self):
        for options in [{'csrf':False},{'origin':False}]:
            self.assertEqual(self.request('POST','/api/threads',{},**options)[0],403)
        self.assertEqual(self.request('POST','/api/threads',{'body':'short'})[0],400)
        for path in ['/server/app.py','/.local/enclave.sqlite3','/content/stories.json','/../AGENTS.md']:
            self.assertEqual(self.request('GET',path)[0],404)
        status,html,headers=self.request('GET','/enclave.html')
        self.assertEqual(status,200);self.assertIn('Conversations.',html);self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
    def test_storage_persistence_search_and_rate_limit(self):
        id=self.question();self.approve(id)
        store=Store(self.store.path)
        self.assertEqual(store.listing('reflection')[0]['id'],id)
        self.assertEqual(store.listing('', 'Money & Ambition'),[])
        for _ in range(9):self.request('POST','/api/reports',{'post':id,'reason':'Spam or promotion'})
        self.assertEqual(self.request('POST','/api/reports',{'post':id,'reason':'Other concern'})[0],429)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM reports').fetchone()[0],1)
    def test_moderation_disabled_without_key(self):
        client=create_app(self.store,admin_key='').test_client()
        self.assertEqual(client.get('/api/moderation',headers={'Authorization':'Bearer '}).status_code,401)
    def test_schema_upgrade_audit_and_backup(self):
        id=self.question();self.approve(id)
        with self.store.connect() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8)
            audit=db.execute('SELECT * FROM moderation_audit').fetchone()
            self.assertEqual(audit['target'],id)
            self.assertNotIn('body',audit.keys())
            import sqlite3
            output=Path(self.tmp.name)/'backup.sqlite3'
            with sqlite3.connect(output) as target:db.backup(target)
        restored=Store(output)
        self.assertEqual(restored.thread(id)['id'],id)
        self.assertEqual(self.request('GET','/api/health')[1],{'status':'ok'})

    def test_production_configuration_and_secure_cookie(self):
        import os
        from unittest.mock import patch
        values={'ENCLAVE_ENV':'production','ENCLAVE_DB':str(Path(self.tmp.name)/'production.sqlite3'),'ENCLAVE_ADMIN_KEY':self.key,'ENCLAVE_ORIGIN':'https://menclave.example'}
        with patch.dict(os.environ,values):
            client=create_app().test_client()
            response=client.get('/api/session')
            self.assertIn('Secure',response.headers['Set-Cookie'])
            self.assertIn('HttpOnly',response.headers['Set-Cookie'])
            self.assertIn('max-age=',response.headers['Strict-Transport-Security'])
            self.assertEqual(client.get('/api/health').json,{'status':'ok'})
            with patch.dict(os.environ,{'ENCLAVE_ADMIN_KEY':''}):
                with self.assertRaises(ValueError):create_app()
            with patch.dict(os.environ,{'ENCLAVE_ORIGIN':'http://unsafe.example'}):
                with self.assertRaises(ValueError):create_app()

if __name__=='__main__':unittest.main()
