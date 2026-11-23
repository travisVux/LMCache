"""Release Management · 'Now · Release Desk' and 'History' tabs (2026-11-15). Idempotent.

Brings the ops-app views into the page's own Release Management view; the other two views (Release Exploration,
Report 1130) are not touched.
  Now · Release Desk (#obs/today, landing): where we are (verdict + STABLE / $GOOD / latest tag / open decisions / blockers),
      data age per source with STALE, D1–D4 with evidence, blockers (publish errors, missing artifacts, dev red + LKG,
      open bugs, carry-over) with owner and copy-able commands, dev gate pipelines. The Today action inbox follows
      (build_today.py, same tab).
  Weekly full suite (#obs/today, section 4): verdict of the newest WEEKLY_FULL=true build, counts, failing jobs,
      compare link to the last green weekly commit, run strip (ops-app collect_weekly.py).
  History (#obs/hist): KPI cards, nightly, weekly full suite, publish.yml per week, dev gate pass rate, release cycle, failing jobs.
Reads release_desk.json (ops-app export: 'overview' + 'history' + 'lkg'), local only. Run after build_today.py.
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
<!-- DESK:HTML:START -->
<section class="card" data-view="obs" data-tab="today" id="dkWhere"><div class="head"><h2 id="dkWhereH">Where we are</h2><p class="sub" id="dkWhereSub"></p></div><div id="dkWhereB"></div></section>
<section class="card" data-view="obs" data-tab="today" id="dkDecide"><div class="head"><h2 id="dkDecideH">Decide</h2><p class="sub" id="dkDecideSub"></p></div><div id="dkDecideB"></div></section>
<section class="card" data-view="obs" data-tab="today" id="dkBlock"><div class="head"><h2 id="dkBlockH">Blocking the next RC</h2><p class="sub" id="dkBlockSub"></p></div><div id="dkBlockB"></div></section>
<section class="card" data-view="obs" data-tab="today" id="dkGates"><div class="head"><h2 id="dkGatesH">dev gate pipelines</h2><p class="sub" id="dkGatesSub"></p></div><div id="dkGatesB"></div></section>
<section class="card" data-view="obs" data-tab="today" id="dkWeekly"><div class="head"><h2 id="dkWeeklyH">Weekly full suite</h2><p class="sub" id="dkWeeklySub"></p></div><div id="dkWeeklyB"></div></section>
<section class="card" data-view="obs" data-tab="hist" id="dkHist"><div class="head"><h2 id="dkHistH">History</h2><p class="sub" id="dkHistSub"></p></div><div id="dkHistB"></div></section>
<!-- DESK:HTML:END -->
"""

