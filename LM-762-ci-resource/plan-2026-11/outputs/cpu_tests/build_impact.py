"""Release · 'CI impact' tab (#obs/impact, aliases #impact #ci-impact #before-after), 2026-11-26 (v4: redesign to the
maintainer spec impact_redesign_spec.md). Idempotent.

One question: did the CI changes (#6730 tiered pre-review CI, #6731 split k3-multiprocess, #6854 weekly full build) make CI
cheaper, faster and no less safe, and is it proven yet? Before = v0 (30 days before the first merge), After = the latest
version window (ops-app/backend/ci_versions.json). Source: collect_ci_impact.py -> ops.db -> export_page_data.py
(release_desk.json 'impact'), embedded as <script id="impactData">.

Sections (top to bottom; the section ids are kept from v3, their content is new):
  imWin  windows (before / switch-over / after) + weekday warning + VERDICT STRIP: 'Too early to prove' / 'Looks better' /
         'Looks worse' by rule (proven = after window >= min_days AND every key number has n >= min_n), day progress,
         3 chips Cost / Speed / Safety (status colour + icon + word, only from numbers with enough runs)
  imGpu  BEFORE -> AFTER per key number, real units: one dumbbell per row (grey = before, blue = after, hollow = too few runs),
         its own axis, labelled values, absolute change + % small, sample-size bar (n vs min_n); grouped Cost / Speed / Safety
  imMp   WHERE DID THE GPU TIME GO: before / after bars per part (draft PR, ready PR, retries that failed again, post-merge
         builds, weekly full build) + the sum written out + the sentence that explains '+GPU a day vs -99 % draft GPU'
  imGha  WATCHLIST: only numbers that got worse (enough runs, >= 10 %) or carry a safety risk, each with a next step
  imRel  details: all metrics as a sortable table (always in the DOM) + 'How it is measured'
Trust rules: deltas are computed here from values (the collector keeps d_base_pct = null under min_days); no delta, no %
and no good / bad colour when n < min_n; n = 0 shows 'no data'.
Palette (dataviz validate_palette.js, light on #ffffff / dark on #16191e): after #2a78d6 / #3987e5 (categorical, PASS);
before grey #5f6570 / #6b727e (neutral: CVD dE 16.0 / 15.7, normal 16.0 / 15.8, >= 3:1); sample-size track #86b6ef / #1c5cab
(ordinal with the after hue, PASS). Good / bad = the page status tokens (--ok / --bad), always with an icon and a word.
Run after build_weekly.py (build_page.py does).
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
<!-- IMPACT:HTML:START -->
<section class="card" data-view="obs" data-tab="impact" id="imWin"><div class="head"><h2 id="imWinH">CI impact</h2></div><div id="imWinB"></div></section>
<section class="card" data-view="obs" data-tab="impact" id="imGpu"><div class="head"><h2 id="imGpuH">Before and after</h2></div><div id="imGpuB"></div></section>
<section class="card" data-view="obs" data-tab="impact" id="imMp"><div class="head"><h2 id="imMpH">Where did the GPU time go</h2></div><div id="imMpB"></div></section>
<section class="card" data-view="obs" data-tab="impact" id="imGha"><div class="head"><h2 id="imGhaH">Watchlist</h2></div><div id="imGhaB"></div></section>
<section class="card" data-view="obs" data-tab="impact" id="imRel"><div class="head"><h2 id="imRelH">Details</h2></div><div id="imRelB"></div></section>
<div id="imTip" role="tooltip" hidden></div>
<!-- IMPACT:HTML:END -->
"""

CSS = r"""
/* IMPACT:CSS:START */
/* CI impact (v4). Chart colours, validated with dataviz validate_palette.js against the page surfaces (light #ffffff, dark #16191e):
   --im-after = the one categorical hue (after); --im-before = neutral grey (before); --im-track = lighter step of the after hue
   (sample-size and day-progress meters, ordinal pair). Good / bad = page status tokens --ok / --bad, never colour alone. */
.viz-root{--im-before:#5f6570;--im-after:#2a78d6;--im-track:#86b6ef}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .viz-root{--im-before:#6b727e;--im-after:#3987e5;--im-track:#1c5cab}}
:root[data-theme="dark"] .viz-root{--im-before:#6b727e;--im-after:#3987e5;--im-track:#1c5cab}
.im-wins{margin:0 0 8px;font-size:12.5px;color:var(--text-2);line-height:1.6;overflow-wrap:anywhere}
.im-wins b{color:var(--text-1);font-weight:650}
.im-wins .im-sw{color:var(--text-3)}
.im-wins .sep{color:var(--text-3);margin:0 6px}
.im-key{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px;box-sizing:border-box}
.im-key.b{background:var(--im-before)}.im-key.a{background:var(--im-after)}.im-key.h{border:2px solid var(--im-after);background:transparent}
.im-chg-prs{font-size:12px;color:var(--text-3);margin:0 0 10px;overflow-wrap:anywhere}
.im-wd{display:flex;gap:8px;align-items:flex-start;font-size:12.5px;color:var(--text-1);background:var(--warn-bg);border:1px solid color-mix(in oklab,var(--warn) 35%,transparent);border-radius:var(--r-box);padding:7px 10px;margin:0 0 12px;line-height:1.5}
.im-wd .ic{color:var(--warn);font-weight:700}
.im-verdict{border:1px solid var(--border);border-left:4px solid var(--text-3);border-radius:var(--r-box);padding:12px 14px;background:var(--surface-1)}
.im-verdict[data-state="early"]{border-left-color:var(--warn)}.im-verdict[data-state="better"]{border-left-color:var(--ok)}.im-verdict[data-state="worse"]{border-left-color:var(--bad)}
.im-verdict .top{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center}
.im-verdict .vt{font-size:22px;font-weight:700;color:var(--text-1);line-height:1.2}
.im-verdict .vt .ic{margin-right:8px}
.im-verdict[data-state="early"] .vt .ic{color:var(--warn)}.im-verdict[data-state="better"] .vt .ic{color:var(--ok)}.im-verdict[data-state="worse"] .vt .ic{color:var(--bad)}
.im-prog{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--text-2);font-weight:600}
.im-prog .bar{display:block;width:120px;height:8px;border-radius:4px;background:var(--im-track);overflow:hidden}
.im-prog .bar i{display:block;height:100%;background:var(--im-after);border-radius:4px}
.im-verdict .why{margin:6px 0 10px;font-size:12.5px;color:var(--text-2);line-height:1.5}
.im-sofar-h{font-size:12px;color:var(--text-3);margin:0 0 6px}
.im-chips{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.im-chip{border:1px solid var(--border);border-radius:var(--r-box);padding:8px 10px;background:var(--surface-2);min-width:0}
.im-chip .h{font-size:15px;font-weight:700;color:var(--text-1);display:flex;flex-wrap:wrap;gap:2px 6px;align-items:baseline}
.im-chip .h .st{font-size:13px;font-weight:650;color:var(--text-2)}
.im-chip.good{background:var(--ok-bg);border-color:color-mix(in oklab,var(--ok) 35%,transparent)}.im-chip.good .h .st{color:var(--ok)}
.im-chip.bad{background:var(--bad-bg);border-color:color-mix(in oklab,var(--bad) 35%,transparent)}.im-chip.bad .h .st{color:var(--bad)}
.im-chip ul{margin:4px 0 0;padding:0;list-style:none;font-size:12px;color:var(--text-2);line-height:1.45}
.im-chip li{overflow-wrap:anywhere}
.im-legend{display:flex;gap:6px 16px;flex-wrap:wrap;align-items:center;font-size:12px;color:var(--text-2);margin:0 0 6px}
.im-grp{font-size:13px;font-weight:700;color:var(--text-1);margin:14px 0 2px;padding-bottom:4px;border-bottom:1px solid var(--border-strong)}
.im-row{display:grid;grid-template-columns:minmax(170px,28%) minmax(0,1fr) minmax(150px,24%);column-gap:16px;align-items:start;padding:8px 0;border-bottom:1px solid var(--border)}
.im-row:last-child{border-bottom:0}
.im-lab{font-size:13px;color:var(--text-1);line-height:1.35;min-width:0;overflow-wrap:anywhere}
.im-lab .u{display:block;font-size:11.5px;color:var(--text-3);margin-top:2px}
.im-def{text-decoration:underline dotted var(--text-3);text-underline-offset:3px;cursor:help}
.im-def:focus-visible,.im-dot:focus-visible,.im-bar:focus-visible,.im-chip:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.im-db{position:relative;height:50px;min-width:0}
.im-db .ax{position:absolute;left:4%;right:4%;top:27px;height:1px;background:var(--border-strong)}
.im-db .ln{position:absolute;top:26px;height:3px;border-radius:2px;background:var(--border-strong)}
.im-db .tk{position:absolute;top:36px;font-size:10px;color:var(--text-3);transform:translateX(-50%);white-space:nowrap;font-variant-numeric:tabular-nums}
.im-vl{position:absolute;top:2px;font-size:12px;line-height:1.2;color:var(--text-2);white-space:nowrap;transform:translateX(-50%);pointer-events:none;font-variant-numeric:tabular-nums}
.im-vl.a{color:var(--text-1);font-weight:700}
.im-vl.l{transform:translateX(calc(-100% + 4px))}.im-vl.r{transform:translateX(-4px)}
.im-dot{position:absolute;top:21px;width:13px;height:13px;margin-left:-6.5px;border-radius:50%;padding:0;border:0;box-shadow:0 0 0 2px var(--surface-1);cursor:default;box-sizing:border-box}
.im-dot::after{content:"";position:absolute;inset:-6px}
.im-dot.b{background:var(--im-before)}.im-dot.a{background:var(--im-after)}
.im-dot.a.hollow{background:var(--surface-1);border:2.5px solid var(--im-after)}
.im-n{display:flex;align-items:center;gap:8px;font-size:11.5px;color:var(--text-3);margin-top:2px;flex-wrap:wrap}
.im-n .bar{display:block;width:72px;height:4px;border-radius:2px;background:var(--im-track);overflow:hidden;flex:0 0 auto}
.im-n .bar i{display:block;height:100%;background:var(--im-after)}
.im-chg{font-size:12.5px;color:var(--text-2);line-height:1.45;min-width:0}
.im-chg b{font-size:15px;color:var(--text-1);font-weight:700;margin-right:4px;font-variant-numeric:tabular-nums}
.im-chg small{font-size:11.5px;color:var(--text-3)}
.im-chg .mute{color:var(--text-3)}
.im-pill{display:inline-block;font-size:11.5px;font-weight:650;padding:0 7px;border-radius:var(--r-pill);border:1px solid var(--border-strong);color:var(--text-2);white-space:nowrap;margin-top:2px}
.im-pill.good{color:var(--ok);background:var(--ok-bg);border-color:color-mix(in oklab,var(--ok) 40%,transparent)}
.im-pill.bad{color:var(--bad);background:var(--bad-bg);border-color:color-mix(in oklab,var(--bad) 40%,transparent)}
.im-sofar{font-size:11px;color:var(--text-3);margin-left:4px}
.im-hint{font-size:11px;color:var(--text-3);display:block;margin-top:2px}
.im-go .im-row{grid-template-columns:minmax(170px,28%) minmax(0,1fr) minmax(120px,18%)}
.im-bars{position:relative;min-width:0;padding:2px 0}
.im-bars .r{position:relative;height:15px;margin:0 0 2px}
.im-bar{position:absolute;left:0;top:1px;height:12px;border-radius:0 4px 4px 0;min-width:2px;padding:0;border:0;cursor:default}
.im-bar.b{background:var(--im-before)}.im-bar.a{background:var(--im-after)}
/* no data / not comparable: texture (45°) + dashed outline in muted ink, never a value-length bar */
.im-hatch{background:repeating-linear-gradient(45deg,color-mix(in oklab,var(--text-3) 45%,transparent) 0 2px,transparent 2px 6px);border:1px dashed var(--text-3)}
.im-bars .nd{display:inline-block;width:26px;height:12px;border-radius:0 4px 4px 0;vertical-align:-2px;margin-right:6px;box-sizing:border-box}
.im-bar.gap{border-radius:0 4px 4px 0;box-sizing:border-box}
.im-key.x{border-radius:2px;width:14px}
.im-bridge .gapt{color:var(--text-2)}
.im-bars .v{position:absolute;top:-1px;font-size:11.5px;line-height:14px;color:var(--text-2);white-space:nowrap;margin-left:6px;font-variant-numeric:tabular-nums}
.im-bars .v.a{color:var(--text-1);font-weight:650}
.im-bars .na{font-size:11.5px;color:var(--text-3);line-height:15px;white-space:nowrap}
.im-row.tot .im-lab{font-weight:700}
.im-up,.im-chg b.im-up{color:var(--bad)}.im-down,.im-chg b.im-down{color:var(--ok)}
.im-bridge{margin:12px 0 0;padding:8px 10px;border-radius:var(--r-box);background:var(--surface-2);font-size:13px;color:var(--text-1);line-height:1.6;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.im-why{margin:10px 0 0;font-size:13.5px;color:var(--text-1);line-height:1.55}
.im-notes{margin:8px 0 0 18px;padding:0;font-size:12px;color:var(--text-2);line-height:1.5}
.im-watch{list-style:none;margin:0;padding:0}
.im-watch li{display:grid;grid-template-columns:22px minmax(0,1fr);gap:8px;padding:9px 0;border-bottom:1px solid var(--border)}
.im-watch li:last-child{border-bottom:0}
.im-watch .ic{color:var(--bad);font-weight:700;font-size:15px;line-height:1.3}
.im-watch .t{font-size:13.5px;color:var(--text-1);overflow-wrap:anywhere}.im-watch .t b{font-weight:650}
.im-watch .nx{margin:3px 0 0;font-size:12.5px;color:var(--text-2);line-height:1.5}
details.im-tbl,details.im-how{margin-top:10px}
details.im-tbl summary,details.im-how summary{cursor:pointer;font-size:13px;color:var(--accent-text);font-weight:600}
details.im-how p{margin:6px 0 0;font-size:12.5px;color:var(--text-2);line-height:1.6}
.im-t td,.im-t th{font-variant-numeric:tabular-nums}.im-t td.r,.im-t th.r{text-align:right;white-space:nowrap}
.im-t td:first-child{min-width:190px}.im-t td.nw{white-space:nowrap}
.im-t th button{all:unset;cursor:pointer;color:inherit;font:inherit;letter-spacing:inherit;text-transform:inherit}
.im-t th button:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.im-t th[aria-sort="ascending"] button::after{content:" ▲"}.im-t th[aria-sort="descending"] button::after{content:" ▼"}
#imTip{position:fixed;z-index:60;pointer-events:none;background:var(--surface-1);color:var(--text-1);border:1px solid var(--border-strong);border-radius:8px;
  padding:7px 10px;font-size:12px;line-height:1.45;box-shadow:var(--shadow-overlay);max-width:320px}
#imTip b{font-size:13.5px}#imTip .s{color:var(--text-2)}
@media (max-width:900px){.im-chips{grid-template-columns:1fr}}
@media (max-width:700px){.im-row,.im-go .im-row{grid-template-columns:minmax(0,1fr);row-gap:4px}.im-verdict .vt{font-size:19px}
  .im-prog .bar{width:90px}.im-wins .sep{margin:0 3px}}
/* IMPACT:CSS:END */
"""

