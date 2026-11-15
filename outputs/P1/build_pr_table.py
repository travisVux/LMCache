"""Step 3: join GitHub (PR, commit, checks) with Buildkite (builds, jobs) for the fixed window of window.json.
Local files only. Writes:

  gh_jobs_30d.csv      one row per GitHub Actions job attempt (check run) that ran (CPU runners)
  pr_commit_30d.csv    one row per (PR, commit) with CI activity in the window: triggers, minutes, retries, links
  pr_30d.csv           one row per PR: the same, added up
  ttg_30d.csv          one row per PR merged into dev in the window: time from the last push to all required checks green
  retry_events_30d.csv one row per first attempt that failed and was run again (job retry, workflow re-run, or a new
                       build on the same commit), with what happened next and the evidence class
  join_quality.json    counts for the data-quality notes (unmatched rows, missing fields)

  python -I -X utf8 outputs/P1/build_pr_table.py
"""
import collections, csv, json, os, re
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
WIN = json.load(open(os.path.join(HERE, "window.json"), encoding="utf-8"))
REPO = WIN["repo"]
REQ_GHA = ("DCO", "Check code quality")
REQ_BK = ("k3-unit-tests", "k3-multiprocess-test")
BAD = ("FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "ACTION_REQUIRED")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def mins(a, b):
    return None if not a or not b else round((ts(b) - ts(a)).total_seconds() / 60, 3)


def inwin(t):
    return bool(t) and WIN["since"] <= t < WIN["until"]


def norm_job(n):
    """matrix job names -> one step name: 'CPU device (ubuntu / opt / zmq)' -> 'CPU device (matrix)'"""
    return re.sub(r"\s*\(.*\)$", " (matrix)", re.sub(r"^test: [\d.]+ on .*$", "test: (matrix)", n))


def write(fn, rows):
    with open(os.path.join(HERE, fn), "w", newline="", encoding="utf-8") as f:
        if not rows:
            return
        w = csv.DictWriter(f, list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    G = json.load(open(os.path.join(HERE, "raw", "gh_checks_30d.json"), encoding="utf-8"))
    jobs = list(csv.DictReader(open(os.path.join(HERE, "jobs_all_30d.csv"), encoding="utf-8")))
    sig = json.load(open(os.path.join(HERE, "raw", "fail_signatures.json"), encoding="utf-8")) if os.path.exists(os.path.join(HERE, "raw", "fail_signatures.json")) else {}
    builds = {}
    for slug, fn in (("k3-multiprocess-test", "builds_30d.json"), ("k3-unit-tests", "builds_k3-unit-tests_30d.json")):
        for b in json.load(open(os.path.join(HERE, "raw", fn), encoding="utf-8")):
            if b.get("pull_request"):
                builds[(slug, str(b["number"]))] = dict(pipeline=slug, number=str(b["number"]), pr=str(b["pull_request"]["id"]), sha=b.get("commit") or "",
                                                        state=b["state"], created=b["created_at"], started=b.get("started_at"), finished=b.get("finished_at"),
                                                        url=b.get("web_url") or "", rebuilt_from=(b.get("rebuilt_from") or {}).get("number") if isinstance(b.get("rebuilt_from"), dict) else None)
    q = collections.Counter()

    # ---------------- GitHub Actions jobs (check runs of github-actions suites)
    gjobs, suites_by = [], collections.defaultdict(list)
    prinfo = {}
    orph = collections.defaultdict(list)  # force-pushed commits, read by SHA (fetch_gh_checks.py)
    for sha, o in (G.get("orphan_commits") or {}).items():
        orph[o["pr"]].append(o["commit"])
    for p in G["prs"]:
        n = str(p["number"])
        lab = [(e["createdAt"], e["__typename"], (e.get("label") or {}).get("name")) for e in p["timelineItems"]["nodes"] if e["__typename"] in ("LabeledEvent", "UnlabeledEvent")]
        prinfo[n] = dict(author=(p.get("author") or {}).get("login") or "", created=p["createdAt"], merged=p["mergedAt"] or "", base=p["baseRefName"], url=p["url"],
                         full=[t for t, k, l in lab if k == "LabeledEvent" and l == "full"], commits=[c["oid"] for c in p["commit_nodes"]], nodes=p["commit_nodes"])
        for c in p["commit_nodes"] + orph.get(n, []):
            for s in c["checkSuites"]["nodes"]:
                suites_by[(n, c["oid"])].append(s)
                if not inwin(s["createdAt"]) or not s.get("workflowRun") or (s.get("app") or {}).get("slug") != "github-actions":
                    continue
                wf = s["workflowRun"]["workflow"]["name"]
                runs = [r for r in s["checkRuns"]["nodes"] if r["startedAt"] and r["conclusion"] not in ("SKIPPED", "NEUTRAL")]
                if len(s["checkRuns"]["nodes"]) >= 60:
                    q["gha_suite_runs_truncated_at_60"] += 1
                by_name = collections.defaultdict(list)
                for r in runs:
                    by_name[r["name"]].append(r)
                for name, rs in by_name.items():
                    rs.sort(key=lambda r: r["startedAt"])
                    for i, r in enumerate(rs):
                        ex = mins(r["startedAt"], r["completedAt"])
                        if ex is not None and ex < 0:  # skipped-like rows: completed before started
                            ex = 0.0
                        gjobs.append(dict(pr=n, commit=c["oid"], workflow=wf, event=s["workflowRun"]["event"], job=name, step=norm_job(name),
                                          conclusion=r["conclusion"] or r["status"], suite_created=s["createdAt"], started=r["startedAt"], completed=r["completedAt"] or "",
                                          exec_min=ex, start_delay_min=mins(s["createdAt"], r["startedAt"]), attempt=i + 1, replaced=int(i < len(rs) - 1),
                                          next_conclusion=rs[i + 1]["conclusion"] if i < len(rs) - 1 else "", required=int(r["name"] in REQ_GHA),
                                          run_url=s["workflowRun"]["url"]))
    write("gh_jobs_30d.csv", gjobs)

    # ---------------- per (PR, commit)
    pc = collections.defaultdict(lambda: dict(gha_runs=set(), gha_jobs=0, gha_job_min=0.0, gha_reruns=0, gha_rerun_min=0.0,
                                              mp_builds=[], unit_builds=[], bk_job_min=0.0, gpu_min=0.0, bk_retried=0, bk_retry_gpu_min=0.0, first=None))
    for j in gjobs:
        d = pc[(j["pr"], j["commit"])]
        d["gha_runs"].add(j["run_url"])
        d["gha_jobs"] += 1
        d["gha_job_min"] += j["exec_min"] or 0
        if j["replaced"]:
            d["gha_reruns"] += 1
            d["gha_rerun_min"] += j["exec_min"] or 0
        d["first"] = min(filter(None, [d["first"], j["suite_created"]]))
    for b in builds.values():
        if not inwin(b["created"]):
            continue
        d = pc[(b["pr"], b["sha"])]
        d["mp_builds" if b["pipeline"] == "k3-multiprocess-test" else "unit_builds"].append(b)
        d["first"] = min(filter(None, [d["first"], b["created"]]))
    for r in jobs:
        if r["is_pr"] != "1" or not r["started_at"]:
            continue
        d = pc.get((r["pr"], r["commit"]))
        if d is None:
            continue
        d["bk_job_min"] += float(r["wall_min"] or 0)
        d["gpu_min"] += float(r["gpu_min"] or 0)
        if r["retried"] == "True":
            d["bk_retried"] += 1
            d["bk_retry_gpu_min"] += float(r["gpu_min"] or 0)
    rows = []
    for (n, sha), d in pc.items():
        info = prinfo.get(n)
        if info is None:
            q["pr_commit_rows_without_github_pr"] += 1
        elif sha not in info["commits"]:
            q["commits_force_pushed_away"] += 1  # read by SHA when fetch_gh_checks found it
            if not any(o["oid"] == sha for o in orph.get(n, [])):
                q["commits_without_github_checks"] += 1
        last = lambda bs: max(bs, key=lambda b: b["created"])["url"] if bs else ""
        same = lambda bs: max(0, len(bs) - 1)
        rows.append(dict(pr=n, commit=sha, author=(info or {}).get("author", ""), first_ci_at=d["first"] or "",
                         gha_workflow_runs=len(d["gha_runs"]), gha_jobs=d["gha_jobs"], gha_job_min=round(d["gha_job_min"], 1),
                         gha_rerun_jobs=d["gha_reruns"], gha_rerun_job_min=round(d["gha_rerun_min"], 1),
                         mp_builds=len(d["mp_builds"]), mp_same_commit_retriggers=same(d["mp_builds"]),
                         unit_builds=len(d["unit_builds"]), unit_same_commit_retriggers=same(d["unit_builds"]),
                         bk_job_min=round(d["bk_job_min"], 1), gpu_min=round(d["gpu_min"], 1),
                         bk_retried_jobs=d["bk_retried"], bk_retry_gpu_min=round(d["bk_retry_gpu_min"], 1),
                         pr_url=(info or {}).get("url") or f"https://github.com/{REPO}/pull/{n}",
                         commit_url=f"https://github.com/{REPO}/pull/{n}/commits/{sha}" if sha else "",
                         last_mp_build=last(d["mp_builds"]), last_unit_build=last(d["unit_builds"])))
    rows.sort(key=lambda r: (int(r["pr"]), r["first_ci_at"]))
    write("pr_commit_30d.csv", rows)

    # ---------------- per PR
    per = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        a = per[r["pr"]]
        a["pushes_with_ci"] += 1
        for k in ("gha_workflow_runs", "gha_jobs", "gha_job_min", "gha_rerun_jobs", "gha_rerun_job_min", "mp_builds", "unit_builds",
                  "mp_same_commit_retriggers", "unit_same_commit_retriggers", "bk_job_min", "gpu_min", "bk_retried_jobs", "bk_retry_gpu_min"):
            a[k] += r[k]
    prs = []
    for n, a in per.items():
        info = prinfo.get(n, {})
        merged = info.get("merged", "")
        prs.append(dict(pr=n, author=info.get("author", ""), created=info.get("created", ""), merged=merged if inwin(merged) else ("after window" if merged else ""),
                        merge_latency_h=round((ts(merged) - ts(info["created"])).total_seconds() / 3600, 1) if merged and inwin(merged) else "",
                        **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in a.items()},
                        retries_total=a["gha_rerun_jobs"] + a["bk_retried_jobs"] + a["mp_same_commit_retriggers"] + a["unit_same_commit_retriggers"],
                        pr_url=info.get("url") or f"https://github.com/{REPO}/pull/{n}"))
    prs.sort(key=lambda r: -float(r["gpu_min"] or 0))
    write("pr_30d.csv", prs)

    # ---------------- time to green (PRs merged into dev in the window)
    ttg = []
    by_sha = collections.defaultdict(list)
    for b in builds.values():
        by_sha[(b["pipeline"], b["sha"])].append(b)
    for n, info in prinfo.items():
        if not inwin(info["merged"]) or info["base"] != "dev" or not info["nodes"]:
            continue
        c = info["nodes"][-1]
        sha = c["oid"]
        suites = suites_by[(n, sha)]
        bks = by_sha[("k3-unit-tests", sha)] + by_sha[("k3-multiprocess-test", sha)]
        push = min([s["createdAt"] for s in suites] + [b["created"] for b in bks], default=None)
        green, src = {}, {}
        for nm in REQ_GHA:
            ok = [r["completedAt"] for s in suites for r in s["checkRuns"]["nodes"] if r["name"] == nm and r["conclusion"] == "SUCCESS" and r["completedAt"]]
            green[nm] = min(ok) if ok else None
        ctx = {x["context"]: x for x in (c.get("status") or {}).get("contexts", [])}
        mp_build = None
        for slug in REQ_BK:
            ok = sorted((b for b in by_sha[(slug, sha)] if b["state"] == "passed" and b["finished"]), key=lambda b: b["finished"])
            if ok:
                green[slug] = ok[0]["finished"]
                if slug == "k3-multiprocess-test":
                    mp_build = ok[0]
            else:
                x = ctx.get("buildkite/" + slug)
                green[slug] = x["createdAt"] if x and x["state"] == "SUCCESS" else None
                if green[slug]:
                    q["ttg_bk_green_from_status_context"] += 1
        missing = [k for k, v in green.items() if not v]
        allg = max(v for v in green.values() if v) if not missing else None
        full = [t for t in info["full"] if t <= (green.get("k3-multiprocess-test") or info["merged"])]
        label_at = max(full) if full else None
        ttg.append(dict(pr=n, commit=sha, author=info["author"], push_at=push or "", merged_at=info["merged"],
                        dco_min=mins(push, green["DCO"]), quality_min=mins(push, green["Check code quality"]),
                        unit_min=mins(push, green["k3-unit-tests"]), mp_min=mins(push, green["k3-multiprocess-test"]),
                        all_green_min=mins(push, allg) if allg else None, not_green=" ".join(missing),
                        full_label_at=label_at or "", wait_for_full_label_min=max(0.0, mins(push, label_at)) if label_at and push else 0.0,
                        mp_queue_min=mins(mp_build["created"], mp_build["started"]) if mp_build else None,
                        mp_exec_min=mins(mp_build["started"], mp_build["finished"]) if mp_build else None,
                        merge_after_green_min=mins(allg, info["merged"]) if allg else None,
                        pr_open_to_merge_h=round((ts(info["merged"]) - ts(info["created"])).total_seconds() / 3600, 1),
                        commit_url=f"https://github.com/{REPO}/pull/{n}/commits/{sha}",
                        mp_build=mp_build["url"] if mp_build else ""))
    ttg.sort(key=lambda r: r["merged_at"])
    write("ttg_30d.csv", ttg)

    # ---------------- retry events: first attempt failed, then the same thing ran again
    ev = []
    byid = {r["job_id"]: r for r in jobs}
    def final(r):
        seen = 0
        while r["retried_in_job_id"] and r["retried_in_job_id"] in byid and seen < 20:
            r, seen = byid[r["retried_in_job_id"]], seen + 1
        return r
    for r in jobs:  # 1) Buildkite job retry (automatic or manual)
        if r["is_pr"] != "1" or r["retried"] != "True" or r["retry_source"]:
            continue
        f = final(r)
        s = sig.get(r["job_id"], {})
        ev.append(dict(kind="job retry", system="Buildkite", pipeline=r["pipeline"], step=r["workload"], pr=r["pr"], commit=r["commit"],
                       first_state=r["state"], exit_status=r["exit_status"], then=("passed" if f["state"] == "passed" else f["state"]),
                       retry_type=r["retry_type"], cls=s.get("cls") or ("infra" if r["exit_status"] in ("128", "255", "-1", "100") else "unknown"),
                       evidence=s.get("sig") or ("exit " + r["exit_status"] if r["exit_status"] in ("128", "255", "-1", "100") else "no log read"),
                       evidence_line=s.get("line", ""), lost_min=float(r["wall_min"] or 0), lost_gpu_min=float(r["gpu_min"] or 0), unit="GPU-min",
                       link=r["build_url"]))
    # 2) a new build of the same commit after a failed one (Buildkite rebuild, label event, or re-sync)
    for (slug, sha), bs in by_sha.items():
        bs = sorted((b for b in bs if inwin(b["created"]) and b["state"] in ("passed", "failed", "canceled")), key=lambda b: b["created"])
        for i, b in enumerate(bs[:-1]):
            if b["state"] != "failed":
                continue
            nxt = bs[i + 1]
            fj = [r for r in jobs if r["pipeline"] == slug and r["build_number"] == b["number"] and r["state"] in ("failed", "timed_out") and r["retried"] != "True"]
            s = next((sig[r["job_id"]] for r in fj if r["job_id"] in sig), {})
            ev.append(dict(kind="new build, same commit", system="Buildkite", pipeline=slug, step=",".join(sorted({r["workload"] for r in fj})) or "(build)", pr=b["pr"], commit=sha,
                           first_state="failed", exit_status=",".join(sorted({r["exit_status"] for r in fj})), then=nxt["state"],
                           retry_type="rebuild" if nxt["rebuilt_from"] else "new trigger", cls=s.get("cls") or ("infra" if fj and all(r["exit_status"] in ("128", "255", "-1", "100") for r in fj) else "unknown"),
                           evidence=s.get("sig") or "no log read", evidence_line=s.get("line", ""),
                           lost_min=round(sum(float(r["wall_min"] or 0) for r in fj), 1), lost_gpu_min=round(sum(float(r["gpu_min"] or 0) for r in fj), 1), unit="GPU-min", link=b["url"]))
    for j in gjobs:  # 3) GitHub Actions job re-run (an earlier attempt of the same job in the same workflow run)
        if not j["replaced"] or j["conclusion"] not in BAD:
            continue
        ev.append(dict(kind="workflow re-run", system="GitHub Actions", pipeline=j["workflow"], step=j["step"], pr=j["pr"], commit=j["commit"],
                       first_state=j["conclusion"].lower(), exit_status="", then=(j["next_conclusion"] or "").lower().replace("success", "passed"),
                       retry_type="re-run", cls="infra" if j["conclusion"] == "STARTUP_FAILURE" else "unknown",
                       evidence="startup_failure" if j["conclusion"] == "STARTUP_FAILURE" else "GitHub logs not read",
                       evidence_line="", lost_min=j["exec_min"] or 0, lost_gpu_min=0, unit="job-min", link=j["run_url"]))
    write("retry_events_30d.csv", ev)

    q = dict(q)
    q.update(prs_in_github_list=len(G["prs"]), pr_commit_rows=len(rows), prs_with_ci=len(prs), gha_job_attempts=len(gjobs), merged_into_dev=len(ttg),
             ttg_not_green=sum(1 for t in ttg if t["not_green"]), retry_events=len(ev),
             bk_pr_builds_unknown_pr=sum(1 for b in builds.values() if b["pr"] not in prinfo),
             bk_jobs_without_gpu_count=sum(1 for r in jobs if r["is_pr"] == "1" and r["started_at"] and r["gpus"] == ""),
             bk_job_min_without_gpu_count=round(sum(float(r["wall_min"] or 0) for r in jobs if r["is_pr"] == "1" and r["started_at"] and r["gpus"] == ""), 1),
             bk_unknown_gpu_workloads=" ".join(sorted({r["workload"] for r in jobs if r["is_pr"] == "1" and r["started_at"] and r["gpus"] == ""})),
             fail_logs_read=sum(1 for v in sig.values() if v.get("sig") != "no_log"), fail_logs_unreadable=sum(1 for v in sig.values() if v.get("sig") == "no_log"))
    json.dump(q, open(os.path.join(HERE, "join_quality.json"), "w", encoding="utf-8"), indent=1)
    print(json.dumps(q, indent=1))


if __name__ == "__main__":
    main()
