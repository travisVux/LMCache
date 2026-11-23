"""Add 3 trace-direction tabs to the #obs view of 06_PR_TO_CI_VISUAL.html (idempotent).

  9  #obs/flaky    Flaky job trace        (#optimal-CI, #debug)
  10 #obs/gpuload  GPU load trace         (#optimal-CI, #increase-PRs-merged)
  11 #obs/bug      Bug / error trace      (one GitHub issue / PR, default #6530)

Data: trace_dirs_model.build() is embedded (offline / gh-pages fallback). The open page polls
outputs/trace_agent/directions.js every 30 s (written by trace_agent_dirs.py), so new agent results
show without a rebuild. The bug tab also asks api.github.com live (CORS *, token optional: the
one saved by the #obs Refresh settings). Run after build_observe.py, before build_i18n.py.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trace_dirs_model as M  # noqa: E402

from pathlib import Path as _Path  # noqa: E402
PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")

HTML = r"""
<!-- TRD:HTML:START -->
<section class="card" data-view="obs" data-tab="flaky">
  <div class="head"><h2>10 · Flaky jobs</h2>
  <p class="sub">Fail first, pass on retry. Costs GPU-h and merge time.</p></div>
  <div id="tdFlaky"></div>
</section>
<section class="card" data-view="obs" data-tab="gpuload">
  <div class="head"><h2>11 · GPU load and waste</h2>
  <p class="sub">Where MP GPU-hours go, and what saves the most.</p></div>
  <div id="tdGpu"></div>
</section>
<section class="card" data-view="obs" data-tab="bug">
  <div class="head"><h2>12 · Bug trace</h2>
  <p class="sub">One bug, from first error to fix.</p></div>
  <div id="tdBug"></div>
