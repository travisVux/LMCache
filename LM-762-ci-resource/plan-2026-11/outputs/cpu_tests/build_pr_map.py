"""PR map for 06_PR_TO_CI_VISUAL.html: one PR -> what it changes, where that sits on the critical path, which PRs it links to.
Idempotent. Run after build_entity_ui.py (needs window.ENT) and before build_i18n.py.

Opens as an overlay ("dashmotion" style: animated dashed flows, click a node for details):
  - from tab 6A (Rebase risk): a click on any PR number
  - from every tab: the "PR map" button in the PR card of the entity drawer
  - window.openPrMap(6572)

Three parts, all from data the page already holds (no new fetch):
  1. Critical path   journeys A-D x steps (opsData.coming.nr.cp: xlsx sheet 00 + NODE_F); steps whose F-ids the PR hits light up
  2. Feature matrix  F-ids hit = PR -> changes -> feature (window.ENT) -> AREA_F; CPU / GPU proof and risk from xlsx sheet 01
  3. Linked PRs      code clashes with level P0-P3 (opsData.overlap.groups: merged of the last 24 h x open PRs)
                     + PRs that change the same feature (window.ENT feature <- changes), shown as weaker links
NODE_F / AREA_F are DRAFT mappings (next_release.py): the map says so.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
PAGE = str(Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")

CSS = r"""
/* PRMAP:CSS:START */
.pm-ov{position:fixed;inset:0;z-index:60;background:color-mix(in srgb,var(--surface-0,#000) 55%,transparent);display:none;align-items:flex-start;justify-content:center;padding:28px 16px;overflow:auto}
.pm-ov.on{display:flex}
.pm-box{width:min(1180px,100%);background:var(--surface-1);border:1px solid var(--border);border-radius:14px;box-shadow:0 20px 60px rgba(0,0,0,.35)}
@keyframes pmIn{from{opacity:0;transform:translateY(-6px)}}
.pm-hd{display:flex;gap:10px;align-items:flex-start;padding:14px 18px 12px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--surface-1);border-radius:14px 14px 0 0;z-index:1}
.pm-hd .tt{flex:1;min-width:0}
.pm-hd .id{font-weight:700;font-size:15px;margin-right:6px}
.pm-hd .ti{font-size:14px;color:var(--text-primary)}
.pm-hd .mt{font-size:12px;color:var(--text-secondary);margin-top:3px;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center}
.pm-btn{background:var(--surface-2);border:1px solid var(--border);color:var(--text-secondary);border-radius:7px;padding:4px 10px;font:inherit;font-size:12px;cursor:pointer;white-space:nowrap}
.pm-btn:hover{color:var(--text-primary);border-color:var(--text-muted)}
.pm-btn:focus-visible{outline:2px solid var(--series-1);outline-offset:1px}
.pm-bd{padding:14px 18px 20px}
.pm-sum{font-size:13.5px;line-height:1.55;margin:0 0 10px;padding:10px 12px;border-left:3px solid var(--series-1);background:color-mix(in srgb,var(--series-1) 7%,transparent);border-radius:3px}
.pm-h{font-size:14px;margin:18px 0 6px;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.pm-h small{font-weight:400;color:var(--text-secondary);font-size:12px}
.pm-svgw{overflow-x:auto;border:1px solid var(--border);border-radius:10px;background:var(--surface-2)}
.pm-svg{display:block;width:100%;min-width:720px;height:auto}
.pm-svg text{font-family:inherit}
.pm-node{cursor:pointer}
.pm-node:hover rect{stroke-width:2}
.pm-node:focus-visible rect{stroke:var(--series-1);stroke-width:2.5}
.pm-node.active rect{stroke-width:2.5;filter:drop-shadow(0 0 6px color-mix(in srgb,var(--series-1) 55%,transparent))}
.pm-flow{stroke-dasharray:5 5;animation:pmDash .75s linear infinite}
.pm-async{stroke-dasharray:2 4;animation:pmDashA .9s linear infinite}
.pm-fail{stroke-dasharray:4 4;animation:pmDashF 1.1s linear infinite}
.pm-dot{animation:pmPulse 1.6s ease-in-out infinite}
@keyframes pmDash{to{stroke-dashoffset:-10}}
@keyframes pmDashA{to{stroke-dashoffset:-12}}
@keyframes pmDashF{to{stroke-dashoffset:-8}}
@keyframes pmPulse{0%,100%{opacity:1}50%{opacity:.35}}
.pm-ov.paused .pm-flow,.pm-ov.paused .pm-async,.pm-ov.paused .pm-fail,.pm-ov.paused .pm-dot{animation-play-state:paused}
@media (prefers-reduced-motion:reduce){.pm-flow,.pm-async,.pm-fail,.pm-dot{animation:none}}
.pm-info{display:none;margin-top:10px;border:1px solid var(--border);border-radius:10px;padding:12px 14px;background:var(--surface-1);animation:pmIn .15s ease}
.pm-info.on{display:block}
.pm-info h4{margin:0 0 6px;font-size:13.5px}
.pm-info .g{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px 16px;font-size:12.5px}
.pm-info .g b{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted);margin-bottom:2px}
.pm-leg{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--text-secondary);margin:6px 0}
.pm-leg i{display:inline-block;width:22px;height:0;border-top:2px dashed currentColor;vertical-align:middle;margin-right:5px}
.pm-tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.pm-tbl th,.pm-tbl td{border-bottom:1px solid var(--border);padding:6px 8px;text-align:left;vertical-align:top}
.pm-tbl th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted);font-weight:600}
.pm-tblw{overflow-x:auto}
.pm-chip{display:inline-block;border-radius:6px;padding:1px 6px;font-size:11px;font-weight:600;border:1px solid var(--border);background:var(--surface-2);white-space:nowrap}
.pm-chip.p0,.pm-chip.p1{color:var(--critical);border-color:color-mix(in srgb,var(--critical) 50%,var(--border))}
.pm-chip.p2{color:var(--warning);border-color:color-mix(in srgb,var(--warning) 50%,var(--border))}
.pm-chip.p3{color:var(--text-primary)}
.pm-chip.p4{color:var(--text-muted);font-weight:500}
.pm-chip.feat{color:var(--series-1);border-color:color-mix(in srgb,var(--series-1) 45%,var(--border))}
.pm-chip.weak{opacity:.7;font-weight:500}
.pm-note{font-size:12px;color:var(--text-secondary);margin-top:6px}
.pm-pr{cursor:pointer;color:var(--series-1);text-decoration:underline dotted;text-underline-offset:2px}
.pm-mx th:not(:first-child){text-align:center}
.pm-mx td{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pm-mx td.pm-hit{background:color-mix(in srgb,var(--series-1) 16%,transparent);text-align:center;font-weight:700}
.pm-mx td.pm-wk{background:color-mix(in srgb,var(--series-1) 7%,transparent);text-align:center;color:var(--text-secondary)}
.pm-mx td.pm-no{text-align:center;color:var(--text-muted)}
.pm-hint{font-size:12px;color:var(--text-secondary)}
.pm-dec{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin:0 0 10px;padding:10px 14px;border-radius:10px;border:1px solid var(--border);border-left:5px solid var(--text-muted);background:var(--surface-2);font-size:14px;line-height:1.5}
.pm-dec .v{font-weight:800;font-size:15px;white-space:nowrap}
.pm-dec.ok{border-left-color:var(--good)}.pm-dec.ok .v{color:var(--good)}
.pm-dec.warn{border-left-color:var(--warning)}.pm-dec.warn .v{color:var(--warning)}
.pm-dec.bad{border-left-color:var(--critical)}.pm-dec.bad .v{color:var(--critical)}
.pm-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:6px 16px;margin:0 0 10px;font-size:13px}
.pm-facts b{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted)}
.pm-draft{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--warning);border:1px dashed var(--warning);border-radius:5px;padding:0 5px}
.pm-leg2{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--text-secondary);margin:0 0 6px}
.pm-leg2 .k{text-transform:none;letter-spacing:0;font-weight:400;white-space:normal}
.pm-leg2 .k-lit::before{content:'';display:inline-block;width:12px;height:10px;border:1.6px solid var(--series-1);background:color-mix(in srgb,var(--series-1) 22%,transparent);border-radius:3px;margin-right:5px;vertical-align:-1px}
.pm-leg2 .k-dash::before{content:'';display:inline-block;width:12px;height:10px;border:1.6px dashed var(--series-1);border-radius:3px;margin-right:5px;vertical-align:-1px}
.pm-leg2 .k-badge::before{content:'3';display:inline-block;font-size:10px;font-weight:700;color:var(--warning);border:1.4px solid var(--warning);border-radius:8px;padding:0 4px;margin-right:5px}
.pm-tbl tr.pm-grp th{background:var(--surface-2);font-size:11.5px;text-transform:none;letter-spacing:0;color:var(--text-primary);padding:6px 8px}
.pm-tbl tr.pm-grp-now th{border-left:4px solid var(--critical)}
.pm-tbl tr.pm-grp-later th{border-left:4px solid var(--warning)}
.pm-tbl tr.pm-grp-p4 th,.pm-tbl tr.pm-grp-fyi th{border-left:4px solid var(--text-muted);color:var(--text-secondary)}
.pm-pf{margin-top:4px;font-size:12px}.pm-pf summary{cursor:pointer;color:var(--text-secondary)}.pm-pf div{margin-top:3px}
.pm-jl{display:flex;flex-direction:column;gap:4px}
.pm-jh{font-weight:700;font-size:13.5px;margin-top:8px}.pm-jh small{font-weight:400;color:var(--series-1)}.pm-jh.off{opacity:.55}.pm-jh.off small{color:var(--text-muted)}
.pm-js{display:flex;gap:6px;align-items:baseline;text-align:left;width:100%;background:var(--surface-1);border:1px solid var(--border);border-radius:8px;padding:6px 8px;font:inherit;font-size:13px;color:var(--text-secondary);cursor:pointer}
.pm-js.on{border-color:var(--series-1);color:var(--text-primary);background:color-mix(in srgb,var(--series-1) 12%,var(--surface-1))}
.pm-js .f{margin-left:auto;font-size:11.5px;color:var(--text-muted)}.pm-js.on .f{color:var(--series-1);font-weight:700}
.pm-lk{margin:0 0 6px;border:1px solid var(--border);border-radius:10px;padding:6px 12px}
.pm-lk>summary{cursor:pointer;font-size:13px;font-weight:600;padding:2px 0}
.pm-lk[open]>summary{margin-bottom:6px}
.pm-lk tr.pm-lk-hit td{background:color-mix(in srgb,var(--series-1) 8%,transparent)}
@media (max-width:600px){.pm-cards thead{display:none}.pm-cards,.pm-cards tbody,.pm-cards tr,.pm-cards td,.pm-cards th{display:block;width:auto}
.pm-cards tr{border:1px solid var(--border);border-radius:8px;margin:0 0 8px;padding:4px 2px}.pm-cards td{border:0;padding:3px 8px}
.pm-cards td[data-l]::before{content:attr(data-l);display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted)}
.pm-cards tr.pm-grp{border:0;padding:0;margin:12px 0 6px}.pm-mx{width:100%!important}}
@media (max-width:700px){.pm-ov{padding:0}.pm-box{border-radius:0;min-height:100%}.pm-hd{border-radius:0}.pm-bd{padding:12px 14px 18px}}
/* PRMAP:CSS:END */
"""

HTML = r"""<!-- PRMAP:HTML:START -->
<div class="pm-ov paused" id="pmOv" role="dialog" aria-modal="true" aria-labelledby="pmTitle" aria-hidden="true">
  <div class="pm-box"><div class="pm-hd"><button type="button" class="pm-btn" id="pmBack" hidden>←</button><div class="tt" id="pmHead"></div>
    <button type="button" class="pm-btn" id="pmPause" aria-pressed="true">▶ animate</button><button type="button" class="pm-btn" id="pmClose">✕</button></div>
  <div class="pm-bd" id="pmBody"></div></div>
