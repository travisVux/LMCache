"""Report 1130: reproducible 30-day PR CI baseline (Jira LM-1130). Third top view of the page (#r1130/...).

  python -I -X utf8 build_report1130.py    # analyse local data -> report1130.json -> rewrite the R1130 blocks

Inputs (local files only, made by the P1 steps listed in the Reproduce tab):
  ../P1/window.json                fixed window [since, until) UTC
  ../P1/jobs_all_30d.csv           Buildkite job attempts, k3-multiprocess-test + k3-unit-tests (GPU)
  ../P1/raw/builds*_30d.json       Buildkite builds (build times)
  ../P1/gh_jobs_30d.csv            GitHub Actions job attempts on PR commits (CPU)
  ../P1/pr_30d.csv, pr_commit_30d.csv, ttg_30d.csv, retry_events_30d.csv, join_quality.json
  ../P1/raw/fail_signatures.json   evidence lines for failed-then-retried attempts
  report_data.json (weekly / monthly merges), ops_ci_24h.json + ops_hist/ (last 24 h, for tracking)
Units: GPU-min = job execution minutes x GPUs the job asks for. job-min = job execution minutes (one runner / agent).
Queue (waiting for an agent / runner) is never added to execution.
"""
import collections
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
P1 = os.path.normpath(os.path.join(HERE, "..", "P1"))
sys.path.insert(0, P1)
from build_jobs_table import GPU as GPU_MAP, parse_label  # noqa: E402  (same GPU-per-workload map as the baseline)

