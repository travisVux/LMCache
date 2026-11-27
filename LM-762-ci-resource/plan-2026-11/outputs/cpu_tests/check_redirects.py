"""Old-hash redirect test for 06_PR_TO_CI_VISUAL.html (tab merge of 2026-11-24).

Every old tab hash (28 tabs before the merge) and every nav alias must still open, land on the merged tab, and show
non-empty sections there. For old tabs that became part of a merged tab, the old content must be visible
(the section that used to be the tab, or the CI cost CPU / GPU half). Also clicks the section-local
[data-goto] buttons of the release cockpit (next_release.js) that used to throw in the nav handler.

Run:  python -I -X utf8 check_redirects.py        exit 1 on any failure
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PAGE = Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html"

# old hash -> (view, merged tab, data-tab that must be visible, hw for CI cost or None)
OLD = {
    "obs/today": ("obs", "today", "today", None), "obs/hist": ("obs", "hist", "hist", None),
    "obs/release": ("obs", "release", "release", None), "obs/trace": ("obs", "release", "trace", None),
    "obs/coming": ("obs", "coming", "coming", None), "obs/opt_cpu": ("obs", "cost", "opt_cpu", "cpu"),
    "obs/opt_gpu": ("obs", "cost", "opt_gpu", "gpu"), "obs/overlap": ("obs", "overlap", "overlap", None),
    "gates/guide": ("gates", "guide", "guide", None), "gates/tiers": ("gates", "tiers", "tiers", None),
    "cpu/overview": ("cpu", "overview", "overview", None), "cpu/tiers": ("cpu", "tiers", "tiers", None),
    "cpu/cost": ("cpu", "cost", "cost", None), "cpu/findings": ("cpu", "cost", "findings", None),
    "cpu/explore": ("cpu", "tiers", "explore", None),
    "gpu/overview": ("gpu", "overview", "overview", None), "gpu/tiers": ("gpu", "tiers", "tiers", None),
    "gpu/cost": ("gpu", "tiers", "cost", None), "gpu/findings": ("gpu", "overview", "findings", None),
    "gpu/explore": ("gpu", "explore", "explore", None),
    # round 2: 8 report tabs merged into baseline / flow / method; the old tab lands on its merged tab
    **{f"r1130/{t}": ("r1130", m, t, None) for t, m in (("baseline", "baseline"), ("cpu", "baseline"), ("green", "flow"), ("retry", "flow"),
                                                        ("prs", "flow"), ("track", "flow"), ("repro", "method"), ("quality", "method"))},
    # aliases that existed before the merge (build_nav.py ALIAS, retired 2026-11-10)
    "obs/now": ("obs", "today", "today", None), "obs/desk": ("obs", "today", "today", None),
    "obs/history": ("obs", "hist", "hist", None), "obs/report": ("obs", "release", "release", None),
    "obs/trend": ("obs", "release", "release", None), "obs/tracer": ("obs", "release", "trace", None),
    "obs/prs": ("obs", "coming", "coming", None), "obs/fixed": ("obs", "coming", "coming", None),
    "obs/merged": ("obs", "coming", "coming", None), "obs/optimal": ("obs", "cost", "opt_cpu", "cpu"),
    "obs/ci": ("obs", "cost", "opt_cpu", "cpu"), "obs/publicci": ("obs", "cost", "opt_cpu", "cpu"),
    "obs/gpuload": ("obs", "cost", "opt_gpu", "gpu"), "obs/gpu": ("obs", "cost", "opt_gpu", "gpu"),
    "obs/flaky": ("obs", "overlap", "overlap", None), "obs/bug": ("obs", "overlap", "overlap", None),
    "obs/24h": ("obs", "overlap", "overlap", None),
    "cpu/matrix": ("cpu", "tiers", "tiers", None), "cpu/notrun": ("cpu", "tiers", "tiers", None),
    "cpu/failfast": ("cpu", "cost", "findings", None), "gpu/mindmap": ("gpu", "explore", "explore", None),
    # new hashes
    "obs/cost": ("obs", "cost", "opt_cpu", "cpu"), "obs/cost/gpu": ("obs", "cost", "opt_gpu", "gpu"),
    "obs/research": ("obs", "research", "research", None), "obs/intake": ("obs", "research", "research", None),
    # 2026-11-26: Weekly full build tab + its short links
    "obs/weekly": ("obs", "weekly", "weekly", None), "obs/full": ("obs", "weekly", "weekly", None),
    "obs/weekly-full": ("obs", "weekly", "weekly", None), "weekly": ("obs", "weekly", "weekly", None),
    # 2026-11-26: CI impact (before / after) tab + its short links
    "obs/impact": ("obs", "impact", "impact", None), "obs/ci-impact": ("obs", "impact", "impact", None),
    "impact": ("obs", "impact", "impact", None), "ci-impact": ("obs", "impact", "impact", None), "before-after": ("obs", "impact", "impact", None),
}

PROBE = r"""<script>(async()=>{const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(1500);
const out={err:window.__err,hash:{},goto:{}};
const vis=()=>[...document.querySelectorAll('section[data-view]')].filter(s=>!s.classList.contains('vhide'));
for(const h of %s){location.hash='#'+h;await wait(120);
  const st=vizNav.state,V=vis();
  out.hash[h]={v:st.v,t:st.t,hw:st.hw,tabs:[...new Set(V.map(s=>s.dataset.tab))],
    empty:V.filter(s=>(s.textContent||'').trim().length<40).map(s=>s.id||s.dataset.ops||'?'),n:V.length,url:location.hash};}
location.hash='#obs/coming';await wait(150);
for(const b of [...document.querySelectorAll('section[data-ops="nr-ck"] [data-goto]')].slice(0,6)){const n0=window.__err.length;b.click();await wait(60);
  out.goto[b.dataset.goto]={err:window.__err.length-n0,v:vizNav.state.v,t:vizNav.state.t};}
document.getElementById('R').textContent=JSON.stringify(out);})();</script><pre id="R"></pre>"""


def main():
    src = PAGE.read_text(encoding="utf-8")
    tmp = tempfile.mkdtemp(prefix="check_redirects_")
    page = src.replace("<head>", '<head><script>try{localStorage.setItem("obsOnOpen","false")}catch(e){}window.__err=[];'
                       'addEventListener("error",e=>__err.push(e.message));</script>', 1)
    page = page.replace("</body>", PROBE % json.dumps(list(OLD)) + "</body>", 1)
    f = Path(tmp) / "probe.html"
    f.write_text(page, encoding="utf-8")
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=60000", "--dump-dom", f.as_uri()],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300).stdout
    m = re.search(r'<pre id="R">(.*?)</pre>', dom, re.S)
    if not m or not m.group(1).strip():
        print("no result from the page"); return 1
    import html
    r = json.loads(html.unescape(m.group(1)))
    bad = 0
    print(f"{'old hash':16} {'lands on':16} {'hw':4} {'sections':8} result")
    for h, (v, t, need, hw) in OLD.items():
        x = r["hash"].get(h) or {}
        why = []
        if (x.get("v"), x.get("t")) != (v, t): why.append(f"landed {x.get('v')}/{x.get('t')}")
        if need not in (x.get("tabs") or []): why.append(f"old content '{need}' not visible")
        if hw and x.get("hw") != hw: why.append(f"hw {x.get('hw')}")
        if not x.get("n"): why.append("no section")
        if x.get("empty"): why.append("empty: " + ",".join(x["empty"]))
        bad += bool(why)
        print(f"{h:16} {str(x.get('v'))+'/'+str(x.get('t')):16} {str(x.get('hw') or ''):4} {x.get('n', 0):<8} {'OK' if not why else 'FAIL ' + '; '.join(why)}")
    for g, x in r["goto"].items():
        ok = not x["err"] and (x["v"], x["t"]) == ("obs", "coming")
        bad += not ok
        print(f"cockpit data-goto={g:10} errors={x['err']} stays {x['v']}/{x['t']}: {'OK' if ok else 'FAIL'}")
    print("JS errors:", r["err"] or "none")
    bad += bool(r["err"])
    print("RESULT:", "PASS" if not bad else f"FAIL ({bad})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
