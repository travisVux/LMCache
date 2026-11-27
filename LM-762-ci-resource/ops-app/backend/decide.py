"""Record a release decision for a blocker (expert review round 2, A4 / B5 / D-7). Python stdlib only. Local only.

  python -X utf8 decide.py list                                     # open blockers of the current line + recorded decisions
  python -X utf8 decide.py record 0.5.8:artifact:pypi:lmcache-cli --action known_issue \
         --reason "cli upload job publishes a dev version; fix in 0.5.9" --by <name>
  python -X utf8 decide.py history [BLOCKER_ID]

Actions: post1 (ship vX.post1 with the fix) · upload (out-of-band upload of the missing artifact) · known_issue (note it in
the release notes, does not gate) · accept (accepted gap for this release, does not gate) · yank · rerun.
known_issue and accept make the blocker non-gating on the page; the others keep it gating and show the decision next to it.
Rows are append-only: a new record for the same blocker replaces the old one on the page, the old one stays in history.
--by defaults to $OPS_RELEASE_OWNER. The page shows the decision after the next build (refresh.ps1).
"""
import argparse
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE.parent / "data" / "ops.db"
ACTIONS = ("post1", "upload", "known_issue", "accept", "yank", "rerun")
DDL = """
CREATE TABLE IF NOT EXISTS release_decision (
  id          INTEGER PRIMARY KEY,
  blocker_id  TEXT NOT NULL,
  line        TEXT,
  action      TEXT NOT NULL CHECK (action IN ('post1','upload','known_issue','accept','yank','rerun')),
  reason      TEXT NOT NULL CHECK (length(trim(reason)) > 0),
  decided_by  TEXT NOT NULL CHECK (length(trim(decided_by)) > 0),
  decided_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_release_decision_blocker ON release_decision(blocker_id, decided_at);
CREATE TRIGGER IF NOT EXISTS release_decision_no_update BEFORE UPDATE ON release_decision
BEGIN SELECT RAISE(ABORT, 'release_decision is append-only'); END;
CREATE TRIGGER IF NOT EXISTS release_decision_no_delete BEFORE DELETE ON release_decision
BEGIN SELECT RAISE(ABORT, 'release_decision is append-only'); END;
"""


def connect(db=DB):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.executescript(DDL)
    return con


def current(con):
    """Blockers of the current line as the page computes them (stored ones + artifact / publish gaps found by the model)."""
    sys.path.insert(0, str(HERE))
    import model
    o = model.overview(con)
    return [dict(id=b["id"], kind=b["kind"], title=b.get("title") or "", line=(o.get("line") or {}).get("line") if isinstance(o.get("line"), dict) else o.get("line"))
            for b in o.get("blockers") or []]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DB))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("record")
    r.add_argument("blocker")
    r.add_argument("--action", required=True, choices=ACTIONS)
    r.add_argument("--reason", required=True)
    r.add_argument("--by", default=os.environ.get("OPS_RELEASE_OWNER"))
    h = sub.add_parser("history")
    h.add_argument("blocker", nargs="?")
    a = ap.parse_args()
    con = connect(a.db)
    if a.cmd == "record":
        if not (a.by or "").strip():
            sys.exit("--by is required (or set OPS_RELEASE_OWNER)")
        b = {x["id"]: x for x in current(con)}.get(a.blocker)
        if not b:
            sys.exit(f"unknown blocker {a.blocker!r}: run  decide.py list")
        with con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("INSERT INTO release_decision(blocker_id, line, action, reason, decided_by, decided_at) VALUES (?,?,?,?,?,?)",
                        (a.blocker, b["line"], a.action, a.reason.strip(), a.by.strip(),
                         dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
        print(f"recorded: {a.blocker} -> {a.action} (by {a.by}). The page shows it after the next build.")
        return 0
    if a.cmd == "list":
        dec = {r["blocker_id"]: r for r in con.execute("SELECT * FROM release_decision ORDER BY decided_at, id")}
        for b in current(con):
            d = dec.get(b["id"])
            print(f"{b['id']:45} {b['kind']:9} {(d['action'] + ' · ' + d['decided_at'][:10]) if d else '-':26} {b['title'][:70]}")
        return 0
    q = "SELECT * FROM release_decision" + (" WHERE blocker_id=?" if a.blocker else "") + " ORDER BY decided_at, id"
    for r in con.execute(q, (a.blocker,) if a.blocker else ()):
        print(f"{r['decided_at']}  {r['blocker_id']:40} {r['action']:12} by {r['decided_by']}: {r['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
