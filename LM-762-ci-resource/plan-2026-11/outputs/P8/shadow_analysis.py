#!/usr/bin/env python3
"""Run ci_rule_shadow on (a) last 100 merged PRs and (b) every PR in P1's 30-day MP job table.
Join with P1 GPU-minutes and list failed MP jobs the rule would NOT have run.
Read-only: uses `gh` and local CSVs. Writes into outputs/P8/ only.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ci_rule_shadow as rs  # noqa: E402

P1 = os.path.join(HERE, "..", "P1", "jobs_all_30d.csv")
RAW = os.path.join(HERE, "raw")
CACHE = os.path.join(RAW, "prs")
os.makedirs(CACHE, exist_ok=True)
INFRA_EXIT = {"128", "2", "-1", "255"}  # P2 b1: checkout / setup-env / agent lost


def pr_info(n: int) -> dict:
    p = os.path.join(CACHE, f"{n}.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    out = subprocess.run(["gh", "pr", "view", str(n), "-R", "LMCache/LMCache", "--json",
                          "number,title,state,labels,files,changedFiles,mergedAt"],
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        d = {"number": n, "error": out.stderr.strip()[:200], "files": [], "labels": []}
    else:
        d = json.loads(out.stdout)
        files = [f["path"] for f in d.get("files", [])]
        if d.get("changedFiles", 0) > len(files):
            o2 = subprocess.run(["gh", "api", "--paginate", f"repos/LMCache/LMCache/pulls/{n}/files?per_page=100",
                                 "--jq", ".[].filename"], capture_output=True, text=True, encoding="utf-8")
            files = [x for x in o2.stdout.splitlines() if x.strip()]
        d["files"] = files
        d["labels"] = [lb["name"] for lb in d.get("labels", [])]
    json.dump(d, open(p, "w", encoding="utf-8"))
    return d


def job_covered(row: dict, wls: list[str]) -> str:
    """'yes' if the rule still runs this job's workload (same engine), 'proxy' for layout stand-in."""
    if wls == ["ALL"]:
        return "yes"
    wl, eng = row["workload"], row["engine"]
    for w in wls:
        name, _, weng = w.partition("@")
        if name == wl and (not weng or weng == eng):
            return "yes"
    if wl in ("dsv4_flash_tp", "kimi_linear_tp") and "hma_dsv4_correctness" in wls:
        return "proxy(layout_smoke)"
    return "no"


def main() -> None:
    rows = list(csv.DictReader(open(P1, encoding="utf-8")))
    pr_rows = collections.defaultdict(list)
    for r in rows:
        if r["is_pr"] == "1" and r["pr"]:
            pr_rows[int(r["pr"])].append(r)

    merged = json.load(open(os.path.join(RAW, "merged100.json"), encoding="utf-8"))
    merged_nums = [p["number"] for p in merged]
    all_nums = sorted(set(merged_nums) | set(pr_rows))
    print(f"fetching {len(all_nums)} PRs (cached in raw/prs)", file=sys.stderr)

    out_rows, fail_rows = [], []
    for n in all_nums:
        info = pr_info(n)
        files, labels = info.get("files", []), info.get("labels", [])
        res = rs.classify(files, labels, n)
        builds = collections.defaultdict(float)
        for r in pr_rows.get(n, []):
            builds[r["build_number"]] += float(r["gpu_min"] or 0)
        ran = {b: g for b, g in builds.items() if g > 0}
        actual = sum(ran.values())
        if "full" in res.required_tiers:
            rule = actual
        else:
            rule = sum(min(g, res.est_gpu_min_per_build) for g in ran.values())
        out_rows.append({
            "pr": n, "in_merged100": n in merged_nums, "in_p1": n in pr_rows,
            "state": info.get("state", "?"), "title": (info.get("title") or "")[:80],
            "labels": ";".join(labels), "n_files": len(files),
            "classes": ";".join(res.classes), "required_tiers": ";".join(res.required_tiers),
            "mp_workloads": ";".join(res.mp_workloads), "is_full": "full" in res.required_tiers,
            "est_rule_gpu_min_per_build": res.est_gpu_min_per_build,
            "mp_builds_with_gpu": len(ran), "actual_gpu_min_30d": round(actual, 2),
            "rule_gpu_min_30d": round(rule, 2), "saved_gpu_min_30d": round(actual - rule, 2),
            "skip_expensive_label": "skip expensive ci" in labels, "error": info.get("error", ""),
        })
        # failed MP jobs on this PR: would the rule still have run them?
        for r in pr_rows.get(n, []):
            if r["state"] != "failed" or r["soft_failed"] == "True":
                continue
            cov = job_covered(r, res.mp_workloads)
            fail_rows.append({
                "pr": n, "build": r["build_number"], "label": r["label"], "workload": r["workload"],
                "engine": r["engine"], "exit": r["exit_status"], "retried": r["retried"],
                "infra_exit": r["exit_status"] in INFRA_EXIT, "rule_runs_it": cov,
                "classes": ";".join(res.classes),
            })

    with open(os.path.join(HERE, "shadow_per_pr.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)
    with open(os.path.join(HERE, "shadow_failed_jobs.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fail_rows[0]))
        w.writeheader()
        w.writerows(fail_rows)
    print(f"wrote shadow_per_pr.csv ({len(out_rows)}) and shadow_failed_jobs.csv ({len(fail_rows)})",
          file=sys.stderr)


if __name__ == "__main__":
    main()
