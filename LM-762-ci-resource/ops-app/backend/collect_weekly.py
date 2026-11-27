"""Collect the weekly full build (GitHub Actions workflow weekly_full_build.yml on LMCache/LMCache) into ops.db.

Local run only, read-only `gh api` calls (the gh login of this user; no Buildkite token needed).

The workflow (.github/workflows/weekly_full_build.yml, dev) has one job per device lane, "Weekly full build (CUDA)",
"Weekly full build (XPU)", later AMD / RBLN. Each lane runs .github/scripts/weekly_full_build.py, which creates one
Buildkite build per pipeline of its manifest, waits, checks every required job and uploads an artifact
`weekly-full-build[-<device>]-<run number>` with report.json:
  {passed, commit, branch, timed_out, log_notes, pipelines: [{slug, name, number, url, state, retried[],
   problems: [{kind (build|failed|soft_failed|not_run|missing|suite_skipped|workload_skipped), label, state,
               exit_status, url, job_id, detail}]}]}
Only report.json and summary.md are read from the artifact zip (in memory; the failed-job logs are not stored).

Cache: data/weekly_cache/run-<id>.json (run + jobs + artifact list of a finished run) and
data/weekly_cache/artifact-<id>.json (report + summary). Artifacts expire after 90 days; what was cached is kept,
so old runs keep their reports. A finished run is fetched again only when GitHub shows a new attempt.

  python -X utf8 collect_weekly.py            # last 12 weeks, up to 30 runs
  python -X utf8 collect_weekly.py --weeks 26 --max 60
"""
import argparse
import datetime as dt
import io
import json
import re
import subprocess
import zipfile

from config import APP, REPO
from db import connect, new_snapshot, now_iso, upsert

WORKFLOW = "weekly_full_build.yml"
CACHE = APP / "data" / "weekly_cache"
# job names: "Weekly full build (CUDA)" (old) or "Weekly full build (CUDA) / weekly / Weekly full build (CUDA)" (reusable workflow, run 8+)
JOB_RE = re.compile(r"^Weekly full build(?: \(([^)]+)\))?(?:$| / )")
ART_RE = re.compile(r"^weekly-full-build-(?:([a-z][a-z0-9]*)-)?(\d+)$")
MAX_MEMBER = 2 * 2**20   # report.json / summary.md are a few KB; anything larger is not read


