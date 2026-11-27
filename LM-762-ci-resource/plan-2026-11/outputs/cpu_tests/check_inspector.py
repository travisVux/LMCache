"""Acceptance test of the PR Inspector (build_pr_inspector.py) in headless Chrome.

Checks, for PR #6572 (merged) and one open PR with patches (and any PR given on the command line):
  - forward: flow (modules -> areas -> features -> gates) and exactly 5 views; every view has findings, a reviewer
    checklist and a CI gate table; every finding has evidence (a link / code ref) or an explicit "unknown"
  - backward: PR -> builds / signatures / regressions, and a bug signature and a dev regression open their suspects
  - entry points: a PR link in Today, the 6A "Inspect" button (opens view 5), a feature chip in a PR row (focus)
  - no console error; VI mode leaves no English sentence in the drawer (same rule as verify_page.py)
  - phone: the drawer at a real 390 px width (iframe, as check_mobile.py) has no horizontal overflow, light and dark

  python -I -X utf8 check_inspector.py [PR ...] [--shot DIR]
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

PROBE = r"""<script>(async()=>{const wait=ms=>new Promise(r=>setTimeout(r,ms));await wait(1800);
const R={err:window.__err,prs:{},entry:{}},dr=document.getElementById('piDrawer');R.entry.entStart={ok:true,ent:document.getElementById('entDrawer').classList.contains('on')};
const SKIP='code,pre,script,style,.obsraw,.pi-why';
const english=()=>{const left=[];const w=document.createTreeWalker(dr,NodeFilter.SHOW_TEXT);let n;
  while(n=w.nextNode()){const t=n.nodeValue.trim(),p=n.parentElement;if(!t||!p||p.closest(SKIP))continue;
    const hits=(t.match(/(?<![\p{L}\-_])(the|is|are|and|of|to|on|when|only|with|for|runs|files|passed|show|see|per|not|in|a)(?![\p{L}\-_])/giu)||[]).length;if(hits>=2)left.push(t.slice(0,90));}return left;};
const viewStats=()=>{const v=dr.querySelector('.pi-view');if(!v)return null;const lis=[...v.querySelectorAll('.pi-items>li')];
  return {items:lis.length,noEvidence:lis.filter(li=>!li.querySelector('a,code,button,.pi-unk')).map(li=>li.textContent.slice(0,80)),
    unknown:v.querySelectorAll('.pi-unk').length,check:v.querySelectorAll('.pi-check li').length,gates:v.querySelectorAll('.pi-gt tr').length,
    kinds:[...new Set([...v.querySelectorAll('.pi-g')].map(x=>x.className.split(' ')[1]))]};};
for(const n of %s){const o={};piOpen('pr:'+n);await wait(50);o.open=dr.classList.contains('on');o.hash=location.hash;o.flow=dr.querySelectorAll('#piFlow .pi-col').length;
  o.tabs=dr.querySelectorAll('[data-pi-v]').length;o.views={};
  for(let i=1;i<=5;i++){dr.querySelector(`[data-pi-v="${i}"]`).click();await wait(20);o.views[i]=viewStats();}
  dr.querySelector('[data-pi-dir="back"]').click();await wait(20);o.back=dr.querySelectorAll('.pi-items>li').length;o.backStart=dr.querySelectorAll('.pi-start [data-pi]').length;
  I18N.setLang('vi');await wait(30);o.viBack=english();dr.querySelector('[data-pi-dir="fwd"]').click();o.vi=[];
  for(let i=1;i<=5;i++){dr.querySelector(`[data-pi-v="${i}"]`).click();await wait(15);o.vi.push(...english());}
  I18N.setLang('en');await wait(30);piClose();R.prs[n]=o;}
{const b=Object.keys(PI.data.bugs).find(s=>(PI.data.bugs[s].b||[]).some(k=>(PI.data.builds[k]||{}).pr&&PI.data.builds[k].pr.length));
 R.bug={sig:b,opened:piOpen('bug:'+b),items:dr.querySelectorAll('.pi-items>li').length,suspects:dr.querySelectorAll('.pi-items>li .pi-pr').length};piClose();}
R.reg={n:PI.data.reg.length,opened:PI.data.reg.length?piOpen('reg:0'):false,items:dr.querySelectorAll('.pi-items>li').length};piClose();
vizNav.show('obs','today',false);await wait(50);{const a=document.querySelector('section[data-view="obs"][data-tab="today"] [data-ent^="pr:"]');
 if(a){a.click();await wait(30);R.entry.todayPr={ent:document.getElementById('entDrawer').classList.contains('on'),ok:dr.classList.contains('on'),title:(dr.querySelector('#piTitle')||{}).textContent||''};piClose();}else R.entry.todayPr={ok:null};}
vizNav.show('obs','overlap',false);await wait(50);{const b=document.querySelector('section[data-ops="overlap"] [data-pi][data-pi-view="5"]');
 if(b){b.click();await wait(30);R.entry.sixA={ent:document.getElementById('entDrawer').classList.contains('on'),ok:dr.classList.contains('on'),view:(dr.querySelector('.pi-view')||{dataset:{}}).dataset.piView};piClose();}else R.entry.sixA={ok:null};}
{const rows=[...document.querySelectorAll('section[data-view] tr,section[data-view] li')].filter(r=>!r.closest('#piDrawer')&&r.querySelector('[data-ent^="feature:"]')&&new Set([...r.querySelectorAll('[data-ent^="pr:"]')].map(x=>x.dataset.ent)).size===1);
 if(rows.length){const f=rows[0].querySelector('[data-ent^="feature:"]');const sec=f.closest('section[data-view]');vizNav.show(sec.dataset.view,sec.dataset.tab,false);await wait(30);f.click();await wait(30);
   R.entry.prFeature={ent:document.getElementById('entDrawer').classList.contains('on'),ok:dr.classList.contains('on'),focus:dr.querySelectorAll('.pi-items>li.focus,.pi-chip.focus').length,areas:dr.querySelectorAll('[data-pn^="a:"]').length,feature:f.dataset.ent};piClose();}else R.entry.prFeature={ok:null,rows:0};}
R.entry.noCardBefore={ok:!document.getElementById('entDrawer').classList.contains('on')};if(window.closeEntity)closeEntity();
location.hash='#e/pr/%s';await wait(80);R.entry.route={ok:dr.classList.contains('on')&&!document.getElementById('entDrawer').classList.contains('on'),pi:dr.classList.contains('on'),ent:document.getElementById('entDrawer').classList.contains('on'),hash:location.hash};piClose();
{const S=PI.data.seq,ks=Object.keys(S);const sp=%s||ks.find(k=>PI.data.prs[k].st==='open')||ks.sort((a,b)=>S[b][0].n_chg-S[a][0].n_chg)[0];
 const B={pr:sp,n:ks.length};piOpen('pr:'+sp);await wait(80);
 B.animDefault=!!dr.querySelector('.pi-links.run')||dr.querySelectorAll('.pi-chip.hot').length>0;B.links=dr.querySelectorAll('.pi-links path').length;
 B.seq=dr.querySelectorAll('.pi-seq').length;B.msgs=dr.querySelectorAll('.pi-seq .pi-msg').length;B.chg=dr.querySelectorAll('.pi-seq .pi-msg.chg').length;
 const m=dr.querySelector('.pi-seq .pi-msg.chg')||dr.querySelector('.pi-seq .pi-msg');
 if(m){m.dispatchEvent(new MouseEvent('click',{bubbles:true}));await wait(20);const det=dr.querySelector('.pi-seqdet:not([hidden])');B.detail=det?{dt:det.querySelectorAll('dt').length,link:!!det.querySelector('a[href*="#L"]'),text:det.textContent.slice(0,200)}:null;}
 dr.querySelector('[data-pa="toggle"]').click();await wait(2400);B.animOn={hot:dr.querySelectorAll('.pi-chip.hot').length,run:!!dr.querySelector('.pi-links.run'),seqHot:dr.querySelectorAll('.pi-msg.hot').length,tick:PISEQ.state().tick};
 dr.querySelector('[data-pa="pause"]').click();const t0=PISEQ.state().tick;await wait(2500);B.paused={tick0:t0,tick1:PISEQ.state().tick,cls:!!dr.querySelector('.pi-links.paused')};
 dr.querySelector('[data-pa="toggle"]').click();await wait(50);B.off=PISEQ.state().anim===false&&dr.querySelectorAll('.pi-chip.hot').length===0;
 const c=dr.querySelector('#piFlow [data-pn^="a:"]');if(c){c.click();await wait(20);B.select={hot:dr.querySelectorAll('#piFlow .pi-chip.hot').length,dim:dr.querySelectorAll('#piFlow .pi-chip.dim').length,edges:dr.querySelectorAll('.pi-links path.hot').length};c.click();}
 I18N.setLang('vi');await wait(40);B.vi=english();I18N.setLang('en');await wait(20);piClose();
 const jp=Object.keys(PI.data.prs).find(n=>PISEQ.journeySeqs(PI.model(n)).length);B.journey={pr:jp};
 if(jp){piOpen('pr:'+jp);await wait(60);const sq=[...dr.querySelectorAll('.pi-seq')].find(x=>/journey/i.test(x.textContent));B.journey.msgs=sq?sq.querySelectorAll('.pi-msg').length:0;
   const mm=sq&&(sq.querySelector('.pi-msg.chg')||sq.querySelector('.pi-msg'));if(mm){mm.dispatchEvent(new MouseEvent('click',{bubbles:true}));await wait(20);const dd=sq.querySelector('.pi-seqdet:not([hidden])');B.journey.detail=dd?dd.textContent.slice(0,200):null;}piClose();}
 R.seqB=B;}
R.err=window.__err;const x=document.createElement('script');x.type='application/json';x.id='Rout';x.textContent=JSON.stringify(R);document.body.appendChild(x);})();</script>"""

FRAME = """<html><body style="margin:0;background:#888"><iframe id="f" src="{src}" style="width:390px;height:1600px;border:0;background:#fff"></iframe><pre id="R"></pre>
<script>document.getElementById('f').onload=()=>setTimeout(()=>{{const w=document.getElementById('f').contentWindow,d=w.document;w.piOpen('pr:{pr}');
setTimeout(()=>{{const out={{}};for(const v of [1,2,3,4,5]){{const b=d.querySelector('[data-pi-v="'+v+'"]');if(b)b.click();
const dr=d.getElementById('piDrawer'),DR=dr.getBoundingClientRect(),CW=d.documentElement.clientWidth,W=DR.right,o=[];if(DR.left<-1||DR.right>CW+1)o.push('drawer '+Math.round(DR.left)+'..'+Math.round(DR.right)+' of '+CW);dr.querySelectorAll('*').forEach(e=>{{const r=e.getBoundingClientRect();
if(r.width&&r.right>W+1&&!e.closest('.pi-body')?.scrollLeft){{const pr=e.parentElement.getBoundingClientRect();if(pr.right<=W+1)o.push(e.tagName.toLowerCase()+'.'+String(e.className).slice(0,30)+' +'+Math.round(r.right-W));}}}});
out[v]=o.slice(0,5);}}const l=d.querySelector('.pi-seqlist'),g=d.querySelector('.pi-seqsvg');out.seq=l?w.getComputedStyle(l).display+'/'+w.getComputedStyle(g).display:'-';
document.getElementById('R').textContent=JSON.stringify(out);}},400);}},2500);</script></body></html>"""


def chrome(args, timeout=300):
    return subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--allow-file-access-from-files"] + args,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prs", nargs="*")
    ap.add_argument("--shot")
    ap.add_argument("--seq", help="PR to use for the new.CI sequence diagram test (default: an open one, else the most edited)")
    a = ap.parse_args()
    src = PAGE.read_text(encoding="utf-8")
    m = re.search(r'<script id="piData" type="application/json">(.*?)</script>', src, re.S)
    D = json.loads(m.group(1).replace("<\\/", "</"))
    open_pr = next((n for n, x in D["prs"].items() if x["st"] == "open" and x["src"] == "patch" and x.get("c24")), None) or \
        next((n for n, x in D["prs"].items() if x["st"] == "open" and x["src"] == "patch"), None)
    prs = a.prs or [p for p in ("6572", open_pr) if p]
    tmp = Path(tempfile.mkdtemp(prefix="check_inspector_"))
    page = src.replace("<head>", '<head><script>try{localStorage.setItem("obsOnOpen","false");localStorage.setItem("ciMapLang","en")}catch(e){}'
                       'window.__err=[];addEventListener("error",e=>__err.push(e.message));</script>', 1)
    i = page.rindex("</body>")
    seq_pr = a.seq or next((n for n, e in D.get("seq", {}).items() if D["prs"][n]["st"] == "open"), None) or         max(D.get("seq", {"": [{"n_chg": 0}]}).items(), key=lambda kv: kv[1][0]["n_chg"])[0]
    page = page[:i] + PROBE % (json.dumps(prs), prs[0], json.dumps(seq_pr)) + page[i:]
    f = tmp / "probe.html"
    f.write_text(page, encoding="utf-8")
    dom = chrome(["--virtual-time-budget=60000", "--dump-dom", f.as_uri()])
    m = re.search(r'<script type="application/json" id="Rout">(.*?)</script>', dom, re.S)
    if not m:
        print("no result from the page"); return 1
    R = json.loads(m.group(1))
    bad = []
    for n, o in R["prs"].items():
        print(f"PR #{n} ({D['prs'].get(n, {}).get('st', '?')}): open={o['open']} hash={o['hash']} flow columns={o['flow']} views={o['tabs']} backward items={o['back']} start-from-failure={o['backStart']}")
        if not o["open"] or o["tabs"] != 5 or o["flow"] != 4 or o["back"] < 1:
            bad.append(f"#{n} drawer / views / backward")
        for v, s in o["views"].items():
            print(f"   view {v}: findings {s['items']:2}  unknown {s['unknown']:2}  checklist {s['check']:2}  gates {s['gates']:2} {s['kinds']}"
                  + (f"  NO EVIDENCE: {s['noEvidence']}" if s["noEvidence"] else ""))
            if not s["items"] or not s["check"] or not s["gates"] or s["noEvidence"]:
                bad.append(f"#{n} view {v}")
        left = o["vi"] + o["viBack"]
        print(f"   VI untranslated in drawer: {len(left)} {left[:3]}")
        if left:
            bad.append(f"#{n} VI")
    print(f"bug signature {R['bug']['sig']}: opened={R['bug']['opened']} items={R['bug']['items']} suspect PR links={R['bug']['suspects']}")
    print(f"dev regressions {R['reg']['n']}: reg:0 opened={R['reg']['opened']} items={R['reg']['items']}")
    if not R["bug"]["opened"] or not R["bug"]["suspects"] or (R["reg"]["n"] and not R["reg"]["items"]):
        bad.append("backward from failure")
    for k, v in R["entry"].items():
        print(f"entry {k}: {v}")
        if not v.get("ok"):
            bad.append("entry " + k)
    if R["entry"].get("sixA", {}).get("view") != "5":
        bad.append("6A button does not open view 5")
    if R["entry"].get("prFeature", {}).get("ok") and R["entry"]["prFeature"].get("areas") and not R["entry"]["prFeature"].get("focus"):   # no file list -> no area to focus
        bad.append("PR.feature focus")
    B = R.get("seqB") or {}
    print(f"new.CI sequence: PR #{B.get('pr')} ({B.get('n')} new.CI PRs) diagrams={B.get('seq')} steps={B.get('msgs')} edited={B.get('chg')} flow links={B.get('links')}")
    print(f"   click a step -> {B.get('detail')}")
    print(f"   animation default on? {B.get('animDefault')} · on: {B.get('animOn')} · paused: {B.get('paused')} · off again: {B.get('off')} · chip path: {B.get('select')}")
    print(f"   VI untranslated: {len(B.get('vi') or [])} {(B.get('vi') or [])[:3]}")
    print(f"multi-stage cache pipeline: {B.get('journey')}")
    d = B.get("detail") or {}
    an, pa = B.get("animOn") or {}, B.get("paused") or {}
    if not (B.get("seq") and B.get("msgs", 0) >= 3 and B.get("chg") and d.get("dt") == 3 and d.get("link")):
        bad.append("new.CI sequence diagram")
    if B.get("animDefault") or not (an.get("hot") and an.get("run") and an.get("tick", 0) >= 1) or pa.get("tick0") != pa.get("tick1") or not pa.get("cls") or not B.get("off"):
        bad.append("animation off by default / on / pause / off")
    if not (B.get("select") or {}).get("hot") or not B.get("links"):
        bad.append("flow links / chip path")
    if B.get("vi"):
        bad.append("sequence VI")
    j = B.get("journey") or {}
    if not (j.get("pr") and j.get("msgs") and j.get("detail")):
        bad.append("cache pipeline sequence")
    print("JS errors:", R["err"] or "none")
    if R["err"]:
        bad.append("JS errors")
    # phone width, light + dark
    for theme in ("light", "dark"):
        p2 = tmp / f"page_{theme}.html"
        p2.write_text(src.replace("<head>", '<head><script>try{localStorage.setItem("obsOnOpen","false")}catch(e){}'
                                  f"document.documentElement.dataset.theme='{theme}';</script><style>.pi-drawer{{transition:none!important}}</style>", 1), encoding="utf-8")
        fr = tmp / f"frame_{theme}.html"
        fr.write_text(FRAME.format(src=p2.as_uri() + "#obs/today", pr=seq_pr or prs[0]), encoding="utf-8")
        out = chrome(["--virtual-time-budget=20000", "--window-size=1000,1700", "--dump-dom", fr.as_uri()])
        mm = re.search(r'<pre id="R">(.*?)</pre>', out, re.S)
        res = json.loads(mm.group(1).replace("&quot;", '"')) if mm and mm.group(1).strip() else None
        seq_disp = (res or {}).pop("seq", "-")
        over = {k: v for k, v in (res or {}).items() if v}
        print(f"390 px {theme} (PR #{seq_pr or prs[0]}): {'OK' if res is not None and not over else 'OVERFLOW ' + json.dumps(over) if res else 'no result'} · sequence list/svg display: {seq_disp}")
        if res is None or over or (seq_pr and seq_disp != "flex/none"):
            bad.append(f"390 px {theme}")
        if a.shot:
            Path(a.shot).mkdir(parents=True, exist_ok=True)
            chrome(["--virtual-time-budget=20000", "--window-size=1000,1700", f"--screenshot={Path(a.shot) / f'inspector_390_{theme}.png'}", fr.as_uri()])
    print("RESULT:", "PASS" if not bad else "FAIL " + "; ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
