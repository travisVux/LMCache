"""Trace Agent for the 3 extra directions (tabs #obs/flaky, #obs/gpuload, #obs/bug).

Same engine as trace_agent_daily.py (headless `claude -p`, read-only tools, cost cap), different prompt per direction:
  flaky   knowledge/prompts/TRACE_FLAKY_AGENT_PROMPT.md     context = top flaky workloads + example builds
  gpuload knowledge/prompts/TRACE_GPU_LOAD_AGENT_PROMPT.md  context = GPU-h per workload, waste, levers
  bug     knowledge/prompts/TRACE_BUG_AGENT_PROMPT.md       target = trace_dirs_model.BUG_TARGET (#6530)
  rebase  knowledge/prompts/TRACE_REBASE_REVIEW_AGENT_PROMPT.md  context = #obs/overlap section A (merges of 24 h vs open PRs)
          -> final decision per merged PR + per open PR, shown in the Rebase risk tab (read by build_ops_tabs.py)

Each run writes ../trace_agent/directions/<dir>.json (+ the full report under ../trace_agent/<day>/),
then refreshes ../trace_agent/directions.js, which the open page polls every 30 s.

Usage (from the CacheAgent root):
  python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/trace_agent_dirs.py            # all 3, only when due
  ... --dir flaky [--dir bug]   # limit to some directions
  ... --data-only               # refresh the tab data (no agent, no cost)
  ... --force                   # run even when the last result is fresh
  ... --bug 6531                # trace another issue / PR number this run
A direction is due when it has no result, its input data changed, the last run failed, or the result is
older than --max-age-hours (default 168). `bug` is skipped (no cost) while the number does not exist yet.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trace_agent_common as C  # noqa: E402
import trace_agent_daily as D  # noqa: E402  (find_claude, ALLOWED, DENIED, parse_summary, pair)
import trace_dirs_model as M  # noqa: E402

PROMPTS = os.path.join(C.WORKSPACE, "knowledge", "prompts")
PROMPT = dict(flaky="TRACE_FLAKY_AGENT_PROMPT.md", gpuload="TRACE_GPU_LOAD_AGENT_PROMPT.md", bug="TRACE_BUG_AGENT_PROMPT.md",
              rebase="TRACE_REBASE_REVIEW_AGENT_PROMPT.md")
OPS_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops_tabs.json")


def rebase_rows():
    """Section A of the Rebase risk tab: merged PRs that touch open PRs, with the open PR's state and clash."""
    try:
        o = json.load(open(OPS_JSON, encoding="utf-8"))["overlap"]
    except (OSError, ValueError, KeyError):
        return None, []
    rv = o.get("review") or {}
    info = {x["num"]: dict(x, state="ci running") for x in rv.get("running") or []}
    info.update({x["num"]: dict(x, state="ready for review") for x in rv.get("queue") or []})
    rows = [m for m in rv.get("by_merged") or [] if m.get("ready") or m.get("running")]
    return dict(at=o.get("snap_at"), w0=o.get("w0"), w1=o.get("at"), info=info), rows
DIRS = list(PROMPT)


def body(name):
    text = open(os.path.join(PROMPTS, name), encoding="utf-8").read()
    parts = re.split(r"\n---\n", text, maxsplit=1)
    return parts[1] if len(parts) == 2 else text


