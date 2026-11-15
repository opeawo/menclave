CREATE TABLE pending_subscriptions(digest TEXT PRIMARY KEY,audience TEXT NOT NULL REFERENCES audience(id) ON DELETE CASCADE,expires INTEGER NOT NULL);
