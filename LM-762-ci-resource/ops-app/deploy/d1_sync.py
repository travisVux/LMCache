"""Keep a Cloudflare D1 copy of the live ops.db in sync, as atomic snapshots. Python stdlib only.

  python -X utf8 d1_sync.py init                 # once: create the D1 database (name OPS_D1_NAME) and print its id
  python -X utf8 d1_sync.py bind                 # once: bind it to the Pages project as RD_DB (checks nothing else changed)
  python -X utf8 d1_sync.py push [--db FILE] [--label NAME] [--data-build HASH] [--errors JSON]
                                                 # default: releases/CURRENT/ops.db, label = release name
  python -X utf8 d1_sync.py verify [--db FILE]   # every table: row count + content hash, local vs the D1 snapshot
  python -X utf8 d1_sync.py status               # current snapshot + the last pushes
  python -X utf8 d1_sync.py rollback [--to N]    # point readers back to an older snapshot (kept: OPS_D1_KEEP, default 7)
  --target sqlite:<file>   instead of D1: same algorithm against a local SQLite file (tests, a local mirror)

Settings (deploy/ops-app.env): CLOUDFLARE_API_TOKEN (needs "D1: Edit"), CLOUDFLARE_ACCOUNT_ID, OPS_D1_DB (database id,
printed by init), OPS_D1_NAME (default release-desk), OPS_D1_KEEP.

How the copy stays consistent (no multi-statement transaction needed):
  * every ops.db table t is stored in D1 as h_t with 4 extra columns: _k (primary key as JSON), _h (row hash),
    _from / _to (sync numbers: the row is part of snapshot S when _from <= S and (_to IS NULL or _to > S));
  * a view named t (same name and columns as in ops.db) shows the CURRENT snapshot, so every query and view of ops.db
    (v_release_cycle, ...) runs unchanged on D1;
  * a push of snapshot S writes only what changed: rows that changed or went away get _to = S, new versions get
    _from = S. Readers do not see any of it while rd_meta.current is S-1;
  * the switch is ONE statement (UPDATE rd_meta SET v = S WHERE k = 'current'): atomic by itself;
  * a push that stopped half way leaves rows with _from > current / _to > current: the next push removes / reopens
    them first, so they never become visible;
  * a lock row in rd_meta (expires after 30 min) keeps two pushes apart; old versions are dropped after OPS_D1_KEEP
    snapshots, which is also how far rollback can go.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
RELEASES = APP / "releases"
LOGS = APP / "logs"
SKIP_TABLES = {"sync_run"}            # local bookkeeping; D1 keeps its own rd_sync
MAX_SQL = 90_000                      # D1: a statement is at most 100 kB
LOCK_S = 1800
TIME_COLS = ("day", "at", "created_at", "started_at", "tagged_at", "published_at", "merged_at", "finished_at", "collected_at")
META_DDL = [
    "CREATE TABLE IF NOT EXISTS rd_meta(k TEXT PRIMARY KEY, v INTEGER, s TEXT)",
    "INSERT OR IGNORE INTO rd_meta(k, v, s) VALUES ('current', 0, NULL)",
    "INSERT OR IGNORE INTO rd_meta(k, v, s) VALUES ('lock', 0, NULL)",
    "CREATE TABLE IF NOT EXISTS rd_sync(sync_id INTEGER PRIMARY KEY, label TEXT, data_build TEXT, source_ref TEXT, "
    "started_at TEXT, switched_at TEXT, status TEXT, partial_errors TEXT, rows_in INTEGER, rows_out INTEGER, tables TEXT)",
]


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_env():
    f = HERE / "ops-app.env"
    if f.is_file():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            t = line.strip()
            if t and not t.startswith("#") and "=" in t:
                k, v = t.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def qi(name):
    return '"' + name.replace('"', '""') + '"'


def lit(v):
    """SQL literal (bulk statements are too large for D1's 100 bound parameters)."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return "NULL" if math.isnan(v) or math.isinf(v) else repr(v)
    if isinstance(v, bytes):
        return "X'" + v.hex() + "'"
    return "'" + str(v).replace("'", "''").replace("\x00", "") + "'"


# ───────────── targets ─────────────
class SqliteTarget:
    """A local SQLite file with the same schema as the D1 copy (tests, local mirror)."""

    def __init__(self, path):
        self.name = f"sqlite:{path}"
        self.con = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.calls = 0

    def q(self, sql, params=()):
        self.calls += 1
        cur = self.con.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        return rows, cur.rowcount if cur.rowcount is not None else 0


class D1Target:
    """Cloudflare D1 over the REST API, one statement per call."""

    def __init__(self, account, db, token):
        self.name = f"d1:{db[:8]}…"
        self.url = f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{db}/query"
        self.token = token
        self.calls = 0

    def q(self, sql, params=()):
        body = json.dumps({"sql": sql, "params": list(params)}).encode("utf-8")
        for i in range(5):
            self.calls += 1
            req = urllib.request.Request(self.url, data=body, method="POST",
                                         headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    j = json.loads(r.read().decode("utf-8"))
                res = (j.get("result") or [{}])[0]
                return res.get("results") or [], (res.get("meta") or {}).get("changes", 0)
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")[:300]
                if e.code in (429, 500, 502, 503, 504) and i < 4:
                    time.sleep(2 * (i + 1))
                    continue
                raise RuntimeError(f"D1 HTTP {e.code}: {msg}") from None
            except urllib.error.URLError as e:
                if i < 4:
                    time.sleep(2 * (i + 1))
                    continue
                raise RuntimeError(f"D1 unreachable: {e.reason}") from None


def cf_api(method, path, body=None):
    acc, tok = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
    req = urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{acc}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Cloudflare API {method} {path.split('?')[0]}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}") from None


def target(spec):
    if spec and spec.startswith("sqlite:"):
        return SqliteTarget(spec[7:])
    for k in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "OPS_D1_DB"):
        if not os.environ.get(k):
            sys.exit(f"{k} is not set (deploy/ops-app.env). Run  d1_sync.py init  first, or pass --target sqlite:<file>")
    return D1Target(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["OPS_D1_DB"], os.environ["CLOUDFLARE_API_TOKEN"])


