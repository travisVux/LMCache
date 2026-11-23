"""Section 9 HTML template, CSS additions and JS additions (compact UI, review fixes)."""

HTML = r"""
<!-- CPU-TESTS:START -->
<section class="card" id="cpu" data-view="cpu" data-tab="overview">
  <div class="head"><h2>1 · CPU tests at a glance</h2>
  <p class="sub">GHA run <code>42189301949</code> + Buildkite <code>k3-unit-tests #14829</code>, same commit <code>05d8eb84</code> (2026-11-06).</p></div>
  <div class="tiles" id="cpuTiles"></div>
</section>

<section class="card" data-view="cpu" data-tab="overview">
  <div class="head"><h2>2 · Which unit tests run where</h2>
  <p class="sub">Same commit, measured test by test. Who gates what: <a class="xlink" data-goto="gates/overview">Gates &amp; tiers → 1</a></p></div>
  <div class="ovl" id="ovl"></div>
  <div class="legend" id="ovlLegend"></div>
  <p class="callout">→ 327 vLLM-connector / lazy-offload tests run only on GHA Test (advisory): k3 has no vLLM, so no merge gate covers them.</p>
</section>

<section class="card" data-view="cpu" data-tab="tiers">
  <div class="head"><h2>3 · Feature matrix</h2>
  <p class="sub">Click a row → what · why · setup · code · files.</p></div>
  <div class="fm-tools"><button type="button" class="chip" id="fmOpen">Expand all</button><button type="button" class="chip" id="fmClose">Collapse all</button></div>
  <table class="fm" id="fm">
    <thead><tr><th>Feature area</th><th>Tests passed</th><th>Time in job</th><th class="num">Files</th><th class="num">Skipped</th><th class="num">CPU-excluded</th></tr></thead>
    <tbody></tbody>
  </table>
  <p class="note">Time = gap between log results (teardown / fixture time is absorbed by the next file; fast files may show 0 s). 47 module-level skips are not itemized.</p>
</section>

<section class="card" data-view="cpu" data-tab="tiers">
  <div class="head"><h2>4 · Setup matrix</h2>
  <p class="sub">Files per area using each technique. Socket / subprocess columns = where port and timing flakes come from.</p></div>
  <div style="overflow-x:auto;padding-right:80px"><table class="hm" id="hm"></table></div>
  <div class="legend" id="hmLegend"></div>
</section>

<section class="card" data-view="gpu" data-tab="tiers">
  <div class="head"><h2>4 · CPU E2E: one script, two runners</h2>
  <p class="sub"><code>.github/scripts/run-cpu-e2e-validation.sh</code> — real vLLM-CPU + LMCache server.</p></div>
  <div class="runners">
    <div class="runner"><span class="badge req">required</span><b>Buildkite cpu_e2e_validation</b><span>in k3-multiprocess-test · 3 transfer modes · 3.6 min p50 · 1,034 runs / 30 d</span></div>
    <div class="runner"><span class="badge adv">advisory</span><b>GHA cpu_device.yml</b><span>7 legs · Ubuntu + macOS · opt-125m + DeepSeek-V2-Lite (MLA, dummy) · zmq / grpc / aio / native</span></div>
  </div>
  <ol class="flow">
    <li><b>Start</b><span>server + vLLM serve</span></li>
    <li><b>Transport</b><span>log shows expected mode</span></li>
    <li><b>Store</b><span>1st request writes chunks</span></li>
    <li><b>Hit</b><span>2nd request reads chunks</span></li>
    <li><b>Reset</b><span>miss, then re-store</span></li>
    <li><b>Restart</b><span>vLLM restarts, still hit</span></li>
    <li><b>Same output</b><span>5 runs identical</span></li>
    <li><b>No false hit</b><span>other prompt misses</span></li>
  </ol>
  <p class="note">GHA legs also run <code>lmcache bench server</code> (2 modes) first. Newest 200 cpu_device runs (2026-11-06 → 11-08, gh run list on 2026-11-09): 124 skipped by the path filter; of the 76 that ran, 39 ok · 9 fail · 12 cancelled · 16 waiting for approval.</p>
</section>

<section class="card" data-view="cpu" data-tab="tiers">
  <div class="head"><h2>5 · CPU-excluded suites</h2>
  <p class="sub" id="nrSub"></p></div>
  <div class="ex-bar"><label><input type="checkbox" id="nrCand"> CPU-portable only</label><label><input type="checkbox" id="nrHelp"> include helper files</label></div>
  <div style="max-height:480px;overflow:auto"><table class="nr" id="nr"><thead><tr><th>File</th><th>Area</th><th>Why</th><th>CPU-portable</th><th class="r">Lines</th></tr></thead><tbody></tbody></table></div>
</section>

<section class="card" data-view="cpu" data-tab="cost">
  <div class="head"><h2>6 · Time: same unit tests, two runners</h2>
  <p class="sub">Commit 05d8eb84. The CPU job is done ≈30 min before the required GPU unit pod starts.</p></div>
  <div class="tline" id="tline"></div>
  <p class="callout"><b>→ Use GHA Test as the early-fail signal for k3-unit-tests.</b> Cost per push: ≈95 CPU runner-min (5 versions × ≈19 min = 2.3 disk + 3.3 install + 12.5 pytest).</p>
  <h3 class="h3">Slowest 15 files (CPU job)</h3>
  <div class="slow" id="slow"></div>
</section>

<section class="card" data-view="cpu" data-tab="findings">
  <div class="head"><h2>7 · Fail-fast findings</h2>
  <p class="sub">Checked by an independent review (REVIEW_ponytail.md). Hover a card for evidence.</p></div>
  <div class="ffg" id="ffg"></div>
</section>

<section class="card" data-view="cpu" data-tab="explore">
  <div class="head"><h2>8 · Test explorer</h2></div>
  <div class="ex-bar">
    <input type="search" id="exQ" placeholder="Search: eviction, lora, shm, restart, quota…">
    <select id="exA"><option value="">All feature areas</option></select>
    <label><input type="checkbox" id="exSk"> with skips</label>
    <label><input type="checkbox" id="exCur"> ★ gate-critical</label>
    <select id="exSort"><option value="area">By area</option><option value="secs">Slowest first</option><option value="tests">Most tests</option></select>
    <span class="ex-count" id="exN"></span>
  </div>
  <details class="rp-foldable" id="gcFold" style="margin:0 0 12px">
    <summary>★ Gate-critical tests (hand-written)</summary>
    <p class="sub" style="margin:0 0 8px">The tests that decide whether a PR merges, explained by hand. Source: <code>curated_tests.py</code>.</p>
    <div class="ex-bar"><span id="gcChips" class="gc-chips"></span><input type="search" id="gcQ" placeholder="Search: lock, LoRA, prefetch, restart…"><span class="ex-count" id="gcN"></span></div>
    <table class="gc" id="gc"><thead><tr><th>Test</th><th>What it guards in LMCache</th><th>If it fails</th><th>Look at</th></tr></thead><tbody></tbody></table>
  </details>
  <div id="exList"></div>
  <div style="margin-top:10px"><button type="button" id="exMore" class="theme">Show more</button></div>
</section>
<!-- CPU-TESTS:END -->
"""

