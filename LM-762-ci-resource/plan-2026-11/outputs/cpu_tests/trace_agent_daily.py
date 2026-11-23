"""Daily Trace Agent: release -> PRs -> fix proposals, written straight into the UI.

For every release >= v0.5.7 (rc tags included), in tracer order:
  1. for each PR of the release: `gh pr checks` (cheap, no agent);
  2. a PR with failed checks becomes a case: knowledge/prompts/PR_FAILURE_TRACE_AGENT_PROMPT.md is filled
     with {{PR_OR_BUILD}} = that PR and run headless with `claude -p` (read-only tools);
  3. after every PR the index is saved and outputs/trace_agent/proposals.js is rewritten. The open
     06_PR_TO_CI_VISUAL.html polls that file every 30 s and redraws the tracer: no rebuild needed.
At the end the page is rebuilt once so the embedded snapshot (gh-pages fallback) is current.

Usage (from the CacheAgent root):
  python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/trace_agent_daily.py          # daily run
  ... --list                          # releases, PRs and their state; runs nothing
  ... --tag v0.5.7rc4 [--pr 6208]     # limit to a release / PR (repeatable)
  ... --checks-only                   # refresh CI checks only, no agent
  ... --force                         # re-trace failing PRs even if their proposal is fresh
  ... --no-build                      # skip the final build_page.py + verify_page.py
A failing PR is (re)traced when it is new, its failed checks changed, the last run failed,
or the proposal is older than --max-age-hours (default 168 = weekly; checks are refreshed daily).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_model  # noqa: E402
import trace_agent_common as C  # noqa: E402

HERE = C.HERE
LMCACHE = report_model.REPO
REPO = "LMCache/LMCache"

ALLOWED = [
    "Read", "Grep", "Glob",
    "Bash(gh pr view:*)", "Bash(gh pr checks:*)", "Bash(gh pr diff:*)", "Bash(gh pr list:*)",
    "Bash(gh run view:*)", "Bash(gh run list:*)", "Bash(gh api:*)", "Bash(gh search:*)", "Bash(gh release view:*)",
    "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)", "Bash(git blame:*)", "Bash(git rev-parse:*)",
    "Bash(git merge-base:*)", "Bash(git branch:*)", "Bash(git tag:*)",
    "Bash(grep:*)", "Bash(sed -n:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(sort:*)", "Bash(uniq:*)",
    "Bash(cut:*)", "Bash(base64 -d:*)", "Bash(jq:*)",
    "mcp__buildkite",
]
DENIED = [
    "Edit", "Write", "NotebookEdit", "WebFetch",
    "Bash(gh run rerun:*)", "Bash(gh run cancel:*)", "Bash(gh pr comment:*)", "Bash(gh pr edit:*)", "Bash(gh pr merge:*)",
    "Bash(gh pr close:*)", "Bash(gh pr review:*)", "Bash(gh issue:*)", "Bash(gh api -X:*)", "Bash(gh api --method:*)",
    "Bash(git push:*)", "Bash(git commit:*)", "Bash(git checkout:*)", "Bash(git reset:*)", "Bash(git fetch:*)",
    "Bash(git pull:*)", "Bash(git stash:*)", "Bash(git clean:*)", "Bash(rm:*)",
]

CONTRACT = r"""

---

## Unattended run notes (added by trace_agent_daily.py)

- This run is **unattended and read-only**. Edit/Write tools are disabled. `gh api` is **GET only**: never use `-X`, `--method`, `-f`, `-F`, `--input`.
  Do not fetch/checkout in the local LMCache clone; use `gh api .../contents/<path>?ref=<sha>` to read files at another commit.
- The local LMCache clone is the working directory. Quote only key log lines.
- Hard rule 3 still applies: finish your own trace before you look for an existing fix PR.
- The PR is already merged into the release below. Say whether its failed checks matter for the release
  (real bug shipped, `dev` red, or only infra/flaky noise on the PR).
- The "Context" block is **input to verify, not evidence**.

## Context from the release tracer

{context}

## Machine-readable summary (required)

