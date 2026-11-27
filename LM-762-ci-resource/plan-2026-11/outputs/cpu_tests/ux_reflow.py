"""Reflow check (expert review 2026-11-25, U1 / U2; WCAG 1.4.10 and 2.4.11): the page in an iframe of the given width
(320 px = 1280 px at 400 % zoom; headless Chrome cannot make a window below 518 px), every top-level tab:
  - the page never scrolls sideways (documentElement.scrollWidth <= clientWidth)
  - the navigation is not pinned (position sticky / fixed) on small screens, so it cannot cover the content
Also a short-and-wide frame (640 x 400 = 1280 x 800 at 200 % zoom) for the pinned-nav rule.

  python -X utf8 ux_reflow.py [--w 320] [--theme light|dark]
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PAGE = Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html"
TABS = ["obs/today", "obs/hist", "obs/release", "obs/coming", "obs/cost", "obs/overlap", "obs/research", "gates/guide", "gates/tiers",
        "cpu/overview", "cpu/tiers", "cpu/cost", "gpu/overview", "gpu/tiers", "gpu/explore", "r1130/baseline", "r1130/cpu", "r1130/green",
        "r1130/retry", "r1130/prs", "r1130/track", "r1130/repro", "r1130/quality"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=int, default=320)
    ap.add_argument("--theme", default="light")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="ux_reflow_"))
    pg = tmp / "page.html"
    pg.write_text(PAGE.read_text(encoding="utf-8").replace("<head>", "<head><script>try{localStorage.setItem('obsOnOpen','false');localStorage.setItem('ciMapLang','en')}catch(e){}"
                                                           f"document.documentElement.dataset.theme='{a.theme}';</script>", 1), encoding="utf-8")
    frames = [(a.w, 900, "w"), (640, 400, "z")]
    probe = """<script>const wait=ms=>new Promise(r=>setTimeout(r,ms));const out={};
async function run(id,tabs){const f=document.getElementById(id);let w=f.contentWindow,d;for(let i=0;i<80;i++){w=f.contentWindow;d=w&&w.document;if(d&&d.querySelector('.vnav')&&w.vizNav)break;await wait(250);}await wait(800);const nav=d.querySelector('.vnav');
  out[id+'_nav']=w.getComputedStyle(nav).position;out[id+'_navH']=Math.round(nav.getBoundingClientRect().height);out[id+'_bad']=[];
  for(const t of tabs){const [v,s]=t.split('/');w.vizNav.show(v,s,false);await wait(350);const W=d.documentElement.clientWidth,S=d.documentElement.scrollWidth;
    if(S>W+1){let wide=[...d.querySelectorAll('body *')].filter(e=>!e.closest('.vhide')).filter(e=>e.getBoundingClientRect().right>W+1&&e.parentElement.getBoundingClientRect().right<=W+1&&!e.closest('[style*=overflow],table,pre,.obs-scroll')).slice(0,3).map(e=>e.tagName+'.'+String(e.className).slice(0,24)+'<'+e.parentElement.tagName+'.'+String(e.parentElement.className).slice(0,20)+' w'+Math.round(e.getBoundingClientRect().width));
      out[id+'_bad'].push(t+' +'+(S-W)+' '+wide.join(','));}}}
(async()=>{try{await run('fw',%s);await run('fz',['obs/coming']);}catch(e){out.err=String(e);}document.getElementById('R').textContent=JSON.stringify(out);})();</script>""" % json.dumps(TABS)
    frm = "".join(f'<iframe id="f{k}" src="{pg.as_uri()}#obs/today" style="width:{w}px;height:{h}px;border:0;display:block"></iframe>' for w, h, k in frames)
    host = tmp / "host.html"
    host.write_text(f'<html><body style="margin:0">{frm}<pre id="R"></pre>{probe}</body></html>', encoding="utf-8")
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--window-size=1000,1400", "--virtual-time-budget=120000",
                          "--dump-dom", host.as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=400).stdout
    m = re.search(r'<pre id="R">(.*?)</pre>', dom, re.S)
    if not m or not m.group(1).strip():
        print("no result"); return 2
    R = json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    if R.get("err"):
        print("probe error:", R["err"]); return 2
    bad = 0
    print(f"{a.w} px: nav position {R['fw_nav']} ({R['fw_navH']} px tall)")
    print(f"640 x 400 (200 % zoom): nav position {R['fz_nav']} ({R['fz_navH']} px tall)")
    for k in ("fw_nav", "fz_nav"):
        if R[k] in ("sticky", "fixed"):
            bad += 1; print("  FAIL pinned nav at", k)
    for x in R["fw_bad"]:
        bad += 1; print("  FAIL sideways scroll:", x)
    print(f"tabs checked {len(TABS)}; sideways scroll on {len(R['fw_bad'])}")
    print("RESULT:", "PASS" if not bad else f"FAIL ({bad})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
