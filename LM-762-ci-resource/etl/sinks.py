"""Sinks: lake -> files that the existing P1 transforms read; and the reverse (ingest old P1 folders into the lake).

export_window(lake, since, until, out):
  out/window.json
  out/raw/builds_30d.json                 k3-multiprocess-test builds created in the window   (same format as P1/fetch_builds.py)
  out/raw/builds_k3-unit-tests_30d.json   k3-unit-tests builds
  out/raw/gh_checks_30d.json              PRs open in the window + every commit's checks + force-pushed commits (same as fetch_gh_checks.py)
  out/raw/gh_run_jobs_30d.jsonl           REST jobs of the window's workflow runs (same as fetch_gh_job_queue.py)
  out/raw/fail_signatures.json, log_markers.json   cached log evidence (lake/cache), so sample_fail_logs.py only reads new logs

ingest_legacy(lake, folder): load an old P1-style folder into the lake (fetched_at = when that file was made),
keeping whatever the lake already has that is newer.
"""
import json
import os
import shutil
from datetime import datetime, timedelta, timezone

from core.pipeline import days, ts
from sources import BK_PIPELINES, REPO, UNFINISHED, GhPrs, BkBuilds, GhCommits, pr_is_final, _suite_last, _all_concluded, _suites

BUILD_FILE = {"k3-multiprocess-test": "builds_30d.json", "k3-unit-tests": "builds_k3-unit-tests_30d.json"}
CACHE_FILES = ("fail_signatures.json", "log_markers.json")


