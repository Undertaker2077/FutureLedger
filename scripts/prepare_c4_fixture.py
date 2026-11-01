"""Build the ignored read-only SQLite fixture from verified published inputs."""
import csv
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'

def source_rows():
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        actual=hashlib.sha256((DATA/name).read_bytes()).hexdigest()
        if actual!=digest:
            raise RuntimeError(f'Published input hash mismatch: {name}')
    accounts=json.loads((DATA/'accounts.json').read_text(encoding='utf-8'))
    with (DATA/'transactions.csv').open(encoding='utf-8',newline='') as f:
        transactions=list(csv.DictReader(f))
    if len(transactions)!=manifest['row_count']:
        raise RuntimeError('Transaction row count does not match manifest')
    return manifest,accounts,transactions

def valid_db(path,expected_rows):
    if not path.is_file() or path.stat().st_size==0:return False
    try:
        with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)) as db:
            names={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
            return {'accounts','transactions'}<=names and db.execute('select count(*) from transactions').fetchone()[0]==expected_rows
    except sqlite3.Error:return False

def main():
    target=DATA/'benchmark.sqlite'
    manifest,accounts,rows=source_rows()
    if valid_db(target,manifest['row_count']):
        print('Using verified ignored SQLite fixture')
        return
    fd,temp_name=tempfile.mkstemp(prefix='benchmark-',suffix='.sqlite',dir=DATA)
    os.close(fd); temp=Path(temp_name)
    try:
        with closing(sqlite3.connect(temp)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('CREATE TABLE accounts(id TEXT PRIMARY KEY,user_id TEXT,opening_balance_cents INTEGER,balance_cents INTEGER)')
            db.executemany('INSERT INTO accounts VALUES(:id,:user_id,:opening_balance_cents,:balance_cents)',accounts)
            columns=list(rows[0]); types={k:('INTEGER' if k=='amount_cents' else 'TEXT') for k in columns}
            db.execute('CREATE TABLE transactions('+','.join(k+' '+types[k] for k in columns)+',PRIMARY KEY(id),UNIQUE(account_id,external_id),FOREIGN KEY(account_id) REFERENCES accounts(id))')
            for row in rows:row['amount_cents']=int(row['amount_cents'])
            db.executemany('INSERT INTO transactions VALUES('+','.join(':'+k for k in columns)+')',rows)
            db.execute('CREATE INDEX idx_scope_date ON transactions(user_id,posted_at)')
            if db.execute('select count(*) from transactions').fetchone()[0]!=manifest['row_count']:
                raise RuntimeError('SQLite row count validation failed')
            db.commit()
        os.replace(temp,target)
    finally:
        if temp.exists():temp.unlink()
    print(f'Prepared ignored SQLite fixture from manifest-verified inputs ({manifest["row_count"]} rows)')

if __name__=='__main__':main()
