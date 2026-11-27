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
ingest_cache(lake, cache_dir, p1_folders): the same for ops-app/data/ci_impact_cache (Buildkite builds, GitHub Actions run jobs).
"""
import json
import os
import shutil
from datetime import datetime, timedelta, timezone

from core.pipeline import days, ts
from sources import BK_PIPELINES, REPO, UNFINISHED, GhPrs, BkBuilds, GhCommits, GhRunJobs, pr_is_final, _suite_last, _all_concluded, _suites

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


# ------------------------------------------------------------------ ops-app CI impact cache -> lake
GHA_CACHE_FILES = ("gha_runs.json", "gha_runs_test.json", "gha_runs_cpu_device.json")
FINAL_BK = ("passed", "failed", "canceled", "skipped", "not_run")


def _p1_jobs(folders):
    """job id -> (node, raw_log_url) from P1 exports (jobs_all*.csv): the cache strips agent / raw_log_url."""
    import csv
    out = {}
    for f in folders:
        for fn in ("jobs_all_30d.csv", "jobs_all.csv"):
            p = os.path.join(f, fn)
            if os.path.exists(p):
                for r in csv.DictReader(open(p, encoding="utf-8")):
                    out[r["job_id"]] = (r.get("node") or "", r.get("raw_log_url") or "")
    return out


def _enrich(builds, older, p1):
    """richest form: keep agent / raw_log_url from an older lake copy (same job id), else the node from a P1 csv;
    raw_log_url is a fixed URL per script job (checked against every P1 row) so it is filled when missing."""
    olds = {j["id"]: j for b in older or [] for j in b.get("jobs") or []}
    n = 0
    for b in builds:
        for j in b.get("jobs") or []:
            o = olds.get(j["id"]) or {}
            for k in ("agent", "raw_log_url"):
                if not j.get(k) and o.get(k):
                    j[k] = o[k]
            node, url = p1.get(j["id"], ("", ""))
            if not j.get("agent") and node:
                j["agent"] = {"meta_data": ["k8s:node=" + node], "_from": "P1 jobs_all csv (node only)"}
                n += 1
            if not j.get("raw_log_url") and j.get("type") == "script":
                j["raw_log_url"] = url or (f"https://api.buildkite.com/v2/organizations/lmcache/pipelines/{b['pipeline_slug']}"
                                           f"/builds/{b['number']}/jobs/{j['id']}/log.txt")
    return n


def ingest_cache(lake, cache_dir, p1_folders=(), dry_run=False):
    """Load ops-app/data/ci_impact_cache (read only) into the lake. Idempotent: a partition is written only when the
    cache copy is newer than the lake copy.
      bk_builds.json {slug#number: build}: per pipeline the build numbers must be contiguous (no build missing) from the
        first cached build on; only whole UTC days after the day of that build are stored, up to the last online fetch
        (after_meta.json 'until', else the file mtime) = fetched_at. final = the BkBuilds rule: fetched_at >= day end
        + 3 days and no unfinished build. pipeline / env are stripped as BkBuilds.fetch does.
      gha_runs*.json {run id: {run, jobs}}: the jobs carry the GhRunJobs fields (filter=all, every attempt);
        fetched_at = file mtime (the runs list is re-read on every online refresh, a new attempt is fetched again);
        final = every job completed (the GhRunJobs rule). Runs with no jobs are left to the fetcher.
      p1_folders: node / raw_log_url per job id, and their raw/fail_signatures.json into the log-evidence cache."""
    from collections import defaultdict
    n, why = defaultdict(int), defaultdict(int)
    origin = "cache:" + os.path.basename(os.path.normpath(cache_dir))
    p1 = _p1_jobs(p1_folders)
    # ---- Buildkite builds
    p = os.path.join(cache_dir, "bk_builds.json")
    if os.path.exists(p):
        meta = os.path.join(cache_dir, "after_meta.json")
        fetched = _mtime(p)
        if os.path.exists(meta):
            fetched = min(fetched, (json.load(open(meta, encoding="utf-8")) or {}).get("until") or fetched)
        allb = json.load(open(p, encoding="utf-8"))
        for pl in BK_PIPELINES:
            bs = sorted((b for b in allb.values() if b.get("pipeline_slug") == pl), key=lambda b: b["number"])
            if not bs:
                continue
            nums = [b["number"] for b in bs]
            gaps = [i for i in range(1, len(nums)) if nums[i] != nums[i - 1] + 1]
            first = bs[gaps[-1]] if gaps else bs[0]   # the cache is complete from this build on
            d0 = (ts(first["created_at"]).date() + timedelta(days=1)).isoformat()
            n[f"bk first whole day {pl}"] = d0
            per = defaultdict(list)
            for b in bs:
                if b["number"] >= first["number"]:
                    per[b["created_at"][:10]].append(b)
            for d in days(d0 + "T00:00:00Z", (ts(fetched).date() + timedelta(days=1)).isoformat() + "T00:00:00Z"):
                key = f"{pl}/{d}"
                if not _newer(lake, "bk_builds", key, fetched):
                    why["bk_builds lake newer or same"] += 1
                    continue
                out = []
                for b in per.get(d, []):
                    b = json.loads(json.dumps(b))
                    b.pop("pipeline", None); b.pop("env", None)
                    for j in b.get("jobs") or []:
                        j.pop("env", None)
                    out.append(b)
                end = (ts(d + "T00:00:00Z") + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
                final = ts(fetched) >= ts(end) + BkBuilds.SETTLE and all(b.get("state") in FINAL_BK for b in out)
                n["bk_builds"] += 1; n["bk_builds final"] += int(final); n["bk_builds rows"] += len(out)
                if dry_run:
                    continue
                n["bk jobs node from P1"] += _enrich(out, lake.read("bk_builds", key), p1)
                lake.write("bk_builds", key, out)
                lake.ok("bk_builds", key, d, len(out), None, final, fetched, origin)
    # ---- GitHub Actions run jobs
    for fn in GHA_CACHE_FILES:
        p = os.path.join(cache_dir, fn)
        if not os.path.exists(p):
            continue
        fetched = _mtime(p)
        for k, v in json.load(open(p, encoding="utf-8")).items():
            jobs = v.get("jobs") or []
            if not jobs:
                why["gh_run_jobs no jobs in cache"] += 1
                continue
            if not _newer(lake, "gh_run_jobs", k, fetched):
                why["gh_run_jobs lake newer or same"] += 1
                continue
            o = dict(run_id=int(k), jobs=[{x: (int(k) if x == "run_id" else j.get(x)) for x in GhRunJobs.KEEP} for j in jobs])
            final = all(j.get("status") == "completed" for j in o["jobs"])
            old = lake.read("gh_run_jobs", k)
            n["gh_run_jobs"] += 1; n["gh_run_jobs new"] += int(old is None); n["gh_run_jobs changed"] += int(old is not None and old != o)
            if dry_run:
                continue
            if old != o:
                lake.write("gh_run_jobs", k, o)
            lake.ok("gh_run_jobs", k, (v["run"].get("created_at") or "")[:10], len(o["jobs"]), None, final, fetched, origin)
    if not dry_run:
        for f in p1_folders:
            _merge_cache(lake, os.path.join(f, "raw"))
    return dict(n, skipped=dict(why))


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
