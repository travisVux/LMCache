"""How many GPU-hours would fast-fail cancel really save?  (task C / onboarding T1)

For every commit in the 30-day P1 window (k3-multiprocess-test PR builds) find the FIRST time a
trigger check failed on that commit, then count the MP GPU-minutes used AFTER that moment:
  - job started after T          -> whole job avoidable
  - job running at T             -> the part after T (x GPUs)
Triggers tried one by one and combined:
  gha_test   GitHub Actions "Test" (test.yml, CPU pytest, advisory today)
  quality    GitHub Actions "Code Quality" (required)
  k3_unit    Buildkite k3-unit-tests (required)
"Real fail" = the trigger never passed later on the same commit. NOTE: GHA re-runs reuse the same run
id (run_attempt), so a flaky fail that a re-run fixed shows only as "success" - real == incl_flaky here.
Also reported: how many hit MP builds PASSED anyway (cancel would have killed a good GPU run).

Inputs : ../P1/jobs_all_30d.csv, ../P1/raw/builds_30d.json (P1 collector)
Cache  : ff_cache_*.json (delete to refetch)
Output : fastfail_savings.json
  python -I -X utf8 fastfail_savings.py
"""
import collections
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime

S = os.path.dirname(os.path.abspath(__file__))
P1 = os.path.join(S, "..", "P1")
sys.path.insert(0, P1)
import bk_api  # noqa: E402

