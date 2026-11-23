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
@media (max-width:700px){.stairs{overflow-x:auto;max-width:100%}table.matrix,table.gc{display:block;overflow-x:auto;max-width:100%}select{max-width:100%}.vnav~* label,section label{white-space:normal;max-width:100%}.tf>summary{grid-template-columns:minmax(0,1fr) auto!important;row-gap:2px}.tf>summary .n{white-space:normal!important}.ffg{grid-template-columns:minmax(0,1fr)!important}.bars{overflow-x:auto;max-width:100%}}
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
/* NAV:CSS:END */
"""

HTML = r"""
<!-- NAV:HTML:START -->
<nav class="vnav" aria-label="Page views">
  <div class="row">
    <div class="seg" role="tablist" aria-label="View" title="Keys: O = management · T / U / E = exploration · ← → = tab · L = EN / VI">
      <button role="tab" data-v="obs" aria-selected="true" style="--ring:var(--series-2)"><span class="ic" style="background:var(--series-2)">MGT</span><span class="tx"><b>Release Management</b><small>Releases · trace · next release · CI cost · rebase risk</small></span></button>
      <button role="tab" data-v="explore" aria-selected="false" style="--ring:var(--series-1)"><span class="ic" style="background:var(--series-1)">EXP</span><span class="tx"><b>Release Exploration</b><small>Quality gates · CPU tests · GPU tests</small></span></button>
      <button role="tab" data-v="r1130" aria-selected="false" style="--ring:var(--series-3)"><span class="ic" style="background:var(--series-3)">RPT</span><span class="tx"><b>Report 1130</b><small>GPU + CPU baseline · time to green · retry</small></span></button>
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
  const TABS={
    obs:[['today','Now · Release Desk','0','Decide'],['hist','History','1','Decide'],['release','Releases','2','Release'],['trace','Release trace','3','Release'],['coming','Next release','4','Release'],['opt_cpu','CI cost · CPU','5','CI cost'],['opt_gpu','CI cost · GPU','6','CI cost'],['overlap','Rebase risk','7','Merge safety']],
    gates:[['guide','Guide & gates','0a–1'],['tiers','Tiers & Impact','2–5']],
    cpu:[['overview','Overview','1–2'],['tiers','Coverage','3–5'],['cost','Cost & Time','6'],['findings','Findings','7'],['explore','Test Explorer','8']],
    gpu:[['overview','Overview','1–2'],['tiers','Workloads','3–4'],['cost','Cost & Time','5–6'],['findings','Findings','7'],['explore','Mindmap','8']],
    r1130:[['baseline','GPU baseline','1','Baseline'],['cpu','CPU baseline','2','Baseline'],['green','Time to green','3','Merge flow'],['retry','Ran again','4','Retry'],['prs','Per PR','5','Evidence'],['track','Track vs baseline','6','Evidence'],['repro','Reproduce','7','Method'],['quality','Data quality','8','Method']]
  };
  const EXTRA={obs:{trace:'v0.5.7+',opt_cpu:'GitHub Actions',opt_gpu:'Buildkite',overlap:'open PRs vs 24h merges'},gates:{guide:'onboarding'},cpu:{explore:'540 files',tiers:'features'},gpu:{explore:'mindmap'}};
  const EXP=['gates','cpu','gpu'],EXPN={gates:'Quality Gate',cpu:'Test CPU',gpu:'Test GPU'};
  const top=v=>v==='obs'||v==='r1130'?v:'explore';
  let lastExp='gates';try{const x=localStorage.getItem('ciMapExp');if(EXP.includes(x))lastExp=x;}catch(e){}
  const flat=()=>top(st.v)!=='explore'?TABS[st.v].map(x=>[st.v,x[0]]):EXP.flatMap(v=>TABS[v].map(x=>[v,x[0]]));
  const SUB={
    obs:"Release owner's view: releases, release trace, the next release, CI cost and the rebase risk of open PRs after the last 24 h of merges. Data comes from local runs only.",
    r1130:"LM-1130: a reproducible 30-day PR CI baseline for GPU (Buildkite) and CPU (GitHub Actions): time to green, retries with evidence, cost per PR and commit, how to rebuild it, and the last 24 h tracked against it.",
    gates:'Architecture guide, merge and release gates, test tiers and change impact. Terms: MP = multiprocess GPU end-to-end CI · k3 = Buildkite GPU cluster · L0–L2 = test tiers, fast → full.',
    cpu:'Unit tests: 540 files in 28 areas, coverage, and CPU vs. GPU runners (commit 05d8eb84). Terms: MP = multiprocess GPU end-to-end CI · k3 = Buildkite GPU cluster · L0–L2 = test tiers, fast → full.',
    gpu:'Multiprocess (MP) GPU end-to-end CI: workloads, cost (3,099 GPU-h / 30 d) and the plan. Terms: MP = multiprocess GPU end-to-end CI · k3 = Buildkite GPU cluster · L0–L2 = test tiers, fast → full.'
  };
  const ACC={gates:'var(--text-secondary)',gpu:'var(--series-1)',cpu:'var(--series-3)',obs:'var(--series-2)',r1130:'var(--series-3)'};
  const secs=[...document.querySelectorAll('[data-view]')];
  secs.forEach((s,i)=>{if(s.tagName==='SECTION'&&!s.id)s.id='sec-'+s.dataset.view+'-'+(s.dataset.tab||'x')+'-'+i;});
  const pills=document.getElementById('vPills'), all=document.getElementById('vAll'), sub=document.getElementById('hdrSub');
  let st={v:'obs',t:'today'};   // landing tab: Today (decision inbox); a #view/tab hash still wins

  const ALIAS={
    // retired tabs (2026-11-10) land on the closest new tab, so old links keep working
    obs:{release:'release',now:'today',today:'today',desk:'today',hist:'hist',history:'hist',report:'release',trend:'release',trace:'trace',tracer:'trace',
      coming:'coming',prs:'coming',fixed:'coming',merged:'coming',optimal:'opt_cpu',opt_cpu:'opt_cpu',opt_gpu:'opt_gpu',ci:'opt_cpu',gpuload:'opt_gpu',gpu:'opt_gpu',publicci:'opt_cpu',
      overlap:'overlap',flaky:'overlap',bug:'overlap','24h':'overlap'},
    cpu:{matrix:'tiers',notrun:'tiers',failfast:'findings',findings:'findings',cost:'cost',explore:'explore',overview:'overview',tiers:'tiers'},
    gpu:{mindmap:'explore',tiers:'tiers',cost:'cost',findings:'findings',overview:'overview',explore:'explore'}
  };
  function parseHash(){
    const h=location.hash.slice(1).split('/');
    if(TABS[h[0]]){
      st.v=h[0];
      const target=(ALIAS[h[0]]&&ALIAS[h[0]][h[1]])||h[1];
      st.t=TABS[h[0]].some(x=>x[0]===target)?target:TABS[h[0]][0][0];
      return h[1];
    }
    return null;
  }
  const initSub=parseHash();

  function count(v,t){return secs.filter(s=>s.dataset.view===v&&s.dataset.tab===t&&s.tagName==='SECTION').length;}
  function drawPills(){
    pills.replaceChildren(); pills.style.setProperty('--accent',ACC[st.v]);
    const rows=top(st.v)!=='explore'?TABS[st.v].map(x=>[st.v,...x]):EXP.flatMap(v=>TABS[v].map(x=>[v,x[0],x[1],x[2],EXPN[v]]));
    let grp=null,box=pills;
    rows.forEach(([v,id,name,nums,g])=>{
      if(g&&g!==grp){grp=g;box=document.createElement('span');box.className='pg';const s=document.createElement('span');s.className='grp';s.textContent=g;box.appendChild(s);pills.appendChild(box);}
      const on=v===st.v&&id===st.t;
      const b=document.createElement('button'); b.setAttribute('role','tab'); b.dataset.t=id; b.dataset.v=v; b.id='tab-'+v+'-'+id; b.setAttribute('aria-selected',String(on)); b.tabIndex=on?0:-1;
      {const ids=secs.filter(s=>s.dataset.view===v&&s.dataset.tab===id&&s.tagName==='SECTION').map(s=>s.id);if(ids.length)b.setAttribute('aria-controls',ids.join(' '));}
      const k=document.createElement('span'); k.className='k'; k.textContent=nums; if(v==='obs'||v==='r1130')b.append(k); b.append(document.createTextNode(name));
      const ex=(EXTRA[v]||{})[id]; if(ex){const c=document.createElement('span');c.className='c';c.textContent=ex;b.appendChild(c);}
      b.addEventListener('click',()=>show(v,id)); box.appendChild(b);
    });
  }
  function scrollToSub(target){
    if(!target) return;
    setTimeout(()=>{
      let el=null;
      if(target==='notrun') el=document.getElementById('nrSub')||document.getElementById('nr');
      else if(target==='matrix') el=document.getElementById('fm');
      else if(target==='failfast') el=document.getElementById('ffg');
      else if(target==='mindmap') el=document.getElementById('mmFit');
      if(el) el.scrollIntoView({behavior:'smooth',block:'start'});
    },60);
  }
  function apply(scroll,targetSub){
    const showAll=all.checked;
    secs.forEach(s=>{const on=showAll||(s.dataset.view===st.v&&s.dataset.tab===st.t); const was=!s.classList.contains('vhide'); s.classList.toggle('vhide',!on); if(on&&!was){s.classList.remove('vshow'); void s.offsetWidth; s.classList.add('vshow');}});
    secs.forEach(s=>{if(s.tagName!=='SECTION')return;const act=!showAll&&s.dataset.view===st.v&&s.dataset.tab===st.t;if(act){s.setAttribute('role','tabpanel');s.setAttribute('aria-labelledby','tab-'+st.v+'-'+st.t);}else{s.removeAttribute('role');s.removeAttribute('aria-labelledby');}});
    document.querySelectorAll('.seg [data-v]').forEach(b=>{const on=b.dataset.v===top(st.v); b.setAttribute('aria-selected',String(on)); b.tabIndex=on?0:-1;});
    pills.hidden=showAll; drawPills(); if(sub) sub.textContent=SUB[st.v];
    document.body.dataset.v=st.v; document.body.dataset.all=showAll?'1':'0'; dispatchEvent(new CustomEvent('viewchange',{detail:{v:st.v,t:st.t}}));
    if(!/^#e\//.test(location.hash)) history.replaceState(null,'','#'+st.v+'/'+st.t); /* #e/<kind>/<id> = entity card route (build_entity_ui.py) */ try{localStorage.setItem('ciMapView7',JSON.stringify(st));}catch(e){}
    if(st.v==='gpu'&&(st.t==='explore'||showAll)) requestAnimationFrame(()=>{const f=document.getElementById('mmFit'); if(f) f.click();});
    if(targetSub) scrollToSub(targetSub);
    else if(scroll){const nav=document.querySelector('.vnav'); const y=nav.getBoundingClientRect().top+scrollY; if(scrollY>y) scrollTo({top:y,behavior:'smooth'});}
  }
  function show(v,t,scroll=true,targetSub=null){ if(v==='explore'){v=lastExp;t=null;}
    if(t&&TABS[v]&&!TABS[v].some(x=>x[0]===t)){const a=ALIAS[v]&&ALIAS[v][t];t=a&&TABS[v].some(x=>x[0]===a)?a:TABS[v][0][0];} if(EXP.includes(v)){lastExp=v;try{localStorage.setItem('ciMapExp',v);}catch(e){}} if(v!==st.v){st.v=v; st.t=t||TABS[v][0][0];} else if(t){st.t=t;} apply(scroll,targetSub); }
  window.vizNav={show,get state(){return {v:st.v,t:st.t};}};
  window.addEventListener('hashchange',()=>{if(/^#e\//.test(location.hash))return; const subT=parseHash(); apply(true,subT);});
  document.querySelectorAll('.seg [data-v]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.v)));
  all.addEventListener('change',()=>apply(false));
  document.addEventListener('click',e=>{const g=e.target.closest('[data-goto]'); if(g){const [v,t]=g.dataset.goto.split('/'); show(v,t);}});
  document.addEventListener('keydown',e=>{
    const tg=e.target&&e.target.closest?e.target:document.body;
    if(tg.closest('input,select,textarea,summary')||e.ctrlKey||e.metaKey||e.altKey) return;
    const k=e.key.toLowerCase();
    if(k==='m') show('gates','guide'); else if(k==='t') show('gates','overview'); else if(k==='g'||k==='e') show('gpu'); else if(k==='c'||k==='u') show('cpu'); else if(k==='o') show('obs','today'); else if(k==='r') show('obs','trace');
    else if(e.key==='ArrowRight'||e.key==='ArrowLeft'){ if(!tg.closest('.pills,.seg')&&tg!==document.body) return;
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
    page = re.sub(r"<title>.*?</title>", "<title>LMCache CI/CD &amp; Release Intelligence — Engineering Telemetry &amp; Quality Gates</title>", page, count=1)
    page = re.sub(r"<h1>.*?</h1>", "<h1>LMCache CI/CD &amp; Release Intelligence</h1>", page, count=1)
    return page


def main():
    page = open(PAGE, encoding="utf-8").read()
    page = tag_sections(page)
    page = put(page, "/* NAV:CSS:START */", "/* NAV:CSS:END */", CSS, "@media (max-width:980px)")
    page = put(page, "<!-- NAV:HTML:START -->", "<!-- NAV:HTML:END -->", HTML, "</header>", before=False)
    page = put(page, "<!-- NAV:JS:START -->", "<!-- NAV:JS:END -->", JS, "</body>")
    open(PAGE, "w", encoding="utf-8").write(page)
    tagged = re.findall(r'data-view="(\w+)" data-tab="(\w+)"', page)
    print("tagged", len(tagged), sorted(set(tagged)))


if __name__ == "__main__":
    main()