CSS_ADD = r"""
.gc-chips{display:inline-flex;gap:4px;flex-wrap:wrap}
.gc th,.gc td{padding:6px 8px;border-bottom:1px solid var(--grid);font-size:12px;text-align:left;vertical-align:top}
.gc th{color:var(--text-secondary);font-weight:600;font-size:11.5px}
.gc tr.gch td{background:var(--surface-2);font-weight:650;font-size:12px}
.gc td.t{font:11.5px ui-monospace,Consolas,monospace;word-break:break-all;width:30%}
.gc td.t small{display:block;font:11px system-ui,sans-serif;color:var(--text-muted);margin-top:2px}
.gc td.l{font:11px ui-monospace,Consolas,monospace;color:var(--text-secondary);word-break:break-all;width:16%}
.chip.on{color:var(--text-primary);border-color:var(--series-3);background:color-mix(in oklab,var(--series-3) 14%,transparent)}
.star{color:var(--warning);font-weight:700;margin-right:4px}
.tt td.lm.cur{font-style:normal}
.sdesc{margin-top:10px;padding:8px 12px;border-left:3px solid var(--series-3);background:var(--surface-2);border-radius:0 8px 8px 0;font-size:12.5px;line-height:1.45}
.sdesc b{color:var(--text-secondary);font-weight:650;margin-right:6px}
.sdesc .sk{margin-top:3px;color:var(--text-primary)}
body.nodesc .sdesc{display:none}
.info{all:unset;cursor:help;display:inline-grid;place-items:center;width:18px;height:18px;margin-left:8px;border-radius:50%;border:1px solid var(--border);color:var(--text-muted);font-size:11px;font-weight:700;vertical-align:2px}
.info:hover,.info:focus-visible{color:var(--text-primary);border-color:var(--text-muted)}
.ovl{display:flex;height:30px;gap:2px;border-radius:6px;overflow:hidden;margin-top:4px}
.ovl div{display:flex;align-items:center;padding:0 10px;font-size:12px;font-weight:650;white-space:nowrap;overflow:hidden;cursor:default;outline:none}
.ovl div:hover,.ovl div:focus{filter:brightness(1.1)}
.badge{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;padding:1px 7px;border-radius:999px;border:1px solid currentColor;margin-right:4px;white-space:nowrap}
.badge.req{color:var(--critical)}
.badge.adv{color:var(--text-muted)}
.badge.rel{color:var(--series-2)}
.badge.ok{color:var(--good)}
.badge.part{color:var(--warning)}
.badge.new{color:var(--series-1)}
.badge.fix{color:var(--series-3)}
.gate th,.gate td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--grid);font-size:12.5px;vertical-align:top}
.gate th{color:var(--text-secondary);font-weight:600;font-size:11.5px}
.gate td small{display:block;color:var(--text-muted);font-size:11px}
.gate td.r{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.gate tr.hl td{background:color-mix(in oklab,var(--series-3) 9%,transparent)}
.h3{font-size:13.5px;font-weight:650;margin:18px 0 8px}
.tline{display:grid;grid-template-columns:170px 1fr;gap:8px 12px;align-items:center}
.tline .lab{font-size:12.5px;text-align:right}
.tline .lab small{display:block;color:var(--text-muted);font-size:11px}
.tline .trk{position:relative;height:26px}
.tline .seg2{position:absolute;top:0;bottom:0;border-radius:5px;display:flex;align-items:center;padding-left:8px;font-size:11.5px;font-weight:600;white-space:nowrap;overflow:hidden;cursor:default}
.tline .axis{grid-column:2;position:relative;height:16px;border-top:1px solid var(--grid)}
.tline .axis span{position:absolute;top:2px;font-size:10.5px;color:var(--text-muted);transform:translateX(-50%);white-space:nowrap}
.tline .axis span:last-child{transform:translateX(-100%)}
.callout{margin:12px 0 0;padding:9px 12px;border-left:3px solid var(--series-3);background:var(--surface-2);border-radius:0 8px 8px 0;font-size:12.5px}
.fm-tools{display:flex;gap:6px;margin:-4px 0 8px}
.chip{all:unset;cursor:pointer;font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid var(--border);color:var(--text-secondary)}
.chip:hover{color:var(--text-primary);border-color:var(--text-muted)}
.runners{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}
.runner{border:1px solid var(--border);border-radius:10px;padding:10px 12px;font-size:12.5px}
.runner b{display:block;margin:4px 0 2px}
.runner span:last-child{color:var(--text-secondary);font-size:12px}
.flow{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(8,1fr);gap:6px;counter-reset:f}
.flow li{position:relative;background:var(--surface-2);border-radius:8px;padding:8px 8px 9px;font-size:11.5px;counter-increment:f}
.flow li::before{content:counter(f);display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;background:var(--series-3);color:#fff;font-size:10.5px;font-weight:700;margin-bottom:4px}
.flow li b{display:block;font-size:12.5px}
.flow li span{color:var(--text-secondary)}
.flow li:not(:last-child)::after{content:"›";position:absolute;right:-6px;top:50%;transform:translateY(-50%);color:var(--text-muted);font-weight:700}
.ffg{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:10px}
.ffc{border:1px solid var(--border);border-radius:10px;padding:11px 13px;background:var(--surface-1);font-size:12.5px;outline:none}
.ffc:hover,.ffc:focus{border-color:var(--text-muted)}
.ffc .t{font-weight:650;margin:5px 0 3px;line-height:1.35}
.ffc .d{color:var(--text-secondary)}
.ffc .a{margin-top:6px;color:var(--text-primary)}
.ffc .a::before{content:"→ ";color:var(--series-3);font-weight:700}
.nr td.cd{white-space:nowrap}
@media (max-width:980px){.flow{grid-template-columns:repeat(4,1fr)}.runners{grid-template-columns:1fr}}
"""

