import base64
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from PIL import Image
from starlette.testclient import TestClient
from server.app import Store
from server.web import create_app
from server.mcp_app import create_asgi
from server.services import Platform,DomainError,SCOPES,canonical,now
from server.tools import dispatch,CATALOG,setup
from server.worker import run_once

KEY='test-only-owner-key-at-least-32-characters'
class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'MENCLAVE_SAMPLE_THREADS':'0','MENCLAVE_WORKER':'0','ENCLAVE_ENV':'development','MENCLAVE_SMTP_HOST':'','ENCLAVE_ORIGIN':''});self.env.start();setup()
        self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.web=create_app(self.store,KEY);self.p=self.web.extensions['platform'];self.owner={'id':'test-client','scopes':sorted(SCOPES)};self.http=self.web.test_client()
    def tearDown(self):self.env.stop();setup();self.tmp.cleanup()
    def call(self,name,**args):
        if CATALOG[name]['write']:args.setdefault('idempotency_key',secrets.token_hex(12))
        return dispatch(self.p,name,args,self.owner)
    def draft(self):return self.call('content_create_draft',data={'title':'A thoughtful test story','slug':'test-'+secrets.token_hex(6),'deck':'A reflection','category':'Faith & Purpose','sections':[{'heading':'A beginning','body':'Some thoughtful editorial copy for this test.'}],'concept':True})
    def approve(self,plan):
        with self.store.connect() as db:db.execute("UPDATE change_plans SET state='approved' WHERE id=?",(plan['plan_id'],))
        return self.call('changes_commit',plan_id=plan['plan_id'])
    def login(self):
        response=self.http.get('/admin');csrf=re.search(r'name="csrf" value="([^"]+)"',response.text)[1]
        result=self.http.post('/admin/login',data={'key':KEY,'csrf':csrf},headers={'Origin':'http://localhost'})
        self.assertEqual(result.status_code,302)
        body=self.http.get('/admin').text
        return re.search(r'name="csrf" value="([^"]+)"',body)[1]
    def test_cms_approval_conflicts_and_public_snapshots(self):
        item=self.draft();url='/magazine/'+item['data']['slug']
        self.assertEqual(self.http.get(url).status_code,404)
        plan=self.call('content_publish',id=item['id'],expected_revision=1)
        self.assertTrue(plan['approval_required'])
        with self.assertRaises(DomainError):self.call('changes_commit',plan_id=plan['plan_id'])
        published=self.approve(plan)
        self.assertEqual(self.http.get(url).status_code,200)
        updated=self.call('content_update',id=item['id'],expected_revision=2,data={'title':'A changed title'})
        self.assertEqual(updated['status'],'draft')
        self.assertIn('A thoughtful test story',self.http.get(url).text)
        self.assertNotIn('A changed title',self.http.get(url).text)
        with self.assertRaises(DomainError):self.call('content_update',id=item['id'],expected_revision=2,data={'title':'Stale edit'})
        plan=self.call('content_publish',id=item['id'],expected_revision=3);self.approve(plan)
        self.assertIn('A changed title',self.http.get(url).text)
        plan=self.call('content_unpublish',id=item['id'],expected_revision=4);self.approve(plan)
        self.assertEqual(self.http.get(url).status_code,404)
    def test_idempotency_and_scope_enforcement(self):
        data={'title':'A test','slug':'idempotent','sections':[]}
        args={'data':data,'idempotency_key':'same-request-key'}
        a=dispatch(self.p,'content_create_draft',args,self.owner);b=dispatch(self.p,'content_create_draft',args,self.owner);self.assertEqual(a,b)
        with self.assertRaises(DomainError):dispatch(self.p,'content_create_draft',{'data':{**data,'title':'Other'},'idempotency_key':'same-request-key'},self.owner)
        with self.assertRaises(DomainError):dispatch(self.p,'content_create_draft',args,{'id':'reader','scopes':['read']})
        with self.assertRaises(DomainError):self.call('content_get',id=a['id'],unexpected='bad')
    def test_plan_expiration_and_post_approval_revision_change(self):
        item=self.draft();plan=self.call('content_publish',id=item['id'],expected_revision=1)
        with self.store.connect() as db:db.execute("UPDATE change_plans SET state='approved' WHERE id=?",(plan['plan_id'],))
        self.call('content_update',id=item['id'],expected_revision=1,data={'deck':'Changed after approval'})
        with self.assertRaises(DomainError):self.call('changes_commit',plan_id=plan['plan_id'])
        with self.store.connect() as db:db.execute('UPDATE change_plans SET expires=0 WHERE id=?',(plan['plan_id'],))
        with self.assertRaises(DomainError):self.call('changes_preview',plan_id=plan['plan_id'])
    def test_owner_auth_csrf_and_token_revocation(self):
        self.assertEqual(self.http.post('/admin/clients',data={'name':'Attacker'}).status_code,403)
        csrf=self.login()
        response=self.http.post('/admin/clients',data={'csrf':csrf,'name':'Grokbot','scopes':['read'],'days':'30'},headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,200)
        token=re.search(r'mcv_[A-Za-z0-9_-]+',response.text)[0]
        principal=self.p.authenticate(token);self.assertEqual(principal['scopes'],['read'])
        self.assertNotIn(token,self.http.get('/admin').text)
        self.http.post('/admin/revoke',data={'csrf':csrf,'id':principal['id']},headers={'Origin':'http://localhost'})
        self.assertIsNone(self.p.authenticate(token))
    def test_oauth_pkce_consent_resource_binding_and_code_replay(self):
        registration=self.http.post('/oauth/register',json={'client_name':'Test MCP','redirect_uris':['http://127.0.0.1:4567/callback']}).json
        verifier='a'*64;challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        values={'client_id':registration['client_id'],'redirect_uri':'http://127.0.0.1:4567/callback','response_type':'code','code_challenge_method':'S256','code_challenge':challenge,'resource':'http://localhost/mcp','scope':'read editorial:read','state':'return-state'}
        self.assertEqual(self.http.get('/oauth/authorize',query_string=values).status_code,401)
        csrf=self.login();response=self.http.post('/oauth/authorize',data={**values,'csrf':csrf},headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,302)
        from urllib.parse import urlsplit,parse_qs
        code=parse_qs(urlsplit(response.location).query)['code'][0]
        args={'grant_type':'authorization_code','code':code,'client_id':registration['client_id'],'redirect_uri':values['redirect_uri'],'code_verifier':verifier,'resource':'http://localhost/mcp'}
        self.assertEqual(self.http.post('/oauth/token',data={**args,'resource':'https://other.example/mcp'}).status_code,400)
        result=self.http.post('/oauth/token',data=args);self.assertEqual(result.status_code,200)
        self.assertEqual(self.p.authenticate(result.json['access_token'])['scopes'],['read','editorial:read'])
        self.assertEqual(self.http.post('/oauth/token',data=args).status_code,400)
    def test_streamable_http_sdk_auth_tools_and_resources(self):
        issued=self.p.issue_client('test reader',['read'])
        asgi=create_asgi(self.web,self.p)
        with TestClient(asgi) as client:
            self.assertEqual(client.post('/mcp',json={}).status_code,401)
            headers={'Authorization':'Bearer '+issued['token'],'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25'}
            initialize={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}}}
            response=client.post('/mcp',json=initialize,headers=headers);self.assertEqual(response.status_code,200,response.text)
            self.assertIn('result',response.json())
            response=client.post('/mcp',json={'jsonrpc':'2.0','id':2,'method':'tools/list'},headers=headers)
            names=[v['name'] for v in response.json()['result']['tools']]
            self.assertIn('community_list_threads',names);self.assertNotIn('content_create_draft',names)
            response=client.post('/mcp',json={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'app_get_status','arguments':{}}},headers=headers)
            self.assertFalse(response.json()['result']['isError'],response.text)
            response=client.post('/mcp',json={'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'content_create_draft','arguments':{'data':{},'idempotency_key':'test-key-long'}}},headers=headers)
            self.assertTrue(response.json()['result']['isError'])
            self.assertEqual(client.post('/mcp',json=initialize,headers={**headers,'Origin':'https://evil.example'}).status_code,403)
            result=client.post('/mcp',json={'jsonrpc':'2.0','id':5,'method':'resources/list'},headers=headers).json()
            self.assertIn('menclave://brand',[str(r['uri']) for r in result['result']['resources']])
    def test_media_real_upload_transform_and_reference_protection(self):
        upload=self.call('media_create_upload',mime='image/png')
        image=io.BytesIO();Image.new('RGB',(20,30),(160,20,20)).save(image,'PNG')
        response=self.http.put(upload['upload_path'],data=image.getvalue(),headers={'Authorization':'Bearer '+upload['upload_token'],'Content-Type':'image/png'})
        self.assertEqual(response.status_code,200,response.text)
        item=self.call('media_finalize_upload',upload_id=upload['upload_id'],alt='Test image')
        self.assertEqual(item['data']['width'],20)
        transformed=self.call('media_transform',id=item['id'],width=10,height=10)
        response=self.http.get(transformed['path']);self.assertEqual(response.status_code,200);response.close()
        draft=self.draft();self.call('content_update',id=draft['id'],expected_revision=1,data={'media_id':item['id']})
        with self.assertRaises(DomainError):self.call('media_archive',id=item['id'],expected_revision=1)
    def test_staff_moderation_lock_and_privacy(self):
        post=self.call('community_create_prompt',topic='Faith & Purpose',title='A staff conversation starter',body='An honest question to help men reflect on their week.')
        self.call('moderation_review',id=post['id'],action='approve')
        thread=self.http.get('/api/threads/'+post['id']).json
        self.assertTrue(thread['staff']);self.assertNotIn('owner',thread)
        self.call('community_lock_thread',id=post['id'])
        with self.assertRaises(ValueError):self.store.submit({'parent':post['id'],'body':'This should not be allowed on a locked thread.'},'private-test-owner')
    def test_backups_and_database_integrity(self):
        result=self.call('backups_create');check=self.call('backups_verify',id=result['id'])
        self.assertEqual(check['integrity'],'ok')
        self.assertNotIn(str(self.tmp.name),canonical(result))
    def test_scheduler_and_smtp_delivery_suppression(self):
        draft=self.draft();plan=self.call('content_schedule',id=draft['id'],expected_revision=1,due=now()+5);scheduled=self.approve(plan)
        with self.store.connect() as db:db.execute('UPDATE jobs SET due=0')
        run_once(self.p)
        self.assertEqual(self.http.get('/magazine/'+draft['data']['slug']).status_code,200)
        with patch.dict(os.environ,{'MENCLAVE_SMTP_HOST':'smtp.example.test','MENCLAVE_SMTP_FROM':'letter@example.test','ENCLAVE_ORIGIN':'https://menclave.example'}):
            setup()
            issue=self.call('newsletter_create_draft',data={'title':'Sunday letter','slug':'sunday-letter','sections':[{'heading':'Hello','body':'A Sunday reflection.'}]})
            with self.store.connect() as db:
                for id,email,suppressed in [('one','one@example.test',0),('two','two@example.test',1)]:db.execute('INSERT INTO audience VALUES(?,?,1,?,?)',(id,email,suppressed,now()))
            plan=self.call('newsletter_send',id=issue['id'],expected_revision=1);job=self.approve(plan)
            with patch('smtplib.SMTP_SSL') as smtp:
                run_once(self.p)
                self.assertEqual(smtp.return_value.__enter__.return_value.send_message.call_count,1)
                run_once(self.p)
                self.assertEqual(smtp.return_value.__enter__.return_value.send_message.call_count,1)
    def test_configured_branding_and_webhook_restrictions(self):
        self.call('site_update_config',data={'tagline':'Life with purpose','accent':'#a32e2b'},expected_revision=0)
        self.assertIn('Life with purpose',self.http.get('/').text)
        self.assertIn('#a32e2b',self.http.get('/theme.css').text)
        with self.assertRaises(DomainError):self.call('site_update_config',data={'accent':'url(https://evil)'},expected_revision=1)
        with self.assertRaises(DomainError):self.call('webhooks_upsert',data={'url':'http://127.0.0.1/private'})

    def test_double_optin_and_unsubscribe(self):
        with patch.dict(os.environ,{'MENCLAVE_SMTP_HOST':'smtp.example.test','MENCLAVE_SMTP_FROM':'letter@example.test','ENCLAVE_ORIGIN':'https://menclave.example'}):
            app=create_app(self.store,KEY);client=app.test_client()
            session=client.get('/api/session').json
            response=client.post('/api/newsletter/subscribe',json={'email':'reader@example.test'},headers={'Origin':'https://menclave.example','X-CSRF-Token':session['csrf']})
            self.assertEqual(response.status_code,200,response.text)
            with self.store.connect() as db:
                subscriber=db.execute('SELECT * FROM audience').fetchone();self.assertEqual(subscriber['consent'],0)
                job=db.execute("SELECT payload FROM jobs WHERE kind='optin'").fetchone();token=json.loads(job[0])['token']
            self.assertEqual(client.get('/newsletter/confirm/'+token).status_code,200)
            with self.store.connect() as db:self.assertEqual(db.execute('SELECT consent FROM audience').fetchone()[0],0)
            self.assertEqual(client.post('/newsletter/confirm/'+token).status_code,200)
            signature=self.store.digest('unsubscribe:'+subscriber['id'])
            path='/unsubscribe/'+subscriber['id']+'/'+signature
            self.assertEqual(client.get(path).status_code,200)
            with self.store.connect() as db:self.assertEqual(db.execute('SELECT suppressed FROM audience').fetchone()[0],0)
            self.assertEqual(client.post(path).status_code,200)
            with self.store.connect() as db:self.assertEqual(db.execute('SELECT suppressed FROM audience').fetchone()[0],1)
    def test_restore_requires_stopped_server_and_revokes_clients(self):
        import subprocess
        issued=self.p.issue_client('Before restore',['read'])
        backup=self.call('backups_create');plan=self.call('backups_restore',id=backup['id']);job=self.approve(plan)
        env=dict(os.environ,ENCLAVE_DB=self.store.path)
        import fcntl
        with open(Path(self.store.path).parent/'runtime.lock','a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result=subprocess.run([os.sys.executable,'-m','server.manage','restore','--job-id',job['job_id'],'--maintenance'],env=env,text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('Menclave is running',result.stderr)
        result=subprocess.run([os.sys.executable,'-m','server.manage','restore','--job-id',job['job_id'],'--maintenance'],env=env,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIsNone(self.p.authenticate(issued['token']))
    def test_official_mcp_client_over_real_http(self):
        import asyncio,socket,threading,time
        import uvicorn,httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
        issued=self.p.issue_client('SDK client',['read','editorial:read'])
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(create_asgi(self.web,self.p),log_level='critical',access_log=False))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
        deadline=time.time()+5
        while not server.started and time.time()<deadline:time.sleep(.02)
        self.assertTrue(server.started)
        async def exercise():
            async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+issued['token']}) as http:
                async with Client(streamable_http_client(f'http://127.0.0.1:{port}/mcp',http_client=http)) as client:
                    tools=await client.list_tools()
                    self.assertIn('content_get',[tool.name for tool in tools.tools])
                    result=await client.call_tool('app_get_status',{})
                    self.assertEqual(result.structured_content['status'],'ok')
                    resource=await client.read_resource('menclave://brand')
                    self.assertIn('Menclave',resource.contents[0].text)
                    prompts=await client.list_prompts();self.assertTrue(prompts.prompts)
                    prompt=await client.get_prompt('audit_seo');self.assertTrue(prompt.messages)
        try:asyncio.run(exercise())
        finally:server.should_exit=True;thread.join(5);sock.close()
    def test_governance_taxonomy_revisions_and_public_config(self):
        category=self.call('categories_upsert',data={'name':'Purpose'})
        self.assertIn(category['id'],[v['id'] for v in self.call('categories_list')['items']])
        author=self.call('authors_upsert',data={'name':'Menclave editorial team'})
        draft=self.draft();self.call('content_update',id=draft['id'],expected_revision=1,data={'author_id':author['id']})
        revisions=self.call('revisions_list',id=draft['id'])
        self.assertEqual(len(revisions['items']),2)
        self.call('guidelines_update',data={'text':'Protect privacy and listen with care.'},expected_revision=0)
        self.assertEqual(self.http.get('/api/community-config').json['text'],'Protect privacy and listen with care.')
        self.call('abuse_rules_update',data={'session_limit':3,'network_limit':10},expected_revision=0)
        self.assertEqual(self.store.abuse_limits()['session_limit'],3)
        self.assertEqual(self.call('abuse_rules_get')['data']['network_limit'],10)
    def test_failed_newsletter_is_not_automatically_retried(self):
        from server.worker import recover
        with patch.dict(os.environ,{'MENCLAVE_SMTP_HOST':'smtp.example.test','MENCLAVE_SMTP_FROM':'letter@example.test','ENCLAVE_ORIGIN':'https://menclave.example'}):
            setup();issue=self.call('newsletter_create_draft',data={'title':'No duplicate sends','slug':'no-duplicate','sections':[{'heading':'Hello','body':'A test newsletter.'}]})
            with self.store.connect() as db:db.execute('INSERT INTO audience VALUES(?,?,1,0,?)',('recipient','reader@example.test',now()))
            job=self.approve(self.call('newsletter_send',id=issue['id'],expected_revision=1))
            with patch('smtplib.SMTP_SSL') as smtp:
                smtp.return_value.__enter__.return_value.send_message.side_effect=TimeoutError('Sensitive provider message must not escape')
                run_once(self.p);run_once(self.p)
                self.assertEqual(smtp.return_value.__enter__.return_value.send_message.call_count,1)
            result=self.call('jobs_get',id=job['job_id']);self.assertEqual(result['state'],'needs_review');self.assertNotIn('Sensitive',canonical(result))

    def test_newsletter_approval_is_bound_to_audience(self):
        with patch.dict(os.environ,{'MENCLAVE_SMTP_HOST':'smtp.example.test'}):
            setup();issue=self.call('newsletter_create_draft',data={'title':'Audience-bound letter','slug':'audience-bound','sections':[{'heading':'Hello','body':'An approved message.'}]})
            with self.store.connect() as db:db.execute('INSERT INTO audience VALUES(?,?,1,0,?)',('first','first@example.test',now()))
            plan=self.call('newsletter_send',id=issue['id'],expected_revision=1)
            self.assertEqual(plan['summary']['confirmed_unsuppressed_recipients'],1)
            with self.store.connect() as db:
                db.execute("UPDATE change_plans SET state='approved' WHERE id=?",(plan['plan_id'],))
                db.execute('INSERT INTO audience VALUES(?,?,1,0,?)',('new','new@example.test',now()))
            with self.assertRaises(DomainError):self.call('changes_commit',plan_id=plan['plan_id'])
    def test_owner_grants_only_requested_scopes_and_replaces_tokens(self):
        issued=self.p.issue_client('Assistant',['read'])
        principal=self.p.authenticate(issued['token'])
        request=dispatch(self.p,'access_request_change',{'scopes':['read','editorial:write'],'idempotency_key':'request-more-scopes'},principal)
        self.assertEqual(request['kind'],'access_request')
        csrf=self.login()
        response=self.http.post('/admin/grant',data={'csrf':csrf,'request_id':request['id']},headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,200,response.text)
        token=re.search(r'mcv_[A-Za-z0-9_-]+',response.text)[0]
        self.assertIsNone(self.p.authenticate(issued['token']))
        self.assertEqual(self.p.authenticate(token)['scopes'],['editorial:write','read'])
    def test_redirects_apply_and_cycles_are_rejected(self):
        self.call('redirects_upsert',data={'source':'/old-story','destination':'/magazine'})
        response=self.http.get('/old-story');self.assertEqual(response.status_code,308);self.assertEqual(response.location,'/magazine')
        with self.assertRaises(DomainError):self.call('redirects_upsert',data={'source':'/magazine','destination':'/old-story'})

    def test_data_deletion_scrubs_delivery_metadata_and_request_plans(self):
        email='erase@example.test'
        with self.store.connect() as db:
            db.execute('INSERT INTO audience VALUES(?,?,1,0,?)',('erase',email,now()))
            db.execute("INSERT INTO jobs(id,kind,payload,state,due,created,updated) VALUES('mail','newsletter','{}','completed',0,0,0)")
            db.execute("INSERT INTO job_deliveries VALUES('mail',?,'sent',0)",(email,))
        plan=self.call('audience_process_deletion',email=email)
        self.approve(plan)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM audience').fetchone()[0],0)
            self.assertNotIn(email,db.execute('SELECT recipient FROM job_deliveries').fetchone()[0])
            self.assertNotIn(email,db.execute('SELECT args FROM change_plans WHERE id=?',(plan['plan_id'],)).fetchone()[0])
            for cached in db.execute('SELECT result FROM idempotency').fetchall():self.assertNotIn(email,cached[0])
    def test_owner_key_rotation_invalidates_sessions(self):
        self.login()
        self.assertIn('Menclave control room',self.http.get('/admin').text)
        create_app(self.store,'replacement-owner-key-longer-than-32-characters')
        self.assertIn('Owner access',self.http.get('/admin').text)

    def test_unified_search_excludes_drafts_pending_and_removed_posts(self):
        public=self.store.submit({'title':'Public perspective on cedar','topic':'Faith & Purpose','body':'An approved conversation about cedar and personal growth.'},'private-owner')
        pending=self.store.submit({'title':'Unreviewed cedar question','topic':'Faith & Purpose','body':'Unreviewed private cedar material should never enter search.'},'private-owner')
        self.store.moderate({'id':public,'action':'approve'})
        draft=self.draft()
        self.call('content_update',id=draft['id'],expected_revision=1,data={'title':'A private cedar article'})
        reply=self.store.submit({'parent':public,'body':'A public reply mentioning unusual birchsearch words.'},'private-reply-owner')
        self.store.moderate({'id':reply,'action':'approve'})
        response=self.http.get('/search?q=cedar')
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('Public perspective on cedar',response.text)
        self.assertNotIn('Unreviewed cedar question',response.text)
        self.assertNotIn('A private cedar article',response.text)
        self.assertNotIn('private-owner',response.text)
        self.assertIn('/conversations/'+public,response.text)
        self.assertIn('Public perspective on cedar',self.http.get('/search?q=birchsearch').text)
        self.store.moderate({'id':public,'action':'remove'})
        self.assertNotIn('Public perspective on cedar',self.http.get('/search?q=cedar').text)
    def test_shared_search_and_feed_composer_structure(self):
        for path in ['/','/magazine','/enclave.html','/magazine/discipline']:
            result=self.http.get(path)
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.text.count('class="global-search"'),1)
            self.assertIn('action="/search"',result.text)
            result.close()
        response=self.http.get('/enclave.html');enclave=response.text;response.close()
        self.assertIn('class="post-composer"',enclave)
        self.assertNotIn('class="ask-panel"',enclave)
        self.assertNotIn('id="community-search"',enclave)
        self.assertLess(enclave.index('id="ask-form"'),enclave.index('id="thread-list"'))
        result=self.http.get('/search?q=faith&type=articles')
        self.assertEqual(result.status_code,200)
        self.assertIn('From the magazine',result.text)
        self.assertNotIn('id="conversation-results"',result.text)

if __name__=='__main__':unittest.main()