CSS = r"""
/* DESK:CSS:START */
.dk-ages{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px}
.dk-age{font-size:11.5px;padding:2px 8px;border-radius:999px;background:var(--surface-2);color:var(--text-secondary);overflow-wrap:anywhere}
.dk-age b{color:var(--text-primary);font-weight:650}
.dk-age.stale{background:color-mix(in oklab,var(--warning) 16%,var(--surface-1));color:var(--text-primary);border:1px dashed var(--warning)}
.dk-stale{display:inline-block;margin-left:6px;font-size:10.5px;font-weight:700;padding:0 6px;border-radius:5px;border:1px dashed var(--warning);color:var(--warning);white-space:nowrap}
.dk-hero{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
.dk-tile{border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--surface-1);min-width:0}
.dk-tile.rb{border-color:var(--good)}
.dk-tile .k{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted)}
.dk-tile .v{font-size:20px;font-weight:700;color:var(--text-primary);margin:2px 0;overflow-wrap:anywhere}
.dk-tile .d{font-size:12px;color:var(--text-secondary);line-height:1.4;overflow-wrap:anywhere}
.dk-st{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:999px;font-weight:650;font-size:12.5px;border:1.5px solid var(--border)}
.dk-st::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--text-muted)}
.dk-st.red{border-color:var(--critical)}.dk-st.red::before{background:var(--critical)}
.dk-st.amber{border-color:var(--warning)}.dk-st.amber::before{background:var(--warning)}
.dk-st.green{border-color:var(--good)}.dk-st.green::before{background:var(--good)}
.dk-phase{font-size:12.5px;color:var(--text-secondary);margin:6px 0 10px}
.dk-scroll{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
.dk-t{width:100%;border-collapse:collapse;font-size:12.5px}
.dk-t th{text-align:left;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted);padding:5px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
.dk-t td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:top;color:var(--text-primary)}
.dk-t tr:last-child td{border-bottom:0}
.dk-mute{color:var(--text-muted);font-size:12px}
.dk-hint{display:block;margin-top:4px;font-size:12px;padding:3px 8px;border-radius:6px;background:color-mix(in oklab,var(--warning) 14%,var(--surface-1));color:var(--text-primary)}
.dk-err{display:block;margin-top:3px;font:11.5px ui-monospace,Consolas,monospace;color:var(--critical);overflow-wrap:anywhere}
.dk-fact{display:block;margin-top:3px;font-size:12px;color:var(--warning)}
.dk-grp{margin:14px 0 4px;font-size:11.5px;color:var(--text-secondary)}
.dk-chip{display:inline-block;font-size:10.5px;font-weight:750;letter-spacing:.03em;padding:1px 8px;border-radius:6px;border:1.5px solid var(--border);white-space:nowrap;margin-right:6px}
.dk-chip.red{border-color:var(--critical)}.dk-chip.amber{border-color:var(--warning)}.dk-chip.green{border-color:var(--good)}.dk-chip.gray{color:var(--text-muted)}
.dk-copy{all:unset;cursor:pointer;font-size:11.5px;font-weight:600;color:var(--series-1);white-space:nowrap}
.dk-copy:focus-visible{outline:2px solid var(--series-1)}
.dk-strip{display:flex;flex-wrap:wrap;gap:2px;align-items:center}
.dk-strip i{width:10px;height:16px;border-radius:2px;display:inline-block;background:var(--text-muted);opacity:.5}
.dk-strip i.p{background:var(--good);opacity:1}.dk-strip i.f{background:var(--critical);opacity:1}.dk-strip i.a{background:var(--warning);opacity:1}
.dk-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.dk-grid>*{min-width:0}
.dk-card{border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--surface-1);min-width:0}
.dk-card h3{margin:0 0 2px;font-size:13.5px}
.dk-card .def{margin:0 0 6px;font-size:12px;color:var(--text-muted)}
.dk-card .val{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
.dk-d{font-size:11.5px;font-weight:700;margin-left:6px}.dk-d.good{color:var(--good)}.dk-d.bad{color:var(--critical)}.dk-d.flat{color:var(--text-muted)}
.dk-chart svg{width:100%;height:auto;display:block}
.dk-chart text{fill:var(--text-muted);font-size:10px}
.dk-h3{margin:16px 0 4px;font-size:14px}
@media (max-width:1100px){.dk-hero{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:700px){.dk-hero{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:520px){.dk-hero,.dk-grid{grid-template-columns:1fr}}
/* DESK:CSS:END */
"""