JS = r"""
<!-- IMPACT:JS:START -->
<script id="impactData" type="application/json">__DATA__</script>
<script>
(function(){
  let D;try{D=JSON.parse(document.getElementById('impactData').textContent);}catch(e){return;}
  D=D||{};
  const MS=D.metrics||[],VS=D.versions||[],BV=VS[0]||{},AV=VS[VS.length-1]||{},MIN=D.min_days||14,ADAYS=AV.days||0,DET=new Set(D.detail||[]);
  const FLAT=3,WATCH=10,WEEKLY_OK=80,MATCH_DAYS=7;   // % treated as 'about the same' · watchlist threshold · weekly pass risk · weekday-matched from day 7
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en;
  const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const M=k=>MS.find(m=>m.key===k);
  const val=(m,id)=>((m&&m.values)||{})[id]||{};
  const bOf=m=>val(m,BV.id),aOf=m=>val(m,AV.id);
  const hasN=x=>!!x&&x.value!=null&&(x.n||0)>0;                      // n = 0 -> 'no data'
  const enough=(m,x)=>hasN(x)&&(x.n||0)>=(m.min_n||0);              // trust rule: below min_n no delta, no %, no colour
  // ONE number formatter for every text, label, tooltip and aria-label, keyed on the current language:
  // EN 6,255 · 1.78   VI 6 255 · 1,78 (thousands = narrow no-break space, so the page-wide VI number pass cannot flip it again)
  const loc=s=>T(s,s.replace(/,/g,' ').replace(/\./g,','));
  const fmt=x=>{if(x==null||!isFinite(x))return '–';const a=Math.abs(x);return loc(a>=1000?Math.round(x).toLocaleString('en-US'):a>=100?String(Math.round(x)):a>=10?x.toFixed(1).replace(/\.0$/,''):(x.toFixed(2).replace(/\.?0+$/,'')||'0'));};
  // percent rule, everywhere: whole percent when |x| >= 10, one decimal below that (0 stays 0)
  const pct=x=>{if(x==null||!isFinite(x))return '–';const r=Math.round(x*10)/10;return loc(Math.abs(r)>=10?String(Math.round(x)):r===0?'0':r.toFixed(1));};
  const sgn=x=>(x>0?'+':x<0?'−':'±')+fmt(Math.abs(x));
  const pctTxt=p=>p==null?'':(p>0?'+':p<0?'−':'±')+pct(Math.abs(p))+'%';
  const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const dfmt=(iso,time)=>{const d=new Date(iso);if(isNaN(d))return '–';const p=n=>String(n).padStart(2,'0'),t=time?' '+p(d.getUTCHours())+':'+p(d.getUTCMinutes()):'';
    return T(`${d.getUTCDate()} ${MON[d.getUTCMonth()]}`,`${p(d.getUTCDate())}/${p(d.getUTCMonth()+1)}`)+t;};
  const WD=()=>T('Mon Tue Wed Thu Fri Sat Sun','T2 T3 T4 T5 T6 T7 CN').split(' ');
  const dayTxt=d=>`${fmt(Math.round(d*10)/10)} ${d===1?T('day','ngày'):T('days','ngày')}`;
  const winTxt=v=>v===AV?`${dfmt(v.since,1)} → ${T('now','nay')} (${dayTxt(v.days||0)})`:`${dfmt(v.since,1)} → ${dfmt(v.until,1)} (${dayTxt(v.days||0)})`;
  const UNIT={'GPU-h':['GPU hours','giờ GPU'],'GPU-min':['GPU minutes','phút GPU'],'job-min':['runner minutes','phút máy chạy'],'min':['min','phút'],'builds':['builds','build'],'workloads':['workloads','workload'],'%':['%','%']};
  const PERDAY=new Set(['gpu_h_day','gpu_h_day_pr','gpu_h_day_wd','draft_gpu_unit','draft_gpu_mp','retry_waste_gpu','mp_gpu_pr','after_draft','gha_draft_min','gha_ready_min','cpu_after_fail','heavy_day','smoke_day','dev_tested']);
  const un=m=>T(...(UNIT[m.unit]||[m.unit,m.unit]))+(PERDAY.has(m.key)?T(' a day',' mỗi ngày'):m.key==='gpu_h_per_push'?T(' per push',' mỗi lần push'):'');
  const nv=(m,x)=>x==null?'–':m.unit==='%'?pct(x):fmt(x);                       // number only (table cells: the unit is in its own column)
  const vu=(m,x)=>x==null?'–':m.unit==='%'?pct(x)+'%':`${fmt(x)} ${un(m)}`;
  const sgnU=(m,d)=>m.unit==='%'?(d>0?'+':d<0?'−':'±')+pct(Math.abs(d)):sgn(d);
  const du=(m,d)=>m.unit==='%'?`${sgnU(m,d)} ${T('points','điểm')}`:`${sgn(d)} ${un(m)}`;
  const runs=n=>`${fmt(n||0)} ${T('runs','lượt chạy')}`;
  const fewTxt=(m,x)=>T(`only ${fmt(x.n||0)} runs, need ${fmt(m.min_n)}`,`chỉ ${fmt(x.n||0)} lượt chạy, cần ${fmt(m.min_n)}`);

  // plain names + hover definitions (spec: no p50 / p90 / N / MP / v0 / v1 jargon)
  const PLAIN={
    gpu_h_day:[['GPU hours per day','Giờ GPU mỗi ngày'],['All GPU time of PR builds and post-merge test builds (k3-unit-tests, k3-multiprocess), without the weekly full build. GPU hours = run minutes × GPUs ÷ 60, divided by the days of the window.','Toàn bộ thời gian GPU của build PR và build test sau merge (k3-unit-tests, k3-multiprocess), không tính weekly full build. Giờ GPU = số phút chạy × số GPU ÷ 60, chia cho số ngày của cửa sổ.']],
    gpu_h_day_wd:[['GPU hours per day, same weekdays','Giờ GPU mỗi ngày, cùng ngày trong tuần'],['Before is re-weighted to the weekdays the after window covers, so busy weekdays are compared with busy weekdays.','Số trước được tính lại theo đúng các ngày trong tuần mà cửa sổ sau có, để ngày bận so với ngày bận.']],
    gpu_h_per_push:[['GPU hours per PR push','Giờ GPU mỗi lần push PR'],['PR GPU time divided by the pushed commits that started a GPU build.','Thời gian GPU của PR chia cho số commit được push có chạy build GPU.']],
    retry_waste_gpu:[['GPU hours per day on retries that failed again','Giờ GPU mỗi ngày cho lần chạy lại vẫn lỗi'],['A failed PR GPU job is retried; when the retry fails too, its GPU time is counted here.','Job GPU của PR bị lỗi được chạy lại; nếu lần chạy lại cũng lỗi, thời gian GPU của nó được tính ở đây.']],
    gpu_queue_p50:[['Typical wait for a GPU','Thời gian chờ GPU thường gặp'],['Typical wait: half of PR GPU jobs wait less than this.','Thời gian chờ thường gặp: một nửa số job GPU của PR chờ ít hơn mức này.']],
    l12_done_p50:[['Typical time from push to all checks green','Thời gian thường gặp từ lúc push đến khi mọi check xanh'],['From a PR push until the lint gate and the tests (GitHub Actions) are all green; half of pushes are faster than this.','Từ lúc push PR đến khi lint gate và test (GitHub Actions) đều xanh; một nửa số lần push nhanh hơn mức này.']],
    repeat_rate:[['Retries that failed again','Lần chạy lại vẫn lỗi'],['Share of PR GPU job attempts whose retry failed too: a real failure or a broken runner, not a flaky test.','Tỉ lệ lượt job GPU của PR mà lần chạy lại cũng lỗi: lỗi thật hoặc máy chạy hỏng, không phải test chập chờn.']],
    weekly_pass:[['Weekly full build runs that passed','Lượt weekly full build đạt'],['The weekly full build (#6854) runs every heavy test with a strict pass gate; it is now the only GPU check after merge. Under 80% passing counts as a risk.','Weekly full build (#6854) chạy mọi test nặng với cổng đạt nghiêm ngặt; giờ đây nó là kiểm tra GPU duy nhất sau merge. Dưới 80% lượt đạt được tính là rủi ro.']],
    weekly_mp_fail:[['Heavy multiprocess workloads failing in the weekly build','Workload multiprocess nặng bị lỗi trong weekly build'],['Most PRs no longer run the heavy workloads (#6731); the weekly full build is where a break shows up.','Phần lớn PR không còn chạy workload nặng (#6731); weekly full build là nơi lỗi lộ ra.']]};
  const P50=()=>T('typical (half are faster)','thường gặp (một nửa nhanh hơn)'),P90=()=>T('slow case (9 in 10 are faster)','trường hợp chậm (9/10 nhanh hơn)');
  // collector labels -> plain words (same words in EN and VI); a term that has to stay gets a hover definition (TERMDEF)
  const WORDS=[[/k3-multiprocess-\*/g,'multiprocess test jobs','job test multiprocess','mp'],[/k3-multiprocess-test \(heavy\)/g,'heavy multiprocess test','test multiprocess nặng','mp'],
    [/k3-multiprocess-smoke/g,'quick multiprocess test','test multiprocess nhanh','mp'],[/ within 3 min of a convert-to-draft/g,' within 3 min of the PR being moved back to draft',null,'draft'],
    [/convert-to-draft/g,'PR moved back to draft','PR chuyển về nháp','draft'],[/GPU-hours/g,'GPU hours',null],[/GPU-min\b/g,'GPU minutes',null],[/Runner-min\b/g,'Runner minutes',null,'runner'],[/runner-min\b/g,'runner minutes',null,'runner'],
    [/^GPU-giờ/,null,'Giờ GPU'],[/GPU-giờ/g,null,'giờ GPU'],[/^GPU-phút/,null,'Phút GPU'],[/GPU-phút/g,null,'phút GPU'],[/[Pp]hút runner/g,null,'phút máy chạy','runner'],[/^phút máy chạy/,null,'Phút máy chạy'],
    [/Retry vẫn lỗi/g,null,'Chạy lại vẫn lỗi'],[/các lần retry/g,null,'các lần chạy lại'],[/bị retry/g,null,'bị chạy lại'],[/pass khi retry/g,null,'đạt khi chạy lại'],[/\bretry\b/g,null,'chạy lại'],
    [/^Run /,null,'Lượt '],[/\bMP\b/g,'multiprocess','multiprocess'],[/k3-unit-tests/g,'k3-unit-tests','k3-unit-tests','unit']];
  const TERMDEF={mp:['Multiprocess test jobs: the Buildkite GPU jobs k3-multiprocess-test (heavy tier) and k3-multiprocess-smoke (quick tier) that run several processes together.','Job test multiprocess: các job GPU Buildkite k3-multiprocess-test (tầng nặng) và k3-multiprocess-smoke (tầng nhanh) chạy nhiều tiến trình cùng lúc.'],
    draft:['PR moved back to draft: the author turned a ready PR back into a draft (GitHub "convert to draft").','PR chuyển về nháp: tác giả đưa PR đang ready về lại trạng thái draft (nút "convert to draft" của GitHub).'],
    runner:['Runner minutes: minutes of GitHub Actions machines (runners) spent on the jobs, summed over jobs.','Phút máy chạy: số phút máy GitHub Actions (runner) dùng cho các job, cộng qua mọi job.'],
    unit:['k3-unit-tests: the Buildkite GPU job that runs the unit tests of a PR.','k3-unit-tests: job GPU Buildkite chạy unit test của PR.']};
  const plainWords=s=>{const vi=T(0,1),used=new Set();WORDS.forEach(([re,en,v,d])=>{const to=vi?v:en;if(to==null)return;re.lastIndex=0;if(re.test(s)){re.lastIndex=0;s=s.replace(re,to);if(d)used.add(d);}});return [s,[...used]];};
  const nameOf=m=>{if(PLAIN[m.key])return T(...PLAIN[m.key][0]);let s=T((m.label||[])[0]||m.key,(m.label||[])[1]||m.key);
    return plainWords(s.replace(/ · p50$/,' · '+P50()).replace(/ · p90$/,' · '+P90()))[0];};
  const termsOf=m=>PLAIN[m.key]?[]:plainWords(T((m.label||[])[0]||'',(m.label||[])[1]||''))[1].map(d=>T(...TERMDEF[d]));
  const defOf=m=>[PLAIN[m.key]?T(...PLAIN[m.key][1]):/p50$/.test(m.key)?T('Typical: half of the runs are faster than this.','Thường gặp: một nửa số lượt chạy nhanh hơn mức này.'):/p90$/.test(m.key)?T('Slow case: 9 in 10 runs are faster than this.','Trường hợp chậm: 9/10 lượt chạy nhanh hơn mức này.'):'',...termsOf(m)].filter(Boolean).join('\n');
  const dirTxt=m=>m.better==='down'?T('↓ lower is better','↓ thấp hơn là tốt hơn'):m.better==='up'?T('↑ higher is better','↑ cao hơn là tốt hơn'):T('for context, no better / worse','để tham khảo, không có tốt / tệ');

  // change computed here from the values (the collector keeps d_base_pct = null under min_days); never below min_n
  function change(m){const a=aOf(m),b=bOf(m);if(m.after_only||!enough(m,a)||!enough(m,b))return null;
    const d=a.value-b.value,p=b.value?100*d/b.value:null;let dir=null;
    if(m.better!=='info')dir=(p!=null?Math.abs(p)<FLAT:Math.abs(d)<1e-9)?'same':((m.better==='down')===(d<0)?'better':'worse');
    return {d,p,dir};}
  const RISK={weekly_pass:v=>v<WEEKLY_OK,weekly_mp_fail:v=>v>0};
  function judge(m){const a=aOf(m);if(!hasN(a))return 'nodata';if(!enough(m,a))return 'few';
    if(RISK[m.key])return RISK[m.key](a.value)?'risk':'ok';const c=change(m);
    if(c&&m.key==='gpu_h_day'&&wdSplit())return 'unclear';   // weekday rule: plain and weekday-matched point in opposite directions
    return c?(c.dir||'info'):'new';}
  // weekday rule (general): after window < MATCH_DAYS and the weekday-matched change has the opposite sign of the plain change
  // -> 'unclear (weekday effect)', neutral, never better / worse. wdCmp() is also used to show both comparisons.
  function wdCmp(){const t=M('gpu_h_day'),w=weekdays();if(!t||!w||ADAYS>=MATCH_DAYS)return null;const a=aOf(t),b=bOf(t);
    if(!enough(t,a)||!enough(t,b)||!(w.before>0))return null;const d=a.value-b.value,dw=a.value-w.before;
    return {m:t,days:w.days,before:w.before,d,p:b.value?100*d/b.value:null,dw,pw:100*dw/w.before,split:(d>0&&dw<0)||(d<0&&dw>0)};}
  const wdSplit=()=>{const w=wdCmp();return !!(w&&w.split);};
  const GOOD=j=>j==='better'||j==='ok',BAD=j=>j==='worse'||j==='risk';
  const UNCLEAR=()=>`<span class="im-pill" data-pill="unclear"><span aria-hidden="true">? </span>${T('unclear (weekday effect)','chưa rõ (lệch ngày trong tuần)')}</span>`;
  const pill=j=>j==='unclear'?UNCLEAR():GOOD(j)?`<span class="im-pill good"><span aria-hidden="true">✓ </span>${j==='ok'?T('OK','ổn'):T('better','tốt hơn')}</span>`:
    BAD(j)?`<span class="im-pill bad"><span aria-hidden="true">${j==='risk'?'⚠':'✗'} </span>${j==='risk'?T('at risk','có rủi ro'):T('worse','tệ hơn')}</span>`:
    j==='same'?`<span class="im-pill"><span aria-hidden="true">≈ </span>${T('about the same','gần như không đổi')}</span>`:'';

  // weekday match: before re-weighted to the weekdays the after window covers (collector meta gpu_by_weekday)
  function weekdays(){const W=D.gpu_by_weekday||{},b=W[BV.id]||{},a=W[AV.id]||{};const ks=Object.keys(a).filter(k=>a[k][1]>0&&b[k]&&b[k][1]>0);
    if(!ks.length)return null;const wa=ks.reduce((s,k)=>s+a[k][1],0);
    return {days:ks.map(k=>WD()[+k]),before:ks.reduce((s,k)=>s+(b[k][0]/b[k][1])*a[k][1],0)/wa};}
  function wdMetric(){const t=M('gpu_h_day'),w=weekdays();if(!t||!w)return null;const b=bOf(t),a=aOf(t);
    return {key:'gpu_h_day_wd',unit:'GPU-h',better:'down',min_n:t.min_n,family:'gpu',values:{[BV.id]:{value:Math.round(w.before*10)/10,n:b.n},[AV.id]:{value:a.value,n:a.n}}};}

  const GROUPS=[['cost',['Cost','Chi phí'],['gpu_h_day','gpu_h_per_push','retry_waste_gpu']],['speed',['Speed','Tốc độ'],['gpu_queue_p50','l12_done_p50']],
    ['safety',['Safety','An toàn'],['repeat_rate','weekly_pass','weekly_mp_fail']]];
  const FAMG={gpu:'cost',mp:'speed',gha:'speed',rel:'safety'};
  function groups(){const used=new Set(GROUPS.flatMap(g=>g[2]));const G=GROUPS.map(([id,n,ks])=>[id,n,ks.map(M).filter(Boolean)]);
    MS.filter(m=>m.headline&&!used.has(m.key)).forEach(m=>{const g=G.find(x=>x[0]===(FAMG[m.family]||'cost'));g[2].push(m);});   // a new headline metric still shows
    if(ADAYS>=MATCH_DAYS){const w=wdMetric();if(w)G[0][2].splice(1,0,w);}
    return G;}
  const HEAD=()=>groups().flatMap(g=>g[2]).filter(m=>m.key!=='gpu_h_day_wd');
  const proven=()=>ADAYS>=MIN&&HEAD().every(m=>enough(m,aOf(m)));

  // ---------- 1: windows + verdict strip
  const CHIP={cost:[['Cost','Chi phí'],['gpu_h_day','gpu_h_per_push'],{better:['▼','down','giảm'],worse:['▲','up','tăng']}],
    speed:[['Speed','Tốc độ'],['gpu_queue_p50','l12_done_p50'],{better:['▼','wait shorter','chờ ngắn hơn'],worse:['▲','wait longer','chờ lâu hơn']}],
    safety:[['Safety','An toàn'],['repeat_rate','weekly_pass','weekly_mp_fail'],{better:['✓','OK','ổn'],worse:['⚠','at risk','có rủi ro']}]};
  const SHORT={gpu_h_day:['GPU hours a day','giờ GPU mỗi ngày'],gpu_h_per_push:['per push','mỗi lần push'],gpu_queue_p50:['typical GPU wait','chờ GPU thường gặp'],l12_done_p50:['push → all green','push → xanh hết'],
    repeat_rate:['retries failing again','chạy lại vẫn lỗi'],weekly_pass:['weekly full build','weekly full build'],weekly_mp_fail:['heavy workloads in weekly','workload nặng trong weekly']};
  function evidence(m){const a=aOf(m),j=judge(m),c=change(m);
    if(j==='nodata')return T('no data','không có dữ liệu');if(j==='few')return fewTxt(m,a);
    if(m.key==='weekly_pass'){const w=(D.weekly||{})[AV.id]||{};return w.finished?T(`${w.passed} of ${w.finished} runs passed`,`${w.passed}/${w.finished} lượt đạt`):vu(m,a.value);}
    if(m.key==='weekly_mp_fail')return a.value?T(`${fmt(a.value)} failing`,`${fmt(a.value)} bị lỗi`):T('none failing','không có lỗi');
    const w=m.key==='gpu_h_day'&&c?wdCmp():null;   // short after window: show the plain AND the weekday-matched comparison
    if(w)return `${T('all days','mọi ngày')} ${sgn(c.d)}${c.p!=null?` (${pctTxt(c.p)})`:''} · ${T('same weekdays','cùng ngày trong tuần')} ${sgn(w.dw)} (${pctTxt(w.pw)})`;
    return c?`${du(m,c.d)}${c.p!=null?` (${pctTxt(c.p)})`:''}`:vu(m,a.value);}
  function chipState(id){const js=CHIP[id][1].map(M).filter(Boolean).map(judge);const g=js.some(GOOD),b=js.some(BAD);
    if(js.includes('unclear'))return 'unclear';   // the weekday rule wins: neutral, never better / worse
    return id==='safety'?(b?'worse':g?'better':js.includes('same')?'same':'few'):(g&&b?'mixed':b?'worse':g?'better':js.includes('same')?'same':'few');}
  function chip(id){const [nm,ks,W]=CHIP[id],st=chipState(id),ms=ks.map(M).filter(Boolean);
    const w=W[st]||(st==='unclear'?['?','unclear (weekday effect)','chưa rõ (lệch ngày trong tuần)']:st==='mixed'?['◆','mixed','lẫn lộn']:st==='same'?['≈','about the same','gần như không đổi']:['…','too few runs to judge','quá ít lượt chạy để đánh giá']);
    const word=st==='better'?T('better','tốt hơn'):st==='worse'?T('worse','tệ hơn'):'';
    const tip=[T(...nm),...ms.map(m=>`${nameOf(m)}: ${evidence(m)}`),`${T('After','Sau')}: ${winTxt(AV)}`].join('\n');
    return `<div class="im-chip ${st==='better'?'good':st==='worse'?'bad':''}" data-chip="${id}" data-state="${st}" tabindex="0" data-tip="${esc(tip)}">`+
      `<div class="h">${T(...nm)} <span class="st"><span aria-hidden="true">${w[0]}</span> ${T(w[1],w[2])}${word&&!(id==='safety'&&st==='better')?` · ${word}`:''}</span></div>`+
      `<ul>${ms.map(m=>`<li>${esc(T(...(SHORT[m.key]||[nameOf(m),nameOf(m)])))}: ${esc(evidence(m))}</li>`).join('')}</ul></div>`;}
  function verdict(){const pv=proven(),cs=['cost','speed','safety'].map(chipState);
    const st=!pv?'early':cs.includes('worse')||cs.includes('mixed')?'worse':'better';
    const title=st==='early'?['◔','Too early to prove','Còn quá sớm để kết luận']:st==='worse'?['⚠','Looks worse','Có vẻ tệ hơn']:['✓','Looks better','Có vẻ tốt hơn'];
    const H=HEAD(),k=H.filter(m=>enough(m,aOf(m))).length,dn=Math.min(MIN,Math.max(1,Math.floor(ADAYS))),pr=Math.min(100,100*ADAYS/MIN);
    const at=AV.since?dfmt(new Date(Date.parse(AV.since)+MIN*864e5).toISOString()):'–';
    const why=pv?T(`Proven: ${dayTxt(ADAYS)} after the change and every key number has enough runs.`,`Đã đủ cơ sở: ${dayTxt(ADAYS)} sau thay đổi và mọi con số chính đều đủ lượt chạy.`):
      T(`Proof needs ${MIN} days after the change and enough runs for every key number. So far: ${dayTxt(ADAYS)} of ${MIN}; ${k} of ${H.length} key numbers have enough runs. Earliest proof: ${at}.`,
        `Để kết luận cần ${MIN} ngày sau thay đổi và đủ lượt chạy cho mọi con số chính. Hiện có: ${fmt(Math.round(ADAYS*10)/10)}/${MIN} ngày; ${k}/${H.length} con số chính đủ lượt chạy. Sớm nhất có kết luận: ${at}.`);
    return `<div class="im-verdict" data-im="verdict" data-state="${st}"><div class="top"><span class="vt"><span class="ic" aria-hidden="true">${title[0]}</span>${T(title[1],title[2])}</span>`+
      `<span class="im-prog" data-im="progress" role="meter" aria-valuemin="0" aria-valuemax="${MIN}" aria-valuenow="${Math.round(Math.min(ADAYS,MIN)*10)/10}" aria-label="${esc(T('days measured after the change','số ngày đã đo sau thay đổi'))}">`+
      `<span class="bar"><i style="width:${pr.toFixed(0)}%"></i></span>${ADAYS>=MIN?T(`${MIN}+ days`,`đủ ${MIN} ngày`):T(`Day ${dn} of ${MIN}`,`Ngày ${dn}/${MIN}`)}</span></div>`+
      `<p class="why">${esc(why)}</p>${pv?'':`<p class="im-sofar-h">${T('So far (not proven yet):','Tạm tính (chưa chắc chắn):')}</p>`}<div class="im-chips">${['cost','speed','safety'].map(chip).join('')}</div></div>`;}
  const PRN={6730:['tiered pre-review CI','CI theo tầng trước review'],6731:['multiprocess tests split into a quick and a heavy tier','tách test multiprocess thành tầng nhanh và tầng nặng'],6854:['weekly full build','weekly full build']};
  function windows(){const burn=(D.burn_in_hours||{})[AV.id],S='<span class="sep" aria-hidden="true">·</span>';
    const gap=BV.until&&AV.since&&BV.until<AV.since?`${S}<span class="im-sw" data-im="switch">${T('not counted','không tính')} ${dfmt(BV.until,1)} → ${dfmt(AV.since,1)} (${T('merges','merge')}${burn?` + ${burn} ${T('h settling','giờ chờ ổn định')}`:''})</span>`:'';
    const prs=(AV.prs||[]).map(n=>`<a href="https://github.com/LMCache/LMCache/pull/${esc(n)}" target="_blank" rel="noopener">#${esc(n)}</a> ${esc(T(...(PRN[n]||['',''])))}`).join(' · ');
    // the three windows on ONE line: before · not counted · after (+ when the data was collected)
    let h=`<p class="im-wins" data-im="windows"><span data-win="before"><span class="im-key b" aria-hidden="true"></span><b>${T('Before','Trước')}</b> ${dfmt(BV.since)} → ${dfmt(BV.until,1)} (${dayTxt(BV.days||0)})</span>${gap}${S}`+
      `<span data-win="after"><span class="im-key a" aria-hidden="true"></span><b>${T('After','Sau')}</b> ${dfmt(AV.since,1)} → ${T('now','nay')} (${dayTxt(ADAYS)})</span>${S}<span class="im-sw">${T('updated','cập nhật')} ${dfmt(D.collected_at||AV.until,1)} UTC</span></p>`+
      (prs?`<p class="im-chg-prs">${T('Changes measured','Thay đổi được đo')}: ${prs}</p>`:'');
    // weekday warning: ONE sentence
    if(ADAYS<MATCH_DAYS){const w=weekdays(),t=M('gpu_h_day'),b=t&&hasN(bOf(t))?bOf(t).value:null,dl=w?` (${w.days.join(', ')}, UTC)`:'';
      h+=`<div class="im-wd" data-im="weekday"><span class="ic" aria-hidden="true">⚠</span><span>`+
        (w&&b!=null?T(`Only ${dayTxt(ADAYS)} after${dl}, against a ${fmt(BV.days||0)}-day average with weekends: on the same weekdays before used ${fmt(w.before)} GPU hours a day, not ${fmt(b)}, so read Cost with care until day ${MATCH_DAYS}.`,
            `Mới có ${dayTxt(ADAYS)} sau thay đổi${dl}, so với trung bình ${dayTxt(BV.days||0)} có cả cuối tuần: vào cùng các ngày đó trước đây dùng ${fmt(w.before)} giờ GPU mỗi ngày chứ không phải ${fmt(b)}, nên đọc mục Chi phí thận trọng đến ngày ${MATCH_DAYS}.`):
          T(`Only ${dayTxt(ADAYS)} after${dl}, against a ${fmt(BV.days||0)}-day average with weekends, so read Cost with care until day ${MATCH_DAYS}.`,
            `Mới có ${dayTxt(ADAYS)} sau thay đổi${dl}, so với trung bình ${dayTxt(BV.days||0)} có cả cuối tuần, nên đọc mục Chi phí thận trọng đến ngày ${MATCH_DAYS}.`))+`</span></div>`;}
    return h;}

  // ---------- 2: before -> after dumbbells, one axis per row
  const niceMax=x=>{if(!(x>0))return 1;const e=Math.pow(10,Math.floor(Math.log10(x)));for(const f of [1,1.2,1.5,2,2.5,3,4,5,6,8,10])if(f*e>=x*1.1)return f*e;return 10*e;};
  function dotTip(m,which){const x=which==='b'?bOf(m):aOf(m),v=which==='b'?BV:AV;
    return [nameOf(m),`${which==='b'?T('Before','Trước'):T('After','Sau')}: ${vu(m,x.value)}`,winTxt(v),`${runs(x.n)} · ${T('need','cần')} ${fmt(m.min_n)}`,
      which==='a'&&hasN(x)&&!enough(m,x)?T('too few runs to judge','quá ít lượt chạy để đánh giá'):''].filter(Boolean).join('\n');}
  function dumbbell(m){const a=aOf(m),b=bOf(m),ha=hasN(a),hb=!m.after_only&&hasN(b),ok=enough(m,a);
    const top=Math.max(hb?b.value:0,ha?a.value:0),mx=m.unit==='%'&&(top>50||m.better==='up')?100:m.unit==='workloads'?Math.max(5,niceMax(top)):niceMax(top);
    const X=v=>4+88*Math.max(0,Math.min(1,v/mx));
    let h=`<div class="im-db" role="group" aria-label="${esc(nameOf(m))}"><span class="ax"></span><span class="tk" style="left:4%">0</span><span class="tk" style="left:92%">${esc(m.unit==='%'?pct(mx)+'%':fmt(mx))}</span>`;
    if(!ha&&!hb)return h+`</div>`;
    const xb=hb?X(b.value):null,xa=ha?X(a.value):null;
    if(hb&&ha)h+=`<span class="ln" style="left:${Math.min(xa,xb)}%;width:${Math.abs(xa-xb)}%"></span>`;
    const close=hb&&ha&&Math.abs(xa-xb)<16,lo=close?(a.value<=b.value?'a':'b'):null;
    const lab=(w,x,v)=>{const c=close?(w===lo?' l':' r'):'';const p=c?x:Math.max(7,Math.min(93,x));return `<span class="im-vl ${w}${c}" style="left:${p}%">${esc(m.unit==='%'?pct(v)+'%':fmt(v))}</span>`;};
    if(hb)h+=lab('b',xb,b.value)+`<button type="button" class="im-dot b" style="left:${xb}%" data-tip="${esc(dotTip(m,'b'))}" aria-label="${esc(dotTip(m,'b').replace(/\n/g,' · '))}"></button>`;
    if(ha)h+=lab('a',xa,a.value)+`<button type="button" class="im-dot a${ok?'':' hollow'}" style="left:${xa}%" data-tip="${esc(dotTip(m,'a'))}" aria-label="${esc(dotTip(m,'a').replace(/\n/g,' · '))}"></button>`;
    return h+`</div>`;}
  function sample(m){const a=aOf(m),n=a.n||0,need=m.min_n||0,p=need?Math.min(100,100*n/need):100;
    if(!hasN(a))return `<div class="im-n" data-im="sample"><span class="bar"><i style="width:0%"></i></span>${T('no data','không có dữ liệu')}</div>`;
    return `<div class="im-n" data-im="sample" role="meter" aria-valuemin="0" aria-valuemax="${need}" aria-valuenow="${Math.min(n,need)}" aria-label="${esc(T('sample size','cỡ mẫu'))}"><span class="bar"><i style="width:${p.toFixed(0)}%"></i></span>`+
      (enough(m,a)?`${T('sample','mẫu')}: ${runs(n)} · ${T('need','cần')} ${fmt(need)} <span aria-hidden="true">✓</span>`:esc(fewTxt(m,a)))+`</div>`;}
  function chgCell(m){const j=judge(m),c=change(m),a=aOf(m),early=ADAYS<MIN?`<span class="im-sofar">${T('so far','tạm tính')}</span>`:'';
    if(j==='nodata')return `<div class="im-chg" data-j="nodata"><span class="mute">${T('no data','không có dữ liệu')}</span></div>`;
    if(j==='few')return `<div class="im-chg" data-j="few"><span class="mute">${T('too few runs to judge','quá ít lượt chạy để đánh giá')}</span></div>`;
    if(j==='risk'||j==='ok')return `<div class="im-chg" data-j="${j}"><b>${esc(evidence(m))}</b>${early}<br>${pill(j)}</div>`;
    if(!c)return `<div class="im-chg" data-j="${j}"><span class="mute">${m.after_only?T('new: nothing to compare with','mới: không có số trước để so'):''}</span></div>`;
    if(j==='unclear'){const w=wdCmp();return `<div class="im-chg" data-j="unclear"><b>${esc(sgn(c.d))}</b>${c.p!=null?`<small>${esc(pctTxt(c.p))}</small>`:''} <span class="mute">${T('all days','mọi ngày')}</span><br>`+
      `<b>${esc(sgn(w.dw))}</b><small>${esc(pctTxt(w.pw))}</small> <span class="mute">${T('same weekdays','cùng ngày trong tuần')}</span>${early}<br>${pill(j)}</div>`;}
    return `<div class="im-chg" data-j="${j}"><b>${esc(du(m,c.d))}</b>${c.p!=null?`<small>${esc(pctTxt(c.p))}</small>`:''}${early}<br>${pill(c.dir)}</div>`;}
  function row(m){const a=aOf(m),d=defOf(m);
    return `<div class="im-row" data-key="${esc(m.key)}" data-enough="${enough(m,a)?1:0}"><div class="im-lab">${d?`<span class="im-def" tabindex="0" data-tip="${esc(nameOf(m)+'\n'+d)}">${esc(nameOf(m))}</span>`:esc(nameOf(m))}`+
      `<span class="u">${esc(m.unit==='%'?T('percent','phần trăm'):un(m))} · ${esc(dirTxt(m))}</span>${m.after_only?`<span class="im-hint">${T('new with the change: no before','mới có từ thay đổi: không có số trước')}</span>`:''}</div>`+
      `<div>${dumbbell(m)}${sample(m)}</div>${chgCell(m)}</div>`;}
  function beforeAfter(){
    return `<div class="im-legend" data-im="legend"><span><span class="im-key b" aria-hidden="true"></span>${T('Before','Trước')} (${fmt(BV.days)} ${T('days','ngày')})</span><span><span class="im-key a" aria-hidden="true"></span>${T('After','Sau')} (${dayTxt(ADAYS)})</span>`+
      `<span><span class="im-key h" aria-hidden="true"></span>${T('After, too few runs to judge','Sau, quá ít lượt chạy để đánh giá')}</span><span>${T('Each row has its own scale, starting at 0.','Mỗi dòng có thang đo riêng, bắt đầu từ 0.')}</span></div>`+
      groups().map(([id,n,ms])=>ms.length?`<div class="im-grp" data-grp="${id}">${T(...n)}</div><div class="im-rows">${ms.map(row).join('')}</div>`:'').join('');}

  // ---------- 3: where did the GPU time go (before / after per part, the sum written out)
  // A part with no data after (n = 0) is NOT a zero: it gets a hatched 'no data' mark, it is left out of the sum, and the chart says
  // how much of the before total it was. The sum then closes on 'before total − unmeasured part' (+ an 'unexplained' term if any).
  function gpuParts(){const tot=M('gpu_h_day'),pr=M('gpu_h_day_pr'),du_=M('draft_gpu_unit'),dm=M('draft_gpu_mp'),rw=M('retry_waste_gpu'),dev=M('dev_tested');if(!tot||!pr)return null;
    const V=(m,id)=>{const x=val(m,id);return hasN(x)?x.value:null;};
    const at=id=>{const t=V(tot,id),p=V(pr,id),dr=du_&&dm&&(V(du_,id)!=null||V(dm,id)!=null)?(V(du_,id)||0)+(V(dm,id)||0):null,r=V(rw,id);
      const postN=!dev||hasN(val(dev,id));   // post-merge part = total − PR; measured only when post-merge builds ran (n > 0)
      return {total:t,post:postN&&t!=null&&p!=null?t-p:null,draft:dr,retry:r,ready:p!=null&&dr!=null&&r!=null?p-dr-r:null};};
    return {b:at(BV.id),a:at(AV.id)};}
  const PARTS=[['ready',['Ready PR runs','Chạy trên PR ready'],['ready PR runs','chạy trên PR ready'],1],['draft',['Draft PR runs','Chạy trên PR draft'],['drafts','PR draft'],0],
    ['retry',['GPU on retries that failed again','GPU cho lần chạy lại vẫn lỗi'],['retries that failed again','lần chạy lại vẫn lỗi'],0],['post',['Post-merge test builds','Build test sau merge'],['post-merge test builds','build test sau merge'],0]];
  function gpuGo(){const P=gpuParts();if(!P)return `<p class="dk-mute">${T('No GPU data yet.','Chưa có dữ liệu GPU.')}</p>`;
    const b=P.b,a=P.a,TOT=M('gpu_h_day'),GH=T('GPU hours a day','giờ GPU mỗi ngày');
    const wk=M('weekly_gpu'),wa=wk?aOf(wk):{},wday=hasN(wa)&&ADAYS?wa.value/ADAYS:null,perRun=hasN(wa)?wa.value/wa.n:null;
    const n_ok=enough(TOT,aOf(TOT)),split=wdSplit();
    // unmeasured parts: a value before, no data after
    const gapK=PARTS.map(x=>x[0]).filter(k=>b[k]!=null&&a[k]==null),gapV=gapK.reduce((s,k)=>s+b[k],0),bc=b.total!=null?b.total-gapV:null;
    const pn=k=>T(...PARTS.find(x=>x[0]===k)[2]),gapNames=gapK.map(pn).join(T(' and ',' và '));
    const ROWS=[['total',['GPU hours a day, all builds (without weekly build)','Giờ GPU mỗi ngày, mọi build (không tính weekly build)'],0],...PARTS.map(([k,n,,ap])=>[k,n,ap])];
    const vals=[...ROWS.flatMap(([k])=>[b[k],a[k]]),wday].filter(x=>x!=null),mx=niceMax(Math.max(...vals,1)),X=v=>Math.max(0,86*v/mx);
    const NOD=()=>T('no data','chưa có dữ liệu');
    const bars=(k,bv,av,lb)=>{const one=(w,v)=>{
        if(v==null){if(w==='a'&&gapK.includes(k))return `<div class="r" data-nodata="1"><span class="nd im-hatch" role="img" aria-label="${esc(lb+': '+NOD())}" tabindex="0" data-tip="${esc([lb,`${T('After','Sau')}: ${NOD()}`,T(`Before: ${fmt(bv)} ${GH}, left out of the sum`,`Trước: ${fmt(bv)} ${GH}, không tính vào tổng`),winTxt(AV)].join('\n'))}"></span><span class="na">${NOD()} · ${T('cannot be compared yet','chưa so sánh được')}</span></div>`;
          return `<div class="r"><span class="na">${w==='b'?T('not counted before','trước đây không tính'):NOD()}</span></div>`;}
        const tip=[lb,`${w==='b'?T('Before','Trước'):T('After','Sau')}: ${fmt(v)} ${GH}`,winTxt(w==='b'?BV:AV)];
        // the before total shows the unmeasured share as a hatched end segment: 'this much of it cannot be compared yet'
        const cut=k==='total'&&w==='b'&&gapV>0?gapV:0,sol=v-cut;
        let h=`<div class="r"><button type="button" class="im-bar ${w}" style="width:${X(sol).toFixed(2)}%" data-tip="${esc((cut?[...tip,T(`of which ${fmt(sol)} can be compared`,`trong đó ${fmt(sol)} so sánh được`)]:tip).join('\n'))}" aria-label="${esc(`${lb}, ${w==='b'?T('before','trước'):T('after','sau')}: ${fmt(v)}`)}"></button>`;
        if(cut)h+=`<span class="im-bar gap im-hatch" data-im="gap-seg" tabindex="0" style="left:calc(${X(sol).toFixed(2)}% + 2px);width:max(4px,calc(${X(cut).toFixed(2)}% - 2px))" data-tip="${esc([gapNames,T(`${fmt(cut)} of the ${fmt(v)} before (${pct(100*cut/v)}%)`,`${fmt(cut)} trên ${fmt(v)} trước đây (${pct(100*cut/v)}%)`),T('no data after: left out of the comparison','chưa có dữ liệu ở cửa sổ sau: không đưa vào so sánh')].join('\n'))}" aria-label="${esc(T(`${gapNames}: ${fmt(cut)} of the before total, no data after`,`${gapNames}: ${fmt(cut)} của tổng trước, chưa có dữ liệu sau`))}"></span>`;
        return h+`<span class="v ${w}" style="left:calc(${X(v).toFixed(2)}% + ${cut?4:0}px)">${fmt(v)}</span></div>`;};
      return `<div class="im-bars">${one('b',bv)}${one('a',av)}</div>`;};
    const delta=(d,p,sub,neutral)=>{const c=neutral||Math.abs(d)<0.05?'':d>0?'im-up':'im-down';
      return `<b class="${c}"><span aria-hidden="true">${d>0.05?'▲ ':d<-0.05?'▼ ':''}</span>${sgn(d)}</b>${p!=null?`<small>${pctTxt(p)}</small>`:''}<br><span class="mute">${sub||(d>0.05?T('more GPU','thêm GPU'):d<-0.05?T('less GPU','bớt GPU'):T('no change','không đổi'))}</span>`;};
    const chg=(bv,av,k)=>{
      if(gapK.includes(k))return `<div class="im-chg" data-j="nodata"><span class="mute">${T('not in the sum','không tính vào tổng')}</span></div>`;
      if(bv==null||av==null)return `<div class="im-chg"><span class="mute">–</span></div>`;
      if(!n_ok)return `<div class="im-chg" data-j="few"><span class="mute">${T('too few runs to judge','quá ít lượt chạy để đánh giá')}</span></div>`;
      if(k==='total'&&gapV>0){const d=av-bc;return `<div class="im-chg" data-like="1">${delta(d,bc?100*d/bc:null,T(`like for like: ${fmt(bc)} → ${fmt(av)}`,`cùng phạm vi: ${fmt(bc)} → ${fmt(av)}`),split)}</div>`;}
      const d=av-bv;return `<div class="im-chg">${delta(d,bv>=1?100*d/bv:null,null,k==='total'&&split)}</div>`;};
    let h=`<p class="im-legend"><span><span class="im-key b" aria-hidden="true"></span>${T('Before','Trước')}</span><span><span class="im-key a" aria-hidden="true"></span>${T('After','Sau')}</span>`+
      (gapK.length?`<span><span class="im-key x im-hatch" aria-hidden="true"></span>${T('no data after: cannot be compared yet, left out of the sum','chưa có dữ liệu ở cửa sổ sau: chưa so sánh được, không tính vào tổng')}</span>`:'')+
      `<span>${T('GPU hours a day, one scale for all rows. ≈ = computed, see the notes.','Giờ GPU mỗi ngày, một thang đo chung cho mọi dòng. ≈ = số tính ra, xem ghi chú.')}</span></p><div class="im-go" data-im="gpu-go">`;
    ROWS.forEach(([k,n,approx])=>{const lb=(approx?'≈ ':'')+T(...n),gp=gapK.includes(k);
      const sub=k==='ready'?T('PR GPU − drafts − failed retries','GPU của PR − draft − chạy lại vẫn lỗi'):
        gp?T(`${fmt(b[k])} of the ${fmt(b.total)} GPU hours a day before (${pct(100*b[k]/b.total)}%)${k==='post'?': no post-merge build ran after the change yet':': no data after'}, so this part cannot be compared yet`,
             `${fmt(b[k])} trên ${fmt(b.total)} giờ GPU mỗi ngày trước đây (${pct(100*b[k]/b.total)}%)${k==='post'?': chưa có build sau merge nào chạy sau thay đổi':': chưa có dữ liệu sau'}, nên phần này chưa so sánh được`):
        k==='total'&&gapV>0?T(`hatched end: ${fmt(gapV)} with no data after (${gapNames})`,`phần gạch chéo: ${fmt(gapV)} chưa có dữ liệu sau (${gapNames})`):'';
      h+=`<div class="im-row${k==='total'?' tot':''}" data-part="${k}"${gp?' data-nodata="1"':''}><div class="im-lab">${esc(lb)}${sub?`<span class="u">${esc(sub)}</span>`:''}</div>${bars(k,b[k],a[k],lb)}${chg(b[k],a[k],k)}</div>`;});
    const wl='≈ '+T('Weekly full build (new, outside the daily total)','Weekly full build (mới, ngoài tổng mỗi ngày)');
    h+=`<div class="im-row" data-part="weekly"><div class="im-lab">${esc(wl)}<span class="u">${perRun!=null?T(`${fmt(wa.n)} runs in ${dayTxt(ADAYS)} · at one run a week ≈ ${fmt(perRun/7)} a day`,`${fmt(wa.n)} lượt trong ${dayTxt(ADAYS)} · nếu mỗi tuần một lượt ≈ ${fmt(perRun/7)} mỗi ngày`):''}</span></div>${bars('weekly',null,wday,wl)}<div class="im-chg"><span class="mute">${T('new: nothing to compare with','mới: không có số trước để so')}</span></div></div></div>`;
    // the sum written out: before total − unmeasured parts = comparable before; + change of each measured part (+ unexplained) = after total
    const meas=PARTS.filter(([k])=>!gapK.includes(k));
    const ok=b.total!=null&&a.total!=null&&PARTS.every(([k])=>b[k]!=null&&(a[k]!=null||gapK.includes(k)));
    if(ok){const dd=meas.map(([k])=>[k,pn(k),a[k]-b[k]]);let sum=bc+dd.reduce((s,x)=>s+x[2],0);const un_=a.total-sum;
      if(Math.abs(un_)>=0.05){dd.push(['unexplained',T('unexplained','chưa giải thích được'),un_]);sum+=un_;}
      // shown to one decimal; the computed part (≈ ready PR runs) takes the rounding, so the sum closes on the numbers as shown
      const r1=x=>Math.round(x*10)/10,f1=x=>loc(r1(x).toFixed(1)),bS=r1(b.total),gS=r1(gapV),cS=r1(bS-gS),aS=r1(a.total);
      const ddS=dd.map(([k,n,d])=>[k,n,r1(d)]),ri=ddS.findIndex(x=>x[0]==='ready');
      if(ri>=0)ddS[ri][2]=r1(aS-cS-ddS.reduce((s,x,i)=>i===ri?s:s+x[2],0));
      const term=([k,n,d])=>`<span data-term="${k}">${d<0?'−':'+'} ${f1(Math.abs(d))} ${esc(n)}</span>`;
      h+=`<p class="im-bridge" data-im="bridge" data-sum="${sum.toFixed(2)}" data-after="${a.total.toFixed(2)}" data-gap="${gapK.join(',')}" data-gapv="${gapV.toFixed(2)}" data-before="${b.total.toFixed(2)}"><b data-v="before">${f1(bS)}</b> ${T('before','trước')} `+
        (gapV>0?`<span class="gapt" data-term="gap">− ${f1(gS)} ${esc(gapNames)} (${T('no data after','chưa có dữ liệu sau')})</span> = <b data-v="comparable">${f1(cS)}</b> ${T('comparable','so sánh được')}; `:'')+
        ddS.map(term).join(' ')+` = <b data-v="after">${f1(aS)}</b> ${T('after','sau')} (${GH}, ${T('to one decimal','làm tròn một chữ số thập phân')})</p>`;
      const dC=a.total-bc,dD=a.draft-b.draft,dR=a.ready-b.ready,dRt=a.retry-b.retry,share=bc?100*b.draft/bc:0;
      const sm=M('smoke_day'),sg=M('gpu_per_smoke'),smA=sm&&sg&&enough(sm,aOf(sm))&&enough(sg,aOf(sg))?aOf(sm).value*aOf(sg).value:null;
      const wend=Object.keys(((D.gpu_by_weekday||{})[AV.id])||{}).some(k=>k==='5'||k==='6');
      const gapS=gapV>0?T(`${gapNames.charAt(0).toUpperCase()+gapNames.slice(1)} were ${fmt(gapV)} of the ${fmt(b.total)} GPU hours a day before (${pct(100*gapV/b.total)}%) but have no data after the change yet, so they are left out: like for like the total went from ${fmt(bc)} to ${fmt(a.total)} (${sgn(dC)}, ${pctTxt(bc?100*dC/bc:null)}). `,
          `${gapNames.charAt(0).toUpperCase()+gapNames.slice(1)} chiếm ${fmt(gapV)} trên ${fmt(b.total)} giờ GPU mỗi ngày trước đây (${pct(100*gapV/b.total)}%) nhưng chưa có dữ liệu sau thay đổi, nên không tính: cùng phạm vi, tổng: ${fmt(bc)} → ${fmt(a.total)} (${sgn(dC)}, ${pctTxt(bc?100*dC/bc:null)}). `):'';
      const smS=smA!=null?T(`; the new quick multiprocess tier alone adds about ${fmt(smA)} (${fmt(aOf(sm).value)} builds a day × ${fmt(aOf(sg).value)} GPU hours)`,`; riêng tầng multiprocess nhanh mới đã thêm khoảng ${fmt(smA)} (${fmt(aOf(sm).value)} build mỗi ngày × ${fmt(aOf(sg).value)} giờ GPU)`):'';
      const wdS=ADAYS<MATCH_DAYS&&!wend?T(', and the after window has no weekend yet (see the note at the top)',', và cửa sổ sau chưa có ngày cuối tuần (xem ghi chú ở đầu trang)'):'';
      let why;
      if(!n_ok)why=gapS+T('Too few runs to judge the parts yet.','Chưa đủ lượt chạy để đánh giá từng phần.');
      else if(dC>0&&dD<0)why=gapS+T(`Why the total went up (${sgn(dC)}, ${pctTxt(100*dC/bc)}) although draft GPU fell ${pctTxt(100*dD/(b.draft||1))}: drafts were only ${pct(share)}% of the comparable before total (${fmt(b.draft)} of ${fmt(bc)}), so stopping them saved ${fmt(-dD)} GPU hours a day. Ready PR runs grew by ${fmt(dR)}${smS}${wdS}.`,
          `Vì sao tổng tăng (${sgn(dC)}, ${pctTxt(100*dC/bc)}) dù GPU của draft giảm ${pctTxt(100*dD/(b.draft||1))}: draft chỉ chiếm ${pct(share)}% tổng trước đây cùng phạm vi (${fmt(b.draft)} trên ${fmt(bc)}), nên dừng chúng chỉ tiết kiệm ${fmt(-dD)} giờ GPU mỗi ngày. Phần chạy trên PR ready tăng ${fmt(dR)}${smS}${wdS}.`);
      else why=gapS+T(`Per part: drafts ${sgn(dD)} (${pctTxt(100*dD/(b.draft||1))}), ready PR runs ${sgn(dR)} (${pctTxt(100*dR/(b.ready||1))}), retries that failed again ${sgn(dRt)} (${pctTxt(100*dRt/(b.retry||1))})${smS}${wdS}.`,
          `Từng phần: PR draft ${sgn(dD)} (${pctTxt(100*dD/(b.draft||1))}), chạy trên PR ready ${sgn(dR)} (${pctTxt(100*dR/(b.ready||1))}), lần chạy lại vẫn lỗi ${sgn(dRt)} (${pctTxt(100*dRt/(b.retry||1))})${smS}${wdS}.`);
      h+=`<p class="im-why" data-im="why">${esc(why)}</p>`;}
    const kn=M('draft_share'),pj=M('gpu_h_day_pr'),known=kn&&pj&&aOf(pj).n?100*(aOf(kn).n||0)/aOf(pj).n:null,knownB=kn&&pj&&bOf(pj).n?100*(bOf(kn).n||0)/bOf(pj).n:null;
    const notes=[T('≈ Ready PR runs are computed (PR GPU − drafts − failed retries), not measured on their own.','≈ Phần chạy trên PR ready là số tính ra (GPU của PR − draft − chạy lại vẫn lỗi), không đo riêng.'),
      known!=null?T(`Draft or ready is known for ${pct(Math.min(knownB??100,known))}% or more of PR GPU jobs; the rest count as ready.`,`Biết được draft hay ready cho ít nhất ${pct(Math.min(knownB??100,known))}% job GPU của PR; phần còn lại được tính là ready.`):'',
      T('A failed retry on a draft PR counts in both "draft" and "retries"; that overlap is not measured (small: drafts are a small part).','Một lần chạy lại lỗi trên PR draft được tính ở cả "draft" và "chạy lại"; phần trùng này không đo được (nhỏ, vì draft chỉ là phần nhỏ).'),
      perRun!=null?T(`≈ Weekly full build: ${fmt(wa.n)} runs in ${dayTxt(ADAYS)} while it was being rolled out, so its daily figure is too high; at one run a week it is about ${fmt(perRun/7)} GPU hours a day.`,`≈ Weekly full build: ${fmt(wa.n)} lượt trong ${dayTxt(ADAYS)} lúc mới triển khai nên số mỗi ngày đang cao; nếu mỗi tuần một lượt thì khoảng ${fmt(perRun/7)} giờ GPU mỗi ngày.`):''].filter(Boolean);
    return h+`<ul class="im-notes" data-im="notes">${notes.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`;}

  // ---------- 4: watchlist (worse with enough runs, or a safety risk) + one next step each
  const NEXT={gpu_h_day:['Do not act yet: wait for day 7 and read the weekday-matched row. If it is still up, look at ready PR runs in "Where did the GPU time go".','Chưa cần làm gì: chờ đến ngày 7 và xem dòng so theo cùng ngày trong tuần. Nếu vẫn tăng, xem phần chạy trên PR ready ở mục "Thời gian GPU đã đi đâu".'],
    retry_waste_gpu:['Open the PR jobs whose retry failed too: a job that fails twice is a real failure or a broken runner, so stop retrying it automatically.','Mở các job PR mà lần chạy lại vẫn lỗi: job lỗi hai lần là lỗi thật hoặc máy chạy hỏng, nên ngừng tự động chạy lại job đó.'],
    retry_rate:['List the most-retried jobs and fix or quarantine the top few.','Liệt kê các job bị chạy lại nhiều nhất và sửa hoặc cách ly vài job đứng đầu.'],
    mp_gpu_pr:['Check whether the quick multiprocess tier also runs on pushes that run the heavy tier: both on one push pays twice.','Kiểm tra xem tầng multiprocess nhanh có chạy cả trên lần push đã chạy tầng nặng không: chạy cả hai trên một push là tốn gấp đôi.'],
    heavy_day:['See why the heavy tier still runs (full / force-ci labels, shared CI files) and narrow those rules.','Xem vì sao tầng nặng vẫn chạy (nhãn full / force-ci, file CI dùng chung) và thu hẹp các quy tắc đó.'],
    weekly_pass:['Open the failed weekly runs (Weekly tab) and fix them: the weekly full build is now the only GPU check after merge.','Mở các lượt weekly bị lỗi (tab Weekly) và sửa: weekly full build giờ là kiểm tra GPU duy nhất sau merge.'],
    weekly_mp_fail:['Open the latest weekly run and fix the failing heavy workloads before the next release.','Mở run weekly mới nhất và sửa các workload nặng bị lỗi trước bản phát hành tiếp theo.'],
    _:['Watch it for a few more days; if it stays worse, open the jobs behind it.','Theo dõi thêm vài ngày; nếu vẫn tệ hơn, mở các job đứng sau con số này.']};
  NEXT.repeat_rate=NEXT.retry_waste_gpu;
  function watch(){const L=MS.filter(m=>!DET.has(m.key)).map(m=>[m,judge(m),change(m)]).filter(([m,j,c])=>j==='risk'||(j==='worse'&&c&&(c.p==null||Math.abs(c.p)>=WATCH)));
    const keys=new Set(L.map(x=>x[0].key));const W=L.filter(([m])=>!(m.key==='repeat_rate'&&keys.has('retry_waste_gpu')))   // same failures, counted once
      .sort((x,y)=>(y[1]==='risk')-(x[1]==='risk')||(x[0].family==='rel'?-1:0)-(y[0].family==='rel'?-1:0)||Math.abs((y[2]||{}).p||0)-Math.abs((x[2]||{}).p||0));
    if(!W.length)return `<p class="dk-mute" data-im="watch-empty">${T('Nothing got worse among the numbers with enough runs, and no safety risk.','Không có con số nào đủ lượt chạy bị tệ hơn, và không có rủi ro an toàn.')}</p>`;
    return `<p class="im-legend" data-im="watch-legend">${T(`Only numbers that got worse by ${pct(WATCH)}% or more (with enough runs) or carry a safety risk.`,`Chỉ các con số tệ hơn từ ${pct(WATCH)}% trở lên (đủ lượt chạy) hoặc có rủi ro an toàn.`)}${ADAYS<MIN?' '+T(`All figures are so far: not proven until day ${MIN}.`,`Mọi con số đều tạm tính: chưa chắc chắn trước ngày ${MIN}.`):''}</p><ul class="im-watch" data-im="watch">`+W.map(([m,j,c])=>{const a=aOf(m),b=bOf(m);
      const what=j==='risk'?evidence(m):`${vu(m,b.value)} → ${vu(m,a.value)}`,ch=c?` (${c.p!=null?pctTxt(c.p):du(m,c.d)})`:'';
      const nx=T(...(NEXT[m.key]||NEXT._)),lnk=/^weekly/.test(m.key)?` <a href="#obs/weekly">${T('Weekly tab','Tab Weekly')} →</a>`:'';
      return `<li data-watch="${esc(m.key)}"><span class="ic" aria-hidden="true">⚠</span><div><div class="t"><b>${esc(nameOf(m))}</b>: ${esc(what)}${esc(ch)} ${pill(j)}</div>`+
        `<p class="nx"><b>${T('Next','Việc tiếp theo')}:</b> ${esc(nx)}${lnk}</p></div></li>`;}).join('')+`</ul>`;}

  // ---------- 5: details: sortable table of every metric (always in the DOM) + how it is measured
  const FAM={gpu:['GPU','GPU'],mp:['Multiprocess tests','Test multiprocess'],gha:['GitHub Actions','GitHub Actions'],rel:['Reliability','Độ tin cậy']};
  const STW={nodata:['no data','không có dữ liệu'],few:['too few runs to judge','quá ít lượt chạy để đánh giá'],risk:['at risk','có rủi ro'],ok:['OK','ổn'],better:['better','tốt hơn'],worse:['worse','tệ hơn'],same:['about the same','gần như không đổi'],info:['for context','để tham khảo'],new:['new: no before','mới: không có số trước'],unclear:['unclear (weekday effect)','chưa rõ (lệch ngày trong tuần)']};
  let SORT={k:null,dir:1};
  const GRPN={cost:['Cost','Chi phí'],speed:['Speed','Tốc độ'],safety:['Safety','An toàn']},GRPO={cost:0,speed:1,safety:2};
  const SAFE=new Set(['smoke_cov','bypass_rate']);
  const grpOf=m=>{const g=GROUPS.find(x=>x[2].includes(m.key));return g?g[0]:m.family==='rel'||SAFE.has(m.key)?'safety':m.unit==='min'?'speed':'cost';};
  const unitCol=m=>m.unit==='%'?T('% (change in points)','% (thay đổi tính bằng điểm)'):un(m);
  const COLS=[['name',['Number','Con số'],0],['g',['Group','Nhóm'],0],['fam',['Area','Khu vực'],0],['u',['Unit','Đơn vị'],0],['b',['Before','Trước'],1],['a',['After','Sau'],1],
    ['c',['Change (%)','Thay đổi (%)'],1],['n',['Runs after / needed','Lượt chạy sau / cần'],1],['s',['State','Trạng thái'],0]];
  function tRows(){return MS.map(m=>{const a=aOf(m),b=bOf(m),c=change(m),j=judge(m);
    const g=grpOf(m);
    return {m,name:nameOf(m),g:GRPO[g]+1,gn:T(...GRPN[g]),u:unitCol(m),fam:T(...(FAM[m.family]||[m.family,m.family])),b:m.after_only||!hasN(b)?null:b.value,a:hasN(a)?a.value:null,n:a.n||0,c:c&&c.p!=null?c.p:c?c.d:null,cs:c,j,
      s:T(...(STW[j]||[j,j]))+(ADAYS<MIN&&!['nodata','few'].includes(j)?' · '+T('still measuring','vẫn đang đo'):'')};});}
  function table(){let R=tRows();if(SORT.k){const k=SORT.k;R.sort((x,y)=>{const p=x[k],q=y[k];if(p==null&&q==null)return 0;if(p==null)return 1;if(q==null)return -1;return (typeof p==='string'?p.localeCompare(q):p-q)*SORT.dir;});}
    return `<details class="im-tbl" data-im="tbl"><summary>${T(`All ${MS.length} numbers (table)`,`Tất cả ${MS.length} con số (bảng)`)}</summary><div class="dk-scroll"><table class="dk-t im-t" data-im="table"><thead><tr>`+
      COLS.map(([k,n,r])=>`<th class="${r?'r':''}" data-col="${k}" aria-sort="${SORT.k===k?(SORT.dir>0?'ascending':'descending'):'none'}"><button type="button" data-sort="${k}">${T(...n)}</button></th>`).join('')+`</tr></thead><tbody>`+
      R.map(r=>{const m=r.m,d=defOf(m);return `<tr data-key="${esc(m.key)}" data-j="${r.j}" data-g="${grpOf(m)}"><td>${d?`<span class="im-def" tabindex="0" data-tip="${esc(r.name+'\n'+d)}">${esc(r.name)}</span>`:esc(r.name)}</td><td class="nw">${esc(r.gn)}</td><td>${esc(r.fam)}</td><td>${esc(r.u)}</td>`+
        `<td class="r">${r.b==null?'–':esc(nv(m,r.b))}</td><td class="r">${r.a==null?'–':esc(nv(m,r.a))}</td>`+
        `<td class="r" data-c="1">${r.cs?esc(sgnU(m,r.cs.d))+(r.cs.p!=null?' ('+esc(pctTxt(r.cs.p))+')':''):'–'}</td><td class="r">${fmt(r.n)} / ${fmt(m.min_n)}</td><td>${esc(r.s)}</td></tr>`;}).join('')+`</tbody></table></div></details>`;}
  function how(){const c=D.coverage||{},burn=(D.burn_in_hours||{})[AV.id];
    return `<details class="im-how" data-im="how"><summary>ⓘ ${T('How it is measured','Cách đo')}</summary><p>`+
      T(`Before = the ${fmt(BV.days)} days just before the first change was merged. After = from the last merge${burn?` plus ${burn} hours of settling`:''} until now. Both windows go through the same code. Per day = total ÷ days of the window; nothing is extrapolated. GPU hours = run minutes × GPUs ÷ 60. Typical = half of the runs are faster; slow case = 9 in 10 are faster.`,
        `Trước = ${fmt(BV.days)} ngày ngay trước khi thay đổi đầu tiên được merge. Sau = từ lần merge cuối${burn?` cộng ${burn} giờ chờ ổn định`:''} đến nay. Cả hai cửa sổ được tính bằng cùng một đoạn code. Mỗi ngày = tổng ÷ số ngày của cửa sổ; không ngoại suy. Giờ GPU = số phút chạy × số GPU ÷ 60. Thường gặp = một nửa số lượt chạy nhanh hơn; trường hợp chậm = 9/10 nhanh hơn.`)+' '+
      T(`Every number needs a minimum of runs (shown as "runs after / needed"). Below it the page shows the value as a hollow dot, with no change, no % and no better / worse. "Proven" needs ${MIN} days after the change and enough runs for every key number. Changes under ${pct(FLAT)}% count as about the same. The weekly full build is at risk under ${pct(WEEKLY_OK)}% of runs passing. The watchlist shows numbers that got worse by ${pct(WATCH)}% or more.`,
        `Mỗi con số cần một số lượt chạy tối thiểu (cột "lượt chạy sau / cần"). Chưa đủ thì trang chỉ hiện giá trị bằng chấm rỗng, không có mức thay đổi, không có % và không có tốt / tệ. "Đủ cơ sở" cần ${MIN} ngày sau thay đổi và đủ lượt chạy cho mọi con số chính. Thay đổi dưới ${pct(FLAT)}% được coi là gần như không đổi. Weekly full build có rủi ro khi dưới ${pct(WEEKLY_OK)}% lượt đạt. Danh sách theo dõi gồm các con số tệ hơn từ ${pct(WATCH)}% trở lên.`)+
      (c.gha_runs?' '+T(`GitHub runs matched to a PR: ${pct(100*c.gha_runs_with_pr/c.gha_runs)}%.`,`Lượt chạy GitHub khớp được với PR: ${pct(100*c.gha_runs_with_pr/c.gha_runs)}%.`):'')+
      ` ${T('Scope','Phạm vi')}: <span class="obsraw">${esc(D.scope||'')}</span>. ${T('Collected','Thu thập lúc')} ${esc(String(D.collected_at||'').slice(0,16).replace('T',' '))} UTC.</p></details>`;}

  const set=(id,h,body)=>{const e=document.getElementById(id);if(!e)return;e.querySelector('h2').textContent=h;document.getElementById(id+'B').innerHTML=body;};
  function render(){
    if(!MS.length||!VS.length){set('imWin',T('CI impact','Tác động CI'),`<p class="dk-mute" data-im="empty">${T('No data yet: run ops-app/backend/collect_ci_impact.py (the daily refresh does).','Chưa có dữ liệu: chạy ops-app/backend/collect_ci_impact.py (lần làm mới hằng ngày sẽ chạy).')}</p>`);
      ['imGpu','imMp','imGha','imRel'].forEach(id=>set(id,'',''));return;}
    const open=!!document.querySelector('#imRel details.im-tbl[open]');
    set('imWin',T('CI impact: cheaper, faster, still safe?','Tác động CI: rẻ hơn, nhanh hơn, vẫn an toàn?'),windows()+verdict());
    set('imGpu',T('Before → after, in real units','Trước → sau, theo đơn vị thật'),beforeAfter());
    set('imMp',T('Where did the GPU time go?','Thời gian GPU đã đi đâu?'),gpuGo());
    set('imGha',T('Watchlist','Danh sách cần theo dõi'),watch());
    set('imRel',T('Details','Chi tiết'),table()+how());
    if(open){const d=document.querySelector('#imRel details.im-tbl');if(d)d.open=true;}
  }
  document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('#imRel [data-sort]');if(!b)return;const k=b.dataset.sort;
    SORT=SORT.k===k?{k,dir:-SORT.dir}:{k,dir:1};render();const f=document.querySelector(`#imRel [data-sort="${k}"]`);if(f)f.focus();});
  // one tooltip for every mark: hover + keyboard focus (values are also in the table); touch: hides on the next tap or after 2.5 s
  const tip=document.getElementById('imTip');let tmo=null,shownAt=0;
  function show(el,touch){const t=el.getAttribute('data-tip');if(!t||!tip)return;const [a,...rest]=t.split('\n');tip.textContent='';const b=document.createElement('b');b.textContent=a;tip.appendChild(b);
    rest.forEach(x=>{const d=document.createElement('div');d.className='s';d.textContent=x;tip.appendChild(d);});tip.hidden=false;
    const r=el.getBoundingClientRect(),w=tip.offsetWidth,hh=tip.offsetHeight;let x=r.left+r.width/2-w/2,y=r.bottom+8;x=Math.max(8,Math.min(innerWidth-w-8,x));if(y+hh>innerHeight-8)y=r.top-hh-8;tip.style.left=x+'px';tip.style.top=y+'px';
    shownAt=Date.now();clearTimeout(tmo);if(touch)tmo=setTimeout(hide,2500);}
  const hide=()=>{if(tip)tip.hidden=true;};
  const at=e=>e.target.closest&&e.target.closest('section[data-tab="impact"] [data-tip]');
  document.addEventListener('pointerover',e=>{if(e.pointerType==='touch')return;const el=at(e);el?show(el):hide();});
  document.addEventListener('pointerdown',e=>{const el=at(e);el?show(el,e.pointerType==='touch'):hide();});
  document.addEventListener('focusin',e=>{const el=at(e);el?show(el):hide();});
  document.addEventListener('focusout',e=>{if(at(e))hide();});
  addEventListener('scroll',()=>{if(Date.now()-shownAt>400)hide();},{passive:true});   // focus scrolls the mark into view: keep the tip it just opened
  window.IMPACT={data:D,render};
  const start=()=>{render();addEventListener('langchange',render);};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
</script>
<!-- IMPACT:JS:END -->
"""


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor) if before else page.index(anchor) + len(anchor)
    return page[:i] + ("" if before else "\n") + block.strip() + ("\n" if before else "") + page[i:]


