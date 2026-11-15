import json
import os
import re
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server.app import Store,ROOT
from server.web import create_app
from server.publishing import bootstrap
from server.editorial import validate_blocks,render_blocks,FORMATS
from server.services import SCOPES,DomainError
from server.tools import dispatch

class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        env=patch.dict(os.environ,{'MENCLAVE_SAMPLE_THREADS':'1','ENCLAVE_ORIGIN':'','MENCLAVE_WORKER':'0'});env.start();self.addCleanup(env.stop)
        self.store=Store(Path(self.temp.name)/'test.sqlite3');self.app=create_app(self.store,'test-only-key-with-at-least-32-characters');self.http=self.app.test_client();self.p=self.app.extensions['platform'];self.owner={'id':'editor-test','scopes':sorted(SCOPES)}
    def call(self,name,**args):
        if name not in {'content_preview','content_validate'}:args.setdefault('idempotency_key',secrets.token_hex(12))
        return dispatch(self.p,name,args,self.owner)
    def test_formats_render_and_block_content_is_searchable(self):
        stories=json.loads((ROOT/'content/stories.json').read_text())
        self.assertEqual(set(FORMATS),{s['format'] for s in stories})
        for story in stories:
            validate_blocks(story['blocks'])
            page=self.http.get('/magazine/'+story['slug']);self.assertEqual(page.status_code,200)
            self.assertIn(story['title'].replace('&','&amp;'),page.text)
            if story['format'] in {'profile','opinion'}:self.assertNotIn('demo-notice',page.text)
        counts={s['slug']:sum(b['type']=='image' for b in s['blocks']) for s in stories}
        self.assertEqual([counts[k] for k in ['good-man','starting-again','fatherhood']],[1,2,3])
        self.assertIn('Discipline Is a Spiritual Practice',self.http.get('/search?q=Thursday%3A+adjust').text)
        with self.http.get('/assets/jensen-huang.jpg') as image:self.assertEqual(image.status_code,200)
        self.assertEqual(self.http.get('/assets/not-a-photo.txt').status_code,404)
    def test_mcp_block_drafts_preview_and_publish(self):
        item=self.call('content_create_draft',data={'title':'Block-only story','slug':'block-only','deck':'A test introduction','format':'how-to','hero_layout':'split','blocks':[{'type':'step','title':'Begin safely','text':'A real body without legacy sections.'}]})
        self.assertTrue(self.call('content_validate',id=item['id'])['valid'])
        self.assertIn('article-step',self.call('content_preview',id=item['id'])['preview_html'])
        plan=self.call('content_publish',id=item['id'],expected_revision=1)
        self.assertTrue(plan['approval_required']);self.assertEqual(self.http.get('/magazine/block-only').status_code,404)
        with self.store.connect() as db:db.execute("UPDATE change_plans SET state='approved' WHERE id=?",(plan['plan_id'],))
        self.call('changes_commit',plan_id=plan['plan_id'])
        self.assertIn('A real body without legacy sections.',self.http.get('/magazine/block-only').text)
    def test_blocks_reject_active_content_and_escape_text(self):
        bad=[{'type':'video','src':'https://evil.test/video.mp4','title':'Video','description':'Description'},{'type':'image','src':'javascript:alert(1)','alt':'bad'},{'type':'sources','items':[{'title':'bad','url':'javascript:alert(1)'}]},{'type':'iframe','src':'https://evil.test/'}]
        for block in bad:
            with self.assertRaises((ValueError,DomainError)):
                self.call('content_create_draft',data={'title':'Unsafe','slug':'unsafe','blocks':[block]})
        html=render_blocks({'blocks':[{'type':'paragraph','text':'<script>alert(1)</script>'},{'type':'qa','question':'<img onerror=x>','answer':'A & B'}]})
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html);self.assertIn('A &amp; B',html)
    def test_thread_pages_are_server_rendered_and_moderation_safe(self):
        with self.store.connect() as db:
            for id,parent,status,body in [('real-root',None,'approved','An approved opening with <script>bad</script> and a real question.'),('real-reply','real-root','approved','A public reply with a different perspective.'),('pending-reply','real-root','pending','PRIVATE PENDING RESPONSE'),('pending-root',None,'pending','PRIVATE PENDING QUESTION')]:
                db.execute('INSERT INTO posts VALUES(?,?,?,?,?,?,?,?)',(id,parent,'Health & Fitness','A conversation worth discussing' if parent is None else '',body,'NEVER-PUBLIC-OWNER',status,1700000000))
        page=self.http.get('/conversations/real-root');self.assertEqual(page.status_code,200)
        self.assertIn('A public reply',page.text);self.assertNotIn('PRIVATE PENDING',page.text);self.assertNotIn('NEVER-PUBLIC-OWNER',page.text)
        self.assertNotIn('<script>bad',page.text);self.assertIn('&lt;script&gt;',page.text)
        self.assertIn('rel="canonical" href="http://localhost/conversations/real-root"',page.text)
        schema=json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',page.text,re.S)[1])
        self.assertEqual(schema['@type'],'DiscussionForumPosting');self.assertEqual(schema['commentCount'],1)
        self.assertIn('name="description"',page.text);self.assertNotIn('name="robots" content="noindex"',page.text)
        self.assertIn('href="/conversations/real-root"',self.http.get('/conversations').text)
        old=self.http.get('/enclave.html?thread=real-root');self.assertEqual(old.status_code,308);self.assertEqual(old.headers['Location'],'/conversations/real-root')
        self.assertIn('/conversations/real-root',self.http.get('/sitemap.xml').text)
        self.assertEqual(self.http.get('/conversations/pending-root').status_code,404)
        with self.store.connect() as db:db.execute("UPDATE posts SET status='removed' WHERE id='real-root'")
        self.assertEqual(self.http.get('/conversations/real-root').status_code,404)
        self.assertNotIn('/conversations/real-root',self.http.get('/sitemap.xml').text)
    def test_sample_threads_are_separate_and_not_indexed(self):
        page=self.http.get('/conversations/sample-vasectomy')
        self.assertIn('name="robots" content="noindex"',page.text);self.assertIn('Sample conversation',page.text)
        self.assertIn('intended to be permanent',page.text);self.assertNotIn('application/ld+json',page.text)
        self.assertNotIn('sample-vasectomy',self.http.get('/sitemap.xml').text)
        first=len(self.store.listing());bootstrap(self.p);self.assertEqual(len(self.store.listing()),first)
    def test_sample_upgrade_preserves_human_changes(self):
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM entities WHERE json_extract(data,'$.slug')='ibidapo-lawal'").fetchone()
            data=json.loads(row['data']);data['title']='A title changed by the editor'
            updated=self.p.save(db,'human-editor','article',data,row['id'],row['revision'],'published')
            db.execute("DELETE FROM config WHERE key='sample_formats_v2'")
        bootstrap(self.p)
        with self.store.connect() as db:current=self.p.get(db,row['id'])
        self.assertEqual(current['data']['title'],data['title']);self.assertEqual(current['revision'],updated['revision'])
