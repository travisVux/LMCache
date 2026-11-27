"""Prove the tab merge lost no fact: facts shown in each OLD tab must be shown in its NEW (merged) tab.

Facts = PR numbers (#1234), feature ids (F01..F17), decision / carry-over ids (D1, C2), release tags (v0.5.8rc1),
CI gate / pipeline names (k3-*, DCO, Check code quality, workflow names from gates.py). Text = textContent of every
visible section (collapsed <details> count: they are one click away), after the page has rendered.

  python -I -X utf8 prove_facts.py --old <backup of the page before the merge> [--json out.json]

Exit 1 if any old-tab fact is missing from its target. Moves approved in the merge table (MOVED) are allowed.
"""
import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PAGE = Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html"

OLD_TABS = [("obs", t) for t in ("today", "hist", "release", "trace", "coming", "opt_cpu", "opt_gpu", "overlap")] + \
    [("gates", t) for t in ("guide", "tiers")] + [("cpu", t) for t in ("overview", "tiers", "cost", "findings", "explore")] + \
    [("gpu", t) for t in ("overview", "tiers", "cost", "findings", "explore")] + \
    [("r1130", t) for t in ("baseline", "cpu", "green", "retry", "prs", "track", "repro", "quality")]
# old tab -> new hash (view/tab[/gpu])
TARGET = {"obs/trace": "obs/release", "obs/opt_cpu": "obs/cost", "obs/opt_gpu": "obs/cost/gpu",
          "cpu/explore": "cpu/tiers", "cpu/findings": "cpu/cost", "gpu/findings": "gpu/overview", "gpu/cost": "gpu/tiers"}
# approved moves: facts of the old tab may live in these other new tabs instead (merge table rows D3, D4/D5)
MOVED = {"obs/today": ["obs/overlap"]}   # ready-for-'full' queue: one copy, on Rebase risk

FACT = re.compile(r"#\d{3,5}\b|\bF(?:0[1-9]|1[0-7])\b|\b[DC][1-9]\b|\bv\d+\.\d+\.\d+(?:\.post\d+|rc\d+)?\b|"
                  r"\bk3-[a-z0-9-]+|\bDCO\b|Check code quality|\b(?:nightly|publish)\.yml\b")

PROBE = r"""<script>const FRE=new RegExp(%s,'g');(async()=>{const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(2500);const out={};
for(const h of %s){location.hash='#'+h;await wait(150);
  const parts=[];for(const s of document.querySelectorAll('section[data-view]')){if(s.classList.contains('vhide'))continue;
    const w=document.createTreeWalker(s,NodeFilter.SHOW_TEXT);let n;while((n=w.nextNode()))parts.push(n.nodeValue);}
  out[h]=[...new Set(parts.join(' ').match(FRE)||[])];}
put(out);})().catch(e=>put({__error:String(e)}));
function put(o){const x=document.createElement('script');x.type='application/json';x.id='Rout';x.textContent=JSON.stringify(o);document.body.appendChild(x);}</script>"""


def texts(page_path, hashes):
    src = Path(page_path).read_text(encoding="utf-8")
    src = src.replace("<head>", '<head><script>try{localStorage.setItem("obsOnOpen","false");localStorage.setItem("ciMapLang","en")}catch(e){}</script>', 1)
    i = src.rindex("</body>")
    src = src[:i] + PROBE % (json.dumps(FACT.pattern), json.dumps(hashes)) + src[i:]
    f = Path(tempfile.mkdtemp(prefix="prove_facts_")) / "p.html"
    f.write_text(src, encoding="utf-8")
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=60000", "--dump-dom", f.as_uri()],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300).stdout
    m = re.search(r'<script type="application/json" id="Rout">(.*?)</script>', dom, re.S)
    if not m or not m.group(1).strip():
        raise SystemExit(f"no result from {page_path} (dom {len(dom)} chars)")
    r = json.loads(m.group(1))
    if "__error" in r:
        raise SystemExit(f"page error in {page_path}: {r['__error']}")
    return r


def facts(t):
    return {x.strip() for x in (t or [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    old_h = [f"{v}/{t}" for v, t in OLD_TABS]
    new_h = sorted({TARGET.get(h, h) for h in old_h} | {x for m in MOVED.values() for x in m})
    old, new = texts(a.old, old_h), texts(PAGE, new_h)
    rep, bad = [], 0
    print(f"{'old tab':16} {'-> new tab':16} {'facts':>6} {'kept':>6} {'moved':>6} missing")
    for h in old_h:
        tgt = TARGET.get(h, h)
        fo, fn = facts(old[h]), facts(new[tgt])
        moved = set().union(*[facts(new[m]) for m in MOVED.get(h, [])]) if h in MOVED else set()
        miss = sorted(fo - fn - moved)
        bad += bool(miss)
        rep.append(dict(old=h, new=tgt, facts=len(fo), kept=len(fo & fn), moved=len((fo - fn) & moved), missing=miss))
        print(f"{h:16} {tgt:16} {len(fo):6} {len(fo & fn):6} {len((fo - fn) & moved):6} {', '.join(miss[:12]) or '-'}")
    allo = set().union(*[facts(x) for x in old.values()])
    alln = set().union(*[facts(x) for x in new.values()])
    print(f"whole page: old {len(allo)} facts, new {len(alln)}, missing {len(allo - alln)}")
    if a.json:
        Path(a.json).write_text(json.dumps(dict(tabs=rep, old_total=len(allo), new_total=len(alln), missing=sorted(allo - alln)), indent=1), encoding="utf-8")
    print("RESULT:", "PASS" if not bad and not (allo - alln) else "FAIL")
    return 1 if bad or (allo - alln) else 0


if __name__ == "__main__":
    sys.exit(main())
