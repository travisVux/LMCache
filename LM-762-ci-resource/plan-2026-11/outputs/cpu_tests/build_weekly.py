"""Release · 'Weekly full build' tab (#obs/weekly, alias #weekly), 2026-11-26. Idempotent.

Source: GitHub Actions workflow .github/workflows/weekly_full_build.yml on LMCache/LMCache dev (one job per device lane:
CUDA, XPU, later AMD / RBLN). Each lane uploads report.json (.github/scripts/weekly_full_build.py): the Buildkite child
pipelines of the lane and the problems that fail the run. ops-app collect_weekly.py stores runs -> lanes -> pipelines ->
problems in ops.db; export_page_data.py writes them to release_desk.json ('weekly'); this module embeds them.

Four sections, all drawn by JS (EN / VI through T(en, vi), the page's .dk-* design system):
  7A  hero      status of the run (PASSED / FAILED / RUNNING / TIMED OUT / CANCELLED), meta, 4 tiles, compare link
  7B  devices   CUDA · XPU · AMD · RBLN: lane state, duration, GitHub job, pass bar, Buildkite pipelines
  7C  problems  device -> pipeline -> problem (kind chip, label, exit status, copy-able debug / re-run commands)
  7D  trend     12-week strip + history table; a click (or Enter / Space, arrow keys in the strip) re-draws 7A-7C for that run
Run after build_desk.py (build_page.py does).
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = str(Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
DESK = os.path.join(HERE, "release_desk.json")

HTML = r"""
<!-- WEEKLY:HTML:START -->
<section class="card" data-view="obs" data-tab="weekly" id="wkHero"><div class="head"><h2 id="wkHeroH">7 · Weekly full build</h2></div><div id="wkHeroB"></div></section>
<section class="card" data-view="obs" data-tab="weekly" id="wkDev"><div class="head"><h2 id="wkDevH">7 · Device lanes</h2></div><div id="wkDevB"></div></section>
<section class="card" data-view="obs" data-tab="weekly" id="wkProb"><div class="head"><h2 id="wkProbH">7 · Problems</h2></div><div id="wkProbB"></div></section>
<section class="card" data-view="obs" data-tab="weekly" id="wkTrend"><div class="head"><h2 id="wkTrendH">7 · Trend</h2></div><div id="wkTrendB"></div></section>
<!-- WEEKLY:HTML:END -->
"""

CSS = r"""
/* WEEKLY:CSS:START */
.wk-top{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:0 0 12px}
.wk-big{display:inline-flex;align-items:center;gap:10px;padding:8px 18px;border-radius:999px;font-size:22px;font-weight:750;letter-spacing:.04em;
  border:2px solid var(--border);background:var(--surface-2);color:var(--text-2);white-space:nowrap}
