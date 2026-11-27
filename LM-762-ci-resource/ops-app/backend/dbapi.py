"""The sync API of the release PC: the same contract as the Cloudflare functions (deploy/pages-functions/functions/api/),
so the page and any client read one shape locally and on the web. Contract (both sides, tests/check_api_contract.py):

  GET /api/sync-status  {source, sync_id, label, last_synced_at, sync_status, partial_errors, data_build, page_build,
                         in_sync, last_attempt, queue, d1, run}
        data_build = the data build of the database this copy answers from; page_build = the page this copy serves;
        in_sync = page_build == data_build; sync_status: synced | partial | syncing | error | unknown
  GET /api/db           {sync, tables: {name: {kind: table|view, cols, pk, time}}}
  GET /api/db/<name>?tag=&branch=&env=&range=7d|24h&since=&until=&<column>=&limit=&offset=
        {sync, name, as_of, filters, n, total, limit, offset, next_offset, rows}
        range counts back from the snapshot's as_of (not from now), so an answer never changes while the snapshot stays
        the same; rows ordered by the time column (newest first) then the primary key; a filter that cannot apply to
        this table is a 400, never silently ignored
  errors                {error: {code, message}, ...}  codes: unknown_table, bad_param, filter_not_applicable,
                         no_snapshot, not_found, server_error

Shared filters: tag -> release_tag|tag, branch -> branch|head_branch|base, env -> device|env|pipeline.
Reads the published release's ops.db read-only: one release = one consistent snapshot. Python stdlib only.
"""
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

SKIP = {"sync_run"}
SHARED = {"tag": ("release_tag", "tag"), "branch": ("branch", "head_branch", "base"), "env": ("device", "env", "pipeline")}
TIME_COLS = ("day", "at", "created_at", "started_at", "tagged_at", "published_at", "merged_at", "finished_at", "collected_at")
RESERVED = {"tag", "branch", "env", "range", "since", "until", "limit", "offset"}
LIMIT_MAX, LIMIT_DEFAULT = 5000, 1000


def qi(n):
    return '"' + n.replace('"', '""') + '"'


def err(code, message, status, **extra):
    return status, {"error": {"code": code, "message": message}, **extra}


def connect_ro(db):
    con = sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def exposed(con):
    """{name: {kind, cols, pk, time}} for every table and view (the same metadata d1_sync.py publishes to D1)."""
    out = {}
    for name, typ in con.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY type, name"):
        if name in SKIP:
            continue
        info = con.execute(f"PRAGMA table_info({qi(name)})").fetchall()
        cols = [r[1] for r in info]
        pk = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]]
        out[name] = {"kind": typ, "cols": cols, "pk": pk, "time": next((c for c in TIME_COLS if c in cols), None)}
    return out


def parse_int(v, default, lo, hi):
    """Same rule as functions/lib/api.js: digits only, else bad_param; clamped to [lo, hi]."""
    if v is None or v == "":
        return default
    if not re.fullmatch(r"\d{1,9}", str(v)):
        raise ValueError(v)
    return min(max(int(v), lo), hi)


def range_start(v, anchor):
    m = re.fullmatch(r"(\d{1,4})([hd])", str(v or ""))
    if not m:
        return None
    d = dt.timedelta(hours=int(m.group(1))) if m.group(2) == "h" else dt.timedelta(days=int(m.group(1)))
    return (anchor - d).strftime("%Y-%m-%dT%H:%M:%SZ")


def as_of(sync):
    t = (sync or {}).get("last_synced_at")
    try:
        return dt.datetime.fromisoformat(str(t).replace("Z", "+00:00")).astimezone(dt.timezone.utc) if t else None
    except ValueError:
        return None


