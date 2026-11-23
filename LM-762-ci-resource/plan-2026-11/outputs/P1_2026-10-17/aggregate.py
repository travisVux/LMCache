"""Step 5: aggregate jobs_all_30d.csv + raw/log_markers.json into cost_by_workload.csv,
cost_by_label.csv, build_level_summary.json, and print a markdown table to stdout."""
import csv, json, collections, os
from datetime import datetime


def pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def fnum(x, nd=1):
    return "UNKNOWN" if x is None else f"{x:.{nd}f}"


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


# per-workload detail is for the MP GPU suite (k3-unit-tests has one workload; build_report1130.py covers it)
rows = [r for r in csv.DictReader(open("jobs_all_30d.csv", encoding="utf-8")) if r.get("pipeline", "k3-multiprocess-test") == "k3-multiprocess-test"]
for r in rows:
    for k in ("wall_min", "queue_wait_min", "gpu_min"):
        r[k] = float(r[k]) if r[k] not in ("", "None") else None
    r["gpus"] = int(r["gpus"]) if r["gpus"] != "" else None
byid = {r["job_id"]: r for r in rows}


def final_of(r):
    while r["retried_in_job_id"] and r["retried_in_job_id"] in byid:
        r = byid[r["retried_in_job_id"]]
    return r


pr = [r for r in rows if r["is_pr"] == "1"]
started = [r for r in pr if r["started_at"]]
pr_builds_ran = {r["build_number"] for r in started}

# ---------------- startup share from sampled logs
markers = json.load(open("raw/log_markers.json", encoding="utf-8")) if os.path.exists("raw/log_markers.json") else {}


def startup(e):
    """setup = log start -> 'Environment ready' (checkout + deps install).
    engine = time the job waits for engine(s) to become ready:
      - harness-launched engines: 'Environment ready' -> '=== Running test:'
      - plus every in-test wait reported as '(took Ns)' / 'ready on port P (Ns)'
      - plus start->ready pairs for scripts that print no seconds (cpu_e2e, p2p)."""
    t0 = e["first_ts"]
    wall = float(e["wall_min"]) * 60
    if not e.get("env_ready"):  # SGLang setup prints no "Environment ready"; use the harness banner instead
        e["env_ready"] = next((t for t, s in e.get("events", []) if s.startswith("=== LMCache Multiprocessing Test")), None)
    if not t0 or not wall:
        return None
    env = e.get("env_ready") or e.get("launch")
    if env is None:
        return None
    setup = env - t0
    tst = e.get("test_start")
    engine = 0.0
    if e.get("launch") and tst and e.get("env_ready"):
        engine += tst - e["env_ready"]
        in_test = [w for w in e["waits"] if w[0] > tst + 1 and w[1] is not None]
    else:
        in_test = [w for w in e["waits"] if w[1] is not None]
    engine += sum(w[1] for w in in_test)
    if e["workload"] == "cpu_e2e_validation" or not e.get("launch"):
        engine += sum(b - a for a, b in e.get("pairs", []))
    return dict(setup=setup, engine=engine, wall=wall)


su = collections.defaultdict(list)
for e in markers.values():
    if float(e["wall_min"]) < 1.0:
        continue
    s = startup(e)
    if s:
        su[e["workload"]].append(s)

out = []
def is_noop(r):
    # adapter/blacklist skip: job passes in < 1 min without launching an engine
    return r["state"] == "passed" and r["wall_min"] is not None and r["wall_min"] < 1.0


