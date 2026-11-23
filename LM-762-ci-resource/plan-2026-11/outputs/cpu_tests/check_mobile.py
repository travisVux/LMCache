"""Phone-width check for 06_PR_TO_CI_VISUAL.html: horizontal overflow per tab at a real 390 px width.

Why an iframe: headless Chrome has a minimum window width (518 px measured 2026-11-15), so
`--window-size=390,...` screenshots are a 518 px page cut at 390 px and show overflow that does not exist.
The page is loaded in a 390 px iframe inside a wide window instead (CSS width 375 px after the scrollbar).

Run:  python -X utf8 check_mobile.py [tab ...] [--shot DIR]     default tabs: today release coming overlap opt_cpu opt_gpu trace
Prints one line per tab: OK, or the outermost elements that stick out. Exit 1 when any tab overflows.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PAGE = Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html"
TABS = ["today", "hist", "release", "trace", "coming", "opt_cpu", "opt_gpu", "overlap",          # Release Management
        "gates/guide", "gates/tiers", "cpu/overview", "cpu/tiers", "cpu/cost", "cpu/findings", "cpu/explore",  # Release Exploration
        "gpu/overview", "gpu/tiers", "gpu/cost", "gpu/findings", "gpu/explore",
        "r1130/baseline", "r1130/cpu", "r1130/green", "r1130/retry", "r1130/prs", "r1130/track", "r1130/repro", "r1130/quality"]  # Report 1130

FRAME = """<html><body style="margin:0;background:#888"><iframe id="f" src="{src}" style="width:390px;height:{h}px;border:0;background:#fff"></iframe><pre id="R"></pre>
<script>document.getElementById('f').onload=()=>setTimeout(()=>{{const d=document.getElementById('f').contentDocument,v=d.defaultView;
const W=d.documentElement.clientWidth,o=[];d.querySelectorAll('body *').forEach(e=>{{const b=e.getBoundingClientRect(),cs=v.getComputedStyle(e);
if(b.width&&b.right>W+1&&cs.position!=='fixed'&&cs.visibility!=='hidden'){{const p=e.parentElement,pb=p.getBoundingClientRect();
if(pb.right<=W+1)o.push(e.tagName.toLowerCase()+'.'+String(e.className).trim().split(/\\s+/).join('.').slice(0,40)+(e.id?'#'+e.id:'')+' +'+Math.round(b.right-W)+'px')}}}});
document.getElementById('R').textContent='W='+W+' scroll='+d.documentElement.scrollWidth+' | '+o.slice(0,8).join(' | ');}},{wait});</script></body></html>"""


def run(tab, lang, shot_dir, tmp, css=""):
    src = PAGE.read_text(encoding="utf-8").replace("</head>", f"<style>{css}</style></head>", 1).replace(
        "<head>", '<head><script>try{localStorage.setItem("ciMapLang","%s");localStorage.setItem("obsOnOpen","false")}catch(e){}</script>' % lang, 1)
    page = Path(tmp) / f"page_{lang}.html"
    if not page.exists():
        page.write_text(src, encoding="utf-8")
    frame = Path(tmp) / f"frame_{tab.replace("/", "_")}.html"
    frame.write_text(FRAME.format(src=page.as_uri() + "#" + (tab if "/" in tab else "obs/" + tab), h=2400, wait=4000), encoding="utf-8")
    args = [CHROME, "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--virtual-time-budget=12000",
            "--window-size=1000,2500"]
    out = subprocess.run(args + ["--dump-dom", frame.as_uri()], capture_output=True, text=True, encoding="utf-8", timeout=180)
    m = re.search(r'<pre id="R">(.*?)</pre>', out.stdout, re.S)
    res = m.group(1) if m else "no result"
    if shot_dir:
        subprocess.run(args + [f"--screenshot={Path(shot_dir) / f'mobile_{lang}_{tab.replace('/', '_')}.png'}", frame.as_uri()],
                       capture_output=True, timeout=180)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tabs", nargs="*", default=TABS)
    ap.add_argument("--lang", default="vi")
    ap.add_argument("--shot", help="also save a screenshot per tab into this folder")
    ap.add_argument("--css", help="try extra CSS from this file without rebuilding the page")
    a = ap.parse_args()
    bad = 0
    with tempfile.TemporaryDirectory(prefix="mobile_") as tmp:
        for t in a.tabs:
            res = run(t, a.lang, a.shot, tmp, Path(a.css).read_text(encoding="utf-8") if a.css else "")
            m = re.match(r"W=(\d+) scroll=(\d+)", res)
            ok = bool(m) and m.group(1) == m.group(2)
            bad += not ok
            print(f"{t:10s} {'OK ' if ok else 'OVERFLOW'} {res}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
