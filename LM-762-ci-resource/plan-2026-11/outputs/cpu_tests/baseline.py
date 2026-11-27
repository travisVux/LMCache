"""The ONE baseline data folder (an ETL export in P1 format) that every tab with 30-day / baseline numbers reads.

Used by build_report1130 (CI Baseline tab) and build_ops_tabs.stage_costs_30d (Optimal CI tab), so both show the
same window and the same totals. R1130_P1=<folder> wins; else P1_full (etl.py window, refreshed by refresh.ps1);
else the P1* folder whose window.json ends latest (widest range first on a tie).
"""
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