for w in sorted({r["workload"] for r in started}):
    rs_all = [r for r in started if r["workload"] == w]
    noop = [r for r in rs_all if is_noop(r)]
    rs = [r for r in rs_all if not is_noop(r)]
    if not rs:
        continue
    fin = [r for r in rs if r["state"] in ("passed", "failed", "timed_out")]
    passed = [r for r in rs if r["state"] == "passed"]
    g = rs[0]["gpus"]
    first = [r for r in fin if not r["retry_source"]]
    first_fail = [r for r in first if r["state"] != "passed"]
    retried = [r for r in first_fail if r["retried_in_job_id"]]
    pass_after = [r for r in first_fail if final_of(r)["state"] == "passed"]
    builds_w = {r["build_number"] for r in rs}
    last_b = max(int(r["build_number"]) for r in rs)
    walls = [r["wall_min"] for r in fin]
    s = su.get(w, [])
    sp = [x["setup"] / x["wall"] * 100 for x in s]
    ep = [x["engine"] / x["wall"] * 100 for x in s]
    tp = [(x["setup"] + x["engine"]) / x["wall"] * 100 for x in s]
    gm_total = sum(r["wall_min"] * g for r in rs if r["wall_min"] is not None) if g is not None else None
    out.append(dict(
        workload=w, gpus=g if g is not None else "UNKNOWN",
        variants_in_latest_build=len({r["label"] for r in rs if int(r["build_number"]) == last_b}),
        pr_builds_with_workload=len(builds_w),
        jobs_per_build=len(rs) / len(builds_w),
        runs_30d=len(rs), noop_skip_runs_30d=len(noop),
        noop_skip_queue_wait_p50_min=pct([r["queue_wait_min"] for r in noop], 50),
        noop_labels=" ; ".join(sorted({r["label"] for r in noop})),
        finished_runs=len(fin), canceled_runs=sum(r["state"] == "canceled" for r in rs),
        p50_wall_min=pct(walls, 50), p90_wall_min=pct(walls, 90),
        p50_wall_passed_min=pct([r["wall_min"] for r in passed], 50),
        gpu_min_p50=None if g is None or pct(walls, 50) is None else pct(walls, 50) * g,
        gpu_min_total_30d=gm_total,
        gpu_min_per_pr_build=None if gm_total is None else gm_total / len(builds_w),
        queue_wait_p50_min=pct([r["queue_wait_min"] for r in rs], 50),
        queue_wait_p90_min=pct([r["queue_wait_min"] for r in rs], 90),
        log_samples=len(s),
        setup_pct_p50=pct(sp, 50), engine_start_pct_p50=pct(ep, 50), startup_pct_p50=pct(tp, 50),
        startup_min_p50=pct([(x["setup"] + x["engine"]) / 60 for x in s], 50),
        first_try_n=len(first),
        first_try_fail_n=len(first_fail),
        first_try_fail_pct=(100 * len(first_fail) / len(first)) if first else None,
        retried_n=len(retried),
        pass_after_retry_pct=(100 * len(pass_after) / len(first_fail)) if first_fail else None,
        retry_gpu_min_30d=None if g is None else sum(r["wall_min"] * g for r in rs if r["retry_source"] and r["wall_min"]),
        first_fail_exit_codes=" ".join(f"{k}:{v}" for k, v in collections.Counter(r["exit_status"] for r in first_fail).most_common()),
    ))

with open("cost_by_workload.csv", "w", newline="", encoding="utf-8") as f:
    wr = csv.DictWriter(f, list(out[0].keys()))
    wr.writeheader()
    for o in out:
        wr.writerow({k: (round(v, 2) if isinstance(v, float) else v) for k, v in o.items()})

lab = []
for l in sorted({r["label"] for r in started}):
    rs = [r for r in started if r["label"] == l]
    fin = [r for r in rs if r["state"] in ("passed", "failed", "timed_out")]
    first = [r for r in fin if not r["retry_source"]]
    g = rs[0]["gpus"]
    lab.append(dict(label=l, workload=rs[0]["workload"], engine=rs[0]["engine"], mode=rs[0]["mode"],
                    transport=rs[0]["transport"], gpus=g if g is not None else "UNKNOWN", runs_30d=len(rs),
                    p50_wall_min=pct([r["wall_min"] for r in fin], 50), p90_wall_min=pct([r["wall_min"] for r in fin], 90),
                    gpu_min_total_30d=None if g is None else sum(r["wall_min"] * g for r in rs if r["wall_min"]),
                    queue_wait_p50_min=pct([r["queue_wait_min"] for r in rs], 50),
                    first_try_fail_pct=(100 * sum(r["state"] != "passed" for r in first) / len(first)) if first else None))
