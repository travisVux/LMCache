"""Data for the 3 extra trace directions in #obs (tabs 9-11), next to the release tracer.

  flaky   -> #obs/flaky    jobs that fail first and pass on retry, same-commit flips, GHA re-runs
  gpuload -> #obs/gpuload  where MP GPU-hours go, what is waste, measured levers (and merge speed)
  bug     -> #obs/bug      one GitHub issue / PR (BUG_TARGET, default #6530) traced to its CI errors

Inputs are local caches only (no network), except `bug`, which asks `gh api` once (tolerant to failure):
  ../P1/jobs_all_30d.csv, ../P1/raw/builds_30d.json, ../P1/cost_by_workload.csv  (k3-multiprocess-test, 30 d)
  ff_cache_gha_test.json (GHA "Test" runs), fastfail_savings.json (measured fast-fail cancel)
Agent results per direction: ../trace_agent/directions/<dir>.json (written by trace_agent_dirs.py).

Writes ../trace_agent/directions.json and directions.js (live feed: the open page polls it).
Usage: python -I -X utf8 trace_dirs_model.py      # rebuild the payload (build_trace_dirs.py calls build())
"""
import csv
import json
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "trace_agent"))
P1 = os.path.abspath(os.path.join(HERE, "..", "P1"))
AGENT_DIR = os.path.join(OUT, "directions")
JSON_OUT = os.path.join(OUT, "directions.json")
LIVE_JS = os.path.join(OUT, "directions.js")
REPO = "LMCache/LMCache"
BK = "https://buildkite.com/lmcache/k3-multiprocess-test/builds/"

# The bug / error the "bug" tab traces. Change the number here (or in the page: it is remembered per browser).
BUG_TARGET = dict(repo=REPO, number=6530, note="upcoming GitHub issue / PR (did not exist on 2026-11-09)")

# Exit codes of the first failed attempt: 1/2 = the test itself failed, the rest = agent / infra.
EXIT_KIND = {"1": "test", "2": "test", "128": "infra", "255": "infra", "-1": "infra", "100": "infra"}


def _t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _week(dt):
    y, w, _ = dt.isocalendar()
    return f"W{w:02d}"


def _load():
    rows = list(csv.DictReader(open(os.path.join(P1, "jobs_all_30d.csv"), encoding="utf-8")))
    builds = json.load(open(os.path.join(P1, "raw", "builds_30d.json"), encoding="utf-8"))
    cost = list(csv.DictReader(open(os.path.join(P1, "cost_by_workload.csv"), encoding="utf-8")))
    return rows, builds, cost


def _window(builds):
    ts = sorted(b["created_at"] for b in builds)
    return dict(start=ts[0][:10], end=ts[-1][:10], pipeline="k3-multiprocess-test", builds=len(builds))


def _weeks(builds):
    """Full ISO weeks inside the window, plus the partial edge weeks flagged."""
    c = Counter(_week(_t(b["created_at"])) for b in builds)
    first, last = _week(_t(min(b["created_at"] for b in builds))), _week(_t(max(b["created_at"] for b in builds)))
    return [dict(w=w, partial=w in (first, last), builds=c[w]) for w in sorted(c)]


