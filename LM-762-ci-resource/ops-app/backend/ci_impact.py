"""Before / after metrics of the merged CI changes (#6730 tiered pre-review CI, #6731 split k3-multiprocess,
#6854 weekly full build). Pure functions, Python stdlib only; collect_ci_impact.py feeds them and stores the result.

Both windows go through the SAME functions on rows of the SAME shape, so a delta never mixes two methods:
  bk   one row per Buildkite job attempt, the columns of plan-2026-11/outputs/P1_*/jobs_all_30d.csv
       (pipeline, build_number, build_state, is_pr, pr, branch, build_created, commit, label, workload, gpus, state,
        retried, retried_in_job_id, runnable_at, started_at, finished_at, wall_min, queue_wait_min, gpu_min, job_id)
  gha  one row per GitHub Actions job attempt on a PR commit, the columns of gh_jobs_30d.csv
       (pr, commit, workflow, event, job, conclusion, suite_created, started, completed, exec_min, attempt)
  draft(pr, iso) -> True / False / None   PR draft state at that moment (GitHub timeline)
  conv  [(pr, iso)] convert-to-draft events in the window

Units as in Report 1130: GPU-min = job execution minutes x GPUs of the job; job-min = execution minutes of a
GitHub runner. Queue time is never added to execution. Nothing is extrapolated: a metric whose After sample is below
its minimum shows the sample and state 'insufficient', not a number; a window younger than MIN_DAYS is 'collecting'.
"""
import datetime as dt

MIN_DAYS = 14         # a window shorter than this is 'collecting': two full weeks, so weekdays are matched (review 2026-11-26)
WEEKLY_BRANCH = "ci-weekly-full"   # weekly full build: its own metric, never mixed into PR / daily GPU totals
UNIT, MP, SMOKE = "k3-unit-tests", "k3-multiprocess-test", "k3-multiprocess-smoke"
L2_WF = ("Test", "CPU Device Tests")