# ───────────── local side ─────────────
def local_db(path):
    if path:
        return Path(path)
    cur = (RELEASES / "CURRENT").read_text(encoding="utf-8").strip()
    return RELEASES / cur / "ops.db"


def local_schema(con):
    """{table: {"cols": [(name, type)], "pk": [names]}} and the views' SQL, in creation order."""
    tabs = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        if t in SKIP_TABLES or t.startswith(("rd_", "h_")):
            continue
        info = con.execute(f"PRAGMA table_info({qi(t)})").fetchall()
        pk = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]]
        tabs[t] = {"cols": [[r[1], r[2] or ""] for r in info], "pk": pk or [r[1] for r in info]}
    views = [(n, s) for n, s in con.execute("SELECT name, sql FROM sqlite_master WHERE type='view' ORDER BY rowid")]
    return tabs, views


# Bookkeeping columns: re-stamped by every ingest although the data did not change (review 2026-11-27: one offline
# rebuild re-wrote 6,514 of 6,940 bk_build rows only because snapshot_id moved). They are copied when a row changes
# for another reason, but a change in them alone is not a change.
VOLATILE = {"snapshot_id", "last_seen", "ingested_at", "updated_at"}
HASH_V = "2"   # bump when the hash definition changes (the next push re-hashes stored rows once, rewrites none)