JS = r"""
<!-- DESK:JS:START -->
<script id="deskData" type="application/json">__DATA__</script>
<script>
(function(){
  let D;try{D=JSON.parse(document.getElementById('deskData').textContent);}catch(e){return;}
  if(!D||!D.overview)return;
  const O=D.overview,H=D.history,LKG=D.lkg||{};
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en;
  const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const raw=s=>`<span class="obsraw">${esc(s)}</span>`;
  // text from RELEASE_PREP.md / registries is data: keep it raw (not translated), allow `code` and **bold**
  const md=s=>`<span class="obsraw">${esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>')}</span>`;
  const day=s=>s?String(s).slice(0,10):'–';
  const ago=s=>{if(!s)return '';const h=(Date.now()-Date.parse(s))/36e5;return h<1?T('just now','vừa xong'):h<48?T(Math.round(h)+' h ago',Math.round(h)+' giờ trước'):T(Math.round(h/24)+' days ago',Math.round(h/24)+' ngày trước');};
  const a=(u,t)=>u?`<a href="${esc(u)}" target="_blank" rel="noopener">${t}</a>`:t;
  const AG=Object.fromEntries((O.ages||[]).map(x=>[x.key,x]));
  const fmtAge=h=>h==null?'?':h<1?'<1 h':h<48?Math.round(h)+' h':Math.round(h/24)+' d';
  const stale=k=>{const x=AG[k];return x&&x.stale?`<span class="dk-stale" title="${esc(x.label)} · ${esc(x.at||'')}">STALE (${Math.round(x.age_h/24)}d)</span>`:'';};
  const copy=(c,tag)=>c?`<button type="button" class="dk-copy" data-cmd="${esc(c)}" title="${esc(c)}">${T('copy cmd','copy lệnh')}${tag?' · '+raw(tag):''}</button>`:'';
  const owner=o=>o&&o.who?`<span class="dk-mute">Owner: <b class="obsraw">${esc(o.who)}</b>${o.how==='author'?' ('+T('author','tác giả')+')':''}</span>`:'';
  const set=(id,h,sub,body)=>{const e=document.getElementById(id);if(!e)return;e.querySelector('h2').textContent=h;e.querySelector('.sub').textContent=sub;e.querySelector('div[id$="B"]').innerHTML=body;};
  const VERD=k=>({red:T('Not ready for the next RC','Chưa sẵn sàng cho RC tiếp'),amber:T('Ready with open items','Sẵn sàng, còn việc mở'),green:T('Ready','Sẵn sàng')})[k];   // a function: language can change
  const KIND={publish:['red','Publish failed','Publish lỗi'],artifact:['red','Missing artifact (PyPI / Docker / GitHub)','Thiếu artifact (PyPI / Docker / GitHub)'],
    ci:['red','dev is red','dev đang đỏ'],pr:['amber','Bug not fixed','Bug chưa sửa'],carryover:['gray','Carried over from the last release','Mang từ bản trước']};

  function where(){
    const nb=O.blockers.length,by={};O.blockers.forEach(b=>by[b.kind]=(by[b.kind]||0)+1);
    const kinds=Object.entries(by).map(([k,n])=>n+' '+T(KIND[k][1],KIND[k][2]).toLowerCase()).join(' · ');
    const g=O.good,openD=O.decisions.filter(d=>d.status==='open');
    const tile=(k,v,d,cls)=>`<div class="dk-tile${cls?' '+cls:''}"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`;
    const ages=`<div class="dk-ages"><span class="dk-age"><b>${T('Data age','Tuổi dữ liệu')}</b></span>`+(O.ages||[]).map(x=>
      `<span class="dk-age${x.stale?' stale':''}" title="${esc(x.at||'')}">${raw(x.label)} · <b>${fmtAge(x.age_h)}</b>${x.stale?' · STALE':''}</span>`).join('')+`</div>`;
    return `<div><span class="dk-st ${O.status}">${esc(VERD(O.status))}</span></div><div class="dk-phase">${esc(T(O.phase.en,O.phase.vi))}</div>`+ages+
      `<div class="dk-hero">`+
      tile(T('Stable (users have)','Stable (người dùng đang dùng)'),a(O.stable&&O.stable.url,raw(O.stable&&O.stable.tag||'–')),day(O.stable&&O.stable.at)+' · '+ago(O.stable&&O.stable.at))+
      tile(T('Rollback target ($GOOD)','Bản rollback ($GOOD)'),a(g&&g.url,raw(g&&g.tag||'–')),
        `<span title="${esc(T('Rule: newest final/post tag whose core artifacts are present and correct: ','Luật: tag final/post mới nhất có đủ artifact lõi: ')+((g&&g.core)||[]).join(', '))}">${T('newest final/post with core artifacts OK ⓘ','final/post mới nhất có đủ artifact lõi ⓘ')}</span>`+
        (g&&g.gaps.length?'<br>'+T('not core, missing: ','ngoài lõi, thiếu: ')+raw(g.gaps.join(', ')):''),'rb')+
      tile(T('Latest tag','Tag mới nhất'),a(O.latest&&O.latest.url,raw(O.latest&&O.latest.tag||'–')),day(O.latest&&O.latest.at)+' · '+ago(O.latest&&O.latest.at))+
      tile(T('Open decisions','Quyết định còn mở'),`${openD.length} / ${O.decisions.length}`,`${openD.filter(d=>d.hint).length} ${T('look decided in practice','có vẻ đã quyết trên thực tế')}`)+
      tile(T('Blocking','Đang chặn'),nb,esc(kinds))+`</div>`;
  }
  function decide(){
    if(!O.decisions.length)return `<p class="dk-mute">${T('No decisions listed.','Không có quyết định nào.')}</p>`;
    return `<div class="dk-scroll"><table class="dk-t"><thead><tr><th>#</th><th>${T('Question','Câu hỏi')}</th><th>${T('Status','Trạng thái')}</th></tr></thead><tbody>`+
      O.decisions.map(d=>`<tr><td><b>${esc(d.code)}</b></td><td>${md(d.question)}${stale('release_prep')}${d.options?`<div class="dk-mute">${md(d.options)}</div>`:''}`+
        (d.hint?`<span class="dk-hint">⚑ ${T('Evidence','Bằng chứng')}: ${esc(T(d.hint.en,d.hint.vi))} ${d.hint.url?a(d.hint.url,'↗'):''}</span>`:'')+`</td>`+
        `<td>${d.status==='open'?(d.hint?`<span class="dk-chip amber">${T('open in doc · confirm','mở trong doc · cần xác nhận')}</span>`:`<span class="dk-chip red">${T('open','mở')}</span>`):`<span class="dk-chip green">${raw(d.choice||T('decided','đã quyết'))}</span>`}</td></tr>`).join('')+`</tbody></table></div>`;
  }
  function blocks(){
    const merged=[];
    O.blockers.forEach(b=>{const ev=(b.title.match(/\((\w+)\)/)||[])[1];
      const same=b.kind==='publish'&&merged.find(x=>x.kind==='publish'&&x.code===b.code&&x.detail===b.detail);
      if(same){same.events.push(ev);if(b.cmd)same.cmds.push([b.cmd,ev]);return;}
      merged.push({...b,events:b.kind==='publish'?[ev]:[],cmds:b.cmd?[[b.cmd,b.kind==='publish'?ev:'']]:[]});});
    const groups={};merged.forEach(b=>(groups[b.kind]=groups[b.kind]||[]).push(b));
    return Object.entries(groups).map(([k,bs])=>`<div class="dk-grp"><span class="dk-chip ${KIND[k][0]}">${esc(T(KIND[k][1],KIND[k][2]))}</span></div>`+
      `<div class="dk-scroll"><table class="dk-t"><tbody>`+bs.map(b=>{
        const lk=b.kind==='ci'&&LKG[b.code]?LKG[b.code]:null;
        const lkg=lk?`<span class="dk-fact">▸ ${lk.green?T('last green','xanh cuối')+' '+a(lk.green.url,'#'+lk.green.number)+' '+day(lk.green.created_at):T('no green build since','không có build xanh từ')+' '+day(lk.history_from)}${lk.red_builds?' · '+lk.red_builds+' '+T('red builds since','build đỏ từ đó'):''}</span>`:'';
        return `<tr><td style="width:30%"><b class="obsraw">${esc(b.code)}</b>${b.events.length?`<div class="dk-mute">run: ${raw(b.events.filter(Boolean).join(' + '))}</div>`:''}</td>`+
          `<td>${b.kind==='publish'?'':md(b.title)}${stale(b.src)}${b.detail?`<span class="dk-err obsraw">${esc(b.detail)}</span>`:''}${b.fact&&b.kind!=='ci'?`<span class="dk-fact obsraw">▸ ${esc(b.fact)}</span>`:''}${lkg}`+
          `${b.fix_ref&&b.kind==='carryover'?`<div class="dk-mute">${T('Fix','Cách sửa')}: ${md(b.fix_ref)}</div>`:''}</td>`+
          `<td style="white-space:nowrap">${owner(b.owner)}${b.cmds.map(([c,t])=>'<br>'+copy(c,b.cmds.length>1?t:'')).join('')}</td>`+
          `<td style="white-space:nowrap">${b.evidence?a(b.evidence,T('evidence ↗','bằng chứng ↗')):''}</td></tr>`;}).join('')+`</tbody></table></div>`).join('');
  }
  function gates(){
    return `<div class="dk-scroll"><table class="dk-t"><tbody>`+(O.dev_gates||[]).map(g=>{const lk=LKG[g.slug]||{};
      return `<tr><td><b class="obsraw">${esc(g.slug)}</b></td><td><div class="dk-strip">${g.recent.map(s=>`<i class="${s==='passed'?'p':s==='failed'?'f':''}" title="${esc(s)}"></i>`).join('')}</div></td>`+
        `<td>${g.last.state==='passed'?'<span class="dk-chip green">passed</span>':'<span class="dk-chip red">failed</span>'} ${a(g.last.url,'#'+g.last.number)}</td>`+
        `<td class="dk-mute">${T('last green','xanh cuối')}: ${day(g.last_pass)}${lk.red_builds?' · '+lk.red_builds+' '+T('red builds since','build đỏ từ đó'):''}</td></tr>`;}).join('')+`</tbody></table></div>`;
  }
  // ── Weekly full suite (k3-multiprocess-test, WEEKLY_FULL=true; ops-app collect_weekly.py)
  const WV={pass:['green','passed','đạt'],fail:['red','failed','không đạt'],no_verdict:['red','no verdict','không có kết luận'],running:['gray','running','đang chạy']};
  // A pass where some job only passed on a retry is amber: an intermittent correctness bug can hide there.
  const wflaky=r=>r.verdict==='pass'&&(r.flaky||0)>0;
  const wchip=r=>{if(wflaky(r))return `<span class="dk-chip amber">${T('passed · '+r.flaky+' flaky','đạt · '+r.flaky+' chập chờn')}</span>`;
    const v=WV[r.verdict]||['gray',r.verdict,r.verdict];return `<span class="dk-chip ${v[0]}">${T(v[1],v[2])}</span>`;};
  const wcls=r=>wflaky(r)?'a':r.verdict==='pass'?'p':r.verdict==='running'?'':'f';
  const sha=s=>s?String(s).slice(0,10):'–';
  function weekly(){
    const W=O.weekly||{},L=W.latest,R=W.reference,runs=W.runs||[];
    const ref=R?`<p class="dk-mute">${T('Reference (last full dev build before the weekly run):','Mốc tham chiếu (build dev đủ bộ cuối cùng trước khi có weekly):')} ${a(R.url,'#'+R.number)} · ${day(R.created_at)} · ${R.passed}/${R.required} ${T('test jobs passed','job test đạt')} · ${T('no verdict step then, so skips were not checked.','khi đó chưa có bước verdict, nên chưa kiểm tra skip.')}</p>`:'';
    if(!L)return `<div><span class="dk-chip gray">${T('No weekly run yet','Chưa có lần chạy weekly')}</span> <span class="dk-mute">${T('Schedule','Lịch')}: ${raw(W.schedule||'')} · ${a(W.pipeline_url,'k3-multiprocess-test ↗')}</span></div>`+ref;
    const age=(Date.now()-Date.parse(L.created_at))/864e5;
    const miss=age>8?`<span class="dk-stale">${T('no run in '+Math.round(age)+' days','không có lần chạy trong '+Math.round(age)+' ngày')}</span>`:'';
    const tile=(k,v,d)=>`<div class="dk-tile"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`;
    const n=x=>x==null?'–':x;
    const P=W.last_pass;
    let since='';
    if(L.verdict!=='pass'&&L.verdict!=='running'){
      since=P?`<span class="dk-hint">⚑ ${T('The regression came in between the last green weekly and this run:','Lỗi xuất hiện giữa lần weekly xanh cuối và lần này:')} ${a('https://github.com/LMCache/LMCache/compare/'+P.commit_sha+'...'+L.commit_sha,raw(sha(P.commit_sha)+'…'+sha(L.commit_sha))+' ↗')}</span>`
        :`<span class="dk-hint">⚑ ${T('No green weekly run yet: fix this run to set the baseline.','Chưa có lần weekly xanh nào: sửa lần này để có baseline.')}</span>`;}
    const probs=L.problems||[];
    const ptab=probs.length?`<div class="dk-scroll" style="margin-top:10px"><table class="dk-t"><thead><tr><th>Job</th><th>${T('state','trạng thái')}</th></tr></thead><tbody>`+
      probs.map(p=>`<tr><td class="obsraw">${esc(p.label)}</td><td><span class="dk-chip red">${esc(p.state)}</span></td></tr>`).join('')+`</tbody></table></div>`:'';
    const strip=[...runs].reverse().map(r=>`<a href="${esc(r.url)}" target="_blank" rel="noopener"><i class="${wcls(r)}" title="${esc(day(r.created_at))} #${r.number} ${esc(r.verdict)}"></i></a>`).join('');
    return `<div>${wchip(L)} ${a(L.url,'#'+L.number)} <span class="dk-mute">${day(L.created_at)} · ${ago(L.created_at)} · ${raw(L.trigger||'')} · ${raw(L.branch||'')} @ ${raw(sha(L.commit_sha))}</span>${miss}</div>`+since+
      `<div class="dk-hero" style="margin-top:10px">`+
      tile(T('Required jobs','Job bắt buộc'),n(L.required),`${T('passed','đạt')} ${n(L.passed)} · ${T('flaky','chập chờn')} ${n(L.flaky)}`)+
      tile(T('Not passed','Không đạt'),(L.failed||0)+(L.missing||0)+(L.skipped||0),`${T('failed','fail')} ${n(L.failed)} · ${T('missing','thiếu')} ${n(L.missing)} · ${T('skipped','bỏ qua')} ${n(L.skipped)}`)+
      tile(T('Known skips','Skip đã biết'),n(L.allowed_skip),T('in allowed-skips.txt: coverage we do not have','trong allowed-skips.txt: phần không được test'))+
      tile(T('Last green weekly','Weekly xanh cuối'),P?a(P.url,'#'+P.number):'–',P?day(P.created_at):T('none yet','chưa có'))+
      tile(T('Red streak','Chuỗi đỏ'),W.red_streak||0,T('weekly runs since the last green','lần weekly từ lần xanh cuối'))+`</div>`+
      ptab+`<div class="dk-grp">${T('Last runs, oldest → newest','Các lần gần nhất, cũ → mới')}</div><div class="dk-strip">${strip}</div>`+ref;
  }
  // ── History
  function spark(v,c){v=v.filter(x=>x!=null);if(v.length<2)return '';const W=160,Hh=34,mx=Math.max(...v),mn=Math.min(...v),r=mx-mn||1;
    return `<svg viewBox="0 0 ${W} ${Hh}" width="${W}" height="${Hh}"><polyline fill="none" stroke="${c}" stroke-width="2" points="${v.map((x,i)=>`${(i/(v.length-1))*W},${Hh-3-((x-mn)/r)*(Hh-6)}`).join(' ')}"/></svg>`;}
  function bars(series,keys,colors,label){const W=Math.max(series.length*18,300),pad=22,h=120,max=Math.max(1,...series.map(s=>keys.reduce((t,k)=>t+(s[k]||0),0))),bw=(W-pad)/Math.max(series.length,1);
    let g=`<line x1="${pad}" y1="${h}" x2="${W}" y2="${h}" stroke="var(--border)"/><text x="0" y="10">${max}</text>`;
    series.forEach((s,i)=>{let y=h;keys.forEach((k,j)=>{const v=s[k]||0,bh=(v/max)*(h-12);if(v)g+=`<rect x="${pad+i*bw+2}" y="${y-bh}" width="${bw-4}" height="${bh}" fill="${colors[j]}"><title>${esc(label(s))} · ${k}: ${v}</title></rect>`;y-=bh;});
      if(i%Math.ceil(series.length/8)===0)g+=`<text x="${pad+i*bw}" y="${h+12}">${esc(label(s))}</text>`;});
    return `<div class="dk-chart"><svg viewBox="0 0 ${W} ${h+16}" role="img">${g}</svg></div>`;}
  function hist(){
    if(!H)return '';
    const css=n=>getComputedStyle(document.querySelector('.viz-root')||document.documentElement).getPropertyValue(n).trim()||'#888';
    const G=css('--good'),R=css('--critical'),M=css('--text-muted'),A=css('--warning');
    const K=[['observe_history.prs.open',T('Open PRs','PR đang mở'),T('Open PRs on GitHub at snapshot time.','Số PR đang mở lúc chụp snapshot.')],
      ['observe_history.prs.merged_unreleased',T('Merged, not released','Đã merge, chưa phát hành'),T('PRs merged since the last stable tag.','PR merge sau tag stable gần nhất.')],
      ['observe_history.queue.k3-unit-tests.w90',T('k3-unit wait p90 (min)','Chờ k3-unit p90 (phút)'),T('90th percentile GPU queue wait, last 20 builds. The median hides long waits.','Phân vị 90 thời gian chờ GPU, 20 build gần nhất. Trung vị che mất các lần chờ lâu.')],
      ['observe_history.queue.k3-multiprocess-test.w90',T('k3-mp wait p90 (min)','Chờ k3-mp p90 (phút)'),T('Same, for the multiprocess pipeline.','Như trên, cho pipeline multiprocess.')],
      ['ops_hist.tot.GPU_failed',T('GPU job-min failed / 24 h','Phút job GPU fail / 24 giờ'),T('GPU job minutes spent on failed jobs in the last 24 h.','Phút job GPU tiêu cho job fail trong 24 giờ.')]];
    const kv={};H.kpi.forEach(r=>(kv[r.key]=kv[r.key]||[]).push(r));
    const cards=K.map(([k,n,def])=>{const s=kv[k]||[],l=s[s.length-1],p=s[s.length-2],d=l&&p?l.value-p.value:null,good=d==null||d===0?null:d<0;
      return `<div class="dk-card"><h3>${esc(n)}</h3><p class="def">${esc(def)}</p><span class="val">${l?Math.round(l.value*10)/10:'–'}</span>`+
        (d!=null?`<span class="dk-d ${good==null?'flat':good?'good':'bad'}">${d>0?'▲':d<0?'▼':'='} ${Math.abs(Math.round(d*10)/10)}</span>`:'')+
        ` <span class="dk-mute">${l?day(l.day):''} · n=${s.length}</span><div>${spark(s.map(x=>x.value),M)}</div></div>`;}).join('');
    const nf=[...H.nightly].reverse().findIndex(n=>n.conclusion==='success');
    const night=H.nightly.map(n=>`<a href="${esc(n.url)}" target="_blank" rel="noopener"><i class="${n.conclusion==='success'?'p':n.conclusion==='failure'?'f':''}" title="${esc(n.day)} ${esc(n.conclusion||'')}"></i></a>`).join('');
    const wk={};H.publish_weekly.forEach(r=>{const w=(wk[r.week]=wk[r.week]||{week:r.week,ok:0,failed:0,cancelled:0});w.ok+=r.ok;w.failed+=r.failed;w.cancelled+=r.cancelled;});
    const pipes={};H.gates.forEach(g=>(pipes[g.pipeline]=pipes[g.pipeline]||[]).push(g));
    const heat=Object.entries(pipes).map(([p,ds])=>`<tr><td><b class="obsraw">${esc(p)}</b></td><td><div class="dk-strip">${ds.map(d=>{const c=d.pass_pct==null?M:d.pass_pct>=90?G:d.pass_pct>=50?A:R;
      return `<i style="background:${c};opacity:1" title="${esc(d.day)}: ${d.passed}/${d.passed+d.failed}"></i>`;}).join('')}</div></td><td class="dk-mute">${ds.length} ${T('days','ngày')}</td></tr>`).join('');
    const cyc=H.cycle.map(c=>`<tr><td><b class="obsraw">${esc(c.line)}</b></td><td>${day(c.first_rc_at)}</td><td>${day(c.final_at)}</td><td>${c.n_rc}</td><td>${c.n_post}</td><td>${c.rc_to_final_days!=null?c.rc_to_final_days+' '+T('d','ngày'):T('in progress','đang làm')}</td></tr>`).join('');
    const jobs=H.failing_jobs.map(j=>`<tr><td class="obsraw">${esc(j.name)}</td><td>${j.failures}</td><td class="dk-mute">${day(j.last_at)}</td><td>${j.last_error?`<span class="dk-err obsraw" title="${esc(j.last_error)}">${esc(j.last_error.length>160?j.last_error.slice(0,160)+'…':j.last_error)}</span>`:''}</td></tr>`).join('');
    const HW=(H.weekly&&H.weekly.runs)||[];
    const wstrip=HW.length?[...HW].reverse().map(r=>`<a href="${esc(r.url)}" target="_blank" rel="noopener"><i class="${wcls(r)}" title="${esc(day(r.created_at))} #${r.number} ${esc(r.verdict)}"></i></a>`).join(''):`<span class="dk-mute">${T('No weekly run yet.','Chưa có lần chạy weekly.')}</span>`;
    const wpass=HW.filter(r=>r.verdict==='pass').length,wdone=HW.filter(r=>r.verdict!=='running').length;
    return `<h3 class="dk-h3">${T('Key numbers per day','Chỉ số chính theo ngày')}</h3><p class="dk-mute">${T('▲▼ = change vs the previous snapshot day; green = better.','▲▼ = thay đổi so với ngày snapshot trước; xanh = tốt hơn.')}</p><div class="dk-grid">${cards}</div>`+
      `<div class="dk-grid" style="margin-top:12px"><div class="dk-card"><h3>${T('Nightly image build','Build image nightly')}</h3><p class="def">${T('Last 30 runs, oldest → newest.','30 run gần nhất, cũ → mới.')} ${nf===-1?`<b>${T('No success in this window.','Không có lần thành công nào trong khoảng này.')}</b>`:T('Failures since last success','Số lần fail từ lần xanh cuối')+': <b>'+nf+'</b>'}</p><div class="dk-strip">${night}</div></div>`+
      `<div class="dk-card"><h3>${T('Weekly full suite','Bộ test đầy đủ hằng tuần')}</h3><p class="def">${T('k3-multiprocess-test with WEEKLY_FULL=true, last 26 runs, oldest → newest. Green = every required job passed.','k3-multiprocess-test với WEEKLY_FULL=true, 26 lần gần nhất, cũ → mới. Xanh = mọi job bắt buộc đều đạt.')} ${wdone?T('Green','Xanh')+': <b>'+wpass+' / '+wdone+'</b>':''}</p><div class="dk-strip">${wstrip}</div></div>`+
      `<div class="dk-card"><h3>${T('publish.yml per week','publish.yml theo tuần')}</h3><p class="def">${T('All events. Green ok · red failed · gray cancelled.','Mọi event. Xanh ok · đỏ fail · xám cancelled.')}</p>${bars(Object.values(wk),['ok','failed','cancelled'],[G,R,M],s=>s.week.slice(5))}</div></div>`+
      `<h3 class="dk-h3">${T('dev gate pass rate per day (30 days)','Tỉ lệ xanh của gate trên dev theo ngày (30 ngày)')}</h3><p class="dk-mute">${T('Green ≥ 90 % · amber ≥ 50 % · red < 50 %.','Xanh ≥ 90 % · vàng ≥ 50 % · đỏ < 50 %.')}</p><div class="dk-scroll"><table class="dk-t"><tbody>${heat}</tbody></table></div>`+
      `<div class="dk-grid" style="margin-top:12px"><div class="dk-card"><h3>${T('Release cycle','Chu kỳ release')}</h3><p class="def">${T('First RC → final tag, per line.','Từ RC đầu tiên → tag final, theo từng bản.')}</p><div class="dk-scroll"><table class="dk-t"><thead><tr><th>Line</th><th>rc1</th><th>final</th><th>#rc</th><th>#post</th><th>${T('days','ngày')}</th></tr></thead><tbody>${cyc}</tbody></table></div></div>`+
      `<div class="dk-card"><h3>${T('Jobs that fail most','Job fail nhiều nhất')}</h3><p class="def">${T('publish / nightly jobs, with the last error line read.','Job publish / nightly, kèm dòng lỗi cuối cùng đã đọc.')}</p><div class="dk-scroll"><table class="dk-t"><thead><tr><th>Job</th><th>#</th><th>${T('last','gần nhất')}</th><th>${T('error','lỗi')}</th></tr></thead><tbody>${jobs}</tbody></table></div></div></div>`;
  }
  function render(){
    set('dkWhere','0 · '+T('Where we are','Đang ở đâu'),T('Release Desk: registry facts (PyPI, Docker Hub, GitHub) from ops-app, local runs only. STALE = source older than 48 h.','Release Desk: dữ kiện registry (PyPI, Docker Hub, GitHub) từ ops-app, chỉ chạy local. STALE = nguồn cũ hơn 48 giờ.'),where());
    set('dkDecide','1 · '+T('Decide','Cần quyết')+' · v'+(O.line||''),T(`From release-${O.line}/RELEASE_PREP.md. ⚑ = facts suggest it was already decided: write the choice in the doc.`,`Từ release-${O.line}/RELEASE_PREP.md. ⚑ = dữ kiện cho thấy đã quyết trên thực tế: ghi lựa chọn vào tài liệu.`),decide());
    set('dkBlock','2 · '+T('Blocking the next RC','Đang chặn RC tiếp theo'),T('Publish errors (first error line) → missing artifacts → dev red + last-known-good → open bugs → carry-over. Copy a command to act.','Lỗi publish (dòng lỗi đầu tiên) → thiếu artifact → dev đỏ + lần xanh cuối → bug còn mở → việc mang sang. Copy lệnh để làm.'),blocks());
    set('dkGates','3 · '+T('dev gate pipelines','Pipeline gate trên dev'),T('Last 10 finished dev builds, oldest → newest. Must be green before an RC. The Today action inbox follows.','10 build dev gần nhất, cũ → mới. Phải xanh trước khi cắt RC. Hộp việc hôm nay ở ngay dưới.'),gates());
    set('dkWeekly','4 · '+T('Weekly full suite','Bộ test đầy đủ hằng tuần'),T('Every multiprocess test + DSV4 full-size (TP=4) on dev, Sun 20:00 UTC. Red = a required job failed, did not run, or was skipped. Check it at stand-up.','Toàn bộ test multiprocess + DSV4 bản đầy đủ (TP=4) trên dev, CN 20:00 UTC. Đỏ = job bắt buộc fail, không chạy, hoặc bị bỏ qua. Xem ở stand-up.'),weekly());
    set('dkHist',T('History','Xu hướng'),T('Trends from the ops-app history store (ops.db) and the daily snapshots.','Xu hướng từ kho lịch sử ops-app (ops.db) và snapshot hằng ngày.'),hist());
    // order on the Now tab: desk sections first, then the Today inbox (build_today.py)
    const td=document.getElementById('todaySec');if(td){['dkWhere','dkDecide','dkBlock','dkGates','dkWeekly'].forEach(id=>{const s=document.getElementById(id);if(s)td.before(s);});}
  }
  document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('button.dk-copy[data-cmd]');if(!b)return;const c=b.dataset.cmd,was=b.innerHTML;
    const done=()=>{b.textContent=T('copied','đã copy');setTimeout(()=>{b.innerHTML=was;},1500);};
    if(navigator.clipboard)navigator.clipboard.writeText(c).then(done,()=>prompt('',c));else prompt('',c);});
  const start=()=>{render();addEventListener('langchange',render);};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
</script>
<!-- DESK:JS:END -->
"""


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor) if before else page.index(anchor) + len(anchor)
    return page[:i] + block.strip() + "\n" + page[i:]


