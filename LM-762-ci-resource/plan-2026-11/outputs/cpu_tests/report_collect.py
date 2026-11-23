"""Backfill data for the PR / Release report (#obs/trend): 60 days of real history, one JSON.

GitHub (gh CLI):
  merged_prs   PRs merged into dev       (search API, split in 10-day windows, <1000 each)
  opened_prs   PRs opened against dev    (search API)
  releases     all releases (tags)
  publish      publish.yml runs          (workflow runs API, created filter)
  nightly      nightly_build.yml runs
Buildkite (token from observe_collect.bk_token):
  dev builds of k3-unit-tests / k3-multiprocess-test / k3-comprehensive-test
  PR builds of k3-unit-tests with jobs  -> GPU wait (longest runnable->started) and build time

  python -I -X utf8 report_collect.py            # writes report_data.json (~ few hundred KB)
Only the fields the report uses are kept.
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "P1"))
import bk_api  # noqa: E402
from build_observe import CONFIG  # noqa: E402

REPO = CONFIG["repo"]
DAYS = 60
END = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
START = END - timedelta(days=DAYS)
OUT = os.path.join(HERE, "report_data.json")
d10 = lambda t: t.strftime("%Y-%m-%d")


def gh(path):
    for i in range(5):
        p = subprocess.run(["gh", "api", "-H", "X-GitHub-Api-Version: 2022-11-28", path],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0:
            return json.loads(p.stdout)
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"gh {path[:80]}: {p.stderr[:200]}")


def search(q):
    out = []
    a = START
    while a < END:
        b = min(END, a + timedelta(days=10))
        page = 1
        while True:
            qq = urllib.parse.quote(f"repo:{REPO} {q}:{d10(a)}..{d10(b - timedelta(days=1))}", safe="")
            d = gh(f"search/issues?q={qq}&per_page=100&page={page}")
            out += d["items"]
            if len(d["items"]) < 100 or page >= 10:
                break
            page += 1
        time.sleep(2.2)  # search API: 30 / min
        a = b
    seen, res = set(), []
    for i in out:
        if i["number"] not in seen:
            seen.add(i["number"]); res.append(i)
    return res


def runs(wf):
    out, page = [], 1
    while True:
        d = gh(f"repos/{REPO}/actions/workflows/{wf}/runs?created={d10(START)}..{d10(END)}&per_page=100&page={page}")
        out += [{k: r.get(k) for k in ("id", "event", "head_branch", "status", "conclusion", "created_at", "run_attempt", "html_url")} for r in d["workflow_runs"]]
        if len(d["workflow_runs"]) < 100:
            return out
        page += 1


def bk_builds(slug, extra, keep_jobs=False, per_page=100):
    url = f"organizations/{CONFIG['bk_org']}/pipelines/{slug}/builds?created_from={START.isoformat().replace('+00:00', 'Z')}&per_page={per_page}{extra}"
    out = []
    while url:
        d, link = bk_api.get(url)
        for b in d:
            x = {k: b.get(k) for k in ("number", "state", "branch", "created_at", "started_at", "finished_at")}
            x["pr"] = (b.get("pull_request") or {}).get("id")
            if keep_jobs:
                w = [(datetime.fromisoformat(j["started_at"].replace("Z", "+00:00")) - datetime.fromisoformat(j["runnable_at"].replace("Z", "+00:00"))).total_seconds() / 60
                     for j in b.get("jobs") or [] if j.get("type") == "script" and j.get("runnable_at") and j.get("started_at")]
                x["wait_min"] = round(max(w), 1) if w else None
            out.append(x)
        url = bk_api.next_link(link)
    return out


def k3u_pr_paged():
    """k3-unit-tests PR builds WITH jobs: big payloads, the connection resets -> 10 per page, each page cached."""
    d = os.path.join(HERE, "report_cache", "k3u_pages"); os.makedirs(d, exist_ok=True)
    out, page = [], 1
    while True:
        f = os.path.join(d, f"{page:04d}.json")
        if os.path.exists(f):
            rows = json.load(open(f, encoding="utf-8"))
        else:
            rows = None
            for i in range(6):
                try:
                    rows = bk_builds_page("k3-unit-tests", page); break
                except Exception as e:  # noqa: BLE001
                    print("  retry page", page, e); time.sleep(5 * (i + 1))
            if rows is None:
                raise RuntimeError(f"page {page} failed")
            json.dump(rows, open(f, "w", encoding="utf-8"))
        out += rows
        if len(rows) < 10:
            return [b for b in out if b["branch"] != "dev"]
        page += 1


def bk_builds_page(slug, page):
    url = f"organizations/{CONFIG['bk_org']}/pipelines/{slug}/builds?created_from={START.isoformat().replace('+00:00', 'Z')}&per_page=10&page={page}"
    d, _ = bk_api.get(url, retries=3)
    out = []
    for b in d:
        x = {k: b.get(k) for k in ("number", "state", "branch", "created_at", "started_at", "finished_at")}
        x["pr"] = (b.get("pull_request") or {}).get("id")
        w = [(datetime.fromisoformat(j["started_at"].replace("Z", "+00:00")) - datetime.fromisoformat(j["runnable_at"].replace("Z", "+00:00"))).total_seconds() / 60
             for j in b.get("jobs") or [] if j.get("type") == "script" and j.get("runnable_at") and j.get("started_at")]
        x["wait_min"] = round(max(w), 1) if w else None
        out.append(x)
    return out


def cached(key, fn):
    """Each step is cached in report_cache/<key>.json (delete the folder to refetch)."""
    d = os.path.join(HERE, "report_cache"); os.makedirs(d, exist_ok=True)
    f = os.path.join(d, key + ".json")
    if os.path.exists(f):
        return json.load(open(f, encoding="utf-8"))
    v = fn(); json.dump(v, open(f, "w", encoding="utf-8")); return v


def main():
    t0 = time.time()
    R = dict(start=d10(START), end=d10(END - timedelta(days=1)), made=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    print("merged PRs ..."); R["merged_prs"] = cached("merged", lambda: [dict(n=i["number"], c=i["created_at"], m=(i.get("pull_request") or {}).get("merged_at"), u=(i.get("user") or {}).get("login"))
                                                for i in search("is:pr is:merged base:dev merged")])
    print("opened PRs ..."); R["opened_prs"] = cached("opened", lambda: [dict(n=i["number"], c=i["created_at"], s=i["state"], u=(i.get("user") or {}).get("login")) for i in search("is:pr base:dev created")])
    print("releases ...")
    rel = []
    for page in range(1, 4):
        d = gh(f"repos/{REPO}/releases?per_page=100&page={page}")
        rel += [{"tag": r["tag_name"], "at": r["published_at"], "pre": r["prerelease"], "url": r["html_url"]} for r in d if not r["draft"]]
        if len(d) < 100:
            break
    R["releases"] = rel
    print("publish / nightly runs ...")
    R["publish"] = cached("publish", lambda: runs(CONFIG["workflows"]["publish"]))
    R["nightly"] = cached("nightly", lambda: runs(CONFIG["workflows"]["nightly"]))
    print("buildkite dev builds ...")
    R["bk_dev"] = {s: cached("dev_" + s, lambda s=s: bk_builds(s, "&branch=dev&exclude_jobs=true")) for s in ("k3-unit-tests", "k3-multiprocess-test", "k3-comprehensive-test")}
    print("buildkite k3-unit PR builds (with jobs) ...")
    R["k3u_pr"] = cached("k3u_pr", k3u_pr_paged)
    s = json.dumps(R, ensure_ascii=False, separators=(",", ":"))
    open(OUT, "w", encoding="utf-8").write(s)
    print(f"{OUT}: {len(s)/1024:.0f} KB in {time.time()-t0:.0f}s | merged {len(R['merged_prs'])} opened {len(R['opened_prs'])} "
          f"publish {len(R['publish'])} nightly {len(R['nightly'])} dev " + str({k: len(v) for k, v in R['bk_dev'].items()}) + f" k3u PR {len(R['k3u_pr'])}")


if __name__ == "__main__":
    main()
