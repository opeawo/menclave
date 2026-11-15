CREATE INDEX IF NOT EXISTS posts_feed ON posts(status,parent,created DESC,id);
CREATE INDEX IF NOT EXISTS posts_topic ON posts(topic,status,parent,created DESC);
CREATE INDEX IF NOT EXISTS reports_queue ON reports(resolved,created);
CREATE TABLE IF NOT EXISTS moderation_audit(id TEXT PRIMARY KEY, target TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL, created INTEGER NOT NULL);
CREATE TRIGGER IF NOT EXISTS valid_post_insert BEFORE INSERT ON posts WHEN NEW.status NOT IN ('pending','approved','removed') BEGIN SELECT RAISE(ABORT,'Invalid post status'); END;
CREATE TRIGGER IF NOT EXISTS valid_post_update BEFORE UPDATE OF status ON posts WHEN NEW.status NOT IN ('pending','approved','removed') BEGIN SELECT RAISE(ABORT,'Invalid post status'); END;
