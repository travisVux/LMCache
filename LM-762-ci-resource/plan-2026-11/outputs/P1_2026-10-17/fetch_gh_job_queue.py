"""Step: GitHub Actions runner queue per job (REST), for the CPU queue-time chart of Report 1130.

  python -I -X utf8 fetch_gh_job_queue.py        # resumable; appends to raw/gh_run_jobs_30d.jsonl

GraphQL check runs (gh_jobs_30d.csv) only give startedAt / completedAt. The REST endpoint
  GET /repos/LMCache/LMCache/actions/runs/{run_id}/jobs?filter=all
gives each job's created_at = the moment the job entered the runner queue (for a job with `needs:`,
when its last dependency finished). Runner queue = started_at - created_at.
Jobs copied into a re-run attempt without running again keep the old started_at (< created_at): drop them.
One call per run (+ pages > 100 jobs); ~13k runs -> about 2.5-3 h at 5,000 calls per hour. Sleeps when the rate limit is low.
"""
import csv
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "raw", "gh_run_jobs_30d.jsonl")
REPO = "LMCache/LMCache"
KEEP = ("id", "run_id", "run_attempt", "name", "status", "conclusion", "created_at", "started_at", "completed_at")


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return json.loads(r.stdout)


def wait_rate():
    rl = gh("rate_limit")["resources"]["core"]
    if rl["remaining"] < 60:
        nap = max(5, rl["reset"] - time.time() + 5)
        print(f"rate limit {rl['remaining']} left, sleeping {nap / 60:.1f} min", flush=True)
        time.sleep(nap)


def fetch(run_id):
    jobs, page = [], 1
    while True:
        d = gh(f"repos/{REPO}/actions/runs/{run_id}/jobs?filter=all&per_page=100&page={page}")
        jobs += [{k: j.get(k) for k in KEEP} for j in d["jobs"]]
        if len(jobs) >= d["total_count"] or not d["jobs"]:
            return dict(run_id=run_id, jobs=jobs)
        page += 1


def main():
    rows = list(csv.DictReader(open(os.path.join(HERE, "gh_jobs_30d.csv"), encoding="utf-8")))
    runs = sorted({r["run_url"].rstrip("/").rsplit("/", 1)[1] for r in rows})
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding="utf-8"):
            try:
                done.add(str(json.loads(line)["run_id"]))
            except (ValueError, KeyError):
                pass
    todo = [r for r in runs if r not in done]
    print(f"runs {len(runs)} · already fetched {len(done)} · to fetch {len(todo)}", flush=True)
    errs = 0
    with open(OUT, "a", encoding="utf-8") as fo, ThreadPoolExecutor(4) as ex:
        for i in range(0, len(todo), 200):
            wait_rate()
            chunk = todo[i:i + 200]
            for rid, res in zip(chunk, ex.map(lambda x: _safe(x), chunk)):
                if isinstance(res, dict):
                    fo.write(json.dumps(res, separators=(",", ":")) + "\n")
                else:
                    errs += 1
                    print(f"run {rid}: {res}", flush=True)
            fo.flush()
            print(f"{min(i + 200, len(todo))}/{len(todo)} · errors {errs}", flush=True)
    print("done", flush=True)


def _safe(rid):
    try:
        return fetch(rid)
    except Exception as e:  # noqa: BLE001  (logged, retried on the next resumable run)
        return str(e)


if __name__ == "__main__":
    sys.exit(main())