def main():
    try:
        data = json.load(open(DESK, encoding="utf-8"))
    except (OSError, ValueError):
        print("desk: no release_desk.json (run ops-app/backend/export_page_data.py); tabs stay empty")
        data = {}
    keep = dict(overview=data.get("overview"), history=data.get("history"), lkg=data.get("lkg"))
    page = open(PAGE, encoding="utf-8").read()
    page = put(page, "/* DESK:CSS:START */", "/* DESK:CSS:END */", CSS, "/* NAV:CSS:START */")   # top level, like TODAY CSS
    page = put(page, "<!-- DESK:HTML:START -->", "<!-- DESK:HTML:END -->", HTML, "<!-- TODAY:HTML:START -->")
    js = JS.replace("__DATA__", json.dumps(keep, ensure_ascii=False, separators=(",", ":"), default=str).replace("</", "<\\/"))
    page = put(page, "<!-- DESK:JS:START -->", "<!-- DESK:JS:END -->", js, "</body>")
    open(PAGE, "w", encoding="utf-8").write(page)
    o = keep["overview"] or {}
    print(f"desk: status {o.get('status')} · {len(o.get('blockers') or [])} blockers · {len(o.get('decisions') or [])} decisions · "
          f"stale sources {[a['key'] for a in o.get('ages') or [] if a.get('stale')]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
