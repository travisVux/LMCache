"""Keep plan-2026-11/outputs/P1_full (the CI Baseline tab #r1130 data) current, cheaply. Run by ops-app/deploy/refresh.ps1
after the collectors (collect_ci_impact refreshes ops-app/data/ci_impact_cache first).

  python -X utf8 refresh_p1_full.py [--dry-run] [--since YYYY-MM-DD]

1. ingest-cache: Buildkite builds + GitHub Actions run jobs that the ops-app cache already holds go into the lake (no API call)
2. update: only what is still missing / changed / not final, from the first Buildkite day in the lake (else 2026-10-17)
   up to today (UTC, until = tomorrow). gh_prs: --max-age 5 (an open PR whose checks all concluded and that did not
   change is not read again). GitHub: stops calling when fewer than ETL_GH_MIN_REMAINING (default here 1500) calls are
   left, instead of sleeping: the scheduled refresh keeps its quota, the rest is fetched on the next run.
3. export + P1 transforms into a staging folder, then swap it into P1_full. Any failure keeps the last P1_full.
Exit 0 = P1_full replaced; 1 = failed (P1_full untouched).
"""
import argparse
import os
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone

os.environ.setdefault("ETL_GH_MIN_REMAINING", "1500")
os.environ.setdefault("ETL_GH_NO_WAIT", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import etl  # noqa: E402
import sinks  # noqa: E402
from core.http import BK, GH  # noqa: E402
from core.lake import Lake  # noqa: E402

OUTS = os.path.normpath(os.path.join(HERE, "..", "plan-2026-11", "outputs"))
CACHE = os.path.normpath(os.path.join(HERE, "..", "ops-app", "data", "ci_impact_cache"))
DEFAULT_SINCE = "2026-10-17"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    lake = Lake(os.environ.get("ETL_LAKE") or os.path.join(HERE, "lake"))
    first = lake.db.execute("SELECT MIN(day) FROM partition WHERE source='bk_builds' AND status='ok'").fetchone()[0]
    since = a.since or min(first or DEFAULT_SINCE, DEFAULT_SINCE)
    until = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    print(f"P1_full refresh: {since} .. {until} (until excluded)", flush=True)
    print("ingest-cache:", sinks.ingest_cache(lake, CACHE, (), dry_run=a.dry_run), flush=True)
    ns = argparse.Namespace(since=since, until=until, source=None, refresh=False, limit=None, dry_run=a.dry_run, max_age=5, dead=False)
    tot = etl.cmd_update(ns, lake)
    if a.dry_run:
        return 0
    stage, final, old = (os.path.join(OUTS, n) for n in ("_P1_full_build", "P1_full", "_P1_full_old"))
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    ns.out = stage
    rep = etl.cmd_export(ns, lake)
    etl.cmd_transform(ns, lake)
    shutil.rmtree(old, ignore_errors=True)
    if os.path.exists(final):
        os.replace(final, old)
    os.replace(stage, final)
    shutil.rmtree(old, ignore_errors=True)
    failed = {k: v.get("failed") for k, v in tot.items() if isinstance(v, dict) and v.get("failed")}
    print(f"P1_full replaced in {time.time() - t0:.0f}s · api calls github {GH.calls} buildkite {BK.calls}"
          f" · failed partitions {failed or 0} (retried next run) · missing build days {len(rep['missing_build_days'])}"
          + (f" · GitHub stopped early: {GH.stopped}" if GH.stopped else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