FINDINGS = [
    # badge, title, detail, action, evidence
    ["new", "327 vLLM-connector unit tests are in no merge gate",
     "They importorskip vllm; k3-unit-tests installs no vLLM, so they run only in GHA Test (advisory). These files broke in recent PRs (lazy_offload, lora_keys).",
     "Gate them: make GHA Test (or a vLLM-only subset) required, or install vLLM in the k3 unit pod.",
     "per-test diff: k3 #14829 log vs GHA job 127850987819 (same commit) · test_mp_connector_kv_roles.py:14 importorskip"],
    ["new", "The CPU job is a free early-fail signal for the required GPU unit pod",
     "8,994 tests pass on both runners (87.7% of k3 tests, but only 12.5 of the 23.9 min k3 job). GHA CPU ends at ≈18 min; k3-unit-tests waits 25 min for a GPU, then runs 24 min.",
     "If GHA Test fails, cancel the queued k3-unit-tests build. Measured: 23 of 36 MP builds on a GHA-Test-failed commit still passed, so do not use GHA Test alone to cancel MP.",
     "Buildkite k3-unit-tests #14829 (job queued 08:40 → started 09:05 → done 09:29; 10,257 passed in 1,350 s) vs GHA job 127850987819"],
    ["new", "Moving CPU tests off the GPU unit pod frees about half of it, not 75–90%",
     "Time per test from the k3 log: 8,981 CPU-portable tests = 12.5 min, 1,267 k3-only tests = 8.8 min (41% of pytest), setup 2.2 min.",
     "Split k3-unit-tests into a CPU job + a GPU job with only the k3-only tests: GPU pod ≈11 min instead of 24.",
     "k3_durations.py · k3-unit-tests #14829 line timestamps · see PR / Release watch → Trend"],
    ["new", "Fast-fail cancel saves ≈6% of MP GPU time",
     "Replay of 401 MP PR builds (30 d). Numbers: Release Management → GPU load.",
     "Still build it (cheap), but trigger on required checks; bigger levers are retries, canceled builds and queue p90.",
     "fastfail_savings.py · ../P1/jobs_all_30d.csv + GHA Test / Code Quality runs + k3-unit-tests builds"],
    ["ok", "GHA Test is advisory for merge, but gates release",
     "Not in the required list; publish.yml needs it to succeed.",
     "Decide: make it required (then stabilise it) or keep advisory + rerun rule for release.",
     "gh api repos/LMCache/LMCache/branches/dev · publish.yml:183-214"],
    ["ok", "Matrix fail-fast works, but the failing leg runs to the end",
     "Other versions get cancelled; the failing leg still runs 12–15 min (no --maxfail; k3 uses --maxfail=1).",
     "Add --maxfail; run all 5 versions nightly without fail-fast to learn if failures are version-specific.",
     "40 failed runs: 29–34 cancelled per version · test.yml pytest line · unit/run.sh:38"],
    ["part", "Failures: 3 classes, and the big one is already fixed",
     "21 failed runs: test_profiling 16 (perf counters blocked on the Azure runner, perf_event_paranoid; fixed on dev by #6350 on 11-06), the rest real PR bugs, 1 ZMQ port collision.",
     "Quarantine flaky tests from per-test history over ≥30 days, not from this snapshot.",
     "REVIEW_ponytail F12 · c5a285ea · port collision in ip_store test_p2p_backend_with_controller (run 42189249028)"],
    ["ok", "≈19 min per Python version, 5 versions per push",
     "136 s free disk + 200 s install + 751 s pytest ≈ 95 runner-min per push.",
     "Cut PR versions only after the nightly data above.",
     "job 127850987819 step timings"],
    ["ok", "~6.5k lines of storage-logic tests skip on CPU only because of a device guard",
     "test_l1_manager, test_prefetch_controller, test_distributed_storage_manager, test_store_controller: the only device use is the skip guard.",
     "Task 2: remove the guard / use CPU tensors; test_multi_l1_serving already runs StorageManager on CPU.",
     "REVIEW_ponytail §5 9g#6 (static check, suites not executed)"],
    ["fix", "Hardcoded 5 s sleep wastes 70 s of runner time",
     "_EVICTION_SETTLE_SECONDS = 5.0 slept in warmup(); 14 tests × 5 s.",
     "monkeypatch it to 0 in tests → −70 s per version.",
     "lmcache/cli/commands/bench/engine_bench/workloads/prefix_suffix_tuner.py:164, :567"],
    ["ok", "A unit test makes a live network call (huggingface.co)",
     "test_create_workload.py: 13 real requests (12 × 401). Passes today = latent flaky test.",
     "Mock the tokenizer download (test double).",
     "job312.log ~2938-2956"],
    ["ok", "Collection quirks",
     "No testpaths → examples/ is collected; marker supa is not in the -m filter.",
     "Keep in mind when defining the L0 smoke tier.",
     "pytest.ini · test.yml"],
]

