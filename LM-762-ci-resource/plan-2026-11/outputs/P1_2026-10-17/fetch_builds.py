"""Step 1a: fetch every Buildkite build (all branches, with jobs incl. retried attempts) of the required GPU pipelines
created in the fixed window of window.json.

  python -I -X utf8 outputs/P1/fetch_builds.py                       # all pipelines in window.json
  python -I -X utf8 outputs/P1/fetch_builds.py --pipeline k3-unit-tests

Writes raw/builds_30d.json (k3-multiprocess-test, name kept for older scripts) and raw/builds_<slug>_30d.json for the others.
The window has an end date (created_to), so a re-run returns the same builds as long as Buildkite keeps them."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # sibling modules also under python -I
import argparse, json, bk_api

HERE = _os.path.dirname(_os.path.abspath(__file__))
WIN = json.load(open(_os.path.join(HERE, "window.json"), encoding="utf-8"))


def raw_path(slug):
    return _os.path.join(HERE, "raw", "builds_30d.json" if slug == "k3-multiprocess-test" else f"builds_{slug}_30d.json")


def fetch(slug, since, until):
    url = (f"organizations/lmcache/pipelines/{slug}/builds?created_from={since}&created_to={until}"
           f"&per_page=100&include_retried_jobs=true")
    out, page = [], 0
    while url:
        page += 1
        data, link = bk_api.get(url)
        out.extend(data)
        print(f"{slug} page {page}: +{len(data)} (total {len(out)})", flush=True)
        url = bk_api.next_link(link)
    for x in out:  # strip fields that may hold secrets (pipeline config / env)
        x.pop("pipeline", None); x.pop("env", None)
        x["pipeline_slug"] = slug
        for j in x.get("jobs", []):
            j.pop("env", None)
    unfinished = [b["number"] for b in out if b.get("state") in ("running", "scheduled", "creating", "canceling", "failing")]
    json.dump(out, open(raw_path(slug), "w", encoding="utf-8"))
    print(f"{slug}: {len(out)} builds, unfinished at fetch time: {unfinished or 'none'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", action="append")
    ap.add_argument("--since", default=WIN["since"])
    ap.add_argument("--until", default=WIN["until"])
    a = ap.parse_args()
    for s in a.pipeline or WIN["pipelines"]:
        fetch(s, a.since, a.until)