def gh(path, binary=False):
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    out = subprocess.run(cmd, capture_output=True, timeout=300)
    if out.returncode:
        raise RuntimeError(f"gh api {path}: {out.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return out.stdout if binary else json.loads(out.stdout.decode("utf-8") or "null")


def device_of_job(name):
    m = JOB_RE.match(name or "")
    return (m.group(1) or "CUDA").lower() if m else None


def device_of_artifact(name):
    m = ART_RE.match(name or "")
    return (m.group(1) or "cuda") if m else None


def minutes(a, b):
    if not a or not b:
        return None
    p = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
    return round((p(b) - p(a)).total_seconds() / 60, 1)


def jload(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def jsave(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def clean_report(rep):
    """Keep only the documented fields, with plain types (the artifact is untrusted data)."""
    s = lambda v, n=500: None if v is None else str(v)[:n]  # noqa: E731
    out = dict(passed=bool(rep.get("passed")), commit=s(rep.get("commit"), 64), branch=s(rep.get("branch"), 100),
               timed_out=bool(rep.get("timed_out")), log_notes=[s(x) for x in (rep.get("log_notes") or [])][:20], pipelines=[])
    for p in (rep.get("pipelines") or [])[:50]:
        if not isinstance(p, dict):
            continue
        num = p.get("number")
        out["pipelines"].append(dict(
            slug=s(p.get("slug"), 100), name=s(p.get("name"), 200), number=num if isinstance(num, int) else None,
            url=s(p.get("url")), state=s(p.get("state"), 40), retried=[s(x, 200) for x in (p.get("retried") or [])][:50],
            problems=[dict(kind=s(q.get("kind"), 40), label=s(q.get("label"), 300), state=s(q.get("state"), 40),
                           exit_status=q.get("exit_status") if isinstance(q.get("exit_status"), int) else None,
                           url=s(q.get("url")), job_id=s(q.get("job_id"), 80), detail=s(q.get("detail"), 1000))
                      for q in (p.get("problems") or [])[:200] if isinstance(q, dict)]))
    return out


def fetch_artifact(art):
    """report.json + summary.md of one artifact, cached forever; None when expired and never cached."""
    path = CACHE / f"artifact-{art['id']}.json"
    got = jload(path)
    if got:
        return got
    if art.get("expired"):
        return None
    blob = gh(f"repos/{REPO}/actions/artifacts/{art['id']}/zip", binary=True)
    rep, summ = None, None
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for info in z.infolist():
            if info.filename not in ("report.json", "summary.md") or info.file_size > MAX_MEMBER:
                continue
            txt = z.read(info).decode("utf-8", "replace")
            if info.filename == "report.json":
                rep = clean_report(json.loads(txt))
            else:
                summ = txt[:20000]
    got = dict(id=art["id"], name=art["name"], created_at=art.get("created_at"), report=rep, summary=summ)
    jsave(path, got)
    return got


def fetch_run(run):
    """Run + latest-attempt jobs + artifacts; finished runs come from the cache unless GitHub shows a new attempt."""
    path = CACHE / f"run-{run['id']}.json"
    old = jload(path)
    if (old and old["run"].get("status") == "completed" and run.get("status") == "completed"
            and old["run"].get("run_attempt") == run.get("run_attempt") and old["run"].get("updated_at") == run.get("updated_at")):
        return old, True
    jobs = gh(f"repos/{REPO}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100").get("jobs") or []
    arts = gh(f"repos/{REPO}/actions/runs/{run['id']}/artifacts?per_page=100").get("artifacts") or []
    keep_run = {k: run.get(k) for k in ("id", "run_number", "run_attempt", "event", "status", "conclusion", "head_branch",
                                         "head_sha", "created_at", "run_started_at", "updated_at", "html_url")}
    keep_jobs = [{k: j.get(k) for k in ("id", "name", "status", "conclusion", "started_at", "completed_at", "html_url", "run_attempt")}
                 for j in jobs]
    keep_arts = [{k: a.get(k) for k in ("id", "name", "created_at", "expired", "size_in_bytes")} for a in arts]
    # an artifact listed before and gone now (expired, deleted): keep the old entry, its report is in the cache
    seen = {a["id"] for a in keep_arts}
    keep_arts += [a for a in (old or {}).get("artifacts") or [] if a["id"] not in seen]
    data = dict(run=keep_run, jobs=keep_jobs, artifacts=keep_arts, fetched_at=now_iso())
    if run.get("status") == "completed":
        jsave(path, data)
    return data, False


def lane_state(job, rep):
    if not job:
        return "not_run"
    if job.get("status") != "completed":
        return "running"
    c = job.get("conclusion")
    if c == "success":
        return "failed" if rep and not rep["passed"] else "passed"
    if c == "skipped":
        return "not_run"
    if c == "cancelled":
        return "cancelled"
    if c == "timed_out" or (rep and rep["timed_out"]):
        return "timed_out"
    return "failed"


def run_verdict(run, lanes):
    if run.get("status") != "completed":
        return "running"
    c = run.get("conclusion")
    if c == "success":
        return "passed"
    if c == "cancelled":
        return "cancelled"
    if c == "timed_out" or any(x["state"] == "timed_out" for x in lanes):
        return "timed_out"
    return "failed"


def schedule_info():
    """Is the cron line enabled on dev? (The workflow file ships it commented out until manual runs are validated.)"""
    try:
        import base64
        f = gh(f"repos/{REPO}/contents/.github/workflows/{WORKFLOW}?ref=dev")
        txt = base64.b64decode(f.get("content") or "").decode("utf-8", "replace")
    except (RuntimeError, ValueError):
        return None
    on = bool(re.search(r"^\s*schedule:\s*$", txt, re.M))
    cron = re.search(r"^\s*#?\s*-\s*cron:\s*['\"]([^'\"]+)['\"]", txt, re.M)
    return dict(enabled=on, cron=cron.group(1) if cron else None)


def store(con, snap, data):
    run, jobs, arts = data["run"], data["jobs"], data["artifacts"]
    rid = run["id"]
    # newest artifact per device (a re-run uploads the same name again); the older ones are earlier attempts
    by_dev = {}
    for a in sorted(arts, key=lambda a: a.get("created_at") or ""):
        d = device_of_artifact(a["name"])
        if d:
            by_dev.setdefault(d, []).append(a)
    jobs_by_dev = {}
    prep = None
    for j in jobs:
        d = device_of_job(j["name"])
        if d:
            jobs_by_dev[d] = j
        elif "Prepare" in (j.get("name") or ""):
            prep = j
    for t in ("weekly_gha_problem", "weekly_gha_pipeline", "weekly_gha_lane"):
        con.execute(f"DELETE FROM {t} WHERE run_id=?", (rid,))
    lanes = []
    n_reports = 0
    for dev in sorted(set(by_dev) | set(jobs_by_dev)):
        job, cand = jobs_by_dev.get(dev), by_dev.get(dev, [])
        reps = [(a, fetch_artifact(a)) for a in cand]
        reps = [(a, r) for a, r in reps if r and r.get("report")]
        art, got = reps[-1] if reps else (cand[-1] if cand else None, None)
        rep = got["report"] if got else None
        earlier = [r for _, r in reps[:-1]]
        n_reports += bool(rep)
        lane = dict(run_id=rid, device=dev, job_id=job and job["id"], job_name=job and job["name"], status=job and job["status"],
                    conclusion=job and job["conclusion"], state=lane_state(job, rep), started_at=job and job["started_at"],
                    completed_at=job and job["completed_at"], url=job and job["html_url"],
                    artifact_name=art and art["name"], artifact_id=art and art["id"], report=int(bool(rep)),
                    report_passed=None if rep is None else int(rep["passed"]), timed_out=None if rep is None else int(rep["timed_out"]),
                    commit_sha=rep and rep["commit"], branch=rep and rep["branch"], earlier_reports=len(earlier),
                    earlier_failed=sum(1 for r in earlier if not r["report"]["passed"]),
                    log_notes=json.dumps(rep["log_notes"]) if rep else None, snapshot_id=snap)
        upsert(con, "weekly_gha_lane", lane, ["run_id", "device"])
        lanes.append(lane)
        for i, p in enumerate((rep or {}).get("pipelines") or []):
            upsert(con, "weekly_gha_pipeline", dict(run_id=rid, device=dev, slug=p["slug"], name=p["name"], number=p["number"],
                                                     url=p["url"], state=p["state"], retried=json.dumps(p["retried"]), ord=i),
                   ["run_id", "device", "slug"])
            for k, q in enumerate(p["problems"]):
                upsert(con, "weekly_gha_problem", dict(run_id=rid, device=dev, slug=p["slug"], idx=k, **{x: q[x] for x in (
                    "kind", "label", "state", "exit_status", "url", "job_id", "detail")}), ["run_id", "device", "slug", "idx"])
    starts = [j["started_at"] for j in jobs if j.get("started_at")]
    ends = [j["completed_at"] for j in jobs if j.get("completed_at")]
    upsert(con, "weekly_gha_run", dict(
        run_id=rid, run_number=run["run_number"], attempt=run.get("run_attempt"), event=run.get("event"), status=run.get("status"),
        conclusion=run.get("conclusion"), verdict=run_verdict(run, lanes), head_branch=run.get("head_branch"), head_sha=run.get("head_sha"),
        created_at=run.get("created_at"), started_at=run.get("run_started_at"), updated_at=run.get("updated_at"),
        first_job_at=min(starts) if starts else None, last_job_at=max(ends) if ends and run.get("status") == "completed" else None,
        prepare_conclusion=prep and prep.get("conclusion"), url=run.get("html_url"), snapshot_id=snap), ["run_id"])
    return lanes, n_reports


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=12)
    ap.add_argument("--max", type=int, default=30)
    args = ap.parse_args()
    con = connect()
    snap = new_snapshot(con, "gha:weekly", now_iso())
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(weeks=args.weeks)
    runs = gh(f"repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page={min(args.max, 100)}").get("workflow_runs") or []
    runs = [r for r in runs if dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= since][:args.max]
    n_lanes = n_rep = cached = 0
    for r in runs:
        data, hit = fetch_run(r)
        cached += hit
        lanes, nr = store(con, snap, data)
        n_lanes += len(lanes)
        n_rep += nr
    sch = schedule_info()
    meta = dict(collected_at=now_iso(), workflow=WORKFLOW, weeks=str(args.weeks))
    if sch:
        meta.update(schedule_enabled="1" if sch["enabled"] else "0", cron=sch["cron"] or "")
    for k, v in meta.items():
        upsert(con, "weekly_gha_meta", dict(key=k, value=v), ["key"])
    con.commit()
    for x in con.execute("""SELECT r.run_number, r.run_id, r.verdict, r.event, substr(r.created_at,1,16) at,
                                   (SELECT group_concat(device||':'||state, ' ') FROM weekly_gha_lane l WHERE l.run_id=r.run_id) lanes,
                                   (SELECT COUNT(*) FROM weekly_gha_pipeline p WHERE p.run_id=r.run_id) pipes,
                                   (SELECT COUNT(*) FROM weekly_gha_problem q WHERE q.run_id=r.run_id) probs
                            FROM weekly_gha_run r ORDER BY r.created_at DESC LIMIT ?""", (args.max,)):
        print(dict(x))
    print(f"schedule on dev: {'enabled' if sch and sch['enabled'] else 'not enabled' if sch else 'unknown'} (cron {sch and sch['cron']})")
    print(f"weekly runs: {len(runs)} (lanes {n_lanes}, reports {n_rep}, from cache {cached})")


if __name__ == "__main__":
    main()
