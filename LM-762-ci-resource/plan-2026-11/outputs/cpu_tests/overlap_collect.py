"""Collect code diffs of every open dev PR (any state, drafts included) for the 24h overlap review.

  python -I -X utf8 overlap_collect.py             # fetch -> overlap_patches.json -> rebuild the ops tabs
  python -I -X utf8 overlap_collect.py --no-build

Read-only GitHub calls (gh CLI): repos/<repo>/pulls/<n>/files (filename + unified patch with 3 context lines).
The PR list comes from observe_snapshot.json (run observe_collect.py first so PR states are fresh).
Merged PRs are read from the local git clone at build time, so they are not fetched here.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir
import observe_collect as oc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "overlap_patches.json")
SNAP = os.path.join(HERE, "observe_snapshot.json")


def pr_files(n):
    out = []
    for page in range(1, 4):
        d = oc.gh(f"repos/{oc.REPO}/pulls/{n}/files?per_page=100&page={page}")
        out += [dict(f=x["filename"], s=x.get("status"), p=(x.get("patch") or "")[:60000]) for x in d]
        if len(d) < 100:
            break
    return n, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()
    snap = json.load(open(SNAP, encoding="utf-8"))
    nodes = [n for n in ((snap.get("gh") or {}).get("prs_gql") or {}).get("nodes") or [] if n.get("baseRefName") == "dev"]
    print("open dev PRs", len(nodes))
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda n: oc.safe(f"files {n['number']}", lambda: pr_files(n["number"]), (n["number"], None)), nodes))
    data = dict(at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), snap_at=snap.get("at"),
                prs={str(n): f for n, f in res if f is not None}, errors=oc.ERRORS)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB), PRs {len(data['prs'])}, errors {len(oc.ERRORS)}")
    if not a.no_build:
        import build_ops_tabs
        build_ops_tabs.main()


if __name__ == "__main__":
    main()
