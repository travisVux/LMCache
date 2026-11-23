"""Collect weekly full-suite builds (k3-multiprocess-test, WEEKLY_FULL=true) into ops.db.

Local run only (no CI, no browser calls). Reads the Buildkite REST API with the same token
as the ETL (BUILDKITE_API_TOKEN, else ~/.claude.json.bak-buildkite).

A weekly build tags itself with meta-data `weekly-full=true` at upload and, at the end,
writes `weekly-verdict` = {"verdict","required","passed","flaky","failed","missing",
"skipped","allowed_skip"} (see .buildkite/k3_tests/multiprocess/weekly/README.md).

  python -X utf8 collect_weekly.py            # weekly builds of the last 120 days + reference
  python -X utf8 collect_weekly.py --days 30
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "etl"))
from core.http import BK  # noqa: E402  (shared client: retry, rate limit, token)

from db import connect, new_snapshot, now_iso, upsert  # noqa: E402
from ingest_files import put_build  # noqa: E402

ORG, PIPELINE = "lmcache", "k3-multiprocess-test"
# Last full dev build before the weekly run existed (2026-10-28, all 38 test jobs, incl.
# dsv4_flash_tp TP=4). Shown on the desk until the first weekly build exists.
REFERENCE_BUILD = 6196
BAD_STATES = {"failed", "timed_out", "expired", "canceled", "broken_failed", "waiting_failed",
              "blocked_failed", "unblocked_failed", "not_run"}


def minutes(a, b):
    if not a or not b:
        return None
    p = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
    return round((p(b) - p(a)).total_seconds() / 60, 1)


def test_jobs(b):
    """Script jobs that are tests (not the upload, not the verdict); last attempt only."""
    out = []
    for j in b.get("jobs") or []:
        name = j.get("name") or ""
        if (j.get("type") != "script" or j.get("retried") or not name or j.get("state") == "broken"
                or "Upload pipeline" in name or "Weekly full verdict" in name):
            # broken = excluded by an `if:` (for example the nightly canary steps); never ran
            continue
        out.append(j)
    return out


def summarize(b, kind):
    meta = b.get("meta_data") or {}
    summary = {}
    if meta.get("weekly-verdict"):
        try:
            summary = json.loads(meta["weekly-verdict"])
        except json.JSONDecodeError:
            summary = {}
    jobs = test_jobs(b)
    if isinstance(summary.get("problems"), list):
        problems = [
            dict(label=p.get("label", ""), state=p.get("state", "failed"))
            for p in summary["problems"]
        ]
    else:
        problems = [dict(label=(j.get("name") or "").split(": ", 1)[-1].lstrip(":").strip(), state=j.get("state"))
                    for j in jobs if j.get("state") in BAD_STATES]
    state = b.get("state")
    if state in ("running", "scheduled", "creating", "canceling"):
        verdict = "running"
    elif kind == "reference":
        # No verdict step existed yet: the build state and every test job passing is the best we have.
        verdict = "pass" if state == "passed" and not problems else "fail"
        summary = dict(required=len(jobs), passed=sum(j.get("state") == "passed" for j in jobs),
                       failed=len(problems))
    elif summary.get("verdict") in ("pass", "fail"):
        verdict = "pass" if summary["verdict"] == "pass" and state == "passed" else "fail"
    else:
        verdict = "no_verdict"
    return dict(
        pipeline=PIPELINE, number=int(b["number"]), kind=kind, trigger=b.get("source"), verdict=verdict,
        required=summary.get("required"), passed=summary.get("passed"), flaky=summary.get("flaky"),
        failed=summary.get("failed"), missing=summary.get("missing"), skipped=summary.get("skipped"),
        allowed_skip=summary.get("allowed_skip"), problems=json.dumps(problems),
        duration_min=minutes(b.get("started_at") or b.get("created_at"), b.get("finished_at")))


def fetch_weekly(days):
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"organizations/{ORG}/pipelines/{PIPELINE}/builds?meta_data[weekly-full]=true"
           f"&created_from={since}&per_page=100&include_retried_jobs=true")
    builds = []
    while url:
        page, headers = BK.request(url)
        builds += page
        nxt = [p.split(";")[0].strip(" <>") for p in (headers.get("Link") or "").split(",") if 'rel="next"' in p]
        url = nxt[0] if nxt else None
    return builds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    args = ap.parse_args()
    con = connect()
    snap = new_snapshot(con, "collect:bk-weekly", now_iso())
    ref, _ = BK.request(f"organizations/{ORG}/pipelines/{PIPELINE}/builds/{REFERENCE_BUILD}?include_retried_jobs=true")
    rows = [("reference", ref)] + [("weekly", b) for b in fetch_weekly(args.days)]
    for kind, b in rows:
        put_build(con, PIPELINE, b, snap)
        upsert(con, "weekly_run", dict(summarize(b, kind), snapshot_id=snap), ["pipeline", "number"])
    con.commit()
    for r in con.execute("SELECT kind, number, verdict, required, passed, failed FROM weekly_run ORDER BY number"):
        print(dict(r))
    print(f"weekly builds: {len(rows) - 1}")


if __name__ == "__main__":
    main()