def _mtime(p):
    return datetime.fromtimestamp(os.path.getmtime(p), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _newer(lake, source, key, fetched):
    st = lake.get(source, key)
    return st is None or st["status"] != "ok" or not st["fetched_at"] or fetched > st["fetched_at"]


# ------------------------------------------------------------------ old P1 folder -> lake
def ingest_legacy(lake, folder):
    win = json.load(open(os.path.join(folder, "window.json"), encoding="utf-8"))
    raw, origin, n = os.path.join(folder, "raw"), "legacy:" + os.path.basename(os.path.normpath(folder)), {}
    for pl, fn in BUILD_FILE.items():
        p = os.path.join(raw, fn)
        if not os.path.exists(p):
            continue
        fetched, per = _mtime(p), {d: [] for d in days(win["since"], win["until"])}
        for b in json.load(open(p, encoding="utf-8")):
            if b["created_at"][:10] in per:
                per[b["created_at"][:10]].append(b)
        for d, bs in per.items():
            key = f"{pl}/{d}"
            if _newer(lake, "bk_builds", key, fetched):
                end = (ts(d + "T00:00:00Z") + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
                final = ts(fetched) >= ts(end) + BkBuilds.SETTLE and not any(b.get("state") in UNFINISHED for b in bs)
                lake.write("bk_builds", key, bs)
                lake.ok("bk_builds", key, d, len(bs), None, final, fetched, origin)
                n["bk_builds"] = n.get("bk_builds", 0) + 1
    p = os.path.join(raw, "gh_checks_30d.json")
    if os.path.exists(p):
        g = json.load(open(p, encoding="utf-8"))
        fetched = g.get("made") or _mtime(p)
        for node in g["prs"]:
            key = str(node["number"])
            if _newer(lake, "gh_prs", key, fetched):
                node = dict(node, fetched_at=fetched)
                lake.write("gh_prs", key, node)
                lake.ok("gh_prs", key, node["createdAt"][:10], len(node.get("commit_nodes") or []), node.get("updatedAt"), pr_is_final(node, fetched), fetched, origin)
                n["gh_prs"] = n.get("gh_prs", 0) + 1
        for sha, o in (g.get("orphan_commits") or {}).items():
            if _newer(lake, "gh_commits", sha, fetched):
                c = o["commit"]
                last = _suite_last([c])
                final = _all_concluded([c]) and (last is None or ts(fetched) >= ts(last) + GhCommits.SETTLE)
                lake.write("gh_commits", sha, dict(o, fetched_at=fetched))
                lake.ok("gh_commits", sha, (c.get("committedDate") or "")[:10], len(_suites([c])), last, final, fetched, origin)
                n["gh_commits"] = n.get("gh_commits", 0) + 1
    p = os.path.join(raw, "gh_run_jobs_30d.jsonl")
    if os.path.exists(p):
        fetched = _mtime(p)
        days_of = _run_days(lake)
        for line in open(p, encoding="utf-8"):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            key = str(o["run_id"])
            if _newer(lake, "gh_run_jobs", key, fetched):
                lake.write("gh_run_jobs", key, o)
                day = days_of.get(key) or min((j.get("created_at") or "9999")[:10] for j in o["jobs"] or [{}])
                lake.ok("gh_run_jobs", key, day, len(o["jobs"]), None, all(j.get("status") == "completed" for j in o["jobs"]), fetched, origin)
                n["gh_run_jobs"] = n.get("gh_run_jobs", 0) + 1
    _merge_cache(lake, raw)
    return n


def _run_days(lake):
    out = {}
    for k, _ in lake.keys("gh_prs"):
        for s in _suites((lake.read("gh_prs", k) or {}).get("commit_nodes") or []):
            if s.get("workflowRun"):
                out.setdefault(str(s["workflowRun"]["databaseId"]), s["createdAt"][:10])
    return out


def _merge_cache(lake, raw):
    """log evidence caches: union of keys, the lake copy wins on conflicts only when the folder has none."""
    cdir = os.path.join(lake.root, "cache")
    os.makedirs(cdir, exist_ok=True)
    for fn in CACHE_FILES:
        src, dst = os.path.join(raw, fn), os.path.join(cdir, fn)
        if not os.path.exists(src):
            continue
        a = json.load(open(dst, encoding="utf-8")) if os.path.exists(dst) else {}
        b = json.load(open(src, encoding="utf-8"))
        if isinstance(a, dict) and isinstance(b, dict):
            a.update(b)
            json.dump(a, open(dst, "w", encoding="utf-8"), indent=0)
        elif not os.path.exists(dst):
            shutil.copyfile(src, dst)


# ------------------------------------------------------------------ lake -> window folder in P1 format
def export_window(lake, since, until, out, note=""):
    raw = os.path.join(out, "raw")
    os.makedirs(raw, exist_ok=True)
    report, missing = {}, []
    json.dump(dict(since=since, until=until, note=note or "Exported from the ETL lake (LM-762-ci-resource/etl).",
                   pipelines=list(BK_PIPELINES), repo=REPO), open(os.path.join(out, "window.json"), "w", encoding="utf-8"), indent=1)
    builds = {}
    for pl in BK_PIPELINES:
        bs = []
        for d in days(since, until):
            part = lake.read("bk_builds", f"{pl}/{d}")
            if part is None:
                missing.append(f"bk_builds {pl}/{d}")
            bs += part or []
        bs = list({b["id"]: b for b in bs}.values())
        json.dump(bs, open(os.path.join(raw, BUILD_FILE[pl]), "w", encoding="utf-8"))
        builds[pl] = bs
        report[pl] = len(bs)
    # PRs open at some time in the window
    prs, made = [], []
    for k, _ in lake.keys("gh_prs"):
        doc = lake.read("gh_prs", k)
        if doc and doc["createdAt"] < until and (doc.get("updatedAt") or doc.get("closedAt") or until) >= since and (not doc.get("closedAt") or doc["closedAt"] >= since):
            prs.append(doc); made.append(doc.get("fetched_at") or "")
    prs.sort(key=lambda d: d["number"])
    have = {c["oid"] for d in prs for c in d.get("commit_nodes") or []}
    orph, orph_missing = {}, []
    for pl, bs in builds.items():
        for b in bs:
            if b.get("pull_request") and b.get("commit") and b["commit"] not in have and b["commit"] not in orph:
                o = lake.read("gh_commits", b["commit"])
                if o and o.get("commit"):
                    orph[b["commit"]] = dict(pr=o.get("pr") or str(b["pull_request"]["id"]), commit=o["commit"])
                else:
                    orph_missing.append(b["commit"])
    g = dict(made=min(made) if made else None, made_latest=max(made) if made else None, window=[since, until], repo=REPO,
             prs=prs, orphan_commits=orph, orphans_missing=sorted(set(orph_missing)))
    json.dump(g, open(os.path.join(raw, "gh_checks_30d.json"), "w", encoding="utf-8"), separators=(",", ":"))
    report.update(prs=len(prs), orphans=len(orph), orphans_missing=len(set(orph_missing)))
    # workflow runs of the window
    runs, nmiss = set(), 0
    for c in [c for d in prs for c in d.get("commit_nodes") or []] + [o["commit"] for o in orph.values()]:
        for s in _suites([c]):
            if s.get("workflowRun") and (s.get("app") or {}).get("slug") == "github-actions" and since <= s["createdAt"] < until:
                runs.add(str(s["workflowRun"]["databaseId"]))
    with open(os.path.join(raw, "gh_run_jobs_30d.jsonl"), "w", encoding="utf-8") as fo:
        for k in sorted(runs):
            o = lake.read("gh_run_jobs", k)
            if o is None:
                nmiss += 1
                continue
            fo.write(json.dumps(o, separators=(",", ":")) + "\n")
    report.update(runs=len(runs), runs_missing=nmiss)
    for fn in CACHE_FILES:
        src = os.path.join(lake.root, "cache", fn)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(raw, fn))
    report["missing_build_days"] = missing
    return report


def save_cache_back(lake, out):
    """after sample_fail_logs.py read new logs in the window folder, keep them in the lake cache."""
    _merge_cache(lake, os.path.join(out, "raw"))