with open("cost_by_label.csv", "w", newline="", encoding="utf-8") as f:
    wr = csv.DictWriter(f, list(lab[0].keys()))
    wr.writeheader()
    for o in lab:
        wr.writerow({k: (round(v, 2) if isinstance(v, float) else v) for k, v in o.items()})

# ---------------- build level
per_build = collections.defaultdict(float)
for r in started:
    if r["wall_min"] and r["gpus"] is not None:
        per_build[r["build_number"]] += r["wall_min"] * r["gpus"]
builds = json.load(open("raw/builds_30d.json", encoding="utf-8"))
bmeta = {str(b["number"]): b for b in builds}
full_pass = [b for b in pr_builds_ran if bmeta[b]["state"] == "passed"]
bdur = [(ts(bmeta[b]["finished_at"]) - ts(bmeta[b]["started_at"])).total_seconds() / 60
        for b in full_pass if bmeta[b]["finished_at"] and bmeta[b]["started_at"]]
allgm = sum(r["wall_min"] * r["gpus"] for r in rows if r["started_at"] and r["wall_min"] and r["gpus"] is not None)
summary = dict(
    pr_builds_total=sum(1 for b in builds if b.get("pull_request")),
    pr_builds_ran_suite=len(pr_builds_ran),
    pr_builds_ran_suite_by_state=dict(collections.Counter(bmeta[b]["state"] for b in pr_builds_ran)),
    distinct_prs=len({bmeta[b]["pull_request"]["id"] for b in pr_builds_ran}),
    skip_label_builds=sum(1 for b in builds if b.get("pull_request") and any(
        (j.get("name") or "").startswith(":fast_forward:") and j.get("state") == "passed" for j in b["jobs"])),
    gpu_min_total_pr=sum(per_build.values()),
    gpu_min_total_all_builds_incl_dev_and_nightly=allgm,
    gpu_min_per_pr_build_p50=pct(list(per_build.values()), 50),
    gpu_min_per_pr_build_p90=pct(list(per_build.values()), 90),
    gpu_min_per_passed_pr_build_p50=pct([per_build[b] for b in full_pass], 50),
    passed_pr_build_duration_min_p50=pct(bdur, 50),
    passed_pr_build_duration_min_p90=pct(bdur, 90),
    canceled_gpu_min_pr=sum(r["wall_min"] * r["gpus"] for r in started
                            if r["state"] == "canceled" and r["wall_min"] and r["gpus"] is not None),
    retry_gpu_min_pr=sum(r["wall_min"] * r["gpus"] for r in started
                         if r["retry_source"] and r["wall_min"] and r["gpus"] is not None),
    queue_wait_p50_all_gpu_jobs=pct([r["queue_wait_min"] for r in started if r["gpus"]], 50),
    queue_wait_p90_all_gpu_jobs=pct([r["queue_wait_min"] for r in started if r["gpus"]], 90),
    log_samples=len(markers),
)
json.dump(summary, open("build_level_summary.json", "w"), indent=1, default=str)
print(json.dumps(summary, indent=1, default=str))
for o in sorted(out, key=lambda o: -(o["gpu_min_total_30d"] or 0)):
    print(f"| {o['workload']} | {o['gpus']} | {o['jobs_per_build']:.2f} | {o['runs_30d']} | {fnum(o['p50_wall_min'])} | "
          f"{fnum(o['p90_wall_min'])} | {fnum(o['gpu_min_p50'])} | {fnum(o['gpu_min_total_30d'], 0)} | "
          f"{fnum(o['queue_wait_p50_min'])} | {fnum(o['startup_pct_p50'], 0)}% ({fnum(o['setup_pct_p50'], 0)} + "
          f"{fnum(o['engine_start_pct_p50'], 0)}), n={o['log_samples']} | {fnum(o['first_try_fail_pct'])}% "
          f"({o['first_try_fail_n']}/{o['first_try_n']}) | {fnum(o['pass_after_retry_pct'], 0)}% | {o['first_fail_exit_codes']} |")
