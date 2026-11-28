"""The ONE baseline data folder (an ETL export in P1 format) that every tab with 30-day / baseline numbers reads.

Used by build_report1130 (CI Baseline tab) and build_ops_tabs.stage_costs_30d (Optimal CI tab), so both show the
same window and the same totals. R1130_P1=<folder> wins; else P1_full (etl.py window, refreshed by refresh.ps1);
else the P1* folder whose window.json ends latest (widest range first on a tie).
"""
import csv
import datetime as _dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..")


def pick():
    if os.environ.get("R1130_P1"):
        return os.environ["R1130_P1"]
    if os.path.exists(os.path.join(OUT, "P1_full", "window.json")):
        return "P1_full"
    best = None
    for d in os.listdir(OUT):
        w = os.path.join(OUT, d, "window.json")
        if d.startswith("P1") and os.path.exists(w):
            try:
                x = json.load(open(w, encoding="utf-8"))
                k = (x["until"], "".join(chr(255 - ord(c)) for c in x.get("since", "")), d)  # latest end, then earliest start
            except (OSError, ValueError, KeyError):
                continue
            best = max(best, k) if best else k
    return best[2] if best else "P1_2026-10-17"


def folder():
    return os.path.join(OUT, pick())


def path(name, base=None):
    """an export file; new exports drop the fixed-window suffix (jobs_all.csv), older ones have it (jobs_all_30d.csv)"""
    base = base or folder()
    p = os.path.join(base, name)
    if os.path.exists(p):
        return p
    stem, ext = os.path.splitext(name)
    return os.path.join(base, f"{stem}_30d{ext}")


def data_range(base=None):
    """[since, until) of the baseline FROM THE DATA: first and last PR build / check-suite day (whole UTC days, until =
    day after the last one), not window.json (whose until can be tomorrow while the data stops today). CI Baseline and
    Optimal CI both use this, so a run at 00:00 UTC cannot give them different end days.
    R1130_SINCE / R1130_UNTIL (YYYY-MM-DD, until exclusive) narrow it on purpose."""
    base = base or folder()

    def rows(name):
        p = path(name, base)
        return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []
    ts = [r["build_created"] for r in rows("jobs_all.csv") if r.get("is_pr") == "1" and r.get("build_created")]
    ts += [r["suite_created"] for r in rows("gh_jobs.csv") if r.get("suite_created")]
    if ts:
        lo, hi = min(ts)[:10], max(ts)[:10]
        since = lo + "T00:00:00Z"
        until = (_dt.date.fromisoformat(hi) + _dt.timedelta(days=1)).isoformat() + "T00:00:00Z"
    else:   # empty export: the window the ETL wrote
        w = json.load(open(os.path.join(base, "window.json"), encoding="utf-8"))
        since, until = w["since"], w["until"]
    if os.environ.get("R1130_SINCE"):
        since = os.environ["R1130_SINCE"][:10] + "T00:00:00Z"
    if os.environ.get("R1130_UNTIL"):
        until = os.environ["R1130_UNTIL"][:10] + "T00:00:00Z"
    return since, until