def ts(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def mins(a, b):
    a, b = ts(a), ts(b)
    return (b - a).total_seconds() / 60 if a and b else None


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def r1(x):
    return None if x is None else round(x, 1)


def truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes")


def days(win):
    a, b = ts(win["since"]), ts(win["until"])
    return max((b - a).total_seconds() / 86400, 1e-9) if a and b else None


# ---------------------------------------------------------------- Buildkite: builds from job rows
def builds_of(rows):
    """Group job rows into builds: {(pipeline, number): dict(pipeline, number, state, is_pr, pr, branch, created, end, jobs)}."""
    out = {}
    for r in rows:
        k = (r["pipeline"], str(r["build_number"]))
        b = out.get(k)
        if not b:
            b = out[k] = dict(pipeline=r["pipeline"], number=str(r["build_number"]), state=r.get("build_state"),
                              is_pr=truthy(r.get("is_pr")), pr=str(r.get("pr") or ""), branch=r.get("branch") or "",
                              created=r.get("build_created"), end=None, jobs=[])
        b["jobs"].append(r)
        f = r.get("finished_at")
        if f and (b["end"] is None or ts(f) > ts(b["end"])):
            b["end"] = f
    return out


def gpu(r):
    return fnum(r.get("gpu_min")) or 0.0


def ran(r):
    return bool(r.get("started_at"))


def by_weekday(since, until, rows):
    """{weekday: [GPU-h, days of that weekday inside the window]} (UTC, '0' = Monday), rows bucketed by build_created
    like the window itself, so the GPU-h add up to gpu_h_day x days. A short window holds only some weekdays: the page
    compares it with the SAME weekdays of the baseline (2026-11-26 impact redesign). Same rows and same gpu() as gpu_h_day."""
    a, b = ts(since), ts(until)
    out = {}
    if not a or not b:
        return out
    t = a
    while t < b:
        nxt = min(b, dt.datetime.combine(t.date() + dt.timedelta(days=1), dt.time(), tzinfo=t.tzinfo))
        out.setdefault(str(t.weekday()), [0.0, 0.0])[1] += (nxt - t).total_seconds() / 86400
        t = nxt
    for r in rows:
        c = ts(r.get("build_created"))
        if c:
            out.setdefault(str(c.weekday()), [0.0, 0.0])[0] += gpu(r) / 60
    return {k: [round(v[0], 2), round(v[1], 3)] for k, v in sorted(out.items())}


# ---------------------------------------------------------------- the metrics
DETAIL = {"gpu_h_day_pr", "gpu_per_heavy", "exec_heavy_p50", "exec_heavy_p90", "e2e_heavy_p50", "e2e_heavy_p90", "exec_smoke_p50", "exec_smoke_p90",
          "l1_exec_p50", "l1_exec_p90", "stop_rate", "gha_ready_min", "gha_draft_min"}   # FRS review: redundant or not a decision metric -> table only


def metric(key, family, en, vi, unit, better, before, after, nb, na, min_n=10, note=None, after_only=False, before_only=False):
    return dict(key=key, family=family, label=[en, vi], unit=unit, better=better, before=before, after=after,
                n_before=nb, n_after=na, min_n=min_n, note=note, after_only=after_only, before_only=before_only,
                detail=key in DETAIL or key.endswith("_p90"))


def window_numbers(win):
    """Every number of one window. win = dict(since, until, bk, gha, draft, conv, mp_builds, weekly)."""
    D = days(win)
    allr = [r for r in win["bk"] if ran(r)]
    wk_rows = [r for r in allr if r.get("branch") == WEEKLY_BRANCH]
    bk = [r for r in allr if r.get("branch") != WEEKLY_BRANCH]
    pr_rows = [r for r in bk if truthy(r.get("is_pr"))]
    B = builds_of(bk)
    draft = win.get("draft") or (lambda pr, t: None)
    o = dict(days=D)
    wk_builds = {(r["pipeline"], str(r["build_number"])) for r in wk_rows}
    o["weekly_gpu_h"] = sum(gpu(r) for r in wk_rows) / 60
    o["n_weekly_builds"] = len(wk_builds)
    o["unmapped_gpu_wall_min"] = round(sum(fnum(r.get("wall_min")) or 0 for r in allr if r.get("gpus") in ("", None)), 1)

    # GPU resource and waste (scope: k3-unit-tests + k3-multiprocess-test + k3-multiprocess-smoke, the baseline scope + smoke)
    o["gpu_h_day"] = sum(gpu(r) for r in bk) / 60 / D
    o["gpu_h_day_pr"] = sum(gpu(r) for r in pr_rows) / 60 / D
    o["gpu_by_weekday"] = by_weekday(win["since"], win["until"], bk)   # same rows as gpu_h_day, split by weekday
    prs = {str(r["pr"]) for r in pr_rows if r.get("pr")}
    o["n_prs"] = len(prs)
    o["gpu_h_per_pr"] = (sum(gpu(r) for r in pr_rows) / 60 / len(prs)) if prs else None
    pushes = {(str(r["pr"]), r.get("commit")) for r in pr_rows if r.get("pr")}
    o["n_pushes"] = len(pushes)
    o["gpu_h_per_push"] = (sum(gpu(r) for r in pr_rows) / 60 / len(pushes)) if pushes else None
    known = [r for r in pr_rows if draft(str(r["pr"]), r.get("build_created")) is not None]
    o["n_known_draft"] = len(known)
    o["n_pr_jobs"] = len(pr_rows)
    for slug, k in ((UNIT, "unit"), (None, "mp")):
        sel = [r for r in known if (r["pipeline"] == UNIT) == (slug == UNIT)]
        dr = [r for r in sel if draft(str(r["pr"]), r.get("build_created"))]
        o[f"draft_gpu_h_day_{k}"] = sum(gpu(r) for r in dr) / 60 / D
        o[f"n_draft_builds_{k}"] = len({(r["pipeline"], r["build_number"]) for r in dr})
        o[f"n_builds_known_{k}"] = len({(r["pipeline"], r["build_number"]) for r in sel})
    tot_known = sum(gpu(r) for r in known)
    o["draft_share"] = 100 * sum(gpu(r) for r in known if draft(str(r["pr"]), r.get("build_created"))) / tot_known if tot_known else None
    # GPU time of builds made BEFORE a convert-to-draft that kept running WHILE the PR was a draft (what
    # pr_draft_cancel_buildkite.yml should stop). conv = [(pr, draft_at, ready_again_at or None)]; only the overlap counts.
    conv = {}
    for x in win.get("conv") or []:
        conv.setdefault(str(x[0]), []).append((ts(x[1]), ts(x[2]) if len(x) > 2 and x[2] else None))
    late, hit = 0.0, set()
    for r in pr_rows:
        cs = conv.get(str(r["pr"]))
        if not cs:
            continue
        s, f, bc = ts(r.get("started_at")), ts(r.get("finished_at")), ts(r.get("build_created"))
        g = fnum(r.get("gpus"))
        if not (s and f and g and bc):
            continue
        for c, e in cs:
            if bc >= c:
                continue                                         # a build made after the conversion is not a missed cancel
            hi = min(f, e) if e else f
            lo = max(s, c)
            if hi > lo:
                late += (hi - lo).total_seconds() / 60 * g
                hit.add((str(r["pr"]), c))
    o["after_draft_gpu_min_day"] = late / D
    # GPU queue wait on PR builds (what a developer feels when GPU is short): runnable -> started, GPU jobs only
    qw = [fnum(r.get("queue_wait_min")) for r in pr_rows if (fnum(r.get("gpus")) or 0) > 0 and fnum(r.get("queue_wait_min")) is not None]
    o["gpu_queue"] = (r1(pct(qw, .5)), r1(pct(qw, .9)), len(qw))
    o["n_conv"] = sum(len(v) for v in conv.values())
    o["n_conv_hit"] = len(hit)

    # multiprocess: heavy suite (k3-multiprocess-test with workload jobs) and PR smoke
    def pb(slug):
        return [b for b in B.values() if b["pipeline"] == slug and b["is_pr"]]
    heavy, smoke, unit_all = pb(MP), pb(SMOKE), pb(UNIT)
    unit = [b for b in unit_all if draft(b["pr"], b["created"]) is not True]   # ready builds only: After builds no drafts
    o["n_heavy"], o["n_smoke"], o["n_unit"] = len(heavy), len(smoke), len(unit)
    dev = [b for b in B.values() if b["pipeline"] in (UNIT, MP) and not b["is_pr"] and b["branch"] == "dev"]
    o["dev_tested_day"], o["n_dev_tested"] = len(dev) / D, len(dev)
    o["heavy_day"] = len(heavy) / D
    # smoke coverage: ready PR commits with a k3-unit-tests build that also got a k3-multiprocess-smoke build
    ready_c = {(b["pr"], b["jobs"][0].get("commit")) for b in unit}
    smoke_c = {(b["pr"], b["jobs"][0].get("commit")) for b in smoke}
    o["smoke_cov"] = (100 * len(ready_c & smoke_c) / len(ready_c) if ready_c else None, len(ready_c))
    # heavy multiprocess workloads that failed in the weekly full build (final attempt): what a bypassed PR could have hidden
    wk_mp = [r for r in wk_rows if r["pipeline"] == MP and r.get("state") in ("failed", "timed_out") and not truthy(r.get("retried"))]
    o["weekly_mp_fail"] = sorted({r.get("workload") or r.get("label") for r in wk_mp})
    o["n_weekly_mp_jobs"] = sum(1 for r in wk_rows if r["pipeline"] == MP and not truthy(r.get("retried")))
    o["smoke_day"] = len(smoke) / D
    o["gpu_h_per_heavy"] = sum(gpu(r) for b in heavy for r in b["jobs"]) / 60 / len(heavy) if heavy else None
    o["gpu_h_per_smoke"] = sum(gpu(r) for b in smoke for r in b["jobs"]) / 60 / len(smoke) if smoke else None
    o["mp_gpu_h_day_pr"] = sum(gpu(r) for b in heavy + smoke for r in b["jobs"]) / 60 / D

    def e2e(bs):
        return [mins(b["created"], b["end"]) for b in bs if b["state"] in ("passed", "failed") and b["end"]]
    for k, bs in (("heavy", heavy), ("smoke", smoke), ("unit", unit)):
        xs = e2e(bs)
        o[f"e2e_{k}"] = (r1(pct(xs, .5)), r1(pct(xs, .9)), len(xs))
        js = [fnum(r.get("wall_min")) for b in bs for r in b["jobs"] if r.get("state") in ("passed", "failed")]
        o[f"exec_{k}"] = (r1(pct(js, .5)), r1(pct(js, .9)), len([x for x in js if x is not None]))
    # MP signal on a PR: the first MP check that finishes (smoke after the split, the heavy suite before)
    first = {}
    for b in heavy + smoke:
        if b["state"] in ("passed", "failed") and b["end"]:
            k = (b["pr"], b["jobs"][0].get("commit"))
            m = mins(b["created"], b["end"])
            if m is not None and (k not in first or m < first[k]):
                first[k] = m
    o["mp_signal"] = (r1(pct(list(first.values()), .5)), r1(pct(list(first.values()), .9)), len(first))
    # heavy tier decisions on PR builds (After only: annotations of k3-multiprocess-test builds)
    mpb = win.get("mp_builds")
    if mpb is not None:
        byp = [b for b in mpb if b.get("decision") == "bypassed"]
        hv = [b for b in mpb if b.get("decision") == "heavy"]
        o["n_bypass"], o["n_heavy_dec"] = len(byp), len(hv)
        o["n_pathskip"] = sum(1 for b in mpb if b.get("decision") == "path_skip")
        o["n_skip_exp"] = sum(1 for b in mpb if b.get("decision") == "skip_expensive")
        o["bypass_rate"] = 100 * len(byp) / (len(byp) + len(hv)) if byp or hv else None
        reasons = {}
        for b in hv:
            for x in b.get("reasons") or ["other"]:
                reasons[x] = reasons.get(x, 0) + 1
        o["heavy_reasons"] = reasons

    # reliability (PR builds with test jobs)
    for k, bs in (("unit", unit), ("heavy", heavy), ("smoke", smoke)):
        fin = [b for b in bs if b["state"] in ("passed", "failed")]
        o[f"pass_{k}"] = (100 * sum(b["state"] == "passed" for b in fin) / len(fin) if fin else None, len(fin))
    att = [r for r in pr_rows if r.get("state") in ("passed", "failed", "timed_out", "canceled")]
    byid = {r.get("job_id"): r for r in bk}
    retried = [r for r in att if truthy(r.get("retried"))]
    flaky = [r for r in retried if r.get("state") in ("failed", "timed_out") and (byid.get(r.get("retried_in_job_id")) or {}).get("state") == "passed"]
    o["retry_rate"] = (100 * len(retried) / len(att) if att else None, len(att))
    o["flake_rate"] = (100 * len(flaky) / len(att) if att else None, len(att))
    o["retry_gpu_h_day"] = sum(gpu(r) for r in retried) / 60 / D
    again = [byid.get(r.get("retried_in_job_id")) for r in retried if r.get("state") in ("failed", "timed_out")]
    again = [x for x in again if x and x.get("state") in ("failed", "timed_out")]
    o["repeat_rate"] = (100 * len(again) / len(att) if att else None, len(att))
    o["retry_waste_gpu_h_day"] = sum(gpu(x) for x in again) / 60 / D

    # GitHub Actions: L1 (Check code quality) -> L2 (Test + CPU device) on PR commits
    g = [r for r in win["gha"] if (r.get("event") or "").startswith("pull_request") and r.get("started")]
    com = {}
    for r in g:
        com.setdefault((str(r["pr"]), r["commit"], str(r.get("run") or "")), []).append(r)
    dr_min = rd_min = 0.0
    n_dr = n_rd = 0
    l1x, l2s, alld, cpu_fail, l1q, gap = [], [], [], 0.0, [], []
    stop_n = stop_hit = 0
    for (pr, c, _run), rs_all in com.items():
        rs = [r for r in rs_all if str(r.get("attempt") or "1") == "1"]     # latency: first attempt only (a re-run hours later is not latency)
        t0 = min((r["suite_created"] for r in rs_all if r.get("suite_created")), default=None)
        jm = sum(fnum(r.get("exec_min")) or 0 for r in rs_all if r.get("workflow") in ("Code Quality",) + L2_WF)   # cost: every attempt
        d = draft(pr, t0)
        if d is True:
            dr_min += jm
            n_dr += 1
        elif d is False:
            rd_min += jm
            n_rd += 1
            q = [fnum(r.get("exec_min")) for r in rs if r.get("job") == "Check code quality" and r.get("conclusion") == "SUCCESS"]
            if q:
                l1x.append(q[0])
            cq = [r for r in rs if r.get("job") == "Check code quality" and r.get("conclusion") == "SUCCESS" and r.get("started")]
            if cq and t0:
                l1q.append((ts(cq[0]["started"]) - ts(t0)).total_seconds() / 60)
            l2 = [ts(r["started"]) for r in rs if r.get("workflow") in L2_WF and r.get("job") != "Detect changes" and r.get("started")]
            if l2 and t0:
                l2s.append((min(l2) - ts(t0)).total_seconds() / 60)
                if cq and cq[0].get("completed"):
                    gap.append((min(l2) - ts(cq[0]["completed"])).total_seconds() / 60)
            ends = [ts(r["completed"]) for r in rs if r.get("workflow") in ("Code Quality",) + L2_WF and r.get("completed")]
            if ends and t0 and all(r.get("conclusion") == "SUCCESS" or r.get("conclusion") == "SKIPPED" for r in rs if r.get("workflow") in ("Code Quality",) + L2_WF):
                alld.append((max(ends) - ts(t0)).total_seconds() / 60)
        if not rs:
            continue
        fails = [ts(r["completed"]) for r in rs if r.get("workflow") == "Test" and r.get("conclusion") == "FAILURE" and r.get("completed")]
        if fails:
            tf = min(fails)
            cpu = [r for r in rs if r.get("workflow") == "CPU Device Tests" and r.get("job") != "Detect changes"]
            cpu_fail += sum(fnum(r.get("exec_min")) or 0 for r in cpu)
            # CPU device jobs still running when the unit tests failed: were they stopped within 10 min?
            live = [r for r in cpu if ts(r.get("started")) and ts(r.get("completed")) and ts(r["started"]) < tf < ts(r["completed"])]
            if live:
                stop_n += 1
                stop_hit += all(r.get("conclusion") == "CANCELLED" and (ts(r["completed"]) - tf).total_seconds() <= 600 for r in live)
            o_tf = o.setdefault("_n_test_fail", 0)
            o["_n_test_fail"] = o_tf + 1
    o["gha_draft_min_day"], o["gha_ready_min_day"], o["n_draft_commits"], o["n_ready_commits"] = dr_min / D, rd_min / D, n_dr, n_rd
    o["gha_ready_per_push"] = rd_min / n_rd if n_rd else None
    o["gha_draft_per_push"] = dr_min / n_dr if n_dr else None
    o["l1_exec"] = (r1(pct(l1x, .5)), r1(pct(l1x, .9)), len(l1x))
    o["l2_start"] = (r1(pct(l2s, .5)), r1(pct(l2s, .9)), len(l2s))
    o["l12_done"] = (r1(pct(alld, .5)), r1(pct(alld, .9)), len(alld))
    o["l1_queue"] = (r1(pct(l1q, .5)), r1(pct(l1q, .9)), len(l1q))
    o["l1_l2_gap"] = (r1(pct(gap, .5)), r1(pct(gap, .9)), len(gap))
    o["cpu_after_test_fail_day"] = cpu_fail / D
    o["n_test_fail_commits"] = o.pop("_n_test_fail", 0)
    o["stop_rate"] = (100 * stop_hit / stop_n if stop_n else None, stop_n)
    return o


def compare(B, A, weekly=None, after_extra=None):
    """Metric rows (before vs after) from two window_numbers() results."""
    X = after_extra or {}
    rows = []
    R = lambda x, n=1: None if x is None else round(x, n)  # noqa: E731
    # ---- GPU resource & waste
    rows += [
        metric("gpu_h_day", "gpu", "GPU-hours per day (unit + multiprocess, without the weekly full build)", "GPU-giờ mỗi ngày (unit + multiprocess, không tính weekly full build)", "GPU-h", "down",
               R(B["gpu_h_day"]), R(A["gpu_h_day"]), B["n_pr_jobs"], A["n_pr_jobs"], 50),
        metric("gpu_h_day_pr", "gpu", "PR GPU-hours per day", "GPU-giờ của PR mỗi ngày", "GPU-h", "down",
               R(B["gpu_h_day_pr"]), R(A["gpu_h_day_pr"]), B["n_pr_jobs"], A["n_pr_jobs"], 50),
        metric("gpu_h_per_push", "gpu", "GPU-hours per PR push", "GPU-giờ mỗi lần push PR", "GPU-h", "down",
               R(B["gpu_h_per_push"], 2), R(A["gpu_h_per_push"], 2), B["n_pushes"], A["n_pushes"], 100,
               note=["per PR commit with a GPU build: a per-PR number would grow with the window length", "theo commit PR có build GPU: số theo PR sẽ tăng theo độ dài cửa sổ"]),
        metric("draft_gpu_unit", "gpu", "Draft-PR GPU-hours per day · k3-unit-tests", "GPU-giờ trên PR draft mỗi ngày · k3-unit-tests", "GPU-h", "down",
               R(B["draft_gpu_h_day_unit"]), R(A["draft_gpu_h_day_unit"]), B["n_builds_known_unit"], A["n_builds_known_unit"], 20,
               note=["PR draft state at build creation, from the GitHub timeline (ready-for-review / convert-to-draft events)", "Trạng thái draft của PR lúc tạo build, từ timeline GitHub (sự kiện ready-for-review / convert-to-draft)"]),
        metric("draft_gpu_mp", "gpu", "Draft-PR GPU-hours per day · k3-multiprocess-*", "GPU-giờ trên PR draft mỗi ngày · k3-multiprocess-*", "GPU-h", "down",
               R(B["draft_gpu_h_day_mp"]), R(A["draft_gpu_h_day_mp"]), B["n_builds_known_mp"], A["n_builds_known_mp"], 20),
        metric("draft_share", "gpu", "Share of PR GPU time on draft commits", "Tỉ lệ GPU của PR chạy trên commit draft", "%", "down",
               R(B["draft_share"]), R(A["draft_share"]), B["n_known_draft"], A["n_known_draft"], 50),
        metric("after_draft", "gpu", "GPU-min per day that ran after the PR went back to draft", "GPU-phút mỗi ngày chạy sau khi PR về draft", "GPU-min", "down",
               R(B["after_draft_gpu_min_day"]), R(A["after_draft_gpu_min_day"]), B["n_conv"], A["n_conv"], 5,
               note=["builds made before a convert-to-draft that kept running while the PR was a draft; pr_draft_cancel_buildkite.yml should stop them. N = convert-to-draft events", "build tạo trước khi PR về draft nhưng vẫn chạy trong lúc PR là draft; pr_draft_cancel_buildkite.yml lẽ ra phải dừng chúng. N = số lần về draft"]),
    ]
    for i, p in ((0, "p50"), (1, "p90")):
        rows.append(metric(f"gpu_queue_{p}", "gpu", f"PR GPU job wait for a GPU · {p}", f"Job GPU của PR chờ GPU · {p}", "min", "down",
                           B["gpu_queue"][i], A["gpu_queue"][i], B["gpu_queue"][2], A["gpu_queue"][2], 100 if i == 0 else 300,
                           note=["runnable -> started on Buildkite, GPU jobs of PR builds", "runnable -> started trên Buildkite, job GPU của build PR"] if i == 0 else None))
    rows += [
        metric("retry_waste_gpu", "gpu", "GPU-hours per day on retries that failed again", "GPU-giờ mỗi ngày cho các lần retry vẫn lỗi", "GPU-h", "down", R(B["retry_waste_gpu_h_day"], 2), R(A["retry_waste_gpu_h_day"], 2), B["repeat_rate"][1], A["repeat_rate"][1], 200,
               note=["an automatic retry of a broken test only burns GPU: fix or quarantine the workload", "retry tự động của test hỏng chỉ đốt GPU: sửa hoặc cách ly workload"]),
        metric("repeat_rate", "gpu", "Retries that failed again (share of PR GPU job attempts)", "Retry vẫn lỗi (tỉ lệ trên lượt job GPU của PR)", "%", "down", R(B["repeat_rate"][0], 2), R(A["repeat_rate"][0], 2), B["repeat_rate"][1], A["repeat_rate"][1], 200),
    ]
    rows.append(metric("weekly_gpu", "gpu", "Weekly full build GPU-hours in the window (Buildkite)", "GPU-giờ của weekly full build trong cửa sổ (Buildkite)", "GPU-h", "info",
                       None, R(A["weekly_gpu_h"]) if A.get("n_weekly_builds") else None, None, A.get("n_weekly_builds"), 1, after_only=True,
                       note=["Buildkite builds on ci-weekly-full (N = builds); kept out of the PR and daily totals", "build Buildkite trên ci-weekly-full (N = số build); không cộng vào tổng PR và tổng mỗi ngày"]))
    if X.get("draft_cancel") is not None:
        dc = X["draft_cancel"]
        rows.append(metric("draft_cancel_runs", "gpu", "Buildkite builds cancelled within 3 min of a convert-to-draft", "Build Buildkite bị huỷ trong 3 phút sau khi PR về draft", "builds", "info",
                           None, dc.get("cancelled"), None, dc.get("runs"), 1, after_only=True,
                           note=[f"{dc.get('runs', 0)} runs of pr_draft_cancel_buildkite.yml; GPU-min spent before the cancel: {dc.get('spent_gpu_min', 0)}", f"{dc.get('runs', 0)} lần chạy pr_draft_cancel_buildkite.yml; GPU-phút đã chạy trước khi huỷ: {dc.get('spent_gpu_min', 0)}"]))
    # ---- multiprocess split
    rows += [
        metric("heavy_day", "mp", "k3-multiprocess-test (heavy) PR builds per day", "Build PR k3-multiprocess-test (heavy) mỗi ngày", "builds", "down",
               R(B["heavy_day"]), R(A["heavy_day"]), B["n_heavy"], A["n_heavy"], 10),
        metric("smoke_day", "mp", "k3-multiprocess-smoke PR builds per day", "Build PR k3-multiprocess-smoke mỗi ngày", "builds", "info",
               None, R(A["smoke_day"]), None, A["n_smoke"], 10, after_only=True),
        metric("smoke_cov", "mp", "Ready PR pushes that got the smoke tier", "Lần push PR ready có chạy tầng smoke", "%", "up",
               None, R(A["smoke_cov"][0]), None, A["smoke_cov"][1], 50, after_only=True,
               note=["ready PR commits with a k3-unit-tests build that also have a k3-multiprocess-smoke build", "commit PR ready có build k3-unit-tests và cũng có build k3-multiprocess-smoke"]),
        metric("mp_gpu_pr", "mp", "Multiprocess PR GPU-hours per day (heavy + smoke)", "GPU-giờ multiprocess của PR mỗi ngày (heavy + smoke)", "GPU-h", "down",
               R(B["mp_gpu_h_day_pr"]), R(A["mp_gpu_h_day_pr"]), B["n_heavy"] + B["n_smoke"], A["n_heavy"] + A["n_smoke"], 10),
        metric("gpu_per_heavy", "mp", "GPU-hours per heavy PR build", "GPU-giờ mỗi build PR heavy", "GPU-h", "info",
               R(B["gpu_h_per_heavy"], 2), R(A["gpu_h_per_heavy"], 2), B["n_heavy"], A["n_heavy"], 10),
        metric("gpu_per_smoke", "mp", "GPU-hours per smoke PR build", "GPU-giờ mỗi build PR smoke", "GPU-h", "info",
               None, R(A["gpu_h_per_smoke"], 2), None, A["n_smoke"], 10, after_only=True),
    ]
    if "bypass_rate" in A:
        rows.append(metric("bypass_rate", "mp", "Heavy tier bypassed on ordinary PR builds", "Tỉ lệ bỏ qua tầng heavy trên build PR thường", "%", "up",
                           None, R(A["bypass_rate"]), None, A["n_bypass"] + A["n_heavy_dec"], 10, after_only=True,
                           note=[f"bypassed {A['n_bypass']} · heavy ran {A['n_heavy_dec']} · path-filter skip {A['n_pathskip']} (Buildkite annotations)", f"bỏ qua {A['n_bypass']} · heavy đã chạy {A['n_heavy_dec']} · path-filter skip {A['n_pathskip']} (annotation Buildkite)"]))
    for k, en, vi in (("mp_signal", "PR multiprocess signal (first MP check done)", "Tín hiệu multiprocess của PR (check MP đầu tiên xong)"),
                      ("e2e_heavy", "Heavy build end-to-end", "Build heavy từ đầu đến cuối"),
                      ("e2e_smoke", "Smoke build end-to-end", "Build smoke từ đầu đến cuối"),
                      ("exec_heavy", "Heavy job execution", "Thời gian chạy job heavy"),
                      ("exec_smoke", "Smoke job execution", "Thời gian chạy job smoke"),
                      ("e2e_unit", "k3-unit-tests build end-to-end", "Build k3-unit-tests từ đầu đến cuối")):
        b, a = B[k], A[k]
        only = k.endswith("smoke")
        for i, p in ((0, "p50"), (1, "p90")):
            rows.append(metric(f"{k}_{p}", "mp" if k != "e2e_unit" else "gpu", f"{en} · {p}", f"{vi} · {p}", "min", "down",
                               None if only else b[i], a[i], None if only else b[2], a[2], 100 if i == 0 else 300, after_only=only,
                               note=(["before: the heavy suite; after: the smoke tier (fewer workloads): faster signal, not the same coverage", "trước: bộ heavy; sau: tầng smoke (ít workload hơn): tín hiệu nhanh hơn, không cùng độ phủ"]
                                     if k == "mp_signal" and i == 0 else ["ready builds only in both windows", "chỉ build ready ở cả hai cửa sổ"] if k == "e2e_unit" and i == 0 else None)))
    # ---- GitHub Actions L1 / L2
    rows += [
        metric("gha_draft_min", "gha", "Runner-min per day on draft commits (Code Quality + Test + CPU device)", "Phút runner mỗi ngày trên commit draft (Code Quality + Test + CPU device)", "job-min", "down",
               R(B["gha_draft_min_day"]), R(A["gha_draft_min_day"]), B["n_draft_commits"], A["n_draft_commits"], 20),
        metric("gha_ready_min", "gha", "Runner-min per day on ready commits", "Phút runner mỗi ngày trên commit ready", "job-min", "info",
               R(B["gha_ready_min_day"]), R(A["gha_ready_min_day"]), B["n_ready_commits"], A["n_ready_commits"], 20),
        metric("gha_ready_per_push", "gha", "Runner-min per ready push (Code Quality + Test + CPU device)", "Phút runner mỗi lần push ready (Code Quality + Test + CPU device)", "job-min", "down",
               R(B["gha_ready_per_push"]), R(A["gha_ready_per_push"]), B["n_ready_commits"], A["n_ready_commits"], 100,
               note=["every attempt counts (re-runs cost runners too)", "tính mọi attempt (chạy lại cũng tốn runner)"]),
        metric("gha_draft_per_push", "gha", "Runner-min per draft push (Code Quality + Test + CPU device)", "Phút runner mỗi lần push draft (Code Quality + Test + CPU device)", "job-min", "down",
               R(B["gha_draft_per_push"]), R(A["gha_draft_per_push"]), B["n_draft_commits"], A["n_draft_commits"], 50,
               note=["#6730: drafts run Python 3.12 only, so a draft push should cost less than before", "#6730: draft chỉ chạy Python 3.12, nên mỗi lần push draft phải tốn ít hơn trước"]),
    ]
    for k, en, vi in (("l1_queue", "Push → lint gate starts (GitHub runner queue)", "Push → lint gate bắt đầu (chờ runner GitHub)"),
                      ("l1_exec", "Lint gate run time", "Thời gian chạy lint gate"),
                      ("l1_l2_gap", "Lint gate done → first test job starts", "Lint gate xong → job test đầu tiên bắt đầu"),
                      ("l2_start", "Push → first test job starts (Test / CPU device)", "Push → job test đầu tiên bắt đầu (Test / CPU device)"),
                      ("l12_done", "Push → lint gate + tests all green", "Push → lint gate + test xanh hết")):
        for i, p in ((0, "p50"), (1, "p90")):
            gap_ = k == "l1_l2_gap"
            rows.append(metric(f"{k}_{p}", "gha", f"{en} · {p}", f"{vi} · {p}", "min", "down" if k not in ("l2_start", "l1_l2_gap") else "info",
                               None if gap_ else B[k][i], A[k][i], None if gap_ else B[k][2], A[k][2], 100 if i == 0 else 300, after_only=gap_,
                               note=(["L2 now waits for L1 by design (#6730): most of the extra wait is the GitHub runner queue before L1 starts", "L2 giờ chờ L1 theo thiết kế (#6730): phần lớn thời gian chờ thêm là hàng đợi runner GitHub trước khi L1 bắt đầu"] if k == "l2_start" and i == 0 else
                                     ["before #6730 L2 did not wait for L1", "trước #6730 L2 không chờ L1"] if gap_ and i == 0 else None)))
    rows += [
        metric("stop_rate", "gha", "Unit tests failed: CPU device jobs still running were stopped within 10 min", "Unit test lỗi: job CPU device đang chạy bị dừng trong 10 phút", "%", "up",
               R(B["stop_rate"][0]), R(A["stop_rate"][0]), B["stop_rate"][1], A["stop_rate"][1], 5,
               note=["N = PR commits whose Test job failed while CPU device jobs ran (first attempt). After: job 'Stop CPU device (Test failed)'; fork PRs get a read-only token and skip it", "N = commit PR có job Test lỗi khi job CPU device đang chạy (lần chạy đầu). Sau: job 'Stop CPU device (Test failed)'; PR từ fork có token chỉ đọc nên bỏ qua job này"]),
        metric("cpu_after_fail", "gha", "CPU-device runner-min per day on commits whose unit tests failed", "Phút runner CPU device mỗi ngày trên commit có unit test lỗi", "job-min", "down",
               R(B["cpu_after_test_fail_day"]), R(A["cpu_after_test_fail_day"]), B["n_test_fail_commits"], A["n_test_fail_commits"], 5),
    ]
    # ---- reliability
    for k, en, vi in (("pass_unit", "k3-unit-tests PR build pass rate", "Tỉ lệ pass build PR k3-unit-tests"),
                      ("pass_heavy", "Heavy multiprocess PR build pass rate", "Tỉ lệ pass build PR multiprocess heavy"),
                      ("pass_smoke", "Smoke PR build pass rate", "Tỉ lệ pass build PR smoke")):
        only = k == "pass_smoke"
        rows.append(metric(k, "rel", en, vi, "%", "info" if k == "pass_heavy" else "up", None if only else R(B[k][0]), R(A[k][0]), None if only else B[k][1], A[k][1], 200, after_only=only,
                           note=["after the split only PRs labelled full / force-ci or touching shared paths run heavy: a different, riskier population", "sau khi tách chỉ PR có nhãn full / force-ci hoặc sửa đường dẫn dùng chung mới chạy heavy: tập PR khác, rủi ro hơn"] if k == "pass_heavy" else
                                ["ready builds only in both windows", "chỉ build ready ở cả hai cửa sổ"] if k == "pass_unit" else None))
    rows += [
        metric("retry_rate", "rel", "PR GPU job attempts retried", "Lượt job GPU của PR bị retry", "%", "down", R(B["retry_rate"][0]), R(A["retry_rate"][0]), B["retry_rate"][1], A["retry_rate"][1], 200),
        metric("flake_rate", "rel", "Flaky: failed, then passed on retry", "Chập chờn: lỗi rồi pass khi retry", "%", "down", R(B["flake_rate"][0], 2), R(A["flake_rate"][0], 2), B["flake_rate"][1], A["flake_rate"][1], 200),
        metric("dev_tested", "rel", "Post-merge dev builds that ran tests, per day (unit + multiprocess)", "Build dev sau merge có chạy test, mỗi ngày (unit + multiprocess)", "builds", "up",
               R(B["dev_tested_day"], 2), R(A["dev_tested_day"], 2), B["n_dev_tested"], A["n_dev_tested"], 0,
               note=["since #6730 k3-unit-tests builds PR commits only, and scheduled dev multiprocess builds skip their tests: the weekly full build is the only post-merge GPU check left", "từ #6730 k3-unit-tests chỉ build commit PR, build dev theo lịch của multiprocess bỏ qua test: weekly full build là kiểm tra GPU sau merge duy nhất còn lại"]),
    ]
    fails = A.get("weekly_mp_fail") or []
    rows.append(metric("weekly_mp_fail", "rel", "Heavy multiprocess workloads failing in the weekly full build", "Workload multiprocess heavy lỗi trong weekly full build", "workloads", "down",
                       None, len(fails) if A.get("n_weekly_mp_jobs") else None, None, A.get("n_weekly_mp_jobs"), 1, after_only=True,
                       note=["possible escapes: heavy suites are bypassed on ordinary PRs (#6731), so the weekly build is where they fail first" + (": " + ", ".join(fails) if fails else ""),
                             "có thể là lỗi lọt: tầng heavy bị bỏ qua trên PR thường (#6731), nên weekly build là nơi chúng lỗi đầu tiên" + (": " + ", ".join(fails) if fails else "")]))
    if weekly is not None:
        rows.append(metric("weekly_pass", "rel", "Weekly full build runs passed", "Run weekly full build đạt", "%", "up",
                           None, R(weekly.get("pass_pct")), None, weekly.get("finished"), 4, after_only=True,
                           note=[f"{weekly.get('passed', 0)} passed · {weekly.get('failed', 0)} failed · {weekly.get('other', 0)} running / cancelled; latest finished: {weekly.get('latest') or '–'}", f"{weekly.get('passed', 0)} đạt · {weekly.get('failed', 0)} lỗi · {weekly.get('other', 0)} đang chạy / đã huỷ; gần nhất đã xong: {weekly.get('latest') or '–'}"]))
    return rows


def status(row, after_days):
    """'ok' | 'collecting' | 'insufficient' | 'new' (After only) | 'no_data'."""
    if row["after"] is None or (not row["n_after"] and row["min_n"] > 0):
        return "no_data"
    if (row["n_after"] or 0) < row["min_n"]:
        return "insufficient"
    if after_days is not None and after_days < MIN_DAYS:
        return "collecting"
    return "new" if row["after_only"] else "ok"


def delta(row):
    """(absolute, percent) or (None, None) when it would mislead (no before, insufficient sample)."""
    b, a = row["before"], row["after"]
    if b is None or a is None or row.get("status") in ("insufficient", "collecting", "no_data"):
        return None, None   # FRS review: a window under MIN_DAYS gives no change and no verdict (no extrapolation)
    d = round(a - b, 2)
    return d, (round(100 * d / b, 1) if b else None)


def finish(rows, after_days):
    for r in rows:
        r["status"] = status(r, after_days)
        r["delta"], r["delta_pct"] = delta(r)
    return rows
