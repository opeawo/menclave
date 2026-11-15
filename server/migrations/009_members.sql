CREATE TABLE member_accounts(id TEXT PRIMARY KEY,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,created INTEGER NOT NULL,disabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE member_sessions(digest TEXT PRIMARY KEY,account TEXT NOT NULL REFERENCES member_accounts(id),expires INTEGER NOT NULL);
CREATE INDEX member_sessions_account ON member_sessions(account);
CREATE TABLE contact_messages(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL,message TEXT NOT NULL,created INTEGER NOT NULL);
