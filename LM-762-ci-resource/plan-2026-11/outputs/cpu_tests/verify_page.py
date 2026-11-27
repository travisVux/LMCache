"""Smoke-check 06_PR_TO_CI_VISUAL.html in headless Chrome.

Checks: no JS errors · every view/tab shows its sections · key widgets rendered ·
no untranslated English left in VI mode. Optional screenshots.

Usage:
  python -I -X utf8 verify_page.py                 # checks only
  python -I -X utf8 verify_page.py --shots OUTDIR  # + screenshots of every tab (EN and VI)
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile

from pathlib import Path as _Path  # noqa: E402
# the page sits in Plan/2026-11/, two levels above outputs/cpu_tests/
PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
VIEWS = {"obs": ["today", "hist", "weekly", "impact", "release", "coming", "cost", "overlap", "research"], "r1130": ["baseline", "cpu", "green", "retry", "prs", "track", "repro", "quality"], "gates": ["guide", "tiers"], "cpu": ["overview", "tiers", "cost"], "gpu": ["overview", "tiers", "explore"]}  # merged tabs 2026-11-24; old tabs: check_redirects.py

PROBE = r"""<script>setTimeout(()=>{const r={err:window.__err,tabs:{},landing:location.hash};
const vis=()=>[...document.querySelectorAll('section[data-view]')].filter(x=>!x.classList.contains('vhide')).map(x=>x.querySelector('h2').textContent);
for(const [v,ts] of Object.entries(VIEWS))for(const t of ts){vizNav.show(v,t,false);r.tabs[v+'/'+t]=vis();}
r.widgets={tiles:document.querySelectorAll('#cpuTiles .tile').length,fm:document.querySelectorAll('#fm tr.ar').length,
  tline:document.querySelectorAll('#tline .seg2').length,cards:document.querySelectorAll('.ffc').length,
  nr:document.querySelectorAll('#nr tbody tr').length,stairs:document.querySelectorAll('.stepcol').length,
  matrixCols:document.querySelectorAll('#matrix thead th').length,mm:document.querySelectorAll('#mm .nd').length,
  jobs:document.querySelectorAll('#gJobs tbody tr').length,gloss:document.querySelectorAll('#tierGloss tr').length,impact:document.querySelectorAll('#impOut .box').length,
  wlm:document.querySelectorAll('#wlm tbody tr').length,gfind:document.querySelectorAll('#gfind .ffc').length,desc:document.querySelectorAll('.sdesc').length,
  obsTrain:document.querySelectorAll('#obsTrain .row').length,
  traceFlowSvg:document.querySelectorAll('#obsTracer svg.tr-flow-svg').length,traceStreams:document.querySelectorAll('#obsTracer .tr-stream').length,traceParticles:document.querySelectorAll('#obsTracer .tr-particle').length,traceStages:new Set([...document.querySelectorAll('#obsTracer .tr-fnode[data-stage]')].map(g=>g.dataset.stage)).size,tracePRs:document.querySelectorAll('#obsTracer .tr-fnode[data-stage="2"]').length,traceInsp:document.querySelectorAll('#obsTracer .tr-insp').length,tracePills:document.querySelectorAll('#obsTracer .tr-pill').length,traceLog:document.querySelectorAll('#obsTracer .tr-term').length,traceAgent:document.querySelectorAll('#obsTracer .tr-agent').length,
  opsComing:document.querySelectorAll('[data-ops="coming"] tbody tr').length,opsBase:document.querySelectorAll('#optBase .ops-card').length,opsStages:document.querySelectorAll('#optFlow3 .ops-stage').length,opsOpt:document.querySelectorAll('[data-ops="oc-stages"] tbody tr,[data-ops="og-stages"] tbody tr').length,opsGoals:document.querySelectorAll('[data-ops="og-sum"] .ops-rule').length,
  opsPub:document.querySelectorAll('#optPub tbody tr').length,opsOverlap:document.querySelectorAll('[data-ops="overlap"] tbody tr').length,
  opsTA:document.querySelectorAll('[data-ops^="ta-"] .head').length,
  obSteps:document.querySelectorAll('#obMental .ob-step').length,obChips:document.querySelectorAll('#obMental .ob-achip').length,obCmds:document.querySelectorAll('#obRunbook .ob-cmd').length};
r.qa={handLog:document.querySelectorAll('#obsTracer .tr-term-note').length,
  gateMiss:[...document.querySelectorAll('#obsTracer .tr-fnode[data-stage="4"] .t2')].filter(t=>t.textContent.startsWith('⚠')).length,
  reqTags:[...document.querySelectorAll('#obsTracer .tr-files .gch')].filter(x=>/required for merge/.test(x.textContent)).length,
  segWrap:getComputedStyle(document.querySelector('.seg')).flexWrap};
vizNav.show('cpu','explore',false);window.cpuOpenFile('tests/__qa_missing__.py');r.qa.exEmpty=document.querySelectorAll('#exList .ex-empty').length;
document.getElementById('exQ').value='zzz';vizNav.show('gates','tiers',false);{const gl=document.querySelector('#impOut a[href="#cpu/explore"]');if(gl){gl.click();r.qa.gxQ=document.getElementById('exQ').value;r.qa.gxN=document.querySelectorAll('#exList details').length;}else{r.qa.gxQ='no link';r.qa.gxN=0;}}
document.getElementById('exQ').value='';document.getElementById('exA').value='';document.getElementById('exQ').dispatchEvent(new Event('input'));
r.qa.retired=['now','prs','ci','trend','flaky','gpuload','bug','today'].map(t=>{vizNav.show('obs',t,false);return t+'>'+document.body.dataset.v+'/'+(location.hash.split('/')[1]||'')+':'+vis().length;});
r.qa.idsMissing=['obsBar','obsTrain','obsPub','obsNightly','obsTracer','todaySec','relVerdict','entDrawer','entData','todayData','opsData','r11Data','obsSnap','obsHist','cpuData','gatesData','i18nData'].filter(i=>!document.getElementById(i));
vizNav.show('obs','trend',false);r.qa.aliasTrend=document.body.dataset.v+'/'+(location.hash.split('/')[1]||'');
r.traceDup=document.querySelectorAll('#obsTracer .tr-pipe,#obsTracer .tr-stage').length;r.traceClick=[1,2,3,4,5].map(s=>{const n=document.querySelector(`#obsTracer .tr-fnode[data-stage="${s}"]`);if(!n)return 0;n.dispatchEvent(new MouseEvent('click',{bubbles:true}));const i=document.querySelector('#obsTracer .tr-insp');return i&&i.dataset.stage===String(s)?1:0;}).reduce((a,b)=>a+b,0);
{const rows=[...document.querySelectorAll('#todaySec .tdy-row:not(.hd)')];r.today={rows:rows.length,chips:rows.filter(x=>(x.querySelector('.tdy-v')||{dataset:{}}).dataset.rule).length,ev:rows.filter(x=>x.querySelector('.tdy-ev')).length,tiles:document.querySelectorAll('#todaySec .tdy-tile').length,kpi:document.querySelectorAll('#todaySec .tdy-kpi').length};}
r.p4={evExt:[...document.querySelectorAll('#todaySec .tdy-ev')].filter(x=>!x.dataset.ent).length,rvFiles:document.querySelectorAll('section[data-ops="overlap"] [data-pi][data-pi-view="5"]').length,rvRule:document.querySelectorAll('section[data-ops="overlap"] .tdy-v[data-rule]').length,nrDec:document.querySelectorAll('[data-ops="nr-scope"] .tdy-v[data-rule]').length,nrStart:[...document.querySelectorAll('[data-ops="nr-ck"] .nr-next b')].some(b=>/^(Start|Bắt đầu) \d/.test(b.textContent.trim()))||!!document.querySelector('[data-ops="nr-ck"] .nr-next[data-nr="rc"]'),relRows:document.querySelectorAll('#relVerdict .rel-row:not(.hd) .tdy-v[data-rule]').length,relFirst:(()=>{const x=document.querySelector('section[data-view="obs"][data-tab="release"]');return x?x.id:'';})()};
vizNav.show('r1130','baseline',false);{const hit=document.querySelector('section[data-r11="baseline"] .r11-cost svg rect[fill="transparent"]');if(hit)hit.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,clientX:120,clientY:120}));const t=document.getElementById('r11tip');r.r11={tipInRoot:!!(t&&t.closest('.viz-root')),tipNull:/null/.test(t?t.textContent:'null'),tipText:t?t.textContent.slice(0,60):'',sw:document.querySelectorAll('section[data-r11="baseline"] .r11-sw').length,cpuSw:document.querySelectorAll('section[data-r11="cpu"] .r11-sw').length,never:document.querySelectorAll('section[data-r11="retry"] .r11-nr').length,ext:!!document.querySelector('section[data-r11="baseline"] .r11-ext')};if(t)t.style.display='none';}
if(window.ENT)location.hash='#e/feature/vllm';
I18N.setLang('vi');document.getElementById('vAll').click();document.querySelectorAll('#fm tr.ar').forEach(x=>x.click());
setTimeout(()=>{if(window.ENT){const L=[...document.querySelectorAll('[data-ent]')].filter(e=>!e.closest('.ent-drawer'));const dr=document.getElementById('entDrawer');
  r.ent={links:L.length,bad:[...new Set(L.filter(e=>!ENT.has(e.dataset.ent)).map(e=>e.dataset.ent))].slice(0,8),kinds:[...new Set(L.map(e=>e.dataset.ent.split(':')[0]))].sort(),
   route:dr.classList.contains('on')&&(dr.querySelector('.ent-id')||{}).textContent==='vllm'&&location.hash==='#e/feature/vllm',routeDown:dr.querySelectorAll('.ent-nb').length,health:document.querySelectorAll('#entHealth tbody tr').length};
  const p=L.find(e=>e.dataset.ent.startsWith('pr:')&&ENT.out(e.dataset.ent).some(x=>x.rel==='changes'));
  if(p){p.click();const pi=document.getElementById('piDrawer');  // a PR link opens the PR Inspector (2026-11-24), not the entity card
   r.ent.card=!!pi&&pi.classList.contains('on')&&((pi.querySelector('#piTitle')||{}).textContent||'').startsWith('#'+p.dataset.ent.slice(3)+' ');
   document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));const fk=(ENT.out(p.dataset.ent).find(x=>x.rel==='changes')||{}).b;
   if(fk){openEntity(fk);const t=dr.querySelector('.ent-nb[data-open^="test:"]');if(t){t.click();r.ent.trip=(dr.querySelector('.ent-kind')||{}).textContent+' '+dr.querySelectorAll('.ent-nb').length;}}
   document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));r.ent.esc=!dr.classList.contains('on')&&!pi.classList.contains('on')&&!/^#e\//.test(location.hash);}}
 const SKIP='code,pre,script,style,[data-ent^="ci:"],.r11-lab,.r11-wf,#mm,.p,.det-files,#slow .l,.tf-body .doc,.tt td,#nr td.p,.lang,.obsraw,.obs-set input';
 const left=new Set();const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
 while(n=w.nextNode()){const t=n.nodeValue.trim();const p=n.parentElement;if(!t||!p||p.closest(SKIP))continue;
  {const g=p.closest('.ent-t');if(/[À-ỹ]/.test(g?g.textContent:t))continue;}  // a sentence split by entity links is judged as a whole
  const hits=(t.match(/(?<![\p{L}\-_])(the|is|are|and|of|to|on|when|only|with|for|runs|files|passed|show|see|per|not|in|a)(?![\p{L}\-_])/giu)||[]).length;
  if(hits>=2)left.add(t.slice(0,100));}
 r.untranslated=[...left];I18N.setLang('en');
 const pre=document.createElement('pre');pre.id='probeOut';pre.className='no-ent';pre.textContent=JSON.stringify(r);document.body.appendChild(pre);},300);},500)</script></body>"""


def chrome(args):
    return subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=15000"] + args,   # 15 s: the entity linkifier walks every tab
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def main():
    src = open(PAGE, encoding="utf-8").read()
    tmp = tempfile.mkdtemp(prefix="verify_page_")
    probe = os.path.join(tmp, "probe.html")
    page = src.replace("<head>", '<head><script>try{localStorage.setItem("obsOnOpen","false")}catch(e){}window.__err=[];addEventListener("error",e=>__err.push(e.message));</script>', 1)
    page = page.replace("</body>", PROBE.replace("VIEWS", json.dumps(VIEWS)))
    open(probe, "w", encoding="utf-8").write(page)
    out = chrome(["--dump-dom", "file:///" + probe.replace("\\", "/")]).stdout
    m = re.search(r'<pre id="probeOut"[^>]*>(.*?)</pre>', out, re.S)
    if not m:
        print("FAIL: probe did not finish (page script crashed?)")
        return 1
    r = json.loads(html.unescape(m.group(1)))
    ok = True
    print("JS errors:", r["err"] or "none"); ok &= not r["err"]
    # standards mode: anything before <!doctype> (a stray key press) puts the page in quirks mode, where tables lose the text colour (dark mode)
    lead = src.lstrip("﻿")[:15].lower()
    print("doctype first:", lead.startswith("<!doctype html>")); ok &= lead.startswith("<!doctype html>")
    for k, v in r["tabs"].items():
        print(f"  {k:14s} {len(v)} section(s): " + " | ".join(x[:28] for x in v))
        ok &= len(v) > 0
    print("widgets:", r["widgets"], "traceDup:", r.get("traceDup"), "traceClick:", r.get("traceClick"))
    ok &= all(v > 0 for v in r["widgets"].values()) and r["widgets"]["traceStages"] == 5 and r.get("traceDup", 1) == 0 and r.get("traceClick", 0) == 5
    # QA probes (2026-11-09): data checks that catch wrong data, not only "count > 0"
    qa = r.get("qa", {})
    hist = json.loads(re.search(r'<script id="obsHist" type="application/json">(.*?)</script>', src, re.S).group(1))
    rep_ = hist.get("report") or {}
    rels = rep_.get("release_trace") or []
    exp_gate_miss = sum(1 for g in (next((x for x in rels if x["tag"] == "v0.5.7rc4"), {"gates": []})["gates"][:4]) if g.get("test_missing"))
    n_miss = sum(len(p.get("missing") or []) for x in rels for p in x["prs"]) + sum(1 for x in rels for g in x["gates"] if g.get("test_missing"))
    n_rng = sum(1 for x in rels for p in x["prs"] if p.get("range_ok") is False)
    print(f"qa: tracer releases verified against git {sum(1 for x in rels if x.get('ref'))}/{len(rels)} · flagged paths {n_miss} · PRs outside range {n_rng}"
          f" · required checks {len((rep_.get('required_checks') or {}).get('names') or [])}")
    print("qa:", qa)
    ok &= bool(rels) and all(x.get("ref") for x in rels) and bool((rep_.get("required_checks") or {}).get("names"))
    ok &= qa.get("handLog", 0) >= 1 and qa.get("reqTags", 0) >= 1 and qa.get("gateMiss", -1) == exp_gate_miss
    ok &= qa.get("exEmpty") == 1 and qa.get("gxQ") == "" and qa.get("gxN", 0) > 0 and qa.get("segWrap") == "wrap"
    # retired tabs (removed 2026-11-13, P5): their old hashes must land on a visible tab with sections; the kept ids must exist
    ok &= all(x.split(":")[1] != "0" and x.split(">")[1].split(":")[0] in ("obs/" + t for t in VIEWS["obs"]) for x in qa.get("retired") or ["x>y:0"])
    ok &= not qa.get("idsMissing")
    ok &= qa.get("aliasTrend") == "obs/release"  # retired tab links land on a visible tab
    ok &= r["widgets"]["opsBase"] >= 6 and r["widgets"]["opsStages"] == 4 and r["widgets"]["opsGoals"] >= 5 and r["widgets"]["opsTA"] == 2
    # v2 entity index (build_entities.py): all level kinds present, the 9 first relations drawn, every edge resolves
    em = re.search(r'<script id="entData" type="application/json">(.*?)</script>', src, re.S)
    if not em:
        print("entities: MISSING (run build_entities.py first)"); ok = False
    else:
        ent = json.loads(em.group(1))
        kinds = {n["kind"] for n in ent["nodes"].values()}
        rels = {ent["R"][e[2]] for e in ent["E"]}
        bad = sum(1 for e in ent["E"] if not (0 <= e[0] < len(ent["K"]) and 0 <= e[1] < len(ent["K"]) and ent["K"][e[0]] in ent["nodes"] and ent["K"][e[1]] in ent["nodes"]))
        need_k = {"release", "pr", "feature", "ci", "build", "test", "bug"}
        need_r = {"contains", "changes", "ran", "runs", "runs_suite", "covered_by", "fails_with", "fixed_by", "shipped_in"}
        print(f"entities: {len(ent['nodes'])} nodes · {len(ent['E'])} edges · kinds {len(kinds)} · relations {len(rels)} · unresolved edges {bad} · made {ent.get('made')}")
        ok &= need_k <= kinds and need_r <= rels and bad == 0
    # v2 entity card + linkify (build_entity_ui.py): every on-page entity link resolves, the route and the card work
    e2 = r.get("ent") or {}
    print("entity links:", e2)
    ok &= e2.get("links", 0) > 500 and not e2.get("bad") and bool(e2.get("route")) and bool(e2.get("card")) and bool(e2.get("esc")) \
        and bool(e2.get("trip")) and e2.get("health", 0) > 10 and {"pr", "feature", "test", "build"} <= set(e2.get("kinds") or [])
    td = r.get("today") or {}
    print("today:", td, "| landing:", r.get("landing"))
    ok &= r.get("landing") == "#obs/today" and td.get("kpi") == 1 and td.get("rows", 0) >= 1 and td.get("chips") == td.get("rows") and td.get("ev") == td.get("rows")
    p4 = r.get("p4") or {}
    print("p4:", p4)
    ok &= p4.get("evExt") == td.get("rows") and p4.get("rvFiles", 0) > 0 and p4.get("rvRule", 0) > 0 and (p4.get("nrDec", 0) > 0 or p4.get("nrStart") is True) and p4.get("relRows", 0) > 0 and p4.get("relFirst") == "relVerdict"
    # every generator's CSS block must be in the page (blocks nested in OBS CSS vanish when build_observe runs alone)
    css = src[src.find("<style>"):src.find("</style>")]
    miss_css = [k for k in ("CPU-TESTS", "GATES", "ONBOARD", "OBS", "OPS", "R1130", "I18N", "TODAY", "ENTUI", "NAV") if f"/* {k}:CSS:START */" not in css]
    print("CSS blocks missing:", miss_css or "none")
    ok &= not miss_css
    r11 = r.get("r11") or {}
    print("r1130:", r11)
    ok &= bool(r11.get("tipInRoot")) and not r11.get("tipNull") and r11.get("sw") == 4 and r11.get("cpuSw") in (2, 4) and r11.get("never", 0) > 0 and bool(r11.get("ext"))
    print("untranslated in VI:", len(r["untranslated"]))
    for x in r["untranslated"]:
        print("   -", x)
    ok &= not r["untranslated"]

    if "--shots" in sys.argv:
        outdir = os.path.abspath(sys.argv[sys.argv.index("--shots") + 1])
        os.makedirs(outdir, exist_ok=True)
        for lang in ("en", "vi"):
            f = os.path.join(tmp, f"page_{lang}.html")
            open(f, "w", encoding="utf-8").write(src.replace("<head>", f'<head><script>try{{localStorage.setItem("ciMapLang","{lang}")}}catch(e){{}}</script>', 1))
            for v, ts in VIEWS.items():
                for t in ts:
                    png = os.path.join(outdir, f"{lang}_{v}_{t}.png")
                    chrome(["--hide-scrollbars", "--window-size=1280,1400", f"--screenshot={png}", "file:///" + f.replace("\\", "/") + f"#{v}/{t}"])
        print("screenshots ->", outdir)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
