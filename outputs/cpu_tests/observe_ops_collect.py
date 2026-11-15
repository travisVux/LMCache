"""Collect the last 24 h of CI for the "Optimal CI" and "24h overlap" tabs (local run only).

  python -I -X utf8 observe_ops_collect.py              # collect -> ops_ci_24h.json -> rebuild the ops tabs
  python -I -X utf8 observe_ops_collect.py --no-build   # collect only
  python -I -X utf8 observe_ops_collect.py --hours 48   # wider window

What it fetches (read-only):
  GitHub Actions: every workflow run created in the window (all events, all branches) and its jobs,
                  so CPU runner-minutes are job-minutes, not run wall time.
  Buildkite:      every build created in the window (all pipelines, all branches) with its jobs,
                  so GPU agent-minutes are job-minutes.
Transport, token handling and retries come from observe_collect.py (gh CLI + Buildkite REST).
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir
import observe_collect as oc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ops_ci_24h.json")
RUN = oc.RUN + [("pull_requests", ["number"])]
GJOB = ["name", "status", "conclusion", "created_at", "started_at", "completed_at", "labels", "runner_group_name", "run_attempt"]
BJOB = ["type", "name", "state", "scheduled_at", "runnable_at", "started_at", "finished_at", "retried", "soft_failed", "agent_query_rules"]
BBUILD = [f for f in oc.BK_BUILD if f != "message"] + [("jobs", BJOB)]


def fmt(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def gha_slice(a, b):
    """Runs created in [a, b). GitHub returns at most 1,000 runs per query, so a full slice is split in two."""
    out = []
    for page in range(1, 11):
        d = oc.gh(f"repos/{oc.REPO}/actions/runs?created={fmt(a)}..{fmt(b - timedelta(seconds=1))}&per_page=100&page={page}")
        rs = d.get("workflow_runs") or []
        out += [oc.pick(r, RUN) for r in rs]
        if len(rs) < 100:
            return out
    if (b - a) > timedelta(minutes=10):
        m = a + (b - a) / 2
        return gha_slice(a, m) + gha_slice(m, b)
    oc.ERRORS.append(f"gha: more than 1,000 runs in {fmt(a)}..{fmt(b)}; truncated")
    return out


def gha_runs(since, until):
    out, a = [], since
    while a < until:  # 3-hour slices keep each query under the 1,000-run cap
        b = min(until, a + timedelta(hours=3))
        out += gha_slice(a, b)
        a = b
    return list({r["id"]: r for r in out}.values())


def gha_jobs(run):
    d = oc.gh(f"repos/{oc.REPO}/actions/runs/{run['id']}/jobs?per_page=100&filter=all")
    return run["id"], [oc.pick(j, GJOB) for j in d.get("jobs") or []]


def bk_builds(since):
    out = []
    for page in range(1, 11):
        d = oc.bk(f"organizations/{oc.ORG}/builds?created_from={since}&per_page=100&page={page}")
        out += [oc.pick(b, BBUILD) for b in d]
        if len(d) < 100:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    since = (now - timedelta(hours=a.hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("window", since, "->", now.isoformat())

    runs = oc.safe("gha runs", lambda: gha_runs(now - timedelta(hours=a.hours), now), [])
    print("  gha runs", len(runs))
    with ThreadPoolExecutor(8) as ex:
        jobs = dict(r for r in ex.map(lambda r: oc.safe(f"jobs {r['id']}", lambda: gha_jobs(r), (r["id"], None)), runs))
    for r in runs:
        r["jobs"] = jobs.get(r["id"])
    builds = []
    if oc.TOK:
        builds = oc.safe("bk builds", lambda: bk_builds(since), [])
    else:
        oc.ERRORS.append("buildkite: no token (BUILDKITE_API_TOKEN or ~/.claude.json.bak-buildkite)")
    print("  bk builds", len(builds))

    snap = dict(at=now.strftime("%Y-%m-%dT%H:%M:%SZ"), since=since, hours=a.hours, gha=runs, bk=builds, errors=oc.ERRORS)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB), errors: {len(oc.ERRORS)}")
    if not a.no_build:
        import build_ops_tabs
        build_ops_tabs.main()


if __name__ == "__main__":
    main()
