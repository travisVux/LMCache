"""Unit checks of the Before / After CI impact logic (backend/ci_impact.py + the parsing helpers of
collect_ci_impact.py). Synthetic rows only: no network, no ops.db.

  python -X utf8 tests/check_ci_impact.py      # exit 1 on any failure
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import ci_impact as M  # noqa: E402
import collect_ci_impact as C  # noqa: E402

FAIL = []


def check(name, ok, got=None):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  (got {got!r})"))
    if not ok:
        FAIL.append(name)


def job(pipe, num, pr, created, start, end, gpus, state="passed", build_state="passed", label="x", jid=None, retried=False, retried_in="", branch="b", commit="c1"):
    w = M.mins(start, end)
    return dict(pipeline=pipe, build_number=num, build_state=build_state, is_pr=1 if pr else 0, pr=pr or "", branch=branch,
                build_created=created, commit=commit, label=label, workload=label, gpus=gpus, state=state, retried=retried,
                retried_in_job_id=retried_in, runnable_at=created, started_at=start, finished_at=end, wall_min=w,
                queue_wait_min=0, gpu_min=None if w is None or gpus == "" else w * gpus, job_id=jid or f"{pipe}-{num}-{label}-{start}")


def gjob(pr, commit, wf, name, concl, created, start, end):
    return dict(pr=pr, commit=commit, workflow=wf, event="pull_request", job=name, conclusion=concl, suite_created=created,
                started=start, completed=end, exec_min=M.mins(start, end), attempt=1)


# ---- timeline -> draft state
tl = {"1": dict(is_draft=False, events=[("2026-11-24T10:00:00Z", "ready")]),        # opened as draft, ready at 10:00
      "2": dict(is_draft=True, events=[("2026-11-24T12:00:00Z", "draft")]),         # opened ready, back to draft at 12:00
      "3": dict(is_draft=True, events=[])}
d = C.draft_fn(tl)
check("draft before ready-for-review", d("1", "2026-11-24T09:00:00Z") is True)
check("ready after ready-for-review", d("1", "2026-11-24T10:30:00Z") is False)
check("ready before convert-to-draft", d("2", "2026-11-24T11:00:00Z") is False)
check("draft after convert-to-draft", d("2", "2026-11-24T12:30:00Z") is True)
check("no events -> current state", d("3", "2026-11-24T09:00:00Z") is True)
check("unknown PR -> None", d("99", "2026-11-24T09:00:00Z") is None)
check("conversions in window (draft until ready again)", C.conversions(tl, "2026-11-24T00:00:00Z", "2026-11-25T00:00:00Z") == [("2", "2026-11-24T12:00:00Z", None)])
tl2 = {"5": dict(is_draft=False, events=[("2026-11-24T10:00:00Z", "draft"), ("2026-11-24T10:10:00Z", "ready")])}
check("draft interval ends at ready-for-review", C.conversions(tl2, "2026-11-24T00:00:00Z", "2026-11-25T00:00:00Z") == [("5", "2026-11-24T10:00:00Z", "2026-11-24T10:10:00Z")])

# ---- smoke labels keep + GPU map
check("smoke job kept", C.keep(M.SMOKE, ":zap: vllm / client_wheel / grpc") and not C.keep(M.SMOKE, ":pipeline: upload"))
fl = C.flatten([dict(pipeline_slug=M.SMOKE, number=1, state="passed", created_at="2026-11-24T12:00:00Z", pull_request={"id": "7"}, branch="x",
                     jobs=[dict(type="script", id="j1", name=":zap: vllm / client_wheel / grpc", state="passed", started_at="2026-11-24T12:01:00Z", finished_at="2026-11-24T12:11:00Z"),
                           dict(type="script", id="j2", name=":zap: cpu_e2e_validation (shm / grpc)", state="passed", started_at="2026-11-24T12:01:00Z", finished_at="2026-11-24T12:05:00Z")])])
check("client_wheel = 1 GPU (10 GPU-min)", round(fl[0]["gpu_min"], 1) == 10.0, fl[0]["gpu_min"])
check("cpu_e2e_validation = 0 GPU", fl[1]["gpu_min"] == 0, fl[1]["gpu_min"])

# ---- window numbers: one draft unit build (1 GPU x 60 min), one ready unit build (60 min), a heavy MP build (2 GPU x 30 min)
W = dict(since="2026-11-24T00:00:00Z", until="2026-11-26T00:00:00Z", draft=d,
         conv=[("2", "2026-11-24T12:00:00Z", None), ("1", "2026-11-24T09:30:00Z", "2026-11-24T09:40:00Z")],
         bk=[job(M.UNIT, 1, "1", "2026-11-24T09:00:00Z", "2026-11-24T09:00:00Z", "2026-11-24T10:00:00Z", 1),
             job(M.UNIT, 2, "1", "2026-11-24T11:00:00Z", "2026-11-24T11:00:00Z", "2026-11-24T12:00:00Z", 1),
             # PR 2 goes to draft at 12:00 while its MP job runs 11:30 -> 12:30: 30 min x 2 GPU ran after the conversion
             job(M.MP, 5, "2", "2026-11-24T11:30:00Z", "2026-11-24T11:30:00Z", "2026-11-24T12:30:00Z", 2, label="w1"),
             job(M.UNIT, 9, None, "2026-11-24T13:00:00Z", "2026-11-24T13:00:00Z", "2026-11-24T13:30:00Z", 1, build_state="failed", state="failed", branch="dev"),
             # flaky: failed attempt retried, retry passed
             job(M.UNIT, 3, "1", "2026-11-24T14:00:00Z", "2026-11-24T14:00:00Z", "2026-11-24T14:10:00Z", 1, state="failed", jid="a", retried=True, retried_in="b"),
             job(M.UNIT, 3, "1", "2026-11-24T14:00:00Z", "2026-11-24T14:11:00Z", "2026-11-24T14:21:00Z", 1, jid="b"),
             job(M.UNIT, 4, "1", "2026-11-24T15:00:00Z", "2026-11-24T15:00:00Z", "2026-11-24T15:10:00Z", 1, state="failed", build_state="failed", jid="c", retried=True, retried_in="d"),
             job(M.UNIT, 4, "1", "2026-11-24T15:00:00Z", "2026-11-24T15:11:00Z", "2026-11-24T15:21:00Z", 1, state="failed", build_state="failed", jid="d"),
             job(M.MP, 99, None, "2026-11-24T16:00:00Z", "2026-11-24T16:00:00Z", "2026-11-24T18:00:00Z", 4, branch="ci-weekly-full")],
         gha=[gjob("1", "c1", "Code Quality", "Check code quality", "SUCCESS", "2026-11-24T11:00:00Z", "2026-11-24T11:01:00Z", "2026-11-24T11:06:00Z"),
              gjob("1", "c1", "Test", "test: 3.12 on ubuntu", "FAILURE", "2026-11-24T11:00:00Z", "2026-11-24T11:08:00Z", "2026-11-24T11:28:00Z"),
              gjob("1", "c1", "CPU Device Tests", "CPU device (ubuntu)", "CANCELLED", "2026-11-24T11:00:00Z", "2026-11-24T11:08:00Z", "2026-11-24T11:30:00Z"),
              gjob("1", "c1", "Code Quality", "Stop CPU device (Test failed)", "SUCCESS", "2026-11-24T11:00:00Z", "2026-11-24T11:28:00Z", "2026-11-24T11:29:00Z"),
              gjob("1", "c0", "Test", "test: 3.12 on ubuntu", "SUCCESS", "2026-11-24T09:00:00Z", "2026-11-24T09:01:00Z", "2026-11-24T09:21:00Z")],
         mp_builds=[dict(decision="bypassed"), dict(decision="bypassed"), dict(decision="heavy", reasons=["force_ci"]), dict(decision="path_skip")])
n = M.window_numbers(W)
check("window = 2 days", abs(n["days"] - 2) < 1e-6, n["days"])
check("draft unit GPU-h/day = 0.5 (60 min on day avg of 2 days)", round(n["draft_gpu_h_day_unit"], 3) == 0.5, n["draft_gpu_h_day_unit"])
check("bypass rate = 2 / 3", round(n["bypass_rate"], 1) == 66.7, n["bypass_rate"])
check("heavy reasons", n["heavy_reasons"] == {"force_ci": 1}, n["heavy_reasons"])
check("flake rate counts the failed-then-passed job", n["flake_rate"][0] is not None and n["flake_rate"][0] > 0, n["flake_rate"])
check("weekly full build kept out of daily GPU (8 GPU-h)", round(n["weekly_gpu_h"], 1) == 8.0 and n["n_weekly_builds"] == 1, n["weekly_gpu_h"])
check("repeat failure counted, flaky counted apart", n["repeat_rate"][0] > 0 and round(n["retry_waste_gpu_h_day"] * 60, 1) == 5.0, (n["repeat_rate"], n["retry_waste_gpu_h_day"]))
check("draft overlap ends at ready again (+10 min on PR 1)", round(n["after_draft_gpu_min_day"], 1) == 35.0, n["after_draft_gpu_min_day"])
check("post-merge dev builds with tests per day = 0.5", n["dev_tested_day"] == 0.5, n["dev_tested_day"])
check("L1 exec p50 = 5 min", n["l1_exec"][0] == 5.0, n["l1_exec"])
check("push -> first L2 start = 8 min", n["l2_start"][0] == 8.0, n["l2_start"])
check("CPU device stopped within 10 min = 100% of 1", n["stop_rate"] == (100.0, 1), n["stop_rate"])
check("CPU device min/day after test failure = 11", round(n["cpu_after_test_fail_day"], 1) == 11.0, n["cpu_after_test_fail_day"])
check("draft commit runner-min counted on draft side", n["n_draft_commits"] == 1 and n["n_ready_commits"] == 1, (n["n_draft_commits"], n["n_ready_commits"]))

# ---- comparison, sample size and status rules (no extrapolation)
rows = M.compare(n, n, weekly=dict(finished=2, passed=1, failed=1, other=0, pass_pct=50.0, latest="#5 passed"))
M.finish(rows, after_days=2)
by = {r["key"]: r for r in rows}
check("young window -> collecting or insufficient, never ok", all(r["status"] in ("collecting", "insufficient", "no_data", "new") for r in rows if not r["after_only"]),
      {r["key"]: r["status"] for r in rows if r["status"] == "ok"})
check("insufficient sample has no delta", all(r["delta"] is None and r["delta_pct"] is None for r in rows if r["status"] == "insufficient"))
check("after-only metric has no before / delta", by["bypass_rate"]["before"] is None and by["bypass_rate"]["delta"] is None)
check("weekly pass with N", by["weekly_pass"]["after"] == 50.0 and by["weekly_pass"]["n_after"] == 2)
r = dict(before=10.0, after=5.0, n_after=100, min_n=10, after_only=False)
check("mature window + big N -> ok", M.status(r, after_days=14) == "ok")
r["status"] = "ok"
check("delta and % (10 -> 5 = -5, -50%)", M.delta(r) == (-5.0, -50.0), M.delta(r))
check("before 0 -> no %", M.delta(dict(before=0.0, after=3.0, status="ok")) == (3.0, None))

# ---- FRS review 2026-11-26
check("collecting window: no change, no verdict", all(r["delta"] is None and r["delta_pct"] is None for r in rows if r["status"] == "collecting"))
check("N = 0 with a minimum -> no_data", M.status(dict(before=1.0, after=0.0, n_after=0, min_n=10, after_only=False), after_days=20) == "no_data")
check("p90 rows and redundant rows are detail", by["l12_done_p90"]["detail"] and by["gpu_h_day_pr"]["detail"] and not by["gpu_h_per_push"]["detail"])
check("retry waste is in the GPU family", by["retry_waste_gpu"]["family"] == "gpu" and by["repeat_rate"]["family"] == "gpu")
check("new metrics present", all(k in by for k in ("gpu_queue_p50", "smoke_cov", "gha_draft_per_push", "weekly_mp_fail")), [k for k in ("gpu_queue_p50", "smoke_cov", "gha_draft_per_push", "weekly_mp_fail") if k not in by])
check("GPU queue wait counted on GPU PR jobs", n["gpu_queue"][2] > 0, n["gpu_queue"])

# ---- impact redesign 2026-11-26: GPU-h per weekday (weekday-matched comparison of a short After window)
wd = n["gpu_by_weekday"]
check("window Tue 24 + Wed 25 Nov: one day of each weekday", {k: v[1] for k, v in wd.items()} == {"1": 1.0, "2": 1.0}, wd)
check("weekday GPU-h add up to gpu_h_day x days (weekly full build kept out)", abs(sum(v[0] for v in wd.values()) - n["gpu_h_day"] * n["days"]) < 0.02, (wd, n["gpu_h_day"]))
check("all rows were created on Tuesday", wd["2"][0] == 0 and wd["1"][0] > 0, wd)
p = M.by_weekday("2026-11-25T11:19:00Z", "2026-11-26T14:02:00Z", [])
check("partial days counted as fractions (Wed 0.53 d, Thu 0.585 d)", p == {"2": [0.0, 0.528], "3": [0.0, 0.585]}, p)

print("RESULT:", "FAIL" if FAIL else "PASS", f"({len(FAIL)} failed)" if FAIL else "")
sys.exit(1 if FAIL else 0)
