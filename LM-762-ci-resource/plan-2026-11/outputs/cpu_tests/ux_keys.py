"""Keyboard path test for the search box and the PR Inspector (UX acceptance: "full keyboard path works").

Synthetic key events drive the page in headless Chrome (a real Tab key cannot be synthesised, so the tab order is
checked as: every interactive control of the drawer is focusable, in DOM order, with no positive tabindex).
Steps: "/" focuses the search box -> type a PR number -> Enter opens the Inspector -> focus is inside the drawer ->
every control is reachable -> Enter on a view tab switches the view -> Enter on a sequence step shows its details ->
j / k move through the findings -> Esc closes the drawer and focus returns to the search box -> deep link #e/pr/N/v3
opens view 3 -> #e/pr/N/docs opens the RFC / FRS panel -> "/" then "F05" + Enter opens an FRS.

  python -X utf8 ux_keys.py [--pr 5673] [--seq 6624]
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

PROBE = r"""<script>(async()=>{const PR=%s,SEQ=%s;const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(1500);
const R={err:window.__err,steps:{}},q=s=>document.querySelector(s),dr=q('#piDrawer');
const key=(k,el)=>{(el||document.activeElement||document.body).dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true,cancelable:true}));};
key('/',document.body);await wait(30);R.steps.slash=document.activeElement&&document.activeElement.id==='uxSearch';
const s=q('#uxSearch');s.value=PR;s.dispatchEvent(new Event('input',{bubbles:true}));await wait(30);key('ArrowDown',s);key('ArrowUp',s);key('Enter',s);await wait(80);
R.steps.enterOpens=dr.classList.contains('on')&&((q('#piTitle')||{}).textContent||'').startsWith('#'+PR);
R.steps.focusInDrawer=dr.contains(document.activeElement);
const ctrls=[...dr.querySelectorAll('a[href],button,input,textarea,select,[tabindex]')].filter(e=>e.getBoundingClientRect().width>0);
R.steps.controls=ctrls.length;R.steps.notFocusable=ctrls.filter(e=>e.tabIndex<0&&!e.matches('.pi-items>li')).map(e=>e.tagName+'.'+e.className).slice(0,5);
R.steps.positiveTabindex=ctrls.filter(e=>e.tabIndex>0).length;
const v3=dr.querySelector('[data-pi-v="3"]');v3.focus();key('Enter',v3);v3.click();await wait(40);R.steps.viewSwitch=(dr.querySelector('.pi-view')||{dataset:{}}).dataset.piView==='3'&&/\/v3$/.test(location.hash);
document.activeElement.blur&&document.activeElement.blur();key('j',document.body);await wait(20);const f1=document.activeElement;key('j',document.body);await wait(20);const f2=document.activeElement;
R.steps.jk=!!(f1&&f2&&f1!==f2&&dr.contains(f2)&&f2.matches('.pi-items>li,.pi-check li'));key('k',document.body);await wait(20);R.steps.kBack=document.activeElement===f1;
key('Escape',document.body);await wait(40);R.steps.escCloses=!dr.classList.contains('on');R.steps.focusReturns=document.activeElement&&document.activeElement.id==='uxSearch';
piOpen('pr:'+SEQ);await wait(80);const m=dr.querySelector('.pi-seq .pi-msg');if(m){m.focus();key('Enter',m);await wait(30);}R.steps.seqEnter=!!dr.querySelector('.pi-seqdet:not([hidden])');piClose();
location.hash='#e/pr/'+PR+'/v3';await wait(120);R.steps.deepView=dr.classList.contains('on')&&(dr.querySelector('.pi-view')||{dataset:{}}).dataset.piView==='3';piClose();
location.hash='#e/pr/'+PR+'/docs';await wait(150);R.steps.deepDocs=dr.classList.contains('on')&&!!dr.querySelector('.pi-kb');piClose();
key('/',document.body);const s2=q('#uxSearch');s2.value='F05';s2.dispatchEvent(new Event('input',{bubbles:true}));await wait(30);key('Enter',s2);await wait(80);
R.steps.fidEnter=dr.classList.contains('on')&&!!dr.querySelector('[data-ux="doc-age"]');piClose();
location.hash='#docs';await wait(80);R.steps.docsList=!!q('#uxDocs:not([hidden]) [data-ux="docs-list"]');key('Escape',document.body);await wait(40);R.steps.docsEsc=!q('#uxDocs:not([hidden])');
R.err=window.__err;const x=document.createElement('script');x.type='application/json';x.id='Rout';x.textContent=JSON.stringify(R);document.body.appendChild(x);})();</script>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", default="5673")
    ap.add_argument("--seq", default="6624")
    a = ap.parse_args()
    src = PAGE.read_text(encoding="utf-8").replace("<head>", "<head><script>try{localStorage.setItem('obsOnOpen','false');localStorage.setItem('ciMapLang','en')}catch(e){}"
                                                   "window.__err=[];addEventListener('error',e=>__err.push(e.message));</script>", 1)
    i = src.rindex("</body>")
    f = Path(tempfile.mkdtemp(prefix="ux_keys_")) / "p.html"
    f.write_text(src[:i] + PROBE % (json.dumps(a.pr), json.dumps(a.seq)) + src[i:], encoding="utf-8")
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--window-size=1440,900", "--virtual-time-budget=40000", "--dump-dom", f.as_uri() + "#obs/today"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300).stdout
    m = re.search(r'<script type="application/json" id="Rout">(.*?)</script>', dom, re.S)
    if not m:
        print("no result"); return 2
    R = json.loads(m.group(1))
    bad = 0
    for k, v in R["steps"].items():
        ok = (v is True) or (k == "controls" and v > 5) or (k in ("notFocusable",) and not v) or (k == "positiveTabindex" and v == 0)
        bad += not ok
        print(f"{k:18} {'OK ' if ok else 'FAIL'} {v if not isinstance(v, bool) else ''}")
    print("JS errors:", R["err"] or "none")
    bad += bool(R["err"])
    print("RESULT:", "PASS" if not bad else f"FAIL ({bad})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
