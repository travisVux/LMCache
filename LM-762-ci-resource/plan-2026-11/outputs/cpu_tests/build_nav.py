"""Add GPU/CPU view switch + sub-tabs to 06_PR_TO_CI_VISUAL.html (idempotent).

Each <section> is tagged with data-view / data-tab from its h2 number.
"""
import json
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling modules also under python -I

from pathlib import Path as _Path  # noqa: E402
# the page sits in Plan/2026-11/, two levels above outputs/cpu_tests/
PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")

# h2 number -> (view, tab)
# Sections carry data-view / data-tab in their own HTML; this map only tags untagged GPU sections.
MAP = {
    "1": ("gpu", "overview"), "2": ("gpu", "overview"),
    "3": ("gpu", "tiers"), "4": ("gpu", "tiers"), "5": ("gpu", "tiers"),
    "6": ("gpu", "cost"), "7": ("gpu", "cost"),
    "8": ("gpu", "findings"), "9": ("gpu", "explore"),
}

CSS = r"""
/* NAV:CSS:START */
.vnav{position:sticky;top:0;z-index:5;margin:0 -32px 4px;padding:12px 32px 10px;background:color-mix(in oklab,var(--surface-0) 88%,transparent);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-bottom:1px solid var(--border)}
.vnav .row{display:flex;gap:14px;align-items:center;flex-wrap:wrap;max-width:1180px;margin:0 auto}
.seg{display:inline-flex;flex-wrap:wrap;max-width:100%;box-sizing:border-box;background:var(--surface-2);border-radius:12px;padding:4px;gap:4px}
@media (max-width:700px){table.gate,table.fm{display:block;overflow-x:auto;max-width:100%}}
/* phone width (checked with check_mobile.py at a real 390 px): staircase, class matrix, test-explorer rows and filters */
@media (max-width:700px){.stairs{overflow-x:auto;max-width:100%}table.matrix,table.gc{display:block;overflow-x:auto;max-width:100%}select{max-width:100%}.vnav~* label,section label{white-space:normal;max-width:100%}.tf>summary{grid-template-columns:minmax(0,1fr) auto!important;row-gap:2px}.tf>summary .n{white-space:normal!important}.ffg{grid-template-columns:minmax(0,1fr)!important}.bars{overflow-x:auto;max-width:100%}.slow{grid-template-columns:minmax(0,46%) 1fr 54px}}
.seg button{all:unset;cursor:pointer;display:flex;align-items:center;gap:10px;padding:8px 16px 8px 12px;border-radius:9px;color:var(--text-secondary)}
.seg button:hover{color:var(--text-primary)}
.seg button:focus-visible{outline:2px solid var(--series-1);outline-offset:1px}
.seg button[aria-selected="true"]{background:var(--surface-1);color:var(--text-primary);box-shadow:0 1px 3px rgba(0,0,0,.14),0 0 0 1.5px var(--ring)}
.seg button[aria-selected="false"] .ic{opacity:.45;filter:saturate(.4)}
.seg button[aria-selected="false"] .tx small{opacity:.8}
.seg .ic{width:30px;height:30px;border-radius:8px;display:grid;place-items:center;font-size:11px;font-weight:800;letter-spacing:.02em;color:#fff}
.seg .tx b{display:block;font-size:13.5px;font-weight:650;line-height:1.2}
.seg .tx small{display:block;font-size:11.5px;color:var(--text-muted);line-height:1.25}
.pills{display:flex;gap:2px;flex-wrap:wrap;margin-top:10px;max-width:1180px;margin-left:auto;margin-right:auto}
.pills button{all:unset;cursor:pointer;font-size:12.5px;padding:6px 12px;border-radius:8px;color:var(--text-secondary);position:relative;white-space:nowrap}
.pills button:hover{background:var(--surface-2);color:var(--text-primary)}
.pills button:focus-visible{outline:2px solid var(--series-1)}
.pills button[aria-selected="true"]{color:var(--text-primary);font-weight:650;background:var(--surface-1);box-shadow:0 0 0 1px var(--border)}
.pills button[aria-selected="true"]::after{content:"";position:absolute;left:12px;right:12px;bottom:-1px;height:2px;border-radius:2px;background:var(--accent,var(--series-1))}
.pills .k{font-size:10.5px;color:var(--text-muted);margin-right:6px;font-variant-numeric:tabular-nums}
.pills .grp{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);align-self:center;padding:0 4px 0 12px}
.pills .pg{display:inline-flex;gap:2px;align-items:center;flex-wrap:wrap}
.pills .pg:first-child .grp{padding-left:2px}
.pills .c{font-size:10.5px;color:var(--text-muted);margin-left:6px;background:var(--surface-2);border-radius:999px;padding:0 6px}
.vnav .sp{flex:1}
.vnav label.all{font-size:12px;color:var(--text-secondary);display:flex;gap:6px;align-items:center;cursor:pointer}
.vnav kbd{font:11px ui-monospace,Consolas,monospace;border:1px solid var(--border);border-bottom-width:2px;border-radius:4px;padding:0 4px;color:var(--text-muted)}
[data-view].vhide{display:none!important}
.vshow{animation:vfade .22s ease}
@keyframes vfade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.tile[data-goto]{cursor:pointer;transition:border-color .15s,transform .15s}
.tile[data-goto]:hover{border-color:var(--text-muted);transform:translateY(-1px)}
.tile[data-goto] .s::after{content:"  →";color:var(--text-muted)}
.goto-btn{all:unset;cursor:pointer;display:inline-block;margin-top:10px;font-size:12.5px;font-weight:600;color:var(--series-1);padding:5px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface-1)}
.goto-btn:hover{border-color:var(--series-1)}
@media (prefers-reduced-motion:reduce){.vshow{animation:none}}
/* CI cost CPU / GPU switch (merged tab, 2026-11-24) */
.nv-hw{display:flex;gap:4px;flex-wrap:wrap;max-width:100%;box-sizing:border-box;margin:8px 0 4px;background:var(--surface-2);border-radius:10px;padding:4px;width:fit-content}
.nv-hw button{all:unset;cursor:pointer;font-size:12.5px;padding:6px 12px;border-radius:8px;color:var(--text-secondary)}
.nv-hw button[aria-pressed="true"]{background:var(--surface-1);color:var(--text-primary);font-weight:650;box-shadow:0 0 0 1px var(--border)}
.nv-hw button:focus-visible{outline:2px solid var(--series-1)}
/* round 2 C2: phones get a compact header so the verdict is on the first screen; E10: focus never under the sticky nav */
@media (min-width:768px) and (min-height:501px){html{scroll-padding-top:260px}}
@media (max-width:767px){header .sub,#hdrSub,.ux-built{display:none}header h1{font-size:17px;line-height:1.25;margin:2px 0}
.vnav .seg .tx small{display:none}.vnav .seg button{padding:6px 8px}.vnav .seg .ic{display:none}
.vnav .pills{flex-wrap:nowrap!important;overflow-x:auto;scrollbar-width:thin;padding-bottom:4px}.vnav .pills .pg{display:contents}.vnav .pills .grp{display:none}
.vnav .pills button{flex:0 0 auto}.vnav .pills .c{display:none}.vnav label.all{display:none}}
/* NAV:CSS:END */
"""