.wk-big::before{content:"";width:12px;height:12px;border-radius:50%;background:var(--text-3)}
.wk-big.green{border-color:var(--ok);background:var(--ok-bg);color:var(--ok)}.wk-big.green::before{background:var(--ok)}
.wk-big.red{border-color:var(--bad);background:var(--bad-bg);color:var(--bad)}.wk-big.red::before{background:var(--bad)}
.wk-big.to{border-color:var(--warn);background:var(--warn-bg);color:var(--warn)}.wk-big.to::before{background:var(--warn)}
.wk-big.run{border-color:var(--info);background:var(--info-bg);color:var(--info)}.wk-big.run::before{background:var(--info);animation:wkPulse 1.4s ease-in-out infinite}
.wk-big.cxl{border-style:dashed;border-color:var(--border-strong);background:var(--surface-2);color:var(--text-2)}.wk-big.cxl::before{background:transparent;border:2px solid var(--text-3);box-sizing:border-box}
@keyframes wkPulse{50%{opacity:.3}}
@media (prefers-reduced-motion:reduce){.wk-big.run::before,.viz-root .dk-chip.wk-run::before,.wk-cell i.r{animation:none!important}}
.wk-meta{min-width:0;flex:1 1 280px;font-size:13px;color:var(--text-2);line-height:1.55}
.wk-meta b{color:var(--text-1)}
.wk-meta .obsraw{overflow-wrap:anywhere}
.wk-tiles{grid-template-columns:repeat(4,minmax(0,1fr))!important;margin:10px 0}
.dk-tile.wk-bad{border-color:var(--bad)}.dk-tile.wk-bad .v{color:var(--bad)}
.dk-tile.wk-ok .v{color:var(--ok)}
.wk-line{margin:10px 0 0;font-size:13px;color:var(--text-2);line-height:1.6}
.wk-line .dk-chip{margin-right:4px}
.wk-btn{all:unset;cursor:pointer;font-size:12.5px;font-weight:600;color:var(--accent-text);padding:1px 6px;border-radius:6px;border:1px solid var(--border)}
.wk-btn:hover{border-color:var(--accent-text)}.wk-btn:focus-visible{outline:2px solid var(--focus);outline-offset:1px}
.wk-devs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.wk-dev{border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--surface-1);min-width:0}
.wk-dev.off{background:var(--surface-2);border-style:dashed}
.wk-dev.bad{border-color:var(--bad)}.wk-dev.to{border-color:var(--warn)}.wk-dev.run{border-color:var(--info)}.wk-dev.cxl{border-style:dashed;border-color:var(--border-strong)}
.wk-dev h3{margin:0 0 6px;font-size:15px;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.wk-dev .dk-chip{margin-right:0}
.wk-bar{display:flex;gap:2px;height:8px;margin:8px 0 6px;border-radius:4px;overflow:hidden;background:var(--surface-2)}
.wk-bar i{flex:1;background:var(--ok)}.wk-bar i.f{background:var(--bad)}.wk-bar i.t{background:var(--warn)}.wk-bar i.r{background:var(--info)}.wk-bar i.c{background:var(--text-3)}
.wk-pl{list-style:none;margin:6px 0 0;padding:0;font-size:12.5px}
.wk-pl li{display:flex;gap:6px;align-items:baseline;padding:4px 0;border-top:1px solid var(--border);min-width:0}
.wk-pl li:first-child{border-top:0}
.wk-pl .nm{flex:1;min-width:0;overflow-wrap:anywhere;color:var(--text-1)}
.wk-pl .dk-chip{flex:0 0 auto}
.wk-pl a{flex:0 0 auto;white-space:nowrap}
.wk-ok-line{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:13.5px;color:var(--text-1)}
.viz-root .dk-chip.wk-dred{color:var(--surface-1)!important;background:var(--bad)!important}
.viz-root .dk-chip.wk-run{color:var(--info)!important;background:var(--info-bg)!important;border-color:var(--info)}
.viz-root .dk-chip.wk-run::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:currentColor;margin-right:5px;vertical-align:1px;animation:wkPulse 1.4s ease-in-out infinite}
.viz-root .dk-chip.wk-cxl{color:var(--text-2)!important;background:var(--surface-2)!important;border-style:dashed;border-color:var(--border-strong)}
.viz-root .dk-chip.wk-off{color:var(--text-3)!important;background:transparent!important;border-style:dashed}
.viz-root .dk-chip.wk-orange{color:color-mix(in oklab,var(--warn) 55%,var(--bad))!important;background:color-mix(in oklab,var(--warn-bg) 55%,var(--bad-bg))!important}
.wk-prob td{vertical-align:top}
.wk-prob .lab{overflow-wrap:anywhere;color:var(--text-1)}
.wk-prob .det{display:block;margin-top:2px;font-size:12px;color:var(--text-2);overflow-wrap:anywhere}
.wk-trend{display:flex;flex-wrap:wrap;gap:6px 4px;align-items:flex-end;margin:4px 0 6px}
.wk-wk{display:flex;flex-direction:column;align-items:center;gap:3px;min-width:22px}
.wk-wk .cells{display:flex;gap:2px;align-items:center;min-height:30px}
.wk-wk .wl{font-size:10.5px;color:var(--text-3);font-variant-numeric:tabular-nums}
.wk-cell{all:unset;cursor:pointer;display:inline-flex;padding:2px;border-radius:6px;border:2px solid transparent}
.wk-cell i{display:block;width:14px;height:22px;border-radius:3px;background:var(--text-3)}
.wk-cell i.p{background:var(--ok)}.wk-cell i.f{background:var(--bad)}.wk-cell i.t{background:var(--warn)}.wk-cell i.r{background:var(--info);animation:wkPulse 1.4s ease-in-out infinite}.wk-cell i.c{background:repeating-linear-gradient(135deg,var(--text-3) 0 2px,transparent 2px 5px);box-shadow:inset 0 0 0 1.5px var(--text-3)}
.wk-cell:hover{border-color:var(--border-strong)}
.wk-cell:focus-visible{outline:2px solid var(--focus);outline-offset:1px}
.wk-cell[aria-pressed="true"]{border-color:var(--accent)}
.wk-none{display:block;width:14px;height:22px;border-radius:3px;border:1.5px dashed var(--border-strong);box-sizing:border-box;margin:4px}
.wk-legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--text-2);margin:2px 0 10px}
.wk-legend i{display:inline-block;width:10px;height:14px;border-radius:2px;vertical-align:-2px;margin-right:4px;background:var(--text-3)}
.wk-legend i.p{background:var(--ok)}.wk-legend i.f{background:var(--bad)}.wk-legend i.t{background:var(--warn)}.wk-legend i.r{background:var(--info)}.wk-legend i.c{background:repeating-linear-gradient(135deg,var(--text-3) 0 2px,transparent 2px 5px);box-shadow:inset 0 0 0 1.5px var(--text-3)}.wk-legend i.n{background:transparent;border:1.5px dashed var(--border-strong);box-sizing:border-box}
.wk-hist tbody tr{cursor:pointer}
.wk-hist tbody tr:hover td{background:var(--surface-2)}
.wk-hist tbody tr.sel td{background:var(--accent-subtle)}
.wk-pick{all:unset;cursor:pointer;font-weight:650;color:var(--accent-text);white-space:nowrap}
.wk-pick:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.wk-hist td{white-space:nowrap}
@media (max-width:1100px){.wk-devs{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:700px){.wk-tiles{grid-template-columns:repeat(2,minmax(0,1fr))!important}.wk-big{font-size:19px;padding:6px 14px}}
@media (max-width:520px){.wk-devs{grid-template-columns:1fr}}
/* phones: a problem row stacks (chip + exit + copy + link on one line, the label below at full width) */
@media (max-width:700px){.viz-root table.wk-prob,.wk-prob tbody,.wk-prob tr{display:block!important;width:100%}.wk-prob tr{padding:6px 0;border-bottom:1px solid var(--border)}
  .wk-prob td{display:inline-block;width:auto!important;border:0!important;padding:2px 6px 2px 0!important;vertical-align:middle}.wk-prob td:nth-child(2){display:block;padding:4px 0!important}}
/* WEEKLY:CSS:END */
"""

JS = r"""
<!-- WEEKLY:JS:START -->
<script id="weeklyData" type="application/json">__DATA__</script>
<script>
(function(){
  let W;try{W=JSON.parse(document.getElementById('weeklyData').textContent);}catch(e){return;}
  W=W||{};const RUNS=W.runs||[],DEV=W.devices||['cuda','xpu','amd','rbln'],REPO=W.repo||'LMCache/LMCache';
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en;
  const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const raw=s=>`<span class="obsraw">${esc(s)}</span>`;
  const a=(u,t,cls)=>u?`<a href="${esc(u)}" target="_blank" rel="noopener"${cls?` class="${cls}"`:''}>${t}</a>`:t;
  const day=s=>s?String(s).slice(0,10):'–';
  const when=s=>s?String(s).slice(0,16).replace('T',' ')+' UTC':'–';
  const hrs=s=>s?(Date.now()-Date.parse(s))/36e5:NaN;
  const ago=s=>{const h=hrs(s);if(!isFinite(h))return '';return h<1?T('just now','vừa xong'):h<48?T(Math.round(h)+' h ago',Math.round(h)+' giờ trước'):T(Math.round(h/24)+' days ago',Math.round(h/24)+' ngày trước');};
  const mins=(x,y)=>x&&y?(Date.parse(y)-Date.parse(x))/6e4:null;
  const dur=m=>{if(m==null||!isFinite(m))return '–';m=Math.round(m);const h=Math.floor(m/60),r=m%60;return h?T(`${h} h ${r} min`,`${h} giờ ${r} phút`):T(`${r} min`,`${r} phút`);};
  const sha=s=>s?String(s).slice(0,8):'–';
  const DN={cuda:'CUDA',xpu:'XPU',amd:'AMD',rbln:'RBLN'},dn=d=>DN[d]||String(d).toUpperCase();
  // run status: [css class of the big pill, EN, VI, strip class]
  // one status palette for the whole tab: passed green · failed red · timed out amber · running blue (pulsing) · cancelled grey dashed · not run outline
  const CH={passed:'green',failed:'red',timed_out:'amber',running:'wk-run',cancelled:'wk-cxl',canceled:'wk-cxl',not_run:'wk-off',not_created:'wk-off'};
  const ST={passed:['green','PASSED','ĐẠT','p'],failed:['red','FAILED','LỖI','f'],timed_out:['to','TIMED OUT','QUÁ GIỜ','t'],
    running:['run','RUNNING','ĐANG CHẠY','r'],cancelled:['cxl','CANCELLED','ĐÃ HỦY','c']};
  const st=v=>ST[v]||['',String(v||'?').toUpperCase(),String(v||'?').toUpperCase(),''];
  const LANE={passed:['green','passed','đạt'],failed:['red','failed','lỗi'],timed_out:['amber','timed out','quá giờ'],running:['wk-run','running','đang chạy'],
    cancelled:['wk-cxl','cancelled','đã hủy'],not_run:['wk-off','Not run / skipped','Không chạy / bỏ qua']};
  const laneChip=s=>{const x=LANE[s]||['gray',s,s];return `<span class="dk-chip ${x[0]}">${esc(T(x[1],x[2]))}</span>`;};
  const KIND={failed:['red','failed','lỗi'],not_run:['wk-dred','not run','không chạy'],build:['red','build failed','build lỗi'],missing:['wk-dred','missing','thiếu'],
    suite_skipped:['wk-orange','suite skipped','bỏ qua suite'],workload_skipped:['wk-orange','workload skipped','bỏ qua workload'],soft_failed:['amber','soft failed','lỗi mềm']};
  const kindChip=k=>{const x=KIND[k]||['red',k,k];return `<span class="dk-chip ${x[0]}">${esc(T(x[1],x[2]))}</span>`;};
  const PST={passed:['passed','đạt'],failed:['failed','lỗi'],canceled:['canceled','đã hủy'],running:['running','đang chạy'],not_created:['not created','chưa tạo']};
  const TRIG={schedule:['scheduled','theo lịch'],workflow_dispatch:['manual','chạy tay']};
  const trig=e=>TRIG[e]?T(...TRIG[e]):raw(e||'?');
  // per-run numbers
  const lanesOf=r=>DEV.map(d=>[d,(r.lanes||{})[d]]).concat(Object.keys(r.lanes||{}).filter(d=>!DEV.includes(d)).map(d=>[d,r.lanes[d]]));
  const ran=r=>lanesOf(r).filter(([,l])=>l&&l.state!=='not_run');
  const pipes=r=>ran(r).flatMap(([d,l])=>(l.pipelines||[]).map(p=>({...p,device:d})));
  const probs=r=>pipes(r).flatMap(p=>(p.problems||[]).map(q=>({...q,device:p.device,slug:p.slug,number:p.number,purl:p.url})));
  const pOK=p=>!(p.problems||[]).length&&p.state==='passed';
  const hasRep=r=>ran(r).some(([,l])=>l.report);
  const done=r=>['passed','failed','timed_out'].includes(r.verdict);
  const pkey=q=>[q.device,q.slug,q.kind,q.label||q.detail||''].join('|');
  const wall=r=>mins(r.first_job_at,r.last_job_at);
  const NEWEST=RUNS[0]||null,DEFAULT=RUNS.find(r=>r.verdict!=='cancelled')||NEWEST;
  let SEL=DEFAULT?DEFAULT.run_id:null;
  const byId=id=>RUNS.find(r=>String(r.run_id)===String(id));
  const set=(id,h,body)=>{const e=document.getElementById(id);if(!e)return;const hh=e.querySelector('h2'),m=(hh.textContent.match(/^\s*\d+[A-Z]?\s·\s/)||['7 · '])[0];hh.textContent=m+h;document.getElementById(id+'B').innerHTML=body;};
  const tile=(k,v,d,cls)=>`<div class="dk-tile${cls?' '+cls:''}"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`;

  function hero(r){
    if(!r)return `<p class="dk-mute">${T('No weekly full build run in the last 12 weeks.','Không có lần chạy weekly full build nào trong 12 tuần qua.')}</p>`+schedLine();
    const s=st(r.verdict),idx=RUNS.indexOf(r);
    const staleH=hrs(NEWEST&&NEWEST.created_at),stale=staleH>8*24?`<span class="dk-stale" data-wk="stale">STALE · ${T('no run in '+Math.round(staleH/24)+' days','không có lần chạy trong '+Math.round(staleH/24)+' ngày')}</span>`:'';
    const R=ran(r),lp=R.filter(([,l])=>l.state==='passed').length,P=pipes(r),pp=P.filter(pOK).length,Q=probs(r);
    const byKind={};Q.forEach(q=>byKind[q.kind]=(byKind[q.kind]||0)+1);
    const green=RUNS.slice(idx+1).find(x=>x.verdict==='passed'),isGreen=r.verdict==='passed';
    const notRun=lanesOf(r).filter(([,l])=>!l||l.state==='not_run').map(([d])=>dn(d));
    const meta=`<div class="wk-meta"><div><b>${T('Run','Run')} #${esc(r.number)}</b>${r.attempt>1?` · ${T('attempt','lần chạy')} ${esc(r.attempt)}`:''} · ${when(r.created_at)} · ${ago(r.created_at)} · ${trig(r.event)} · `+
      `${raw(r.head_branch||'dev')} @ ${a(`https://github.com/${REPO}/commit/${esc(r.head_sha||'')}`,raw(sha(r.head_sha)))} · ${T('wall time','tổng thời gian')} ${dur(wall(r))}${stale}</div>`+
      `<div>${a(r.url,T('Open the run on GitHub Actions ↗','Mở run trên GitHub Actions ↗'))}${r.prepare&&r.prepare!=='success'?` · <span class="dk-chip red">${T('prepare job','job prepare')}: ${raw(r.prepare)}</span>`:''}</div></div>`;
    const newer=RUNS.slice(0,idx).filter(x=>x.verdict==='cancelled');
    const nNote=r===DEFAULT&&newer.length?`<p class="wk-line">${T('Newer run','Run mới hơn')} ${newer.map(x=>`<button type="button" class="wk-btn" data-wk-run="${x.run_id}">#${esc(x.number)}</button>`).join(' ')} ${T('was cancelled; this is the newest run with a result.','đã bị hủy; đây là run mới nhất có kết quả.')}</p>`:'';
    const back=r!==DEFAULT&&DEFAULT?`<p class="wk-line">${T('You are looking at an older run.','Bạn đang xem một run cũ hơn.')} <button type="button" class="wk-btn" data-wk-run="${DEFAULT.run_id}">${T('Back to the newest result','Về kết quả mới nhất')} (#${esc(DEFAULT.number)})</button></p>`:'';
    const tiles=`<div class="dk-hero wk-tiles" data-wk="tiles">`+
      tile(T('Device lanes','Lane thiết bị'),R.length?`${lp} / ${R.length}`:'–',R.map(([d,l])=>`${dn(d)} ${l.state==='passed'?'✓':l.state==='failed'||l.state==='timed_out'?'✗':'…'}`).join(' · ')+(notRun.length?`<br>${T('not run','không chạy')}: ${notRun.join(', ')}`:''),
        R.length&&lp===R.length?'wk-ok':R.some(([,l])=>l.state==='failed'||l.state==='timed_out')?'wk-bad':'')+
      tile(T('Pipelines','Pipeline'),P.length?`${pp} / ${P.length}`:'–',T('Buildkite builds with no problem','Build Buildkite không có vấn đề'),P.length&&pp===P.length?'wk-ok':pp<P.length?'wk-bad':'')+
      tile(T('Problems','Vấn đề'),hasRep(r)?Q.length:'–',Q.length?Object.entries(byKind).map(([k,n])=>`${n} ${esc(T((KIND[k]||[0,k])[1],(KIND[k]||[0,0,k])[2]))}`).join(' · '):hasRep(r)?T('no failed, missing or skipped job','không có job lỗi, thiếu hay bị bỏ qua'):T('no report for this run','run này không có report'),Q.length?'wk-bad':'')+
      tile(T('Last green','Xanh gần nhất'),isGreen?T('this run','run này'):green?a(green.url,'#'+esc(green.number)):'–',
        isGreen?when(r.created_at):green?`${when(green.created_at)} · ${ago(green.created_at)}`:T('none in the last 12 weeks','không có trong 12 tuần qua'))+`</div>`;
    let hint='';
    if(r.verdict==='failed'||r.verdict==='timed_out'){
      hint=green?`<span class="dk-hint" data-wk="compare">⚑ ${T('The break came in between the last green run and this one:','Lỗi xuất hiện giữa run xanh gần nhất và run này:')} ${a(`https://github.com/${REPO}/compare/${esc(green.head_sha)}...${esc(r.head_sha)}`,raw(sha(green.head_sha)+'…'+sha(r.head_sha))+' ↗')} (#${esc(green.number)} → #${esc(r.number)})</span>`
        :`<span class="dk-hint" data-wk="compare">⚑ ${T('No green run before this one in the last 12 weeks: fix it to set the baseline.','Không có run xanh nào trước run này trong 12 tuần qua: sửa để có baseline.')}</span>`;}
    const reruns=R.filter(([,l])=>l.earlier_failed).map(([d,l])=>`${dn(d)} (${l.earlier_failed})`);
    const rr=reruns.length&&r.verdict==='passed'?`<span class="dk-hint">⚑ ${T('Passed only on a re-run, earlier failed attempts:','Chỉ đạt khi chạy lại, các lần trước bị lỗi:')} ${reruns.join(', ')} · ${T('check for flakiness','kiểm tra có chập chờn không')}</span>`:'';
    return `<div class="wk-top"><span class="wk-big ${s[0]}" data-wk="status" data-run="${r.run_id}" role="status">${esc(T(s[1],s[2]))}</span>${meta}</div>`+nNote+back+tiles+hint+rr+delta(r,idx)+schedLine();
  }
  function delta(r,idx){
    const prev=RUNS.slice(idx+1).find(done);
    if(!prev)return `<p class="wk-line">${T('No earlier finished run to compare with.','Không có run đã xong nào trước đó để so sánh.')}</p>`;
    const sp=st(prev.verdict),sr=st(r.verdict);
    const A=new Set(probs(r).map(pkey)),B=new Set(probs(prev).map(pkey));
    const nNew=[...A].filter(k=>!B.has(k)).length,nFix=[...B].filter(k=>!A.has(k)).length;
    const lanes=DEV.filter(d=>{const x=(r.lanes||{})[d],y=(prev.lanes||{})[d];return (x&&x.state)!==(y&&y.state);}).map(d=>`${dn(d)}: ${esc(T(...((LANE[((prev.lanes||{})[d]||{}).state||'not_run']||[0,'?','?']).slice(1))))} → ${esc(T(...((LANE[((r.lanes||{})[d]||{}).state||'not_run']||[0,'?','?']).slice(1))))}`);
    const cmp=prev.head_sha&&r.head_sha&&prev.head_sha!==r.head_sha?` · ${a(`https://github.com/${REPO}/compare/${esc(prev.head_sha)}...${esc(r.head_sha)}`,T('commits in between ↗','commit ở giữa ↗'))}`:'';
    return `<p class="wk-line" data-wk="delta"><b>${T('Changed vs the previous run','Thay đổi so với run trước')}</b> <button type="button" class="wk-btn" data-wk-run="${prev.run_id}">#${esc(prev.number)}</button> ${day(prev.created_at)}: `+
      `${esc(T(sp[1],sp[2]))} → ${esc(T(sr[1],sr[2]))} · <span class="dk-chip ${nNew?'red':'gray'}">${nNew} ${T('new problems','vấn đề mới')}</span><span class="dk-chip ${nFix?'green':'gray'}">${nFix} ${T('fixed','đã hết')}</span>`+
      (lanes.length?` · ${T('lanes','lane')}: ${lanes.join(' · ')}`:'')+cmp+`</p>`;
  }
  function schedLine(){const S=W.schedule||{};const en=S.enabled===true?T('enabled on dev','đã bật trên dev'):S.enabled===false?T('not enabled on dev yet: manual runs only','chưa bật trên dev: chỉ chạy tay'):T('state unknown','chưa rõ trạng thái');
    return `<p class="wk-line dk-mute">${T('Schedule','Lịch')}: ${raw(S.text||'Sun 08:00 UTC (cron 0 8 * * 0)')} · ${en} · ${a(W.workflow_url,'weekly_full_build.yml ↗')} · ${T('collected','thu thập lúc')} ${when(W.collected_at)}</p>`;}
  function devices(r){
    if(!r)return '';
    const known=new Set(RUNS.flatMap(x=>Object.keys(x.lanes||{})));
    return `<div class="wk-devs" data-wk="devices">`+lanesOf(r).map(([d,l])=>{
      if(!l||l.state==='not_run'){const why=!known.has(d)?T('No lane for this device in the workflow yet.','Workflow chưa có lane cho thiết bị này.'):T('Not part of this run (device input or skipped job).','Không thuộc run này (input device hoặc job bị bỏ qua).');
        return `<div class="wk-dev off" data-dev="${esc(d)}"><h3>${dn(d)} ${laneChip('not_run')}</h3><p class="dk-mute" style="margin:0">${why}</p></div>`;}
      const P=l.pipelines||[],ok=P.filter(pOK).length,bad=l.state==='failed'||l.state==='timed_out';
      const list=P.length?`<ul class="wk-pl">`+P.map(p=>{const n=(p.problems||[]).length;const c=pOK(p)?'green':n||p.state==='failed'?'red':CH[p.state]||'gray';
        return `<li><span class="dk-chip ${c}">${esc(PST[p.state]?T(...PST[p.state]):p.state||'?')}</span><span class="nm">${raw(p.slug)}${n?` <span class="dk-chip red">${n} ${T('problems','vấn đề')}</span>`:''}${(p.retried||[]).length?` <span class="dk-chip amber" title="${esc((p.retried||[]).join(', '))}">${(p.retried||[]).length} ${T('retried','chạy lại')}</span>`:''}</span>${a(p.url,'#'+esc(p.number))}</li>`;}).join('')+`</ul>`
        :`<p class="dk-mute" style="margin:6px 0 0">${l.state==='running'?T('Still running: the pipelines and report.json appear when this lane finishes.','Đang chạy: pipeline và report.json sẽ hiện khi lane này chạy xong.'):l.report?T('The report lists no pipeline.','Report không có pipeline nào.'):T('No report.json for this lane (not uploaded, or the artifact expired before it was collected).','Lane này không có report.json (chưa upload, hoặc artifact đã hết hạn trước khi thu thập).')}</p>`;
      return `<div class="wk-dev${l.state==='failed'?' bad':l.state==='timed_out'?' to':l.state==='running'?' run':l.state==='cancelled'?' cxl':''}" data-dev="${esc(d)}"><h3>${dn(d)} ${laneChip(l.state)}</h3>`+
        `<div class="dk-mute">${dur(mins(l.started,l.completed))} · ${a(l.job_url,T('GitHub job ↗','Job GitHub ↗'))}${l.earlier_reports?` · ${T('re-run','chạy lại')} ×${esc(l.earlier_reports)}`:''}</div>`+
        (P.length?`<div class="wk-bar" role="img" aria-label="${esc(T(`${ok} of ${P.length} pipelines without problems`,`${ok} / ${P.length} pipeline không có vấn đề`))}">${P.map(p=>`<i class="${pOK(p)?'':(p.problems||[]).length||p.state==='failed'?'f':p.state==='running'?'r':p.state==='canceled'||p.state==='not_created'?'c':'f'}"></i>`).join('')}</div><div class="dk-mute">${ok} / ${P.length} ${T('pipelines OK','pipeline OK')}</div>`:'')+
        list+`</div>`;}).join('')+`</div>`;
  }
  function cmd(r,q){const l=(r.lanes||{})[q.device]||{};
    return [`# ${dn(q.device)} · ${q.slug} #${q.number} · ${q.kind}: ${q.label||q.detail||''}`,
      l.artifact?`# report.json + failed-job logs of this lane\ngh run download ${r.run_id} -R ${REPO} -n ${l.artifact}`:'',
      q.url?`# Buildkite job\n# ${q.url}`:'',
      l.job_id?`# re-run only this lane (new Buildkite builds: hours of GPU time)\ngh run rerun ${r.run_id} --job ${l.job_id} -R ${REPO}`:''].filter(Boolean).join('\n');}
  function problems(r){
    if(!r)return '';
    const Q=probs(r);
    if(!Q.length){
      if(hasRep(r)&&(r.verdict==='passed'||r.verdict==='failed'))return `<div class="wk-ok-line" data-wk="allok"><span class="dk-chip green">OK</span>${T('All required suites passed, 0 unexpected skips.','Mọi suite bắt buộc đều đạt, 0 lần bỏ qua ngoài dự kiến.')}</div>`;
      return `<p class="dk-mute" data-wk="noreport">${r.verdict==='running'?T('Still running: problems appear when a lane finishes.','Đang chạy: vấn đề sẽ hiện khi một lane chạy xong.'):T('No report for this run, so no problem list (the lanes did not finish).','Run này không có report nên không có danh sách vấn đề (các lane chưa chạy xong).')}</p>`;}
    const g={};Q.forEach(q=>{const k=q.device+'|'+q.slug;(g[k]=g[k]||[]).push(q);});
    return Object.values(g).map(qs=>{const q0=qs[0];
      return `<div class="dk-grp"><b>${dn(q0.device)}</b> · ${a(q0.purl,raw(q0.slug)+' #'+esc(q0.number)+' ↗')} · ${qs.length} ${T('problems','vấn đề')}</div>`+
      `<div class="dk-scroll"><table class="dk-t wk-prob" data-wk="problems"><tbody>`+qs.map(q=>{const skipId=/^weekly-skip-/.test(q.label||'');
        const main=skipId?(q.detail||q.label):(q.label||q.detail||'');const det=skipId?q.label:(q.label&&q.detail?q.detail:'');
        return `<tr><td style="width:1%">${kindChip(q.kind)}</td><td><span class="lab obsraw">${esc(main)}</span>${det?`<span class="det obsraw">${esc(det.length>220?det.slice(0,220)+'…':det)}</span>`:''}</td>`+
          `<td class="dk-mute" style="white-space:nowrap">${q.exit_status!=null?'exit '+esc(q.exit_status):''}</td>`+
          `<td style="white-space:nowrap"><button type="button" class="dk-copy" data-cmd="${esc(cmd(r,q))}" title="${esc(cmd(r,q))}">${T('copy debug cmd','chép lệnh debug')}</button></td>`+
          `<td style="white-space:nowrap">${a(q.url||q.purl,q.url?T('job ↗','job ↗'):T('build ↗','build ↗'))}</td></tr>`;}).join('')+`</tbody></table></div>`;}).join('');
  }
  function weekStart(t){const d=new Date(t);d.setUTCHours(0,0,0,0);d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));return d;}
  function trend(){
    const weeks=W.weeks||12,w0=weekStart(Date.now()),slots=[];
    for(let i=weeks-1;i>=0;i--){const s=new Date(w0.getTime()-i*7*864e5);slots.push({s,runs:[]});}
    [...RUNS].reverse().forEach(r=>{const ws=weekStart(Date.parse(r.created_at)).getTime();const sl=slots.find(x=>x.s.getTime()===ws);if(sl)sl.runs.push(r);});
    const lab=r=>{const s=st(r.verdict),P=pipes(r);return `${day(r.created_at)} · run #${r.number} · ${T(s[1],s[2])} · ${P.length?`${P.filter(pOK).length}/${P.length} ${T('pipelines OK','pipeline OK')}`:T('no report','không có report')}`;};
    const strip=`<div class="wk-trend dk-strip" role="group" aria-label="${esc(T('Weekly full build runs, oldest to newest. Arrow keys move, Enter shows the run.','Các run weekly full build, cũ → mới. Phím mũi tên để di chuyển, Enter để xem run.'))}" data-wk="strip">`+
      slots.map(sl=>`<div class="wk-wk" title="${esc(T('Week of ','Tuần bắt đầu ')+sl.s.toISOString().slice(0,10))}"><div class="cells">`+
        (sl.runs.length?sl.runs.map(r=>`<button type="button" class="wk-cell" data-wk-run="${r.run_id}" aria-pressed="${String(r.run_id)===String(SEL)}" aria-label="${esc(lab(r))}" title="${esc(lab(r))}"><i class="${st(r.verdict)[3]}" aria-hidden="true"></i></button>`).join(''):`<i class="wk-none" aria-hidden="true"></i>`)+
        `</div><span class="wl" aria-hidden="true">${sl.s.toISOString().slice(5,10)}</span></div>`).join('')+`</div>`;
    const legend=`<div class="wk-legend"><span><i class="p"></i>${T('passed','đạt')}</span><span><i class="f"></i>${T('failed','lỗi')}</span><span><i class="t"></i>${T('timed out','quá giờ')}</span><span><i class="r"></i>${T('running','đang chạy')}</span><span><i class="c"></i>${T('cancelled','đã hủy')}</span><span><i class="n"></i>${T('no run that week','tuần đó không có run')}</span></div>`;
    const done=RUNS.filter(r=>['passed','failed','timed_out'].includes(r.verdict)),pass=done.filter(r=>r.verdict==='passed').length;
    const rows=RUNS.map(r=>{const s=st(r.verdict),P=pipes(r),Q=probs(r),on=String(r.run_id)===String(SEL);
      return `<tr class="${on?'sel':''}" data-wk-row="${r.run_id}"${on?' aria-current="true"':''}><td><button type="button" class="wk-pick" data-wk-run="${r.run_id}" aria-label="${esc(T('Show run','Xem run')+' #'+r.number)}">#${esc(r.number)}</button></td>`+
        `<td>${when(r.created_at)}</td><td>${trig(r.event)}</td><td>${raw(sha(r.head_sha))}</td>`+
        `<td><span class="dk-chip ${CH[r.verdict]||'gray'}">${esc(T(s[1],s[2]))}</span></td>`+
        `<td>${ran(r).map(([d,l])=>`<span class="dk-chip ${(LANE[l.state]||['gray'])[0]}" title="${esc(T(...(LANE[l.state]||[0,l.state,l.state]).slice(1)))}">${dn(d)}</span>`).join('')||'–'}</td>`+
        `<td>${P.length?`${P.filter(pOK).length} / ${P.length}`:'–'}</td><td>${hasRep(r)?Q.length:'–'}</td><td>${dur(wall(r))}</td></tr>`;}).join('');
    return `<p class="wk-line" style="margin:0 0 8px">${T(`Last ${weeks} weeks, oldest → newest; one bar per run.`,`${weeks} tuần qua, cũ → mới; mỗi vạch là một run.`)} ${done.length?`${T('Green','Xanh')}: <b>${pass} / ${done.length}</b> ${T('finished runs','run đã xong')}.`:''} ${T('Click a bar or a row to see that run above.','Bấm một vạch hoặc một dòng để xem run đó ở trên.')}</p>`+strip+legend+
      (RUNS.length?`<div class="dk-scroll"><table class="dk-t wk-hist" data-wk="history"><thead><tr><th>Run</th><th>${T('Started','Bắt đầu')}</th><th>${T('Trigger','Kích hoạt')}</th><th>Commit</th><th>${T('Status','Trạng thái')}</th><th>${T('Lanes','Lane')}</th><th>${T('Pipelines OK','Pipeline OK')}</th><th>${T('Problems','Vấn đề')}</th><th>${T('Wall time','Tổng thời gian')}</th></tr></thead><tbody>${rows}</tbody></table></div>`:'');
  }
  function render(){
    const r=byId(SEL);
    set('wkHero',T('Weekly full build','Weekly full build'),hero(r));
    set('wkDev',T('Device lanes','Lane theo thiết bị')+(r?` · run #${r.number}`:''),devices(r));
    set('wkProb',T('Problems','Vấn đề')+(r?` · run #${r.number}`:''),problems(r));
    set('wkTrend',T('Trend and history','Xu hướng và lịch sử'),trend());
  }
  function pick(id,from){if(!byId(id))return;SEL=id;render();
    const h=document.getElementById('wkHero');if(h&&h.getBoundingClientRect().top<0)h.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
    if(from){const box=document.getElementById(from);const b=box&&box.querySelector(`[data-wk-run="${id}"]`);if(b)b.focus({preventScroll:true});}}
  document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('[data-wk-run],tr[data-wk-row]');if(!b||!b.closest('section[data-tab="weekly"]'))return;
    if(b.tagName==='TR'&&e.target.closest('a,button'))return;
    const id=b.dataset.wkRun||b.dataset.wkRow;const sec=b.closest('section[data-tab="weekly"]');pick(id,sec&&sec.id==='wkTrend'?'wkTrendB':null);});
  document.addEventListener('keydown',e=>{const c=e.target.closest&&e.target.closest('.wk-cell');if(!c||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
    const L=[...document.querySelectorAll('#wkTrend .wk-cell')],i=L.indexOf(c);let j=e.key==='Home'?0:e.key==='End'?L.length-1:i+(e.key==='ArrowRight'?1:-1);
    j=Math.max(0,Math.min(L.length-1,j));e.preventDefault();e.stopPropagation();L[j].focus();},true);
  window.WEEKLY={pick,get sel(){return SEL;},runs:RUNS};
  const start=()=>{render();addEventListener('langchange',render);};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
</script>
<!-- WEEKLY:JS:END -->
"""


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor) if before else page.index(anchor) + len(anchor)
    return page[:i] + ("" if before else "\n") + block.strip() + ("\n" if before else "") + page[i:]


def main():
    try:
        data = json.load(open(DESK, encoding="utf-8")).get("weekly") or {}
    except (OSError, ValueError):
        print("weekly: no release_desk.json (run ops-app/backend/export_page_data.py); tab stays empty")
        data = {}
    page = open(PAGE, encoding="utf-8").read()
    page = put(page, "/* WEEKLY:CSS:START */", "/* WEEKLY:CSS:END */", CSS, "/* NAV:CSS:START */")
    page = put(page, "<!-- WEEKLY:HTML:START -->", "<!-- WEEKLY:HTML:END -->", HTML, "<!-- DESK:HTML:END -->", before=False)
    js = JS.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).replace("</", "<\\/"))
    page = put(page, "<!-- WEEKLY:JS:START -->", "<!-- WEEKLY:JS:END -->", js, "</body>")
    open(PAGE, "w", encoding="utf-8").write(page)
    runs = data.get("runs") or []
    r = next((x for x in runs if x.get("verdict") != "cancelled"), runs[0] if runs else None)
    print(f"weekly: {len(runs)} runs · shown first: " + (f"#{r['number']} {r['verdict']} ({', '.join(f'{d}:{l['state']}' for d, l in r['lanes'].items())})" if r else "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