def main():
    try:
        data = json.load(open(DESK, encoding="utf-8")).get("impact") or {}
    except (OSError, ValueError):
        print("impact: no release_desk.json (run ops-app/backend/export_page_data.py); tab stays empty")
        data = {}
    with open(PAGE, encoding="utf-8", newline="") as f:
        page = f.read()
    nl = "\r\n" if "\r\n" in page else "\n"   # keep the page's line endings (CRLF)
    eol = lambda s: s.replace("\r\n", "\n").replace("\n", nl)  # noqa: E731
    page = put(page, "/* IMPACT:CSS:START */", "/* IMPACT:CSS:END */", eol(CSS), "/* NAV:CSS:START */")
    page = put(page, "<!-- IMPACT:HTML:START -->", "<!-- IMPACT:HTML:END -->", eol(HTML), "<!-- WEEKLY:HTML:END -->", before=False)
    js = eol(JS).replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).replace("</", "<\\/"))
    page = put(page, "<!-- IMPACT:JS:START -->", "<!-- IMPACT:JS:END -->", js, "</body>")
    with open(PAGE, "w", encoding="utf-8", newline="") as f:
        f.write(page)
    ms, vs = data.get("metrics") or [], data.get("versions") or []
    st = {}
    for m in ms:
        s = ((m.get("values") or {}).get(vs[-1]["id"]) or {}).get("status") if vs else None
        st[s] = st.get(s, 0) + 1
    print(f"impact: {len(ms)} metrics x {len(vs)} versions {st} · latest {vs[-1]['id'] if vs else '-'} {vs[-1].get('days') if vs else ''} d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