HTML = r"""
<!-- NAV:HTML:START -->
<nav class="vnav" aria-label="Page views">
  <div class="row">
    <div class="seg" role="tablist" aria-label="View" title="Keys: O = management · T / U / E = exploration · ← → = tab · L = EN / VI">
      <button role="tab" data-v="obs" aria-selected="true"><span class="tx"><b>Release</b><small>Releases · trace · next release · CI cost · rebase risk</small></span></button>
      <button role="tab" data-v="explore" aria-selected="false"><span class="tx"><b>Tests &amp; gates</b><small>Quality gates · CPU tests · GPU tests</small></span></button>
      <button role="tab" data-v="r1130" aria-selected="false" title="LM-1130 · PR CI telemetry &amp; baseline"><span class="tx"><b>CI Baseline</b><small>GPU · CPU usage · time to green · retry &amp; waste</small></span></button>
    </div>
    <span class="sp"></span>
    <label class="all"><input type="checkbox" id="vAll"> Show all sections</label>
  </div>
  <div class="pills" role="tablist" aria-label="Sections" id="vPills"></div>
</nav>
<!-- NAV:HTML:END -->
"""

JS = r"""
<!-- NAV:JS:START -->
<script>
(function(){
  {const m=location.hash.match(/^#pr[:\/](\d+)$/);if(m)history.replaceState(null,'','#e/pr/'+m[1]);}   // round 2: #pr:N / #pr/N = the PR Inspector
  const TABS={
    obs:[['today','Today','0','Decide'],['hist','History','1','Decide'],['weekly','Weekly full build','7','Decide'],['release','Releases','2','Release'],['coming','Next release','3','Release'],['cost','CI cost','4','CI cost'],['impact','CI impact','8','CI cost'],['overlap','Rebase risk','5','Merge safety'],['research','Research','6','Research']],
    gates:[['guide','Guide','0a–1'],['tiers','Tiers & impact','2–5']],
    cpu:[['overview','Overview','1–2'],['tiers','Coverage','3–5 · 8'],['cost','Cost & findings','6–7']],
    gpu:[['overview','Overview','1–2 · 7'],['tiers','Workloads & cost','3–6'],['explore','Map','8']],
    r1130:[['baseline','GPU · CPU usage','1–2','Usage'],['flow','Merge flow','3–6','Flow'],['method','Method','7–8','Method']]
  };
  // merged tabs (2026-11-24, approved table): a tab shows every section whose data-tab is in its member list.
  // Sections keep their own data-view / data-tab (builders use them); only the nav groups them.
  const MEMBERS={r1130:{baseline:['baseline','cpu'],flow:['green','retry','prs','track'],method:['repro','quality']},obs:{release:['release','trace'],cost:['opt_cpu','opt_gpu']},cpu:{tiers:['tiers','explore'],cost:['cost','findings']},gpu:{overview:['overview','findings'],tiers:['tiers','cost']}};
  const mem=(v,t)=>(MEMBERS[v]&&MEMBERS[v][t])||[t];
  // old tab -> element to scroll to inside the merged tab ('@gpu' / '@cpu' = CI cost hardware switch)
  const SUBT={'obs/trace':'obsTracer','obs/tracer':'obsTracer','obs/opt_gpu':'@gpu','obs/gpuload':'@gpu','obs/gpu':'@gpu','obs/opt_cpu':'@cpu','obs/ci':'@cpu','obs/optimal':'@cpu','obs/publicci':'@cpu',
    'cpu/explore':'exQ','cpu/findings':'ffg','cpu/failfast':'ffg','gpu/findings':'gfind','gpu/cost':'bars'};
  let hw='cpu';
  const EXTRA={};   // round 3 (D_identity 3.6): no count / version chips on tabs
  const EXP=['gates','cpu','gpu'],EXPN={gates:'Gates',cpu:'CPU tests',gpu:'GPU tests'};
  const top=v=>v==='obs'||v==='r1130'?v:'explore';
  let lastExp='gates';try{const x=localStorage.getItem('ciMapExp');if(EXP.includes(x))lastExp=x;}catch(e){}
  const flat=()=>top(st.v)!=='explore'?TABS[st.v].map(x=>[st.v,x[0]]):EXP.flatMap(v=>TABS[v].map(x=>[v,x[0]]));
  const SUB={
    obs:"Release owner's view: releases, release trace, the next release, CI cost and the rebase risk of open PRs after the last 24 h of merges. Data comes from local runs only.",
    r1130:"PR CI telemetry & baseline synced from raw GitHub Actions and Buildkite data",
    gates:'Architecture guide, merge and release gates, test tiers and change impact. Terms: MP = multiprocess GPU end-to-end CI · k3 = Buildkite GPU cluster · L0–L2 = test tiers, fast → full.',
    cpu:'Unit tests: 540 files in 28 areas, coverage, and CPU vs. GPU runners (commit 05d8eb84). Terms: MP = multiprocess GPU end-to-end CI · k3 = Buildkite GPU cluster · L0–L2 = test tiers, fast → full.',
    gpu:'Multiprocess (MP) GPU end-to-end CI: workloads, cost (3,099 GPU-h / 30 d) and the plan. Terms: MP = multiprocess GPU end-to-end CI · k3 = Buildkite GPU cluster · L0–L2 = test tiers, fast → full.'
  };
  const ACC={gates:'var(--text-secondary)',gpu:'var(--series-1)',cpu:'var(--series-3)',obs:'var(--series-2)',r1130:'var(--series-3)'};
  // Releases & trace: decision first (verdict), then the release train, its health, then the trace (DOM order = display order)
  {const S=x=>{const e=document.getElementById(x);return e&&e.closest('section[data-view]');};
   const L=[S('relVerdict'),S('obsTrain'),document.querySelector('section[data-ops="ta-release"]'),S('obsTracer'),document.querySelector('section[data-ops="ta-trace"]')].filter(Boolean);
   if(L.length>1){const first=L.reduce((a,b)=>(a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_PRECEDING)?b:a);const ph=document.createComment('release-order');first.parentNode.insertBefore(ph,first);L.forEach(e=>ph.parentNode.insertBefore(e,ph));ph.remove();}}
  // CI cost: one tab, CPU (GitHub Actions) / GPU (Buildkite) switch above the sections
  {const f=document.querySelector('section[data-ops="oc-sum"]');
   if(f&&!document.getElementById('nvHw')){const d=document.createElement('div');d.id='nvHw';d.className='nv-hw';d.dataset.view='obs';d.dataset.tab='opt_cpu';d.setAttribute('role','group');d.setAttribute('aria-label','CI cost');
     d.innerHTML='<button type="button" data-hw="cpu">CPU · GitHub Actions</button><button type="button" data-hw="gpu">GPU · Buildkite</button>';f.parentNode.insertBefore(d,f);}}
  const secs=[...document.querySelectorAll('[data-view]')];
  secs.forEach((s,i)=>{if(s.tagName==='SECTION'&&!s.id)s.id='sec-'+s.dataset.view+'-'+(s.dataset.tab||'x')+'-'+i;});
  const pills=document.getElementById('vPills'), all=document.getElementById('vAll'), sub=document.getElementById('hdrSub');
  let st={v:'obs',t:'today'};   // landing tab: Today (decision inbox); a #view/tab hash still wins

  const ALIAS={
    // retired tabs (2026-11-10) land on the closest new tab, so old links keep working
    // merged tabs (2026-11-24): trace -> release, opt_cpu/opt_gpu -> cost, cpu explore -> tiers, cpu findings -> cost, gpu findings -> overview, gpu cost -> tiers
    obs:{release:'release',now:'today',today:'today',desk:'today',hist:'hist',history:'hist',report:'release',trend:'release',trace:'release',tracer:'release',
      coming:'coming',prs:'coming',fixed:'coming',merged:'coming',optimal:'cost',opt_cpu:'cost',opt_gpu:'cost',ci:'cost',gpuload:'cost',gpu:'cost',publicci:'cost',cost:'cost',
      overlap:'overlap',flaky:'overlap',bug:'overlap','24h':'overlap',research:'research',intake:'research',
      weekly:'weekly',full:'weekly','weekly-full':'weekly',weekly_full_build:'weekly',wfb:'weekly',   // 2026-11-26: Weekly full build tab
      impact:'impact','ci-impact':'impact','before-after':'impact',beforeafter:'impact'},   // 2026-11-26: CI impact (before / after) tab
    cpu:{matrix:'tiers',notrun:'tiers',failfast:'cost',findings:'cost',cost:'cost',explore:'tiers',overview:'overview',tiers:'tiers'},
    gpu:{mindmap:'explore',tiers:'tiers',cost:'tiers',findings:'overview',overview:'overview',explore:'explore'},
    // round 2 (B): 8 report tabs -> 3; the old tab scrolls to its own section inside the merged tab
    r1130:{baseline:'baseline',cpu:'baseline',green:'flow',retry:'flow',prs:'flow',track:'flow',flow:'flow',repro:'method',quality:'method',method:'method'}
  };
  function parseHash(){
    if(/^#weekly(?:[-_]full(?:[-_]build)?)?\/?$/i.test(location.hash))history.replaceState(null,'','#obs/weekly');   // short link #weekly
    if(/^#(?:ci[-_]?)?impact\/?$|^#before[-_]?after\/?$/i.test(location.hash))history.replaceState(null,'','#obs/impact');   // short links #impact #ci-impact #before-after
    const h=location.hash.slice(1).split('/');
    if(TABS[h[0]]){
      st.v=h[0];
      const target=(ALIAS[h[0]]&&ALIAS[h[0]][h[1]])||h[1];
      st.t=TABS[h[0]].some(x=>x[0]===target)?target:TABS[h[0]][0][0];
      if(st.v==='obs'&&st.t==='cost') hw=(h[2]==='gpu'||SUBT['obs/'+h[1]]==='@gpu')?'gpu':'cpu';
      return h[1];
    }
    return null;
  }
  const initSub=parseHash();

  function count(v,t){return secs.filter(s=>s.dataset.view===v&&mem(v,t).includes(s.dataset.tab)&&s.tagName==='SECTION').length;}
  const inTab=s=>s.dataset.view===st.v&&mem(st.v,st.t).includes(s.dataset.tab)&&(!(st.v==='obs'&&st.t==='cost')||s.id==='nvHw'||s.dataset.tab===(hw==='gpu'?'opt_gpu':'opt_cpu'));
  function drawPills(){
    pills.replaceChildren(); pills.style.removeProperty('--accent');   // round 3: one accent for every view
    const rows=top(st.v)!=='explore'?TABS[st.v].map(x=>[st.v,...x]):EXP.flatMap(v=>TABS[v].map(x=>[v,x[0],x[1],x[2],EXPN[v]]));
    let grp=null,box=pills;
    const sampleOnly=()=>{const cs=[...document.querySelectorAll('section[data-view="obs"][data-tab="research"] .rs-card')];return cs.length>0&&cs.every(c=>c.querySelector('.rs-badge'));};
    rows.forEach(([v,id,name,nums,g])=>{ if(v==='obs'&&id==='research'&&!(st.v==='obs'&&st.t==='research')&&sampleOnly()) return;
      if(g&&g!==grp){grp=g;box=document.createElement('span');box.className='pg';const s=document.createElement('span');s.className='grp';s.textContent=g;box.appendChild(s);pills.appendChild(box);}
      const on=v===st.v&&id===st.t;
      const b=document.createElement('button'); b.setAttribute('role','tab'); b.dataset.t=id; b.dataset.v=v; b.id='tab-'+v+'-'+id; b.setAttribute('aria-selected',String(on)); b.tabIndex=on?0:-1;
      {const ids=secs.filter(s=>s.dataset.view===v&&mem(v,id).includes(s.dataset.tab)&&s.tagName==='SECTION').map(s=>s.id);if(ids.length)b.setAttribute('aria-controls',ids.join(' '));}
      const k=document.createElement('span'); k.className='k'; k.textContent=nums; if(v==='obs'||v==='r1130'){b.append(k);b.append(document.createTextNode(' '));} b.append(document.createTextNode(name));
      const ex=(EXTRA[v]||{})[id]; if(ex){const c=document.createElement('span');c.className='c';c.textContent=ex;b.append(document.createTextNode(' '));b.appendChild(c);}
      b.addEventListener('click',()=>{show(v,id);const nb=document.getElementById('tab-'+v+'-'+id);if(nb)nb.focus({preventScroll:true});}); box.appendChild(b);
    });
  }
  function scrollToSub(target){
    if(!target) return;
    const sub=SUBT[st.v+'/'+target];
    if(sub&&sub[0]==='@') return;   // CI cost switch: already applied, stay at the top of the tab
    setTimeout(()=>{
      let el=sub?document.getElementById(sub):null;
      if(el){if(sub!=='exQ'){const s=el.closest('section[data-view]');if(s)el=s;}}
      else if(target==='notrun') el=document.getElementById('nrSub')||document.getElementById('nr');
      else if(target==='matrix') el=document.getElementById('fm');
      else if(target==='failfast') el=document.getElementById('ffg');
      else if(target==='mindmap') el=document.getElementById('mmFit');
      else if(target!==st.t&&mem(st.v,st.t).includes(target)) el=document.querySelector('section[data-view="'+st.v+'"][data-tab="'+target+'"]');   // an old tab inside a merged tab: its own section (never the tab itself: that would scroll the page on every open)
      if(el) el.scrollIntoView({behavior:(matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'),block:'start'});
    },60);
  }
  function apply(scroll,targetSub){
    const showAll=all.checked;
    secs.forEach(s=>{const on=showAll||inTab(s); const was=!s.classList.contains('vhide'); s.classList.toggle('vhide',!on); if(on&&!was){s.classList.remove('vshow'); void s.offsetWidth; s.classList.add('vshow');}});
    secs.forEach(s=>{if(s.tagName!=='SECTION')return;const act=!showAll&&inTab(s);if(act){s.setAttribute('role','tabpanel');s.setAttribute('aria-labelledby','tab-'+st.v+'-'+st.t);}else{s.removeAttribute('role');s.removeAttribute('aria-labelledby');}});
    document.querySelectorAll('.seg [data-v]').forEach(b=>{const on=b.dataset.v===top(st.v); b.setAttribute('aria-selected',String(on)); b.tabIndex=on?0:-1;});
    pills.hidden=showAll; drawPills(); if(sub) sub.textContent=SUB[st.v];
    document.body.dataset.v=st.v; document.body.dataset.all=showAll?'1':'0'; document.querySelectorAll('#nvHw [data-hw]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.hw===hw)));
    dispatchEvent(new CustomEvent('viewchange',{detail:{v:st.v,t:st.t,members:mem(st.v,st.t),hw}}));
    {const h='#'+st.v+'/'+st.t+(st.v==='obs'&&st.t==='cost'&&hw==='gpu'?'/gpu':''); if(!/^#(e\/|ux$|decision$|docs$)/.test(location.hash)){if(PUSH&&location.hash!==h) history.pushState(null,'',h); else history.replaceState(null,'',h);} PUSH=false;} /* #e/<kind>/<id> = entity card route (build_entity_ui.py) */ try{localStorage.setItem('ciMapView7',JSON.stringify(st));}catch(e){}
    /* round 2 C9: no auto "Fit" on open (it shrank labels to 6-7 px); the map opens at its readable default, Fit stays a button */
    if(targetSub) scrollToSub(targetSub);
    else if(scroll){const nav=document.querySelector('.vnav'); const y=nav.getBoundingClientRect().top+scrollY; if(scrollY>y) scrollTo({top:y,behavior:(matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth')});}
  }
  let PUSH=false;   // round 2 (D): a tab change by the user adds a history entry, so Back returns to the previous tab
  function show(v,t,scroll=true,targetSub=null){ PUSH=true; if(v==='explore'){v=lastExp;t=null;}
    if(!TABS[v]) return;   // not a view (e.g. a section-local data-goto such as next_release.js 'nr-scope')
    if(t&&TABS[v]&&!TABS[v].some(x=>x[0]===t)){const a=ALIAS[v]&&ALIAS[v][t];const o=t;t=a&&TABS[v].some(x=>x[0]===a)?a:TABS[v][0][0];
      if(SUBT[v+'/'+o]){if(v==='obs'&&t==='cost')hw=SUBT[v+'/'+o]==='@gpu'?'gpu':'cpu';if(!targetSub)targetSub=o;}
      else if(o!==t&&mem(v,t).includes(o)&&!targetSub)targetSub=o;} if(EXP.includes(v)){lastExp=v;try{localStorage.setItem('ciMapExp',v);}catch(e){}} if(v!==st.v){st.v=v; st.t=t||TABS[v][0][0];} else if(t){st.t=t;} apply(scroll,targetSub); }
  window.vizNav={show,members:mem,get state(){return {v:st.v,t:st.t,hw};}};
  window.addEventListener('hashchange',()=>{if(/^#(e\/|ux$|decision$|docs$)/.test(location.hash))return; const subT=parseHash(); apply(true,subT);});
  document.querySelectorAll('.seg [data-v]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.v)));
  all.addEventListener('change',()=>apply(false));
  document.addEventListener('click',e=>{const g=e.target.closest('[data-goto]'); if(g){const [v,t]=g.dataset.goto.split('/'); if(TABS[v]||v==='explore') show(v,t);}});
  document.addEventListener('click',e=>{const b=e.target.closest('#nvHw [data-hw]'); if(b){hw=b.dataset.hw; apply(false);}});
  document.addEventListener('keydown',e=>{
    const tg=e.target&&e.target.closest?e.target:document.body;
    if(tg.closest('input,select,textarea,summary')||e.ctrlKey||e.metaKey||e.altKey) return;
    const k=e.key.toLowerCase();
    if(k==='m') show('gates','guide'); else if(k==='t') show('gates','overview'); else if(k==='g'||k==='e') show('gpu'); else if(k==='c'||k==='u') show('cpu'); else if(k==='o') show('obs','today'); else if(k==='r') show('obs','trace');
    else if((e.key==='ArrowRight'||e.key==='ArrowLeft')&&tg.closest('.seg')){ const V=[...document.querySelectorAll('.seg [data-v]')], i=V.findIndex(b=>b.dataset.v===top(st.v)), j=(i+(e.key==='ArrowRight'?1:-1)+V.length)%V.length; e.preventDefault(); show(V[j].dataset.v); V[j].focus(); }
    else if(e.key==='ArrowRight'||e.key==='ArrowLeft'){ if(!tg.closest('.pills')&&tg!==document.body) return;
      const L=flat(), i=L.findIndex(x=>x[0]===st.v&&x[1]===st.t), j=(i+(e.key==='ArrowRight'?1:-1)+L.length)%L.length; e.preventDefault(); show(L[j][0],L[j][1]); pills.querySelector('[aria-selected="true"]').focus(); }
  });
  apply(false,initSub);
})();
</script>
<!-- NAV:JS:END -->
"""


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor) if before else page.index(anchor) + len(anchor)
    return page[:i] + ("" if before else "\n") + block.strip() + ("\n" if before else "") + page[i:]