PAGE = str(Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
OUT = os.path.join(HERE, "report1130.json")
PIPES = {"k3-multiprocess-test": ["MP suite (k3-multiprocess-test)", "Bộ MP (k3-multiprocess-test)"],
         "k3-unit-tests": ["Unit tests (k3-unit-tests)", "Unit test (k3-unit-tests)"]}
CLS = {"infra": ["infrastructure (evidence in log)", "hạ tầng (có bằng chứng trong log)"],
       "test": ["test failed (evidence in log)", "test fail (có bằng chứng trong log)"],
       "config": ["code / config error", "lỗi code / cấu hình"],
       "unknown": ["unknown (no evidence)", "chưa rõ (không có bằng chứng)"]}
SIG = {"git": ["git checkout failed", "git checkout lỗi"], "network": ["network / download", "mạng / tải về"],
       "interrupted": ["job killed by a signal", "job bị kill bằng signal"], "agent_lost": ["agent / pod lost", "mất agent / pod"],
       "gpu_not_free": ["no free GPU", "không có GPU trống"], "gpu_memory": ["GPU out of memory", "GPU hết bộ nhớ"],
       "disk": ["disk full", "đầy ổ đĩa"], "registry": ["image registry", "registry image"],
       "not_implemented": ["test script missing for this engine", "thiếu script test cho engine này"],
       "perf_threshold": ["performance threshold missed", "trượt ngưỡng hiệu năng"], "test_assert": ["test assertion", "assert của test"],
       "test_failed": ["test reported failed", "test báo fail"], "engine_start": ["engine did not start", "engine không khởi động"],
       "none": ["no signature in log", "log không có dấu hiệu"], "no log read": ["log not read", "chưa đọc log"],
       "no_log": ["log not readable", "không đọc được log"], "GitHub logs not read": ["GitHub logs not read", "chưa đọc log GitHub"],
       "startup_failure": ["workflow startup failure", "workflow lỗi khởi động"]}


def pct(a, p):
    a = sorted(x for x in a if x is not None)
    return a[min(len(a) - 1, int(p * (len(a) - 1) + .5))] if a else None


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def r1(x):
    return None if x is None else round(x, 1)


def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def mins(a, b):
    return None if not a or not b else (dt(b) - dt(a)).total_seconds() / 60


def csvr(name):
    p = os.path.join(P1, name)
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []


def p5090(vals, k=1.0, nd=1):
    """p50 / p90 of vals scaled by k (e.g. 1/60 for hours)."""
    a = [v * k for v in vals if v is not None]
    rr = (lambda x: None if x is None else round(x, nd))
    return dict(p50=rr(pct(a, .5)), p90=rr(pct(a, .9)), n=len(a))


def hist_bins(vals, n=12, step=0.5):
    """equal-width bins up to the p95; everything above goes in the last bin."""
    if not vals:
        return None
    top = pct(vals, .95) or max(vals)
    w = max(top / n, step)
    w = round(w / step) * step or step
    bins = [dict(lo=round(i * w, 1), hi=round((i + 1) * w, 1), n=0) for i in range(n)]
    for v in vals:
        bins[min(n - 1, int(v // w))]["n"] += 1
    bins[-1]["open"] = True
    return dict(bins=bins, p50=r1(pct(vals, .5)), p90=r1(pct(vals, .9)), n=len(vals))


def sha12(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:12]
    except OSError:
        return None


def analyze():
    WIN = json.load(open(os.path.join(P1, "window.json"), encoding="utf-8"))
    since, until = WIN["since"], WIN["until"]
    inwin = lambda t: bool(t) and since <= t.replace(".000Z", "Z") < until if t else False
    days = (dt(until) - dt(since)).days
    window = [since[:10], (dt(until) - timedelta(days=1)).strftime("%Y-%m-%d")]
    jobs = [r for r in csvr("jobs_all_30d.csv") if r["is_pr"] == "1" and inwin(r["build_created"])]
    ran = [r for r in jobs if r["started_at"]]
    by_id = {r["job_id"]: r for r in csvr("jobs_all_30d.csv")}

    # ---------------- GPU baseline (Buildkite), per pipeline + together
    builds = {}
    for slug, fn in (("k3-multiprocess-test", "builds_30d.json"), ("k3-unit-tests", "builds_k3-unit-tests_30d.json")):
        p = os.path.join(P1, "raw", fn)
        if os.path.exists(p):
            builds[slug] = [b for b in json.load(open(p, encoding="utf-8")) if b.get("pull_request") and inwin(b["created_at"])]
    pipes = {}
    for slug, name in PIPES.items():
        rs = [r for r in ran if r["pipeline"] == slug]
        bs = builds.get(slug, [])
        by_pr = collections.defaultdict(set)
        gpr = collections.defaultdict(float)
        for b in bs:
            by_pr[str(b["pull_request"]["id"])].add(b["number"])
        for r in rs:
            gpr[r["pr"]] += f(r["gpu_min"]) or 0
        passed = [b for b in bs if b["state"] == "passed" and b.get("finished_at")]
        fin = [r for r in rs if r["state"] in ("passed", "failed", "timed_out")]
        first = [r for r in fin if not r["retry_source"]]
        gm = sum(f(r["gpu_min"]) or 0 for r in rs)
        pipes[slug] = dict(name=name, builds=len(bs), builds_ran=len({r["build_number"] for r in rs}), prs=len(by_pr), jobs=len(rs),
                           gpu_h=round(gm / 60, 1), gpu_h_day=round(gm / 60 / days, 1), job_h=round(sum(f(r["wall_min"]) or 0 for r in rs) / 60, 1),
                           builds_pr=p5090([len(v) for v in by_pr.values()], 1, 0), gpu_pr=p5090(list(gpr.values()), 1 / 60),
                           job_exec=p5090([f(r["wall_min"]) for r in fin]), job_queue=p5090([f(r["queue_wait_min"]) for r in rs]),
                           build_e2e=p5090([mins(b["created_at"], b["finished_at"]) for b in passed]),
                           build_run=p5090([mins(b["started_at"], b["finished_at"]) for b in passed if b.get("started_at")]),
                           first_fail_pct=round(100 * sum(r["state"] != "passed" for r in first) / len(first), 1) if first else None,
                           by_state=dict(collections.Counter(b["state"] for b in bs)))
    per_build = collections.defaultdict(float)
    for r in ran:
        per_build[(r["pipeline"], r["build_number"])] += f(r["gpu_min"]) or 0
    build_gpu = dict(mp_build_gpu_p50=r1(pct([v for (pl, _), v in per_build.items() if pl == "k3-multiprocess-test"], .5)),
                     unit_build_gpu_p50=r1(pct([v for (pl, _), v in per_build.items() if pl == "k3-unit-tests"], .5)))
    gpu_pr = collections.defaultdict(float)
    daily = collections.defaultdict(lambda: [0.0, 0.0])
    for r in ran:
        g = f(r["gpu_min"]) or 0
        gpu_pr[r["pr"]] += g
        daily[r["build_created"][:10]][1 if r["retried"] == "True" else 0] += g
    tot = sum(gpu_pr.values())
    dl = [(dt(since) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    gpu = dict(window=window, days=days, gpu_h=round(tot / 60, 1), gpu_h_day=round(tot / 60 / days, 1), prs=len(gpu_pr),
               gpu_pr=p5090(list(gpu_pr.values()), 1 / 60), pipes=pipes,
               series=[dict(d=d, a=round(daily[d][0] / 60, 1), b=round(daily[d][1] / 60, 1)) for d in dl],
               pr_hist=hist_bins([v / 60 for v in gpu_pr.values()]),
               cancel_gpu_h=round(sum(f(r["gpu_min"]) or 0 for r in ran if r["state"] == "canceled") / 60, 1))

    # ---------------- what one PR costs: merged PRs (cost until merge) or all PRs; run time only or run + queued time
    merged_prs = {r["pr"] for r in csvr("pr_30d.csv") if r.get("merged")}
    gpu_q = collections.defaultdict(float)
    for r in ran:   # queued = agent wait (job runnable -> started) x GPUs the job asks for
        gpu_q[r["pr"]] += (f(r["gpu_min"]) or 0) + (f(r["queue_wait_min"]) or 0) * (f(r["gpus"]) or 0)

    def cost_views(run, withq, step):
        out = {}
        for sc, keep in (("merged", lambda k: k in merged_prs), ("all", lambda k: True)):
            for qk, d in (("run", run), ("q", withq)):
                vals = [v / 60 for k, v in d.items() if keep(k)]
                out[f"{sc}_{qk}"] = dict(hist=hist_bins(vals, step=step), stats=p5090(vals, 1, 1), total=round(sum(vals), 1), prs=len(vals))
        return out
    gpu["views"] = cost_views(gpu_pr, gpu_q, 0.5)
    gpu["queue_h"] = round((sum(gpu_q.values()) - tot) / 60, 1)

    # ---------------- CPU baseline (GitHub Actions jobs on PR commits)
    gj = [r for r in csvr("gh_jobs_30d.csv") if inwin(r["suite_created"])]
    for r in gj:
        r["x"] = f(r["exec_min"]) or 0.0
    cpr = collections.defaultdict(float)
    runs_pr = collections.defaultdict(set)
    cday = collections.defaultdict(lambda: [0.0, 0.0])
    wf = collections.defaultdict(lambda: dict(min=0.0, jobs=0, rerun=0, rerun_min=0.0, ex=[], sd=[], runs=set()))
    for r in gj:
        cpr[r["pr"]] += r["x"]
        runs_pr[r["pr"]].add(r["run_url"])
        cday[r["suite_created"][:10]][1 if r["replaced"] == "1" else 0] += r["x"]
        w = wf[r["workflow"]]
        w["min"] += r["x"]; w["jobs"] += 1; w["runs"].add(r["run_url"])
        w["ex"].append(r["x"]); w["sd"].append(f(r["start_delay_min"]))
        if r["replaced"] == "1":
            w["rerun"] += 1; w["rerun_min"] += r["x"]
    ctot = sum(cpr.values())
    rer = sum(r["x"] for r in gj if r["replaced"] == "1")
    cq = [r for r in gj if r["job"] == "Check code quality"]
    pcs = csvr("pr_commit_30d.csv")
    push_pr = collections.Counter(r["pr"] for r in pcs if inwin(r["first_ci_at"]) and int(r["gha_jobs"] or 0) + int(r["mp_builds"] or 0) + int(r["unit_builds"] or 0) > 0)
    cpu = dict(job_h=round(ctot / 60, 1), job_h_day=round(ctot / 60 / days, 1), jobs=len(gj), runs=len({r["run_url"] for r in gj}), prs=len(cpr),
               job_pr=p5090(list(cpr.values()), 1 / 60), runs_pr=p5090([len(v) for v in runs_pr.values()], 1, 0),
               pushes_pr=p5090(list(push_pr.values()), 1, 0),
               exec_all=p5090([r["x"] for r in gj]), delay_all=p5090([f(r["start_delay_min"]) for r in gj]),
               exec_cq=p5090([r["x"] for r in cq]), delay_cq=p5090([f(r["start_delay_min"]) for r in cq]),
               rerun_h=round(rer / 60, 1), rerun_share=round(100 * rer / ctot, 1) if ctot else None, rerun_jobs=sum(1 for r in gj if r["replaced"] == "1"),
               series=[dict(d=d, a=round(cday[d][0] / 60, 1), b=round(cday[d][1] / 60, 2)) for d in dl],
               workflows=sorted([dict(name=k, job_h=round(v["min"] / 60, 1), share=round(100 * v["min"] / ctot, 1) if ctot else 0, jobs=v["jobs"], runs=len(v["runs"]),
                                      exec=p5090(v["ex"]), delay=p5090(v["sd"]), rerun=v["rerun"], rerun_h=round(v["rerun_min"] / 60, 1)) for k, v in wf.items()],
                                key=lambda x: -x["job_h"]),
               pr_hist=hist_bins([v / 60 for v in cpr.values()], step=0.5))
    cpu_q = collections.defaultdict(float)
    for r in gj:   # queued = start delay (runner queue + wait for earlier jobs of the same workflow run)
        cpu_q[r["pr"]] += r["x"] + (f(r["start_delay_min"]) or 0)
    cpu["views"] = cost_views(cpr, cpu_q, 0.5)
    cpu["queue_h"] = round((sum(cpu_q.values()) - ctot) / 60, 1)

    # ---------------- time to green (merged PRs) + merges per week / month
    tt = csvr("ttg_30d.csv")
    for r in tt:
        for k in ("dco_min", "quality_min", "unit_min", "mp_min", "all_green_min", "wait_for_full_label_min", "mp_exec_min", "mp_queue_min", "merge_after_green_min", "pr_open_to_merge_h"):
            r[k] = f(r[k])
        r["cpu_min"] = max(r["dco_min"], r["quality_min"]) if r["dco_min"] is not None and r["quality_min"] is not None else None
    green = [r for r in tt if r["all_green_min"] is not None]
    lab = [r for r in green if (r["wait_for_full_label_min"] or 0) > 1]
    comp = lambda k, en, vi, rows=green, scale=1 / 60: dict(key=k, label=[en, vi], note=NOTE.get(k), **p5090([r[k] for r in rows], scale))
    NOTE = {"cpu_min": ["DCO + Check code quality", "DCO + Check code quality"],
            "wait_for_full_label_min": ["Only PRs whose 'full' label came after the last push", "Chỉ PR được gắn 'full' sau lần push cuối"],
            "mp_queue_min": ["MP build created → started", "Build MP tạo → bắt đầu"], "mp_exec_min": ["MP build started → finished", "Build MP bắt đầu → xong"],
            "merge_after_green_min": ["All checks green → merge", "Mọi check xanh → merge"]}
    ttg = dict(n=len(tt), green=len(green), not_green=[dict(pr=r["pr"], missing=r["not_green"]) for r in tt if r["not_green"]],
               all=p5090([r["all_green_min"] for r in green], 1 / 60), hist=hist_bins([r["all_green_min"] / 60 for r in green], step=1),
               label_n=len(lab), label_share=round(100 * len(lab) / len(green)) if green else None,
               comps=[comp("cpu_min", "CPU checks green", "Check CPU xanh"),
                      comp("unit_min", "k3-unit-tests green", "k3-unit-tests xanh"),
                      comp("mp_min", "k3-multiprocess-test green", "k3-multiprocess-test xanh"),
                      comp("wait_for_full_label_min", "↳ wait for 'full' label", "↳ chờ nhãn 'full'", lab),
                      comp("mp_queue_min", "↳ MP build queued", "↳ build MP chờ chạy"),
                      comp("mp_exec_min", "↳ MP build running", "↳ build MP chạy"),
                      comp("merge_after_green_min", "Green → merged", "Xanh → merge")],
               open_to_merge=p5090([r["pr_open_to_merge_h"] for r in tt], 1),
               no_label=p5090([r["all_green_min"] for r in green if (r["wait_for_full_label_min"] or 0) <= 1], 1 / 60))
    RD = json.load(open(os.path.join(HERE, "report_data.json"), encoding="utf-8")) if os.path.exists(os.path.join(HERE, "report_data.json")) else {}
    mp_ = [x for x in RD.get("merged_prs") or [] if x.get("m")]
    wk, mo = collections.defaultdict(list), collections.defaultdict(list)
    for x in mp_:
        m = dt(x["m"])
        lat = (m - dt(x["c"])).total_seconds() / 3600 if x.get("c") else None
        wk[(m - timedelta(days=m.weekday())).strftime("%Y-%m-%d")].append(lat)
        mo[m.strftime("%Y-%m")].append(lat)
    rd_end = RD.get("end") or ""
    mk = lambda d, k, full: dict(k=k, n=len(d[k]), p50=r1(pct(d[k], .5)), p90=r1(pct(d[k], .9)), partial=not full)
    weeks = [mk(wk, k, (dt(k + "T00:00:00Z") + timedelta(days=7)).strftime("%Y-%m-%d") <= rd_end) for k in sorted(wk)]
    months = [mk(mo, k, k < rd_end[:7]) for k in sorted(mo)]
    if weeks and weeks[0]["k"] < (RD.get("start") or ""):
        weeks[0]["partial"] = True
    if months and months[0]["k"] < (RD.get("start") or "")[:7] + "x" and (RD.get("start") or "")[8:10] != "01":
        months[0]["partial"] = True
    merges = dict(weeks=weeks, months=months, start=RD.get("start"), end=rd_end, window_n=len(tt),
                  window_lat=p5090([r["pr_open_to_merge_h"] for r in tt], 1))

    # ---------------- retry: first attempt failed, then the same work ran again
    ev = csvr("retry_events_30d.csv")
    for e in ev:
        e["lost"] = f(e["lost_gpu_min"]) if e["system"] == "Buildkite" else f(e["lost_min"])
    def first_att(rows_):
        out = collections.defaultdict(lambda: [0, 0])
        for k, ok in rows_:
            out[k][0] += 1
            out[k][1] += 0 if ok else 1
        return out
    den = first_att(((("Buildkite", r["pipeline"], r["workload"]), r["state"] == "passed") for r in ran
                     if r["state"] in ("passed", "failed", "timed_out") and not r["retry_source"]))
    den.update(first_att(((("GitHub Actions", r["workflow"], r["step"]), r["conclusion"] == "SUCCESS") for r in gj
                          if r["attempt"] == "1" and r["conclusion"] in ("SUCCESS", "FAILURE", "TIMED_OUT", "STARTUP_FAILURE"))))
    steps = collections.defaultdict(lambda: dict(n=0, ok=0, again=0, lost=0.0, cls=collections.Counter(), kinds=collections.Counter()))
    for e in ev:
        for st in e["step"].split(","):
            k = (e["system"], e["pipeline"], st)
            s = steps[k]
            s["n"] += 1
            s["ok"] += e["then"] == "passed"
            s["again"] += e["then"] in ("failed", "failure", "timed_out")
            s["lost"] += (e["lost"] or 0) / max(1, len(e["step"].split(",")))
            s["cls"][e["cls"]] += 1
            s["kinds"][e["kind"]] += 1
    step_rows = []
    for (sy, pl, st), s in steps.items():
        d = den.get((sy, pl, st), [0, 0])
        step_rows.append(dict(system=sy, pipeline=pl, step=st, first=d[0], first_fail=d[1], fail_pct=round(100 * d[1] / d[0], 1) if d[0] else None,
                              n=s["n"], ok=s["ok"], again=s["again"], lost_h=round(s["lost"] / 60, 1), unit="GPU-h" if sy == "Buildkite" else "job-h",
                              cls=dict(s["cls"]), kinds=dict(s["kinds"])))
    step_rows.sort(key=lambda x: (x["system"] != "Buildkite", -x["lost_h"]))
    bycls = {}
    for c in CLS:
        es = [e for e in ev if e["cls"] == c]
        bycls[c] = dict(n=len(es), ok=sum(e["then"] == "passed" for e in es),
                        gpu_h=round(sum(e["lost"] or 0 for e in es if e["system"] == "Buildkite") / 60, 1),
                        cpu_h=round(sum(e["lost"] or 0 for e in es if e["system"] != "Buildkite") / 60, 1))
    sigs = collections.defaultdict(lambda: dict(n=0, cls="", line="", gpu=0.0))
    for e in ev:
        s = sigs[e["evidence"]]
        s["n"] += 1; s["cls"] = e["cls"]; s["gpu"] += (e["lost"] or 0) if e["system"] == "Buildkite" else 0
        if e["evidence_line"] and not s["line"]:
            s["line"] = e["evidence_line"]
    bk_ev = [e for e in ev if e["system"] == "Buildkite"]
    gh_ev = [e for e in ev if e["system"] != "Buildkite"]
    retry = dict(n=len(ev), bk=len(bk_ev), gh=len(gh_ev), ok=sum(e["then"] == "passed" for e in ev),
                 bk_ok=sum(e["then"] == "passed" for e in bk_ev), gh_ok=sum(e["then"] == "passed" for e in gh_ev),
                 gpu_h=round(sum(e["lost"] or 0 for e in bk_ev) / 60, 1), cpu_h=round(sum(e["lost"] or 0 for e in gh_ev) / 60, 1),
                 share_gpu=round(100 * sum(e["lost"] or 0 for e in bk_ev) / tot, 1) if tot else None,
                 kinds=dict(collections.Counter(e["kind"] for e in ev)), auto=sum(1 for e in ev if e["retry_type"] == "automatic"),
                 bycls=bycls, steps=step_rows[:40],
                 sigs=sorted([dict(sig=k, name=SIG.get(k, [k, k]), cls=v["cls"], n=v["n"], gpu_h=round(v["gpu"] / 60, 1), line=v["line"]) for k, v in sigs.items()], key=lambda x: -x["n"]),
                 per_day_gpu=round(sum(e["lost"] or 0 for e in bk_ev) / 60 / days, 2))
    # queued time of the failed attempts that ran again (Buildkite job retries); "lost" above is run time only
    retry["gpu_h_queue_add"] = round(sum((f(r["queue_wait_min"]) or 0) * (f(r["gpus"]) or 0) for r in ran
                                         if r["retried"] == "True" and r["state"] in ("failed", "timed_out")) / 60, 1)
    # retries that never pass: every attempt of the same work (pipeline, PR, commit, job label) across job retries and new builds
    sig_by_job = {}
    sp = os.path.join(P1, "raw", "fail_signatures.json")
    if os.path.exists(sp):
        sig_by_job = json.load(open(sp, encoding="utf-8"))
    chains = collections.defaultdict(list)
    for r in ran:
        if r["state"] in ("passed", "failed", "timed_out"):
            chains[(r["pipeline"], r["pr"], r["commit"], r["label"])].append(r)
    tb = {k: dict(tries=k, passed=0, never=0, gpu_never=0.0, gpu_never_q=0.0, hours=[]) for k in (1, 2, 3, 4, 5)}
    top = collections.defaultdict(lambda: dict(chains=0, tries=0, gpu=0.0, gpu_q=0.0, hours=[], sig=collections.Counter(), cls=collections.Counter(), prs=set()))
    for key, rs in chains.items():
        rs.sort(key=lambda r: r["started_at"])
        n, ok = len(rs), any(r["state"] == "passed" for r in rs)
        b = tb[min(n, 5)]
        if ok:
            b["passed"] += 1
            continue
        g = sum(f(r["gpu_min"]) or 0 for r in rs)
        gq = g + sum((f(r["queue_wait_min"]) or 0) * (f(r["gpus"]) or 0) for r in rs)
        hrs = (mins(rs[0]["started_at"], rs[-1]["finished_at"] or rs[-1]["started_at"]) or 0) / 60
        b["never"] += 1; b["gpu_never"] += g; b["gpu_never_q"] += gq; b["hours"].append(hrs)
        if n >= 2:
            t = top[(key[0], rs[0]["workload"] or key[3])]
            t["chains"] += 1; t["tries"] += n; t["gpu"] += g; t["gpu_q"] += gq; t["hours"].append(hrs); t["prs"].add(key[1])
            for r in rs:
                sg = sig_by_job.get(r["job_id"])
                if sg:
                    t["sig"][sg.get("sig")] += 1; t["cls"][sg.get("cls")] += 1
    NONRETRY = ("config", "test")   # the same failure on every try: retrying does not help (infra = may pass on retry)
    tops = []
    for (pl, wl), t in top.items():
        cls = t["cls"].most_common(1)[0][0] if t["cls"] else "unknown"
        sig = t["sig"].most_common(1)[0][0] if t["sig"] else None
        tops.append(dict(pipeline=pl, workload=wl, chains=t["chains"], tries=t["tries"], prs=len(t["prs"]), gpu_h=round(t["gpu"] / 60, 1),
                         gpu_h_q=round(t["gpu_q"] / 60, 1), hours=p5090(t["hours"], 1, 1), sig=sig, sig_name=SIG.get(sig, [sig, sig]) if sig else None,
                         cls=cls, nonretry=cls in NONRETRY))
    tops.sort(key=lambda x: -x["gpu_h"])
    multi = [b for k, b in tb.items() if k >= 2]
    retry["never"] = dict(
        bins=[dict(tries=b["tries"], passed=b["passed"], never=b["never"], gpu_h=round(b["gpu_never"] / 60, 1), gpu_h_q=round(b["gpu_never_q"] / 60, 1),
                   hours=p5090(b["hours"], 1, 1)) for b in tb.values()],
        top=tops[:15], chains=sum(b["never"] for b in multi), gpu_h=round(sum(b["gpu_never"] for b in multi) / 60, 1),
        gpu_h_q=round(sum(b["gpu_never_q"] for b in multi) / 60, 1),
        nonretry_gpu_h=round(sum(t["gpu_h"] for t in tops if t["nonretry"]), 1), nonretry_chains=sum(t["chains"] for t in tops if t["nonretry"]))

    # ---------------- per PR (all PRs with CI in the window) + their commits
    prs = csvr("pr_30d.csv")
    ttg_by = {r["pr"]: r for r in tt}
    com = collections.defaultdict(list)
    for r in pcs:
        if not inwin(r["first_ci_at"]):
            continue
        bn = lambda u: int(u.rsplit("/", 1)[1]) if u else 0
        com[r["pr"]].append([r["commit"], r["first_ci_at"][:16].replace("T", " "), int(r["gha_workflow_runs"]), f(r["gha_job_min"]), int(r["gha_rerun_jobs"]),
                             int(r["mp_builds"]), int(r["unit_builds"]), f(r["gpu_min"]), int(r["bk_retried_jobs"]), bn(r["last_mp_build"]), bn(r["last_unit_build"])])
    prow = []
    for r in prs:
        if r["pr"] not in com:
            continue
        t = ttg_by.get(r["pr"])
        prow.append([int(r["pr"]), r["author"], (r["merged"] or "")[:10], int(r["pushes_with_ci"]), int(r["gha_workflow_runs"]), f(r["gha_job_min"]),
                     int(r["gha_rerun_jobs"]), int(r["mp_builds"]), int(r["unit_builds"]), f(r["gpu_min"]), int(r["bk_retried_jobs"]),
                     int(r["mp_same_commit_retriggers"]) + int(r["unit_same_commit_retriggers"]), r1(t["all_green_min"] / 60) if t and t["all_green_min"] is not None else None,
                     t["commit"] if t else ""])
    prow.sort(key=lambda x: -(x[9] or 0))

    # ---------------- data quality + reproducibility
    Q = json.load(open(os.path.join(P1, "join_quality.json"), encoding="utf-8")) if os.path.exists(os.path.join(P1, "join_quality.json")) else {}
    G = None
    ctx = collections.Counter()
    gp = os.path.join(P1, "raw", "gh_checks_30d.json")
    if os.path.exists(gp):
        G = json.load(open(gp, encoding="utf-8"))
        for p in G["prs"]:
            for c in p["commit_nodes"]:
                for x in (c.get("status") or {}).get("contexts", []):
                    if inwin(x["createdAt"]):
                        ctx[(x["context"].replace("buildkite/", ""), bool(x["isRequired"]))] += 1
    other = sorted([dict(name=k[0], n=v) for k, v in ctx.items() if not k[1]], key=lambda x: -x["n"])
    inputs = []
    for rel in ("window.json", "raw/builds_30d.json", "raw/builds_k3-unit-tests_30d.json", "raw/gh_checks_30d.json", "raw/fail_signatures.json",
                "jobs_all_30d.csv", "gh_jobs_30d.csv", "pr_commit_30d.csv", "pr_30d.csv", "ttg_30d.csv", "retry_events_30d.csv"):
        p = os.path.join(P1, rel)
        if os.path.exists(p):
            inputs.append(dict(path="outputs/P1/" + rel, sha=sha12(p), kb=round(os.path.getsize(p) / 1024),
                               made=datetime.fromtimestamp(os.path.getmtime(p), timezone.utc).strftime("%Y-%m-%d %H:%M")))
    sigf = json.load(open(os.path.join(P1, "raw", "fail_signatures.json"), encoding="utf-8")) if os.path.exists(os.path.join(P1, "raw", "fail_signatures.json")) else {}
    quality = dict(Q, other_pipelines=other, inputs=inputs, gh_made=(G or {}).get("made"), fail_logs=len(sigf),
                   gpu_map={k: v for k, v in GPU_MAP.items()}, orphans=len((G or {}).get("orphan_commits") or {}),
                   unfinished=sum(1 for bs in builds.values() for b in bs if b["state"] in ("running", "scheduled", "creating", "canceling", "failing")))

    # ---------------- tracking: last 24 h of the same sources, same units
    track = None
    O = json.load(open(os.path.join(HERE, "ops_ci_24h.json"), encoding="utf-8")) if os.path.exists(os.path.join(HERE, "ops_ci_24h.json")) else None
    if O:
        first_ = min((r["created_at"] for r in O.get("gha") or [] if r.get("created_at")), default=O.get("since"))
        span = max(1.0, (dt(O["at"]) - dt(first_)).total_seconds() / 3600) if O.get("at") and first_ else 24.0
        k = 24 / span
        jm = lambda j: max(0.0, mins(j.get("started_at"), j.get("finished_at") or j.get("completed_at")) or 0.0)
        def gpus(slug, name):
            if slug == "k3-unit-tests":
                return 1 if "Unit Tests" in (name or "") else None
            return GPU_MAP.get(parse_label(name or "")[0])
        now = {}
        for slug in PIPES:
            bs = [b for b in O.get("bk") or [] if (b.get("pipeline") or {}).get("slug") == slug and b.get("pull_request")]
            js = [(j, gpus(slug, j.get("name"))) for b in bs for j in b.get("jobs") or [] if j.get("type") == "script" and j.get("started_at")]
            js = [(j, g) for j, g in js if g is not None]
            now[slug] = dict(builds=len(bs), gpu=sum(jm(j) * g for j, g in js), retried=sum(jm(j) * g for j, g in js if j.get("retried")),
                             failed=sum(jm(j) * g for j, g in js if j.get("state") in ("failed", "timed_out")), n_ret=sum(1 for j, g in js if j.get("retried")),
                             n_fail=sum(1 for j, g in js if j.get("state") in ("failed", "timed_out")),
                             q=[mins(j.get("runnable_at") or j.get("scheduled_at"), j["started_at"]) for j, g in js if g])
        gh = [r for r in O.get("gha") or [] if (r.get("event") or "").startswith("pull_request")]
        gjs = [(r, j) for r in gh for j in r.get("jobs") or [] if j.get("started_at") and j.get("conclusion") not in ("skipped", None)]
        c_tot = sum(jm(j) for r, j in gjs)
        c_rer = sum(jm(j) for r, j in gjs if (j.get("run_attempt") or 1) > 1)
        cq_now = [jm(j) for r, j in gjs if j.get("name") == "Check code quality"]
        b_ret = sum(e["lost"] or 0 for e in bk_ev if e["kind"] == "job retry") / days
        b_fail = sum(f(r["gpu_min"]) or 0 for r in ran if r["state"] in ("failed", "timed_out")) / days
        n_ret = sum(v["n_ret"] for v in now.values())
        n_fail = sum(v["n_fail"] for v in now.values())
        rows = []
        for slug, v in now.items():
            sh = "MP" if slug == "k3-multiprocess-test" else "Unit"
            rows.append(dict(key=f"gpu_{sh}", label=[f"{sh} PR GPU-min per day", f"GPU-phút {sh} của PR mỗi ngày"], base=round(pipes[slug]["gpu_h_day"] * 60), now=round(v["gpu"] * k), unit="GPU-min", better="down"))
            rows.append(dict(key=f"builds_{sh}", label=[f"{sh} PR builds per day", f"Build {sh} của PR mỗi ngày"], base=round(pipes[slug]["builds"] / days, 1), now=round(v["builds"] * k, 1), unit="", better="down"))
        rows += [dict(key="retry_gpu", label=["Retried GPU-min per day (MP + Unit)", "GPU-phút bị retry mỗi ngày (MP + Unit)"], base=round(b_ret), now=round(sum(v["retried"] for v in now.values()) * k), unit="GPU-min", better="down"),
                 dict(key="failed_gpu", label=["Failed GPU-min per day (MP + Unit)", "GPU-phút fail mỗi ngày (MP + Unit)"], base=round(b_fail), now=round(sum(v["failed"] for v in now.values()) * k), unit="GPU-min", better="down"),
                 dict(key="queue_p50", label=["Queue wait per GPU job (median)", "Chờ queue mỗi job GPU (trung vị)"], base=pipes["k3-multiprocess-test"]["job_queue"]["p50"], now=r1(pct(now["k3-multiprocess-test"]["q"], .5)), unit="min", better="down"),
                 dict(key="queue_p90", label=["Queue wait per GPU job (p90)", "Chờ queue mỗi job GPU (p90)"], base=pipes["k3-multiprocess-test"]["job_queue"]["p90"], now=r1(pct(now["k3-multiprocess-test"]["q"], .9)), unit="min", better="down"),
                 dict(key="cpu_jobmin", label=["CPU job-min per day (GitHub Actions, PRs)", "Phút job CPU mỗi ngày (GitHub Actions, PR)"], base=round(cpu["job_h_day"] * 60), now=round(c_tot * k), unit="job-min", better="down"),
                 dict(key="cpu_rerun", label=["CPU re-run share of job-min", "Tỉ lệ chạy lại trên phút job CPU"], base=cpu["rerun_share"], now=round(100 * c_rer / c_tot, 1) if c_tot else None, unit="%", better="down"),
                 dict(key="cq_exec", label=["Check code quality run time (median)", "Thời gian chạy Check code quality (trung vị)"], base=cpu["exec_cq"]["p50"], now=r1(pct(cq_now, .5)), unit="min", better="down")]
        track = dict(at=O.get("at"), span_h=round(span, 1), n_retried=n_ret, n_failed=n_fail, rows=rows)
        if n_ret == 0 and n_fail:
            for r_ in rows:
                if r_["key"] == "retry_gpu":
                    r_.update(now=None, na=["n/a: no job carries the 'retried' flag in this window", "không áp dụng: không job nào có cờ 'retried' trong khung này"])
    hist = []
    hd = os.path.join(HERE, "ops_hist")
    if os.path.isdir(hd):
        for fn in sorted(os.listdir(hd)):
            h = json.load(open(os.path.join(hd, fn), encoding="utf-8"))
            rr = h.get("rows") or {}
            hist.append(dict(date=h.get("date"), mp=(rr.get("k3-multiprocess-test") or {}).get("total"), unit=(rr.get("k3-unit-tests") or {}).get("total"),
                             gpu_rerun=(h.get("tot") or {}).get("GPU_rerun"), cpu_rerun=(h.get("tot") or {}).get("CPU_rerun")))
    return dict(made=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), window=window, since=since, until=until, days=days, repo=WIN["repo"],
                gpu=gpu, cpu=cpu, ttg=ttg, merges=merges, retry=retry, prs=prow, commits=com, quality=quality, track=track, hist=hist,
                cls=CLS, base=dict(gpu_build_p50=r1(pct([v for v in gpu_pr.values()], .5)), **build_gpu))


HTML = r"""
<!-- R1130:HTML:START -->
<section class="card ops r11" data-view="r1130" data-tab="baseline" data-r11="baseline"></section>
<section class="card ops r11" data-view="r1130" data-tab="cpu" data-r11="cpu"></section>
<section class="card ops r11" data-view="r1130" data-tab="green" data-r11="green"></section>
<section class="card ops r11" data-view="r1130" data-tab="retry" data-r11="retry"></section>
<section class="card ops r11" data-view="r1130" data-tab="prs" data-r11="prs"></section>
<section class="card ops r11" data-view="r1130" data-tab="track" data-r11="track"></section>
<section class="card ops r11" data-view="r1130" data-tab="repro" data-r11="repro"></section>
<section class="card ops r11" data-view="r1130" data-tab="quality" data-r11="quality"></section>
<!-- R1130:HTML:END -->
"""

JS = r"""
<!-- R1130:JS:START -->
<script id="r11Data" type="application/json">__DATA__</script>
<script>
(function(){
  let D=null;try{D=JSON.parse(document.getElementById('r11Data').textContent);}catch(e){return;}
  const V=()=>(window.I18N&&I18N.lang==='vi')?1:0,T=(en,vi)=>V()?vi:en,L=a=>Array.isArray(a)?(a[V()]||a[0]):(a||'');
  const el=(t,a={},...k)=>{const e=document.createElement(t);for(const[x,v]of Object.entries(a)){if(v==null)continue;if(x==='class')e.className=v;else if(x==='style')e.style.cssText=v;else if(x.startsWith('on'))e.addEventListener(x.slice(2),v);else e.setAttribute(x,v);}k.flat().forEach(c=>{if(c==null||c===false)return;e.append(c.nodeType?c:document.createTextNode(String(c)));});return e;};
  const fmt=n=>n==null?'—':Number(n).toLocaleString('en-US');
  const h1=n=>n==null?'—':fmt(Math.round(n*10)/10);
  const sec=k=>document.querySelector(`section[data-r11="${k}"]`);
  const head=(n,en,vi,sen,svi)=>el('div',{class:'head'},el('h2',{},`${n} · ${T(en,vi)}`),sen?el('p',{class:'sub'},T(sen,svi)):null);
  const table=(cols,rows)=>{const t=el('table',{class:'obs-t'});t.append(el('thead',{},el('tr',{},cols.map(c=>el('th',{class:c[1]||''},c[0])))));const b=el('tbody');rows.forEach(r=>b.append(r));t.append(b);return el('div',{class:'obs-scroll'},t);};
  const tile=(v,u,l,sub,cls)=>el('div',{class:'r11-stat'+(cls?' '+cls:'')},el('div',{class:'l'},l),
    el('div',{class:'v'},v==null?'—':(typeof v==='number'?fmt(v):v),u?el('span',{class:'u'},u):null),sub?el('div',{class:'s'},sub):null);
  // median tile: big median, p90 as a second figure, and a thin meter (track = p90, fill = median) that shows the skew
  const mtile=(o,u,l,cls)=>{if(!o||o.p50==null)return tile(null,u,l,null,cls);const w=o.p90?Math.max(3,Math.min(100,100*o.p50/o.p90)):100;
    return el('div',{class:'r11-stat'+(cls?' '+cls:'')},el('div',{class:'l'},l),
      el('div',{class:'v'},fmt(o.p50),u?el('span',{class:'u'},u):null,el('span',{class:'tag'},T('median','trung vị'))),
      el('div',{class:'r11-meter',title:T(`median ${fmt(o.p50)} of p90 ${fmt(o.p90)}`,`trung vị ${fmt(o.p50)} trên p90 ${fmt(o.p90)}`)},el('i',{style:`width:${w}%`})),
      el('div',{class:'p9'},el('b',{},`p90 ${fmt(o.p90)}${u?' '+u:''}`),el('span',{},T('9 in 10 at or below','9/10 bằng hoặc thấp hơn'))));};
  // cost tile: p90 is the big number (what the costly PRs pay), the median is the second figure
  const ctile=(o,u,l,sub,cls)=>{if(!o||o.p90==null)return tile(null,u,l,sub,cls);const w=o.p90?Math.max(3,Math.min(100,100*o.p50/o.p90)):100;
    return el('div',{class:'r11-stat'+(cls?' '+cls:'')},el('div',{class:'l'},l),
      el('div',{class:'v'},fmt(o.p90),u?el('span',{class:'u'},u):null,el('span',{class:'tag'},'p90')),
      el('div',{class:'r11-meter',title:T(`median ${fmt(o.p50)} of p90 ${fmt(o.p90)}`,`trung vị ${fmt(o.p50)} trên p90 ${fmt(o.p90)}`)},el('i',{style:`width:${w}%`})),
      el('div',{class:'p9'},el('b',{},`${T('median','trung vị')} ${fmt(o.p50)}${u?' '+u:''}`),el('span',{},T('half the PRs at or below','một nửa số PR bằng hoặc thấp hơn'))),
      sub?el('div',{class:'s'},sub):null);};
  const src=(en,vi)=>el('p',{class:'ops-src'},T(en,vi));
  const W=D.window.join(' → '),BK='https://buildkite.com/lmcache/',GH=`https://github.com/${D.repo}`;
  const link=(href,txt)=>el('a',{href,target:'_blank',rel:'noopener'},txt);
  // ---------- chart kit (SVG, theme tokens, hover tooltip on every mark, table view for every chart)
  const NS='http://www.w3.org/2000/svg';
  const sv=(t,a={})=>{const e=document.createElementNS(NS,t);for(const[k,v]of Object.entries(a))e.setAttribute(k,v);return e;};
  // the tooltip lives inside .viz-root: the colour tokens (light / dark) are defined there, not on <body>
  let tip=document.getElementById('r11tip');if(!tip){tip=el('div',{id:'r11tip',class:'r11-tip',role:'tooltip'});(document.querySelector('.viz-root')||document.body).append(tip);}
  const showTip=(e,rows,title)=>{tip.replaceChildren(...[title?el('div',{class:'tt'},title):null,...rows.map(([v,lab,col])=>el('div',{class:'tr'},col?el('i',{style:`background:${col}`}):null,el('b',{},v),' ',el('span',{},lab)))].filter(Boolean));   // replaceChildren(null) would print "null"
    tip.style.display='block';const r=e.target.getBoundingClientRect?e.target.getBoundingClientRect():{left:e.clientX,top:e.clientY,width:0};
    let x=(e.clientX||r.left+r.width/2)+14,y=(e.clientY||r.top)+14;const w=tip.offsetWidth,h=tip.offsetHeight;if(x+w>innerWidth-8)x=x-w-28;if(y+h>innerHeight-8)y=y-h-28;tip.style.left=x+'px';tip.style.top=y+'px';};
  const hideTip=()=>{tip.style.display='none';};
  const hover=(node,fn)=>{node.setAttribute('tabindex','0');node.addEventListener('pointermove',e=>fn(e));node.addEventListener('focus',e=>fn(e));node.addEventListener('pointerleave',hideTip);node.addEventListener('blur',hideTip);};
  const C1='var(--series-1)',C2='var(--series-2)',C3='var(--series-3)',CN='var(--text-muted)';
  const CLSC={test:C1,infra:C2,config:C3,unknown:CN};
  const colPath=(x,y,w,h,r)=>{r=Math.min(r,h,w/2);return `M${x},${y+h}V${y+r}Q${x},${y} ${x+r},${y}H${x+w-r}Q${x+w},${y} ${x+w},${y+r}V${y+h}Z`;};
  const barPath=(x,y,w,h,r)=>{r=Math.min(r,w,h/2);return `M${x},${y}H${x+w-r}Q${x+w},${y} ${x+w},${y+r}V${y+h-r}Q${x+w},${y+h} ${x+w-r},${y+h}H${x}Z`;};
  const niceMax=v=>{const p=Math.pow(10,Math.floor(Math.log10(v||1))),m=v/p;return (m<=1?1:m<=2?2:m<=2.5?2.5:m<=5?5:10)*p;};
  const legend=items=>el('div',{class:'r11-leg'},items.map(([lab,col])=>el('span',{},el('i',{style:`background:${col}`}),lab)));
  const tableView=(cols,rows)=>el('details',{class:'r11-tv'},el('summary',{},T('Show as table','Xem dạng bảng')),table(cols,rows.map(r=>el('tr',{},r.map((c,i)=>el('td',{class:i?'r':''},c))))));
  // stacked daily columns: a = first try, b = re-run / retried (same unit)
  function dailyChart(series,u,la,lb){const W_=1000,H=200,ml=40,mr=8,mt=10,mb=26,iw=W_-ml-mr,ih=H-mt-mb,n=series.length,band=iw/n,bw=Math.min(24,band*0.7);
    const mx=niceMax(Math.max(...series.map(d=>d.a+d.b),0.1)),y=v=>mt+ih-ih*v/mx,svg=sv('svg',{viewBox:`0 0 ${W_} ${H}`,class:'r11-svg',role:'img','aria-label':`${la} / ${lb}`});
    [0,.5,1].forEach(f=>{const v=mx*f,yy=y(v);svg.append(sv('line',{x1:ml,x2:W_-mr,y1:yy,y2:yy,class:'r11-grid'}));const t=sv('text',{x:ml-6,y:yy+4,class:'r11-ax','text-anchor':'end'});t.textContent=fmt(Math.round(v));svg.append(t);});
    series.forEach((d,i)=>{const x=ml+i*band+(band-bw)/2,tot=d.a+d.b,g=sv('g',{class:'r11-col'});
      const hF=ih*d.a/mx,hR=ih*d.b/mx,gap=hR>0&&hF>0?2:0;
      if(hR>0){g.append(sv('path',{d:colPath(x,y(tot),bw,hR,4),fill:C2}));}
      if(hF>0){g.append(sv('path',{d:hR>0?`M${x},${mt+ih}V${y(d.a)+gap}H${x+bw}V${mt+ih}Z`:colPath(x,y(d.a),bw,hF,4),fill:C1}));}
      const hit=sv('rect',{x:ml+i*band,y:mt,width:band,height:ih,fill:'transparent'});g.append(hit);
      hover(hit,e=>{g.classList.add('on');showTip(e,[[`${h1(tot)} ${u}`,T('total','tổng')],[`${h1(d.a)} ${u}`,la,C1],[`${h1(d.b)} ${u}`,lb,C2]],d.d);});
      hit.addEventListener('pointerleave',()=>g.classList.remove('on'));hit.addEventListener('blur',()=>g.classList.remove('on'));
      if(i%7===0||(i===n-1&&(n-1)%7>=4)){const t=sv('text',{x:x+bw/2,y:H-8,class:'r11-ax','text-anchor':'middle'});t.textContent=d.d.slice(5);svg.append(t);}
      svg.append(g);});
    return el('div',{},legend([[la,C1],[lb,C2]]),svg,
      tableView([[T('Day','Ngày')],[la,'r'],[lb,'r']],series.map(d=>[d.d,h1(d.a),h1(d.b)])));}
  // histogram with p50 / p90 rules
  function histChart(Hs,unit,what){if(!Hs)return null;const W_=1000,H=200,ml=40,mr=8,mt=40,mb=26,iw=W_-ml-mr,ih=H-mt-mb,b=Hs.bins,band=iw/b.length,bw=Math.min(24,band*0.8);
    const mx=niceMax(Math.max(...b.map(x=>x.n))),y=v=>mt+ih-ih*v/mx,top=b[b.length-1].hi,xv=v=>ml+iw*Math.min(v,top)/top;
    const svg=sv('svg',{viewBox:`0 0 ${W_} ${H}`,class:'r11-svg',role:'img','aria-label':what});
    [0,.5,1].forEach(f=>{const v=mx*f,yy=y(v);svg.append(sv('line',{x1:ml,x2:W_-mr,y1:yy,y2:yy,class:'r11-grid'}));const t=sv('text',{x:ml-6,y:yy+4,class:'r11-ax','text-anchor':'end'});t.textContent=fmt(Math.round(v));svg.append(t);});
    b.forEach((x,i)=>{const xx=ml+i*band+(band-bw)/2,h=ih*x.n/mx,g=sv('g',{class:'r11-col'});if(h>0)g.append(sv('path',{d:colPath(xx,y(x.n),bw,h,4),fill:C1}));
      const hit=sv('rect',{x:ml+i*band,y:mt,width:band,height:ih,fill:'transparent'});g.append(hit);
      hover(hit,e=>{g.classList.add('on');showTip(e,[[`${x.n} PR`,x.open?`${x.lo}+ ${unit}`:`${x.lo}–${x.hi} ${unit}`]]);});
      hit.addEventListener('pointerleave',()=>g.classList.remove('on'));svg.append(g);
      if(i%2===0){const t=sv('text',{x:ml+i*band,y:H-8,class:'r11-ax','text-anchor':'middle'});t.textContent=x.lo;svg.append(t);}});
    const x50=xv(Hs.p50),x90=xv(Hs.p90),near=x90-x50<230;
    [[x50,T(`median ${Hs.p50} ${unit}`,`trung vị ${Hs.p50} ${unit}`),(near&&x50>260)||x50>W_-260?'end':'start',14,''],
     [x90,`p90 ${Hs.p90} ${unit}`,x90>W_-260?'end':'start',near?30:14,' r11-p90']].forEach(([xx,lab,anc,yy,p9])=>{
      svg.append(sv('line',{x1:xx,x2:xx,y1:yy+4,y2:mt+ih,class:'r11-rule'+p9}));
      const t=sv('text',{x:anc==='end'?xx-5:xx+5,y:yy,class:'r11-ax r11-rl'+(p9?' r11-p90t':''),'text-anchor':anc});t.textContent=lab;svg.append(t);});
    return el('div',{},svg,el('div',{class:'meta'},T(`${what}, ${Hs.n} PRs. Solid line: p90 (9 in 10 PRs are at or below: what the costly PRs pay). Dashed line: median (half the PRs are at or below). Last bin = ${b[b.length-1].lo} ${unit} and more.`,`${what}, ${Hs.n} PR. Đường liền: p90 (9/10 PR bằng hoặc thấp hơn: mức các PR tốn nhiều phải trả). Đường nét đứt: trung vị (một nửa số PR bằng hoặc thấp hơn). Cột cuối = ${b[b.length-1].lo} ${unit} trở lên.`)),
      tableView([[unit],['PR','r']],b.map(x=>[x.open?`${x.lo}+`:`${x.lo}–${x.hi}`,x.n])));}
  // what one PR costs: switch merged PRs / all PRs and run time only / run + queued; the queued choice is always written next to the chart
  function costChart(Vw,unit,what,qtxt){if(!Vw)return null;const st={s:'merged',q:'run'},box=el('div',{class:'r11-cost'});
    const draw=()=>{const v=Vw[st.s+'_'+st.q];
      const btn=(g,val,lab)=>el('button',{type:'button',class:'r11-sw'+(st[g]===val?' on':''),'aria-pressed':String(st[g]===val),onclick:()=>{st[g]=val;draw();}},lab);
      const other=Vw[st.s+'_'+(st.q==='q'?'run':'q')];
      box.replaceChildren(el('div',{class:'r11-sws'},
          el('span',{class:'r11-swg',role:'group','aria-label':T('Which PRs','PR nào')},btn('s','merged',T('Merged PRs (until merge)','PR đã merge (tới khi merge)')),btn('s','all',T('All PRs','Mọi PR'))),
          qtxt.q?el('span',{class:'r11-swg',role:'group','aria-label':T('Queued time','Thời gian chờ queue')},btn('q','run',T('Run time only','Chỉ thời gian chạy')),btn('q','q',T('Run + queued time','Chạy + thời gian chờ queue'))):null),
        el('div',{class:'r11-qnote'+(st.q==='q'?' on':'')},el('b',{},st.q==='q'?T('Queued time INCLUDED','CÓ tính thời gian chờ queue'):T('Queued time NOT included','KHÔNG tính thời gian chờ queue')),' · ',L(qtxt[st.q]),
          qtxt.q&&other&&other.stats.p90!=null?el('span',{class:'meta'},' · '+T(`other view: p90 ${fmt(other.stats.p90)} ${unit}`,`cách xem kia: p90 ${fmt(other.stats.p90)} ${unit}`)):null),
        histChart(v.hist,unit,`${what} · ${st.s==='merged'?T('PRs merged in the window','PR merge trong khung'):T('all PRs with a build in the window','mọi PR có build trong khung')} · ${st.q==='q'?T('run + queued','chạy + chờ queue'):T('run time only','chỉ thời gian chạy')}`));};
    draw();return box;}
  // retries that never pass: stacked columns by number of tries (passed in the end / never passed)
  function triesChart(N){const bins=N.bins,W_=1000,H=210,ml=40,mr=8,mt=12,mb=30,iw=W_-ml-mr,ih=H-mt-mb,band=iw/bins.length,bw=Math.min(70,band*0.5);
    const mx=niceMax(Math.max(...bins.map(b=>b.never),1)),y=v=>mt+ih-ih*v/mx,CK='var(--critical)';   // only the never-passed items: passed ones (thousands) would hide them
    const svg=sv('svg',{viewBox:`0 0 ${W_} ${H}`,class:'r11-svg',role:'img','aria-label':T('Work items by number of tries and final result','Việc theo số lần thử và kết quả cuối')});
    [0,.5,1].forEach(f=>{const v=mx*f,yy=y(v);svg.append(sv('line',{x1:ml,x2:W_-mr,y1:yy,y2:yy,class:'r11-grid'}));const t=sv('text',{x:ml-6,y:yy+4,class:'r11-ax','text-anchor':'end'});t.textContent=fmt(Math.round(v));svg.append(t);});
    bins.forEach((b,i)=>{const x=ml+i*band+(band-bw)/2,tot=b.never,g=sv('g',{class:'r11-col'}),hN=ih*b.never/mx;
      if(hN>0)g.append(sv('path',{d:colPath(x,y(tot),bw,hN,4),fill:CK}));
      const lab=b.tries===5?T('5+ tries','5+ lần'):T(`${b.tries} ${b.tries===1?'try':'tries'}`,`${b.tries} lần`);
      const tv=sv('text',{x:x+bw/2,y:y(tot)-5,class:'r11-val','text-anchor':'middle'});tv.textContent=b.never?`${fmt(b.never)} · ${fmt(b.gpu_h)} GPU-h`:'';g.append(tv);
      const hit=sv('rect',{x:ml+i*band,y:mt,width:band,height:ih,fill:'transparent'});g.append(hit);
      hover(hit,e=>{g.classList.add('on');showTip(e,[[fmt(b.passed),T('passed in the end','cuối cùng pass'),C1],[fmt(b.never),T('never passed','không bao giờ pass'),CK],
        [`${fmt(b.gpu_h)} GPU-h`,T('spent on the never-passed ones, run time','tốn cho các việc không pass, thời gian chạy')],[`${fmt(b.gpu_h_q)} GPU-h`,T('same, with queued time','như trên, có thời gian chờ queue')],
        [b.hours.p50==null?'—':`${fmt(b.hours.p50)} h · p90 ${fmt(b.hours.p90)} h`,T('first try → last try, median · p90','lần đầu → lần cuối, trung vị · p90')]],lab);});
      hit.addEventListener('pointerleave',()=>g.classList.remove('on'));
      const t=sv('text',{x:x+bw/2,y:H-10,class:'r11-ax','text-anchor':'middle'});t.textContent=lab;svg.append(t);svg.append(g);});
    return el('div',{},el('div',{class:'meta'},T('Bars: work items that never passed, by how many times they were tried (label: items · GPU-h, run time). 1 try = failed once and nobody ran it again. Hover a bar for the items that passed in the end and the hours from the first to the last try.','Cột: số việc không bao giờ pass, theo số lần đã thử (nhãn: số việc · GPU-h, thời gian chạy). 1 lần = fail một lần và không ai chạy lại. Rê chuột lên cột để xem số việc cuối cùng pass và số giờ từ lần thử đầu tới lần cuối.')),svg,
      tableView([[T('Tries','Số lần thử')],[T('Passed in the end','Cuối cùng pass'),'r'],[T('Never passed','Không pass'),'r'],[T('GPU-h never passed (run · + queued)','GPU-h không pass (chạy · + chờ)'),'r'],[T('Hours first → last try (median · p90)','Giờ lần đầu → lần cuối (trung vị · p90)'),'r']],
        bins.map(b=>[b.tries===5?'5+':String(b.tries),fmt(b.passed),fmt(b.never),`${fmt(b.gpu_h)} · ${fmt(b.gpu_h_q)}`,b.hours.p50==null?'—':`${fmt(b.hours.p50)} · ${fmt(b.hours.p90)}`])));}
  // ranked horizontal bars (largest first)
  function rankBars(items,{val,lab,col,fmtv,detail,kinds}){const W_=1000,rowH=26,ml=200,mr=detail?440:140,bh=14,H=items.length*rowH+6,mx=Math.max(...items.map(val),0.1),iw=W_-ml-mr;
    const svg=sv('svg',{viewBox:`0 0 ${W_} ${H}`,class:'r11-svg',role:'img'});
    items.forEach((it,i)=>{const yy=i*rowH+6,w=Math.max(2,iw*val(it)/mx),g=sv('g',{class:'r11-col'});
      const tl=sv('text',{x:ml-8,y:yy+bh-2,class:'r11-lab','text-anchor':'end'});tl.textContent=lab(it);g.append(tl);
      g.append(sv('path',{d:barPath(ml,yy,w,bh,4),fill:col(it)}));
      const tv=sv('text',{x:ml+w+6,y:yy+bh-2,class:'r11-val'});tv.textContent=fmtv(it);g.append(tv);
      if(detail){const td=sv('text',{x:W_-4,y:yy+bh-2,class:'r11-ax','text-anchor':'end'});td.textContent=detail(it);g.append(td);}
      const hit=sv('rect',{x:0,y:yy-5,width:W_,height:rowH,fill:'transparent'});g.append(hit);hover(hit,e=>{g.classList.add('on');showTip(e,[[fmtv(it),lab(it),col(it)]].concat(detail?[[detail(it),'']]:[]));});hit.addEventListener('pointerleave',()=>g.classList.remove('on'));svg.append(g);});
    return el('div',{},kinds?legend(kinds):null,svg);}
  // median -> p90 dumbbell per row (one hue, two shades) on a log axis: the rows span minutes to days
  function rangeBars(rows,unit){const W_=1000,rowH=32,ml=230,mr=130,H=rows.length*rowH+34,iw=W_-ml-mr,lo=0.05,hiV=Math.max(1,...rows.map(r=>r.p90||0)),hi=Math.pow(10,Math.ceil(Math.log10(hiV))),
      x=v=>ml+iw*(Math.log10(Math.max(lo,Math.min(v,hi)))-Math.log10(lo))/(Math.log10(hi)-Math.log10(lo)),DK=C1,LT='color-mix(in srgb, var(--series-1) 45%, var(--text-muted))';
    const tl=v=>v<1?`${Math.round(v*60)} ${T('min','phút')}`:`${fmt(v)} ${unit}`;
    const svg=sv('svg',{viewBox:`0 0 ${W_} ${H}`,class:'r11-svg',role:'img','aria-label':T('Median and p90 per step, log scale','Trung vị và p90 theo bước, thang log')});
    [0.1,1,10,100,1000].filter(v=>v<=hi).forEach(v=>{const xx=x(v);svg.append(sv('line',{x1:xx,x2:xx,y1:4,y2:H-24,class:'r11-grid'}));const t=sv('text',{x:xx,y:H-8,class:'r11-ax','text-anchor':'middle'});t.textContent=tl(v);svg.append(t);});
    rows.forEach((r,i)=>{const yy=i*rowH+16,g=sv('g',{class:'r11-col'});const tlab=sv('text',{x:ml-12,y:yy+4,class:'r11-lab','text-anchor':'end'});tlab.textContent=L(r.label);g.append(tlab);
      if(r.p50==null){const t=sv('text',{x:ml,y:yy+4,class:'r11-ax'});t.textContent=T('no data','không có dữ liệu');g.append(t);svg.append(g);return;}
      g.append(sv('line',{x1:x(r.p50),x2:x(r.p90),y1:yy,y2:yy,stroke:LT,'stroke-width':4,'stroke-linecap':'round'}));
      g.append(sv('circle',{cx:x(r.p90),cy:yy,r:6,fill:LT,stroke:'var(--surface-1)','stroke-width':2}));
      g.append(sv('circle',{cx:x(r.p50),cy:yy,r:6,fill:DK,stroke:'var(--surface-1)','stroke-width':2}));
      const tv=sv('text',{x:W_-4,y:yy+4,class:'r11-val','text-anchor':'end'});tv.textContent=`${tl(r.p50)} → ${tl(r.p90)}`;g.append(tv);
      const hit=sv('rect',{x:0,y:yy-rowH/2,width:W_,height:rowH,fill:'transparent'});g.append(hit);
      hover(hit,e=>showTip(e,[[tl(r.p50),T('median (p50): half the PRs at or below','trung vị (p50): một nửa số PR bằng hoặc thấp hơn'),DK],[tl(r.p90),T('p90: 9 in 10 PRs at or below','p90: 9/10 PR bằng hoặc thấp hơn'),LT],[`${r.n}`,T('PRs','PR')]].concat(r.note?[[L(r.note),'']]:[]),L(r.label)));svg.append(g);});
    return el('div',{},legend([[T('median (p50)','trung vị (p50)'),DK],[T('p90 (9 in 10 at or below)','p90 (9/10 bằng hoặc thấp hơn)'),LT]]),svg,
      el('div',{class:'meta'},T('Log scale: each grid step is 10× the one before, so minutes and days fit on one axis. Right column: median → p90.','Thang log: mỗi vạch lớn gấp 10 lần vạch trước, để phút và ngày nằm trên cùng một trục. Cột phải: trung vị → p90.')),
      tableView([[T('Step','Bước')],[T('Median (p50)','Trung vị (p50)'),'r'],['p90','r'],['PRs','r']],rows.map(r=>[L(r.label),r.p50==null?'—':tl(r.p50),r.p90==null?'—':tl(r.p90),r.n])));}
  // dumbbell: baseline (100%) -> now, one shared axis indexed to the baseline
  function dumbbells(rows){const W_=1000,rowH=32,ml=300,mr=70,H=rows.length*rowH+30,vals=rows.map(r=>r.base?100*r.now/r.base:null).filter(v=>v!=null),hi=niceMax(Math.max(150,...vals)),iw=W_-ml-mr,x=v=>ml+iw*Math.min(v,hi)/hi;
    const svg=sv('svg',{viewBox:`0 0 ${W_} ${H}`,class:'r11-svg',role:'img','aria-label':T('Now as a percent of the baseline','Hiện tại tính theo % của baseline')});
    [0,50,100,150,hi].filter((v,i,a)=>a.indexOf(v)===i&&v<=hi).forEach(v=>{const xx=x(v);svg.append(sv('line',{x1:xx,x2:xx,y1:4,y2:H-22,class:v===100?'r11-rule':'r11-grid'}));const t=sv('text',{x:xx,y:H-6,class:'r11-ax','text-anchor':'middle'});t.textContent=v+'%';svg.append(t);});
    rows.forEach((r,i)=>{const yy=i*rowH+18,idx=r.base&&r.now!=null?100*r.now/r.base:null,g=sv('g',{class:'r11-col'});
      const tl=sv('text',{x:ml-10,y:yy+4,class:'r11-lab','text-anchor':'end'});tl.textContent=L(r.label);g.append(tl);
      if(idx==null){const t=sv('text',{x:ml,y:yy+4,class:'r11-ax'});t.textContent=r.na?L(r.na):T('no data yet','chưa có dữ liệu');g.append(t);svg.append(g);return;}
      const good=r.better==='up'?idx>=100:idx<=100,same=Math.abs(idx-100)<5,col=same?'var(--text-muted)':good?'var(--good)':'var(--critical)';
      g.append(sv('line',{x1:x(100),x2:x(idx),y1:yy,y2:yy,stroke:col,'stroke-width':2,'stroke-linecap':'round'}));
      g.append(sv('circle',{cx:x(100),cy:yy,r:5,fill:'var(--text-muted)',stroke:'var(--surface-1)','stroke-width':2}));
      g.append(sv('circle',{cx:x(idx),cy:yy,r:6,fill:col,stroke:'var(--surface-1)','stroke-width':2}));
      const left=idx<100&&x(idx)-70>ml,tv=sv('text',{x:idx>=100?x(Math.min(idx,hi))+12:left?x(idx)-12:x(100)+12,y:yy+4,class:'r11-val','text-anchor':idx>=100||!left?'start':'end'});tv.textContent=`${same?'=':good?'✓':'!'} ${Math.round(idx)}%`;g.append(tv);
      const hit=sv('rect',{x:0,y:yy-14,width:W_,height:rowH,fill:'transparent'});g.append(hit);
      hover(hit,e=>showTip(e,[[`${fmt(r.now)} ${r.unit}`,T('now','hiện tại'),col],[`${fmt(r.base)} ${r.unit}`,T('baseline','baseline'),'var(--text-muted)'],[`${Math.round(idx)}%`,T('of baseline','so với baseline')]],L(r.label)));svg.append(g);});
    return el('div',{},legend([[T('baseline (100%)','baseline (100%)'),'var(--text-muted)'],[T('now: better','hiện tại: tốt hơn'),'var(--good)'],[T('now: worse','hiện tại: xấu hơn'),'var(--critical)']]),svg);}
  const csvDl=(name,cols,rows)=>{const q=v=>{v=v==null?'':String(v);return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;};
    const b=new Blob([[cols.join(','),...rows.map(r=>r.map(q).join(','))].join('\n')],{type:'text/csv'});const a=el('a',{href:URL.createObjectURL(b),download:name});document.body.append(a);a.click();a.remove();};

  // ================= 1 · GPU baseline
  function rBaseline(){const s=sec('baseline');if(!s)return;const G=D.gpu,MP=G.pipes['k3-multiprocess-test'],U=G.pipes['k3-unit-tests'];
    s.replaceChildren(el('a',{class:'tr-btn sm r11-ext','data-ev':'',href:'https://opendataio.github.io/lmcache-community-insights/',target:'_blank',rel:'noopener'},T('Community insights dashboard ↗','Dashboard community insights ↗')),head('1','GPU baseline (30 days)','Baseline GPU (30 ngày)',
      `Fixed window ${W} (UTC, by build creation). Buildkite PR builds of the two required GPU checks: ${fmt(MP.builds)} MP builds and ${fmt(U.builds)} unit-test builds for ${fmt(G.prs)} PRs.`,
      `Khung cố định ${W} (UTC, theo lúc tạo build). Build PR trên Buildkite của hai check GPU bắt buộc: ${fmt(MP.builds)} build MP và ${fmt(U.builds)} build unit test cho ${fmt(G.prs)} PR.`));
    s.append(el('div',{class:'ops-kpis'},
      tile(G.gpu_h,'GPU-h',T('PR GPU time, 30 days','GPU của PR, 30 ngày'),T(`${fmt(G.gpu_h_day)} GPU-h per day · MP + unit`,`${fmt(G.gpu_h_day)} GPU-giờ mỗi ngày · MP + unit`)),
      ctile((G.views||{}).merged_run?G.views.merged_run.stats:G.gpu_pr,'GPU-h',T('GPU per merged PR, until merge','GPU mỗi PR đã merge, tới khi merge'),
        (G.views||{}).merged_q?T(`queued time not included · with queued: p90 ${fmt(G.views.merged_q.stats.p90)} GPU-h`,`không tính chờ queue · có tính: p90 ${fmt(G.views.merged_q.stats.p90)} GPU-h`):null),
      tile(G.cancel_gpu_h,'GPU-h',T('Cancelled jobs','Job bị huỷ'),T('not counted as retries','không tính là retry'))));
    const P=[MP,U],row=(lab,fn)=>el('tr',{},el('td',{},lab),...P.map(p=>el('td',{class:'r'},fn(p))));
    const pr=o=>o&&o.p50!=null?`${fmt(o.p50)} · p90 ${fmt(o.p90)}`:'—';
    s.append(el('h3',{},T('Per pipeline','Theo pipeline')),table([[T('Metric (median, then p90)','Metric (trung vị, rồi p90)')],...P.map(p=>[L(p.name),'r'])],[
      row(T('PR builds (ran a job)','Build PR (có chạy job)'),p=>`${fmt(p.builds)} (${fmt(p.builds_ran)})`),
      row(T('GPU-hours (per day)','GPU-giờ (mỗi ngày)'),p=>`${fmt(p.gpu_h)} (${fmt(p.gpu_h_day)})`),
      row(T('Builds per PR','Số build mỗi PR'),p=>pr(p.builds_pr)),
      row(T('GPU-hours per PR','GPU-giờ mỗi PR'),p=>pr(p.gpu_pr)),
      row(T('Job execution, min (agent busy)','Job chạy, phút (agent bận)'),p=>pr(p.job_exec)),
      row(T('Job queue, min (waiting for an agent)','Job chờ queue, phút (chờ agent)'),p=>pr(p.job_queue)),
      row(T('Passed build, created → finished, min (includes queue)','Build pass, tạo → xong, phút (gồm chờ queue)'),p=>pr(p.build_e2e)),
      row(T('Passed build, started → finished, min (jobs may still queue inside)','Build pass, bắt đầu → xong, phút (job bên trong vẫn có thể chờ)'),p=>pr(p.build_run)),
      row(T('First-try job failure rate','Tỉ lệ job fail lần đầu'),p=>p.first_fail_pct==null?'—':p.first_fail_pct+'%')]));
    s.append(el('h3',{style:'margin-top:14px'},T('PR GPU-hours per day','GPU-giờ của PR theo ngày')),dailyChart(G.series,'GPU-h',T('first try','lần chạy đầu'),T('retried attempts','lần chạy bị retry')));
    s.append(el('h3',{style:'margin-top:14px'},T('What one PR costs until it merges','Một PR tốn bao nhiêu tới khi merge')),
      costChart(G.views,'GPU-h',T('GPU-hours per PR','GPU-giờ mỗi PR'),{run:[`job run time × GPUs the job asks for; the wait for a free agent is left out`,`thời gian job chạy × số GPU job yêu cầu; thời gian chờ agent trống không tính`],
        q:[`+ the wait for a free agent (job runnable → started, Buildkite "Waited") × GPUs of the job; ${fmt(G.queue_h)} GPU-h over all PRs`,`+ thời gian chờ agent trống (job sẵn sàng → bắt đầu, "Waited" trên Buildkite) × số GPU của job; ${fmt(G.queue_h)} GPU-h trên mọi PR`]}),
      el('p',{class:'meta'},T('Counted: every job of the PR on the 2 required GPU checks, Buildkite k3-multiprocess-test and k3-unit-tests, all builds and retries. Not counted: other Buildkite pipelines (xpu-mp-test, amd-mp-test, k3-blend-test, …; not required checks) and GitHub Actions CPU jobs (see 2 · CPU baseline). Builds before the window start are not counted for PRs opened earlier.',
        'Có tính: mọi job của PR trên 2 check GPU bắt buộc, Buildkite k3-multiprocess-test và k3-unit-tests, mọi build và retry. Không tính: các pipeline Buildkite khác (xpu-mp-test, amd-mp-test, k3-blend-test, …; không phải check bắt buộc) và job CPU GitHub Actions (xem 2 · Baseline CPU). Build trước khi khung bắt đầu không được tính cho PR mở sớm hơn.')));
    s.append(src('GPU-min = job execution minutes × GPUs the job asks for (pod spec in pipeline.yml). The queued view adds the agent wait × the same GPUs, as if the GPUs were held while waiting: use it for "how long a PR is stuck", the run-only view for "how much GPU it used". Median (p50) = half the values are at or below; p90 = 9 in 10 are at or below. Not averages: a few very costly PRs would pull an average up.','GPU-phút = số phút job chạy × số GPU job yêu cầu (pod spec trong pipeline.yml). Cách xem có queue cộng thêm thời gian chờ agent × cùng số GPU, như thể GPU bị giữ khi chờ: dùng để xem "PR bị kẹt bao lâu"; cách xem chỉ chạy để xem "dùng bao nhiêu GPU". Trung vị (p50) = một nửa giá trị bằng hoặc thấp hơn; p90 = 9 trên 10 bằng hoặc thấp hơn. Không phải trung bình: vài PR rất tốn sẽ kéo trung bình lên.'));}

  // ================= 2 · CPU baseline
  function rCpu(){const s=sec('cpu');if(!s)return;const C=D.cpu;
    s.replaceChildren(head('2','CPU baseline (30 days)','Baseline CPU (30 ngày)',
      `Same window ${W}. GitHub Actions jobs on PR commits (one job = one CPU runner): ${fmt(C.jobs)} job attempts in ${fmt(C.runs)} workflow runs for ${fmt(C.prs)} PRs. Skipped jobs are left out.`,
      `Cùng khung ${W}. Job GitHub Actions trên commit của PR (một job = một runner CPU): ${fmt(C.jobs)} lần chạy job trong ${fmt(C.runs)} workflow run cho ${fmt(C.prs)} PR. Bỏ các job bị skip.`));
    s.append(el('div',{class:'ops-kpis'},
      tile(C.job_h,'job-h',T('CPU time, 30 days','CPU, 30 ngày'),T(`${fmt(C.job_h_day)} job-h per day`,`${fmt(C.job_h_day)} giờ job mỗi ngày`)),
      ctile((C.views||{}).merged_run?C.views.merged_run.stats:C.job_pr,'job-h',T('CPU per merged PR, until merge','CPU mỗi PR đã merge, tới khi merge'),
        T('queued time not included (GitHub does not give it for old runs)','không tính thời gian chờ queue (GitHub không trả số này cho run cũ)')),
      mtile(C.runs_pr,'',T('Workflow runs per PR','Workflow run mỗi PR')),
      mtile(C.pushes_pr,'',T('Pushes per PR','Push mỗi PR')),
      mtile(C.exec_cq,T('min','phút'),T('Check code quality: run','Check code quality: chạy')),
      mtile(C.delay_cq,T('min','phút'),T('Check code quality: wait to start','Check code quality: chờ bắt đầu')),
      tile(C.rerun_h,'job-h',T('Re-runs','Chạy lại'),T(`${C.rerun_share}% of CPU · ${fmt(C.rerun_jobs)} job attempts`,`${C.rerun_share}% CPU · ${fmt(C.rerun_jobs)} lần chạy job`),C.rerun_share>5?'warn':'')));
    s.append(el('h3',{},T('CPU job-hours per day','Giờ job CPU theo ngày')),dailyChart(C.series,'job-h',T('first attempt','lần chạy đầu'),T('re-run attempts','lần chạy lại')));
    const WF=C.workflows.slice(0,10);
    s.append(el('h3',{style:'margin-top:14px'},T('CPU job-hours by workflow (top 10)','Giờ job CPU theo workflow (10 đầu)')),
      rankBars(WF,{val:w=>w.job_h,lab:w=>w.name,col:()=>C1,fmtv:w=>`${fmt(w.job_h)} h · ${w.share}%`,detail:w=>T(`median run ${h1(w.exec.p50)} min · median start delay ${h1(w.delay.p50)} min`,`trung vị chạy ${h1(w.exec.p50)} phút · trung vị trễ bắt đầu ${h1(w.delay.p50)} phút`)}),
      tableView([['Workflow'],[T('Job-h','Giờ job'),'r'],['%','r'],[T('Runs','Run'),'r'],[T('Jobs','Job'),'r'],[T('Run time, min (median · p90)','Chạy, phút (trung vị · p90)'),'r'],[T('Start delay, min (median · p90)','Trễ bắt đầu, phút (trung vị · p90)'),'r'],[T('Re-run jobs','Job chạy lại'),'r']],
        C.workflows.map(w=>[w.name,fmt(w.job_h),w.share+'%',fmt(w.runs),fmt(w.jobs),`${h1(w.exec.p50)} · p90 ${h1(w.exec.p90)}`,`${h1(w.delay.p50)} · p90 ${h1(w.delay.p90)}`,w.rerun])));
    s.append(el('h3',{style:'margin-top:14px'},T('What one PR costs in CPU until it merges','Một PR tốn bao nhiêu CPU tới khi merge')),
      costChart(C.views,'job-h',T('CPU job-hours per PR (GitHub Actions jobs on the PR commits)','Giờ job CPU mỗi PR (job GitHub Actions trên commit của PR)'),{run:['job start → job end on the runner. There is no "with queued" view for CPU: GitHub does not give the runner queue time of old runs, and the start delay it does give also holds the wait for earlier jobs of the same workflow run (adding it up would count the same wait many times)','job bắt đầu → job xong trên runner. CPU không có cách xem "có queue": GitHub không trả thời gian chờ runner của run cũ, và độ trễ bắt đầu mà GitHub trả còn gồm thời gian chờ các job trước trong cùng workflow run (cộng lại sẽ tính một lần chờ nhiều lần)'],q:null}));
    s.append(src('job-min = job start → job end on a GitHub-hosted runner. Start delay = job start − workflow run creation: it holds the runner queue AND the wait for earlier jobs of the same workflow; GitHub does not expose the pure runner queue for old runs, so the queue is reported as unavailable. Re-run attempt = an earlier attempt of the same job in the same workflow run.',
      'job-phút = job bắt đầu → job xong trên runner của GitHub. Độ trễ bắt đầu = lúc job bắt đầu − lúc tạo workflow run: gồm cả chờ runner VÀ chờ các job trước trong cùng workflow; GitHub không trả thời gian chờ runner thuần cho run cũ, nên queue được ghi là không có. Lần chạy lại = lần chạy trước của cùng job trong cùng workflow run.'));}

  // ================= 3 · Time to green + merges
  function rGreen(){const s=sec('green');if(!s)return;const G=D.ttg,M=D.merges;
    s.replaceChildren(head('3','Time to green & merges','Thời gian tới xanh & merge',
      `${fmt(G.n)} PRs merged into dev in ${W}. Time to green = last push of the PR → all 4 required checks green on that commit (DCO, Check code quality, k3-unit-tests, k3-multiprocess-test).`,
      `${fmt(G.n)} PR merge vào dev trong ${W}. Thời gian tới xanh = lần push cuối của PR → cả 4 check bắt buộc xanh trên commit đó (DCO, Check code quality, k3-unit-tests, k3-multiprocess-test).`));
    s.append(el('div',{class:'ops-kpis'},
      mtile(G.all,T('h','giờ'),T('Last push → all checks green','Push cuối → mọi check xanh')),
      mtile(G.no_label,T('h','giờ'),T("Same, 'full' already on","Như trên, đã có 'full'")),
      tile(`${G.label_share}%`,'',T("'full' added after last push","Gắn 'full' sau push cuối"),T(`${G.label_n} of ${G.green} PRs · MP waited for a person`,`${G.label_n} trên ${G.green} PR · MP chờ người gắn nhãn`)),
      mtile(G.open_to_merge,T('h','giờ'),T('PR opened → merged','PR mở → merge')),
      tile(G.not_green.length,'',T('Merged without all green','Merge khi chưa xanh đủ'),G.not_green.map(x=>'#'+x.pr+' ('+x.missing+')').join(', ')||null,G.not_green.length?'warn':'')));
    s.append(el('h3',{},T('Where the time goes (from the last push, hours)','Thời gian đi đâu (tính từ lần push cuối, giờ)')),rangeBars(G.comps,T('h','giờ')));
    s.append(el('h3',{style:'margin-top:14px'},T('Time to green per PR','Thời gian tới xanh mỗi PR')),histChart(G.hist,T('h','giờ'),T('Hours from the last push to all required checks green','Số giờ từ lần push cuối tới mọi check bắt buộc xanh')));
    // merges per week / month
    const WK=M.weeks||[];
    if(WK.length){const mx=niceMax(Math.max(...WK.map(w=>w.n))),W_=1000,H=190,ml=40,mr=8,mt=12,mb=30,iw=W_-ml-mr,ih=H-mt-mb,band=iw/WK.length,bw=Math.min(28,band*0.6),y=v=>mt+ih-ih*v/mx;
      const svg=sv('svg',{viewBox:`0 0 ${W_} ${H}`,class:'r11-svg',role:'img','aria-label':T('PRs merged per week','PR merge mỗi tuần')});
      [0,.5,1].forEach(f=>{const v=mx*f,yy=y(v);svg.append(sv('line',{x1:ml,x2:W_-mr,y1:yy,y2:yy,class:'r11-grid'}));const t=sv('text',{x:ml-6,y:yy+4,class:'r11-ax','text-anchor':'end'});t.textContent=fmt(Math.round(v));svg.append(t);});
      const inW=k=>k>=D.window[0].slice(0,10)&&k<=D.window[1];
      WK.forEach((w,i)=>{const x=ml+i*band+(band-bw)/2,h=ih*w.n/mx,g=sv('g',{class:'r11-col'});
        if(h>0)g.append(sv('path',{d:colPath(x,y(w.n),bw,h,4),fill:w.partial?'var(--text-muted)':(inW(w.k)?C1:C3)}));
        const hit=sv('rect',{x:ml+i*band,y:mt,width:band,height:ih,fill:'transparent'});g.append(hit);
        hover(hit,e=>showTip(e,[[`${w.n}`,T('PRs merged','PR merge')],[`${h1(w.p50)} h · p90 ${h1(w.p90)} h`,T('open → merge, median · p90','mở → merge, trung vị · p90')]].concat(w.partial?[[T('partial week','tuần chưa đủ'),'']]:[]),T('week of ','tuần từ ')+w.k));
        const t=sv('text',{x:x+bw/2,y:H-12,class:'r11-ax','text-anchor':'middle'});t.textContent=w.k.slice(5);svg.append(t);
        const tv=sv('text',{x:x+bw/2,y:y(w.n)-4,class:'r11-val','text-anchor':'middle'});tv.textContent=w.n;g.append(tv);svg.append(g);});
      s.append(el('h3',{style:'margin-top:14px'},T('PRs merged per week (and how long they were open)','PR merge mỗi tuần (và mở bao lâu)')),
        legend([[T('week inside the baseline window','tuần trong khung baseline'),C1],[T('week outside the window','tuần ngoài khung'),C3],[T('partial week','tuần chưa đủ'),'var(--text-muted)']]),svg,
        tableView([[T('Week of','Tuần từ')],[T('Merged','Merge'),'r'],[T('Open → merge median (h)','Mở → merge trung vị (giờ)'),'r'],[T('p90 (h)','p90 (giờ)'),'r']],WK.map(w=>[w.k+(w.partial?' *':''),w.n,h1(w.p50),h1(w.p90)])));}
    if((M.months||[]).length)s.append(el('h3',{style:'margin-top:14px'},T('Per month','Theo tháng')),table([[T('Month','Tháng')],[T('PRs merged','PR merge'),'r'],[T('Open → merge, h (median · p90)','Mở → merge, giờ (trung vị · p90)'),'r']],
      M.months.map(m=>el('tr',{},el('td',{},m.k+(m.partial?T(' (partial)',' (chưa đủ tháng)'):'')),el('td',{class:'r'},fmt(m.n)),el('td',{class:'r'},`${h1(m.p50)} · p90 ${h1(m.p90)}`)))));
    s.append(src(`Push time is not exposed by GitHub for every push, so the last push = the first check suite or Buildkite build created on the PR's last commit. Green = first success of each required check on that commit; Buildkite green = the first passed build finish (status context when no build is in the window). Merges per week / month: report_data.json (${M.start} → ${M.end}, merged PRs, by merge time UTC, weeks start on Monday).`,
      `GitHub không trả thời điểm push cho mọi lần push, nên lần push cuối = check suite hoặc build Buildkite đầu tiên tạo trên commit cuối của PR. Xanh = lần thành công đầu tiên của từng check bắt buộc trên commit đó; Buildkite xanh = lúc build pass đầu tiên kết thúc (dùng status context khi không có build trong khung). Merge theo tuần / tháng: report_data.json (${M.start} → ${M.end}, PR đã merge, theo giờ merge UTC, tuần bắt đầu thứ Hai).`));}

  // ================= 4 · Retry
  function rRetry(){const s=sec('retry');if(!s)return;const R=D.retry;
    s.replaceChildren(head('4','First-try failures that ran again','Fail lần đầu rồi chạy lại',
      `A first attempt failed and the same work ran again: a Buildkite job retry, a new build of the same commit, or a GitHub Actions re-run. ${fmt(R.n)} cases in ${W}. The cause is only called infrastructure or test when the log shows it; otherwise it stays unknown.`,
      `Lần chạy đầu fail và cùng việc đó được chạy lại: retry job trên Buildkite, build mới cho cùng commit, hoặc re-run trên GitHub Actions. ${fmt(R.n)} trường hợp trong ${W}. Chỉ gọi là hạ tầng hay test khi log cho thấy; nếu không thì để "chưa rõ".`));
    s.append(el('div',{class:'ops-kpis'},
      tile(R.gpu_h,'GPU-h',T('GPU lost to failed first tries','GPU mất vì lần đầu fail'),T(`run time only (queued time not included; with queued +${fmt(R.gpu_h_queue_add)} GPU-h) · ${R.share_gpu}% of PR GPU · ${fmt(R.per_day_gpu)} GPU-h per day`,`chỉ thời gian chạy (không tính chờ queue; có tính thì +${fmt(R.gpu_h_queue_add)} GPU-h) · ${R.share_gpu}% GPU của PR · ${fmt(R.per_day_gpu)} GPU-giờ mỗi ngày`),'warn'),
      tile(R.cpu_h,'job-h',T('CPU lost to failed first tries','CPU mất vì lần đầu fail'),T('GitHub Actions re-runs','lần chạy lại GitHub Actions')),
      tile(`${Math.round(100*R.bk_ok/Math.max(1,R.bk))}%`,'',T('Buildkite: passed next try','Buildkite: pass lần sau'),T(`${R.bk_ok} of ${R.bk}`,`${R.bk_ok} trên ${R.bk}`)),
      tile(`${Math.round(100*R.gh_ok/Math.max(1,R.gh))}%`,'',T('GitHub Actions: passed on re-run','GitHub Actions: pass khi chạy lại'),T(`${R.gh_ok} of ${R.gh}`,`${R.gh_ok} trên ${R.gh}`))));
    // goal (LM-1115): stop retrying work that cannot pass. One work item = one job label of one PR commit, across job retries and new builds.
    const NV=R.never;if(NV){
      s.append(el('h3',{},T('Retries that never pass','Retry không bao giờ pass')),
        el('div',{class:'ops-kpis'},
          tile(NV.chains,'',T('Work items tried 2+ times, never passed','Việc thử 2+ lần, không lần nào pass'),T('same PR commit and job label, across job retries and new builds','cùng commit PR và nhãn job, qua retry job và build mới'),'warn'),
          tile(NV.gpu_h,'GPU-h',T('GPU spent on them','GPU tốn cho chúng'),T(`run time only · with queued time ${fmt(NV.gpu_h_q)} GPU-h`,`chỉ thời gian chạy · có tính chờ queue ${fmt(NV.gpu_h_q)} GPU-h`),'warn'),
          tile(NV.nonretry_gpu_h,'GPU-h',T('…of which the failure cannot pass on retry','…trong đó lỗi không thể pass khi retry'),T(`${NV.nonretry_chains} items · log signature is a config or test failure, the same on every try`,`${NV.nonretry_chains} việc · dấu hiệu log là lỗi config hoặc test, giống nhau ở mọi lần thử`),'warn')),
        triesChart(NV),
        el('h4',{style:'margin:12px 0 4px'},T('Where it happens (2+ tries, never passed; costliest first)','Xảy ra ở đâu (2+ lần thử, không pass; tốn nhất trước)')),
        table([[T('Pipeline · job','Pipeline · job')],[T('Items','Việc'),'r'],[T('Tries','Lần thử'),'r'],['PRs','r'],[T('GPU-h (run · + queued)','GPU-h (chạy · + chờ)'),'r'],[T('Hours first → last try (median · p90)','Giờ lần đầu → lần cuối (trung vị · p90)'),'r'],[T('Most common log signature','Dấu hiệu log thường gặp nhất')]],
          NV.top.map(x=>el('tr',{},el('td',{},`${x.pipeline} · ${x.workload}`),el('td',{class:'r'},x.chains),el('td',{class:'r'},x.tries),el('td',{class:'r'},x.prs),el('td',{class:'r'},`${fmt(x.gpu_h)} · ${fmt(x.gpu_h_q)}`),
            el('td',{class:'r'},x.hours.p50==null?'—':`${fmt(x.hours.p50)} · ${fmt(x.hours.p90)}`),
            el('td',{},x.sig_name?L(x.sig_name):'—',' ',el('span',{class:'r11-cls'},el('span',{class:'r11-dot',style:`background:${CLSC[x.cls]||CN}`}),x.cls),x.nonretry?el('span',{class:'r11-nr'},T('retry will not help','retry không giúp được')):null)))),
        src('A work item fails "for good" when no try of it passed in the window. "Retry will not help" = the most common log signature is a config error (for example a test script missing for the engine) or a test failure, which repeats on every try; infrastructure failures (git, agent lost, network) can pass on a retry. Run time only unless the column says queued.',
          'Một việc fail "hẳn" khi không lần thử nào pass trong khung. "Retry không giúp được" = dấu hiệu log thường gặp nhất là lỗi config (ví dụ thiếu script test cho engine) hoặc test fail, lặp lại ở mọi lần thử; lỗi hạ tầng (git, mất agent, mạng) có thể pass khi retry. Chỉ thời gian chạy, trừ cột ghi có chờ queue.'));}
    const BC=Object.entries(R.bycls).map(([k,v])=>Object.assign({k},v)).filter(c=>c.n);
    s.append(el('h3',{},T('By evidence class','Theo loại bằng chứng')),
      rankBars(BC,{val:c=>c.n,lab:c=>L(D.cls[c.k]),col:c=>CLSC[c.k],fmtv:c=>`${c.n} ${T('cases','ca')}`,detail:c=>`${fmt(c.gpu_h)} GPU-h · ${fmt(c.cpu_h)} job-h · ${Math.round(100*c.ok/c.n)}% ${T('passed next','pass lần sau')}`,
        kinds:Object.keys(D.cls).map(k=>[L(D.cls[k]),CLSC[k]])}));
    s.append(el('h3',{style:'margin-top:14px'},T('Evidence found in the logs','Bằng chứng tìm thấy trong log')),table([[T('Signature','Dấu hiệu')],[T('Class','Loại')],[T('Cases','Ca'),'r'],['GPU-h','r'],[T('Example line from a log','Dòng ví dụ trong log')]],
      R.sigs.map(x=>el('tr',{},el('td',{},L(x.name)),el('td',{},el('span',{class:'r11-dot',style:`background:${CLSC[x.cls]||CN}`}),L(D.cls[x.cls]||x.cls)),el('td',{class:'r'},x.n),el('td',{class:'r'},fmt(x.gpu_h)),el('td',{},x.line?el('code',{class:'r11-line'},x.line):'—')))));
    s.append(el('h3',{style:'margin-top:14px'},T('By pipeline and step','Theo pipeline và bước')),table([[T('System · pipeline / workflow','Hệ thống · pipeline / workflow')],[T('Step','Bước')],[T('First attempts','Lần chạy đầu'),'r'],[T('Failed first','Fail lần đầu'),'r'],[T('Ran again','Chạy lại'),'r'],[T('Passed next','Pass lần sau'),'r'],[T('Failed again','Fail tiếp'),'r'],[T('Lost','Mất'),'r'],[T('Evidence','Bằng chứng')]],
      R.steps.map(x=>el('tr',{},el('td',{},`${x.system} · ${x.pipeline}`),el('td',{},x.step),el('td',{class:'r'},fmt(x.first)),el('td',{class:'r'},x.fail_pct==null?'—':`${x.first_fail} (${x.fail_pct}%)`),el('td',{class:'r'},x.n),el('td',{class:'r'},x.ok),el('td',{class:'r'},x.again),el('td',{class:'r'},`${fmt(x.lost_h)} ${x.unit}`),
        el('td',{},Object.entries(x.cls).sort((a,b)=>b[1]-a[1]).map(([k,v])=>el('span',{class:'r11-cls'},el('span',{class:'r11-dot',style:`background:${CLSC[k]}`}),`${k} ${v}`)))))));
    s.append(src(`Evidence = the failure region of the Buildkite log (the 120 lines before the agent's error line, last 400 KB, read by P1/sample_fail_logs.py; only the matched line is kept). "Performance threshold missed" and "test reported failed" that then pass on the same commit point to a timing-sensitive or flaky test, but a busy shared GPU can cause the same, so treat them as test-side evidence, not proof. GitHub Actions logs are not read: every GitHub re-run stays unknown. Kinds: ${Object.entries(R.kinds).map(([k,v])=>k+' '+v).join(', ')}.`,
      `Bằng chứng = vùng lỗi của log Buildkite (120 dòng trước dòng lỗi của agent, trong 400 KB cuối, đọc bằng P1/sample_fail_logs.py; chỉ giữ dòng khớp). "Trượt ngưỡng hiệu năng" và "test báo fail" mà chạy lại trên cùng commit thì pass cho thấy test nhạy thời gian hoặc flaky, nhưng GPU dùng chung bị bận cũng gây ra như vậy, nên coi là bằng chứng phía test, chưa phải kết luận. Log GitHub Actions không được đọc: mọi lần chạy lại trên GitHub để "chưa rõ". Loại: ${Object.entries(R.kinds).map(([k,v])=>k+' '+v).join(', ')}.`));}

  // ================= 5 · Per PR × commit
  let PRS={q:'',sort:9,all:false,open:new Set()};
  function rPrs(){const s=sec('prs');if(!s)return;const P=D.prs,Cm=D.commits;
    s.replaceChildren(head('5','Per PR and commit','Theo PR và commit',
      `Every PR with CI in ${W} (${fmt(P.length)} PRs). Open a row to see each commit: its exact SHA, what ran on it, and links to the Buildkite build and the GitHub commit.`,
      `Mọi PR có CI trong ${W} (${fmt(P.length)} PR). Mở một dòng để xem từng commit: SHA chính xác, những gì đã chạy trên đó, và link tới build Buildkite và commit GitHub.`));
    const COLS=[['PR'],[T('Author','Tác giả')],[T('Merged','Merge')],[T('Pushes','Push'),'r'],[T('GHA runs','Run GHA'),'r'],[T('CPU job-min','Phút job CPU'),'r'],[T('GHA re-runs','GHA chạy lại'),'r'],[T('MP builds','Build MP'),'r'],[T('Unit builds','Build unit'),'r'],['GPU-min','r'],[T('BK retried jobs','Job BK retry'),'r'],[T('Same-commit rebuilds','Build lại cùng commit'),'r'],[T('Time to green (h)','Tới xanh (giờ)'),'r']];
    const SORTS=[[9,'GPU-min'],[5,T('CPU job-min','Phút job CPU')],[10,T('retries','retry')],[12,T('time to green','thời gian tới xanh')],[0,'PR']];
    const ctl=el('div',{class:'r11-ctl'},
      el('input',{type:'search',placeholder:T('Filter by PR number or author','Lọc theo số PR hoặc tác giả'),value:PRS.q,oninput:e=>{PRS.q=e.target.value.trim().toLowerCase();draw();}}),
      el('label',{},T('Sort by ','Sắp theo '),el('select',{onchange:e=>{PRS.sort=+e.target.value;draw();}},SORTS.map(([k,n])=>el('option',{value:k,...(k===PRS.sort?{selected:''}:{})},n)))),
      el('button',{type:'button',class:'tr-btn sm',onclick:()=>csvDl('lm1130_pr_30d.csv',['pr','author','merged','pushes_with_ci','gha_workflow_runs','gha_job_min','gha_rerun_jobs','mp_builds','unit_builds','gpu_min','bk_retried_jobs','same_commit_rebuilds','time_to_green_h','head_commit'],P)},T('Download PRs (CSV)','Tải PR (CSV)')),
      el('button',{type:'button',class:'tr-btn sm',onclick:()=>csvDl('lm1130_pr_commit_30d.csv',['pr','commit','first_ci_at_utc','gha_workflow_runs','gha_job_min','gha_rerun_jobs','mp_builds','unit_builds','gpu_min','bk_retried_jobs','last_mp_build','last_unit_build'],Object.entries(Cm).flatMap(([p,cs])=>cs.map(c=>[p,...c]))) },T('Download commits (CSV)','Tải commit (CSV)')));
    const box=el('div');s.append(ctl,box);
    function draw(){let rows=P.filter(r=>!PRS.q||String(r[0]).includes(PRS.q)||(r[1]||'').toLowerCase().includes(PRS.q));
      const k=PRS.sort;rows=rows.slice().sort((a,b)=>k===0?b[0]-a[0]:((b[k]??-1)-(a[k]??-1)));const shown=PRS.all?rows:rows.slice(0,50);
      const t=el('table',{class:'obs-t r11-prs'});t.append(el('thead',{},el('tr',{},el('th',{}),COLS.map(c=>el('th',{class:c[1]||''},c[0])))));const tb=el('tbody');
      shown.forEach(r=>{const op=PRS.open.has(r[0]);
        tb.append(el('tr',{class:'r11-pr'+(op?' on':''),onclick:()=>{op?PRS.open.delete(r[0]):PRS.open.add(r[0]);draw();}},el('td',{},el('button',{type:'button',class:'r11-x','aria-expanded':String(op),'aria-label':T('show commits','xem commit')},op?'−':'+')),
          el('td',{},link(`${GH}/pull/${r[0]}`,'#'+r[0])),el('td',{},r[1]),el('td',{},r[2]||'—'),...[3,4,5,6,7,8,9,10,11,12].map(i=>el('td',{class:'r'},r[i]==null?'—':fmt(r[i])))));
        if(op){const cs=Cm[String(r[0])]||[];
          const ccols=[[T('Commit (first CI, UTC)','Commit (CI đầu tiên, UTC)')],[T('GHA runs','Run GHA'),'r'],[T('CPU job-min','Phút job CPU'),'r'],[T('GHA re-runs','GHA chạy lại'),'r'],[T('MP builds','Build MP'),'r'],[T('Unit builds','Build unit'),'r'],['GPU-min','r'],[T('BK retried','BK retry'),'r'],[T('Last builds','Build cuối')]];
          const crow=c=>{const sha=el('td',{},link(`${GH}/pull/${r[0]}/commits/${c[0]}`,el('code',{},c[0].slice(0,10))),' ',el('span',{class:'meta'},c[1]),c[0]===r[13]?el('b',{class:'r11-head'},T(' merged head',' head khi merge')):null);
            const nums=[2,3,4,5,6,7,8].map(i=>el('td',{class:'r'},c[i]==null?'—':fmt(c[i])));
            const bl=el('td',{},c[9]?link(`${BK}k3-multiprocess-test/builds/${c[9]}`,'MP #'+c[9]):null,c[9]&&c[10]?' · ':null,c[10]?link(`${BK}k3-unit-tests/builds/${c[10]}`,'unit #'+c[10]):null);
            return el('tr',{},sha,...nums,bl);};
          tb.append(el('tr',{class:'r11-sub'},el('td',{colspan:COLS.length+1},table(ccols,cs.map(crow)))));}});
      t.append(tb);box.replaceChildren(el('div',{class:'obs-scroll'},t),rows.length>50?el('button',{type:'button',class:'tr-btn sm',style:'margin-top:8px',onclick:()=>{PRS.all=!PRS.all;draw();}},PRS.all?T('Show top 50','Chỉ hiện 50 dòng đầu'):T(`Show all ${rows.length}`,`Hiện cả ${rows.length}`)):null);}
    draw();
    s.append(src('Buildkite build pages and GitHub pages are public: the links open without a login. Retries counted per PR = Buildkite job retries + GitHub Actions re-run attempts + extra builds of the same commit.','Trang build Buildkite và trang GitHub là công khai: link mở được khi chưa đăng nhập. Số retry mỗi PR = retry job Buildkite + lần chạy lại GitHub Actions + build thêm cho cùng commit.'));}

  // ================= 6 · Track
  function rTrack(){const s=sec('track');if(!s)return;const K=D.track;
    s.replaceChildren(head('6','Track against the baseline','Theo dõi so với baseline','The last 24 h of the same sources next to the 30-day baseline, in the same units (GPU-min uses the same GPU-per-workload map as the baseline).','24 giờ gần nhất của cùng nguồn đặt cạnh baseline 30 ngày, cùng đơn vị (GPU-phút dùng cùng bảng số GPU mỗi workload như baseline).'));
    if(!K){s.append(el('div',{class:'ops-empty'},T('No 24 h data yet: run observe_ops_collect.py.','Chưa có dữ liệu 24 giờ: chạy observe_ops_collect.py.')));return;}
    if(K.n_retried===0&&K.n_failed)s.append(el('div',{class:'ops-verdict',style:'border-left-color:var(--warning)'},T(`No job was marked "retried" by Buildkite in the last ${K.span_h} h, while ${K.n_failed} GPU jobs failed. If automatic retries were turned off, retry waste now shows up as failed jobs: read "Failed GPU-min per day".`,
      `Không có job nào được Buildkite đánh dấu "retried" trong ${K.span_h} giờ qua, trong khi có ${K.n_failed} job GPU fail. Nếu retry tự động đã bị tắt, lãng phí do retry giờ nằm ở job fail: đọc dòng "GPU-phút fail mỗi ngày".`)));
    s.append(el('h3',{},T(`Now (last ${K.span_h} h) as a percent of the 30-day baseline`,`Hiện tại (${K.span_h} giờ gần nhất) tính theo % baseline 30 ngày`)),dumbbells(K.rows));
    s.append(table([[T('Metric','Metric')],[T('Baseline (30 d)','Baseline (30 ngày)'),'r'],[T(`Now (last ${K.span_h} h)`,`Hiện tại (${K.span_h} giờ gần nhất)`),'r'],[T('Change','Thay đổi'),'r']],K.rows.map(r=>{
      const ch=r.base&&r.now!=null?Math.round(100*(r.now-r.base)/r.base):null,good=ch==null?null:(r.better==='up'?ch>0:ch<0);
      return el('tr',{},el('td',{},L(r.label)),el('td',{class:'r'},`${fmt(r.base)} ${r.unit}`),el('td',{class:'r'},r.now==null?(r.na?L(r.na):'—'):`${fmt(r.now)} ${r.unit}`),el('td',{class:'r'},ch==null?'—':el('b',{style:`color:var(--${Math.abs(ch)<5?'text-muted':good?'good':'critical'})`},`${ch>0?'+':''}${ch}%`)));})));
    if((D.hist||[]).length)s.append(el('h3',{style:'margin-top:14px'},T('Daily history (one row per collector day, job-min)','Lịch sử theo ngày (mỗi ngày chạy collector một dòng, phút job)')),table([[T('Day','Ngày')],[T('MP job-min','Phút job MP'),'r'],[T('Unit job-min','Phút job unit'),'r'],[T('GPU re-run min','Phút GPU chạy lại'),'r'],[T('CPU re-run min','Phút CPU chạy lại'),'r']],D.hist.map(h=>el('tr',{},el('td',{},h.date),el('td',{class:'r'},fmt(h.mp)),el('td',{class:'r'},fmt(h.unit)),el('td',{class:'r'},fmt(h.gpu_rerun)),el('td',{class:'r'},fmt(h.cpu_rerun))))));
    s.append(src('One day is noisy: compare a 7-day average with the baseline before calling a change. 24 h CPU = GitHub Actions runs with a pull_request event; the baseline counts jobs on PR commits, which is the same set in practice. To make a new baseline, change the dates in outputs/P1/window.json and re-run the Reproduce steps; keep the old files to compare.','Một ngày còn nhiễu: so trung bình 7 ngày với baseline trước khi kết luận. CPU 24 giờ = run GitHub Actions có sự kiện pull_request; baseline đếm job trên commit của PR, thực tế là cùng tập. Muốn baseline mới, đổi ngày trong outputs/P1/window.json rồi chạy lại các bước Reproduce; giữ file cũ để so sánh.'));}

  // ================= 7 · Reproduce + definitions
  function rRepro(){const s=sec('repro');if(!s)return;const Q=D.quality;
    s.replaceChildren(head('7','Reproduce the numbers','Tái tạo số liệu',`Run from LM-762-ci-resource/plan-2026-11/, in this order. Steps 1–3 call the Buildkite / GitHub APIs (read-only; Buildkite token from the environment, GitHub through the logged-in gh CLI); the rest only read local files, so the same inputs give the same numbers. The window is fixed in outputs/P1/window.json: ${D.since} → ${D.until} (end excluded).`,
      `Chạy từ LM-762-ci-resource/plan-2026-11/, theo thứ tự này. Bước 1–3 gọi API Buildkite / GitHub (chỉ đọc; token Buildkite từ biến môi trường, GitHub qua gh CLI đã đăng nhập); các bước còn lại chỉ đọc file local, nên cùng đầu vào cho cùng kết quả. Khung cố định trong outputs/P1/window.json: ${D.since} → ${D.until} (không gồm mốc cuối).`));
    const steps=[[T('Buildkite builds + jobs of the required GPU pipelines (window end fixed)','Build + job Buildkite của các pipeline GPU bắt buộc (cố định mốc cuối)'),'python -I -X utf8 outputs/P1/fetch_builds.py'],
      [T('GitHub PRs, commits and all check runs incl. re-runs (+ force-pushed commits by SHA)','PR, commit và mọi check run trên GitHub kể cả chạy lại (+ commit bị force-push, đọc theo SHA)'),'python -I -X utf8 outputs/P1/fetch_gh_checks.py'],
      [T('Per-job table (both pipelines, commit SHA, GPU-min, queue)','Bảng theo job (hai pipeline, SHA commit, GPU-phút, queue)'),'python -I -X utf8 outputs/P1/build_jobs_table.py'],
      [T('Evidence from failed-then-retried logs (keeps earlier results; --fresh to redo)','Bằng chứng từ log fail rồi retry (giữ kết quả cũ; --fresh để làm lại)'),'python -I -X utf8 outputs/P1/sample_fail_logs.py'],
      [T('MP detail per workload (startup share, cost by label)','Chi tiết MP theo workload (tỉ lệ khởi động, chi phí theo label)'),'python -I -X utf8 outputs/P1/aggregate.py'],
      [T('Join PR × commit × builds; time to green; retry events','Nối PR × commit × build; thời gian tới xanh; sự kiện retry'),'python -I -X utf8 outputs/P1/build_pr_table.py'],
      [T('Last 24 h for the Track tab (optional)','24 giờ gần nhất cho tab Track (tuỳ chọn)'),'python -I -X utf8 outputs/cpu_tests/observe_ops_collect.py --no-build'],
      [T('Rebuild this report','Build lại báo cáo này'),'python -I -X utf8 outputs/cpu_tests/build_report1130.py']];
    s.append(el('ol',{class:'r11-steps'},steps.map(([t,c])=>el('li',{},el('div',{},t),el('code',{class:'obsraw'},c),' ',el('button',{type:'button',class:'tr-btn sm',onclick:e=>{try{navigator.clipboard.writeText(c);e.target.textContent='✓';}catch(x){}}},T('Copy','Chép'))))));
    s.append(el('h3',{},T('Definitions','Định nghĩa')),table([[T('Term','Thuật ngữ')],[T('Rule','Quy tắc')]],[
      [T('Window','Khung thời gian'),T(`${D.window.join(' → ')} (${D.days} days, UTC). Buildkite: build created_at in the window. GitHub Actions: workflow (check suite) created in the window. Merged PRs: merged_at in the window.`,`${D.window.join(' → ')} (${D.days} ngày, UTC). Buildkite: created_at của build nằm trong khung. GitHub Actions: workflow (check suite) tạo trong khung. PR merge: merged_at nằm trong khung.`)],
      [T('PR build','Build PR'),T('A Buildkite build of k3-multiprocess-test or k3-unit-tests with a pull_request. Dev pushes and nightlies are left out.','Build Buildkite của k3-multiprocess-test hoặc k3-unit-tests có pull_request. Bỏ push dev và nightly.')],
      [T('Required checks','Check bắt buộc'),T('DCO, Check code quality, buildkite/k3-unit-tests, buildkite/k3-multiprocess-test (GitHub isRequired = true on the PRs of the window).','DCO, Check code quality, buildkite/k3-unit-tests, buildkite/k3-multiprocess-test (GitHub isRequired = true trên các PR trong khung).')],
      [T('Execution','Thời gian chạy'),T('Job start → job end. Buildkite: started_at → finished_at. GitHub: check run startedAt → completedAt.','Job bắt đầu → job xong. Buildkite: started_at → finished_at. GitHub: startedAt → completedAt của check run.')],
      [T('Queue','Chờ queue'),T('Buildkite: runnable_at → started_at (waiting for an agent). GitHub: not available for old runs; "start delay" (workflow created → job start) is shown instead and named so.','Buildkite: runnable_at → started_at (chờ agent). GitHub: không có cho run cũ; hiện "độ trễ bắt đầu" (tạo workflow → job bắt đầu) và ghi rõ tên.')],
      ['GPU-min',T('Execution minutes × GPUs the job asks for (pod limit nvidia.com/gpu in pipeline.yml). Jobs with no known GPU count are left out and listed in Data quality.','Số phút chạy × số GPU job yêu cầu (pod limit nvidia.com/gpu trong pipeline.yml). Job không rõ số GPU bị bỏ và liệt kê ở Data quality.')],
      ['job-min',T('Execution minutes of one job on one runner / agent (CPU side).','Số phút chạy của một job trên một runner / agent (phía CPU).')],
      [T('Trigger','Lần trigger'),T('Per PR: pushes with CI (distinct commits that got a check suite or build), GitHub workflow runs, Buildkite builds per pipeline.','Mỗi PR: số lần push có CI (commit khác nhau có check suite hoặc build), số workflow run GitHub, số build Buildkite theo pipeline.')],
      [T('Ran again','Chạy lại'),T('A first attempt that failed and then ran again: Buildkite retried job (automatic or manual), a new build of the same commit after a failed one, or a GitHub Actions re-run attempt.','Lần chạy đầu fail rồi được chạy lại: job Buildkite bị retry (tự động hoặc tay), build mới cho cùng commit sau build fail, hoặc lần re-run trên GitHub Actions.')],
      [T('Evidence class','Loại bằng chứng'),T('infrastructure / test / code-config only when a known line is in the failure region of the log; unknown otherwise (incl. all GitHub re-runs).','hạ tầng / test / code-cấu hình chỉ khi có dòng nhận diện trong vùng lỗi của log; ngược lại là chưa rõ (gồm mọi lần chạy lại trên GitHub).')],
      [T('Time to green','Thời gian tới xanh'),T('Last push (first check suite / build on the PR\'s last commit) → the latest of the four required checks\' first success on that commit.','Lần push cuối (check suite / build đầu tiên trên commit cuối của PR) → thời điểm muộn nhất trong bốn lần thành công đầu tiên của các check bắt buộc trên commit đó.')],
      [T('Merge latency','Độ trễ merge'),T('PR created → merged, hours.','PR tạo → merge, giờ.')]].map(([a,b])=>el('tr',{},el('td',{},el('b',{},a)),el('td',{},b)))));
    s.append(el('h3',{style:'margin-top:14px'},T('Input files of this build (sha256, first 12)','File đầu vào của lần build này (sha256, 12 ký tự đầu)')),table([[T('File','File')],['sha256','r'],['KB','r'],[T('Written (UTC)','Ghi lúc (UTC)'),'r']],Q.inputs.map(x=>el('tr',{},el('td',{},el('code',{},x.path)),el('td',{class:'r'},el('code',{},x.sha)),el('td',{class:'r'},fmt(x.kb)),el('td',{class:'r'},x.made)))));}

  // ================= 8 · Data quality
  function rQuality(){const s=sec('quality');if(!s)return;const Q=D.quality;
    s.replaceChildren(head('8','Data quality & coverage','Chất lượng & độ phủ dữ liệu','What is in, what is not, and where the numbers are weaker. Read this before you quote a number.','Cái gì có, cái gì không, và chỗ nào số liệu yếu hơn. Đọc phần này trước khi trích dẫn một con số.'));
    const li=(st,en,vi)=>el('li',{},el('span',{class:'r11-q '+st},st==='ok'?'OK':st==='gap'?T('gap','thiếu'):T('note','lưu ý')),' ',T(en,vi));
    s.append(el('h3',{},T('Coverage','Độ phủ')),el('ul',{class:'r11-ql'},
      li('ok',`Required GPU checks: k3-multiprocess-test and k3-unit-tests, all PR builds in the window (with retried job attempts). Unfinished builds at fetch time: ${Q.unfinished}.`,`Check GPU bắt buộc: k3-multiprocess-test và k3-unit-tests, mọi build PR trong khung (kể cả lần job bị retry). Build chưa xong lúc lấy dữ liệu: ${Q.unfinished}.`),
      li('ok',`GitHub: ${fmt(Q.prs_in_github_list)} PRs open at some time in the window, every commit, every check run incl. re-run attempts (${fmt(Q.gha_job_attempts)} GitHub Actions job attempts that ran).`,`GitHub: ${fmt(Q.prs_in_github_list)} PR mở trong khung, mọi commit, mọi check run kể cả lần chạy lại (${fmt(Q.gha_job_attempts)} lần chạy job GitHub Actions có chạy).`),
      li('ok',`Force-pushed commits: ${fmt(Q.commits_force_pushed_away)} (PR, commit) pairs had Buildkite builds on a commit that is no longer in the PR; their GitHub checks were read by SHA (${fmt(Q.orphans)} commits). Without GitHub checks: ${fmt(Q.commits_without_github_checks||0)}.`,`Commit bị force-push: ${fmt(Q.commits_force_pushed_away)} cặp (PR, commit) có build Buildkite trên commit không còn trong PR; check GitHub của chúng được đọc theo SHA (${fmt(Q.orphans)} commit). Không có check GitHub: ${fmt(Q.commits_without_github_checks||0)}.`),
      li('gap',`Other Buildkite pipelines that report on PRs are not in this baseline (not required checks): ${Q.other_pipelines.slice(0,10).map(x=>x.name+' '+x.n).join(', ')} (status updates in the window).`,`Các pipeline Buildkite khác có báo trên PR không nằm trong baseline này (không phải check bắt buộc): ${Q.other_pipelines.slice(0,10).map(x=>x.name+' '+x.n).join(', ')} (số lần cập nhật status trong khung).`),
      li('gap','Dev-branch pushes and nightlies are left out by design (PR baseline).','Push lên dev và nightly bị bỏ có chủ đích (baseline của PR).')));
    s.append(el('h3',{},T('Fields that are missing or weaker','Trường bị thiếu hoặc yếu hơn')),el('ul',{class:'r11-ql'},
      li('gap','GitHub Actions runner queue: unavailable for old runs. The CPU tab shows "start delay" (workflow created → job start) instead, which also holds the wait for earlier jobs.','Thời gian chờ runner GitHub Actions: không có cho run cũ. Tab CPU hiện "độ trễ bắt đầu" (tạo workflow → job bắt đầu), gồm cả chờ các job trước.'),
      li('gap','Push time: GitHub does not record every push. The last push = the first check suite or build created on the commit (usually seconds after the push).','Thời điểm push: GitHub không ghi mọi lần push. Lần push cuối = check suite hoặc build đầu tiên tạo trên commit (thường vài giây sau push).'),
      li('note',`GPU count per job comes from a static map of pod specs (unchanged in the window). Jobs with no known count are left out of GPU-min: ${fmt(Q.bk_jobs_without_gpu_count)} jobs, ${fmt(Q.bk_job_min_without_gpu_count)} job-min (${Q.bk_unknown_gpu_workloads}).`,`Số GPU mỗi job lấy từ bảng tĩnh theo pod spec (không đổi trong khung). Job không rõ số GPU bị bỏ khỏi GPU-phút: ${fmt(Q.bk_jobs_without_gpu_count)} job, ${fmt(Q.bk_job_min_without_gpu_count)} phút job (${Q.bk_unknown_gpu_workloads}).`),
      li('note','k3-unit-tests waits for a free GPU inside the job (pick-free-gpu.sh, up to 60 min). That wait is counted as execution, because Buildkite cannot see it.','k3-unit-tests chờ GPU trống bên trong job (pick-free-gpu.sh, tối đa 60 phút). Thời gian chờ này bị tính là chạy, vì Buildkite không thấy được.'),
      li('note',`Retry evidence: ${fmt(Q.fail_logs_read)} failed-attempt logs read, ${fmt(Q.fail_logs_unreadable)} could not be read (counted as unknown). GitHub Actions logs are not read.`,`Bằng chứng retry: đọc được ${fmt(Q.fail_logs_read)} log của lần fail, ${fmt(Q.fail_logs_unreadable)} log không đọc được (tính là chưa rõ). Log GitHub Actions không được đọc.`),
      li('note',`Time to green: ${fmt(Q.ttg_not_green)} merged PRs never had all four checks green on the merged commit (listed on the Time to green tab); ${fmt(Q.ttg_bk_green_from_status_context||0)} Buildkite green times come from the status context because the passing build was before the window.`,`Thời gian tới xanh: ${fmt(Q.ttg_not_green)} PR đã merge chưa từng xanh đủ bốn check trên commit được merge (liệt kê ở tab Time to green); ${fmt(Q.ttg_bk_green_from_status_context||0)} mốc xanh Buildkite lấy từ status context vì build pass nằm trước khung.`),
      li('note','The earlier version of this baseline had no window end date and read 937 MP builds, 2 still running. The window now has a fixed end, so the MP numbers moved a little (941 builds, none running).','Phiên bản trước của baseline không có mốc cuối và đọc 937 build MP, 2 build còn đang chạy. Giờ khung có mốc cuối cố định, nên số MP thay đổi một chút (941 build, không build nào đang chạy).')));
    s.append(el('h3',{},T('GPU count per workload (from pipeline.yml)','Số GPU mỗi workload (từ pipeline.yml)')),el('p',{class:'meta'},Object.entries(Q.gpu_map).map(([k,v])=>`${k} ${v}`).join(' · ')));
    s.append(src(`GitHub data read ${(Q.gh_made||'').replace('T',' ').slice(0,16)} UTC. Report built ${D.made.replace('T',' ').slice(0,16)} UTC. Raw files are kept in outputs/P1/raw so the same numbers can be rebuilt without the APIs.`,`Dữ liệu GitHub đọc lúc ${(Q.gh_made||'').replace('T',' ').slice(0,16)} UTC. Báo cáo build lúc ${D.made.replace('T',' ').slice(0,16)} UTC. File thô giữ trong outputs/P1/raw nên có thể build lại cùng số liệu mà không cần gọi API.`));}

  function render(){rBaseline();rCpu();rGreen();rRetry();rPrs();rTrack();rRepro();rQuality();}
  render();addEventListener('langchange',render);
})();
</script>
<!-- R1130:JS:END -->
"""

CSS = r"""
/* R1130:CSS:START */
.r11-steps{margin:6px 0 12px;padding-left:20px;font-size:13px}
.r11-steps li{margin-bottom:8px}
.r11-steps code{font-size:12px}
.r11-svg{width:100%;height:auto;display:block;overflow:visible}
.r11-grid{stroke:var(--grid);stroke-width:1}
.r11-rule{stroke:var(--text-muted);stroke-width:1;stroke-dasharray:3 3}
.r11-ax{font-size:11px;fill:var(--text-muted);font-variant-numeric:tabular-nums}
.r11-rl{fill:var(--text-secondary);font-weight:600}
.r11-lab{font-size:12px;fill:var(--text-primary)}
.r11-val{font-size:11.5px;fill:var(--text-secondary);font-variant-numeric:tabular-nums}
.r11-col.on path,.r11-col.on circle{filter:brightness(1.12)}
.r11-col rect:focus{outline:none}.r11-col rect:focus-visible{stroke:var(--text-muted);stroke-width:1}
.r11-leg{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--text-secondary);margin:4px 0 6px}
.r11-leg span{display:inline-flex;align-items:center;gap:6px}.r11-leg i{width:10px;height:10px;border-radius:3px;display:inline-block}
.r11-tv{margin-top:6px;font-size:12px}.r11-tv summary{cursor:pointer;color:var(--text-secondary)}
.r11-tip{position:fixed;z-index:50;display:none;pointer-events:none;background:var(--surface-1);border:1px solid var(--border);border-radius:8px;padding:6px 9px;font-size:12px;box-shadow:0 4px 14px rgba(0,0,0,.18);max-width:300px}
.r11-tip .tt{color:var(--text-muted);margin-bottom:3px}.r11-tip .tr{display:flex;align-items:center;gap:6px}.r11-tip .tr b{color:var(--text-primary)}.r11-tip .tr span{color:var(--text-secondary)}
.r11-tip i{width:10px;height:2px;border-radius:1px;display:inline-block}
.r11-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle}
.r11-cls{display:inline-flex;align-items:center;margin-right:10px;font-size:12px;white-space:nowrap}
.r11-line{font-size:11.5px;white-space:pre-wrap;word-break:break-word;color:var(--text-secondary)}
.r11-ctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:6px 0 10px;font-size:13px}
.r11-ctl input[type=search]{min-width:220px;padding:5px 8px;border:1px solid var(--border);border-radius:6px;background:var(--surface-1);color:var(--text-primary)}
.r11-ctl select{padding:4px 6px;border:1px solid var(--border);border-radius:6px;background:var(--surface-1);color:var(--text-primary)}
.r11-prs tr.r11-pr{cursor:pointer}.r11-prs tr.r11-pr.on td{background:var(--surface-2,transparent)}
.r11-x{border:1px solid var(--border);background:transparent;color:var(--text-secondary);border-radius:4px;width:20px;height:20px;line-height:16px;padding:0;cursor:pointer}
.r11-sub>td{padding:4px 0 10px 28px}.r11-head{color:var(--text-secondary);font-size:11.5px;margin-left:6px}
.r11-ql{margin:4px 0 12px;padding-left:18px;font-size:13px}.r11-ql li{margin-bottom:6px}
.r11-q{display:inline-block;min-width:38px;text-align:center;font-size:11px;font-weight:600;border-radius:4px;padding:0 5px;border:1px solid var(--border);color:var(--text-secondary)}
.r11-q.gap{border-left:3px solid var(--warning);color:var(--text-primary)}.r11-q.ok{border-left:3px solid var(--good)}
.r11-stat{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:12px 14px;min-width:0;display:flex;flex-direction:column;gap:4px}
.r11-stat.warn{border-color:var(--warning)}
.r11-stat .l{font-size:12.5px;color:var(--text-secondary);line-height:1.3}
.r11-stat .v{font-size:26px;font-weight:600;color:var(--text-primary);line-height:1.15;font-variant-numeric:tabular-nums;display:flex;align-items:baseline;gap:5px;flex-wrap:wrap}
.r11-stat .v .u{font-size:13px;font-weight:500;color:var(--text-muted)}
.r11-stat .v .tag{font-size:11px;font-weight:500;color:var(--text-secondary);border:1px solid var(--border);border-radius:999px;padding:0 7px;line-height:17px}
.r11-stat .s{font-size:12px;color:var(--text-muted);line-height:1.35}
.r11-stat .p9{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;font-size:12px;color:var(--text-muted)}
.r11-stat .p9 b{font-size:13.5px;font-weight:600;color:var(--text-primary);font-variant-numeric:tabular-nums}
.r11-meter{height:4px;border-radius:2px;background:color-mix(in srgb, var(--series-1) 25%, var(--surface-1));margin:3px 0 1px;overflow:hidden}
.r11-meter i{display:block;height:100%;border-radius:2px;background:var(--series-1)}
.r11-sws{display:flex;flex-wrap:wrap;gap:8px 12px;margin:4px 0 8px}
.r11-swg{display:inline-flex;background:var(--surface-2);border-radius:9px;padding:3px;gap:2px}
.r11-sw{all:unset;cursor:pointer;font-size:12px;font-weight:600;padding:4px 10px;border-radius:7px;color:var(--text-secondary)}
.r11-sw:hover{color:var(--text-primary)}
.r11-sw.on{background:var(--surface-1);color:var(--text-primary);box-shadow:0 0 0 1px var(--border)}
.r11-sw:focus-visible{outline:2px solid var(--series-1)}
.r11-qnote{font-size:12.5px;color:var(--text-secondary);border-left:3px solid var(--border);padding:4px 10px;margin:0 0 6px;border-radius:2px}
.r11-qnote b{color:var(--text-primary)}
.r11-qnote.on{border-left-color:var(--warning);background:color-mix(in oklab,var(--warning) 12%,transparent)}
.r11-p90{stroke:var(--text-primary);stroke-dasharray:none;stroke-width:1.5}
.r11-p90t{fill:var(--text-primary);font-weight:700}
.r11-nr{display:inline-block;margin-left:6px;font-size:11px;font-weight:650;padding:0 6px;border-radius:5px;border:1px solid var(--critical);color:var(--crit-text)}
.r11-ext{float:right;margin:2px 0 0 12px}
/* R1130:CSS:END */
"""


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor) if before else page.index(anchor) + len(anchor)
    return page[:i] + ("" if before else "\n") + block.strip() + ("\n" if before else "") + page[i:]


def main():
    data = analyze()
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    page = open(PAGE, encoding="utf-8").read()
    page = put(page, "/* R1130:CSS:START */", "/* R1130:CSS:END */", CSS, "@media (max-width:980px)")
    page = put(page, "<!-- R1130:HTML:START -->", "<!-- R1130:HTML:END -->", HTML, "<!-- ONBOARD:HTML:START -->")
    page = put(page, "<!-- R1130:JS:START -->", "<!-- R1130:JS:END -->", JS.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")), "</body>")
    open(PAGE, "w", encoding="utf-8").write(page)
    g, c, t, r = data["gpu"], data["cpu"], data["ttg"], data["retry"]
    print(f"r1130: {data['window']} GPU {g['gpu_h']} GPU-h ({g['prs']} PRs); CPU {c['job_h']} job-h ({c['prs']} PRs); "
          f"time to green p50 {t['all']['p50']} h p90 {t['all']['p90']} h ({t['green']}/{t['n']}); ran again {r['n']} ({r['gpu_h']} GPU-h, {r['cpu_h']} job-h); PR rows {len(data['prs'])}")


if __name__ == "__main__":
    main()
