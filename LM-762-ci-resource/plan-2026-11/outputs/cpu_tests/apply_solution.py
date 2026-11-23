"""Register an Optimal CI solution as applied, and freeze its baseline (local run).

  python -I -X utf8 apply_solution.py "<solution id>" [--date YYYY-MM-DD] [--ref "PR #1234"] [--note "..."]
  python -I -X utf8 apply_solution.py --list            # ids, metric and current value
  python -I -X utf8 apply_solution.py --undo "<id>"

The page's "Apply" button shows the exact command. The baseline is the solution's metric value in ops_tabs.json
right now (the last build). From the next builds on, the page shows before (baseline) -> after (days after the date).
Keep the collectors running daily (observe_collect.py, observe_ops_collect.py, the daily report) so "after" has data.
"""
import argparse
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "ops_tabs.json")
SOL = os.path.join(HERE, "optimal_solutions.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id", nargs="?")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--ref", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--undo")
    a = ap.parse_args()
    acts = ((json.load(open(DATA, encoding="utf-8")).get("opt") or {}).get("v3") or {}).get("actions") or []
    sols = json.load(open(SOL, encoding="utf-8")) if os.path.exists(SOL) else []
    if a.list:
        for x in acts:
            r = x.get("result") or {}
            print(f"{x['id']:<48} {str(r.get('now')):>10} {r.get('unit') or ''}  {((r.get('metric') or ['-'])[0])}")
        return 0
    if a.undo:
        sols = [s for s in sols if s.get("id") != a.undo]
        json.dump(sols, open(SOL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("removed", a.undo)
        return 0
    x = next((x for x in acts if x["id"] == a.id), None)
    if not x:
        print("unknown id; use --list", file=sys.stderr)
        return 1
    r = x.get("result") or {}
    if r.get("now") is None:
        print("note: this solution has no measured value yet; before -> after starts when data exists")
    entry = dict(id=x["id"], title=x["title"][0], applied=a.date, baseline=r.get("now"), unit=r.get("unit"),
                 metric=(r.get("metric") or [""])[0], ref=a.ref, note=a.note)
    sols = [s for s in sols if s.get("id") != x["id"]] + [entry]
    json.dump(sols, open(SOL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"applied {x['id']} on {a.date}; baseline {entry['baseline']} {entry['unit'] or ''} ({entry['metric']})")
    print("rebuild the page: python -I -X utf8 build_ops_tabs.py  (then build_i18n.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
