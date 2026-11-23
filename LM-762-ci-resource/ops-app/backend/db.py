"""SQLite access: open, migrate, upsert, snapshot."""
import datetime as dt
import sqlite3

from config import ARTIFACT_SPECS, DB_PATH, HERE, parse_tag


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(path=DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))
    con.executemany(
        "INSERT INTO artifact_spec(code,channel,package,label,for_rc,for_final,ord) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(code) DO UPDATE SET channel=excluded.channel, package=excluded.package, label=excluded.label, "
        "for_rc=excluded.for_rc, for_final=excluded.for_final, ord=excluded.ord",
        [(*s, i) for i, s in enumerate(ARTIFACT_SPECS)])
    con.commit()
    return con


def upsert(con, table, row, keys, keep=()):
    """Insert or update by natural key. Columns in `keep` are not overwritten with NULL."""
    cols = list(row)
    upd = [c for c in cols if c not in keys]
    sets = ", ".join(
        f"{c}=COALESCE(excluded.{c}, {table}.{c})" if c in keep else f"{c}=excluded.{c}" for c in upd)
    sql = (f"INSERT INTO {table}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
           f"ON CONFLICT({', '.join(keys)}) DO " + (f"UPDATE SET {sets}" if upd else "NOTHING"))
    con.execute(sql, [row[c] for c in cols])


def new_snapshot(con, source, taken_at=None, note=None):
    """One row per (source, taken_at): re-reading an unchanged file reuses its snapshot, so history has no repeats."""
    if taken_at:
        old = con.execute("SELECT id FROM snapshot WHERE source=? AND taken_at=?", (source, taken_at)).fetchone()
        if old:
            return old[0]
    cur = con.execute("INSERT INTO snapshot(taken_at, ingested_at, source, note) VALUES (?,?,?,?)",
                      (taken_at or now_iso(), now_iso(), source, note))
    return cur.lastrowid


def ensure_release(con, tag, snap, **extra):
    """Create release_line + release rows for a main tag. Returns the parsed tag or None."""
    p = parse_tag(tag)
    if not p or p["plat"]:
        return None
    a, b, c = p["ver"]
    upsert(con, "release_line", dict(line=p["line"], major=a, minor=b, patch=c), ["line"])
    row = dict(tag=tag, line=p["line"], kind=p["kind"], seq=p["seq"], sort_key=p["sort_key"], snapshot_id=snap)
    row.update({k: v for k, v in extra.items()})
    upsert(con, "release", row, ["tag"], keep=("sha", "tagged_at", "published_at", "prerelease", "url"))
    return p


def prune_untagged(con):
    """Remove release rows that never got a tag date (plans like 'next release'), with their dependent rows."""
    bad = [r[0] for r in con.execute(
        "SELECT tag FROM release WHERE tagged_at IS NULL AND published_at IS NULL "
        "AND tag NOT IN (SELECT release_tag FROM wf_run WHERE release_tag IS NOT NULL)")]
    for t in bad:
        for tbl in ("artifact", "release_verdict", "pr_release"):
            con.execute(f"DELETE FROM {tbl} WHERE release_tag=?", (t,))
        con.execute("DELETE FROM release WHERE tag=?", (t,))
    con.commit()
    return len(bad)