def flaky(rows, builds, cost):
    byid = {r["job_id"]: r for r in rows}
    bstate = {str(b["number"]): b for b in builds}

    def final(r):
        n = 0
        while r["retried"] == "True" and r["retried_in_job_id"] in byid and n < 10:
            r, n = byid[r["retried_in_job_id"]], n + 1
        return r, n

    wl = defaultdict(lambda: dict(first_fail=0, flaky=0, still_fail=0, canceled=0, retry_gpu_min=0.0,
                                  exits=Counter(), examples=[], weeks=Counter()))
    kind = Counter()
    weeks = Counter()
    for r in rows:
        if r["retry_source"] or r["state"] != "failed":
            continue
        w = wl[r["workload"] or r["label"]]
        w["first_fail"] += 1
        if r["retried"] != "True":
            continue
        f, n = final(r)
        # GPU spent on the retries themselves (all attempts after the first)
        x, k = r, 0
        while x["retried"] == "True" and x["retried_in_job_id"] in byid and k < 10:
            x, k = byid[x["retried_in_job_id"]], k + 1
            w["retry_gpu_min"] += _f(x["gpu_min"])
        if f["state"] == "passed":
            w["flaky"] += 1
            ex = r["exit_status"] or "?"
            w["exits"][ex] += 1
            kind[EXIT_KIND.get(ex, "infra")] += 1
            wk = _week(_t(r["build_created"]))
            w["weeks"][wk] += 1
            weeks[wk] += 1
            if len(w["examples"]) < 4 and all(e["build"] != r["build_number"] for e in w["examples"]):
                w["examples"].append(dict(build=r["build_number"], pr=r["pr"], exit=ex, attempts=n + 1,
                                          url=BK + r["build_number"], at=r["build_created"][:10]))
        elif f["state"] == "failed":
            w["still_fail"] += 1
        else:
            w["canceled"] += 1
    runs = {c["workload"]: dict(runs=int(_f(c["runs_30d"])), gpus=c["gpus"]) for c in cost}
    table = []
    for name, w in wl.items():
        if not w["flaky"] and not w["still_fail"]:
            continue
        rn = runs.get(name, {}).get("runs") or 0
        table.append(dict(workload=name, gpus=runs.get(name, {}).get("gpus", ""), runs=rn,
                          first_fail=w["first_fail"], flaky=w["flaky"], still_fail=w["still_fail"], canceled=w["canceled"],
                          flaky_rate=round(w["flaky"] / rn, 4) if rn else None,
                          retry_gpu_h=round(w["retry_gpu_min"] / 60, 1), exits=dict(w["exits"].most_common()),
                          examples=w["examples"], weeks=dict(w["weeks"])))
    table.sort(key=lambda x: (-x["flaky"], -x["retry_gpu_h"]))
    # same commit: one build failed, another build passed (no code change in between)
    by_commit = defaultdict(list)
    for b in builds:
        by_commit[b["commit"]].append(b)
    flips = []
    for sha, bs in by_commit.items():
        st = {b["state"] for b in bs}
        if "failed" in st and "passed" in st:
            bs = sorted(bs, key=lambda b: b["created_at"])
            flips.append(dict(sha=sha[:10], pr=(bs[0].get("pull_request") or {}).get("id"), branch=bs[0]["branch"],
                              builds=[dict(n=b["number"], state=b["state"], url=BK + str(b["number"])) for b in bs]))
    # GitHub Actions "Test" workflow: a run with run_attempt > 1 was re-run; success on attempt >= 2 = flaky-then-passed
    gha = json.load(open(os.path.join(HERE, "ff_cache_gha_test.json"), encoding="utf-8"))
    att = Counter((min(int(g.get("run_attempt") or 1), 3), g.get("conclusion")) for g in gha)
    gha_out = dict(runs=len(gha), rerun=sum(v for (a, _), v in att.items() if a > 1),
                   rerun_success=sum(v for (a, c), v in att.items() if a > 1 and c == "success"),
                   first_failure=att.get((1, "failure"), 0), start=min(g["created_at"] for g in gha)[:10],
                   end=max(g["created_at"] for g in gha)[:10])
    tot = dict(first_fail=sum(x["first_fail"] for x in wl.values()), flaky=sum(x["flaky"] for x in wl.values()),
               still_fail=sum(x["still_fail"] for x in wl.values()),
               retry_gpu_h=round(sum(x["retry_gpu_min"] for x in wl.values()) / 60, 1),
               test_kind=kind.get("test", 0), infra_kind=kind.get("infra", 0), flips=len(flips))
    return dict(totals=tot, workloads=table, flips=flips, gha=gha_out, weeks=dict(weeks))


