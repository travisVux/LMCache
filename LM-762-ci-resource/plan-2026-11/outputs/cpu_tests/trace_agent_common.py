"""Shared helpers for the Trace Agent (release -> PRs -> fix proposals).

trace_agent_daily.py walks every release >= v0.5.7, checks each PR's CI, runs the
PR_FAILURE_TRACE_AGENT_PROMPT.md agent for PRs with failed checks, and writes:
  - outputs/trace_agent/proposals.json  (index, source of truth)
  - outputs/trace_agent/proposals.js    (live feed: the open page polls it and redraws the tracer)
report_model.py embeds ui_payload() into the page as RP.trace_agent (snapshot / gh-pages fallback).
"""
import json
import os
import re
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
PROMPT_MD = os.path.join(WORKSPACE, "knowledge", "prompts", "PR_FAILURE_TRACE_AGENT_PROMPT.md")
OUT_DIR = os.path.abspath(os.path.join(HERE, "..", "trace_agent"))
INDEX = os.path.join(OUT_DIR, "proposals.json")
LIVE_JS = os.path.join(OUT_DIR, "proposals.js")

# Policy: from this release line on, every fix proposal shown in the UI must come from the Trace Agent.
MIN_VERSION = (0, 5, 7)
REPORT_CAP = 16000  # chars of each full markdown report embedded in the page


def version_tuple(tag):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def in_scope(tag):
    """True for v0.5.7rc1 .. v0.5.7 and every later release (rc tags count as their release line)."""
    v = version_tuple(tag)
    return v is not None and v >= MIN_VERSION


def pr_key(tag, num):
    return f"{tag}::{num}"


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_index():
    try:
        idx = json.load(open(INDEX, encoding="utf-8"))
    except (OSError, ValueError):
        idx = {}
    if idx.get("version") != 2:  # v1 was gate-based; start over (old reports stay on disk)
        idx = dict(version=2, updated_at="", releases={}, prs={}, runs=idx.get("runs", []))
    return idx


def ui_payload(idx=None):
    """What the page needs: per-release summary + per-PR checks and proposal (with report text)."""
    idx = idx or load_index()
    prs = {}
    for k, r in idx.get("prs", {}).items():
        x = {f: r.get(f) for f in ("tag", "num", "checks", "checked_at", "check_error")}
        p = r.get("proposal")
        if p:
            p = dict(p)
            rp = p.get("report")
            try:
                p["report_text"] = open(os.path.join(OUT_DIR, rp), encoding="utf-8").read()[:REPORT_CAP] if rp else ""
            except OSError:
                p["report_text"] = ""
            p["ok"] = p.get("status") == "ok" and bool(p.get("fix"))
            p["stale"] = p.get("sig") != r.get("sig")
        x["proposal"] = p
        prs[k] = x
    return dict(updated_at=idx.get("updated_at", ""), min_version=list(MIN_VERSION),
                releases=idx.get("releases", {}), prs=prs)


def save_index(idx):
    """Persist the index and refresh the live feed the open page polls."""
    os.makedirs(OUT_DIR, exist_ok=True)
    idx["updated_at"] = now_iso()
    for path, text in ((INDEX, json.dumps(idx, ensure_ascii=False, indent=1)),
                       (LIVE_JS, "window.onTraceAgent&&window.onTraceAgent(" +
                        json.dumps(ui_payload(idx), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ");\n")):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