After the report, end your answer with exactly one fenced ```json block, with this shape (both languages required):

```json
{{"class": "infra | pr-bug | dev-red | env-dependent | flaky | unknown",
 "release_impact": "blocks-release | shipped-bug | none",
 "root_cause": {{"en": "one sentence", "vi": "một câu"}},
 "fix": {{"en": "the recommended fix in 1-2 sentences", "vi": "hướng fix đề xuất, 1-2 câu"}},
 "option": "R | A | B | C | D | Q",
 "fix_pr": null,
 "fix_status": "merged | open | none",
 "confidence": "high | medium | low",
 "failing_tests": ["tests/... path or check name"],
 "repro": "single shell command to reproduce locally, or empty",
 "guard": {{"en": "prevention (option G)", "vi": "phòng lặp lại (G)"}},
 "unverified": ["claims you could not verify"]}}
```
`fix_pr` is the PR number (integer) of an existing fix, else null.
"""


def find_claude():
    for c in (os.environ.get("CLAUDE_BIN"), shutil.which("claude"),
              os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe"),
              os.path.join(os.path.expanduser("~"), ".local", "bin", "claude")):
        if c and os.path.isfile(c):
            return c
    sys.exit("claude CLI not found: set CLAUDE_BIN")


def prompt_body():
    text = open(C.PROMPT_MD, encoding="utf-8").read()
    parts = re.split(r"\n---\n", text, maxsplit=1)  # the file says: paste everything below the line
    return parts[1] if len(parts) == 2 else text


def pr_checks(num):
    """CI checks of a PR's head commit: pass/fail/pending counts + failed checks with links."""
    p = subprocess.run(["gh", "pr", "checks", str(num), "-R", REPO, "--json", "name,state,bucket,link,workflow"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    try:
        rows = json.loads(p.stdout or "[]")  # gh exits non-zero when checks fail; stdout still has the JSON
    except ValueError:
        return None, (p.stderr or p.stdout or "gh pr checks failed").strip()[-200:]
    b = lambda k: [r for r in rows if r.get("bucket") == k]  # noqa: E731
    fail = [dict(name=r.get("name", ""), link=r.get("link", ""), workflow=r.get("workflow", "")) for r in b("fail")]
    return dict(total=len(rows), passed=len(b("pass")), failed=len(fail), pending=len(b("pending")),
                cancelled=len(b("cancel")), fail=sorted(fail, key=lambda x: x["name"])[:20]), ""


def fail_sig(checks):
    blob = json.dumps([(f["name"], f["link"]) for f in checks.get("fail", [])])
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def build_prompt(rel, pr, checks):
    ref = f"PR #{pr['num']} — https://github.com/{REPO}/pull/{pr['num']} (merged into release {rel['tag']})"
    gates = [g for g in rel["gates"] if g.get("log_id") == pr.get("log_id")]
    log = rel["logs"].get(pr.get("log_id")) or {}
    fails = "\n".join(f"| {f['name']} | {f['workflow']} | {f['link']} |" for f in checks["fail"]) or "| — | | |"
    ctx = "\n".join([
        f"- Release: **{rel['tag']}** (status `{rel['status']}`, {rel.get('badge', '')}); focus: {rel['focus'][0]}",
        f"- PR: **#{pr['num']}** `{pr.get('sha', '')}` · area `{pr.get('area', '')}` · {pr.get('title', '')}",
        f"- Files (from git): {', '.join(pr.get('files') or []) or '—'}",
        f"- Checks on the PR head: {checks['passed']} passed, {checks['failed']} failed, {checks['pending']} pending, {checks['cancelled']} cancelled",
        "", "| Failed check | Workflow | Link |", "|---|---|---|", fails, "",
        "- Release gates the tracer links to this PR (a hint, may be wrong): " +
        ("; ".join(f"`{g['name']}` ({g['status']})" for g in gates) or "none"),
        f"- Tracer log title for that link: {log.get('title', '—')}",
        f"- Local LMCache clone: `{LMCACHE}`",
    ])
    return prompt_body().replace("{{PR_OR_BUILD}}", ref) + CONTRACT.format(context=ctx)


def parse_summary(text):
    for b in reversed(re.findall(r"```json\s*(\{.*?\})\s*```", text or "", re.S)):
        try:
            return json.loads(b)
        except ValueError:
            continue
    return None


def pair(v):
    if isinstance(v, dict):
        return [str(v.get("en", "")), str(v.get("vi", "") or v.get("en", ""))]
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return [str(v[0]), str(v[1])]
    return [str(v or ""), str(v or "")]


def run_agent(rel, pr, checks, sig, claude, a, log):
    prompt = build_prompt(rel, pr, checks)
    t0 = time.time()
    cmd = [claude, "-p", "--output-format", "json", "--max-budget-usd", str(a.budget),
           "--allowedTools", *ALLOWED, "--disallowedTools", *DENIED]
    if a.model:
        cmd += ["--model", a.model]
    e = dict(sig=sig, run_at=C.now_iso(), model=a.model or "default")
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=LMCACHE, timeout=a.timeout * 60)
        res = json.loads(p.stdout) if p.stdout.strip().startswith("{") else dict(is_error=True, result=p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        res = dict(is_error=True, result=f"timeout after {a.timeout} min")
    except (OSError, ValueError) as ex:
        res = dict(is_error=True, result=f"{type(ex).__name__}: {ex}")
    text = res.get("result") or ""
    e.update(secs=round(time.time() - t0), cost_usd=res.get("total_cost_usd"), turns=res.get("num_turns"),
             session_id=res.get("session_id", ""))
    day = datetime.now().strftime("%Y-%m-%d")
    fname = f"{rel['tag']}__pr{pr['num']}.md"
    day_dir = os.path.join(C.OUT_DIR, day)
    os.makedirs(day_dir, exist_ok=True)
    head = (f"<!-- trace_agent_daily · {e['run_at']} · {e['model']} · sig {sig} · cost ${e['cost_usd']} · {e['secs']}s -->\n"
            f"# Trace Agent — {rel['tag']} · PR #{pr['num']}\n\n")
    open(os.path.join(day_dir, fname), "w", encoding="utf-8").write(head + text)
    open(os.path.join(day_dir, fname[:-3] + ".prompt.md"), "w", encoding="utf-8").write(prompt)
    e["report"] = f"{day}/{fname}"
    s = None if res.get("is_error") else parse_summary(text)
    if s:
        fpr = s.get("fix_pr")
        e.update(status="ok", cls=str(s.get("class", "unknown")), impact=str(s.get("release_impact", "")),
                 root_cause=pair(s.get("root_cause")), fix=pair(s.get("fix")), guard=pair(s.get("guard")),
                 option=str(s.get("option", "")), fix_pr=fpr if isinstance(fpr, int) else None,
                 fix_status=str(s.get("fix_status", "")), confidence=str(s.get("confidence", "")),
                 failing_tests=[str(x) for x in (s.get("failing_tests") or [])][:10],
                 repro=str(s.get("repro", "")), unverified=[str(x) for x in (s.get("unverified") or [])][:12])
    else:
        e.update(status="error", error=(text or "no output")[-400:])
    log(f"      agent {e['status']}  {e['secs']}s  ${e['cost_usd']}  -> {e['report']}")
    return e


def age_hours(iso):
    try:
        return (datetime.now().astimezone() - datetime.fromisoformat(iso)).total_seconds() / 3600
    except (TypeError, ValueError):
        return 1e9


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--tag", action="append")
    ap.add_argument("--pr", action="append", type=int)
    ap.add_argument("--checks-only", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-age-hours", type=float, default=168)
    ap.add_argument("--model", default=os.environ.get("TRACE_AGENT_MODEL", ""))
    ap.add_argument("--budget", type=float, default=float(os.environ.get("TRACE_AGENT_BUDGET_USD", "3")), help="USD cap per PR")
    ap.add_argument("--budget-total", type=float, default=float(os.environ.get("TRACE_AGENT_BUDGET_TOTAL_USD", "20")),
                    help="stop starting new agent runs after this much spend in one run")
    ap.add_argument("--timeout", type=int, default=25, help="minutes per PR")
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()

    os.makedirs(C.OUT_DIR, exist_ok=True)
    logf = open(os.path.join(C.OUT_DIR, "run.log"), "a", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
        logf.flush()

    idx = C.load_index()
    rels = [r for r in report_model.build_release_trace() if C.in_scope(r["tag"]) and (not a.tag or r["tag"] in a.tag)]
    if a.list:
        for rel in rels:
            log(f"{rel['tag']}  ({len(rel['prs'])} PRs in tracer, {rel['total_prs']} in release)")
            for pr in rel["prs"]:
                r = idx["prs"].get(C.pr_key(rel["tag"], pr["num"])) or {}
                ck, pp = r.get("checks") or {}, r.get("proposal") or {}
                log(f"   #{pr['num']:<5} checks={'—' if not ck else str(ck.get('failed')) + ' failed/' + str(ck.get('total'))}"
                    f"  proposal={pp.get('status', '—')} {pp.get('run_at', '')[:16]}")
        return 0

    claude, spent, run = None, 0.0, dict(at=C.now_iso(), traced=[], cost_usd=0.0)
    log(f"trace_agent_daily: {len(rels)} release(s) >= v{'.'.join(map(str, C.MIN_VERSION))}")
    for rel in rels:
        tag = rel["tag"]
        log(f"- {tag}: {len(rel['prs'])} PRs")
        for pr in rel["prs"]:
            if a.pr and pr["num"] not in a.pr:
                continue
            key = C.pr_key(tag, pr["num"])
            rec = idx["prs"].setdefault(key, dict(tag=tag, num=pr["num"]))
            checks, err = pr_checks(pr["num"])
            rec.update(title=pr.get("title", ""), checked_at=C.now_iso(), check_error=err)
            if checks is None:
                log(f"   #{pr['num']}: gh pr checks error: {err}")
                C.save_index(idx)
                continue
            rec["checks"], rec["sig"] = checks, fail_sig(checks)
            C.save_index(idx)  # live: checks show up in the UI right away
            if not checks["failed"]:
                log(f"   #{pr['num']}: CI green ({checks['passed']}/{checks['total']})")
                continue
            old = rec.get("proposal")
            why = ("forced" if a.force else "new" if not old else "checks changed" if old.get("sig") != rec["sig"]
                   else "retry" if old.get("status") != "ok"
                   else f"refresh ({age_hours(old.get('run_at')):.0f}h)" if age_hours(old.get("run_at")) >= a.max_age_hours else None)
            log(f"   #{pr['num']}: {checks['failed']} failed check(s) -> {why or 'proposal fresh, skip'}")
            if not why or a.checks_only:
                continue
            if spent >= a.budget_total:
                log(f"      skip: run budget ${a.budget_total} reached")
                continue
            claude = claude or find_claude()
            rec["proposal"] = run_agent(rel, pr, checks, rec["sig"], claude, a, log)
            spent += rec["proposal"].get("cost_usd") or 0
            run["traced"].append(dict(key=key, status=rec["proposal"]["status"]))
            C.save_index(idx)  # live: proposal shows up in the UI right away
        # per-release summary for the tracer header
        recs = [idx["prs"].get(C.pr_key(tag, p["num"])) or {} for p in rel["prs"]]
        idx["releases"][tag] = dict(
            last_run=C.now_iso(), prs=len(rel["prs"]),
            checked=sum(1 for r in recs if r.get("checks")),
            failing=sum(1 for r in recs if (r.get("checks") or {}).get("failed")),
            proposed=sum(1 for r in recs if (r.get("proposal") or {}).get("status") == "ok"))
        C.save_index(idx)
    run["cost_usd"] = round(spent, 2)
    idx.setdefault("runs", []).append(run)
    idx["runs"] = idx["runs"][-60:]
    C.save_index(idx)
    log(f"done: traced {len(run['traced'])} PR(s), cost ${spent:.2f}")
    if not a.no_build:
        for s in ("build_page.py", "verify_page.py"):
            r = subprocess.run([sys.executable, "-I", "-X", "utf8", os.path.join(HERE, s)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            tail = (r.stdout or "").strip().splitlines()[-1:] or [r.stderr.strip()[-300:]]
            log(f"{s}: exit {r.returncode} {tail[0] if tail else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
