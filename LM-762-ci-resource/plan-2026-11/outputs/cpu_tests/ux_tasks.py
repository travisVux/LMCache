"""UX task test: drive the real DOM from #obs/today and record, per task, the clicks (or typed queries) needed and the
time to the answer. Real clock (Chrome --timeout, no virtual time). Times are MACHINE times (load + scripted clicks
+ render), not human reading time; "fold" says whether the answer is visible without scrolling at 1440x900 (a proxy
for "readable in a few seconds").

Tasks (targets from the UX brief):
  T1 Can we ship the next release? Name the top blocker.          <= 1 click, answer above the fold
  T2 PR #<open PR>: safe to merge? What to check first?            <= 3 clicks
  T3 Which open PRs must rebase now, and why?                      <= 3 clicks
  T4 A CI gate is red: which PR / feature likely caused it?        <= 3 clicks
  T5 What changed since yesterday?                                 <= 4 clicks
  T6 Where is the RFC / FRS for feature F<nn>, is it stale?         <= 4 clicks
  T7 A Research PR: which context, what does the benchmark say?    <= 4 clicks
An answer counts only if the UI states it (an explicit element), not if it can be inferred from raw tables.

  python -X utf8 ux_tasks.py [--pr 5673] [--fid F05] [--json out.json]
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
TARGET = {"T1": 1, "T2": 3, "T3": 3, "T4": 3, "T5": 4, "T6": 4, "T7": 4}

PROBE = r"""<script>(async()=>{const PR=%s,FID=%s;const wait=ms=>new Promise(r=>setTimeout(r,ms));
const ready=()=>window.vizNav&&window.PI;while(!ready())await wait(20);const t_ready=performance.now();await wait(300);
const R={load_ms:Math.round(t_ready),tasks:{}};const q=s=>document.querySelector(s);
const vis=e=>{if(!e)return false;const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&!e.closest('.vhide,[hidden]');};
const top=e=>{const r=e.getBoundingClientRect();return Math.round(r.top+scrollY);};
async function reset(){if(window.piClose)piClose();if(window.closeEntity)closeEntity();if(window.UX&&UX.closeAll)UX.closeAll();vizNav.show('obs','today',false);scrollTo(0,0);await wait(60);}
let clicks=0;const click=async e=>{clicks++;e.click();await wait(80);};
const type=async(text)=>{const s=q('[data-ux="search"]');if(!s)return false;clicks++;s.focus();s.value=text;s.dispatchEvent(new Event('input',{bubbles:true}));await wait(60);
  s.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await wait(150);return true;};
async function task(id,fn){await reset();clicks=0;const t0=performance.now();let a;try{a=await fn();}catch(e){a={ok:false,why:'error: '+e.message};}
  R.tasks[id]=Object.assign({clicks,ms:Math.round(performance.now()-t0)},a);}
// T1
await task('T1',async()=>{const v=q('[data-ux="verdict"]')||q('#dkWhere .dk-st');const b=q('[data-ux="top-blocker"]');
  const fb=q('#dkBlock .dk-row, #dkBlock tr, #dkBlock li');
  if(v&&b&&vis(v)&&vis(b))return {ok:true,answer:(v.textContent+' | '+b.textContent).slice(0,160),fold:top(b)<900&&top(v)<900};
  return {ok:false,why:'no explicit top blocker'+(fb?' (first row of section 2 at y='+top(fb)+')':''),answer:v?v.textContent.slice(0,80):'',fold:false};});
// T2
await task('T2',async()=>{if(!(await type(PR))){const a=q(`section[data-view] [data-ent="pr:${PR}"]`);if(!a)return {ok:false,why:'PR not linked anywhere'};
    const s=a.closest('section[data-view]');await click(document.querySelector(`#vPills [data-v="${s.dataset.view}"][data-t]`)||a);vizNav.show(s.dataset.view,s.dataset.tab,false);await click(a);}
  const dr=q('#piDrawer');if(!dr||!dr.classList.contains('on'))return {ok:false,why:'Inspector did not open'};
  const m=dr.querySelector('[data-ux="merge-verdict"]');const c=dr.querySelector('.pi-check li');
  return m&&c?{ok:true,answer:(m.textContent+' | first check: '+c.textContent).slice(0,200)}:{ok:false,why:'no merge verdict in the Inspector',answer:c?c.textContent.slice(0,80):''};});
// T3
await task('T3',async()=>{await click(q('#vPills [data-t="overlap"]'));const m=q('[data-ux="rebase-now"]');
  if(m&&vis(m))return {ok:true,answer:m.textContent.slice(0,200)};
  const rows=[...document.querySelectorAll('section[data-ops="overlap"] .tdy-v')].filter(x=>/rebase/i.test(x.textContent)&&vis(x));
  return {ok:false,why:`no explicit "rebase now" list (${rows.length} rebase chips in the table)`};});
// T4
await task('T4',async()=>{const f=q('[data-ux="find-cause"]');if(f&&vis(f)){await click(f);}
  else{const a=q('section[data-view="obs"][data-tab="today"] [data-ent^="pr:"]');if(!a)return {ok:false,why:'no entry'};await click(a);const d=q('#piDrawer [data-pi-dir="back"]');if(d)await click(d);
    const r=q('#piDrawer .pi-start [data-pi^="reg:"]');if(r)await click(r);}
  const dr=q('#piDrawer');const sus=dr&&dr.classList.contains('on')?dr.querySelectorAll('.pi-items>li .pi-pr').length:0;const unk=dr?dr.querySelectorAll('.pi-unk').length:0;
  return sus||unk?{ok:true,answer:`${sus} suspect PR(s), ${unk} unknown note(s): `+((dr.querySelector('#piTitle')||{}).textContent||'').slice(0,80)}:{ok:false,why:'no cause view'};});
// T5
await task('T5',async()=>{let m=q('[data-ux="since-yesterday"]');if(!(m&&vis(m))){const h=q('#vPills [data-t="hist"]');if(h)await click(h);m=q('[data-ux="since-yesterday"]');}
  return m&&vis(m)?{ok:true,answer:m.textContent.slice(0,200)}:{ok:false,why:'no "since yesterday" view'};});
// T6
await task('T6',async()=>{if(await type(FID)){const d=q('[data-ux="doc-age"]');if(!d){const r=q('[data-ux="search-results"] [data-kind="frs"]');if(r)await click(r);}
    const d2=q('[data-ux="doc-age"]');return d2&&vis(d2)?{ok:true,answer:d2.textContent.slice(0,200)}:{ok:false,why:'search did not reach the FRS'};}
  // baseline: needs a PR that touches the feature, then the RFC/FRS panel, then the FRS tab
  const pr=Object.keys(PI.data.prs).find(n=>PI.model(n).F.includes(FID)&&document.querySelector(`section[data-view="obs"] [data-ent="pr:${n}"]`));
  if(!pr)return {ok:false,why:'no visible PR leads to it'};const a=document.querySelector(`section[data-view="obs"] [data-ent="pr:${pr}"]`);
  const s=a.closest('section[data-view]');clicks++;vizNav.show(s.dataset.view,s.dataset.tab,false);await click(a);const k=q('#piDrawer [data-kbopen]');if(k)await click(k);
  const fa=PI.model(pr).areas.find(x=>(PI.data.areas[x].F||[]).includes(FID));const t=q(`#piDrawer [data-kb="frs:${fa}"]`);if(t)await click(t);
  return {ok:false,why:'reachable only by knowing a PR of that feature; no stale label',answer:((q('#piDrawer .pi-kb-meta')||{}).textContent||'').slice(0,120)};});
// T7
await task('T7',async()=>{const rp=q('#vPills [data-t="research"]');if(rp)await click(rp);else{vizNav.show('obs','research');await wait(300);}const c=[...document.querySelectorAll('.rs-card')].find(x=>vis(x)&&x.querySelector('[data-pi^="pr:"]'));
  if(!c)return {ok:false,why:'no research card with a PR'};const sec=c.closest('section');return {ok:true,answer:((sec.querySelector('h2')||{}).textContent+' | '+(c.querySelector('.rs-v')||{}).textContent+' | '+c.querySelector('.rs-tab tbody tr').textContent).slice(0,200)};});
await fetch('/result',{method:'POST',body:JSON.stringify(R)});})();</script>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", default="5673")
    ap.add_argument("--fid", default="F05")
    ap.add_argument("--json")
    a = ap.parse_args()
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    src = PAGE.read_text(encoding="utf-8").replace("<head>", "<head><script>try{localStorage.setItem('obsOnOpen','false');localStorage.setItem('ciMapLang','en')}catch(e){}</script>", 1)
    src = src.replace("<body>", '<body><img src="/hold" alt="" style="position:absolute;width:1px;height:1px;opacity:0">', 1)
    i = src.rindex("</body>")
    body = (src[:i] + PROBE % (json.dumps(a.pr), json.dumps(a.fid)) + src[i:]).encode("utf-8")
    done, box = threading.Event(), {}

    class H(BaseHTTPRequestHandler):   # real clock: the page's load event waits for /hold until the probe has posted
        def log_message(self, *x):
            pass

        def do_GET(self):
            if self.path.startswith("/hold"):
                done.wait(120)
                self.send_response(200); self.send_header("Content-Type", "image/gif"); self.end_headers()
                self.wfile.write(bytes.fromhex("47494638396101000100000000003b"))
                return
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def do_POST(self):
            box["r"] = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
            self.send_response(204); self.end_headers(); done.set()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/p.html#obs/today"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--window-size=1440,900", "--timeout=120000", "--dump-dom", url],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    srv.shutdown()
    if "r" not in box:
        print("no result"); return 2
    R = json.loads(box["r"])
    print(f"page ready (real clock, load + scripts): {R['load_ms']} ms")
    print(f"{'task':4} {'met':4} {'clicks':>6} {'target':>6} {'ms':>6}  answer / why")
    bad = 0
    for t, x in R["tasks"].items():
        met = x.get("ok") and x["clicks"] <= TARGET[t] and (t != "T1" or x.get("fold"))
        bad += not met
        print(f"{t:4} {'yes' if met else 'NO':4} {x['clicks']:>6} {TARGET[t]:>6} {x['ms']:>6}  {x.get('answer') or ''}{'' if met else '  <- ' + (x.get('why') or 'over target')}")
    if a.json:
        Path(a.json).write_text(json.dumps(R, indent=1, ensure_ascii=False), encoding="utf-8")
    print("RESULT:", "ALL MET" if not bad else f"{bad} task(s) not met")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
