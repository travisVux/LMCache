"""Collect every k3-multiprocess-test build since a date (PR and dev), for the MP evidence of the next release.

  python -I -X utf8 mp_pr_collect.py                    # since 2026-11-04 (end of the P1 30-day window)
  python -I -X utf8 mp_pr_collect.py --since 2026-11-10

Read-only Buildkite REST calls (token as in observe_collect.py), about 1 call per 100 builds, jobs excluded.
Writes mp_pr_builds.json. build_entities.py reads it: each build gets a 'ran' link from its PR (pull_request.id),
so Next release 3B can show the PR's own MP result (PR CI, not dev).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir
import observe_collect as oc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "mp_pr_builds.json")
PIPE = "k3-multiprocess-test"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-11-04")
    ap.add_argument("--pages", type=int, default=30)
    a = ap.parse_args()
    if not oc.TOK:
        print("no Buildkite token (BUILDKITE_API_TOKEN or ~/.claude.json.bak-buildkite)")
        return 1
    since = a.since + "T00:00:00Z" if "T" not in a.since else a.since
    out, pages = [], 0
    for page in range(1, a.pages + 1):
        d = oc.bk(f"organizations/{oc.ORG}/pipelines/{PIPE}/builds?created_from={since}&per_page=100&page={page}&exclude_jobs=true")
        pages += 1
        out += [oc.pick(b, oc.BK_BUILD) for b in d]
        if len(d) < 100:
            break
    data = dict(at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), since=since, pipeline=PIPE, pages=pages, builds=out)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    prs = {(b.get("pull_request") or {}).get("id") for b in out} - {None}
    print(f"wrote {OUT}: {len(out)} builds ({sum(1 for b in out if b.get('state') == 'passed')} passed) for {len(prs)} PRs, {pages} calls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
