"""Lake = raw API payloads, one gzip JSON file per partition, plus a SQLite state table.

  <root>/raw/<source>/<key>.json.gz     payload exactly as the API gave it (secrets stripped by the source)
  <root>/state.db                       one row per (source, key): status, attempts, fetched_at, final, error

Writes are atomic (tmp file + rename): a crash never leaves a half file.
"""
import gzip
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS partition (
  source     TEXT NOT NULL,
  key        TEXT NOT NULL,
  day        TEXT,             -- UTC day the partition belongs to (for window exports)
  status     TEXT NOT NULL,    -- ok | failed | dead (failed max_attempts times)
  attempts   INTEGER NOT NULL DEFAULT 0,
  rows       INTEGER,
  fetched_at TEXT,             -- last successful fetch, UTC
  watermark  TEXT,             -- source-defined 'last changed' time seen at fetch time
  final      INTEGER NOT NULL DEFAULT 0,  -- 1 = settled, never fetched again unless the watermark moves or --refresh
  error      TEXT,
  origin     TEXT,             -- api | legacy:<path>
  PRIMARY KEY (source, key)
);
CREATE INDEX IF NOT EXISTS partition_day ON partition (source, day);
CREATE TABLE IF NOT EXISTS run_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, command TEXT,
  source TEXT, planned INTEGER, fetched INTEGER, skipped INTEGER, failed INTEGER
);
"""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Lake:
    def __init__(self, root):
        self.root = root
        os.makedirs(os.path.join(root, "raw"), exist_ok=True)
        self.db = sqlite3.connect(os.path.join(root, "state.db"), check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    # ---------- payload files
    def path(self, source, key):
        return os.path.join(self.root, "raw", source, key.replace(":", "_") + ".json.gz")

    def write(self, source, key, payload):
        p = self.path(source, key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
        os.replace(tmp, p)

    def read(self, source, key):
        p = self.path(source, key)
        if not os.path.exists(p):
            return None
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)

    # ---------- state
    def get(self, source, key):
        with self.lock:
            r = self.db.execute("SELECT status, attempts, fetched_at, watermark, final FROM partition WHERE source=? AND key=?", (source, key)).fetchone()
        return None if r is None else dict(status=r[0], attempts=r[1], fetched_at=r[2], watermark=r[3], final=bool(r[4]))

    def ok(self, source, key, day, rows, watermark, final, fetched_at=None, origin="api"):
        with self.lock:
            self.db.execute("""INSERT INTO partition (source, key, day, status, attempts, rows, fetched_at, watermark, final, error, origin)
                VALUES (?,?,?,'ok',0,?,?,?,?,NULL,?)
                ON CONFLICT(source, key) DO UPDATE SET day=excluded.day, status='ok', attempts=0, rows=excluded.rows,
                  fetched_at=excluded.fetched_at, watermark=excluded.watermark, final=excluded.final, error=NULL, origin=excluded.origin""",
                            (source, key, day, rows, fetched_at or now(), watermark, int(final), origin))
            self.db.commit()

    def fail(self, source, key, day, err, max_attempts):
        with self.lock:
            r = self.db.execute("SELECT attempts, fetched_at FROM partition WHERE source=? AND key=?", (source, key)).fetchone()
            att = (r[0] if r else 0) + 1
            # a partition that has an older good payload keeps it; the failure is recorded for retry
            st = "dead" if att >= max_attempts else "failed"
            self.db.execute("""INSERT INTO partition (source, key, day, status, attempts, error, origin) VALUES (?,?,?,?,?,?, 'api')
                ON CONFLICT(source, key) DO UPDATE SET status=excluded.status, attempts=excluded.attempts, error=excluded.error""",
                            (source, key, day, st, att, str(err)[:500]))
            self.db.commit()
        return st

    def keys(self, source, since_day=None, until_day=None, status="ok"):
        q, a = "SELECT key, day FROM partition WHERE source=?", [source]
        if status:
            q += " AND status=?"; a.append(status)
        if since_day:
            q += " AND day>=?"; a.append(since_day)
        if until_day:
            q += " AND day<?"; a.append(until_day)
        with self.lock:
            return self.db.execute(q + " ORDER BY day, key", a).fetchall()

    def has_payload(self, source, key):
        return os.path.exists(self.path(source, key))

    def log(self, **kw):
        with self.lock:
            self.db.execute("INSERT INTO run_log (started, finished, command, source, planned, fetched, skipped, failed) VALUES (?,?,?,?,?,?,?,?)",
                            (kw["started"], now(), kw["command"], kw["source"], kw["planned"], kw["fetched"], kw["skipped"], kw["failed"]))
            self.db.commit()

    def summary(self):
        with self.lock:
            return self.db.execute("""SELECT source, status, final, COUNT(*), MIN(day), MAX(day), SUM(rows), MAX(fetched_at)
                FROM partition GROUP BY source, status, final ORDER BY source, status, final""").fetchall()

    def failures(self, source=None, limit=20):
        q, a = "SELECT source, key, status, attempts, error FROM partition WHERE status IN ('failed','dead')", []
        if source:
            q += " AND source=?"; a.append(source)
        with self.lock:
            return self.db.execute(q + " ORDER BY source, key LIMIT ?", a + [limit]).fetchall()
