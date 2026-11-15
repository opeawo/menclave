"""Permission-enforced services used by MCP and the administrative HTTP interface."""
from server.editorial import validate_blocks, render_blocks, FORMATS, HERO_LAYOUTS, safe_media
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit
from server.app import ROOT, TOPICS

SCOPES={'read','editorial:read','editorial:write','editorial:publish','media:write','site:write','community:moderate','newsletter:write','newsletter:send','audience:read','audience:write','analytics:read','integrations:write','operations:read','operations:write','database:maintain','access:manage','audit:read'}
KINDS={'article','interview','news','page','newsletter','category','tag','author','site','navigation','homepage','redirect','guidelines','abuse_rules','segment','integration','webhook','schedule','seo','feed','media','access_request'}
PROTECTED={'content_schedule','content_publish','content_unpublish','content_archive','content_restore','revisions_restore','newsletter_send','newsletter_schedule','audience_process_deletion','deployments_publish','deployments_rollback','backups_restore','access_revoke_client','migrations_apply','schedules_upsert'}

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def now():return int(time.time())
def ident():return secrets.token_urlsafe(16)

class DomainError(Exception):
    def __init__(self,code,message):self.code=code;super().__init__(message)
def require(condition,message,code='invalid_arguments'):
    if not condition:raise DomainError(code,message)

