"""Daily release digest (expert review round 2, B / W3). Python stdlib only.

  python -X utf8 digest.py            # writes logs/digest-YYYY-MM-DD.md and prints it

Content: the verdict, the top blocker with its owner ROLE (no GitHub logins: decision D-5), PRs that must rebase,
red dev gates, the age of the oldest data source, and links into the page.
Sending it anywhere is OFF: only when OPS_DIGEST_URL is set (an ntfy topic or a webhook that takes a plain-text POST)
the text is posted there. Nothing else leaves this machine.
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP / "backend"))
import model  # noqa: E402

OPS_TABS = APP.parent / "plan-2026-11" / "outputs" / "cpu_tests" / "ops_tabs.json"
ROLE = {"assignee": "the PR assignee", "author": "the PR author", "codeowners": "CODEOWNERS of the publish workflow"}


def age_h(at):
    try:
        return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(str(at).replace("Z", "+00:00"))).total_seconds() / 3600
    except ValueError:
        return float("nan")


def main():
    con = sqlite3.connect(f"{(APP / 'data' / 'ops.db').resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    O = model.overview(con)
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    bl = [b for b in O.get("blockers") or [] if b.get("gating", True)]
    top = bl[0] if bl else None
    lines = [f"Release Desk digest {day} · line {O.get('line') if not isinstance(O.get('line'), dict) else O['line'].get('line')}",
             f"Status: {O.get('status')}" + (" · shipped" if O.get("shipped") else "") + f" · {(O.get('phase') or {}).get('en', '')}"]
    if top:
        own = (top.get("owner") or {}).get("how")
        dec = top.get("decided")
        lines.append(f"Top blocker: {top.get('title')}" + (" (data older than 48 h)" if top.get("stale") else ""))
        lines.append(f"  owner: {ROLE.get(own, 'not set')}" + (f" · decided: {dec['action']} {dec['at'][:10]}" if dec else " · no decision recorded"))
    else:
        lines.append("Top blocker: none")
    try:
        ov = (json.load(open(OPS_TABS, encoding="utf-8")).get("overlap") or {})
        rv = ov.get("review") or {}
        must = [x for x in (rv.get("queue") or []) + (rv.get("running") or []) if any(str(c.get("level", "")) in ("p0", "p1", "p2") for c in x.get("clash") or [])]
        oh = age_h(ov.get("at"))
        lines.append(("Rebase now: " + ", ".join(f"#{x['num']}" for x in must[:10])) if must and oh <= 24 else
                     ("Rebase now: none" if oh <= 24 else f"Rebase now: unknown (overlap data {oh / 24:.0f} d old)"))
    except (OSError, ValueError):
        lines.append("Rebase now: unknown (no overlap data)")
    red = [g for g in O.get("dev_gates") or [] if (g.get("last") or {}).get("state") == "failed"]
    if red:
        lines.append("Dev gates red: " + ", ".join(f"{g['slug']} (last build {age_h((g.get('last') or {}).get('created_at')) / 24:.0f} d ago)" for g in red[:8]))
    ages = sorted(((a.get("label", "").split(" (")[0], age_h(a.get("at"))) for a in O.get("ages") or []), key=lambda x: -x[1] if x[1] == x[1] else 0)
    if ages:
        lines.append(f"Oldest data source: {ages[0][0]} ({ages[0][1] / 24:.1f} d)")
    lines.append("Page: #now (verdict) · #obs/overlap (rebase) · #obs/coming (cockpit)")
    text = "\n".join(lines) + "\n"
    out = APP / "logs" / f"digest-{day}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    url = os.environ.get("OPS_DIGEST_URL")
    if url:
        try:
            urllib.request.urlopen(urllib.request.Request(url, data=text.encode("utf-8"), method="POST"), timeout=20)
            print("posted to OPS_DIGEST_URL")
        except OSError as e:
            print(f"digest post failed: {type(e).__name__}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