def sync_info(app_dir, site, release):
    """The snapshot the release PC serves. Its database is the release's own ops.db, so data_build = page_build."""
    out = {"source": "release-pc", "sync_id": None, "label": release, "last_synced_at": None, "sync_status": "unknown",
           "partial_errors": [], "data_build": None, "page_build": None, "in_sync": None, "last_attempt": None,
           "queue": None, "d1": None, "run": None}
    man = (site / "data" / "manifest.json") if site else None
    if man and man.is_file():
        try:
            j = json.loads(man.read_text(encoding="utf-8"))
            out["page_build"] = out["data_build"] = j.get("build")
            out["page_made"] = j.get("made")
            out["partial_errors"] = j.get("partial_errors") or []
        except ValueError:
            pass
    out["in_sync"] = bool(out["page_build"]) and out["page_build"] == out["data_build"]
    rel = (site.parent / "release.json") if site else None
    if rel and rel.is_file():
        try:
            out["last_synced_at"] = json.loads(rel.read_text(encoding="utf-8")).get("published_at")
        except ValueError:
            pass
    logs = Path(app_dir) / "logs"
    try:   # the web copy's database: same snapshot as this release?
        d1 = json.loads((logs / "last-d1-push.json").read_text(encoding="utf-8"))
        out["d1"] = dict(d1, same_snapshot=d1.get("label") == release)
        if d1.get("label") == release:
            out["sync_id"] = d1.get("sync_id")
    except (OSError, ValueError):
        pass
    try:
        last = json.loads((logs / "last-refresh.json").read_text(encoding="utf-8-sig"))
        out["run"] = out["last_attempt"] = {k: last.get(k) for k in ("status", "at", "text")}
    except (OSError, ValueError):
        last = None
    st = (last or {}).get("status")
    # same meaning as on Cloudflare: error = the latest attempt to move failed and an older snapshot is served
    out["sync_status"] = ("error" if st == "failed" else "partial" if st == "warn" or out["partial_errors"]
                          else "synced" if out["label"] else "unknown")
    return out


def build_query(info, q, anchor):
    """-> (where, args, applied) or raises KeyError(filter names that cannot apply)."""
    cols, time = info["cols"] or [], info["time"]
    where, args, applied, bad = [], [], {}, []
    for p, cands in SHARED.items():
        v = q.get(p)
        if v in (None, ""):
            continue
        c = next((c for c in cands if c in cols), None)
        if not c:
            bad.append(p)
            continue
        where.append(f"{qi(c)} = ?")
        args.append(v)
        applied[p] = c
    lo = range_start(q.get("range"), anchor or dt.datetime.now(dt.timezone.utc)) if q.get("range") else q.get("since")
    if q.get("range") and not lo:
        raise ValueError("range")
    hi = q.get("until")
    for name, val, op in (("since", lo, ">="), ("until", hi, "<")):
        if not val:
            continue
        if not time:
            bad.append("range" if name == "since" and q.get("range") else name)
            continue
        v = val[:10] if time == "day" else val   # day columns hold YYYY-MM-DD
        where.append(f"{qi(time)} {op} ?")
        args.append(v)
        applied[name] = v
    for k, v in q.items():
        if k in RESERVED:
            continue
        if k not in cols:
            bad.append(k)
            continue
        where.append(f"{qi(k)} = ?")
        args.append(v)
        applied[k] = k
    if bad:
        raise KeyError(bad)
    return where, args, applied


def rows(db, name, query, sync=None):
    """-> (status, body) for GET /api/db/<name>. query: dict of lists (urllib.parse.parse_qs)."""
    con = connect_ro(db)
    try:
        ex = exposed(con)
        if name not in ex:
            return err("unknown_table", f"no table or view '{name}'", 404, tables=sorted(ex))
        info, q = ex[name], {k: v[-1] for k, v in query.items()}
        try:
            limit = parse_int(q.get("limit"), LIMIT_DEFAULT, 1, LIMIT_MAX)
            offset = parse_int(q.get("offset"), 0, 0, 10**9)
        except ValueError as e:
            return err("bad_param", f"limit / offset must be digits (got {e})", 400)
        anchor = as_of(sync)
        try:
            where, args, applied = build_query(info, q, anchor)
        except KeyError as e:
            return err("filter_not_applicable", f"{name} has no column for: {', '.join(e.args[0])}", 400,
                       columns=info["cols"], time=info["time"])
        except ValueError:
            return err("bad_param", "range must look like 24h or 7d", 400)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        order = ([f"{qi(info['time'])} DESC"] if info["time"] else []) + [qi(c) for c in (info["pk"] or info["cols"][:1])]
        total = con.execute(f"SELECT COUNT(*) FROM {qi(name)}{w}", args).fetchone()[0]
        sel = ", ".join(qi(c) for c in info["cols"]) if info["cols"] else "*"
        out = [dict(r) for r in con.execute(f"SELECT {sel} FROM {qi(name)}{w} ORDER BY {', '.join(order)} LIMIT {limit} OFFSET {offset}", args)]
        nxt = offset + len(out) if offset + len(out) < total else None
        # pinned: the release's ops.db never changes, so tables AND views are one snapshot here
        return 200, {"sync": sync, "name": name, "as_of": anchor.strftime("%Y-%m-%dT%H:%M:%SZ") if anchor else None, "pinned": True, "filters": applied,
                     "n": len(out), "total": total, "limit": limit, "offset": offset, "next_offset": nxt, "rows": out}
    finally:
        con.close()


def index(db, sync=None):
    con = connect_ro(db)
    try:
        return {"sync": sync, "tables": exposed(con)}
    finally:
        con.close()