def tag_sections(page):
    def fix(m):
        if "data-view=" in m.group(0):
            return m.group(0)
        tag = m.group(0)
        ahead = page[m.end(): m.end() + 400]
        n = re.search(r"<h2[^>]*>([0-9]+[a-z]?) ·", ahead)
        if not n or n.group(1) not in MAP:
            return tag
        v, t = MAP[n.group(1)]
        return tag[:-1] + f' data-view="{v}" data-tab="{t}">'
    page = re.sub(r"<section\b[^>]*>", fix, page)
    # GPU KPI tiles under the header belong to the GPU overview tab
    page = re.sub(r'<div class="tiles"(?: data-view="gpu" data-tab="overview")?>', '<div class="tiles" data-view="gpu" data-tab="overview">', page, count=1)
    if 'id="hdrSub"' not in page:
        page = page.replace('<p class="sub">How a PR becomes mergeable', '<p class="sub" id="hdrSub">How a PR becomes mergeable', 1)
    page = re.sub(r"<title>.*?</title>", "<title>Release Desk</title>", page, count=1)
    page = re.sub(r"<h1>.*?</h1>", "<h1><span class=\"h1-pre\">LMCache ·</span> Release Desk</h1>", page, count=1)
    return page


REFRESH_BTN = '<div id="rdRfPop" role="region" aria-label="Refresh progress" hidden></div><style>#rdRfPop{position:absolute;z-index:70;width:min(600px,94vw);box-sizing:border-box;background:var(--surface-1);border:1px solid var(--border);border-radius:8px;box-shadow:var(--ux-e2);padding:12px;color:var(--text-primary);font-size:13px;text-align:left;font-weight:400;max-height:min(75vh,760px);overflow:auto}#rdRfPop[hidden]{display:none}#rdRfPop table{width:100%;border-collapse:collapse}#rdRfPop td{padding:4px 6px;border-top:1px solid var(--border);vertical-align:top}#rdRfPop .rd-g th{text-align:left;font-size:12px;font-weight:600;color:var(--text-secondary);padding:8px 6px 2px}.rd-bar{height:6px;border-radius:3px;background:var(--border);overflow:hidden;margin:6px 0 4px}.rd-bar>i{display:block;height:100%;background:var(--accent);transition:width .4s}#rdRfPop .rd-ic{width:16px;text-align:center;font-weight:600}.rd-done .rd-ic{color:var(--ok)}.rd-running .rd-ic{color:var(--accent);animation:rdp 1.2s infinite}.rd-running td{background:var(--accent-subtle)}.rd-failed .rd-ic,.rd-failed .rd-n{color:var(--bad)}.rd-pending td,.rd-skipped td{color:var(--text-secondary)}.rd-src{display:block;font-size:12px;color:var(--text-secondary)}.rd-s{white-space:nowrap;color:var(--text-secondary);text-align:right;font-variant-numeric:tabular-nums}@keyframes rdp{50%{opacity:.3}}@media (prefers-reduced-motion:reduce){.rd-running .rd-ic{animation:none}.rd-bar>i{transition:none}}@media (max-width:640px){#rdRfPop{position:fixed;left:8px;right:8px;width:auto;max-height:70vh}}@media (max-width:480px){#rdRfPop td.rd-s{display:none}}#hdrRefreshMore{background:none;border:0;color:var(--accent-text);cursor:pointer;font-size:13px;padding:0 4px;margin-left:2px}#hdrRefreshMore:focus-visible{outline:2px solid var(--ux-focus)}</style><button type="button" id="hdrRefresh" class="ux-btn" hidden style="margin-left:8px;font-size:12px;padding:2px 10px"></button><span id="hdrRefreshSt" role="status" aria-live="polite" style="margin-left:8px;font-size:12px"></span><button type="button" id="hdrRefreshMore" hidden aria-expanded="false" aria-controls="rdRfPop"></button><!--/rdRefresh-->'
REFRESH_JS = '<script>(function(){/* round 3: "Refresh data" runs the 07:00 pipeline (scheduled task ops-app-refresh); round 4: per-source progress panel */\nconst PROT=window.__rdProto||location.protocol,HOST=window.__rdHost||location.hostname;   // __rd*: test hooks (ux_round3.py)\nconst local=/^(127\\.0\\.0\\.1|localhost|\\[::1\\])$/.test(HOST)&&PROT===\'http:\',web=!local&&PROT===\'https:\';\nconst $=id=>document.getElementById(id),b=$(\'hdrRefresh\'),st=$(\'hdrRefreshSt\'),tg=$(\'hdrRefreshMore\'),pop=$(\'rdRfPop\');if(!b||!st||!tg||!pop||!(local||web))return;\nconst vi=()=>document.documentElement.lang===\'vi\',L=(e,v)=>vi()?v:e,esc=s=>String(s==null?\'\':s).replace(/[&<>"]/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\'}[c]));\nconst API=web?\'/api/refresh\':\'/api/refresh/status\',EVERY=web?10000:3000;\nlet t0=null,timer=null,P=null,run=false,queued=false,fin=null,watch=false;   // P = progress {running,done,total,elapsed_s,outcome,steps[]}; fin = finished outcome of a run seen here\nconst IC={done:\'✓\',running:\'●\',pending:\'○\',skipped:\'–\',failed:\'✕\'};\nconst GR=[[\'collect\',[\'observe_collect\',\'observe_ops_collect\',\'git_fetch\',\'overlap_collect\',\'mp_pr_collect\',\'collect_release\',\'collect_weekly\',\'etl_window\'],\'Pull new data\',\'Lấy dữ liệu mới\'],\n  [\'build\',[\'ingest_files\',\'build_page\',\'verify_page\',\'build_today\',\'export_static\',\'check_sync\',\'check_app\'],\'Build and check\',\'Build & kiểm tra\'],\n  [\'ship\',[\'publish\',\'digest\',\'d1_push\',\'d1_verify\',\'pages_deploy\'],\'Go live\',\'Đưa lên\']];\nconst NV=[[\'upload failed (the release PC copy is live)\',\'upload lỗi (bản trên máy release vẫn chạy)\'],[\'Buildkite: kept old data (no token)\',\'Buildkite: giữ dữ liệu cũ (chưa có token)\'],\n  [\'stopped after a failed step\',\'dừng vì bước trước lỗi\'],[\'fetch failed (old refs kept)\',\'fetch lỗi (giữ ref cũ)\'],[\'no Buildkite token\',\'chưa có token Buildkite\'],[\'offline run\',\'chạy offline\'],\n  [\'GitHub runs\',\'run GitHub\'],[\'Buildkite builds\',\'build Buildkite\'],[\'weekly runs\',\'run weekly\'],[\'weekly builds\',\'build weekly\'],[\'reports\',\'report\'],[\'open PRs\',\'PR đang mở\'],[\'PRs\',\'PR\'],[\'changed files\',\'file thay đổi\'],[\'views OK\',\'view OK\'],\n  [\' passed\',\' pass\'],[\' failed\',\' lỗi\'],[\' errors\',\' lỗi\'],[\' hits\',\' lỗi\'],[\'in ops.db\',\'trong ops.db\'],[\'builds\',\'build\'],[\'tags\',\'tag\'],[\'artifacts\',\'artifact\'],\n  [\'uploaded\',\'đã upload\'],[\'fetched\',\'đã fetch\'],[\'live \',\'lên bản \'],[\'snapshot\',\'snapshot\']];\nconst note=n=>{if(!n)return\'\';let s=String(n);if(vi())for(const[e,v]of NV)s=s.split(e).join(v);return s;};\nconst dur=s=>s==null?\'\':s<60?s+(vi()?\' giây\':\' s\'):Math.floor(s/60)+(vi()?\' phút \':\' min \')+(s%60?String(s%60).padStart(2,\'0\')+(vi()?\' giây\':\' s\'):\'\');\nconst label=()=>{b.textContent=L(\'Refresh data\',\'Làm mới dữ liệu\');tg.textContent=L(\'Progress\',\'Tiến trình\')+(pop.hidden?\' ▾\':\' ▴\');\n  b.title=web?L(\'Ask the release PC to pull every data source again, rebuild, check and publish this page (about 5–10 min). The progress panel shows each source.\',\'Yêu cầu máy release kéo lại mọi nguồn dữ liệu, build, kiểm tra và publish trang này (khoảng 5–10 phút). Bảng tiến trình cho thấy từng nguồn.\')\n    :L(\'Pull every data source again, rebuild, check and publish here (about 4–7 min). The progress panel shows each source.\',\'Kéo lại mọi nguồn dữ liệu, build, kiểm tra và publish tại máy này (khoảng 4–7 phút). Bảng tiến trình cho thấy từng nguồn.\');};\nconst color=k=>{st.style.color=k===\'bad\'?\'var(--bad)\':k===\'ok\'?\'var(--ok)\':k===\'warn\'?\'var(--warn)\':\'var(--text-secondary)\';};\nconst OUT={ok:[\'Done: new data is live\',\'Xong: dữ liệu mới đã lên\',\'ok\'],warn:[\'Done, with a warning\',\'Xong, có cảnh báo\',\'warn\'],failed:[\'Failed: the live page was not changed\',\'Lỗi: trang đang chạy giữ nguyên\',\'bad\'],busy:[\'Another refresh was running\',\'Đang có lần làm mới khác\',\'warn\']};\nfunction line(){if(run){const cur=P&&P.steps.find(s=>s.state===\'running\');st.textContent=P?`${P.done}/${P.total} · ${cur?(vi()?cur.vi:cur.en):\'…\'} · ${dur(P.elapsed_s)}`:L(\'Starting on the release PC…\',\'Đang khởi động trên máy release…\');color(\'\');return;}\n  if(queued){st.textContent=L(\'Request sent: the release PC starts within 2 min\',\'Đã gửi yêu cầu: máy release sẽ bắt đầu trong ≤ 2 phút\');color(\'\');return;}\n  if(fin){const o=OUT[fin]||OUT.ok;st.textContent=L(o[0],o[1])+(P&&P.elapsed_s?\' · \'+dur(P.elapsed_s):\'\');color(o[2]);return;}\n  st.textContent=\'\';}\nfunction draw(){label();line();tg.hidden=!P&&!run&&!queued;if(pop.hidden)return;\n  if(!P){pop.innerHTML=`<p style="margin:0">${run||queued?L(\'Waiting for the release PC to start the run…\',\'Đang chờ máy release bắt đầu…\'):L(\'No refresh has run yet.\',\'Chưa có lần làm mới nào.\')}</p>`;return;}\n  const by={};P.steps.forEach(s=>by[s.id]=s);const pct=P.total?Math.round(100*P.done/P.total):0;\n  const head=run?L(\'Refreshing every data source\',\'Đang làm mới mọi nguồn dữ liệu\'):fin?L(OUT[fin][0],OUT[fin][1]):(L(\'Last refresh\',\'Lần làm mới gần nhất\')+(P.started?\' · \'+P.started.slice(0,16).replace(\'T\',\' \'):\'\')+(P.outcome&&OUT[P.outcome]?\' · \'+L(OUT[P.outcome][0],OUT[P.outcome][1]):\'\'));\n  let h=`<div style="display:flex;justify-content:space-between;gap:8px;font-weight:600"><span>${esc(head)}</span><span class="rd-s">${P.done}/${P.total} · ${esc(dur(P.elapsed_s))}</span></div>`+\n    `<div class="rd-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${P.total}" aria-valuenow="${P.done}" aria-label="${esc(L(\'Steps done\',\'Số bước xong\'))}"><i style="width:${pct}%"></i></div><table><tbody>`;\n  for(const[g,ids,ge,gv]of GR){const rows=ids.map(i=>by[i]).filter(Boolean);if(!rows.length)continue;h+=`<tr class="rd-g"><th colspan="4">${esc(L(ge,gv))}</th></tr>`;\n    for(const s of rows)h+=`<tr class="rd-${s.state}"><td class="rd-ic" aria-label="${esc(s.state)}">${IC[s.state]||\'?\'}</td><td>${esc(vi()?s.vi:s.en)}<span class="rd-src">${esc(s.src)}</span></td><td class="rd-n">${esc(note(s.note))}</td><td class="rd-s">${esc(s.state===\'pending\'||s.state===\'skipped\'?\'\':dur(s.secs))}</td></tr>`;}\n  h+=\'</tbody></table>\';if(fin&&fin!==\'failed\')h+=`<p style="margin:10px 0 0"><button type="button" class="ux-btn" id="rdRfReload">${esc(L(\'Reload to see the new data\',\'Tải lại để xem dữ liệu mới\'))}</button></p>`;\n  pop.innerHTML=h;const rl=$(\'rdRfReload\');if(rl)rl.onclick=()=>location.reload();}\nfunction place(){if(matchMedia(\'(max-width:640px)\').matches){pop.style.left=\'\';pop.style.top=(b.getBoundingClientRect().bottom+6)+\'px\';return;}pop.style.left=Math.max(0,Math.min(b.offsetLeft,(pop.offsetParent||document.body).clientWidth-pop.offsetWidth-8))+\'px\';pop.style.top=(b.offsetTop+b.offsetHeight+6)+\'px\';}\nfunction open(v){pop.hidden=!v;tg.setAttribute(\'aria-expanded\',String(v));draw();if(v)place();}\ntg.addEventListener(\'click\',e=>{e.stopPropagation();open(pop.hidden);});\ndocument.addEventListener(\'click\',e=>{if(!pop.hidden&&!pop.contains(e.target)&&e.target!==b&&e.target!==tg)open(false);});\ndocument.addEventListener(\'keydown\',e=>{if(e.key===\'Escape\'&&!pop.hidden){open(false);tg.focus();e.stopPropagation();}},true);\nfunction take(j){if(web){const s=j.status||{};P=s.progress||P;queued=!!j.queued&&s.state!==\'running\';run=s.state===\'running\';\n    if((t0||watch)&&!run&&!queued&&s.at&&(watch||Date.parse(s.at)>=t0-5000))fin=s.state===\'failed\'?\'failed\':(s.result===\'warn\'?\'warn\':\'ok\');}\n  else{P=j.progress||P;run=!!j.running;const l=j.last||{};if((t0||watch)&&!run&&l.at&&(watch||Date.parse(l.at)>=t0-5000))fin=l.status===\'failed\'?\'failed\':l.status===\'warn\'?\'warn\':\'ok\';}\n  if(run)watch=true;if(fin){watch=false;t0=null;if(timer){clearInterval(timer);timer=null;}}b.disabled=run||queued;draw();}\nasync function poll(){try{const r=await fetch(API,{cache:\'no-store\'});if(!r.ok)throw 0;take(await r.json());}catch(e){st.textContent=L(\'Server not reachable\',\'Không kết nối được server\');color(\'bad\');}}\nconst go=()=>{if(!timer)timer=setInterval(poll,EVERY);};\nb.addEventListener(\'click\',async e=>{e.stopPropagation();b.disabled=true;t0=Date.now();fin=null;P=null;st.textContent=L(\'Starting…\',\'Đang bắt đầu…\');color(\'\');open(true);\n  try{const r=await fetch(\'/api/refresh\',{method:\'POST\',headers:{\'X-Release-Desk\':\'refresh\'}});const j=await r.json().catch(()=>({}));\n    if(r.status===409){watch=true;run=true;}else if(web?r.status!==202:!(r.ok&&j.started)){b.disabled=false;t0=null;st.textContent=web?L(\'Could not send the request.\',\'Không gửi được yêu cầu.\'):L(\'Could not start the refresh task.\',\'Không khởi động được task làm mới.\');color(\'bad\');return;}\n    else if(web)queued=true;else run=true;\n    draw();go();poll();}catch(err){b.disabled=false;t0=null;st.textContent=L(\'Server not reachable\',\'Không kết nối được server\');color(\'bad\');}});\naddEventListener(\'langchange\',draw);\nfetch(API,{cache:\'no-store\'}).then(r=>r.ok?r.json():null).then(j=>{if(!j||(web&&j.enabled!==true)){b.hidden=true;tg.hidden=true;return;}   // web without the function / KV: stay hidden, no error\n  b.hidden=false;take(j);if(run||queued){watch=true;go();}}).catch(()=>{b.hidden=true;tg.hidden=true;});\nlabel();})();</script>'


