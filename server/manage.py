"""Database maintenance. Run python -m server.manage COMMAND."""
import argparse
import os
import sqlite3
from pathlib import Path
from server.app import Store, ROOT

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['migrate','check','backup','restore','issue-client','revoke-client'])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--name')
    parser.add_argument('--scopes',nargs='+')
    parser.add_argument('--client-id')
    parser.add_argument('--job-id')
    parser.add_argument('--maintenance',action='store_true')
    args=parser.parse_args()
    path=Path(os.environ.get('ENCLAVE_DB',str(ROOT / '.local' / 'enclave.sqlite3')))
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    store=Store(path)
    os.chmod(path,0o600)
    if args.command in {'issue-client','revoke-client'}:
        from server.services import Platform
        platform=Platform(store)
        if args.command=='issue-client':
            if not args.name or not args.scopes:parser.error('--name and --scopes are required')
            result=platform.issue_client(args.name,args.scopes)
            import json
            print(json.dumps(result))  # Operator-only, one-time secret output; never logged by the server.
        else:
            if not args.client_id:parser.error('--client-id is required')
            with store.connect() as db:db.execute('UPDATE assistant_clients SET revoked=1 WHERE id=?',(args.client_id,));platform.audit(db,'operator','access_revoke_client',args.client_id)
        return
    if args.command=='restore':
        if not args.maintenance or not args.job_id:parser.error('Stop the app first, then pass --maintenance --job-id for an approved restore job')
        import fcntl,json,re
        lock=open(path.parent/'runtime.lock','a+')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Restore refused: Menclave is running. Stop it first.')
        worker_lock=open(path.parent/'worker.lock','a+')
        try:fcntl.flock(worker_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Restore refused: the background worker is running. Stop it first.')
        with store.connect() as db:
            suppression=[row[0] for row in db.execute("SELECT key FROM config WHERE key LIKE 'suppression:%'").fetchall()]
            suppression += ['suppression:'+store.digest(row[0]) for row in db.execute('SELECT email FROM audience WHERE suppressed=1').fetchall()]
        with store.connect() as db:job=db.execute("SELECT * FROM jobs WHERE id=? AND kind='restore' AND state='waiting_maintenance'",(args.job_id,)).fetchone()
        if not job:raise SystemExit('Approved maintenance job unavailable.')
        id=json.loads(job['payload'])['backup_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,60}',id):raise SystemExit('Invalid backup ID.')
        source=Path(os.environ.get('MENCLAVE_DATA_DIR',str(path.parent)))/'backups'/(id+'.sqlite3')
        if not source.is_file():raise SystemExit('Backup unavailable.')
        with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as backup,sqlite3.connect(path) as target:
            if backup.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise SystemExit('Backup integrity check failed.')
            version=backup.execute('PRAGMA user_version').fetchone()[0]
            maximum=max(int(file.name.split('_')[0]) for file in (ROOT/'server'/'migrations').glob('*.sql'))
            if version>maximum:raise SystemExit('Backup schema is newer than this application.')
            backup.backup(target)
        restored=Store(path)
        with restored.connect() as db:
            # Keep the current HMAC key so revocation/suppression digests cannot roll back.
            db.execute("UPDATE config SET value=? WHERE key='secret'",(store.secret.decode(),))
            restored.secret=store.secret
            db.execute('UPDATE assistant_clients SET revoked=1')
            db.execute('UPDATE assistant_tokens SET revoked=1')
            db.execute('DELETE FROM admin_sessions')
            db.execute('DELETE FROM oauth_codes')
            db.execute('DELETE FROM pending_subscriptions')
            db.execute('UPDATE media_uploads SET expires=0')
            db.execute('UPDATE audience SET consent=0')
            for marker in suppression:db.execute('INSERT OR REPLACE INTO config VALUES(?,?)',(marker,'1'))
            for person in db.execute('SELECT id,email FROM audience').fetchall():
                # Re-hash with the restored database key: old-key tombstones are also retained.
                if 'suppression:'+store.digest(person['email']) in suppression:db.execute('UPDATE audience SET suppressed=1 WHERE id=?',(person['id'],))
            db.execute("UPDATE jobs SET state='cancelled' WHERE state IN ('queued','processing','waiting_maintenance')")
            from server.services import Platform
            Platform(restored).audit(db,'operator','backups_restore',id)
        print('Restore completed. All assistant grants, owner sessions and pending jobs were revoked; newsletter consent must be reconfirmed. Restart the app and issue fresh grants.')
        worker_lock.close();lock.close();return
    with store.connect() as db:
        if args.command=='backup':
            if args.output is None:parser.error('backup requires --output')
            # Exclusive creation avoids overwriting an existing backup or the live database.
            fd=os.open(args.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            with sqlite3.connect(args.output) as target:db.backup(target)
            print('Database backup completed. Protect and encrypt this file before offsite storage.')
        elif args.command=='check':
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise SystemExit('Database integrity check failed.')
            if db.execute('PRAGMA foreign_key_check').fetchone():raise SystemExit('Database references check failed.')
            print('Database integrity and references: OK')
        else:print('Database schema version:',db.execute('PRAGMA user_version').fetchone()[0])
if __name__=='__main__':main()