REPO = "LMCache/LMCache"
WF = {"gha_test": 188757477, "quality": 164322816}
WIN = ("2026-10-04", "2026-11-06")  # a bit wider than the MP window (2026-10-05 .. 11-04)


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def cached(name, fn):
    p = os.path.join(S, f"ff_cache_{name}.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    v = fn()
    json.dump(v, open(p, "w", encoding="utf-8"))
    return v


def gh(path):
    for i in range(4):
        p = subprocess.run(["gh", "api", "-H", "X-GitHub-Api-Version: 2022-11-28", path],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0:
            return json.loads(p.stdout)
        time.sleep(2 * (i + 1))
    raise RuntimeError(p.stderr[:200])


def first_fail_time(run_id):
    """completed_at of the earliest failed job in the run (all attempts)."""
    jobs = gh(f"repos/{REPO}/actions/runs/{run_id}/jobs?filter=all&per_page=100")["jobs"]
    t = [j["completed_at"] for j in jobs if j.get("conclusion") == "failure" and j.get("completed_at")]
    return min(t) if t else None


def gha_trigger(name):
    def fetch():
        # created= filter caps at 1000; split the window by week to stay below it
        runs, seen = [], set()
        d0 = datetime.fromisoformat(WIN[0])
        while d0.strftime("%Y-%m-%d") < WIN[1]:
            d1 = datetime.fromtimestamp(d0.timestamp() + 6 * 86400)
            win = (d0.strftime("%Y-%m-%d"), d1.strftime("%Y-%m-%d"))
            page = 1
            while True:
                d = gh(f"repos/{REPO}/actions/workflows/{WF[name]}/runs?created={win[0]}..{win[1]}&per_page=100&page={page}")
                for r in d["workflow_runs"]:
                    if r["id"] not in seen:
                        seen.add(r["id"])
                        runs.append({k: r[k] for k in ("id", "head_sha", "conclusion", "run_attempt", "created_at", "updated_at", "event")})
                if len(d["workflow_runs"]) < 100:
                    break
                page += 1
            d0 = datetime.fromtimestamp(d1.timestamp() + 86400)
        for r in runs:
            if r["conclusion"] == "failure":
                r["fail_at"] = first_fail_time(r["id"])
        return runs
    return cached(name, fetch)


def k3_unit():
    def fetch():
        out, url = [], (f"organizations/lmcache/pipelines/k3-unit-tests/builds?created_from={WIN[0]}T00:00:00Z"
                        f"&created_to={WIN[1]}T00:00:00Z&per_page=100&exclude_jobs=true")
        while url:
            d, link = bk_api.get(url)
            out += [{k: b.get(k) for k in ("number", "commit", "state", "created_at", "failing_at", "finished_at")} for b in d]
            url = bk_api.next_link(link)
        return out
    return cached("k3_unit", fetch)


# ---------------------------------------------------------------- per-commit trigger times
def trig_gha(runs):
    """sha -> (first fail time, real?) ; real = no later successful run on the same sha."""
    by = collections.defaultdict(list)
    for r in runs:
        by[r["head_sha"]].append(r)
    out = {}
    for sha, rs in by.items():
        fails = [ts(r.get("fail_at") or r["updated_at"]) for r in rs if r["conclusion"] == "failure"]
        if fails:
            out[sha] = (min(fails), not any(r["conclusion"] == "success" for r in rs))
    return out


def trig_k3(builds):
    by = collections.defaultdict(list)
    for b in builds:
        by[b["commit"]].append(b)
    out = {}
    for sha, bs in by.items():
        fails = [ts(b["failing_at"] or b["finished_at"]) for b in bs if b["state"] == "failed" and (b["failing_at"] or b["finished_at"])]
        if fails:
            out[sha] = (min(fails), not any(b["state"] == "passed" for b in bs))
    return out


def main():
    builds = json.load(open(os.path.join(P1, "raw", "builds_30d.json"), encoding="utf-8"))
    sha_of = {str(b["number"]): b["commit"] for b in builds}
    jobs = [j for j in csv.DictReader(open(os.path.join(P1, "jobs_all_30d.csv"), encoding="utf-8")) if j["is_pr"] == "1"]
    total_gpu_min = sum(float(j["gpu_min"] or 0) for j in jobs)
    n_builds = len({j["build_number"] for j in jobs})

    T = {"gha_test": trig_gha(gha_trigger("gha_test")), "quality": trig_gha(gha_trigger("quality")), "k3_unit": trig_k3(k3_unit())}

    def combo(names):
        out = {}
        for n in names:
            for sha, (t, real) in T[n].items():
                if sha not in out or t < out[sha][0]:
                    out[sha] = (t, real)
        return out

    def saved(trig, real_only):
        mins, hit_builds, hit_shas = 0.0, set(), set()
        for j in jobs:
            sha = sha_of.get(j["build_number"])
            if sha not in trig:
                continue
            t, real = trig[sha]
            if real_only and not real:
                continue
            g = int(j["gpus"] or 1)
            st, fi = ts(j["started_at"]), ts(j["finished_at"])
            if not st or not fi:
                continue
            # job created before the build was even triggered by this commit? still counts: cancel at t
            if st >= t:
                m = float(j["gpu_min"] or 0)
            elif fi > t:
                m = (fi - t) / 60 * g
            else:
                m = 0
            if m > 0:
                mins += m; hit_builds.add(j["build_number"]); hit_shas.add(sha)
        return dict(gpu_hours=round(mins / 60, 1), share=round(mins / total_gpu_min, 4), mp_builds=len(hit_builds), commits=len(hit_shas))

    sets = {"gha_test": ["gha_test"], "quality": ["quality"], "k3_unit": ["k3_unit"],
            "required (quality+k3_unit)": ["quality", "k3_unit"], "all three": ["gha_test", "quality", "k3_unit"]}
    res = {}
    for label, names in sets.items():
        tr = combo(names)
        res[label] = dict(real=saved(tr, True), incl_flaky=saved(tr, False),
                          failed_commits=len(tr), real_failed_commits=sum(1 for v in tr.values() if v[1]))
    out = dict(window="2026-10-05..2026-11-04 (k3-multiprocess-test PR builds)", mp_pr_gpu_hours=round(total_gpu_min / 60),
               mp_pr_builds=n_builds, mp_commits=len({sha_of.get(j["build_number"]) for j in jobs}), triggers=res)
    json.dump(out, open(os.path.join(S, "fastfail_savings.json"), "w"), indent=1)
    print(f"MP PR GPU-h {total_gpu_min/60:.0f} in {n_builds} builds")
    for k, v in res.items():
        print(f"  {k:28s} real {v['real']['gpu_hours']:7.1f} GPU-h ({100*v['real']['share']:4.1f}%) {v['real']['mp_builds']:3d} builds"
              f" | incl. flaky {v['incl_flaky']['gpu_hours']:7.1f} ({100*v['incl_flaky']['share']:4.1f}%)"
              f" | failed commits {v['failed_commits']} (real {v['real_failed_commits']})")


if __name__ == "__main__":
    main()
