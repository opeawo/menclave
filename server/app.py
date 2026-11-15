"""Menclave standalone community server. Run from the repository root."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ['Faith & Purpose', 'Relationships & Family', 'Money & Ambition', 'Health & Fitness', 'Style & Living', 'Culture & Society', 'Men’s Stories']

class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            # Migrations run in order under a write lock and never drop existing data.
            for migration in sorted((ROOT / 'server' / 'migrations').glob('*.sql')):
                version = int(migration.name.split('_')[0])
                db.execute('BEGIN IMMEDIATE')
                current = db.execute('PRAGMA user_version').fetchone()[0]
                if current < version:
                    # complete_statement also handles multi-line trigger definitions.
                    statement = ''
                    for line in migration.read_text().splitlines(True):
                        statement += line
                        if sqlite3.complete_statement(statement):
                            db.execute(statement)
                            statement = ''
                    if statement.strip(): raise ValueError('Incomplete migration')
                    db.execute(f'PRAGMA user_version={version}')
                db.commit()
            db.execute('INSERT OR IGNORE INTO config VALUES(?,?)', ('secret', secrets.token_hex(32)))
            self.secret = db.execute("SELECT value FROM config WHERE key='secret'").fetchone()[0].encode()
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()
    def digest(self, value):
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()
    def limited(self, identity, action, maximum, window):
        bucket = f'{self.digest(identity)}:{action}:{int(time.time()) // window}'
        with self.connect() as db:
            db.execute('INSERT INTO limits VALUES(?,1) ON CONFLICT(bucket) DO UPDATE SET count=count+1', (bucket,))
            count = db.execute('SELECT count FROM limits WHERE bucket=?', (bucket,)).fetchone()[0]
            # Expired windows cannot match; periodically bound retained counters.
            if secrets.randbelow(100) == 0:
                db.execute('DELETE FROM limits WHERE rowid NOT IN (SELECT rowid FROM limits ORDER BY rowid DESC LIMIT 10000)')
        return count > maximum
    def abuse_limits(self):
        with self.connect() as db:
            row=db.execute("SELECT data FROM entities WHERE kind='abuse_rules' ORDER BY updated DESC LIMIT 1").fetchone()
        configured=json.loads(row[0]) if row else {}
        return {'session_limit':configured.get('session_limit',10),'network_limit':configured.get('network_limit',30)}
    def public(self, row):
        result={k: row[k] for k in ('id','parent','topic','title','body','created')}
        with self.connect() as db:
            control=db.execute('SELECT staff,locked FROM thread_controls WHERE post=?',(row['id'],)).fetchone()
            result.update(staff=bool(control['staff']) if control else False,locked=bool(control['locked']) if control else False)
        return result
    def listing(self, query='', topic=''):
        with self.connect() as db:
            rows = db.execute("SELECT p.*, (SELECT count(*) FROM posts r WHERE r.parent=p.id AND r.status='approved') replies FROM posts p WHERE p.parent IS NULL AND p.status='approved' AND (?='' OR p.topic=?) AND (?='' OR instr(lower(p.title || ' ' || p.body),lower(?))>0) ORDER BY p.created DESC,p.id LIMIT 100", (topic,topic,query,query)).fetchall()
            return [dict(self.public(r), replies=r['replies']) for r in rows]
    def thread(self, post_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM posts WHERE id=? AND parent IS NULL AND status='approved'", (post_id,)).fetchone()
            if not row: return None
            replies = db.execute("SELECT * FROM posts WHERE parent=? AND status='approved' ORDER BY created,id LIMIT 200", (post_id,)).fetchall()
            return dict(self.public(row), replies=[self.public(r) for r in replies])
    def submit(self, data, owner):
        parent = data.get('parent')
        body = data.get('body', '')
        title = data.get('title', '')
        topic = data.get('topic', '')
        if not isinstance(body,str) or not 20 <= len(body.strip()) <= 5000: raise ValueError('Write between 20 and 5,000 characters.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if parent:
                if not isinstance(parent,str): raise ValueError('Invalid conversation.')
                row = db.execute("SELECT topic FROM posts WHERE id=? AND parent IS NULL AND status='approved'", (parent,)).fetchone()
                if not row: raise ValueError('This conversation is unavailable.')
                control=db.execute('SELECT locked FROM thread_controls WHERE post=?',(parent,)).fetchone()
                if control and control['locked']:raise ValueError('This conversation is locked.')
                title, topic = '', row['topic']
            elif not isinstance(title,str) or not 10 <= len(title.strip()) <= 160 or topic not in TOPICS:
                raise ValueError('Choose a topic and write a title between 10 and 160 characters.')
            post_id = secrets.token_urlsafe(16)
            db.execute('INSERT INTO posts VALUES(?,?,?,?,?,?,?,?)', (post_id,parent or None,topic,title.strip(),body.strip(),owner,'pending',int(time.time())))
            return post_id
    def report(self, data, owner):
        reason = data.get('reason')
        if reason not in ['Identifying information','Harassment or hate','Spam or promotion','Harmful content','Other concern']: raise ValueError('Choose a report reason.')
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM posts WHERE id=? AND status='approved'", (data.get('post'),)).fetchone(): raise ValueError('Post unavailable.')
            db.execute('INSERT OR IGNORE INTO reports(id,post,reason,reporter,created) VALUES(?,?,?,?,?)', (secrets.token_urlsafe(16),data['post'],reason,owner,int(time.time())))
    def queue(self):
        with self.connect() as db:
            pending = db.execute("SELECT * FROM posts WHERE status='pending' ORDER BY created LIMIT 100").fetchall()
            reports = db.execute("SELECT r.id,r.post,r.reason,r.created,p.title,p.body FROM reports r JOIN posts p ON p.id=r.post WHERE resolved=0 ORDER BY r.created LIMIT 100").fetchall()
            return {'pending':[self.public(r) for r in pending], 'reports':[dict(r) for r in reports]}
    def moderate(self, data, actor='moderator'):
        action = data.get('action')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if action not in ['approve','remove','dismiss']: raise ValueError('Invalid moderation action.')
            db.execute('INSERT INTO moderation_audit VALUES(?,?,?,?,?)', (secrets.token_urlsafe(16),str(data.get('id','')),action,actor,int(time.time())))
            if action == 'dismiss':
                if not db.execute('UPDATE reports SET resolved=1 WHERE id=?', (data.get('id'),)).rowcount: raise ValueError('Report unavailable.')
                return
            if action not in ['approve','remove']: raise ValueError('Invalid moderation action.')
            row = db.execute('SELECT * FROM posts WHERE id=?', (data.get('id'),)).fetchone()
            if not row: raise ValueError('Post unavailable.')
            if action == 'approve' and row['parent'] and not db.execute("SELECT 1 FROM posts WHERE id=? AND status='approved'", (row['parent'],)).fetchone(): raise ValueError('Parent conversation is unavailable.')
            # Removing content purges its text. Rejected replies cannot resurface later.
            if action == 'remove':
                db.execute("UPDATE posts SET status='removed',title='',body='' WHERE id=? OR parent=?", (row['id'],row['id']))
                db.execute('UPDATE reports SET resolved=1 WHERE post=? OR post IN (SELECT id FROM posts WHERE parent=?)', (row['id'],row['id']))
            else: db.execute("UPDATE posts SET status='approved' WHERE id=? AND status='pending'", (row['id'],))



if __name__ == '__main__':
    import sys
    sys.path.insert(0,str(ROOT))
    from server.web import create_app
    from server.mcp_app import create_asgi
    import uvicorn
    web=create_app()
    uvicorn.run(create_asgi(web,web.extensions['platform']),host=os.environ.get('ENCLAVE_HOST','127.0.0.1'),port=int(os.environ.get('PORT','8000')),access_log=False,log_level='warning')