JS_ADD = r"""
  // section 10: gate-critical tests (hand-written, curated_tests.py)
  (function(){
    const C=D.curated, TI=C.tiers, rows=C.rows, tb=$('#gc tbody'); if(!tb) return;
    let tier='', q='';
    const L=()=>(window.I18N&&I18N.lang==='vi')?1:0;
    const chips=$('#gcChips');
    const draw=()=>{const vi=L();tb.replaceChildren();let n=0,last='';
      chips.replaceChildren();[['',vi?'Tất cả':'All']].concat(Object.keys(TI).map(k=>[k,k])).forEach(([k,lab])=>{const b=el('button',{class:'chip'+(tier===k?' on':''),type:'button',title:k?TI[k][vi]:''},lab+(k?` · ${rows.filter(r=>r[0]===k).length}`:''));b.addEventListener('click',()=>{tier=k;draw();});chips.appendChild(b);});
      rows.filter(r=>(!tier||r[0]===tier)&&(!q||r.join(' ').toLowerCase().includes(q))).forEach(r=>{
        if(r[0]!==last){last=r[0];const h=el('tr',{class:'gch'}),td=el('td',{colspan:'4'});td.append(el('span',{class:'badge '+TI[r[0]][2]},r[0]),document.createTextNode(' '+TI[r[0]][vi]));h.appendChild(td);tb.appendChild(h);}
        const tr=el('tr'),t=el('td',{class:'t'});t.append(document.createTextNode(r[1]),el('small',{},r[2]));
        tr.append(t,el('td',{},r[3+vi]),el('td',{},r[5+vi]),el('td',{class:'l'},r[7]));tb.appendChild(tr);n++;});
      $('#gcN').textContent=`${n} / ${rows.length}`;};
    $('#gcQ').addEventListener('input',e=>{q=e.target.value.trim().toLowerCase();draw();});
    addEventListener('langchange',draw); draw();
  })();
  // overlap bar: measured per test (k3 #14829 vs GHA 42189301949)
  (function(){
    const box=$('#ovl'), lg=$('#ovlLegend'); if(!box) return;
    const parts=[
      ['GHA only',327,'var(--series-2)','#fff','vLLM connector + lazy offload tests (importorskip vllm). Top: test_mp_connector_kv_roles 59, test_offload_manager 53, test_mp_connector_mm_keys 38'],
      ['both runners',8994,'var(--series-3)','#fff','96.5% of GHA tests · 87.7% of k3 tests'],
      ['k3 GPU only',1264,'var(--series-1)','#fff','cuda / device-guarded suites. Top: test_l1_manager 102, test_mp_mem_kernels 69, test_cache_engine 67, test_prefetch_controller 65'],
    ];
    const tot=parts.reduce((a,p)=>a+p[1],0);
    parts.forEach(([n,v,bg,fg,meta])=>{const d=el('div',{tabindex:'0',style:`flex:${v} 1 0;background:${bg};color:${fg}`},`${n} · ${fmt(v)}`);tipOn(d,fmt(v)+' tests',n,meta);box.appendChild(d);});
    parts.forEach(([n,v,bg])=>{const sp=el('span');sp.append(el('i',{class:'sw',style:`background:${bg}`}),document.createTextNode(`${n}: ${fmt(v)} (${(100*v/tot).toFixed(1)}%)`));lg.appendChild(sp);});
  })();
  // timeline: same tests, two runners
  (function(){
    const box=$('#tline'), MAX=50;
    const rows=[
      ['GHA Test (CPU)','advisory · 9,326 tests',[[0,5.6,'setup','var(--surface-2)','var(--text-secondary)','free disk + pip install'],[5.6,18.1,'pytest 12.5 min','var(--series-3)','#fff','751 s']]],
      ['k3-unit-tests (GPU)','required · 10,258 tests',[[0,24.9,'waiting for a GPU · 25 min','transparent','var(--text-secondary)','job created 08:40 → started 09:05'],[24.9,48.8,'run 24 min','var(--series-1)','#fff','pytest 1,350 s']]],
    ];
    rows.forEach(([n,s,segs])=>{const l=el('div',{class:'lab'},n);l.appendChild(el('small',{},s));const t=el('div',{class:'trk'});
      segs.forEach(([a,b,txt,bg,fg,meta])=>{const g=el('div',{class:'seg2',tabindex:'0',style:`left:${a/MAX*100}%;width:calc(${(b-a)/MAX*100}% - 2px);background:${bg};color:${fg};${bg==='transparent'?'border:1px dashed var(--text-muted);':''}`},txt);tipOn(g,(b-a).toFixed(1)+' min',n+' · '+txt,meta);t.appendChild(g);});
      box.append(l,t);});
    const ax=el('div',{class:'axis'});[0,10,20,30,40,50].forEach(m=>ax.appendChild(el('span',{style:`left:${m/MAX*100}%`},m+' min')));box.append(el('div'),ax);
  })();

  // feature matrix expand / collapse all
  $('#fmOpen').addEventListener('click',()=>document.querySelectorAll('#fm tr.ar:not(.open)').forEach(r=>r.click()));
  $('#fmClose').addEventListener('click',()=>document.querySelectorAll('#fm tr.ar.open').forEach(r=>r.click()));

  // findings cards
  const BL={new:'new',ok:'confirmed',part:'partly',fix:'easy fix'};
  const ff=$('#ffg');D.findings.forEach(f=>{const c=el('div',{class:'ffc',tabindex:'0'});c.append(el('span',{class:'badge '+f[0]},BL[f[0]]),el('div',{class:'t'},f[1]),el('div',{class:'d'},f[2]),el('div',{class:'a'},f[3]));tipOn(c,'Evidence',f[1],f[4]);ff.appendChild(c);});
"""