def context(d, key):
    if key == "rebase":
        meta, rows = rebase_rows()
        if not rows:
            return "- No merge of the last 24 h touches an open PR."
        L = [f"- Window: merges into dev {meta['w0']} .. {meta['w1']}; PR snapshot {meta['at']}", f"- Local LMCache clone: `{D.LMCACHE}`", ""]
        for m in rows:
            L.append(f"### Merged #{m['num']} — {m['title']} (post-merge CI: {m.get('ci')})")
            for r in (m.get("ready") or []) + (m.get("running") or []):
                x = meta["info"].get(r["num"]) or {}
                why = next((c.get("same") or ["", ""] for c in x.get("clash") or [] if c.get("m") == m["num"]), ["", ""])[0]
                runs = ", ".join(f"{b['pipe']} {b['url']}" for b in x.get("runs") or [])
                L.append(f"- open #{r['num']} {x.get('title', '')} | {x.get('state')} | level {r['level'].upper()} | rule action {r['verb']} | "
                         f"gates {x.get('gates')} | review {x.get('review')} | diff check: {why}" + (f" | running: {runs}" if runs else ""))
            L.append("")
        return "\n".join(L)
    w = d["window"]
    head = f"- Data window: {w['start']}..{w['end']}, pipeline `{w['pipeline']}`, {w['builds']} builds (cache, may be days old)\n" \
           f"- Local LMCache clone: `{D.LMCACHE}`\n"
    if key == "flaky":
        f = d["flaky"]
        t = f["totals"]
        lines = [head, f"- {t['flaky']} of {t['first_fail']} first-try job failures passed on retry; retries used {t['retry_gpu_h']} GPU-h;"
                 f" {t['test_kind']} had test exit codes (1/2), {t['infra_kind']} infra codes (128/255/-1/100)",
                 f"- GHA Test: {f['gha']['rerun_success']} runs passed only on attempt >= 2 ({f['gha']['start']}..{f['gha']['end']})", "",
                 "| Workload | GPUs | Runs | Flaky | Still failed | Retry GPU-h | Exit codes | Example builds |", "|---|---|---|---|---|---|---|---|"]
        for x in f["workloads"][:6]:
            ex = ", ".join(f"[{e['build']}]({e['url']}) PR {e['pr'] or '—'} exit {e['exit']}" for e in x["examples"])
            lines.append(f"| {x['workload']} | {x['gpus']} | {x['runs']} | {x['flaky']} | {x['still_fail']} | {x['retry_gpu_h']} | "
                         f"{x['exits']} | {ex} |")
        lines += ["", "Same commit, one build failed and another passed:"] + \
                 [f"- {x['sha']} PR {x['pr']}: " + ", ".join(f"[{b['n']}]({b['url']}) {b['state']}" for b in x["builds"]) for x in f["flips"]]
        return "\n".join(lines)
    if key == "gpuload":
        g = d["gpuload"]
        m = g["merge"]
        lines = [head, f"- Total {g['total_gpu_h']} GPU-h in the window; by build outcome: {g['by_state_h']}",
                 f"- Passed PR build p50: {g['pr_build_p50_gpu_h']} GPU-h; queue wait p50/p90 {m['queue_p50_min']}/{m['queue_p90_min']} min;"
                 f" passed PR build duration p50/p90 {m['passed_dur_p50_min']}/{m['passed_dur_p90_min']} min", "",
                 "| Workload | GPUs | GPU-h | Share | GPU-min / PR build | First-try fail % | Retry GPU-h |", "|---|---|---|---|---|---|---|"]
        for x in g["workloads"][:10]:
            lines.append(f"| {x['workload']} | {x['gpus']} | {x['gpu_h']} | {x['share'] * 100:.1f}% | {x['per_pr_build_min']} | "
                         f"{x['first_try_fail_pct']} | {x['retry_gpu_h']} |")
        lines += ["", "Levers from the tab (verify each):"] + \
                 [f"- {x['en']} — {x['gpu_h'] if x['gpu_h'] is not None else '?'} GPU-h ({x['basis']}, {x['ticket']}); {x['note_en']}" for x in g["levers"]]
        return "\n".join(lines)
    b = d["bug"]
    it = b.get("item") or {}
    return "\n".join([f"- Target: {b['target']['repo']}#{b['target']['number']} ({'PR' if it.get('is_pr') else 'issue'}), "
                      f"state {it.get('state')}, by {it.get('user')}, labels {it.get('labels')}",
                      f"- Title: {it.get('title')}", f"- Local LMCache clone: `{D.LMCACHE}`", "", "Body (first 1500 chars):", "",
                      "```", it.get("body") or "", "```"])


def sig(d, key):
    if key == "rebase":
        meta, rows = rebase_rows()
        part = [(m["num"], sorted((r["num"], r["level"], r["verb"]) for r in (m.get("ready") or []) + (m.get("running") or []))) for m in rows]
        return hashlib.sha1(json.dumps(part, sort_keys=True).encode()).hexdigest()[:12]
    part = {"flaky": d["flaky"]["workloads"][:6], "gpuload": d["gpuload"]["workloads"][:10],
            "bug": [d["bug"].get("item"), d["bug"]["target"]]}[key]
    return hashlib.sha1(json.dumps([d["window"], part], sort_keys=True, default=str).encode()).hexdigest()[:12]