class Platform:
    def __init__(self,store):
        self.store=store
        self.data_dir=Path(os.environ.get('MENCLAVE_DATA_DIR',str(Path(store.path).parent)))
        self.media_dir=self.data_dir/'media';self.backup_dir=self.data_dir/'backups'
        for path in (self.media_dir,self.backup_dir):path.mkdir(mode=0o700,parents=True,exist_ok=True)
    def audit(self,db,actor,tool,target='',outcome='ok'):
        event_id=ident()
        db.execute('INSERT INTO platform_audit VALUES(?,?,?,?,?,?)',(event_id,actor,tool,str(target)[:100],outcome,now()))
        for row in db.execute("SELECT id,data FROM entities WHERE kind='webhook' AND status!='archived'").fetchall():
            data=json.loads(row['data'])
            if data.get('enabled',True) and (not data.get('events') or tool in data['events']):
                db.execute('INSERT INTO webhook_deliveries VALUES(?,?,?,?,?)',(ident(),row['id'],canonical({'id':event_id,'tool':tool,'target':str(target)[:100],'outcome':outcome,'created':now()}),'queued',now()))
    def issue_client(self,name,scopes,days=30):
        require(isinstance(name,str) and 1<=len(name)<=100,'Client name required.')
        require(set(scopes)<=SCOPES and bool(scopes),'Unknown or empty scopes.')
        require(1<=days<=365,'Expiry must be between 1 and 365 days.')
        client=ident();token='mcv_'+secrets.token_urlsafe(40);expiry=now()+days*86400
        with self.store.connect() as db:
            db.execute('INSERT INTO assistant_clients(id,name,scopes,expires) VALUES(?,?,?,?)',(client,name,canonical(sorted(set(scopes))),expiry))
            db.execute('INSERT INTO assistant_tokens VALUES(?,?,?,?,0)',(self.store.digest(token),client,canonical(sorted(set(scopes))),expiry))
            self.audit(db,'owner','access_issue_client',client)
        return {'client_id':client,'token':token,'expires':expiry}
    def authenticate(self,token):
        if not token or len(token)>500:return None
        with self.store.connect() as db:
            row=db.execute('SELECT t.*,c.revoked client_revoked,c.expires client_expires FROM assistant_tokens t JOIN assistant_clients c ON c.id=t.client WHERE t.digest=?',(self.store.digest(token),)).fetchone()
            if not row or row['revoked'] or row['client_revoked'] or min(row['expires'],row['client_expires'])<=now():return None
            return {'id':row['client'],'scopes':json.loads(row['scopes'])}
    def record(self,row):
        require(row is not None,'Record unavailable.','not_found')
        return {'id':row['id'],'kind':row['kind'],'data':json.loads(row['data']),'status':row['status'],'revision':row['revision'],'created':row['created'],'updated':row['updated']}
    def get(self,db,id,kind=None):
        result=self.record(db.execute('SELECT * FROM entities WHERE id=?',(id,)).fetchone())
        require(not kind or result['kind'] in ([kind] if isinstance(kind,str) else kind),'Wrong record type.')
        return result
    def list(self,db,kind=None,status=None,query='',cursor='',limit=25):
        require(isinstance(limit,int) and 1<=limit<=100,'Limit must be 1–100.')
        rows=db.execute("SELECT * FROM entities WHERE (? IS NULL OR kind=?) AND (? IS NULL OR status=?) AND (?='' OR instr(lower(data),lower(?))>0) AND id>? ORDER BY id LIMIT ?",(kind,kind,status,status,query,query,cursor,limit+1)).fetchall()
        return {'items':[self.record(row) for row in rows[:limit]],'next_cursor':rows[limit-1]['id'] if len(rows)>limit else None}
    def save(self,db,actor,kind,data,id=None,revision=None,status=None):
        require(kind in KINDS,'Unsupported record type.')
        require(isinstance(data,dict) and len(canonical(data))<=100000,'Record must be a bounded object.')
        if kind in {'article','interview','news','page','newsletter'}:
            data=dict(data);data.setdefault('concept',True)
            require(isinstance(data.get('title'),str) and 1<=len(data['title'])<=200,'Title required (maximum 200 characters).')
            require('\n' not in data['title'] and '\r' not in data['title'],'Titles must be a single line.')
            require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',data.get('slug','')) is not None,'A lowercase URL slug is required.')
            require(isinstance(data.get('sections',[]),list) and len(data.get('sections',[]))<=100,'Invalid sections.')
            require(data.get('format','personal-story') in FORMATS,'Invalid article format.')
            require(data.get('hero_layout','overlay-left') in HERO_LAYOUTS,'Invalid hero layout.')
            if 'blocks' in data:
                try:validate_blocks(data['blocks'])
                except ValueError as error:raise DomainError('invalid_arguments',str(error))
            for section in data.get('sections',[]):
                require(isinstance(section,dict) and all(isinstance(section.get(k,''),str) for k in ('heading','body')),'Sections contain plain heading/body text.')
            for field in ['deck','category','alt','image','author_id','media_id']:
                require(isinstance(data.get(field,''),str),'Invalid '+field)
            for field,related in [('media_id','media'),('author_id','author')]:
                if data.get(field):require(self.get(db,data[field],related)['status']!='archived','Referenced record is archived.')
            for field in ['seo_title','seo_description','canonical']:
                require(isinstance(data.get(field,''),str),'Invalid '+field)
            if data.get('canonical'):require(re.fullmatch(r'/(?!/)[A-Za-z0-9/_-]*',data['canonical']) is not None,'Canonical must be a local path.')
            if data.get('image'):
                require(safe_media(data['image']),'Use uploaded media or an approved image host.')
            duplicate=db.execute("SELECT id FROM entities WHERE kind IN ('article','interview','news','page','newsletter') AND json_extract(data,'$.slug')=? AND id!=?",(data['slug'],id or '')).fetchone()
            require(not duplicate,'That slug is already in use.','conflict')
        existing=db.execute('SELECT * FROM entities WHERE id=?',(id,)).fetchone() if id else None
        previous=self.record(existing) if existing else None
        require(not previous or previous['kind']==kind,'Wrong record type.')
        if previous:require(revision==previous['revision'],'Record changed; refresh its revision.','conflict')
        id=id or ident();version=previous['revision']+1 if previous else 1
        state=status or (previous['status'] if previous else 'draft')
        require(state in {'draft','published','scheduled','archived','review'},'Invalid record status.')
        db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,status=excluded.status,revision=excluded.revision,updated=excluded.updated',(id,kind,canonical(data),state,version,previous['created'] if previous else now(),now()))
        result=self.get(db,id)
        if state=='published' and kind in {'article','interview','news','page','newsletter'}:
            db.execute('INSERT INTO published_content VALUES(?,?,?) ON CONFLICT(entity) DO UPDATE SET revision=excluded.revision,snapshot=excluded.snapshot',(id,version,canonical(result)))
        db.execute('INSERT INTO entity_revisions VALUES(?,?,?,?,?)',(id,version,canonical(result),actor,now()))
        return result
    def call(self,tool,args,principal,definition,approved=False):
        require(definition['scope'] in principal['scopes'],'Permission denied.','forbidden')
        require(definition.get('enabled',True),'This integration is not configured.','unavailable')
        if definition['write']:
            require(isinstance(args.get('idempotency_key'),str) and 8<=len(args['idempotency_key'])<=150,'An idempotency_key of 8–150 characters is required.')
        with self.store.connect() as db:
            if definition['write']:db.execute('BEGIN IMMEDIATE')
            fingerprint=hashlib.sha256(canonical({'tool':tool,'args':args}).encode()).hexdigest()
            if definition['write']:
                old=db.execute('SELECT * FROM idempotency WHERE actor=? AND key=?',(principal['id'],args['idempotency_key'])).fetchone()
                if old:
                    require(old['fingerprint']==fingerprint,'Idempotency key was used for another request.','conflict')
                    return json.loads(old['result'])
            if tool in PROTECTED and not approved:
                plan=ident();clean={k:v for k,v in args.items() if k!='idempotency_key'}
                # Bind a plan to the current revision rather than whatever is current at approval time.
                if 'id' in clean and tool.startswith(('content_','revisions_','newsletter_')):
                    item=self.get(db,clean['id'])
                    require(clean.get('expected_revision')==item['revision'],'An up-to-date expected_revision is required.','conflict')
                summary={'action':tool,'environment':os.environ.get('ENCLAVE_ENV','development')}
                if tool in {'newsletter_send','newsletter_schedule'} or tool=='schedules_upsert' and clean.get('data',{}).get('kind')=='newsletter':
                    audience=self.newsletter_audience(db,clean)
                    clean['_audience_fingerprint']=self.store.digest(canonical(audience))
                    summary['confirmed_unsuppressed_recipients']=len(audience)
                if tool.startswith('content_') and 'id' in clean:
                    item=self.get(db,clean['id']);summary.update(title=item['data'].get('title'),current_revision=item['revision'],current_status=item['status'])
                if tool.startswith('deployments_'):
                    clean['_provider_project_id']=os.environ.get('MENCLAVE_PXXL_PROJECT_ID','');summary['project_id']=clean['_provider_project_id']
                if tool=='backups_restore':summary['effects']=['Database replacement during maintenance','Revoke all assistant tokens and owner sessions','Cancel pending jobs','Media files are not included']
                db.execute('INSERT INTO change_plans(id,actor,tool,args,fingerprint,expires,state,summary) VALUES(?,?,?,?,?,?,?,?)',(plan,principal['id'],tool,canonical(clean),fingerprint,now()+900,'pending',canonical(summary)))
                result={'approval_required':True,'plan_id':plan,'tool':tool,'arguments':clean,'summary':summary,'expires':now()+900,'approval_path':'/admin#approvals'}
            else:
                result=self.execute(db,tool,args,principal)
            if definition['write']:
                db.execute('INSERT INTO idempotency VALUES(?,?,?,?)',(principal['id'],args['idempotency_key'],fingerprint,canonical(result)))
                self.audit(db,principal['id'],tool,args.get('id',args.get('plan_id','')))
            return result
    def execute(self,db,tool,a,p):
        actor=p['id'];read={'article','interview','news','page','newsletter'}
        if tool=='app_get_status':return {'status':'ok','database':'connected','schema':db.execute('PRAGMA user_version').fetchone()[0]}
        if tool=='app_search':
            require('editorial:read' in p['scopes'],'Editorial read permission required.','forbidden')
            return self.list(db,query=a.get('query',''),cursor=a.get('cursor',''),limit=a.get('limit',25))
        if tool=='content_list':
            kinds=[a['kind']] if a.get('kind') else sorted(read)
            items=[]
            for kind in kinds:items.extend(self.list(db,kind,a.get('status'),a.get('query',''),a.get('cursor',''),a.get('limit',25))['items'])
            items=sorted(items,key=lambda v:v['id']);limit=a.get('limit',25)
            return {'items':items[:limit],'next_cursor':items[limit-1]['id'] if len(items)>limit else None}
        if tool in {'content_get','content_validate','content_preview','newsletter_preview','seo_audit','social_preview'}:
            item=self.get(db,a['id'],'newsletter' if tool=='newsletter_preview' else read)
            if tool in {'content_validate','seo_audit'}:
                data=item['data'];issues=[]
                for field in ['title','slug','deck']:
                    if not data.get(field):issues.append('Missing '+field)
                if not (data.get('blocks') or data.get('sections')):issues.append('Missing body content')
                if data.get('image') and not data.get('alt'):issues.append('Image alt text is missing')
                if not data.get('concept',True) and not data.get('approved_copy'):issues.append('Real editorial copy needs approval')
                return {'valid':not issues,'issues':issues,'revision':item['revision']}
            if tool in {'content_preview','newsletter_preview'}:
                from jinja2 import Environment
                item['preview_html']=Environment(autoescape=True).from_string('<article>{% if story.concept %}<p>EDITORIAL CONCEPT</p>{% endif %}<h1>{{story.title}}</h1><p>{{story.deck}}</p>{{body|safe}}</article>').render(story=item['data'],body=render_blocks(item['data']))
                item['owner_preview_path']='/admin/preview/'+item['id']
                return item
            if tool=='social_preview':return {'title':item['data']['title'],'description':item['data'].get('deck',''),'image':item['data'].get('image'),'url':'/magazine/'+item['data']['slug']}
            return item
        if tool in {'content_create_draft','newsletter_create_draft'}:
            kind='newsletter' if tool.startswith('newsletter') else a.get('kind','article')
            require(kind in read,'Unsupported editorial type.')
            return self.save(db,actor,kind,a['data'])
        if tool in {'content_update','newsletter_update','seo_update'}:
            old=self.get(db,a['id'],read)
            data=dict(old['data']);data.update(a['data'])
            return self.save(db,actor,old['kind'],data,a['id'],a['expected_revision'],'draft')
        states={'content_publish':'published','content_unpublish':'draft','content_archive':'archived','content_restore':'draft','editorial_request_review':'review'}
        if tool in states:
            old=self.get(db,a['id'],read)
            if tool=='content_publish':require(bool(old['data'].get('blocks') or old['data'].get('sections')),'Content must have body content before publishing.')
            if tool in {'content_unpublish','content_archive'}:
                require(a['expected_revision']==old['revision'],'Record changed.','conflict')
                db.execute('DELETE FROM published_content WHERE entity=?',(a['id'],))
            return self.save(db,actor,old['kind'],old['data'],a['id'],a['expected_revision'],states[tool])
        if tool=='content_schedule':
            old=self.get(db,a['id'],read);require(a['due']>now(),'Schedule must be in the future.')
            result=self.save(db,actor,old['kind'],old['data'],a['id'],a['expected_revision'],'scheduled')
            job=self.enqueue(db,'publish',{'id':a['id'],'revision':result['revision']},a['due'])
            return {'content':result,'job':job}
        if tool=='editorial_review':
            old=self.get(db,a['id'],read);data=dict(old['data']);data['review']={'decision':a['decision'],'note':a.get('note',''),'reviewer':actor,'at':now()}
            return self.save(db,actor,old['kind'],data,a['id'],a['expected_revision'],'draft')
        if tool=='editorial_calendar':return self.list(db,status='scheduled',limit=a.get('limit',25),cursor=a.get('cursor',''))
        if tool.startswith('revisions_'):
            self.get(db,a['id'],read)
            if tool=='revisions_list':
                rows=db.execute('SELECT revision,actor,created FROM entity_revisions WHERE entity=? AND revision>? ORDER BY revision LIMIT ?',(a['id'],int(a.get('cursor') or 0),a.get('limit',25)+1)).fetchall();limit=a.get('limit',25)
                return {'items':[dict(r) for r in rows[:limit]],'next_cursor':str(rows[limit-1]['revision']) if len(rows)>limit else None}
            def revision(n):
                row=db.execute('SELECT snapshot FROM entity_revisions WHERE entity=? AND revision=?',(a['id'],n)).fetchone();require(row is not None,'Revision unavailable.','not_found');return json.loads(row[0])
            if tool=='revisions_get':return revision(a['revision'])
            if tool=='revisions_compare':return {'before':revision(a['from_revision']),'after':revision(a['to_revision'])}
            old=self.get(db,a['id']);snapshot=revision(a['revision'])
            return self.save(db,actor,old['kind'],snapshot['data'],a['id'],a['expected_revision'],'draft')
        simple={'categories':'category','tags':'tag','authors':'author','site':'site','navigation':'navigation','homepage':'homepage','redirects':'redirect','guidelines':'guidelines','abuse_rules':'abuse_rules','audience':'segment','integrations':'integration','webhooks':'webhook','schedules':'schedule'}
        prefix='abuse_rules' if tool.startswith('abuse_rules_') else tool.split('_')[0]
        if prefix in simple and tool not in {'audience_get_summary','audience_get_consent','audience_suppress','audience_process_deletion','integrations_test','webhooks_disable','guidelines_update','abuse_rules_update'}:
            kind=simple[prefix]
            if tool.endswith('_list') or tool=='audience_list_segments':return self.list(db,kind,cursor=a.get('cursor',''),limit=a.get('limit',25))
            id=a.get('id') or (kind if kind in {'site','navigation','homepage','guidelines','abuse_rules'} else None)
            if tool.endswith(('_get','_get_config')):
                row=db.execute('SELECT * FROM entities WHERE id=? AND kind=?',(id,kind)).fetchone()
                return self.record(row) if row else {'id':id,'kind':kind,'data':{},'revision':0}
            data=a['data'];old=db.execute('SELECT revision FROM entities WHERE id=?',(id,)).fetchone()
            if kind in {'category','tag','author'}:require(isinstance(data.get('name'),str) and 1<=len(data['name'])<=150,'Name required.')
            if kind=='redirect':
                require(re.fullmatch(r'/(?!/)[A-Za-z0-9/_-]*',data.get('source','')) and re.fullmatch(r'/(?!/)[A-Za-z0-9/_-]*',data.get('destination','')) and data['source']!=data['destination'],'Use distinct local redirect paths without queries.')
                duplicate=db.execute("SELECT id FROM entities WHERE kind='redirect' AND json_extract(data,'$.source')=? AND id!=?",(data['source'],id or '')).fetchone()
                require(not duplicate,'A redirect already exists for this source. Update its ID.','conflict')
                destination=data['destination'];seen={data['source']}
                for _ in range(20):
                    require(destination not in seen,'Redirect cycle detected.');seen.add(destination)
                    next_row=db.execute("SELECT data FROM entities WHERE kind='redirect' AND json_extract(data,'$.source')=? AND id!=?",(destination,id or '')).fetchone()
                    if not next_row:break
                    destination=json.loads(next_row[0])['destination']
                else:raise DomainError('invalid_arguments','Redirect chain is too long.')
            if kind=='site':
                require(set(data)<={'title','tagline','description','accent','paper','ink'} and all(isinstance(v,str) and len(v)<=500 for v in data.values()),'Only approved text branding fields may be changed.')
                for color in ['accent','paper','ink']:
                    if color in data:require(re.fullmatch(r'#[0-9a-fA-F]{6}',data[color]) is not None,'Colors must use six-digit hex.')
            if kind=='navigation':
                require(isinstance(data.get('links'),list) and len(data['links'])<=12,'At most 12 links.')
                require(all(isinstance(v,dict) and isinstance(v.get('label'),str) and re.fullmatch(r'/[A-Za-z0-9/#?=&%._-]*',v.get('href','')) and not v['href'].startswith('//') for v in data['links']),'Navigation links must use local paths.')
            if kind=='homepage':
                require(isinstance(data.get('featured_ids',[]),list) and all(isinstance(v,str) for v in data.get('featured_ids',[])) and isinstance(data.get('heading',''),str),'Invalid homepage fields.')
                require(set(data)<={'hero_id','featured_ids','heading'},'Unsupported homepage setting.')
                ids=([data['hero_id']] if data.get('hero_id') else [])+data.get('featured_ids',[])
                require(len(ids)<=20,'At most 20 featured stories.')
                for target in ids:require(db.execute('SELECT 1 FROM published_content WHERE entity=?',(target,)).fetchone() is not None,'Homepage can feature published content only.')
            if kind=='segment':
                require(set(data)<={'name','created_after','created_before'} and isinstance(data.get('name'),str),'Use a segment name and optional creation timestamps.')
                require(all(isinstance(v,int) and v>=0 for k,v in data.items() if k!='name'),'Segment times must be UNIX timestamps.')
            if kind=='integration':
                require(set(data)<={'provider','enabled','secret_ref'},'Only provider metadata and secret references are allowed.')
                require(re.fullmatch(r'MENCLAVE_[A-Z0-9_]+',data.get('secret_ref','')) is not None,'Use an environment variable reference, never a raw credential.')
            if kind=='webhook':
                from server.providers import validate_webhook
                validate_webhook(data)
            if kind=='schedule':
                require(set(data)<={'kind','content_id','content_revision','due','every_seconds','enabled'},'Unsupported schedule fields.')
                require(data.get('kind') in {'publish','newsletter'} and isinstance(data.get('due'),int) and data['due']>now() and isinstance(data.get('every_seconds'),int) and 60<=data['every_seconds']<=2678400,'Invalid schedule.')
                needed='editorial:publish' if data['kind']=='publish' else 'newsletter:send'
                require(needed in p['scopes'],'Action-specific scheduling permission required.','forbidden')
                item=self.get(db,data['content_id']);require(item['revision']==data.get('content_revision'),'Scheduled content changed.','conflict')
                if data['kind']=='publish':require(item['status']=='scheduled','Use content_schedule for a future publication.')
                else:
                    require(item['kind']=='newsletter' and bool(os.environ.get('MENCLAVE_SMTP_HOST')),'Newsletter delivery is not configured.','unavailable')
                    audience=self.newsletter_audience(db,{})
                    require(a.get('_audience_fingerprint')==self.store.digest(canonical(audience)),'Audience changed after schedule approval.','conflict')
                    data=dict(data);data['audience_ids']=[r['id'] for r in audience]
            return self.save(db,actor,kind,data,id,a.get('expected_revision'))
        if tool in {'guidelines_update','abuse_rules_update'}:
            kind='guidelines' if tool.startswith('guidelines') else 'abuse_rules'
            old=db.execute('SELECT * FROM entities WHERE kind=? ORDER BY updated DESC LIMIT 1',(kind,)).fetchone()
            if kind=='guidelines':require(isinstance(a['data'].get('text'),str) and len(a['data']['text'])<=10000,'Guidelines text required.')
            else:
                require(set(a['data'])<={'session_limit','network_limit'} and all(isinstance(v,int) and 1<=v<=100 for v in a['data'].values()),'Abuse limits must be 1–100.')
            return self.save(db,actor,kind,a['data'],old['id'] if old else kind,a.get('expected_revision'))
        if tool=='integrations_test':
            item=self.get(db,a['id'],'integration');ref=item['data'].get('secret_ref','')
            configured=bool(os.environ.get(ref));provider=item['data'].get('provider')
            if not configured:return {'configured':False,'provider':provider,'connection_verified':False}
            if provider=='pxxl':
                from server.providers import pxxl_operation
                result=pxxl_operation('deployments_list',{})
                return {'configured':True,'provider':provider,'connection_verified':True,'result':result}
            if provider=='smtp':
                import smtplib,ssl
                require(bool(os.environ.get('MENCLAVE_SMTP_HOST')),'SMTP host required.')
                with smtplib.SMTP_SSL(os.environ['MENCLAVE_SMTP_HOST'],int(os.environ.get('MENCLAVE_SMTP_PORT','465')),timeout=10,context=ssl.create_default_context()) as smtp:
                    if os.environ.get('MENCLAVE_SMTP_USER'):smtp.login(os.environ['MENCLAVE_SMTP_USER'],os.environ.get('MENCLAVE_SMTP_PASSWORD',''))
                    code,_=smtp.noop();require(code==250,'SMTP connection failed.','provider_error')
                return {'configured':True,'provider':provider,'connection_verified':True}
            return {'configured':True,'provider':provider,'connection_verified':False,'note':'No connection-test adapter for this provider.'}
        if tool=='webhooks_disable':
            item=self.get(db,a['id'],'webhook');data=dict(item['data']);data['enabled']=False
            return self.save(db,actor,'webhook',data,a['id'],a['expected_revision'])
        if tool.startswith('community_') or tool.startswith('moderation_') or tool=='reports_list' or tool=='reports_resolve':return self.community(db,tool,a,p)
        if tool.startswith('audience_'):return self.audience(db,tool,a,p)
        if tool.startswith('analytics_'):
            if tool=='analytics_get_newsletter':return {'items':[dict(r) for r in db.execute('SELECT state,count(*) count FROM job_deliveries GROUP BY state').fetchall()]}
            if tool=='analytics_get_community':return self.community(db,'community_get_summary',a,p)
            rows=db.execute('SELECT day,path,source,sum(count) count FROM analytics_daily WHERE day>=? GROUP BY day,path,source ORDER BY day DESC LIMIT 100',(a.get('since','1970-01-01'),)).fetchall()
            return {'items':[dict(r) for r in rows],'coverage':'Only traffic observed by this instance; no historical backfill.'}
        if tool.startswith('media_'):return self.media(db,tool,a,p)
        if tool.startswith('newsletter_'):return self.newsletter(db,tool,a,p)
        if tool.startswith('jobs_'):
            if tool=='jobs_list':return {'items':[dict(r) for r in db.execute('SELECT id,kind,state,due,created,updated FROM jobs WHERE id>? ORDER BY id LIMIT ?',(a.get('cursor',''),a.get('limit',25))).fetchall()]}
            row=db.execute('SELECT * FROM jobs WHERE id=?',(a['id'],)).fetchone();require(row is not None,'Job unavailable.','not_found')
            if tool=='jobs_cancel':require(row['state']=='queued','Only queued jobs may be cancelled.');db.execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=?",(now(),a['id']))
            if tool=='jobs_cancel':return {'id':a['id'],'state':'cancelled'}
            return {**{k:row[k] for k in ('id','kind','state','due','created','updated')},'result':json.loads(row['result'])}
        if tool in {'database_get_status','migrations_get_status','migrations_plan','migrations_apply','schedules_upsert'}:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            return {'schema_version':version,'integrity':db.execute('PRAGMA quick_check').fetchone()[0],'pending':[],'note':'Migrations are applied atomically during startup; schema changes deploy with code.'}
        if tool.startswith('backups_'):return self.backups(db,tool,a,p)
        if tool.startswith('access_'):
            if tool=='access_get_scopes':return {'scopes':p['scopes'],'available':sorted(SCOPES)}
            if tool=='access_list_clients':return {'items':[dict(r) for r in db.execute('SELECT id,name,scopes,expires,revoked FROM assistant_clients ORDER BY id LIMIT 100').fetchall()]}
            if tool=='access_request_change':
                require(set(a['scopes'])<=SCOPES,'Unknown scopes.')
                return self.save(db,actor,'access_request',{'client_id':actor,'requested_scopes':sorted(set(a['scopes']))})
            require(a['id']!=actor,'Use the trusted owner UI to revoke this active client.')
            db.execute('UPDATE assistant_clients SET revoked=1 WHERE id=?',(a['id'],));return {'revoked':True}
        if tool.startswith('audit_') or tool=='logs_get':
            if tool=='audit_get_change':
                row=db.execute('SELECT * FROM platform_audit WHERE id=?',(a['id'],)).fetchone();require(row is not None,'Audit entry unavailable.','not_found');return dict(row)
            rows=db.execute('SELECT * FROM platform_audit WHERE id>? ORDER BY id LIMIT ?',(a.get('cursor',''),a.get('limit',25))).fetchall()
            return {'items':[dict(row) for row in rows]}
        if tool=='health_get':return {'status':'ok','database':'connected'}
        if tool=='cache_invalidate':return {'status':'ok','note':'Dynamic pages and management responses are not cached.'}
        if tool in {'feeds_rebuild','sitemap_rebuild'}:return {'path':'/feed.xml' if tool.startswith('feeds') else '/sitemap.xml','generated':'on request from published content'}
        if tool.startswith('changes_'):
            row=db.execute('SELECT * FROM change_plans WHERE id=? AND actor=?',(a['plan_id'],actor)).fetchone();require(row is not None,'Plan unavailable.','not_found')
            require(row['expires']>now(),'Plan expired.','expired')
            if tool=='changes_preview':return {**{k:row[k] for k in ('id','tool','expires','state')},'args':json.loads(row['args']),'summary':json.loads(row['summary'])}
            require(row['state']=='approved','Owner approval in the trusted admin UI is required.','approval_required')
            from server.tools import CATALOG
            definition=CATALOG[row['tool']]
            require(definition['scope'] in p['scopes'],'Permission revoked.','forbidden')
            require(definition.get('enabled',True),'Integration unavailable.','unavailable')
            result=self.execute(db,row['tool'],json.loads(row['args']),p)
            db.execute("UPDATE change_plans SET state='committed' WHERE id=?",(row['id'],));self.audit(db,actor,row['tool'],row['id'])
            return result
        if tool.startswith('deployments_'):
            if tool in {'deployments_publish','deployments_rollback'}:require(a.get('_provider_project_id')==os.environ.get('MENCLAVE_PXXL_PROJECT_ID'),'Provider project changed after approval.','conflict')
            if tool in {'deployments_publish','deployments_rollback','deployments_preview'}:
                return self.enqueue(db,'pxxl',{'tool':tool,'args':{k:v for k,v in a.items() if k!='idempotency_key'},'project_id':os.environ.get('MENCLAVE_PXXL_PROJECT_ID')})
            from server.providers import pxxl_operation
            return pxxl_operation(tool,a)
        raise DomainError('unavailable','This capability is not configured.')
    def enqueue(self,db,kind,payload,due=None):
        id=ident();db.execute('INSERT INTO jobs(id,kind,payload,state,due,created,updated) VALUES(?,?,?,?,?,?,?)',(id,kind,canonical(payload),'queued',due or now(),now(),now()));return {'job_id':id,'state':'queued'}
    def community(self,db,tool,a,p):
        if tool=='community_list_threads':
            rows=db.execute("SELECT * FROM posts WHERE parent IS NULL AND status='approved' AND id>? AND (?='' OR topic=?) ORDER BY id LIMIT ?",(a.get('cursor',''),a.get('topic',''),a.get('topic',''),a.get('limit',25))).fetchall()
            return {'items':[{k:r[k] for k in ('id','parent','topic','title','body','created')} for r in rows]}
        if tool=='community_get_thread':return self.store.thread(a['id']) or {'unavailable':True}
        if tool=='community_get_summary':return {'approved_questions':db.execute("SELECT count(*) FROM posts WHERE parent IS NULL AND status='approved'").fetchone()[0],'approved_replies':db.execute("SELECT count(*) FROM posts WHERE parent IS NOT NULL AND status='approved'").fetchone()[0]}
        if tool=='community_get_guidelines':
            row=db.execute("SELECT data FROM entities WHERE kind='guidelines' ORDER BY updated DESC LIMIT 1").fetchone();return json.loads(row[0]) if row else {'text':'Protect privacy. Be respectful. No hate, harassment or spam. Posts are reviewed.'}
        if tool=='moderation_list_queue':
            rows=db.execute("SELECT id,parent,topic,title,body,created FROM posts WHERE status='pending' AND id>? ORDER BY id LIMIT ?",(a.get('cursor',''),a.get('limit',25))).fetchall();return {'items':[dict(r) for r in rows]}
        if tool=='reports_list':return {'items':[dict(r) for r in db.execute('SELECT id,post,reason,created,resolved FROM reports WHERE resolved=0 AND id>? ORDER BY id LIMIT ?',(a.get('cursor',''),a.get('limit',25))).fetchall()]}
        if tool=='reports_resolve':db.execute('UPDATE reports SET resolved=1 WHERE id=?',(a['id'],));return {'resolved':True}
        if tool in {'community_lock_thread','community_unlock_thread'}:
            row=db.execute("SELECT id FROM posts WHERE id=? AND parent IS NULL AND status='approved'",(a['id'],)).fetchone();require(row is not None,'Conversation unavailable.','not_found')
            db.execute('INSERT INTO thread_controls(post,locked) VALUES(?,?) ON CONFLICT(post) DO UPDATE SET locked=excluded.locked',(a['id'],int(tool=='community_lock_thread')));return {'locked':tool=='community_lock_thread'}
        if tool=='community_create_prompt':
            require(a.get('topic') in TOPICS and 10<=len(a.get('title',''))<=160 and 20<=len(a.get('body',''))<=5000,'Invalid prompt.')
            id=ident();db.execute('INSERT INTO posts VALUES(?,NULL,?,?,?,?,?,?)',(id,a['topic'],a['title'],a['body'],'staff','pending',now()));db.execute('INSERT INTO thread_controls(post,staff) VALUES(?,1)',(id,));return {'id':id,'status':'pending','staff':True}
        if tool=='moderation_review':
            require(a['action'] in {'approve','remove'},'Invalid moderation action.')
            row=db.execute('SELECT * FROM posts WHERE id=?',(a['id'],)).fetchone();require(row is not None,'Post unavailable.','not_found')
            if a['action']=='approve':
                if row['parent']:require(db.execute("SELECT 1 FROM posts WHERE id=? AND status='approved'",(row['parent'],)).fetchone() is not None,'Parent unavailable.')
                require(row['status']=='pending','Only pending posts may be approved.')
                db.execute("UPDATE posts SET status='approved' WHERE id=?",(row['id'],))
            else:
                # Moderation removal is an explicitly scoped action. No identity data is returned.
                db.execute("UPDATE posts SET status='removed',title='',body='' WHERE id=? OR parent=?",(row['id'],row['id']))
                db.execute('UPDATE reports SET resolved=1 WHERE post=? OR post IN (SELECT id FROM posts WHERE parent=?)',(row['id'],row['id']))
            db.execute('INSERT INTO moderation_audit VALUES(?,?,?,?,?)',(ident(),row['id'],a['action'],p['id'],now()));return {'id':row['id'],'action':a['action']}
        raise DomainError('unavailable','Community operation unavailable.')
    def audience(self,db,tool,a,p):
        if tool=='audience_get_summary':return {'confirmed':db.execute('SELECT count(*) FROM audience WHERE consent=1 AND suppressed=0').fetchone()[0],'suppressed':db.execute('SELECT count(*) FROM audience WHERE suppressed=1').fetchone()[0]}
        require(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',a.get('email','')) is not None,'Email required.')
        row=db.execute('SELECT * FROM audience WHERE email=?',(a['email'].strip().lower(),)).fetchone()
        if tool=='audience_get_consent':return {'exists':bool(row),'consent':bool(row['consent']) if row else False,'suppressed':bool(row['suppressed']) if row else False}
        if tool=='audience_suppress':
            db.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('suppression:'+self.store.digest(a['email'].strip().lower()),'1'))
            if row:db.execute('UPDATE audience SET suppressed=1 WHERE id=?',(row['id'],))
            return {'suppressed':True}
        # Retain a one-way suppression digest to prevent later accidental reimport.
        email=a['email'].strip().lower()
        db.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('suppression:'+self.store.digest(email),'1'))
        db.execute('UPDATE job_deliveries SET recipient=? WHERE lower(recipient)=?',('deleted:'+self.store.digest(email),email))
        for plan in db.execute("SELECT id,args FROM change_plans WHERE lower(json_extract(args,'$.email'))=?",(email,)).fetchall():
            args=json.loads(plan['args']);args['email']='[deleted]'
            db.execute("UPDATE change_plans SET args=?,state=CASE WHEN state IN ('pending','approved') THEN 'redacted' ELSE state END WHERE id=?",(canonical(args),plan['id']))
        for cached in db.execute("SELECT actor,key,result FROM idempotency WHERE lower(json_extract(result,'$.arguments.email'))=?",(email,)).fetchall():
            result=json.loads(cached['result']);result['arguments']['email']='[deleted]'
            db.execute('UPDATE idempotency SET result=? WHERE actor=? AND key=?',(canonical(result),cached['actor'],cached['key']))
        for job in db.execute("SELECT id,payload,state FROM jobs WHERE lower(json_extract(payload,'$.email'))=?",(email,)).fetchall():
            db.execute("UPDATE jobs SET payload='{}',state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END WHERE id=?",(job['id'],))
        if row:db.execute('DELETE FROM audience WHERE id=?',(row['id'],))
        return {'deleted':True}
    def media(self,db,tool,a,p):
        from PIL import Image, ImageOps, UnidentifiedImageError
        if tool=='media_list':return self.list(db,'media',cursor=a.get('cursor',''),limit=a.get('limit',25))
        if tool=='media_get':return self.get(db,a['id'],'media')
        if tool=='media_create_upload':
            require(a['mime'] in {'image/jpeg','image/png','image/webp'},'Only JPEG, PNG and WebP images are accepted.')
            id=ident();secret=secrets.token_urlsafe(32)
            db.execute('INSERT INTO media_uploads VALUES(?,?,?,?,0)',(id,self.store.digest(secret),a['mime'],now()+900))
            return {'upload_id':id,'upload_path':'/api/media-upload/'+id,'upload_token':secret,'expires':now()+900,'max_bytes':10000000}
        if tool=='media_finalize_upload':
            row=db.execute('SELECT * FROM media_uploads WHERE id=?',(a['upload_id'],)).fetchone();require(row is not None and row['uploaded'],'Upload image bytes first.')
            path=self.media_dir/(a['upload_id']+'.webp');require(path.is_file(),'Uploaded image unavailable.')
            old=db.execute("SELECT * FROM entities WHERE kind='media' AND json_extract(data,'$.upload_id')=?",(a['upload_id'],)).fetchone()
            if old:return self.record(old)
            require(isinstance(a.get('alt'),str) and len(a['alt'])<=500,'Alt text required.')
            with Image.open(path) as image:width,height=image.size
            return self.save(db,p['id'],'media',{'upload_id':a['upload_id'],'alt':a['alt'],'credit':a.get('credit',''),'license':a.get('license',''),'width':width,'height':height,'path':'/media/'+path.name})
        item=self.get(db,a['id'],'media')
        if tool=='media_update_metadata':
            require(set(a['data'])<={'alt','credit','license','focal_x','focal_y'},'Unsupported metadata.')
            data=dict(item['data']);data.update(a['data']);return self.save(db,p['id'],'media',data,a['id'],a['expected_revision'])
        if tool=='media_archive':
            require(not db.execute("SELECT 1 FROM entities WHERE status!='archived' AND json_extract(data,'$.media_id')=?",(a['id'],)).fetchone(),'Media is referenced by content.')
            return self.save(db,p['id'],'media',item['data'],a['id'],a['expected_revision'],'archived')
        if tool=='media_transform':
            width=a['width'];height=a['height'];require(1<=width<=3000 and 1<=height<=3000,'Image dimensions must be 1–3000.')
            source=self.media_dir/(item['data']['upload_id']+'.webp');name=ident()+'.webp'
            with Image.open(source) as image:ImageOps.fit(image,(width,height)).save(self.media_dir/name,'WEBP',quality=85)
            return {'path':'/media/'+name,'width':width,'height':height}
        raise DomainError('unavailable','Media operation unavailable.')
    def newsletter_audience(self,db,args):
        segment=self.get(db,args['segment_id'],'segment')['data'] if args.get('segment_id') else {}
        return [dict(row) for row in db.execute('SELECT id,email FROM audience WHERE consent=1 AND suppressed=0 AND created>=? AND created<=? ORDER BY id',(segment.get('created_after',0),segment.get('created_before',now()))).fetchall()]
    def newsletter(self,db,tool,a,p):
        if tool=='newsletter_list_issues':return self.list(db,'newsletter',cursor=a.get('cursor',''),limit=a.get('limit',25))
        if tool=='newsletter_cancel':
            row=db.execute("SELECT state FROM jobs WHERE id=? AND kind='newsletter'",(a['id'],)).fetchone();require(row is not None and row['state']=='queued','Only queued sends can be cancelled.');db.execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=?",(now(),a['id']));return {'cancelled':True}
        if tool=='newsletter_get_delivery':
            row=db.execute("SELECT id,state,result,created,updated FROM jobs WHERE id=? AND kind='newsletter'",(a['id'],)).fetchone();require(row is not None,'Delivery unavailable.','not_found');return {**dict(row),'result':json.loads(row['result'])}
        require(bool(os.environ.get('MENCLAVE_SMTP_HOST')),'SMTP delivery is not configured.','unavailable')
        item=self.get(db,a['id'],'newsletter');require(bool(item['data'].get('blocks') or item['data'].get('sections')),'Newsletter content required.')
        require(a.get('expected_revision')==item['revision'],'Newsletter changed.','conflict')
        if tool=='newsletter_schedule':require(a['due']>now(),'Schedule must be in the future.')
        payload={'id':item['id'],'revision':item['revision'],'test':tool=='newsletter_send_test'}
        if not payload['test']:
            audience=self.newsletter_audience(db,a)
            require(self.store.digest(canonical(audience))==a.get('_audience_fingerprint'),'Newsletter audience changed after approval. Preview a new send plan.','conflict')
            payload['audience_ids']=[row['id'] for row in audience]
        if payload['test']:
            allowed=os.environ.get('MENCLAVE_TEST_RECIPIENTS','').split(',');require(a.get('email') in allowed,'Test recipient must be owner-allowlisted.');payload['email']=a['email']
        return self.enqueue(db,'newsletter',payload,a.get('due'))
    def backups(self,db,tool,a,p):
        if tool=='backups_list':return {'items':[{'id':path.stem,'bytes':path.stat().st_size} for path in sorted(self.backup_dir.glob('*.sqlite3'))[:100]]}
        if tool=='backups_create':
            # SQLite backup needs a separate read connection rather than the active write transaction.
            id=ident();path=self.backup_dir/(id+'.sqlite3')
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            with sqlite3.connect(self.store.path) as source,sqlite3.connect(path) as target:source.backup(target)
            return {'id':id,'status':'created'}
        require(re.fullmatch(r'[A-Za-z0-9_-]{10,60}',a.get('id','')) is not None,'Invalid backup ID.')
        path=self.backup_dir/(a['id']+'.sqlite3');require(path.is_file(),'Backup unavailable.','not_found')
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as backup:
            integrity=backup.execute('PRAGMA quick_check').fetchone()[0]
            version=backup.execute('PRAGMA user_version').fetchone()[0]
        if tool=='backups_verify':return {'integrity':integrity,'schema_version':version}
        require(integrity=='ok','Backup integrity failed.')
        if tool=='backups_plan_restore':return {'backup_id':a['id'],'requires_maintenance':True,'note':'Restore is an offline operator job; stop writes and run server.manage restore.'}
        id=ident()
        db.execute('INSERT INTO jobs(id,kind,payload,state,due,created,updated) VALUES(?,?,?,?,?,?,?)',(id,'restore',canonical({'backup_id':a['id']}),'waiting_maintenance',now(),now(),now()))
        return {'job_id':id,'state':'waiting_maintenance','next_step':'Stop the app and run python -m server.manage restore --job-id '+id+' --maintenance. Restoring revokes assistant tokens and owner sessions.'}