</section>
<!-- TRD:HTML:END -->
"""

CSS = r"""
/* TRD:CSS:START */
.td-kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px;margin:4px 0 14px}
.td-kpi{border:1px solid var(--border);border-radius:10px;padding:9px 12px;background:var(--surface-1);display:flex;flex-direction:column;gap:3px;min-width:0}
.td-kpi .v{font-size:21px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.15}
.td-kpi .v small{font-size:12px;font-weight:500;color:var(--text-muted);margin-left:4px}
.td-kpi .n{font-size:12px;font-weight:650;color:var(--text-primary)}
.td-kpi .d{font-size:11.5px;color:var(--text-secondary);line-height:1.35}
.td-kpi .s{font-size:10.5px;color:var(--text-muted)}
.td-kpi .dir{font-size:10px;font-weight:650;color:var(--muted-text,var(--text-muted));border:1px solid var(--border);border-radius:999px;padding:0 6px;align-self:flex-start}
.td-h3{margin:16px 0 8px;font-size:12px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.04em}
.td-cols{display:flex;align-items:flex-end;gap:10px;height:120px;padding:6px 4px 0;border-bottom:1px solid var(--border);max-width:520px}
.td-col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:3px;cursor:default;min-width:0}
.td-col .b{width:100%;max-width:46px;display:flex;flex-direction:column-reverse;gap:2px}
.td-col .b i{display:block;border-radius:4px 4px 0 0;background:var(--series-1)}
.td-col .b i.w{background:var(--warning)}
.td-col.part .b i{opacity:.45}
.td-col .lv{font-size:10.5px;color:var(--text-secondary);font-variant-numeric:tabular-nums}
.td-col:hover .b i{filter:brightness(1.12)}
.td-xl{display:flex;gap:10px;max-width:520px;padding:3px 4px 0}
.td-xl span{flex:1;text-align:center;font-size:10.5px;color:var(--text-muted)}
.td-leg{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--text-secondary);margin-top:6px}
.td-leg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;vertical-align:-1px}
.td-hbar{display:inline-block;height:8px;border-radius:0 4px 4px 0;background:var(--series-1);vertical-align:middle;margin-right:6px;min-width:2px}
.td-stack{display:flex;gap:2px;height:16px;border-radius:5px;overflow:hidden;margin:6px 0}
.td-stack i{display:block;height:100%}
.td-chip{display:inline-block;font-size:10.5px;font-weight:650;padding:1px 7px;border-radius:999px;border:1px solid var(--border);color:var(--text-secondary);white-space:nowrap}
.td-chip.m{border-color:color-mix(in oklab,var(--good) 55%,var(--border));color:var(--good-text,var(--good))}
.td-chip.e{border-color:color-mix(in oklab,var(--warning) 60%,var(--border))}
.td-chip.x{border-style:dashed;color:var(--text-muted)}
.td-cmd{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px;font-size:11.5px;color:var(--text-secondary)}
.td-cmd code{font:11px ui-monospace,Consolas,monospace;background:var(--surface-2);padding:3px 7px;border-radius:6px;word-break:break-all}
.td-cmd button,.td-tgt button{all:unset;cursor:pointer;font-size:11.5px;font-weight:600;color:var(--series-1);padding:3px 9px;border:1px solid var(--border);border-radius:7px;background:var(--surface-1)}
.td-cmd button:hover,.td-tgt button:hover{border-color:var(--series-1)}
.td-tgt{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px;font-size:12.5px}
.td-tgt input{width:90px;font:inherit;padding:4px 8px;border:1px solid var(--border);border-radius:7px;background:var(--surface-1);color:var(--text-primary)}
.td-steps{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;margin:8px 0 12px}
.td-step{border:1px solid var(--border);border-radius:9px;padding:7px 10px;font-size:11.5px;background:var(--surface-1)}
.td-step b{display:block;font-size:12px;margin-bottom:2px}
.td-step.done{border-color:color-mix(in oklab,var(--good) 55%,var(--border))}
.td-step.now{border-color:var(--series-1);box-shadow:0 0 0 1px var(--series-1)}
.td-step .st{font-size:10.5px;color:var(--text-muted)}
.td-wait{border:1px dashed color-mix(in oklab,var(--warning) 60%,var(--border));border-radius:10px;padding:12px 14px;background:var(--surface-1);font-size:12.5px;display:flex;flex-direction:column;gap:6px}
.td-wait b{font-size:14px}
.td-body{white-space:pre-wrap;word-break:break-word;max-height:220px;overflow:auto;font:11px/1.45 ui-monospace,Consolas,monospace;background:var(--surface-2);padding:8px;border-radius:6px;margin:6px 0 0}
.td-2col{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
@media (max-width:820px){.td-2col{grid-template-columns:1fr}}
/* TRD:CSS:END */
"""

JS = r"""
<!-- TRD:JS:START -->
<script id="trdData" type="application/json">__DATA__</script>
<script>
(function(){
  let D=null;try{D=JSON.parse(document.getElementById('trdData').textContent);}catch(e){}
  if(!D)return;
  let LIVE=null,FAIL=0;const SRC='outputs/trace_agent/directions.js';
  const el=(t,a={},...kids)=>{const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(v==null)continue;if(k==='class')e.className=v;else if(k==='style')e.style.cssText=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else e.setAttribute(k,v);}
    kids.flat(Infinity).forEach(c=>{if(c==null||c===false)return;e.append(c.nodeType?c:document.createTextNode(String(c)));});return e;};
  const V=()=>(window.I18N&&I18N.lang==='vi')?1:0, T=(en,vi)=>V()?vi:en, P=p=>Array.isArray(p)?(V()?p[1]||p[0]:p[0]):(p||'');
  const fmt=(n,d=0)=>n==null||!isFinite(n)?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
  const pc=(a,b,d=0)=>b?fmt(100*a/b,d)+'%':'—';
  const store=(k,d)=>{try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v);}catch(e){return d;}};
  const save=(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}};
  const cur=()=>LIVE&&LIVE.updated_at>D.updated_at?LIVE:D;
  const link=(href,txt)=>el('a',{class:'obs-link',href,target:'_blank',rel:'noopener'},txt);
  const agoD=t=>{const h=(Date.now()-Date.parse(t))/36e5;return !isFinite(h)?'—':h<1?T('<1 h','<1 giờ'):h<48?Math.round(h)+T(' h',' giờ'):Math.round(h/24)+T(' d',' ngày');};
  const fresh=d=>{const n=Math.round((Date.now()-Date.parse(d.window.end))/864e5),old=n>=3;
    return el('div',{class:'obs-note',style:'margin:0 0 6px;font-weight:600'+(old?';color:var(--warning)':'')},(old?'⚠ ':'')+T(`Data ends ${d.window.end} (${n} d ago).`,`Dữ liệu tới ${d.window.end} (${n} ngày trước).`));};
  const win=d=>T(`${d.window.pipeline} · ${d.window.start} → ${d.window.end} · ${fmt(d.window.builds)} builds`,`${d.window.pipeline} · ${d.window.start} → ${d.window.end} · ${fmt(d.window.builds)} build`);

  // delta vs the previous FULL week; get(w) -> number|null; lo = lower is better; pp = difference in percentage points
  function wk(d,get,lo,pp){const fw=d.weeks.filter(x=>!x.partial).map(x=>x.w),a=fw[fw.length-1],b=fw[fw.length-2];if(!a||!b)return null;
    const x=get(a),y=get(b);if(x==null||y==null||(!pp&&!y))return null;const p=pp?x-y:(x-y)/y*100,good=Math.abs(p)<0.05?null:(lo?p<0:p>0);
    return {txt:`${p>0?'▲ +':p<0?'▼ ':''}${fmt(p,pp?1:0)}${pp?' pp':'%'} ${a} vs ${b}`,good};}
  function dl(x){return el('div',{class:'dl',style:'font-size:11px;margin-top:3px;font-weight:600;color:'+(!x?'var(--text-muted)':x.good==null?'var(--text-secondary)':x.good?'var(--good-text,var(--good))':'var(--crit-text,var(--critical))')},
    !x?T('Δ: no previous period (30-day window)','Δ: không có kỳ trước (cửa sổ 30 ngày)'):x.txt+(x.good==null?'':x.good?T(' · better',' · tốt hơn'):T(' · worse',' · xấu hơn')));}
  function kpi(name,val,unit,def,src,dir,delta){return el('div',{class:'td-kpi'},el('div',{class:'n'},name),el('div',{class:'v'},val,unit?el('small',{},unit):null),
    el('div',{class:'d'},def),dir?el('span',{class:'dir'},dir==='lo'?T('lower is better','càng thấp càng tốt'):T('higher is better','càng cao càng tốt')):null,el('div',{class:'s'},src),dl(delta));}
  // weekly columns: series = [{w,partial,vals:[a,b?]}]; single series unless 2 values
  function cols(series,names,unit){const max=Math.max(1,...series.map(s=>s.vals.reduce((a,b)=>a+b,0)));
    const box=el('div',{class:'td-cols',role:'img','aria-label':names.join(' / ')});
    series.forEach(s=>{const tot=s.vals.reduce((a,b)=>a+b,0);const b=el('div',{class:'b'});
      s.vals.forEach((v,i)=>{if(v>0)b.append(el('i',{class:i?'w':'',style:`height:${Math.max(2,100*v/max)}px`}));});
      box.append(el('div',{class:'td-col'+(s.partial?' part':''),title:`${s.w}${s.partial?T(' (partial week)',' (tuần chưa đủ)'):''}: `+s.vals.map((v,i)=>`${names[i]} ${fmt(v,1)}${unit}`).join(' · ')},el('span',{class:'lv'},fmt(tot,tot<100&&tot%1?1:0)),b));});
    const xl=el('div',{class:'td-xl'},series.map(s=>el('span',{},s.w+(s.partial?'*':''))));
    const leg=names.length>1?el('div',{class:'td-leg'},names.map((n,i)=>el('span',{},el('i',{style:`background:var(${i?'--warning':'--series-1'})`}),n))):null;
    return el('div',{},box,xl,leg,el('div',{class:'obs-note',style:'margin-top:4px'},T('* partial week (window edge): do not compare it with full weeks.','* tuần chưa đủ (đầu/cuối cửa sổ): không so với tuần đủ.')));}
  function agentCard(key,a,cmd){
    const box=el('div',{class:'tr-agent '+(!a?'pending':a.status==='ok'?'ok':'err'),style:'margin-top:14px'});
    box.append(el('div',{class:'tr-agent-hd'},'🤖 ',el('b',{},T('Trace Agent — this direction','Trace Agent — hướng này')),
      a?el('span',{class:'m'},`${(a.run_at||'').slice(0,16).replace('T',' ')} · ${a.model||''} · $${a.cost_usd!=null?fmt(a.cost_usd,2):'—'} · ${a.secs||'—'} s`):el('span',{class:'m'},T('no run yet','chưa chạy')),
      LIVE?el('span',{style:'color:var(--good)',title:SRC},' ● live'):null));
    if(!a)box.append(el('div',{},T('No agent result yet. Run the command below; the result appears here within 30 s while this page is open.','Chưa có kết quả agent. Chạy lệnh dưới; kết quả hiện ở đây trong 30 giây khi trang đang mở.')));
    else if(a.status!=='ok')box.append(el('div',{},T('Last run failed: ','Lần chạy trước lỗi: '),el('span',{class:'obsraw'},(a.error||'').slice(-240))));
    else if(key==='bug'){
      box.append(el('div',{},el('b',{},T('Root cause: ','Nguyên nhân: ')),P(a.root_cause)),el('div',{class:'fx'},el('b',{},T('Fix: ','Hướng fix: ')),P(a.fix)),
        el('div',{class:'obs-note'},`class ${a.cls||'—'} · impact ${a.impact||'—'} · confidence ${a.confidence||'—'}`,a.fix_pr?[' · ',link(`https://github.com/${cur().bug.target.repo}/pull/${a.fix_pr}`,'fix PR #'+a.fix_pr)]:null),
        a.where?el('div',{class:'obsraw'},a.where):null,a.first_error?el('pre',{class:'td-body obsraw'},a.first_error):null);
    }else{
      if(a.summary){const sm=P(a.summary),first=sm.split(/(?<=[.!?]) /)[0];box.append(el('div',{},first));
        if(first.length<sm.length)box.append(el('details',{class:'td-ops'},el('summary',{},T('More','Thêm')),el('div',{},sm.slice(first.length).trim())));}
      const t=el('table',{class:'obs-t'});
      if(key==='flaky'){t.append(el('thead',{},el('tr',{},el('th',{},'Workload'),el('th',{},T('Class','Loại')),el('th',{},T('Root cause','Nguyên nhân')),el('th',{},T('Fix','Hướng fix')),el('th',{},T('Confidence','Độ tin cậy')))));
        t.append(el('tbody',{},(a.items||[]).map(x=>el('tr',{},el('td',{class:'nw'},el('b',{},x.workload||'')),el('td',{},x.class||''),el('td',{},P(x.root_cause)),el('td',{class:'fx'},P(x.fix)),el('td',{},x.confidence||'')))));}
      else{t.append(el('thead',{},el('tr',{},el('th',{},T('Change','Thay đổi')),el('th',{class:'r'},'GPU-h / 30 d'),el('th',{},T('Merge effect','Ảnh hưởng merge')),el('th',{},T('Where','Ở đâu')),el('th',{},T('Risk','Rủi ro')))));
        t.append(el('tbody',{},(a.items||[]).map(x=>el('tr',{},el('td',{},el('b',{},x.lever||''),el('div',{class:'meta'},P(x.change))),el('td',{class:'r'},fmt(x.gpu_h_30d,1),el('div',{class:'meta'},x.basis||'')),el('td',{},P(x.merge_effect)),el('td',{class:'obsraw'},x.where||''),el('td',{},P(x.risk))))));}
      box.append(el('div',{class:'obs-scroll'},t));
    }
    if(a&&(a.unverified||[]).length)box.append(el('details',{},el('summary',{},T(`Not verified (${a.unverified.length})`,`Chưa xác minh (${a.unverified.length})`)),el('ul',{},a.unverified.map(x=>el('li',{},x)))));
    if(a&&a.report_text)box.append(el('details',{},el('summary',{},T('Full trace report','Báo cáo truy vết đầy đủ'),el('span',{class:'obsraw',style:'font-weight:400'},a.report?` · ${a.report}`:'')),el('pre',{class:'obsraw'},a.report_text)));
    const b=el('button',{type:'button',onclick:()=>{try{navigator.clipboard.writeText(cmd);b.textContent=T('Copied','Đã chép');setTimeout(()=>b.textContent=T('Copy','Chép'),1400);}catch(e){}}},T('Copy','Chép'));
    box.append(el('details',{class:'td-ops'},el('summary',{},T('For operators: run the agent','Cho người vận hành: chạy agent')),el('div',{class:'td-cmd'},T('Run:','Chạy:'),el('code',{},cmd),b)));
    return box;}
  const CMD='python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/trace_agent_dirs.py --dir ';

  // ---------------- 9 · flaky ----------------
  function rFlaky(){const w=document.getElementById('tdFlaky');if(!w)return;const d=cur(),f=d.flaky,t=f.totals;w.replaceChildren();
    w.append(fresh(d));w.append(el('div',{class:'obs-note'},T('Source: ','Nguồn: '),win(d),T(' (cached Buildkite jobs, outputs/P1). A job is flaky when its first attempt failed and an automatic or manual retry of the same job passed.',' (cache job Buildkite, outputs/P1). Job là flaky khi lần chạy đầu lỗi và lần retry (tự động hoặc tay) của cùng job thì qua.')));
    w.append(el('div',{class:'td-kpis'},
      kpi(T('Flaky job failures','Lỗi job flaky'),fmt(t.flaky),T('in 30 d','trong 30 ngày'),T('First-try failures that passed on retry of the same commit.','Lỗi lần đầu nhưng qua khi retry cùng commit.'),'k3-multiprocess-test · retry chain','lo',wk(d,w=>d.flaky.weeks[w]==null?null:d.flaky.weeks[w],true,false)),
      kpi(T('Share of first-try failures','Tỷ lệ trong lỗi lần đầu'),pc(t.flaky,t.first_fail),'',T(`${fmt(t.flaky)} of ${fmt(t.first_fail)} first-try failures were not real: the same code passed later.`,`${fmt(t.flaky)} trong ${fmt(t.first_fail)} lỗi lần đầu là giả: cùng code chạy lại thì qua.`),T(`${fmt(t.still_fail)} still failed after retry`,`${fmt(t.still_fail)} vẫn lỗi sau retry`),'lo'),
      kpi(T('GPU-hours on retries','GPU-giờ cho retry'),fmt(t.retry_gpu_h,1),'GPU-h',T('GPU time of all retry attempts (after the first).','Thời gian GPU của mọi lần retry (sau lần đầu).'),T(`${pc(t.retry_gpu_h,d.gpuload.total_gpu_h,1)} of all MP GPU-h`,`${pc(t.retry_gpu_h,d.gpuload.total_gpu_h,1)} tổng GPU-h MP`),'lo'),
      kpi(T('Test vs infra','Test hay hạ tầng'),`${fmt(t.test_kind)} / ${fmt(t.infra_kind)}`,'',T('Exit code of the failed attempt: 1/2 = the test failed; 128/255/-1/100 = agent, git or network.','Exit code của lần lỗi: 1/2 = test lỗi; 128/255/-1/100 = agent, git hoặc mạng.'),T('flaky failures only','chỉ lỗi flaky')),
      kpi(T('GHA Test: passed only on re-run','GHA Test: chỉ qua khi chạy lại'),fmt(f.gha.rerun_success),T(`of ${fmt(f.gha.runs)} runs`,`trên ${fmt(f.gha.runs)} run`),T('Runs whose final attempt (2 or 3) passed. Earlier attempts are hidden by GitHub, so this is a lower bound.','Run mà lần cuối (2 hoặc 3) qua. GitHub ẩn lần trước nên đây là mức tối thiểu.'),`${f.gha.start} → ${f.gha.end}`,'lo'),
      kpi(T('Same-commit build flips','Build đổi kết quả cùng commit'),fmt(t.flips),'',T('Commits with one failed and one passed MP build.','Commit có một build MP lỗi và một build qua.'),T('build level','mức build'),'lo')));
    const order=d.weeks.map(x=>x.w);
    w.append(el('div',{class:'td-h3'},T('Flaky job failures per week','Lỗi job flaky theo tuần')));
    w.append(cols(order.map(k=>({w:k,partial:(d.weeks.find(x=>x.w===k)||{}).partial,vals:[f.weeks[k]||0]})),[T('flaky failures','lỗi flaky')],''));
    w.append(el('div',{class:'td-h3'},T('Ranking: where flaky failures come from','Xếp hạng: lỗi flaky đến từ đâu')));
    const mx=Math.max(1,...f.workloads.map(x=>x.flaky));const tb=el('tbody');
    f.workloads.forEach(x=>tb.append(el('tr',{},el('td',{class:'nw'},el('b',{},x.workload)),el('td',{class:'r'},x.gpus||'—'),el('td',{class:'r'},fmt(x.runs)),
      el('td',{class:'nw'},el('span',{class:'td-hbar',style:`width:${Math.round(90*x.flaky/mx)}px`}),fmt(x.flaky)),el('td',{class:'r'},x.flaky_rate!=null?fmt(100*x.flaky_rate,1)+'%':'—'),
      el('td',{class:'r'},fmt(x.still_fail)),el('td',{class:'r'},fmt(x.retry_gpu_h,1)),el('td',{class:'obsraw nw'},Object.entries(x.exits).map(([k,v])=>`${k}×${v}`).join(' ')),
      el('td',{},x.examples.map((e,i)=>[i?' · ':'',link(e.url,'#'+e.build)])))));
    w.append(el('div',{class:'obs-scroll'},el('table',{class:'obs-t'},el('thead',{},el('tr',{},el('th',{},'Workload'),el('th',{class:'r'},'GPUs'),el('th',{class:'r'},T('Runs','Lần chạy')),el('th',{},T('Flaky','Flaky')),el('th',{class:'r'},T('Flaky rate','Tỷ lệ flaky')),el('th',{class:'r'},T('Still failed','Vẫn lỗi')),el('th',{class:'r'},T('Retry GPU-h','GPU-h retry')),el('th',{},T('Exit codes','Exit code')),el('th',{},T('Example builds','Build ví dụ')))),tb)));
    if(f.flips.length){w.append(el('div',{class:'td-h3'},T('Same commit, different result','Cùng commit, kết quả khác')));
      w.append(el('ul',{class:'obs-note',style:'margin:0;padding-left:18px'},f.flips.map(x=>el('li',{},el('span',{class:'obsraw'},x.sha),x.pr?` · PR #${x.pr} · `:' · ',x.builds.map((b,i)=>[i?', ':'',link(b.url,'#'+b.n),' ',b.state])))));}
    w.append(el('div',{class:'obs-note',style:'margin-top:10px'},T('Blind spots: GitHub re-runs keep the run id, so only the last attempt is visible; k3-unit builds in the cache have no commit, so their flips are not counted.','Điểm mù: GitHub chạy lại giữ nguyên run id nên chỉ thấy lần cuối; build k3-unit trong cache không có commit nên chưa đếm được.')));
    w.append(agentCard('flaky',(d.agents||{}).flaky,CMD+'flaky'));}

  // ---------------- 10 · GPU load ----------------
  function rGpu(){const w=document.getElementById('tdGpu');if(!w)return;const d=cur(),g=d.gpuload,s=g.by_state_h,m=g.merge,tot=g.total_gpu_h;w.replaceChildren();
    w.append(fresh(d));w.append(el('div',{class:'obs-note'},T('Source: ','Nguồn: '),win(d),T('. GPU-h = job wall time × GPUs of the job.','. GPU-h = thời gian chạy job × số GPU của job.')));
    w.append(el('div',{class:'td-kpis'},
      kpi(T('GPU-hours in 30 d','GPU-giờ trong 30 ngày'),fmt(tot),'GPU-h',T('All MP builds: PR, dev and nightly.','Mọi build MP: PR, dev và nightly.'),T(`PR builds only: ${fmt(g.mp_pr_gpu_h)} GPU-h`,`Chỉ build PR: ${fmt(g.mp_pr_gpu_h)} GPU-h`),'lo',wk(d,w=>(d.gpuload.weeks.find(x=>x.w===w)||{}).gpu_h,true,false)),
      kpi(T('Waste: no useful result','Lãng phí: không cho kết quả'),pc((s.canceled||0)+(s.failed||0),tot),'',T('GPU of canceled or failed builds, all MP builds. (Report: retry + cancel only.)','GPU của build hủy hoặc lỗi, mọi build MP. (Report: chỉ retry + hủy.)'),`${fmt(s.canceled)} ${T('canceled','hủy')} + ${fmt(s.failed)} ${T('failed','lỗi')} GPU-h`,'lo',wk(d,w=>{const x=d.gpuload.weeks.find(y=>y.w===w);return x&&x.gpu_h?100*x.waste_h/x.gpu_h:null;},true,true)),
      kpi(T('GPU per passed PR build','GPU mỗi build PR qua'),fmt(g.pr_build_p50_gpu_h,1),'GPU-h',T('Median of one green PR build. (Report: total ÷ merged PRs.)','Trung vị một build PR xanh. (Report: tổng ÷ PR merge.)'),'p50','lo'),
      kpi(T('Wait for a GPU agent','Chờ agent GPU'),`${fmt(m.queue_p50_min)} / ${fmt(m.queue_p90_min)}`,'min',T('Per GPU job, 30 d. (CI health: longest wait per build.)','Mỗi job GPU, 30 ngày. (CI health: chờ lâu nhất mỗi build.)'),'p50 / p90','lo'),
      kpi(T('Green PR build time','Thời gian build PR xanh'),`${fmt(m.passed_dur_p50_min)} / ${fmt(m.passed_dur_p90_min)}`,'min',T('Created → finished for passed PR builds, p50 / p90. The p90 is what blocks merges.','Từ tạo đến xong của build PR qua, p50 / p90. p90 là thứ chặn merge.'),T(`timed over passed builds only; ${fmt(m.pr_builds)} PR builds · ${fmt(m.distinct_prs)} PRs in total`,`chỉ tính build qua; tổng ${fmt(m.pr_builds)} build PR · ${fmt(m.distinct_prs)} PR`),'lo')));
    w.append(el('div',{class:'td-h3'},T('GPU-hours by build result','GPU-giờ theo kết quả build')));
    const parts=[['passed','--good',T('passed','qua')],['failed','--critical',T('failed','lỗi')],['canceled','--text-muted',T('canceled','hủy')],['running','--series-1',T('running','đang chạy')]].filter(p=>s[p[0]]>0);
    w.append(el('div',{class:'td-stack',role:'img','aria-label':parts.map(p=>`${p[2]} ${fmt(s[p[0]])} GPU-h`).join(', ')},parts.map(p=>el('i',{style:`flex:${s[p[0]]};background:var(${p[1]})`,title:`${p[2]}: ${fmt(s[p[0]])} GPU-h (${pc(s[p[0]],tot,1)})`}))));
    w.append(el('div',{class:'td-leg'},parts.map(p=>el('span',{},el('i',{style:`background:var(${p[1]})`}),`${p[2]} ${fmt(s[p[0]])} GPU-h · ${pc(s[p[0]],tot,1)}`))));
    const cr=g.cancel_reasons||{};w.append(el('div',{class:'obs-note',style:'margin-top:4px'},T('Why builds were canceled: ','Lý do build bị hủy: '),el('span',{class:'obsraw'},Object.entries(cr).map(([k,v])=>`${k} ${v}`).join(' · '))));
    w.append(el('div',{class:'td-h3'},T('GPU-hours per week (used vs. wasted)','GPU-giờ theo tuần (có ích và lãng phí)')));
    w.append(cols(g.weeks.map(x=>({w:x.w,partial:(d.weeks.find(y=>y.w===x.w)||{}).partial,vals:[Math.max(0,x.gpu_h-x.waste_h),x.waste_h]})),[T('useful','có ích'),T('canceled + failed','hủy + lỗi')],' GPU-h'));
    w.append(el('div',{class:'td-h3'},T('Levers: what to change, ranked by GPU-hours','Đòn bẩy: nên đổi gì, xếp theo GPU-giờ')));
    const lb=el('tbody');
    [...g.levers].sort((a,b)=>(b.gpu_h??-1)-(a.gpu_h??-1)).forEach(l=>lb.append(el('tr',{},el('td',{},el('b',{},V()?l.vi:l.en),el('div',{class:'meta'},V()?l.note_vi:l.note_en)),
      el('td',{class:'r'},l.gpu_h!=null?fmt(l.gpu_h,1):'?',el('div',{class:'meta'},l.gpu_h!=null?pc(l.gpu_h,tot,1):'')),
      el('td',{},el('span',{class:'td-chip '+(l.basis==='measured'?'m':l.basis==='spent'?'e':'x'),title:l.basis==='estimated'?T('Replay of real builds: GPU-h the cancel WOULD have saved. Not a measured saving.','Phát lại build thật: GPU-h mà việc hủy SẼ tiết kiệm. Không phải số đã đo.'):null},l.basis==='measured'?T('measured saving','tiết kiệm đã đo'):l.basis==='estimated'?T('estimated saving (replay)','tiết kiệm ước tính (phát lại)'):l.basis==='spent'?T('already spent','đã tiêu'):T('not measured','chưa đo'))),
      el('td',{class:'nw'},l.ticket||'—',l.goto?[' · ',el('a',{class:'obs-link',href:l.goto},T('open','mở'))]:null))));
    w.append(el('div',{class:'obs-scroll'},el('table',{class:'obs-t'},el('thead',{},el('tr',{},el('th',{},T('Lever','Đòn bẩy')),el('th',{class:'r'},'GPU-h / 30 d'),el('th',{},T('Basis','Cơ sở')),el('th',{},T('Ticket','Ticket')))),lb)));
    w.append(el('div',{class:'obs-note'},T('Cost per workload: ','Chi phí theo workload: '),el('a',{class:'obs-link',href:'#gpu/cost'},T('GPU E2E → Cost →','GPU E2E → Chi phí →'))));
    w.append(agentCard('gpuload',(d.agents||{}).gpuload,CMD+'gpuload'));}

  // ---------------- 11 · bug ----------------
  let BUG_N=store('tdBugN',null),BUG_LIVE=null,BUG_BUSY=false,BUG_AT=0;
  const bugTarget=()=>{const t=cur().bug.target;return {repo:t.repo,number:BUG_N||t.number};};
  async function bugFetch(force){if(window.OBS_LOCAL_ONLY!==false)return;const t=bugTarget();if(BUG_BUSY||(!force&&BUG_LIVE&&BUG_LIVE.number===t.number&&Date.now()-BUG_AT<120000))return;BUG_BUSY=true;rBug();
    let tok='';try{tok=(JSON.parse(localStorage.getItem('obsTok')||sessionStorage.getItem('obsTok')||'{}').gh)||'';}catch(e){}
    const h={'Accept':'application/vnd.github+json'};if(tok)h.Authorization='Bearer '+tok;
    const r={number:t.number,at:Date.now(),exists:null,item:null,checks:null,newest:null,error:''};
    try{const a=await fetch(`https://api.github.com/repos/${t.repo}/issues/${t.number}`,{headers:h});
      if(a.status===404)r.exists=false;else if(a.ok){const j=await a.json();r.exists=true;r.item={number:j.number,title:j.title,state:j.state,url:j.html_url,is_pr:!!j.pull_request,user:(j.user||{}).login,labels:(j.labels||[]).map(x=>x.name),created_at:j.created_at,comments:j.comments,body:(j.body||'').slice(0,1500)};
        if(r.item.is_pr){const p=await fetch(`https://api.github.com/repos/${t.repo}/pulls/${t.number}`,{headers:h});if(p.ok){const pj=await p.json();r.item.merged=!!pj.merged_at;
          const c=await fetch(`https://api.github.com/repos/${t.repo}/commits/${pj.head.sha}/check-runs?per_page=100`,{headers:h});if(c.ok){const cj=await c.json();const runs=cj.check_runs||[];
            r.checks={total:runs.length,failed:runs.filter(x=>['failure','timed_out'].includes(x.conclusion)).map(x=>({name:x.name,url:x.html_url})),pending:runs.filter(x=>x.status!=='completed').length};}}}}
      else r.error='GitHub '+a.status+(a.status===403?T(' (rate limit: add a token in #obs settings)',' (hết lượt: thêm token trong cài đặt #obs)'):'');
      if(r.exists===false){const n=await fetch(`https://api.github.com/repos/${t.repo}/issues?state=all&per_page=1&sort=created&direction=desc`,{headers:h});if(n.ok){const nj=await n.json();r.newest=nj[0]&&nj[0].number;}}
    }catch(e){r.error=String(e.message||e);}
    BUG_LIVE=r;BUG_AT=Date.now();BUG_BUSY=false;rBug();}
  function rBug(){const w=document.getElementById('tdBug');if(!w)return;const d=cur(),t=bugTarget(),snap=d.bug||{};w.replaceChildren();
    const live=BUG_LIVE&&BUG_LIVE.number===t.number?BUG_LIVE:null;
    const st=live||(snap.target&&snap.target.number===t.number?{exists:snap.exists,item:snap.item,newest:snap.newest,at:Date.parse(snap.fetched_at),error:snap.error}:{exists:null});
    const inp=el('input',{type:'number',min:'1',value:String(t.number),'aria-label':T('Issue or PR number','Số issue hoặc PR')});
    const go=()=>{const n=parseInt(inp.value,10);if(n>0){BUG_N=n===d.bug.target.number?null:n;save('tdBugN',BUG_N);BUG_LIVE=null;bugFetch(true);}};
    inp.addEventListener('keydown',e=>{if(e.key==='Enter')go();});
    w.append(el('div',{class:'td-tgt'},el('b',{},T('Target','Mục tiêu')),el('span',{class:'obsraw'},t.repo+'#'),inp,el('button',{type:'button',onclick:go},T('Trace','Truy vết')),
      el('button',{type:'button',onclick:()=>bugFetch(true)},BUG_BUSY?T('Checking…','Đang kiểm tra…'):T('Check GitHub now','Kiểm tra GitHub ngay')),
      link(`https://github.com/${t.repo}/issues/${t.number}`,'GitHub ↗'),
      el('span',{class:'obs-note',style:'margin:0'},st.at?T('checked ','đã kiểm tra ')+new Date(st.at).toLocaleString(V()?'vi-VN':'en-GB'):'',live?' · live':T(' · build snapshot',' · ảnh chụp lúc build'))));
    if(st.error)w.append(el('div',{class:'obs-al s-warn'},el('span',{class:'x'},st.error)));
    const a=(d.agents||{}).bug,aok=a&&a.status==='ok'&&a.target===t.number;
    const it=st.item;
    const steps=[[T('0 · Read the report','0 · Đọc báo cáo'),T('title, body, version, links','tiêu đề, nội dung, phiên bản, liên kết'),!!it],
      [T('1 · First error','1 · Lỗi đầu tiên'),T('stack trace or first red CI log','stack trace hoặc log CI đỏ đầu tiên'),aok&&!!a.first_error],
      [T('2 · Find the code','2 · Tìm code'),'file:line + commit',aok&&!!a.where],
      [T('3 · Release impact','3 · Ảnh hưởng release'),T('in a tag >= v0.5.7?','có trong tag >= v0.5.7?'),aok&&!!a.impact],
      [T('4 · Reproduce','4 · Tái hiện'),T('one command','một lệnh'),aok&&!!a.repro],
      [T('5 · Fix','5 · Fix'),T('options, pick one','các phương án, chọn một'),aok&&!!(a.fix&&a.fix[0])],
      [T('6 · Compare fix PR','6 · So với PR fix'),T('after the own trace','sau khi tự truy vết'),aok&&a.fix_pr!=null]];
    const nowI=steps.findIndex(s=>!s[2]);
    w.append(el('div',{class:'td-steps'},steps.map((s,i)=>el('div',{class:'td-step'+(s[2]?' done':i===nowI&&st.exists?' now':'')},el('b',{},s[0]),s[1],el('div',{class:'st'},s[2]?'✓ '+T('done','xong'):i===nowI&&st.exists?T('next','tiếp theo'):T('waiting','đang chờ'))))));
    if(st.exists===false){const gap=st.newest?t.number-st.newest:null;
      w.append(el('div',{class:'td-wait'},el('b',{},T(`#${t.number} does not exist yet`,`#${t.number} chưa tồn tại`)),
        el('div',{},st.newest?T(`Newest issue / PR on ${t.repo} is #${st.newest}`,`Issue / PR mới nhất trên ${t.repo} là #${st.newest}`)+(gap>0?T(` — ${gap} numbers to go.`,` — còn ${gap} số nữa.`):'.'):''),
        el('div',{},T('This tab checks GitHub each time it opens. When the number appears, run the agent below (it skips, at no cost, while the number is missing).','Tab này kiểm tra GitHub mỗi lần mở. Khi số này xuất hiện, chạy agent bên dưới (agent bỏ qua, không tốn phí, khi số chưa có).'))));}
    else if(st.exists&&it){
      const ck=live&&live.checks;
      w.append(el('div',{class:'td-2col'},
        el('div',{},el('div',{class:'td-h3',style:'margin-top:0'},it.is_pr?'Pull request':'Issue'),
          el('div',{style:'font-weight:650;font-size:14px',class:'obsraw'},link(it.url,`#${it.number} ${it.title}`)),
          el('div',{class:'obs-note',style:'margin-top:4px'},`${it.state}${it.merged?' · merged':''} · ${it.user||''} · ${(it.created_at||'').slice(0,10)} · ${fmt(it.comments)} ${T('comments','bình luận')}`),
          el('div',{},(it.labels||[]).map(l=>el('span',{class:'gch'},l))),
          it.body?el('pre',{class:'td-body obsraw'},it.body):null),
        el('div',{},el('div',{class:'td-h3',style:'margin-top:0'},T('CI checks','CI check')),
          !it.is_pr?el('div',{class:'obs-empty'},T('An issue has no checks. The agent looks for the error in the text and in linked PRs.','Issue không có check. Agent tìm lỗi trong nội dung và PR liên kết.')):
          !ck?el('div',{class:'obs-empty'},T('Click "Check GitHub now" to load the checks.','Bấm "Kiểm tra GitHub ngay" để tải check.')):
          el('div',{},el('div',{class:'obs-note'},`${fmt(ck.total)} ${T('checks','check')} · ${fmt(ck.failed.length)} ${T('failed','lỗi')} · ${fmt(ck.pending)} ${T('pending','đang chạy')}`),
            ck.failed.length?el('ul',{style:'margin:0;padding-left:18px;font-size:12.5px'},ck.failed.map(x=>el('li',{},link(x.url,x.name)))):el('div',{class:'obs-empty'},T('No failed checks.','Không có check lỗi.'))))));}
    else if(st.exists==null)w.append(el('div',{class:'obs-empty'},T('Not checked yet.','Chưa kiểm tra.')));
    if(a&&a.target!=null&&a.target!==t.number)w.append(el('div',{class:'obs-note',style:'margin-top:10px'},T(`The last agent run traced #${a.target}, not #${t.number}.`,`Lần chạy agent trước truy vết #${a.target}, không phải #${t.number}.`)));
    w.append(agentCard('bug',aok?a:null,CMD+'bug'+(t.number!==d.bug.target.number?' --bug '+t.number:'')));}

  function render(){rFlaky();rGpu();rBug();}
  window.onTraceDirs=x=>{if(!x||!x.updated_at||(LIVE&&LIVE.updated_at===x.updated_at))return;const before=cur().updated_at;LIVE=x;if(x.updated_at>before)render();};
  function poll(){if(FAIL>=3)return;const s=document.createElement('script');s.src=SRC+'?t='+Date.now();s.onload=()=>{FAIL=0;s.remove();};s.onerror=()=>{FAIL++;s.remove();};document.head.append(s);}
  const visible=()=>['tdFlaky','tdGpu','tdBug'].some(id=>{const e=document.getElementById(id);return e&&e.offsetParent;});
  setTimeout(poll,1500);setInterval(()=>{if(!document.hidden&&visible())poll();},30000);
  addEventListener('viewchange',e=>{const x=e.detail||{};if(x.v==='obs'&&x.t==='bug')bugFetch(false);});
  addEventListener('langchange',render);
  render();
})();
</script>
<!-- TRD:JS:END -->
"""


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor) if before else page.index(anchor) + len(anchor)
    return page[:i] + block.strip() + "\n" + page[i:]


def main():
    page = open(PAGE, encoding="utf-8").read()
    try:
        d = M.save(M.build())
    except Exception as ex:  # keep the page buildable even if the caches are missing
        print(f"trace_dirs: model failed ({type(ex).__name__}: {ex}); using last directions.json")
        d = json.load(open(M.JSON_OUT, encoding="utf-8"))
    data = json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = put(page, "/* TRD:CSS:START */", "/* TRD:CSS:END */", CSS, "/* OBS:CSS:END */", before=False)
    # sit between the release trace (8) and the report (12)
    page = re.sub(r"<!-- TRD:HTML:START -->.*?<!-- TRD:HTML:END -->\n?", "", page, flags=re.S)
    page = put(page, "<!-- TRD:HTML:START -->", "<!-- TRD:HTML:END -->", HTML, '<section class="card" data-view="obs" data-tab="trend">')
    page = put(page, "<!-- TRD:JS:START -->", "<!-- TRD:JS:END -->", JS.replace("__DATA__", data), "<!-- OBS:JS:END -->", before=False)
    open(PAGE, "w", encoding="utf-8").write(page)
    print(f"trace_dirs: 3 tabs, data {len(data) / 1024:.0f} KB, bug #{d['bug']['target']['number']} exists={d['bug']['exists']}")


if __name__ == "__main__":
    main()
