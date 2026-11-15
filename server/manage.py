"""Database maintenance. Run python -m server.manage COMMAND."""
import argparse
import os
import sqlite3
from pathlib import Path
from server.app import Store, ROOT

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['migrate','check','backup'])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    path=Path(os.environ.get('ENCLAVE_DB',str(ROOT / '.local' / 'enclave.sqlite3')))
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    store=Store(path)
    os.chmod(path,0o600)
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