def gpuload(rows, builds, cost, fl):
    byb = defaultdict(list)
    for r in rows:
        byb[r["build_number"]].append(r)
    by_state = Counter()
    wk = defaultdict(Counter)
    pr_gpu = []
    for b in builds:
        g = sum(_f(j["gpu_min"]) for j in byb[str(b["number"])])
        by_state[b["state"]] += g
        wk[_week(_t(b["created_at"]))][b["state"]] += g
        if b.get("pull_request") and b["state"] == "passed":
            pr_gpu.append(g)
    total = sum(by_state.values())
    creasons = Counter(b.get("cancel_reason") or "?" for b in builds if b["state"] == "canceled")
    # superseded: GPU a PR build still burned after a newer build of the same PR was created
    prs = defaultdict(list)
    for b in builds:
        if b.get("pull_request"):
            prs[b["pull_request"]["id"]].append(b)
    sup = 0.0
    for bs in prs.values():
        bs.sort(key=lambda b: b["created_at"])
        for i, b in enumerate(bs[:-1]):
            t = _t(bs[i + 1]["created_at"])
            for j in byb[str(b["number"])]:
                if j["started_at"] and j["finished_at"] and j["gpus"].isdigit():
                    s, f = max(_t(j["started_at"]), t), _t(j["finished_at"])
                    if f > s:
                        sup += int(j["gpus"]) * (f - s).total_seconds() / 60
    wl = []
    for c in cost:
        g = _f(c["gpu_min_total_30d"])
        if not g:
            continue
        wl.append(dict(workload=c["workload"], gpus=c["gpus"], gpu_h=round(g / 60, 1), share=round(g / total, 4) if total else 0,
                       per_pr_build_min=_f(c["gpu_min_per_pr_build"]), p50_wall_min=_f(c["p50_wall_min"]),
                       first_try_fail_pct=_f(c["first_try_fail_pct"]), retry_gpu_h=round(_f(c["retry_gpu_min_30d"]) / 60, 1),
                       queue_p90_min=_f(c["queue_wait_p90_min"]), canceled_runs=int(_f(c["canceled_runs"]))))
    wl.sort(key=lambda x: -x["gpu_h"])
    fr = {x["workload"]: x["retry_gpu_h"] for x in fl["workloads"]}  # one source: the retry chains of the flaky tab
    for x in wl:
        x["retry_gpu_h"] = fr.get(x["workload"], 0.0)
    ff = json.load(open(os.path.join(HERE, "fastfail_savings.json"), encoding="utf-8"))
    summ = json.load(open(os.path.join(P1, "build_level_summary.json"), encoding="utf-8"))
    ffa = ff["triggers"]["all three"]["real"]
    ffr = ff["triggers"]["required (quality+k3_unit)"]["real"]
    retry_h = fl["totals"]["retry_gpu_h"]
    top_flaky = sorted(wl, key=lambda x: -x["retry_gpu_h"])[:5]
    pr_gpu.sort()
    levers = [
        dict(id="ff", gpu_h=ffa["gpu_hours"], basis="estimated", ticket="LM-1062",
             en="Fast-fail: cancel the MP build when GHA Test, Lint or k3-unit is red on the same commit",
             vi="Fast-fail: hủy build MP khi GHA Test, Lint hoặc k3-unit đỏ trên cùng commit",
             note_en=f"{ffa['mp_builds']} MP builds; only the 2 required checks: {ffr['gpu_hours']} GPU-h",
             note_vi=f"{ffa['mp_builds']} build MP; chỉ 2 check bắt buộc: {ffr['gpu_hours']} GPU-h",
             effect_en="Frees 2-GPU & 4-GPU pool slots earlier on red commits → shorter queue wait (18.5m p50 / 56.5m p90) [hypothesis]",
             effect_vi="Giải phóng sớm slot 2-GPU & 4-GPU ở commit đỏ → giảm thời gian chờ hàng đợi (18.5p p50 / 56.5p p90) [giả thuyết]"),
        dict(id="flaky", gpu_h=round(sum(x["retry_gpu_h"] for x in top_flaky), 1), basis="measured", ticket="LM-762", goto="#obs/flaky",
             en="Fix the top flaky workloads (" + ", ".join(x["workload"] for x in top_flaky[:3]) + ") so their automatic retries stop",
             vi="Sửa các workload flaky nhất (" + ", ".join(x["workload"] for x in top_flaky[:3]) + ") để hết retry tự động",
             note_en="GPU spent on the retry attempts of the top 5 (out of 191.7 GPU-h all retries)",
             note_vi="GPU đã tốn cho các lần retry của top 5 (trên tổng 191.7 GPU-giờ retry)",
             effect_en="Removes 1–2 retry cycles (~15–30 min wall time) on affected PRs + frees 2-GPU/4-GPU queue [hypothesis]",
             effect_vi="Bỏ được 1–2 vòng retry (~15–30 phút thời gian thực) trên PR bị vướng + giảm nghẽn hàng đợi 2-GPU/4-GPU [giả thuyết]"),
        dict(id="sup", gpu_h=round(sup / 60, 1), basis="measured", ticket="LM-1115",
             en="Cancel a PR build when a newer commit of the same PR starts",
             vi="Hủy build PR khi commit mới hơn của cùng PR bắt đầu chạy",
             note_en="Already done for MP: little left to gain", note_vi="MP đã làm việc này: không còn nhiều để tiết kiệm",
             effect_en="Already active via build_skipping (229/235 canceled builds)",
             effect_vi="Đã bật sẵn qua build_skipping (229/235 build hủy)"),
        dict(id="cancel", gpu_h=round(by_state.get("canceled", 0) / 60, 1), basis="spent", ticket="LM-1115",
             en="GPU burned by builds that ended canceled, so they gave no result",
             vi="GPU đã đốt bởi build kết thúc bị hủy, nên không cho kết quả",
             note_en=f"{creasons.get('build_skipping', 0)} of {sum(creasons.values())} were canceled by build_skipping (a newer build on the same branch). "
                     "Already spent, not a saving: push fewer times while CI runs, or skip GPU on draft PRs",
             note_vi=f"{creasons.get('build_skipping', 0)} trong {sum(creasons.values())} bị hủy bởi build_skipping (build mới hơn trên cùng branch). "
                     "Đã tiêu rồi, không phải tiết kiệm: push ít lần hơn khi CI đang chạy, hoặc bỏ qua GPU cho PR draft",
             effect_en="Skip GPU CI on draft PRs to avoid starting builds that get superseded [hypothesis]",
             effect_vi="Bỏ chạy GPU CI trên PR draft để tránh khởi chạy các build sẽ bị hủy đè [giả thuyết]"),
        dict(id="path", gpu_h=None, basis="not measured", ticket="LM-762", goto="#gpu/explore",
             en=f"Path-based gating: run {wl[0]['workload']} ({wl[0]['gpu_h']} GPU-h) only when its paths change",
             vi=f"Chạy theo path: chỉ chạy {wl[0]['workload']} ({wl[0]['gpu_h']} GPU-h) khi path liên quan thay đổi",
             note_en="Needs the path→workload map from plan P-tasks (see GPU E2E tab for shadow estimate)",
             note_vi="Cần bảng path→workload trong kế hoạch P (xem ước tính shadow ở tab Pipeline E2E GPU)",
             effect_en="Skips unaffected GPU jobs on doc/CPU/narrow PRs → direct wall-time & queue reduction [hypothesis]",
             effect_vi="Bỏ qua job GPU không liên quan trên PR doc/CPU/hẹp → giảm trực tiếp thời gian chạy & chờ [giả thuyết]"),
    ]
    weeks = [dict(w=k, gpu_h=round(sum(v.values()) / 60, 1), waste_h=round((v.get("canceled", 0) + v.get("failed", 0)) / 60, 1))
             for k, v in sorted(wk.items())]
    merge = dict(queue_p50_min=round(summ["queue_wait_p50_all_gpu_jobs"], 1), queue_p90_min=round(summ["queue_wait_p90_all_gpu_jobs"], 1),
                 passed_dur_p50_min=round(summ["passed_pr_build_duration_min_p50"], 1),
                 passed_dur_p90_min=round(summ["passed_pr_build_duration_min_p90"], 1),
                 pr_builds=summ["pr_builds_total"], distinct_prs=summ["distinct_prs"])
    return dict(total_gpu_h=round(total / 60, 1), by_state_h={k: round(v / 60, 1) for k, v in by_state.items()},
                pr_build_p50_gpu_h=round(pr_gpu[len(pr_gpu) // 2] / 60, 2) if pr_gpu else None,
                retry_gpu_h=retry_h, cancel_reasons=dict(creasons.most_common()), superseded_gpu_h=round(sup / 60, 1), workloads=wl, levers=levers,
                weeks=weeks, merge=merge, mp_pr_gpu_h=ff["mp_pr_gpu_hours"])


def bug_snapshot(target=BUG_TARGET):
    """One `gh api` call; the page re-fetches live from api.github.com (CORS *)."""
    out = dict(target=target, fetched_at=_now(), exists=None, item=None, newest=None, error="")
    try:
        p = subprocess.run(["gh", "api", f"repos/{target['repo']}/issues/{target['number']}"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=40)
        if p.returncode == 0:
            j = json.loads(p.stdout)
            out["exists"] = True
            out["item"] = dict(number=j["number"], title=j["title"], state=j["state"], url=j["html_url"],
                               is_pr="pull_request" in j, user=(j.get("user") or {}).get("login"),
                               labels=[x["name"] for x in j.get("labels", [])], created_at=j["created_at"],
                               comments=j.get("comments", 0), body=(j.get("body") or "")[:1500])
        elif "404" in (p.stderr + p.stdout) or "Not Found" in (p.stderr + p.stdout):
            out["exists"] = False
        else:
            out["error"] = (p.stderr or p.stdout).strip()[-200:]
        q = subprocess.run(["gh", "api", f"repos/{target['repo']}/issues?state=all&per_page=1&sort=created&direction=desc"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40)
        if q.returncode == 0 and q.stdout.strip().startswith("["):
            n = json.loads(q.stdout)
            out["newest"] = n[0]["number"] if n else None
    except (OSError, ValueError, subprocess.TimeoutExpired) as ex:
        out["error"] = f"{type(ex).__name__}: {ex}"[:200]
    return out


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def agents():
    res = {}
    for d in ("flaky", "gpuload", "bug", "rebase"):
        try:
            res[d] = json.load(open(os.path.join(AGENT_DIR, d + ".json"), encoding="utf-8"))
        except (OSError, ValueError):
            res[d] = None
    return res


def build(fetch_bug=True):
    if os.environ.get("TRD_NO_GH"):   # local-only rebuild: keep the last bug snapshot, no `gh api` call
        fetch_bug = False
    rows, builds, cost = _load()
    prev = {}
    try:
        prev = json.load(open(JSON_OUT, encoding="utf-8"))
    except (OSError, ValueError):
        pass
    fl = flaky(rows, builds, cost)
    d = dict(updated_at=_now(), window=_window(builds), weeks=_weeks(builds),
             flaky=fl, gpuload=gpuload(rows, builds, cost, fl),
             bug=bug_snapshot() if fetch_bug else prev.get("bug") or dict(target=BUG_TARGET, exists=None),
             agents=agents())
    return d


def save(d):
    os.makedirs(OUT, exist_ok=True)
    d["updated_at"] = _now()
    for path, text in ((JSON_OUT, json.dumps(d, ensure_ascii=False, indent=1)),
                       (LIVE_JS, "window.onTraceDirs&&window.onTraceDirs(" +
                        json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ");\n")):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    return d


if __name__ == "__main__":
    d = save(build())
    f, g, b = d["flaky"]["totals"], d["gpuload"], d["bug"]
    print(f"window {d['window']['start']}..{d['window']['end']} · flaky {f['flaky']}/{f['first_fail']} first-try fails passed on retry"
          f" · retry {f['retry_gpu_h']} GPU-h · flips {f['flips']}")
    print(f"gpu {g['total_gpu_h']} GPU-h · by state {g['by_state_h']} · superseded {g['superseded_gpu_h']} GPU-h")
    print(f"bug #{b['target']['number']}: exists={b['exists']} newest=#{b.get('newest')} {b.get('error', '')}")
