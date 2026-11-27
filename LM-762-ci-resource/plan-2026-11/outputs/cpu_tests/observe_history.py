"""History for the "Trend" tab (#obs/trend) — Git-as-database, no server.

Two sources, both small JSON files in observe_history/ (commit them, the folder IS the database):
  <YYYY-MM-DD>.json   one point per day from an observe_collect.py snapshot (last run of the day wins)
  baseline_mp.json    daily MP-pipeline cost from the P1 Buildkite dataset (../P1/jobs_all_30d.csv)

  python -I -X utf8 observe_history.py              # add a point from observe_snapshot.json
  python -I -X utf8 observe_history.py --baseline   # rebuild baseline_mp.json from P1 data
observe_collect.py calls add_point() after every collection. build_observe.py embeds load_all().
"""
import collections
import csv
import json
import os
import re
import statistics
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "observe_history")
SNAP = os.path.join(HERE, "observe_snapshot.json")
P1_JOBS = os.path.join(HERE, "..", "P1", "jobs_all_30d.csv")
P1_BUILDS = os.path.join(HERE, "..", "P1", "raw", "builds_30d.json")
sys.path.insert(0, HERE)


def ms(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def pct(a, p):
    if not a:
        return None
    s = sorted(a)
    return s[min(len(s) - 1, int(p * (len(s) - 1) + .5))]


def rnd(x, n=1):
    return None if x is None else round(x, n)


# ------------------------------------------------------------------ one point from a snapshot
def point(snap):
    from build_observe import CONFIG
    G, B = snap.get("gh") or {}, snap.get("bk")
    if snap.get("bk_at") and snap.get("bk_at") != snap.get("at"):
        B = None   # Buildkite half kept from an older run (no token): no Buildkite numbers for this day (round 2)
    c = G.get("counts") or {}
    p = dict(at=snap["at"], day=snap["at"][:10])
    p["prs"] = dict(open=c.get("open"), draft=c.get("draft"), approved=c.get("approved"), changes=c.get("changes"),
                    merged_unreleased=len(G.get("merged") or []), since=G.get("merged_since"))
    # approved, non-draft PRs whose newest commit has a failing merge gate
    if G.get("prs_gql"):
        merge_rx = [re.compile(g["re"]) for g in CONFIG["gates"] if CONFIG["gate_kind"].get(g["id"]) == "merge"]
        n = 0
        for pr in G["prs_gql"]["nodes"]:
            if pr.get("isDraft") or pr.get("reviewDecision") != "APPROVED":
                continue
            ru = ((pr["commits"]["nodes"] or [{}])[0].get("commit") or {}).get("statusCheckRollup") or {}
            for x in (ru.get("contexts") or {}).get("nodes", []):
                name = x.get("name") or x.get("context") or ""
                bad = x.get("conclusion") in ("FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "ACTION_REQUIRED") or x.get("state") in ("FAILURE", "ERROR")
                if bad and any(r.search(name) for r in merge_rx):
                    n += 1
                    break
        p["prs"]["approved_gate_fail"] = n
    # dev health: pass share of the last 10 finished dev builds per key pipeline
    p["dev"] = {}
    if B:
        by = collections.defaultdict(list)
        for b in B.get("dev_builds") or []:
            slug = (b.get("pipeline") or {}).get("slug") or (re.search(r"buildkite\.com/[^/]+/([^/]+)/builds", b.get("web_url") or "") or [None, None])[1]
            if b.get("state") in ("passed", "failed"):
                by[slug].append(b)
        for slug in [s for s, key in CONFIG["pipelines"] if key] + ["k3-comprehensive-test"]:
            bs = sorted(by.get(slug, []), key=lambda b: -b["number"])[:10]
            if bs:
                p["dev"][slug] = dict(passed=sum(b["state"] == "passed" for b in bs), n=len(bs), last=bs[0]["state"])
    t = [r for r in G.get("runs_dev") or [] if r.get("name") == "Test" and r.get("event") == "push" and r.get("conclusion") in ("success", "failure")][:10]
    if t:
        p["dev"]["gha-test"] = dict(passed=sum(r["conclusion"] == "success" for r in t), n=len(t), last=t[0]["conclusion"])
    # queue wait / build time of recent PR builds (same rule as the page: longest runnable->started gap)
    p["queue"] = {}
    for slug, bs in ((B or {}).get("recent") or {}).items():
        W, D = [], []
        for b in bs or []:
            js = [j for j in b.get("jobs") or [] if j.get("runnable_at") and j.get("started_at")]
            if js:
                W.append(max(ms(j["started_at"]) - ms(j["runnable_at"]) for j in js) / 60)
            if b.get("finished_at") and b.get("created_at"):
                D.append((ms(b["finished_at"]) - ms(b["created_at"])) / 60)
        p["queue"][slug] = dict(w50=rnd(pct(W, .5)), w90=rnd(pct(W, .9)), d50=rnd(pct(D, .5)),
                                passed=sum(b.get("state") == "passed" for b in bs or []), n=len(bs or []))
    pl = (B or {}).get("pipelines") or []
    p["load"] = dict(bk_running=sum(x.get("running_builds_count") or 0 for x in pl) if B else None,
                     bk_waiting=sum(x.get("waiting_jobs_count") or 0 for x in pl) if B else None,
                     gha_queued=G.get("gha_queued"), gha_running=G.get("gha_running"))
    nr = sorted(G.get("nightly_runs") or [], key=lambda r: r["created_at"])
    p["nightly"] = nr[-1].get("conclusion") or nr[-1].get("status") if nr else None
    rel = [r for r in G.get("releases") or [] if not r.get("draft") and re.match(CONFIG["main_tag_re"], r["tag_name"])]
    rel.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    st = next((r["tag_name"] for r in rel if re.match(CONFIG["stable_tag_re"], r["tag_name"])), None)
    p["release"] = dict(latest=rel[0]["tag_name"] if rel else None, stable=st)
    if rel:
        runs = sorted((G.get("publish_tags") or {}).get(rel[0]["tag_name"]) or [], key=lambda r: r["created_at"])
        p["release"]["publish"] = runs[-1].get("conclusion") or runs[-1].get("status") if runs else None
    return p


def add_point(snap=None):
    snap = snap or json.load(open(SNAP, encoding="utf-8"))
    os.makedirs(DIR, exist_ok=True)
    p = point(snap)
    path = os.path.join(DIR, p["day"] + ".json")
    old = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
    if old and old["at"] > p["at"]:
        return old  # never overwrite a newer point of the same day
    json.dump(p, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("history point", path)
    return p


# ------------------------------------------------------------------ 30-day baseline from P1 (MP pipeline)
def baseline():
    builds = {str(b["number"]): b for b in json.load(open(P1_BUILDS, encoding="utf-8"))}
    jobs = [j for j in csv.DictReader(open(P1_JOBS, encoding="utf-8")) if j["is_pr"] == "1"]
    D = collections.defaultdict(lambda: dict(builds=set(), gpu=0.0, cancel=0.0, retry=0.0, wait=[], st=collections.Counter()))
    for j in jobs:
        d = D[j["build_created"][:10]]
        g = float(j["gpu_min"] or 0)
        d["gpu"] += g
        if j["state"] == "canceled":
            d["cancel"] += g
        if j["retried"] == "True":
            d["retry"] += g
        if j["queue_wait_min"]:
            d["wait"].append(float(j["queue_wait_min"]))
        if j["build_number"] not in d["builds"]:
            d["builds"].add(j["build_number"])
            d["st"][(builds.get(j["build_number"]) or {}).get("state") or j["build_state"]] += 1
    rows = []
    for day in sorted(D):
        d = D[day]
        fin = d["st"]["passed"] + d["st"]["failed"]
        rows.append(dict(day=day, builds=len(d["builds"]), gpu_h=rnd(d["gpu"] / 60), cancel_h=rnd(d["cancel"] / 60), retry_h=rnd(d["retry"] / 60),
                         passed=d["st"]["passed"], failed=d["st"]["failed"], canceled=d["st"]["canceled"],
                         pass_rate=rnd(d["st"]["passed"] / fin, 3) if fin else None,
                         wait_p50=rnd(statistics.median(d["wait"])) if d["wait"] else None, wait_p90=rnd(pct(d["wait"], .9))))
    os.makedirs(DIR, exist_ok=True)
    out = dict(source="P1 Buildkite collector: k3-multiprocess-test PR builds (jobs_all_30d.csv)", made=datetime.now().strftime("%Y-%m-%d"), days=rows)
    json.dump(out, open(os.path.join(DIR, "baseline_mp.json"), "w", encoding="utf-8"), indent=1)
    print(f"baseline: {len(rows)} days, {sum(r['gpu_h'] for r in rows):.0f} GPU-h")


def load_all():
    """{points:[...], mp:[...], measured:{...}} for the page (small)."""
    pts, mp = [], None
    if os.path.isdir(DIR):
        for f in sorted(os.listdir(DIR)):
            if re.match(r"\d{4}-\d{2}-\d{2}\.json$", f):
                pts.append(json.load(open(os.path.join(DIR, f), encoding="utf-8")))
        bp = os.path.join(DIR, "baseline_mp.json")
        if os.path.exists(bp):
            mp = json.load(open(bp, encoding="utf-8"))
    meas = {}
    for k, f in (("k3_time", "k3_durations.json"), ("fastfail", "fastfail_savings.json")):
        fp = os.path.join(HERE, f)
        if os.path.exists(fp):
            d = json.load(open(fp, encoding="utf-8"))
            if k == "k3_time":
                d = {x: d[x] for x in ("build", "job_wall_s", "pytest_wall_s", "setup_s", "buckets")}
            meas[k] = d
    import report_model
    return dict(measured=meas, report=report_model.build())  # daily points stay on disk (observe_history/) for later use


if __name__ == "__main__":
    if "--baseline" in sys.argv:
        baseline()
    else:
        add_point()