def norm(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def row_hash(vals, mask=()):
    vals = [None if i in mask else norm(v) for i, v in enumerate(vals)]
    return hashlib.sha1(json.dumps(vals, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()[:20]


def mask_of(cols):
    return {i for i, c in enumerate(cols) if c in VOLATILE}


def local_rows(con, t, spec):
    cols = [c for c, _ in spec["cols"]]
    idx = [cols.index(p) for p in spec["pk"]]
    mask = mask_of(cols)
    out = {}
    for r in con.execute(f"SELECT {', '.join(qi(c) for c in cols)} FROM {qi(t)}"):
        vals = list(r)
        out[json.dumps([vals[i] for i in idx], ensure_ascii=False, default=str, separators=(",", ":"))] = (row_hash(vals, mask), vals)
    return out


def table_hash(rows):
    h = hashlib.sha1()
    for k in sorted(rows):
        h.update(k.encode("utf-8") + b"\0" + rows[k][0].encode() + b"\0")
    return h.hexdigest()[:20]


# ───────────── remote side ─────────────
def exposed_meta(src, tabs, views):
    """{name: {kind, cols, pk, time}}: the same metadata backend/dbapi.exposed() gives on the release PC."""
    out = {}
    for t, spec in tabs.items():
        cols = [c for c, _ in spec["cols"]]
        out[t] = {"kind": "table", "cols": cols, "pk": spec["pk"], "time": next((c for c in TIME_COLS if c in cols), None)}
    for n, _ in views:
        cols = [r[1] for r in src.execute(f"PRAGMA table_info({qi(n)})")]
        out[n] = {"kind": "view", "cols": cols, "pk": [], "time": next((c for c in TIME_COLS if c in cols), None)}
    return dict(sorted(out.items()))


def ensure_schema(tg, tabs, views, expo=None):
    for s in META_DDL:
        tg.q(s)
    known = {r["k"][7:]: json.loads(r["s"]) for r in tg.q("SELECT k, s FROM rd_meta WHERE k LIKE 'schema:%'")[0]}
    if not tg.q("SELECT 1 AS x FROM rd_meta WHERE k='idx_v2'")[0]:   # once: drop the _from index of older copies
        for t in known:
            tg.q(f"DROP INDEX IF EXISTS {qi('h_' + t + '_from')}")
        tg.q("INSERT OR REPLACE INTO rd_meta(k, v, s) VALUES ('idx_v2', 1, NULL)")
    changed_views = False
    for t, spec in tabs.items():
        h = "h_" + t
        cols = spec["cols"]
        if t not in known:
            tg.q(f"CREATE TABLE IF NOT EXISTS {qi(h)} (_k TEXT NOT NULL, _h TEXT NOT NULL, _from INTEGER NOT NULL, _to INTEGER, "
                 + ", ".join(f"{qi(c)} {typ}".strip() for c, typ in cols) + ")")
            tg.q(f"CREATE INDEX IF NOT EXISTS {qi(h + '_cur')} ON {qi(h)}(_to, _k)")
        else:
            have = {c for c, _ in known[t]["cols"]}
            for c, typ in cols:
                if c not in have:
                    tg.q(f"ALTER TABLE {qi(h)} ADD COLUMN {qi(c)} {typ}".strip())
        if known.get(t) != spec:
            changed_views = True
            tg.q("INSERT OR REPLACE INTO rd_meta(k, v, s) VALUES (?, NULL, ?)", ("schema:" + t, json.dumps(spec)))
    if expo is not None:
        want = json.dumps(expo, separators=(",", ":"))
        have = tg.q("SELECT s FROM rd_meta WHERE k='exposed'")[0]
        if not have or have[0]["s"] != want:
            tg.q("INSERT OR REPLACE INTO rd_meta(k, v, s) VALUES ('exposed', NULL, ?)", (want,))
    want_views = json.dumps([v for v in views])
    have_views = tg.q("SELECT s FROM rd_meta WHERE k='views'")[0]
    if changed_views or not have_views or have_views[0]["s"] != want_views:
        for n, _ in reversed(views):
            tg.q(f"DROP VIEW IF EXISTS {qi(n)}")
        for t, spec in tabs.items():   # the current snapshot under the ops.db table name
            tg.q(f"DROP VIEW IF EXISTS {qi(t)}")
            cur = "(SELECT v FROM rd_meta WHERE k='current')"
            tg.q(f"CREATE VIEW {qi(t)} AS SELECT {', '.join(qi(c) for c, _ in spec['cols'])} FROM {qi('h_' + t)} "
                 f"WHERE _from <= {cur} AND (_to IS NULL OR _to > {cur})")
        for n, sql in views:           # the ops.db views, unchanged, on top of those
            tg.q(sql)
        tg.q("INSERT OR REPLACE INTO rd_meta(k, v, s) VALUES ('views', NULL, ?)", (want_views,))


def meta(tg):
    m = {r["k"]: r for r in tg.q("SELECT k, v, s FROM rd_meta")[0]}
    return m


def lock(tg, who):
    """Take the lock row; -> owner string. A lock older than LOCK_S is taken over (a push that died)."""
    t = int(time.time())
    who = f"{who} #{os.getpid()}-{t}"
    _, n = tg.q("UPDATE rd_meta SET v=?, s=? WHERE k='lock' AND (v IS NULL OR v < ?)", (t + LOCK_S, who, t))
    if not n:
        r = tg.q("SELECT v, s FROM rd_meta WHERE k='lock'")[0][0]
        sys.exit(f"another push holds the lock ({r['s']}, until {dt.datetime.fromtimestamp(r['v'], dt.timezone.utc):%H:%M} UTC)")
    return who


def renew(tg, who):
    tg.q("UPDATE rd_meta SET v=? WHERE k='lock' AND s=?", (int(time.time()) + LOCK_S, who))


def unlock(tg, who):
    tg.q("UPDATE rd_meta SET v=0, s=NULL WHERE k='lock' AND s=?", (who,))   # never frees someone else's lock


def chunks(head, items, tail=""):
    """Yield statements head + items joined by ',' + tail, each under MAX_SQL bytes."""
    buf, size = [], len(head) + len(tail)
    for it in items:
        if buf and size + len(it) + 1 > MAX_SQL:
            yield head + ",".join(buf) + tail
            buf, size = [], len(head) + len(tail)
        buf.append(it)
        size += len(it.encode("utf-8")) + 1
    if buf:
        yield head + ",".join(buf) + tail


# ───────────── commands ─────────────
def push(tg, db, label, data_build=None, errors=None, keep=7, log=print, as_of=None):
    src = sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True)
    tabs, views = local_schema(src)
    for st in META_DDL:   # the lock row must exist before the lock is taken
        tg.q(st)
    if not tg.q("SELECT 1 AS x FROM rd_meta WHERE k='rd_sync_v2'")[0]:   # once: the snapshot's as_of time
        try:
            tg.q("ALTER TABLE rd_sync ADD COLUMN as_of TEXT")
        except Exception as e:  # noqa: BLE001  (already there)
            if "duplicate" not in str(e).lower():
                raise
        tg.q("INSERT OR REPLACE INTO rd_meta(k, v, s) VALUES ('rd_sync_v2', 1, NULL)")
    me = lock(tg, f"{label} {now()}")
    try:
        ensure_schema(tg, tabs, views, exposed_meta(src, tabs, views))   # under the lock: two pushes never rebuild views at the same time
        m = meta(tg)
        cur = int(m["current"]["v"] or 0)
        S = max(cur, int((tg.q("SELECT MAX(sync_id) AS n FROM rd_sync")[0][0] or {}).get("n") or 0)) + 1
        last = tg.q("SELECT status FROM rd_sync ORDER BY sync_id DESC LIMIT 1")[0]
        dirty = not last or last[0]["status"] != "switched"
        run = os.environ.get("RD_RUN_ID", "")   # the local sync_run id: joins a web answer to the run log
        tg.q("INSERT OR REPLACE INTO rd_sync(sync_id, label, data_build, source_ref, started_at, status, partial_errors) "
             "VALUES (?,?,?,?,?,?,?)", (S, label, data_build, f"run:{run}" if run.isdigit() else None, now(), "writing",
                                        json.dumps(errors or [])))
        rows_in = rows_out = 0
        changed = []
        for t, spec in tabs.items():
            h = "h_" + t
            rows = local_rows(src, t, spec)
            th = HASH_V + ":" + table_hash(rows)
            if not dirty and (m.get("th:" + t) or {}).get("s") == th:
                continue
            renew(tg, me)   # only for tables that are written: a long first push keeps its lock
            if dirty:   # a push stopped half way: drop rows it added, reopen rows it closed (none of them is visible)
                tg.q(f"DELETE FROM {qi(h)} WHERE _from > ?", (cur,))
                tg.q(f"UPDATE {qi(h)} SET _to = NULL WHERE _to > ?", (cur,))
            # hash the VALUES D1 holds with today's definition (reads are cheap, writes are the quota): a change of
            # the hash definition or of the volatile columns never rewrites a row
            cl = [c for c, _ in spec["cols"]]
            mk = mask_of(cl)
            remote = {r["_k"]: row_hash([r[c] for c in cl], mk) for r in
                      tg.q(f"SELECT _k, {', '.join(qi(c) for c in cl)} FROM {qi(h)} WHERE _to IS NULL")[0]}
            gone = [k for k in remote if k not in rows or rows[k][0] != remote[k]]
            new = [k for k in rows if remote.get(k) != rows[k][0]]
            for st in chunks(f"UPDATE {qi(h)} SET _to = {S} WHERE _to IS NULL AND _k IN (", [lit(k) for k in gone], ")"):
                tg.q(st)
            cols = ["_k", "_h", "_from"] + [c for c, _ in spec["cols"]]
            head = f"INSERT INTO {qi(h)} ({', '.join(qi(c) for c in cols)}) VALUES "
            for st in chunks(head, ["(" + ",".join([lit(k), lit(rows[k][0]), str(S)] + [lit(v) for v in rows[k][1]]) + ")" for k in new]):
                tg.q(st)
            tg.q("INSERT OR REPLACE INTO rd_meta(k, v, s) VALUES (?, ?, ?)", ("th:" + t, S, th))
            rows_in += len(new)
            rows_out += len([k for k in gone if k not in rows])
            if new or gone:
                changed.append(f"{t}+{len(new)}/-{len(gone)}")
        # the switch: one statement
        tg.q("UPDATE rd_meta SET v = ? WHERE k = 'current'", (S,))
        tg.q("UPDATE rd_sync SET status='switched', switched_at=?, as_of=?, rows_in=?, rows_out=?, tables=? WHERE sync_id=?",
             (now(), as_of or now(), rows_in, rows_out, json.dumps(changed), S))
        old = S - keep
        if old > 0:
            for t in tabs:
                tg.q(f"DELETE FROM {qi('h_' + t)} WHERE _to IS NOT NULL AND _to <= ?", (old,))
            # snapshots <= old are incomplete from now on: rollback must never go there (review 4.2)
            tg.q("INSERT INTO rd_meta(k, v, s) VALUES ('gc_floor', ?, NULL) "
                 "ON CONFLICT(k) DO UPDATE SET v = MAX(COALESCE(v, 0), excluded.v)", (old,))
        log(f"d1 push: snapshot {S} ({label}) is live on {tg.name}: {rows_in} rows written, {rows_out} removed, "
            f"{len(changed)} table(s) changed{': ' + ', '.join(changed[:8]) if changed else ''}; {tg.calls} calls")
        return S
    except BaseException:
        try:
            tg.q("UPDATE rd_sync SET status='failed' WHERE sync_id=(SELECT MAX(sync_id) FROM rd_sync) AND status='writing'")
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        unlock(tg, me)


def verify(tg, db, log=print):
    src = sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True)
    tabs, _ = local_schema(src)
    cur = int(meta(tg)["current"]["v"] or 0)
    bad = []
    for t, spec in tabs.items():
        rows = local_rows(src, t, spec)
        cl = [c for c, _ in spec["cols"]]
        mk = mask_of(cl)
        r = {x["_k"]: row_hash([x[c] for c in cl], mk) for x in
             tg.q(f"SELECT _k, {', '.join(qi(c) for c in cl)} FROM {qi('h_' + t)} WHERE _from <= ? AND (_to IS NULL OR _to > ?)",
                  (cur, cur))[0]}
        n_view = tg.q(f"SELECT COUNT(*) AS n FROM {qi(t)}")[0][0]["n"]
        ok = {k: v[0] for k, v in rows.items()} == r and n_view == len(rows)
        if not ok:
            bad.append(f"{t}: local {len(rows)} rows, D1 {len(r)} (view {n_view})")
    log(f"d1 verify: snapshot {cur}, {len(tabs)} tables, " + ("all equal to the local ops.db" if not bad else f"{len(bad)} differ: " + "; ".join(bad[:6])))
    return not bad


def status(tg):
    m = meta(tg)
    runs = tg.q("SELECT sync_id, label, data_build, started_at, switched_at, status, rows_in, rows_out FROM rd_sync ORDER BY sync_id DESC LIMIT 8")[0]
    return {"current": int(m["current"]["v"] or 0), "runs": runs}


def rollback(tg, to=None, keep=7):
    me = lock(tg, f"rollback {now()}")
    try:
        m = meta(tg)
        cur = int(m["current"]["v"] or 0)
        # rows closed at or before gc_floor were deleted: only snapshots above it are complete. Stored, so a second
        # rollback cannot reach a garbage-collected snapshot (review 4.2)
        floor = int((m.get("gc_floor") or {}).get("v") or 0)
        ok = [r["sync_id"] for r in tg.q("SELECT sync_id FROM rd_sync WHERE status='switched' AND sync_id < ? AND sync_id > ? "
                                         "ORDER BY sync_id DESC", (cur, floor))[0]]
        to = to or (ok[0] if ok else None)
        if not to or to not in ok:
            sys.exit(f"no switched snapshot {to or 'before ' + str(cur)} to go back to (kept: {ok})")
        tg.q("UPDATE rd_meta SET v = ? WHERE k = 'current'", (to,))
        # the snapshots after `to` stay readable as history but the next push treats them as written-over
        tg.q("UPDATE rd_sync SET status='rolled_back' WHERE sync_id > ?", (to,))
        print(f"d1 rollback: readers now see snapshot {to} (was {cur})")
    finally:
        unlock(tg, me)


def init():
    name = os.environ.get("OPS_D1_NAME", "release-desk")
    have = cf_api("GET", f"/d1/database?name={name}").get("result") or []
    db = next((d for d in have if d.get("name") == name), None)
    if not db:
        db = cf_api("POST", "/d1/database", {"name": name})["result"]
        print(f"created D1 database {name}")
    uuid = db.get("uuid") or db.get("id")
    print(f"OPS_D1_DB={uuid}\n-> add that line to deploy/ops-app.env, then bind it to the Pages project as RD_DB "
          f"(d1_sync.py bind, or dashboard: Workers & Pages > project > Settings > Bindings > D1 > RD_DB)")
    return uuid


def bind():
    """Bind the D1 database to the Pages project as RD_DB (production + preview). Sends ONLY d1_databases (Cloudflare
    merges deployment_configs), then reads the project back and checks the other bindings and secrets are still there."""
    proj, dbid = os.environ.get("OPS_PAGES_PROJECT", "").strip(), os.environ.get("OPS_D1_DB", "").strip()
    if not proj or not dbid:
        sys.exit("OPS_PAGES_PROJECT and OPS_D1_DB must be set (deploy/ops-app.env)")
    def names(cfg):
        return {k: sorted((cfg.get(k) or {}).keys()) for k in ("env_vars", "kv_namespaces", "d1_databases")}
    before = cf_api("GET", f"/pages/projects/{proj}")["result"]["deployment_configs"]
    cf_api("PATCH", f"/pages/projects/{proj}", {"deployment_configs": {env: {"d1_databases": {"RD_DB": {"id": dbid}}} for env in ("production", "preview")}})
    after = cf_api("GET", f"/pages/projects/{proj}")["result"]["deployment_configs"]
    for env in ("production", "preview"):
        b, a = names(before.get(env) or {}), names(after.get(env) or {})
        lost = {k: sorted(set(b[k]) - set(a[k])) for k in ("env_vars", "kv_namespaces") if set(b[k]) - set(a[k])}
        print(f"{env}: d1 {a['d1_databases']} · env/secrets {a['env_vars']} · kv {a['kv_namespaces']}" + (f"  LOST {lost}" if lost else ""))
        if lost:
            sys.exit("a binding or secret went missing: set it again in the dashboard (Workers & Pages > project > Settings)")
    print("bound. It is used from the next deployment on (pages.py deploy).")


def main():
    load_env()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["init", "bind", "push", "verify", "status", "rollback"])
    ap.add_argument("--target", help="sqlite:<file> instead of Cloudflare D1")
    ap.add_argument("--db", help="local ops.db (default: releases/CURRENT/ops.db)")
    ap.add_argument("--label", help="snapshot name (default: the CURRENT release name)")
    ap.add_argument("--data-build", help="data/<build> hash of the page published with it")
    ap.add_argument("--errors", help="JSON list of partial errors to record with the snapshot")
    ap.add_argument("--to", type=int)
    a = ap.parse_args()
    if a.cmd == "init":
        init()
        return
    if a.cmd == "bind":
        bind()
        return
    tg = target(a.target)
    if a.cmd == "status":
        print(json.dumps(status(tg), indent=1))
        return
    if a.cmd == "rollback":
        rollback(tg, a.to, int(os.environ.get("OPS_D1_KEEP", "7")))
        return
    db = local_db(a.db)
    if not db.is_file():
        sys.exit(f"no local database {db}")
    if a.cmd == "verify":
        sys.exit(0 if verify(tg, db) else 1)
    label = a.label or (RELEASES / "CURRENT").read_text(encoding="utf-8").strip()
    # the snapshot carries the release's data build and its partial errors (manifest.json, written by check_sync.py),
    # so /api/sync-status answers the same on the release PC and on Cloudflare
    man_f = db.parent / "site" / "data" / "manifest.json"
    man = json.loads(man_f.read_text(encoding="utf-8")) if man_f.is_file() else {}
    build = a.data_build or man.get("build")
    errors = json.loads(a.errors) if a.errors else man.get("partial_errors") or []
    sys.path.insert(0, str(HERE))
    import publish   # the same privacy rules as the web copy: nothing leaves this PC with a hit
    hits = publish.scan_db(db)
    if hits:
        sys.exit(f"privacy scan of {db.name}: {len(hits)} hit(s) - nothing pushed")
    t0 = time.time()
    # as_of = when the release went live on the PC: the same time /api/sync-status and range= use there
    rel = db.parent / "release.json"
    as_of = json.loads(rel.read_text(encoding="utf-8")).get("published_at") if rel.is_file() else None
    S = push(tg, db, label, build, errors, int(os.environ.get("OPS_D1_KEEP", "7")), as_of=as_of)
    LOGS.mkdir(exist_ok=True)
    (LOGS / "last-d1-push.json").write_text(json.dumps(dict(at=now(), sync_id=S, label=label, data_build=build, target=tg.name,
                                                            seconds=round(time.time() - t0, 1))), encoding="utf-8")


if __name__ == "__main__":
    main()
