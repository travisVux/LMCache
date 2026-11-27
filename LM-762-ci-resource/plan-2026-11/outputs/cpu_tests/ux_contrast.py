"""Automated WCAG 2.1 AA contrast check of 06_PR_TO_CI_VISUAL.html, light and dark.

For every visible text node in each top-level tab (plus the open PR Inspector and the #ux showcase): text colour vs the
effective background (first non-transparent ancestor background, alpha-blended over the page surface).
Required ratio: 4.5:1, or 3:1 for large text (>= 24 px, or >= 18.66 px bold). Disabled controls are skipped.
Prints failures per target and the most frequent failing (class, colour, background) pairs; exit 1 on any failure.

  python -X utf8 ux_contrast.py [--json out.json] [--max 10]
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HERE = Path(__file__).resolve().parent
PAGE = HERE.parents[1] / "06_PR_TO_CI_VISUAL.html"
sys.path.insert(0, str(HERE))
from ux_capture import TABS  # noqa: E402

PROBE = r"""<script>(async()=>{const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(1500);
const cv=document.createElement('canvas');cv.width=cv.height=1;const cx=cv.getContext('2d',{willReadFrequently:true});
const parse=c=>{if(!c||c==='transparent')return null;const m=c.match(/^rgba?\(([^)]+)\)$/);if(m){const p=m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);return [p[0],p[1],p[2],p.length>3?p[3]:1];}
  cx.clearRect(0,0,1,1);cx.fillStyle='#000';cx.fillStyle=c;cx.fillRect(0,0,1,1);const d=cx.getImageData(0,0,1,1).data;return [d[0],d[1],d[2],d[3]/255];};   // color(srgb ..), oklab(..), color-mix results
const lin=v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);};
const lum=c=>0.2126*lin(c[0])+0.7152*lin(c[1])+0.0722*lin(c[2]);
const blend=(fg,bg)=>[0,1,2].map(i=>fg[i]*fg[3]+bg[i]*(1-fg[3])).concat([1]);
const root=parse(getComputedStyle(document.querySelector('.viz-root')).backgroundColor)||[255,255,255,1];
function bgOf(el){const stack=[];let e=el;while(e&&e.nodeType===1){const c=parse(getComputedStyle(e).backgroundColor);if(c&&c[3]>0){stack.push(c);if(c[3]>=1)break;}e=e.parentElement;}
  let b=root;for(let i=stack.length-1;i>=0;i--)b=blend(stack[i],b);return b;}
function scan(scope,tag){const out=[];const w=document.createTreeWalker(scope,NodeFilter.SHOW_TEXT);let n;const seen=new Set();
  while(n=w.nextNode()){const t=n.nodeValue.trim();const el=n.parentElement;if(!t||!el||seen.has(el))continue;seen.add(el);
    if(el.closest('script,style,svg,.vhide,[hidden],option')||el.disabled)continue;const r=el.getBoundingClientRect();if(!r.width||!r.height)continue;
    const cs=getComputedStyle(el);if(cs.visibility==='hidden'||+cs.opacity===0)continue;let op=1,e=el;while(e&&e.nodeType===1){op*=+getComputedStyle(e).opacity;e=e.parentElement;}
    const bg=bgOf(el);let fg=parse(cs.color);if(!fg)continue;fg=[fg[0],fg[1],fg[2],fg[3]*op];const f=blend(fg,bg);
    const L1=lum(f),L2=lum(bg),ratio=(Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05);const px=parseFloat(cs.fontSize),bold=+cs.fontWeight>=700;
    const need=(px>=24||(bold&&px>=18.66))?3:4.5;
    if(ratio+1e-6<need)out.push({t:tag,cls:(el.className&&el.className.baseVal===undefined?String(el.className):'').slice(0,40),tag:el.tagName.toLowerCase(),
      fg:cs.color,bg:'rgb('+bg.slice(0,3).map(Math.round).join(',')+')',ratio:Math.round(ratio*100)/100,need,text:t.slice(0,50)});}
  return out;}
const R={};
for(const h of %s){if(h.startsWith('e/pr/')){vizNav.show('obs','today',false);piOpen('pr:'+h.slice(5));await wait(120);R[h]=scan(document.getElementById('piDrawer'),h);piClose();continue;}
  if(h==='ux'){location.hash='#ux';await wait(150);const u=document.getElementById('uxShow');R[h]=u?scan(u,h):[];location.hash='#obs/today';await wait(50);continue;}
  const [v,t]=h.split('/');vizNav.show(v,t,false);await wait(120);const parts=[...document.querySelectorAll('section[data-view]:not(.vhide),.vnav,header')];
  R[h]=parts.flatMap(p=>scan(p,h));}
const x=document.createElement('script');x.type='application/json';x.id='Rout';x.textContent=JSON.stringify(R);document.body.appendChild(x);})();</script>"""


def run(theme, targets):
    src = PAGE.read_text(encoding="utf-8").replace("<head>", "<head><script>try{localStorage.setItem('obsOnOpen','false');localStorage.setItem('ciMapLang','en')}catch(e){}"
                                                   f"document.documentElement.dataset.theme='{theme}';</script><style>*,*::before,*::after{{animation:none!important;transition:none!important}}</style>", 1)
    i = src.rindex("</body>")
    f = Path(tempfile.mkdtemp(prefix="ux_contrast_")) / "p.html"
    f.write_text(src[:i] + PROBE % json.dumps(targets) + src[i:], encoding="utf-8")
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--window-size=1440,1000", "--virtual-time-budget=90000", "--dump-dom", f.as_uri()],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600).stdout
    m = re.search(r'<script type="application/json" id="Rout">(.*?)</script>', dom, re.S)
    return json.loads(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--max", type=int, default=8)
    a = ap.parse_args()
    targets = TABS + ["e/pr/5673", "e/pr/6624", "ux"]
    res, total = {}, 0
    for theme in ("light", "dark"):
        R = run(theme, targets)
        if R is None:
            print(theme, ": no result"); return 2
        res[theme] = R
        n = sum(len(v) for v in R.values())
        total += n
        print(f"{theme}: {n} failing text elements in {sum(1 for v in R.values() if v)} of {len(R)} targets")
        pairs = {}
        for v in R.values():
            for x in v:
                k = (x["cls"] or x["tag"], x["fg"], x["bg"], x["need"])
                pairs.setdefault(k, [0, x["ratio"], x["text"]])[0] += 1
        for (cls, fg, bg, need), (cnt, ratio, text) in sorted(pairs.items(), key=lambda kv: -kv[1][0])[:a.max]:
            print(f"   {cnt:4}× .{cls:30} {fg:22} on {bg:18} ratio {ratio} < {need}  e.g. {text!r}")
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=0), encoding="utf-8")
    print("RESULT:", "PASS" if total == 0 else f"FAIL ({total})")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
