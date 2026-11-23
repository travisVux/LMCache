"""CI data ETL: incremental fetch + backfill + retry into a lake, then export any window for the P1 transforms.

Run from LM-762-ci-resource/etl/ :

  python -X utf8 etl.py status                                   # partitions per source, failures
  python -X utf8 etl.py update   --since 2026-10-17 --until 2026-11-16          # fetch only what is missing / changed / failed
  python -X utf8 etl.py backfill --since 2026-09-01 --until 2026-10-17          # same as update, for an older range
  python -X utf8 etl.py retry                                    # re-run only failed partitions (add --dead for given-up ones)
  python -X utf8 etl.py ingest-legacy ../plan-2026-11/outputs/P1           # load an old P1 folder into the lake
  python -X utf8 etl.py export   --since 2026-10-17 --until 2026-11-16 --out ../plan-2026-11/outputs/P1_2026-10-17
  python -X utf8 etl.py window   --since 2026-10-17 --until 2026-11-16 --out ../plan-2026-11/outputs/P1_2026-10-17
        # = update + export + transforms (build_jobs_table, sample_fail_logs, aggregate, build_pr_table)

Options: --dry-run (plan only) · --source NAME (one source only; repeatable) · --refresh (refetch even final partitions) · --limit N (first N partitions, for a test)
Dates are UTC days; --until is exclusive. The lake lives in etl/lake/ (override with ETL_LAKE).
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from core.lake import Lake, now  # noqa: E402
from core.pipeline import run  # noqa: E402
from sources import SOURCES, BY_NAME  # noqa: E402
import sinks  # noqa: E402

TRANSFORMS = ["build_jobs_table.py", "sample_fail_logs.py", "aggregate.py", "build_pr_table.py"]


class Ctx:
    def __init__(self, lake):
        self.lake = lake


def day(s):
    return s if "T" in s else s + "T00:00:00Z"


def cmd_update(a, lake, only_failed=False):
    ctx, total = Ctx(lake), {}
    for src in [BY_NAME[n] for n in a.source] if a.source else SOURCES:
        try:
            total[src.name] = run(src, ctx, day(a.since), day(a.until), refresh=a.refresh, retry_dead=getattr(a, "dead", False),
                                  only_failed=only_failed, limit=a.limit, command=" ".join(sys.argv[1:]), dry_run=getattr(a, "dry_run", False))
        except Exception as e:  # noqa: BLE001  planning failed (e.g. the PR search): later sources still run on what the lake has
            print(f"[{src.name}] planning failed: {type(e).__name__}: {e}", flush=True)
            total[src.name] = dict(error=str(e))
    print("summary:", total, flush=True)
    return total


def cmd_status(lake):
    print(f"lake: {lake.root}")
    print(f"{'source':12} {'status':7} {'final':5} {'parts':>7} {'first day':10} {'last day':10} {'rows':>9}  last fetch")
    for s, st, fi, n, d0, d1, rows, last in lake.summary():
        print(f"{s:12} {st:7} {'yes' if fi else 'no':5} {n:7} {d0 or '':10} {d1 or '':10} {rows or 0:9}  {last or ''}")
    f = lake.failures()
    if f:
        print("\nfailures (source, key, status, attempts, error):")
        for r in f:
            print("  ", r)


def cmd_export(a, lake):
    out = os.path.abspath(a.out)
    rep = sinks.export_window(lake, day(a.since), day(a.until), out)
    print("export:", {k: v for k, v in rep.items() if k != "missing_build_days"}, flush=True)
    if rep["missing_build_days"] or rep["runs_missing"] or rep["orphans_missing"]:
        print(f"  WARNING missing in lake: build days {rep['missing_build_days'][:6]}{'…' if len(rep['missing_build_days']) > 6 else ''}, "
              f"runs {rep['runs_missing']}, force-pushed commits {rep['orphans_missing']} -> run `update` for the window", flush=True)
    return rep


def cmd_transform(a, lake):
    out = os.path.abspath(a.out)
    for f in os.listdir(os.path.join(HERE, "transforms", "p1")):
        if f.endswith(".py"):
            shutil.copyfile(os.path.join(HERE, "transforms", "p1", f), os.path.join(out, f))
    for f in TRANSFORMS:
        t0 = time.time()
        print(f"== transform {f}", flush=True)
        p = subprocess.run([sys.executable, "-X", "utf8", f], cwd=out)
        if p.returncode != 0:
            raise SystemExit(f"transform {f} failed (exit {p.returncode})")
        print(f"   {f} ok in {time.time() - t0:.0f}s", flush=True)
    sinks.save_cache_back(lake, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["status", "update", "backfill", "retry", "ingest-legacy", "export", "window"])
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--out")
    ap.add_argument("--source", action="append", choices=list(BY_NAME))
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dead", action="store_true", help="retry: also partitions that failed max_attempts times")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true", help="plan only: how many partitions would be fetched and why")
    a = ap.parse_args()
    lake = Lake(os.environ.get("ETL_LAKE") or os.path.join(HERE, "lake"))
    print(f"started {now()} · {a.command}", flush=True)
    if a.command == "status":
        cmd_status(lake)
    elif a.command in ("update", "backfill"):
        cmd_update(a, lake)
    elif a.command == "retry":
        a.since, a.until = a.since or "2000-01-01", a.until or "2100-01-01"
        # planning needs the range: retry re-plans every range that has failures, from the state table
        rows = lake.db.execute("SELECT source, MIN(day), MAX(day) FROM partition WHERE status IN ('failed','dead') GROUP BY source").fetchall()
        for s, d0, d1 in rows:
            if a.source and s not in a.source:
                continue
            a2 = argparse.Namespace(**vars(a))
            a2.source, a2.since = [s], d0
            a2.until = (date.fromisoformat((d1 or d0)[:10]) + timedelta(days=1)).isoformat()
            cmd_update(a2, lake, only_failed=True)
        if not rows:
            print("no failed partitions")
    elif a.command == "ingest-legacy":
        print("ingested:", sinks.ingest_legacy(lake, os.path.abspath(a.folder)))
    elif a.command == "export":
        cmd_export(a, lake)
    elif a.command == "window":
        cmd_update(a, lake)
        cmd_export(a, lake)
        cmd_transform(a, lake)
    print(f"finished {now()}", flush=True)


if __name__ == "__main__":
    main()