def main():
    page = open(PAGE, encoding="utf-8").read()
    page = tag_sections(page)
    page = put(page, "/* NAV:CSS:START */", "/* NAV:CSS:END */", CSS, "@media (max-width:980px)")
    page = put(page, "<!-- NAV:HTML:START -->", "<!-- NAV:HTML:END -->", HTML, "</header>", before=False)
    page = put(page, "<!-- NAV:JS:START -->", "<!-- NAV:JS:END -->", JS, "</body>")
    # round 2 B2 / B3: build time + oldest data source under the header (filled by JS from deskData; language aware)
    from datetime import datetime, timezone
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = (f'<p class="ux-built" id="hdrBuilt" data-built="{built}" style="margin:2px 0 0;font-size:12px;color:var(--text-secondary)"></p>'
             '<script>(function(){const p=document.getElementById("hdrBuilt");if(!p)return;'
             'const draw=()=>{const vi=document.documentElement.lang==="vi",b=p.dataset.built;let O={};'
             'try{O=JSON.parse(document.getElementById("deskData").textContent).overview||{};}catch(e){}'
             'const ag=(O.ages||[]).map(a=>[a.label.split(" (")[0],(Date.now()-Date.parse(a.at))/36e5]).filter(a=>isFinite(a[1])).sort((x,y)=>y[1]-x[1]);'
             'const f=h=>h<48?Math.round(h)+(vi?" giờ":" h"):Math.round(h/24)+(vi?" ngày":" d");'
             'const old=ag[0];p.textContent=(vi?"Build lúc ":"Built ")+b.slice(0,16).replace("T"," ")+" UTC";p.title=old?(vi?"Nguồn dữ liệu cũ nhất: ":"Oldest data source: ")+old[0]+" ("+f(old[1])+")":"";};'
             'if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",draw);else draw();addEventListener("langchange",draw);})();</script>')
    # round 3: drop the old button + its script first, so the old stamp is again "<p></p><script>" and the stamp regex removes it
    # (before, each build left one stale stamp with a duplicate id="hdrBuilt")
    page, n_rf = re.subn(r'<div id="rdRfPop".*?<!--/rdRefresh-->', '', page, count=1, flags=re.S)   # round 4 markup (progress panel)
    if not n_rf:
        page = re.sub(r'<button type="button" id="hdrRefresh".*?</span>', '', page, count=1, flags=re.S)
    page = re.sub(r'<script>\(function\(\)\{/\* round 3: "Refresh data".*?\}\)\(\);</script>', '', page, count=1, flags=re.S)
    page = re.sub(r'<p class="ux-built" id="hdrBuilt"[^>]*></p><script>\(function\(\)\{const p=document.getElementById\("hdrBuilt"\).*?\}\)\(\);</script>', '', page, flags=re.S)
    stamp = stamp.replace('></p><script>', '></p>' + REFRESH_BTN + '<script>', 1) + REFRESH_JS   # round 3: local "Refresh data" button
    page = page.replace('<!-- NAV:HTML:START -->', stamp + '<!-- NAV:HTML:START -->', 1)
    open(PAGE, "w", encoding="utf-8").write(page)
    tagged = re.findall(r'data-view="(\w+)" data-tab="(\w+)"', page)
    print("tagged", len(tagged), sorted(set(tagged)))


if __name__ == "__main__":
    main()