</div>
<!-- PRMAP:HTML:END -->"""

JS = r"""<!-- PRMAP:JS:START -->
<script>
(function(){
  const ov=document.getElementById('pmOv'); if(!ov||!window.ENT) return;
  {const R=document.getElementById('root'); if(R&&ov.parentNode!==R) R.append(ov);}   // the colour / font tokens live on .viz-root
  const head=document.getElementById('pmHead'),body=document.getElementById('pmBody'),back=document.getElementById('pmBack'),pause=document.getElementById('pmPause');
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en, L=a=>Array.isArray(a)?T(a[0],a[1]):(a||'');
  const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const GH='https://github.com/LMCache/LMCache';
  let OPS=null; const ops=()=>{if(OPS) return OPS; try{OPS=JSON.parse(document.getElementById('opsData').textContent);}catch(e){OPS={};} return OPS;};
  const LV={p0:['P0 · breaks on rebase','P0 · vỡ khi rebase'],p1:['P1 · same function','P1 · cùng hàm'],p2:['P2 · nearby lines','P2 · dòng gần nhau'],p3:['P3 · same file','P3 · cùng file'],p4:['P4 · tests / docs only','P4 · chỉ test / docs'],feat:['same feature, no shared code','cùng feature, không chung code']};
  const LCOL={p0:'var(--critical)',p1:'var(--critical)',p2:'var(--warning)',p3:'var(--text-secondary)',p4:'var(--text-muted)',feat:'var(--series-1)'};
  const LW={p0:2.5,p1:2.5,p2:1.75,p3:1,p4:1,feat:1};
  const LDASH={p0:'none',p1:'none',p2:'6 3',p3:'3 3',p4:'1 3',feat:'2 4'};
  const CODE=l=>l.level!=='feat';   // shares code with this PR (P0-P4)
  const SMALL=()=>innerWidth<600;
  const LCLS={p0:'pm-fail',p1:'pm-fail',p2:'pm-flow',p3:'',p4:'',feat:''};   // only P0-P2 edges move
  const RANK={p0:0,p1:1,p2:2,p3:3,p4:4,feat:5};
  const VERB={rebase:['rebase first','rebase trước'],review:['review','review'],merge:['merge','merge'],full:["add 'full'","gắn 'full'"],red:['wait fix','chờ sửa'],dco:['fix DCO','sửa DCO'],author:['wait author','chờ tác giả'],cancel:['cancel CI','huỷ CI'],keep:['keep running','để chạy'],block:['block merge','chặn merge'],hold:['hold','giữ lại'],stop:['stop CI','dừng CI'],later:['rebase before merge','rebase trước merge'],go:['proceed','tiếp tục'],idle:['no CI','không CI']};
  const SUB={draft:['draft','nháp'],wait_review:['waiting review','chờ review'],wait_full:["waiting 'full'","chờ nhãn full"],adapt:['changes requested','yêu cầu sửa'],ci_missing:['required check not run','check bắt buộc chưa chạy'],ci_run:['CI running','CI đang chạy'],ready:['approved','đã duyệt'],ci_fail:['required check red','check bắt buộc đỏ'],conflict:['merge conflict','xung đột merge'],old:['stale (30+ d)','cũ (30+ ngày)']};
  const SVGNS='http://www.w3.org/2000/svg';

  // ---------------------------------------------------------------- model of one PR
  function model(num){
    const k='pr:'+num,n=ENT.get(k); if(!n) return null;
    const O=ops().overlap||{},CP=((ops().coming||{}).nr||{}).cp||{},AF=CP.area_f||{},FD={};
    (CP.features||[]).forEach(f=>FD[f.id]=f);
    const feats=ENT.out(k).filter(e=>e.rel==='changes').map(e=>{const f=ENT.get(e.b)||{};return {key:e.b,id:e.b.replace(/^feature:/,''),s:e.s,title:f.title||e.b,stage:f.stage};})
      .sort((a,b)=>(a.s==='strong'?0:1)-(b.s==='strong'?0:1));
    const F={};   // F-id -> {s: strong|weak, via:[feature titles]}
    feats.forEach(f=>(AF[f.id]||[]).forEach(id=>{const x=F[id]=F[id]||{s:'weak',via:[]}; if(f.s==='strong') x.s='strong'; x.via.push(f);}));
    // links: code clashes (overlap.groups) + same feature (ENT)
    const links={};
    const add=(p,o)=>{const c=links[p]; if(!c||RANK[o.level]<RANK[c.level]) links[p]=Object.assign({num:p},c||{},o);};
    (O.groups||[]).forEach(g=>{
      if(String(g.p)===String(num)) g.items.forEach(it=>add(String(it.m),{level:it.level,dir:'merged',same:it.same,shared:it.shared||[],title:it.m_title,state:'merged',ci:it.m_ci}));
      else g.items.forEach(it=>{if(String(it.m)===String(num)) add(String(g.p),{level:it.level,dir:'open',same:it.same,shared:it.shared||[],title:g.p_title,state:'open',sub:g.p_sub,verb:g.verb,inactive:g.inactive});});
    });
    const fshare={};
    feats.filter(f=>f.s==='strong').forEach(f=>ENT.inn(f.key).forEach(e=>{if(e.rel!=='changes'||e.s!=='strong'||e.a===k) return; const o=ENT.get(e.a); if(!o||o.kind!=='pr'||!(o.state==='open'||o.state==='merged')) return;
      const id=o.id; (fshare[id]=fshare[id]||{n:o,f:[]}).f.push(f.title);}));
    Object.values(fshare).sort((a,b)=>b.f.length-a.f.length||String(b.n.at||'').localeCompare(String(a.n.at||''))).slice(0,10).forEach(x=>{
      if(!links[x.n.id]) links[x.n.id]={num:x.n.id,level:'feat',dir:x.n.state==='merged'?'merged':'open',title:x.n.title,state:x.n.state,same:[`Same feature: ${x.f.join(', ')}`,`Cùng feature: ${x.f.join(', ')}`],shared:[]};});
    const L_=Object.values(links).sort((a,b)=>RANK[a.level]-RANK[b.level]||Number(b.num)-Number(a.num));
    // F-ids of each linked PR (for "who else is on this step")
    L_.forEach(l=>{l.F=new Set(); ENT.out('pr:'+l.num).filter(e=>e.rel==='changes').forEach(e=>(AF[e.b.replace(/^feature:/,'')]||[]).forEach(id=>l.F.add(id)));});
    const q=((O.review||{}).queue||[]).concat((O.review||{}).running||[]).find(x=>String(x.num)===String(num));
    const g=(O.groups||[]).find(x=>String(x.p)===String(num));
    return {num:String(num),n,feats,F,FD,CP,links:L_,q,g,snap:O.snap_at,fcap:Object.keys(fshare).length>10?Object.keys(fshare).length:0};
  }

  // ---------------------------------------------------------------- small svg helpers
  const sv=(tag,a)=>{const e=document.createElementNS(SVGNS,tag);for(const k in a) if(a[k]!=null) e.setAttribute(k,a[k]);return e;};
  const txt=(x,y,s,a)=>{const t=sv('text',Object.assign({x,y},a||{}));t.textContent=s;return t;};
  function wrap(s,n){const w=String(s).split(/\s+/),out=[''];w.forEach(x=>{const c=out[out.length-1];if((c+' '+x).trim().length>n&&c) out.push(x); else out[out.length-1]=(c+' '+x).trim();});
    if(out.length>2){out.length=2;out[1]=out[1].slice(0,n-1)+'…';} return out;}
  const arrowDefs=svg=>{const d=sv('defs',{});const m=sv('marker',{id:'pmArrow',viewBox:'0 0 10 10',refX:'8',refY:'5',markerWidth:'6',markerHeight:'6',orient:'auto-start-reverse'});
    m.append(sv('path',{d:'M2 1L8 5L2 9',fill:'none',stroke:'context-stroke','stroke-width':'1.5','stroke-linecap':'round','stroke-linejoin':'round'}));d.append(m);svg.append(d);};

  // ---------------------------------------------------------------- 1 · critical path
  function critPath(M,info){
    const J=M.CP.journeys||[],NF=M.CP.node_f||{};
    if(!J.length) return el('div',{class:'pm-note'},T('Critical path model not in this build (needs knowledge/inputs/LMCache_CPU_GPU_Feature_Matrix.xlsx).','Bản build này không có mô hình critical path (cần knowledge/inputs/LMCache_CPU_GPU_Feature_Matrix.xlsx).'));
    const W=1000,lx=150,lh=96,top=14,H=top+J.length*lh,nw=104,nh=46;
    const svg=sv('svg',{viewBox:`0 0 ${W} ${H}`,class:'pm-svg',role:'img','aria-label':T('Critical path journeys A–D; steps this PR touches are highlighted','Các hành trình critical path A–D; bước PR này chạm tới được tô sáng')});
    arrowDefs(svg);
    J.forEach((j,ji)=>{
      const y=top+ji*lh,n=j.steps.length,gap=n>1?(W-lx-20-n*nw)/(n-1):0,hitN=j.steps.filter((s,i)=>(NF[j.id]||[])[i]&&(NF[j.id][i]).some(f=>M.F[f])).length;
      const lane=sv('g',{opacity:hitN?1:.5});svg.append(lane);
      lane.append(sv('line',{x1:8,x2:W-8,y1:y+lh-6,y2:y+lh-6,stroke:'var(--border)','stroke-dasharray':'4 6'}));
      lane.append(txt(10,y+30,`${j.id} · ${j.name.toLowerCase().replace(/^\w/,c=>c.toUpperCase())}`,{fill:'var(--text-primary)','font-size':'14','font-weight':'700'}));
      lane.append(txt(10,y+49,hitN?T(`${hitN}/${n} steps touched`,`chạm ${hitN}/${n} bước`):T('not touched','không chạm'),{fill:hitN?'var(--series-1)':'var(--text-muted)','font-size':'12'}));
      const pos=i=>lx+i*(nw+gap);
      j.steps.forEach((st,i)=>{
        const fs=(NF[j.id]||[])[i]||[],hit=fs.filter(f=>M.F[f]),strong=hit.some(f=>M.F[f].s==='strong'),x=pos(i),yy=y+18;
        if(i<n-1){const x2=pos(i+1),nxt=((NF[j.id]||[])[i+1]||[]).some(f=>M.F[f]);
          lane.append(sv('path',{d:`M${x+nw} ${yy+nh/2} L${x2-3} ${yy+nh/2}`,fill:'none',stroke:(hit.length||nxt)?'var(--series-1)':'var(--text-muted)','stroke-width':(hit.length||nxt)?'1.8':'1.1',class:(hit.length&&nxt)?'pm-flow':null,'stroke-dasharray':(hit.length&&nxt)?null:'5 5','marker-end':'url(#pmArrow)',opacity:(hit.length||nxt)?1:.55}));}
        const others=hit.length?M.links.filter(l=>CODE(l)&&hit.some(f=>l.F.has(f))).length:0;   // code-sharing PRs on an F-id this PR touches
        const g=sv('g',{class:'pm-node',tabindex:'0',role:'button','aria-label':`${j.id}${i+1} ${st}`});
        g.append(sv('rect',{x,y:yy,width:nw,height:nh,rx:8,fill:hit.length?(strong?'color-mix(in srgb,var(--series-1) 22%,var(--surface-1))':'color-mix(in srgb,var(--series-1) 10%,var(--surface-1))'):'var(--surface-1)',
          stroke:hit.length?'var(--series-1)':'var(--border)','stroke-width':hit.length?'1.6':'1','stroke-dasharray':hit.length&&!strong?'4 3':null}));
        wrap(st,14).forEach((ln,li,arr)=>g.append(txt(x+nw/2,yy+(arr.length>1?19:27)+li*14,ln,{'text-anchor':'middle',fill:hit.length?'var(--text-primary)':'var(--text-secondary)','font-size':'12','font-weight':hit.length?'600':'400'})));
        {const cw=26,x0=x+nw/2-(fs.length*cw)/2+cw/2;fs.forEach((f,fi)=>{const tt=txt(x0+fi*cw,yy+nh+13,f,{'text-anchor':'middle',fill:M.F[f]?'var(--series-1)':'var(--text-secondary)','font-size':'11','font-weight':M.F[f]?'700':'400',style:'cursor:help'});
          const ti=sv('title',{});ti.textContent=fTip(M,f);tt.append(ti);g.append(tt);});}
        if(hit.length) g.append(sv('circle',{cx:x+nw-7,cy:yy+7,r:3.5,fill:'var(--series-1)',class:'pm-dot'}));
        if(others) {g.append(sv('rect',{x:x-6,y:yy-7,width:others>9?24:18,height:15,rx:7.5,fill:'var(--surface-1)',stroke:'var(--warning)','stroke-width':'1.4'}));g.append(txt(x+(others>9?6:3),yy+4.5,String(others),{'text-anchor':'middle','font-size':'11',fill:'var(--warning)','font-weight':'700'}));}
        const t=sv('title',{});t.textContent=`${j.id}${i+1} · ${st} · ${fs.join(', ')}${hit.length?' · '+T('touched by this PR','PR này chạm tới'):''}${others?' · '+others+' '+T('PRs share code with this PR on this step','PR chung code với PR này ở bước này'):''}`;g.append(t);
        const act=()=>{svg.querySelectorAll('.pm-node.active').forEach(x=>x.classList.remove('active'));g.classList.add('active');showStep(M,info,j,i,st,fs);};
        g.addEventListener('click',act);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();act();}});
        lane.append(g);});
    });
    return svg;
  }
  // phone width: the journeys as lists (the SVG text would shrink to ~5 px)
  function critList(M,info){
    const J=M.CP.journeys||[],NF=M.CP.node_f||{},w=el('div',{class:'pm-jl'});
    J.forEach(j=>{const hitN=j.steps.filter((s,i)=>((NF[j.id]||[])[i]||[]).some(f=>M.F[f])).length;
      w.append(el('div',{class:'pm-jh'+(hitN?'':' off')},`${j.id} · ${j.name.toLowerCase().replace(/^\w/,c=>c.toUpperCase())}`,el('small',{},hitN?T(` · ${hitN}/${j.steps.length} steps touched`,` · chạm ${hitN}/${j.steps.length} bước`):T(' · not touched',' · không chạm'))));
      if(!hitN) return;
      j.steps.forEach((st,i)=>{const fs=(NF[j.id]||[])[i]||[],hit=fs.filter(f=>M.F[f]),others=hit.length?M.links.filter(l=>CODE(l)&&hit.some(f=>l.F.has(f))).length:0;
        const b=el('button',{type:'button',class:'pm-js'+(hit.length?' on':'')},el('b',{},`${j.id}${i+1}`),' ',st,el('span',{class:'f'},fs.join(' ')),others?el('span',{class:'pm-chip p2'},String(others)):null);
        b.addEventListener('click',()=>showStep(M,info,j,i,st,fs));w.append(b);});});
    return w;
  }
  function showStep(M,info,j,i,st,fs){
    const fl=fs.map(id=>{const f=M.FD[id]||{},h=M.F[id];return `<div style="margin-bottom:8px"><b>${esc(id)} · ${esc(f.name||'')}</b> ${h?`<span class="pm-chip feat${h.s==='weak'?' weak':''}">${T(h.s==='strong'?'this PR: source':'this PR: tests only',h.s==='strong'?'PR này: code nguồn':'PR này: chỉ test')}</span>`:''}
      <div class="g" style="margin-top:4px"><div><b>${T('Critical','Mức critical')}</b>${esc(f.crit||'—')}</div><div><b>${T('CPU proves','CPU chứng minh')}</b>${esc(f.cpu||'—')}</div><div><b>${T('GPU proves','GPU chứng minh')}</b>${esc(f.gpu||'—')}</div><div><b>${T('Risk if broken','Rủi ro nếu hỏng')}</b>${esc(f.risk||'—')}</div></div>
      ${h?`<div class="pm-note">${T('via','qua')} ${h.via.map(v=>ENT.a(v.key,v.title)).join(', ')}</div>`:''}</div>`;}).join('');
    const oth=M.links.filter(l=>fs.some(f=>l.F.has(f))).sort((a,b)=>RANK[a.level]-RANK[b.level]);
    info.innerHTML=`<h4>${esc(j.id)}${i+1} · ${esc(st)} <span class="pm-hint">· ${esc(j.name)}</span></h4>${fl||`<div class="pm-note">${T('No F-id on this step.','Bước này không có F-id.')}</div>`}`+
      `<div class="pm-note"><b>${T('Linked PRs on this step','PR liên quan ở bước này')}:</b> ${oth.length?oth.map(l=>`<span class="pm-pr" data-pm="${esc(l.num)}">#${esc(l.num)}</span> <span class="pm-chip ${l.level}">${esc(l.level==='feat'?T('feature','feature'):l.level.toUpperCase())}</span>`).join(' · '):T('none','không có')}</div>`;
    info.classList.add('on');
  }

  // ---------------------------------------------------------------- F-id lookup (what F01..F17 mean)
  function fTip(M,id){const f=M.FD[id]||{},h=M.F[id];return `${id} · ${f.name||''}${f.step?' ('+f.step+')':''}\n${T('Critical','Critical')}: ${f.crit||'—'}\n${T('Risk if broken','Rủi ro nếu hỏng')}: ${f.risk||'—'}${h?'\n'+T(h.s==='strong'?'This PR changes its source code':'This PR changes only its tests',h.s==='strong'?'PR này sửa code nguồn của nó':'PR này chỉ sửa test của nó'):''}`;}
  function fLookup(M){
    const FS=M.CP.features||[],J=M.CP.journeys||[],NF=M.CP.node_f||{},AF=M.CP.area_f||{};
    if(!FS.length) return null;
    const steps=id=>J.map(j=>(NF[j.id]||[]).map((fs,i)=>fs.includes(id)?j.id+(i+1):null).filter(Boolean).join(' ')).filter(Boolean).join(' · ');
    const areas=id=>Object.keys(AF).filter(a=>AF[a].includes(id)).map(a=>{const n=ENT.get('feature:'+a);return n?ENT.a('feature:'+a,n.title):esc(a);}).join(', ');
    const hit=FS.filter(f=>M.F[f.id]).length,d=document.createElement('details');d.className='pm-lk';
    d.innerHTML=`<summary>${T(`Lookup: what F01–F17 mean (${FS.length} features, ${hit} touched by this PR)`,`Tra cứu: F01–F17 là gì (${FS.length} feature, PR này chạm ${hit})`)}</summary>`+
      `<p class="pm-note">${T('F = one user-facing feature row of the CPU / GPU feature matrix','F = một dòng feature (chức năng người dùng thấy) của feature matrix CPU / GPU')} (<code class="obsraw">${esc(M.CP.src||'')}</code>, sheet "01 Feature Test Matrix"). ${T('Each row says what CPU tests must prove, what GPU tests must prove, and what the user sees if it breaks. Journey steps and code areas link to F through DRAFT mappings (NODE_F / AREA_F).','Mỗi dòng ghi test CPU phải chứng minh gì, test GPU phải chứng minh gì, và người dùng thấy gì nếu hỏng. Bước hành trình và vùng code nối vào F qua ánh xạ BẢN NHÁP (NODE_F / AREA_F).')}</p>`+
      `<div class="pm-tblw"><table class="pm-tbl"><thead><tr><th>F</th><th>${T('Feature','Feature')}</th><th>${T('Critical','Critical')}</th><th>${T('CPU proves','CPU chứng minh')}</th><th>${T('GPU proves','GPU chứng minh')}</th><th>${T('Risk if broken','Rủi ro nếu hỏng')}</th><th>${T('Journey steps','Bước hành trình')}</th><th>${T('Code areas','Vùng code')}</th></tr></thead><tbody>`+
      FS.map(f=>{const h=M.F[f.id];return `<tr${h?' class="pm-lk-hit"':''}><td><b>${esc(f.id)}</b>${h?` <span class="pm-chip feat${h.s==='weak'?' weak':''}">${T(h.s==='strong'?'this PR':'this PR · tests',h.s==='strong'?'PR này':'PR này · test')}</span>`:''}</td><td>${esc(f.name)}<div class="pm-hint">${esc(f.step)}</div></td><td>${esc(f.crit||'—')}</td><td>${esc(f.cpu||'—')}</td><td>${esc(f.gpu||'—')}</td><td>${esc(f.risk||'—')}</td><td>${esc(steps(f.id)||'—')}</td><td>${areas(f.id)||'—'}</td></tr>`;}).join('')+
      `</tbody></table></div>`;
    return d;
  }

  // ---------------------------------------------------------------- 2 · feature matrix
  function featMatrix(M){
    const ids=Object.keys(M.F).sort(),J=M.CP.journeys||[],NF=M.CP.node_f||{};
    if(!M.feats.length) return el('div',{class:'pm-note'},T('No code area found for this PR in the entity index.','Không tìm thấy vùng code của PR này trong bảng thực thể.'));
    const onSteps=id=>J.map(j=>((NF[j.id]||[]).map((fs,i)=>fs.includes(id)?j.id+(i+1):null).filter(Boolean)).join(' ')).filter(Boolean).join(' · ');
    const rows=ids.map(id=>{const f=M.FD[id]||{},h=M.F[id],oth=M.links.filter(l=>l.F.has(id));
      const oc=oth.filter(CODE).sort((a,b)=>RANK[a.level]-RANK[b.level]),of=oth.length-oc.length;
      return `<tr><td><b>${esc(id)}</b> ${esc(f.name||'')}<div class="pm-hint">${esc(f.step||'')} · ${esc(f.crit||'')}</div>`+
        `<details class="pm-pf"><summary>${T('CPU / GPU proof','Bằng chứng CPU / GPU')}</summary><div><b>CPU</b> ${esc(f.cpu||'—')}</div><div><b>GPU</b> ${esc(f.gpu||'—')}</div></details></td>`+
        `<td data-l="${esc(T('Changed through','Sửa qua'))}">${h.via.map(v=>`${ENT.a(v.key,v.title)} <span class="pm-chip feat${v.s==='weak'?' weak':''}">${T(v.s==='strong'?'source':'tests only',v.s==='strong'?'code nguồn':'chỉ test')}</span>`).join('<br>')}</td>`+
        `<td data-l="${esc(T('Journey steps','Bước hành trình'))}">${esc(onSteps(id)||'—')}</td><td data-l="${esc(T('Risk if broken','Rủi ro nếu hỏng'))}">${esc(f.risk||'—')}</td>`+
        `<td data-l="${esc(T('PRs on this F','PR trên F này'))}">${oc.length?oc.slice(0,8).map(l=>`<span class="pm-pr" data-pm="${esc(l.num)}">#${esc(l.num)}</span> <span class="pm-chip ${l.level}">${l.level.toUpperCase()}</span>`).join(' · ')+(oc.length>8?` · +${oc.length-8}`:''):'<span class="pm-hint">'+T('no code clash','không đụng code')+'</span>'}${of?`<div class="pm-hint">+${of} ${T('same-feature PRs','PR cùng feature')}</div>`:''}</td></tr>`;}).join('');
    const none=M.feats.filter(f=>!(M.CP.area_f||{})[f.id]);
    // compact area x F grid: which code area maps to which F
    const grid=`<table class="pm-tbl pm-mx" style="table-layout:fixed;width:${Math.min(100,30+ids.length*9)}%"><colgroup><col style="width:${Math.max(30,100-ids.length*9)}%">${ids.map(()=>'<col>').join('')}</colgroup><thead><tr><th>${T('Code area changed','Vùng code bị sửa')}</th>${ids.map(id=>`<th title="${esc(fTip(M,id))}" style="cursor:help">${esc(id)}</th>`).join('')}</tr></thead><tbody>${M.feats.filter(f=>(M.CP.area_f||{})[f.id]).map(f=>`<tr><td>${ENT.a(f.key,f.title)} ${f.s==='weak'?`<span class="pm-chip weak">${T('tests only','chỉ test')}</span>`:''}</td>${ids.map(id=>((M.CP.area_f||{})[f.id]||[]).includes(id)?`<td class="${f.s==='strong'?'pm-hit':'pm-wk'}">●</td>`:'<td class="pm-no"></td>').join('')}</tr>`).join('')}</tbody></table>`;
    const w=document.createElement('div');
    w.innerHTML=`<div class="pm-tblw">${grid}</div><div class="pm-tblw" style="margin-top:10px"><table class="pm-tbl pm-cards"><thead><tr><th>${T('Feature (F)','Feature (F)')}</th><th>${T('Changed through','Sửa qua')}</th><th>${T('Journey steps','Bước hành trình')}</th><th>${T('Risk if broken','Rủi ro nếu hỏng')}</th><th>${T('PRs on this F (code clash first)','PR trên F này (đụng code trước)')}</th></tr></thead><tbody>${rows||`<tr><td colspan="5" class="pm-hint">${T('The areas this PR changes have no F row.','Các vùng PR này sửa không có dòng F.')}</td></tr>`}</tbody></table></div>`+
      (none.length?`<div class="pm-note">${T('No F row for','Không có dòng F cho')}: ${none.map(f=>ENT.a(f.key,f.title)).join(', ')}.</div>`:'')+
      ((M.n.tests_changed||[]).length?`<div class="pm-note"><b>${T('Tests this PR edits','Test PR này sửa')}:</b> ${(M.n.tests_changed||[]).map(t=>ENT.a('test:'+t,t.split('/').pop())).join(' · ')}</div>`:'');
    return w;
  }

  // ---------------------------------------------------------------- 3 · linked PRs (network)
  function network(M){
    const cl=M.links.filter(CODE),near=cl.filter(l=>RANK[l.level]<=2),Ls=(near.length?near:cl).slice(0,14),left=Ls.filter(l=>l.dir==='merged'),right=Ls.filter(l=>l.dir!=='merged');
    if(!Ls.length&&M.links.length) return el('div',{class:'pm-note'},T('No PR shares code with this PR; only same-feature PRs (table above).','Không PR nào chung code với PR này; chỉ có PR cùng feature (bảng ở trên).'));
    if(!Ls.length) return el('div',{class:'pm-note'},T('No linked PR: no code clash with the merges of the last 24 h and no other open or recently merged PR on the same feature.','Không có PR liên quan: không đụng code với các merge trong 24 giờ qua và không PR mở / mới merge nào cùng feature.'));
    const W=1000,rh=40,H=Math.max(left.length,right.length,3)*rh+50,cx=W/2,cy=H/2,bw=290,bh=34,cw=210,ch=64;
    const svg=sv('svg',{viewBox:`0 0 ${W} ${H}`,class:'pm-svg',role:'img','aria-label':T('This PR in the middle; merged PRs on the left, open PRs on the right; line style = how close the code is','PR này ở giữa; PR đã merge bên trái, PR đang mở bên phải; kiểu đường = mức gần nhau của code')});
    arrowDefs(svg);
    svg.append(txt(16,18,T('Merged','Đã merge'),{fill:'var(--text-muted)','font-size':'11','font-weight':'700'}));
    svg.append(txt(W-16,18,T('Open','Đang mở'),{fill:'var(--text-muted)','font-size':'11','font-weight':'700','text-anchor':'end'}));
    const side=(arr,isL)=>{const y0=cy-(arr.length-1)*rh/2;arr.forEach((l,i)=>{
      const y=y0+i*rh,x=isL?16:W-16-bw,ex=isL?x+bw:x,sx=isL?cx-cw/2:cx+cw/2,mx=(sx+ex)/2;
      svg.append(sv('path',{d:`M${isL?ex:sx} ${isL?y:cy} C${mx} ${isL?y:cy}, ${mx} ${isL?cy:y}, ${isL?sx:ex} ${isL?cy:y}`,fill:'none',stroke:LCOL[l.level],'stroke-width':LW[l.level],class:LCLS[l.level]||null,'stroke-dasharray':LCLS[l.level]?null:LDASH[l.level],'marker-end':'url(#pmArrow)',opacity:l.inactive?.5:1}));
      const g=sv('g',{class:'pm-node',tabindex:'0',role:'button','data-pm':l.num,'aria-label':`#${l.num} ${l.title||''}`});
      g.append(sv('rect',{x,y:y-bh/2,width:bw,height:bh,rx:7,fill:'var(--surface-1)',stroke:LCOL[l.level],'stroke-width':RANK[l.level]<=1?'1.6':'1','stroke-dasharray':l.level==='feat'?'3 3':null,opacity:l.inactive?.6:1}));
      g.append(txt(x+8,y-2,`#${l.num}`,{fill:'var(--text-primary)','font-size':'13','font-weight':'700'}));
      g.append(txt(x+56,y-2,String(l.title||'').slice(0,36)+(String(l.title||'').length>36?'…':''),{fill:'var(--text-secondary)','font-size':'12'}));
      g.append(txt(x+8,y+12,`${l.level==='feat'?T('same feature','cùng feature'):l.level.toUpperCase()}${l.dir!=='merged'&&l.verb?' · '+L(VERB[l.verb]||[l.verb,l.verb]):''}${l.sub?' · '+L(SUB[l.sub]||[l.sub,l.sub]):''}`,{fill:LCOL[l.level],'font-size':'11','font-weight':'700'}));
      const t=sv('title',{});t.textContent=`#${l.num} · ${L(LV[l.level])} · ${L(l.same)}`;g.append(t);svg.append(g);});};
    side(left,true);side(right,false);
    const c=sv('g',{});c.append(sv('rect',{x:cx-cw/2,y:cy-ch/2,width:cw,height:ch,rx:10,fill:'color-mix(in srgb,var(--series-1) 18%,var(--surface-1))',stroke:'var(--series-1)','stroke-width':'2'}));
    c.append(txt(cx,cy-8,`#${M.num}`,{'text-anchor':'middle',fill:'var(--text-primary)','font-size':'15','font-weight':'800'}));
    wrap(M.n.title||'',30).slice(0,1).forEach(ln=>c.append(txt(cx,cy+10,ln,{'text-anchor':'middle',fill:'var(--text-secondary)','font-size':'10.5'})));
    c.append(txt(cx,cy+24,M.n.state||'',{'text-anchor':'middle',fill:'var(--series-1)','font-size':'10','font-weight':'700'}));
    svg.append(c);
    const w=el('div',{});w.append(el('div',{class:'pm-svgw'},svg));
    if(cl.length>Ls.length) w.append(el('div',{class:'pm-note'},T(`The diagram shows the ${Ls.length} closest code clashes (${near.length?'P0–P2':'P3–P4'}); all ${M.links.length} links are in the table above.`,`Sơ đồ hiện ${Ls.length} cặp đụng code gần nhất (${near.length?'P0–P2':'P3–P4'}); đủ ${M.links.length} liên kết ở bảng phía trên.`)));
    return w;
  }
  function linkTable(M){
    if(!M.links.length) return null;
    const w=document.createElement('div');w.className='pm-tblw';
    const GRP=[['now',l=>RANK[l.level]<=1,['Must rebase now · P0 / P1 (same function or removed symbol)','Phải rebase ngay · P0 / P1 (cùng hàm hoặc symbol bị xoá)']],
      ['later',l=>RANK[l.level]===2||RANK[l.level]===3,['Rebase before merge · P2 / P3 (nearby lines or same file)','Rebase trước merge · P2 / P3 (dòng gần nhau hoặc cùng file)']],
      ['p4',l=>l.level==='p4',['Tests / docs only · P4','Chỉ test / docs · P4']],
      ['fyi',l=>l.level==='feat',[`Same feature only, no shared code · FYI${M.fcap?` (the 10 most related of ${M.fcap})`:''}`,`Chỉ cùng feature, không chung code · để biết${M.fcap?` (10 PR liên quan nhất trong ${M.fcap})`:''}`]]];
    const row=l=>`<tr><td><span class="pm-pr" data-pm="${esc(l.num)}">#${esc(l.num)}</span> <span class="obsraw">${esc(l.title||'')}</span><div class="pm-hint">${esc(l.dir==='merged'?T('merged','đã merge'):T('open','đang mở'))}${l.sub?' · '+esc(L(SUB[l.sub]||[l.sub,l.sub])):''}${l.inactive?' · '+T('no CI now','hiện không có CI'):''}</div></td>`+
        `<td data-l="${esc(T('Overlap','Mức chồng'))}"><span class="pm-chip ${l.level}">${esc(L(LV[l.level]))}</span></td><td data-l="${esc(T('What is shared','Phần chung'))}">${esc(L(l.same))}${(l.shared||[]).length?`<div class="pm-hint obsraw">${l.shared.slice(0,4).map(f=>esc(f.split('/').pop())).join(', ')}${l.shared.length>4?' +'+(l.shared.length-4):''}</div>`:''}</td>`+
        `<td data-l="${esc(T('Next step','Bước tiếp theo'))}">${l.dir==='merged'?'<span class="pm-hint">— '+T('merged','đã merge')+'</span>':l.verb==='idle'?`<b>${esc(l.sub==='conflict'?T('resolve conflict, then rebase','gỡ xung đột, rồi rebase'):l.sub==='draft'?T('rebase when out of draft','rebase khi hết nháp'):T('rebase if revived','rebase nếu làm tiếp'))}</b>`:l.verb?`<b>${esc(L(VERB[l.verb]||[l.verb,l.verb]))}</b>`:'—'}</td></tr>`;
    w.innerHTML=`<table class="pm-tbl pm-cards"><thead><tr><th>PR</th><th>${T('Overlap','Mức chồng')}</th><th>${T('What is shared','Phần chung')}</th><th>${T('Next step for that PR','Bước tiếp theo của PR đó')}</th></tr></thead>`+
      GRP.map(([k,f,lab])=>{const rs=M.links.filter(f);return rs.length?`<tbody><tr class="pm-grp pm-grp-${k}"><th colspan="4">${esc(L(lab))} · ${rs.length}</th></tr>${rs.map(row).join('')}</tbody>`:'';}).join('')+`</table>`;
    return w;
  }

  // ---------------------------------------------------------------- overlay
  function el(tag,attrs,...kids){const e=document.createElement(tag);for(const k in attrs||{}) e.setAttribute(k,attrs[k]);kids.flat().forEach(x=>{if(x==null)return;e.append(x.nodeType?x:document.createTextNode(x));});return e;}
  // what to do with THIS PR (open: its own verdict + the closest merged clash; merged: which open PRs must move)
  function decision(M){
    const n=M.n,cl=M.links.filter(CODE),VC={rebase:'warn',red:'warn',dco:'bad',block:'bad',stop:'bad',cancel:'bad',hold:'warn',later:'warn',merge:'ok',full:'ok',go:'ok',review:'',author:'',keep:'',idle:''};
    const prs=a=>a.slice(0,6).map(l=>`<span class="pm-pr" data-pm="${esc(l.num)}">#${esc(l.num)}</span>`).join(' ')+(a.length>6?` +${a.length-6}`:'');
    let verb,cls,txt;
    if(n.state==='merged'){
      const now=cl.filter(l=>l.dir!=='merged'&&RANK[l.level]<=1),later=cl.filter(l=>l.dir!=='merged'&&(RANK[l.level]===2||RANK[l.level]===3));
      verb=T('Merged','Đã merge'); cls=now.length?'warn':'ok';
      txt=now.length?T(`${now.length} open PR(s) must rebase now (P0/P1): ${prs(now)}.`,`${now.length} PR đang mở phải rebase ngay (P0/P1): ${prs(now)}.`)+(later.length?' '+T(`${later.length} more rebase before merge (P2/P3).`,`${later.length} PR khác rebase trước merge (P2/P3).`):'')
        :later.length?T(`No open PR must rebase now; ${later.length} rebase before merge (P2/P3): ${prs(later)}.`,`Không PR mở nào phải rebase ngay; ${later.length} PR rebase trước merge (P2/P3): ${prs(later)}.`)
        :T('No open PR shares code with it.','Không PR đang mở nào chung code với nó.');
    }else{
      const v=(M.q&&M.q.verb)||(M.g&&M.g.verb)||null,top=cl.filter(l=>l.dir==='merged')[0],sub=(M.q&&M.q.sub)||(M.g&&M.g.p_sub);
      verb=v?L(VERB[v]||[v,v]).replace(/^./,c=>c.toUpperCase()):T('No decision yet','Chưa có quyết định'); cls=VC[v]||'';
      txt=(top?T(`Clashes ${L(LV[top.level])} with merged `,`Đụng ${L(LV[top.level])} với PR đã merge `)+`<span class="pm-pr" data-pm="${esc(top.num)}">#${esc(top.num)}</span>${top.same?': '+esc(L(top.same).replace(/^[^:]*:\s*/,'')):''} `:T('No clash with the merges of the last 24 h. ','Không đụng merge nào trong 24 giờ qua. '))+
        (sub?esc(L(SUB[sub]||[sub,sub]))+'. ':'')+(M.q&&M.q.why?`<span class="pm-hint">${esc(L(M.q.why))}</span>`:'');
    }
    const d=el('div',{class:'pm-dec '+cls});d.innerHTML=`<span class="v">${esc(verb)}</span><span class="t">${txt}</span>`;return d;
  }
  let cur=null,stack=[],opener=null;
  function render(num){
    const M=model(num); if(!M) return false; cur=String(num);
    const n=M.n,cl=M.links.filter(l=>l.level!=='feat'),byL={};cl.forEach(l=>byL[l.level]=(byL[l.level]||0)+1);
    const Fs=Object.keys(M.F).sort(),J=M.CP.journeys||[],NF=M.CP.node_f||{};
    const jt=J.filter(j=>(NF[j.id]||[]).some(fs=>fs.some(f=>M.F[f]))).map(j=>j.id);
    head.innerHTML=`<div><span class="id">#${esc(M.num)}</span><span class="ti obsraw" id="pmTitle">${esc(n.title||'')}</span></div>`+
      `<div class="mt"><span class="pm-chip">${esc(n.state||'')}</span><a href="${esc(n.url||GH+'/pull/'+M.num)}" target="_blank" rel="noopener">GitHub ↗</a><a href="${esc((n.url||GH+'/pull/'+M.num)+'/files')}" target="_blank" rel="noopener">Diff ↗</a><button type="button" class="pm-btn" id="pmCard">${T('Open in entity index','Mở trong bảng thực thể')}</button>`+
      `<span class="pm-hint">${[n.author,n.at?n.at+' UTC':null,n.labels&&n.labels.length?T('labels','label')+': '+n.labels.join(', '):null,n.nfiles?n.nfiles+' '+T('files','file'):null].filter(Boolean).map(esc).join(' · ')}</span></div>`;
    const dec=decision(M),JN=J.filter(j=>jt.includes(j.id)).map(j=>j.id+' '+j.name.toLowerCase());
    const facts=el('div',{class:'pm-facts'},
      el('div',{},el('b',{},T('Touches','Chạm')),`${Fs.length} ${T('features','feature')} (${Fs.join(' ')||'—'})`),
      el('div',{},el('b',{},T('Journeys','Hành trình')),JN.join(' · ')||T('none','không')),
      el('div',{},el('b',{},T('Shares code with','Chung code với')),cl.length?`${cl.length} PR (${['p0','p1','p2','p3','p4'].filter(x=>byL[x]).map(x=>byL[x]+' '+x.toUpperCase()).join(', ')})`:T('no PR','không PR nào'),M.links.length-cl.length?` · +${M.links.length-cl.length} ${T('same-feature','cùng feature')}`:''));
    const _sum=T(`This PR changes ${M.feats.filter(f=>f.s==='strong').length} code area(s)${M.feats.some(f=>f.s==='weak')?` (+${M.feats.filter(f=>f.s==='weak').length} tests only)`:''} → features ${Fs.join(', ')||'—'} → journeys ${jt.join(', ')||'—'}. Linked PRs: ${cl.length} share code (${['p0','p1','p2','p3','p4'].filter(x=>byL[x]).map(x=>byL[x]+' '+x.toUpperCase()).join(', ')||'none'}), ${M.links.length-cl.length} share a feature.`,
      `PR này sửa ${M.feats.filter(f=>f.s==='strong').length} vùng code${M.feats.some(f=>f.s==='weak')?` (+${M.feats.filter(f=>f.s==='weak').length} chỉ test)`:''} → feature ${Fs.join(', ')||'—'} → hành trình ${jt.join(', ')||'—'}. PR liên quan: ${cl.length} chung code (${['p0','p1','p2','p3','p4'].filter(x=>byL[x]).map(x=>byL[x]+' '+x.toUpperCase()).join(', ')||'không'}), ${M.links.length-cl.length} chung feature.`);
    const info=el('div',{class:'pm-info',role:'region','aria-live':'polite'});
    body.replaceChildren(
      dec,facts,
      fLookup(M),
      el('div',{class:'pm-h'},T('1 · Critical path','1 · Đường critical (critical path)'),el('span',{class:'pm-draft'},T('draft mapping','ánh xạ nháp'))),
      el('div',{class:'pm-leg2'},el('span',{class:'k k-lit'},T('lit step = this PR touches one of its F-ids','bước sáng = PR này chạm một F-id của nó')),el('span',{class:'k k-dash'},T('dashed = tests only','nét đứt = chỉ test')),el('span',{class:'k k-badge'},T('orange number = PRs sharing code with this PR on that step','số cam = số PR chung code với PR này ở bước đó')),el('span',{class:'k'},T('click a step for proof and risk','bấm một bước để xem bằng chứng và rủi ro'))),
      SMALL()?critList(M,info):el('div',{class:'pm-svgw'},critPath(M,info)),info,
      el('div',{class:'pm-h'},T('2 · Feature matrix','2 · Ma trận feature'),el('span',{class:'pm-draft'},T('draft mapping','ánh xạ nháp')),el('small',{},T('code area changed → feature F → risk','vùng code bị sửa → feature F → rủi ro'))),
      featMatrix(M),
      el('div',{class:'pm-h'},T('3 · Linked PRs','3 · PR liên quan'),el('small',{},T('click a PR to open its map','bấm một PR để mở map của nó'))),
      linkTable(M),
      SMALL()?null:el('div',{class:'pm-leg'},['p1','p2','p3','p4','feat'].map(x=>el('span',{style:`color:${LCOL[x]}`},el('i',{style:`border-top:${LW[x]+0.5}px ${LDASH[x]==='none'?'solid':'dashed'} currentColor`}),L(LV[x])))),
      SMALL()?null:network(M),
      el('div',{class:'pm-note'},T(`Sources: code clashes = tab 6A diff rules on the snapshot ${ops().overlap&&ops().overlap.snap_at||''} (merges of the last 24 h × open PRs); features = entity index (changed files × code areas); F-ids and journeys = ${M.CP.src||'feature matrix xlsx'}. The area → F and step → F mappings are DRAFT (next_release.py NODE_F / AREA_F).`,
        `Nguồn: đụng code = luật diff của tab 6A trên snapshot ${ops().overlap&&ops().overlap.snap_at||''} (merge 24 giờ × PR đang mở); feature = bảng thực thể (file bị sửa × vùng code); F-id và hành trình = ${M.CP.src||'xlsx feature matrix'}. Ánh xạ vùng → F và bước → F là BẢN NHÁP (next_release.py NODE_F / AREA_F).`)));
    back.hidden=!stack.length; back.setAttribute('aria-label',T('Back','Quay lại'));
    document.getElementById('pmClose').setAttribute('aria-label',T('Close','Đóng'));
    pause.title=T('Animate the flows (off by default)','Chạy hiệu ứng dòng chảy (mặc định tắt)');pLab();
    ov.scrollTop=0; return true;
  }
  function open(num,push){
    num=String(num).replace(/^#|^pr:/,'');
    if(!ENT.get('pr:'+num)) return false;
    if(!ov.classList.contains('on')){opener=document.activeElement;stack=[];}
    else if(push!==false&&cur&&cur!==num) stack.push(cur);
    if(window.closeEntity) closeEntity();
    render(num); ov.classList.add('on'); ov.setAttribute('aria-hidden','false'); document.body.style.overflow='hidden';
    document.getElementById('pmClose').focus({preventScroll:true}); return true;
  }
  function close(){
    if(!ov.classList.contains('on')) return;
    ov.classList.remove('on'); ov.setAttribute('aria-hidden','true'); document.body.style.overflow=''; cur=null; stack=[];
    if(opener&&opener.isConnected&&opener.focus) opener.focus({preventScroll:true}); opener=null;
  }
  window.openPrMap=open; window.closePrMap=close;
  document.getElementById('pmClose').addEventListener('click',close);
  back.addEventListener('click',()=>{const k=stack.pop(); if(k) open(k,false);});
  function pLab(){const p=ov.classList.contains('paused');pause.textContent=p?T('▶ animate','▶ chạy hiệu ứng'):T('⏸ pause','⏸ dừng');pause.setAttribute('aria-pressed',String(p));}
  pause.addEventListener('click',()=>{ov.classList.toggle('paused');pLab();});
  ov.addEventListener('click',e=>{
    if(e.target===ov){close();return;}
    if(e.target.closest('#pmCard')){const k='pr:'+cur;close();if(window.openEntity) openEntity(k);return;}
    const p=e.target.closest('[data-pm]'); if(p){e.preventDefault();e.stopPropagation();open(p.getAttribute('data-pm'));}
  });
  ov.addEventListener('keydown',e=>{
    if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close();return;}
    if((e.key==='Enter'||e.key===' ')&&e.target.matches&&e.target.matches('.pm-pr,g.pm-node[data-pm]')){e.preventDefault();open(e.target.getAttribute('data-pm'));}
  });
  // tab 6A: a click on a PR number opens its map (window capture runs before the entity drawer's document handler)
  window.addEventListener('click',e=>{
    // inside the map: a feature / test link opens the entity card, so the map steps aside
    if(ov.classList.contains('on')&&e.target.closest&&e.target.closest('#pmOv [data-ent]')&&!e.target.closest('[data-pm]')){ov.classList.remove('on');ov.setAttribute('aria-hidden','true');document.body.style.overflow='';cur=null;stack=[];return;}
    if(e.ctrlKey||e.metaKey||e.shiftKey||e.button) return;
    const sec=e.target.closest&&e.target.closest('section[data-ops="overlap"]'); if(!sec) return;
    const a=e.target.closest('[data-ent^="pr:"],a[href*="/pull/"]'); if(!a) return;
    const m=(a.getAttribute('data-ent')||'').match(/^pr:(\d+)$/)||(a.getAttribute('href')||'').match(/\/pull\/(\d+)(?:$|[/?#])/);
    if(!m||(a.getAttribute('href')||'').includes('/files')||!ENT.get('pr:'+m[1])) return;
    e.preventDefault(); e.stopPropagation(); open(m[1]);
  },true);
  // every tab: "PR map" button in the PR card of the entity drawer
  const eh=document.getElementById('entHead');
  if(eh) new MutationObserver(()=>{
    const id=eh.querySelector('.ent-id'); if(!id||eh.querySelector('.pm-open')) return;
    const m=id.textContent.match(/^#(\d+)$/); if(!m||!ENT.get('pr:'+m[1])) return;
    const b=el('button',{type:'button',class:'pm-btn pm-open',style:'margin-top:6px'},T('PR map: features · critical path · linked PRs','PR map: feature · critical path · PR liên quan'));
    b.addEventListener('click',()=>open(m[1]));eh.append(b);
  }).observe(eh,{childList:true,subtree:true});
  addEventListener('langchange',()=>{if(cur) render(cur);});
})();
</script>
<!-- PRMAP:JS:END -->"""


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor)
    return page[:i] + block.strip() + "\n" + page[i:] if before else page[:i + len(anchor)] + "\n" + block.strip() + page[i + len(anchor):]


def main():
    page = open(PAGE, encoding="utf-8").read()
    if 'id="entData"' not in page or "ENTUI:JS:END" not in page:
        raise SystemExit("build_pr_map: run build_entities.py and build_entity_ui.py first")
    page = put(page, "/* PRMAP:CSS:START */", "/* PRMAP:CSS:END */", CSS, "</style>")
    page = put(page, "<!-- PRMAP:HTML:START -->", "<!-- PRMAP:HTML:END -->", HTML, "<!-- ENTUI:JS:START -->")
    page = put(page, "<!-- PRMAP:JS:START -->", "<!-- PRMAP:JS:END -->", JS, "<!-- ENTUI:JS:END -->", before=False)
    open(PAGE, "w", encoding="utf-8").write(page)
    print("pr map: page bytes", len(page.encode("utf-8")))


if __name__ == "__main__":
    main()