def run(d, key, claude, a, log):
    tgt = d["bug"]["target"]
    prompt = body(PROMPT[key]).replace("{{CONTEXT}}", context(d, key)).replace(
        "{{TARGET}}", f"{tgt['repo']}#{tgt['number']} — https://github.com/{tgt['repo']}/issues/{tgt['number']}")
    cmd = [claude, "-p", "--output-format", "json", "--max-budget-usd", str(a.budget),
           "--allowedTools", *D.ALLOWED, "--disallowedTools", *D.DENIED]
    if a.model:
        cmd += ["--model", a.model]
    e = dict(dir=key, sig=sig(d, key), run_at=C.now_iso(), model=a.model or "default")
    t0 = time.time()
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=D.LMCACHE, timeout=a.timeout * 60)
        res = json.loads(p.stdout) if p.stdout.strip().startswith("{") else dict(is_error=True, result=p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        res = dict(is_error=True, result=f"timeout after {a.timeout} min")
    except (OSError, ValueError) as ex:
        res = dict(is_error=True, result=f"{type(ex).__name__}: {ex}")
    text = res.get("result") or ""
    e.update(secs=round(time.time() - t0), cost_usd=res.get("total_cost_usd"), turns=res.get("num_turns"))
    day = datetime.now().strftime("%Y-%m-%d")
    fname = f"dir_{key}" + (f"__{tgt['number']}" if key == "bug" else "") + ".md"
    os.makedirs(os.path.join(C.OUT_DIR, day), exist_ok=True)
    open(os.path.join(C.OUT_DIR, day, fname), "w", encoding="utf-8").write(
        f"<!-- trace_agent_dirs · {e['run_at']} · {e['model']} · cost ${e['cost_usd']} · {e['secs']}s -->\n"
        f"# Trace Agent — direction {key}\n\n" + text)
    open(os.path.join(C.OUT_DIR, day, fname[:-3] + ".prompt.md"), "w", encoding="utf-8").write(prompt)
    e["report"] = f"{day}/{fname}"
    e["report_text"] = text[:C.REPORT_CAP]
    s = None if res.get("is_error") else D.parse_summary(text)
    if s:
        e["status"] = "ok"
        if key == "bug":
            e.update(cls=str(s.get("class", "")), impact=str(s.get("release_impact", "")), root_cause=D.pair(s.get("root_cause")),
                     fix=D.pair(s.get("fix")), fix_pr=s.get("fix_pr") if isinstance(s.get("fix_pr"), int) else None,
                     first_error=str(s.get("first_error", "")), where=str(s.get("where", "")), repro=str(s.get("repro", "")),
                     confidence=str(s.get("confidence", "")), target=tgt["number"])
        elif key == "rebase":
            items = []
            for x in (s.get("items") or [])[:80]:
                x = dict(x)
                x["reason"] = D.pair(x.get("reason"))
                items.append(x)
            merged = []
            for x in (s.get("merged") or [])[:40]:
                x = dict(x)
                x["reason"] = D.pair(x.get("reason"))
                merged.append(x)
            e.update(items=items, merged=merged, summary=D.pair(s.get("summary")), snap_at=(rebase_rows()[0] or {}).get("at"))
        else:
            items = []
            for x in (s.get("items") or [])[:6]:
                x = dict(x)
                for k in ("root_cause", "fix", "change", "merge_effect", "risk"):
                    if k in x:
                        x[k] = D.pair(x[k])
                items.append(x)
            e.update(items=items, summary=D.pair(s.get("summary")))
        e["unverified"] = [str(x) for x in (s.get("unverified") or [])][:12]
    else:
        e.update(status="error", error=(text or "no output")[-400:])
    log(f"   {key}: agent {e['status']} {e['secs']}s ${e['cost_usd']} -> {e['report']}")
    return e


def age_h(iso):
    try:
        return (datetime.now().astimezone() - datetime.fromisoformat(iso)).total_seconds() / 3600
    except (TypeError, ValueError):
        return 1e9


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", action="append", choices=DIRS)
    ap.add_argument("--data-only", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--bug", type=int)
    ap.add_argument("--max-age-hours", type=float, default=168)
    ap.add_argument("--model", default=os.environ.get("TRACE_AGENT_MODEL", ""))
    ap.add_argument("--budget", type=float, default=float(os.environ.get("TRACE_AGENT_BUDGET_USD", "3")), help="USD cap per direction")
    ap.add_argument("--timeout", type=int, default=25, help="minutes per direction")
    a = ap.parse_args()
    if a.bug:
        M.BUG_TARGET = dict(M.BUG_TARGET, number=a.bug, note="set with --bug")
    os.makedirs(M.AGENT_DIR, exist_ok=True)
    logf = open(os.path.join(C.OUT_DIR, "run.log"), "a", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [dirs] {msg}\n")
        logf.flush()

    d = M.save(M.build())
    log(f"trace_agent_dirs: data {d['window']['start']}..{d['window']['end']}, bug #{d['bug']['target']['number']} exists={d['bug']['exists']}")
    if a.data_only:
        return 0
    claude = None
    for key in a.dir or [k for k in DIRS if k != "rebase"]:  # rebase runs only when asked (--dir rebase): it is per-day and paid
        if key == "rebase" and not rebase_rows()[1]:
            log("   rebase: no merge of the last 24 h touches an open PR -> skip, no cost")
            continue
        if key == "bug" and not d["bug"].get("exists"):
            log(f"   bug: #{d['bug']['target']['number']} does not exist yet (newest #{d['bug'].get('newest')}) -> skip, no cost")
            continue
        old = (d["agents"] or {}).get(key) or {}
        s = sig(d, key)
        why = ("forced" if a.force else "new" if not old else "data changed" if old.get("sig") != s
               else "retry" if old.get("status") != "ok" else "refresh" if age_h(old.get("run_at")) >= a.max_age_hours else None)
        if key == "bug" and old.get("target") not in (None, d["bug"]["target"]["number"]):
            why = why or "new target"
        log(f"   {key}: {why or 'fresh, skip'}")
        if not why:
            continue
        claude = claude or D.find_claude()
        e = run(d, key, claude, a, log)
        json.dump(e, open(os.path.join(M.AGENT_DIR, key + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        d["agents"] = M.agents()
        M.save(d)  # live: the tab shows the result right away
    return 0


if __name__ == "__main__":
    sys.exit(main())
