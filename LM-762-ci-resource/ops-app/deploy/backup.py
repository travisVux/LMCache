"""Daily backup of the SQLite stores (consistent copy with the sqlite backup API). Python stdlib only.

  python -X utf8 backup.py                 # -> ops-app/backups/<YYYY-MM-DD>/{ops.db, state.db}; keep 14 days
  python -X utf8 backup.py --keep 30
  python -X utf8 backup.py --restore 2026-11-20 [--what ops]   # put a backup back (stop the refresh task first)
  python -X utf8 backup.py --drill                 # restore drill: newest backup -> temp folder, integrity + row counts vs live

Off-host copy (expert review O1): set OPS_BACKUP_COPY_TO (in ops-app.env) to a folder on another disk / NAS / synced drive;
every backup day is also copied there (and pruned with the same --keep). Without it the backups stay on this disk only and the
run says so. The drill result is written to logs/backup-drill.json.

Backed up: ops-app/data/ops.db (history store), etl/lake/state.db (ETL state, if present on this host).
Served copies under releases/ are not backed up: they are rebuilt from ops.db and kept 5 deep by publish.py.
"""
import argparse
import datetime as dt
import json
import os
import tempfile
import shutil
import sqlite3
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
STORES = {"ops": APP / "data" / "ops.db", "state": APP.parent / "etl" / "lake" / "state.db"}
OUT = APP / "backups"


def copy(src, dst):
    s = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    with d:
        s.backup(d)
    ok = d.execute("PRAGMA integrity_check").fetchone()[0]
    d.close()
    s.close()
    if ok != "ok":
        raise RuntimeError(f"integrity_check of {dst.name}: {ok}")


def counts(db):
    con = sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True)
    try:
        ts = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in ts}
    finally:
        con.close()


def drill():
    """Restore the newest backup into a temp folder (never over the live file) and compare it with the live store."""
    days = sorted(p for p in OUT.iterdir() if p.is_dir()) if OUT.is_dir() else []
    res = dict(at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), ok=False)
    if not days:
        res["error"] = "no backup"
    else:
        day = days[-1]
        res["backup"] = day.name
        with tempfile.TemporaryDirectory() as t:
            for k, live in STORES.items():
                src = day / live.name
                if not src.is_file():
                    continue
                dst = Path(t) / live.name
                copy(src, dst)                                  # the same path --restore uses, integrity_check included
                b, l_ = counts(dst), (counts(live) if live.is_file() else {})
                missing = sorted(set(l_) - set(b))
                fewer = {x: [b[x], l_[x]] for x in b if x in l_ and b[x] > l_[x]}
                res[k] = dict(tables=len(b), rows=sum(b.values()), live_rows=sum(l_.values()), missing_tables=missing, more_rows_than_live=fewer)
        res["ok"] = all(not res[k]["missing_tables"] for k in STORES if k in res)
    log = APP / "logs" / "backup-drill.json"
    log.parent.mkdir(exist_ok=True)
    log.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0 if res["ok"] else 1


def offhost(day, keep):
    to = os.environ.get("OPS_BACKUP_COPY_TO")
    if not to:
        print("off-host copy: OPS_BACKUP_COPY_TO is not set, backups stay on this disk only")
        return
    dest = Path(to)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(day, dest / day.name, dirs_exist_ok=True)
    print(f"off-host copy: {day.name} -> {dest}")
    for old in sorted(p for p in dest.iterdir() if p.is_dir())[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--keep", type=int, default=14)
    ap.add_argument("--restore", metavar="DATE")
    ap.add_argument("--what", choices=sorted(STORES), help="with --restore: only this store")
    ap.add_argument("--drill", action="store_true", help="restore drill into a temp folder")
    a = ap.parse_args()
    if a.drill:
        return drill()
    if a.restore:
        day = OUT / a.restore
        for k, dst in STORES.items():
            if a.what and k != a.what:
                continue
            src = day / dst.name
            if src.is_file():
                if dst.is_file():
                    shutil.copy2(dst, dst.with_suffix(".db.before-restore"))
                copy(src, dst)
                print(f"restored {dst.name} from {a.restore} (old file kept as {dst.name}.before-restore)")
        return 0
    day = OUT / dt.date.today().isoformat()
    day.mkdir(parents=True, exist_ok=True)
    for k, src in STORES.items():
        if src.is_file():
            copy(src, day / src.name)
            print(f"backup {src.name} -> backups/{day.name}/ ({(day / src.name).stat().st_size // 1024} KB)")
        else:
            print(f"skip {k}: {src.name} not on this host")
    offhost(day, a.keep)
    days = sorted(p for p in OUT.iterdir() if p.is_dir())
    for old in days[:-a.keep]:
        shutil.rmtree(old)
        print("removed old backup", old.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
