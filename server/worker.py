"""Durable publisher, newsletter outbox and webhook dispatcher. No ambiguous SMTP retries."""
import argparse
import json
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from server.services import now,ident,canonical

def run_once(platform):
    store=platform.store
    # Exactly one claimant changes queued->processing under a SQLite write lock.
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        schedules=db.execute("SELECT * FROM entities WHERE kind='schedule' AND status!='archived'").fetchall()
        for row in schedules:
            data=json.loads(row['data'])
            if data.get('enabled',True) and data.get('due',0)<=now():
                platform.enqueue(db,data['kind'],{'id':data['content_id'],'revision':data['content_revision'],'test':False,'audience_ids':data.get('audience_ids',[])},data['due'])
                data['due']=now()+data['every_seconds']
                db.execute('UPDATE entities SET data=?,revision=revision+1,updated=? WHERE id=?',(canonical(data),now(),row['id']))
        row=db.execute("SELECT * FROM jobs WHERE state='queued' AND due<=? ORDER BY due,id LIMIT 1",(now(),)).fetchone()
        if row:db.execute("UPDATE jobs SET state='processing',updated=? WHERE id=?",(now(),row['id']))
    if row:
        try:
            payload=json.loads(row['payload'])
            if row['kind']=='publish':
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE');item=platform.get(db,payload['id'])
                    if item['status']!='scheduled' or item['revision']!=payload['revision']:raise ValueError('Scheduled content changed; review is needed.')
                    platform.save(db,'scheduler',item['kind'],item['data'],item['id'],item['revision'],'published')
                    platform.audit(db,'scheduler','content_publish',item['id'])
                result={'published':True}
            elif row['kind']=='newsletter':result=send_newsletter(platform,row['id'],payload)
            elif row['kind']=='optin':result=send_optin(platform,payload)
            elif row['kind']=='pxxl':
                from server.providers import pxxl_operation
                if payload.get('project_id')!=os.environ.get('MENCLAVE_PXXL_PROJECT_ID'):raise ValueError('Provider project changed.')
                result=pxxl_operation(payload['tool'],payload['args'])
            else:raise ValueError('Unsupported job.')
            state='completed'
        except Exception:
            # Do not disclose recipient addresses or provider secrets in logs/results.
            result={'error':'Delivery or publishing failed. Review configuration and delivery state before retrying.'};state='needs_review'
        with store.connect() as db:
            db.execute('UPDATE jobs SET state=?,result=?,updated=? WHERE id=?',(state,canonical(result),now(),row['id']))
            if row['kind']=='optin':db.execute("UPDATE jobs SET payload='{}' WHERE id=?",(row['id'],))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        event=db.execute("SELECT * FROM webhook_deliveries WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
        if event:db.execute("UPDATE webhook_deliveries SET state='sending' WHERE id=?",(event['id'],))
    if event:
        state='sent'
        try:
            from server.providers import deliver_webhook
            event_payload=json.loads(event['payload'])
            with store.connect() as db:hook=platform.get(db,event['event'],'webhook')['data']
            if not hook.get('enabled',True):state='cancelled'
            else:deliver_webhook(hook,event_payload)
        except Exception:state='needs_review'
        with store.connect() as db:db.execute('UPDATE webhook_deliveries SET state=? WHERE id=?',(state,event['id']))
    return bool(row or event)

def send_newsletter(platform,job_id,payload):
    store=platform.store
    host=os.environ.get('MENCLAVE_SMTP_HOST');sender=os.environ.get('MENCLAVE_SMTP_FROM');base=os.environ.get('ENCLAVE_ORIGIN','').rstrip('/')
    if not host or not sender or not base.startswith('https://'):raise ValueError('SMTP sender and HTTPS origin required.')
    with store.connect() as db:
        item=platform.get(db,payload['id'],'newsletter')
        if item['revision']!=payload['revision']:raise ValueError('Newsletter changed after approval.')
        if payload.get('test'):
            recipients=[payload['email']]
            if payload['email'] not in os.environ.get('MENCLAVE_TEST_RECIPIENTS','').split(','):raise ValueError('Test recipient not allowed.')
        else:
            allowed=set(payload.get('audience_ids',[]))
            recipients=[r['email'] for r in db.execute('SELECT id,email FROM audience WHERE consent=1 AND suppressed=0').fetchall() if r['id'] in allowed]
        for email in recipients:db.execute('INSERT OR IGNORE INTO job_deliveries VALUES(?,?,?,?)',(job_id,email,'queued',now()))
    with smtplib.SMTP_SSL(host,int(os.environ.get('MENCLAVE_SMTP_PORT','465')),timeout=15,context=ssl.create_default_context()) as smtp:
        if os.environ.get('MENCLAVE_SMTP_USER'):smtp.login(os.environ['MENCLAVE_SMTP_USER'],os.environ.get('MENCLAVE_SMTP_PASSWORD',''))
        for email in recipients:
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                subscriber=db.execute('SELECT * FROM audience WHERE email=?',(email,)).fetchone()
                if not payload.get('test') and (not subscriber or not subscriber['consent'] or subscriber['suppressed']):
                    db.execute("UPDATE job_deliveries SET state='suppressed',updated=? WHERE job=? AND recipient=? AND state='queued'",(now(),job_id,email));continue
                changed=db.execute("UPDATE job_deliveries SET state='sending',updated=? WHERE job=? AND recipient=? AND state='queued'",(now(),job_id,email)).rowcount
            if not changed:continue
            message=EmailMessage();message['From']=sender;message['To']=email;message['Subject']=('[TEST] ' if payload.get('test') else '')+item['data']['title'];message['Message-ID']='<'+store.digest(job_id+':'+email)+'@'+base.split('://')[1]+'>'
            body='\n\n'.join(section.get('heading','')+'\n'+section.get('body','') for section in item['data'].get('sections',[]))
            if subscriber:
                link=base+'/unsubscribe/'+subscriber['id']+'/'+store.digest('unsubscribe:'+subscriber['id'])
                body+='\n\nUnsubscribe: '+link;message['List-Unsubscribe']='<'+link+'>';message['List-Unsubscribe-Post']='List-Unsubscribe=One-Click'
            message.set_content(body)
            try:smtp.send_message(message)
            except Exception:
                with store.connect() as db:db.execute("UPDATE job_deliveries SET state='unknown',updated=? WHERE job=? AND recipient=?",(now(),job_id,email))
                raise
            with store.connect() as db:db.execute("UPDATE job_deliveries SET state='sent',updated=? WHERE job=? AND recipient=?",(now(),job_id,email))
    with store.connect() as db:return {'deliveries':{r['state']:r['count'] for r in db.execute('SELECT state,count(*) count FROM job_deliveries WHERE job=? GROUP BY state',(job_id,)).fetchall()}}

def send_optin(platform,payload):
    store=platform.store;id=payload['audience'];token=payload['token']
    with store.connect() as db:
        row=db.execute('SELECT * FROM audience WHERE id=?',(id,)).fetchone()
        if not row or row['suppressed'] or row['consent']:return {'skipped':True}
        email=row['email']
    base=os.environ['ENCLAVE_ORIGIN'].rstrip('/')
    message=EmailMessage();message['From']=os.environ['MENCLAVE_SMTP_FROM'];message['To']=email;message['Subject']='Confirm your Menclave letter subscription'
    message.set_content('Confirm your subscription by opening this page and pressing Confirm: '+base+'/newsletter/confirm/'+token+'\nIf you did not request this, ignore this message.')
    with smtplib.SMTP_SSL(os.environ['MENCLAVE_SMTP_HOST'],int(os.environ.get('MENCLAVE_SMTP_PORT','465')),timeout=15,context=ssl.create_default_context()) as smtp:
        if os.environ.get('MENCLAVE_SMTP_USER'):smtp.login(os.environ['MENCLAVE_SMTP_USER'],os.environ.get('MENCLAVE_SMTP_PASSWORD',''))
        smtp.send_message(message)
    return {'confirmation_sent':True}

def recover(platform):
    with platform.store.connect() as db:
        db.execute("UPDATE jobs SET state='needs_review' WHERE state='processing'")
        db.execute("UPDATE job_deliveries SET state='unknown' WHERE state='sending'")
        db.execute("UPDATE webhook_deliveries SET state='needs_review' WHERE state='sending'")

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    from server.web import create_app
    platform=create_app().extensions['platform']
    import fcntl
    from pathlib import Path
    lock=open(Path(platform.store.path).parent/'worker.lock','a+')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Another Menclave worker is already running.')
    recover(platform)
    while True:
        run_once(platform)
        if args.once:break
        time.sleep(15)
if __name__=='__main__':main()
