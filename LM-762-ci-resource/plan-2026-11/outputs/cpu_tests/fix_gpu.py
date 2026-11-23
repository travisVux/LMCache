"""One-time fixes for the GPU half (sections 1-9) of 06_PR_TO_CI_VISUAL.html.

Applies REVIEW_ponytail.md F1-F3, F6-F8, F14-F19 + renumbering + shorter text.
Each replacement is skipped if already applied, so re-running is safe.
"""
from pathlib import Path as _Path  # noqa: E402
# the page sits in Plan/2026-11/, two levels above outputs/cpu_tests/
PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
s = open(PAGE, encoding="utf-8").read()
done, skipped = 0, []


def rep(a, b):
    global s, done
    if a in s:
        s = s.replace(a, b, 1)
        done += 1
    elif b in s:
        pass
    else:
        skipped.append(a[:70])


# ---- renumber + retag (same tab skeleton as CPU) ----
rep('<h2>3 · Proposed: an early-fail staircase</h2>', '<h2>3 · Early-fail staircase (proposed)</h2>')
rep('<h2>3b · What L0 … Full mean</h2>', '<h2>4 · What L0 … Full mean</h2>')
rep('<h2>4 · Test-impact map: change class → required tiers</h2>', '<h2>5 · Change class → required tiers</h2>')
rep('<h2>5 · Each MP workload: GPU cost today and where it moves</h2>', '<h2>6 · GPU cost per MP workload, and where it moves</h2>')
rep('<h2>6 · PR GPU-min in 30 days</h2>', '<h2>7 · PR GPU-min in 30 days</h2>')
rep('<h2>7 · Findings, pinned to the layer they hit</h2>', '<h2>8 · Findings by layer</h2>')
rep('<h2>8 · Interactive mindmap: PR → test case → logic check → function</h2>', '<h2>9 · Mindmap: PR → tier → test → check → function</h2>')
s = s.replace('data-view="gpu" data-tab="plan"', 'data-view="gpu" data-tab="tiers"').replace('data-view="gpu" data-tab="mindmap"', 'data-view="gpu" data-tab="explore"')

# ---- shorter subtitles ----
rep('<p class="sub">Read left to right. Bottom line of each lane: the main finding for that layer.</p>', '<p class="sub">Left to right. Bottom line = main finding.</p>')
rep('<p class="sub">Share of PR GPU-min, weighted over all MP workloads. Most GPU time is spent getting ready, not testing.</p>', '<p class="sub">Most GPU time goes to getting ready, not testing.</p>')
rep('<p class="sub">Each step costs more than the one before. A PR only climbs as high as its change class needs. Step height = relative cost per run.</p>', '<p class="sub">A PR climbs only as high as its change class needs. Height = relative cost. <span class="badge req">required today</span> jobs are named in the tooltip.</p>')
rep('''<p class="sub">"L" = <b>Layer</b> of testing. Lower number = cheaper, faster, runs earlier. A PR stops climbing as soon as a step fails, so most bad PRs fail cheap, before any GPU is used.</p>''', '<p class="sub">Lower = cheaper and earlier. A failing step stops the climb.</p>')
rep('<p class="sub">Which tiers a PR must pass, by what its files touch. A PR with several classes takes the union.</p>', '<p class="sub">Union of tiers over the classes a PR touches (P8).</p>')
rep('<p class="sub">GPU-min used by PR builds in 30 days. Color = where the workload goes in the proposed path; text = its exact new home.</p>', '<p class="sub">GPU-min / 30 d. Color = where it moves.</p>')
rep('<p class="sub">Click a node to open / close it. Drag to move, scroll to zoom. Search finds a test, check or function and opens the path to it.</p>', '<p class="sub">Click to open · drag · scroll to zoom · search opens the path.</p>')
rep('<p class="note">Rule of thumb: a test belongs in the lowest step that can still catch its bug. Only move it up if a lower step cannot see the bug (needs real model math, real GPU, or many GPUs).</p>', '<p class="note">Rule: a test lives in the lowest step that can still catch its bug.</p>')

# ---- F6: -80% caveat ----
rep('<div class="tile hl"><div class="v">−80%</div><div class="l">PR GPU-min with the proposed rule</div><div class="s">shadow estimate, 0 missed bug catches · P8</div></div>',
    '<div class="tile hl"><div class="v">−80%*</div><div class="l">PR GPU-min with the proposed rule</div><div class="s">*estimate, needs L2 scenarios built · checked vs 1 real catch (9/59 failures read) · P8</div></div>')
rep("['3 Classify','MP is all-or-nothing; any code file runs ~35 jobs','Path classes → tiers (−80%, 0 missed catches)','policy','P8'],",
    "['3 Classify','MP is all-or-nothing; any code file runs ~35 jobs','Path classes → tiers (−80% est.; 1 known catch checked)','policy','P8'],")
# ---- F19 ----
rep("['—','HF_TOKEN in plain text in Buildkite UI config','Ask maintainers to rotate','security','P1'],",
    "['—','HF_TOKEN in plain text in Buildkite UI config (reported; no artifact in plan folder)','Confirm, then ask maintainers to rotate','security','reported'],")
# ---- F16/F17: section 2 ----
rep('''    <div class="tl" role="img" aria-label="Queue wait 18.5 minutes, then running until 87 minutes">
      <div style="left:0;width:calc(18.5/87*100%);background:var(--surface-0);color:var(--text-secondary);border:1px dashed var(--text-muted)" data-tip="Queue wait (GPU jobs)|18.5 min p50|56.5 p90 · 4-GPU dsv4 jobs wait 46 min">queue 18.5</div>
      <div style="left:calc(18.5/87*100% + 2px);right:0;background:var(--seq-250);color:var(--text-primary)" data-tip="Build running|to 87 min p50|p90 288 min">running → 87 min</div>
    </div>''', '''    <div class="tl" role="img" aria-label="Passed build 87 minutes p50">
      <div style="left:0;right:0;background:var(--seq-250);color:var(--text-primary)" data-tip="Passed PR build, wall clock|87 min p50|p90 288 min">build 87 min p50 · p90 288</div>
    </div>
    <div class="lbl">Queue wait</div>
    <div class="q" style="font-size:12.5px;color:var(--text-secondary)">18.5 min p50 <b>per GPU job</b> (p90 56.5; 4-GPU dsv4 jobs 46) — jobs queue in parallel, so this is not a build segment</div>''')
rep('<p class="note">Source: outputs/P1 (288 sampled logs; startup = p50 per workload, weighted by GPU-min).</p>',
    '<p class="note">Approx.: p50 of 15 logs per workload, GPU-min weighted; test body = remainder. Source P1.</p>')
rep('<div class="f">Core-only PR: 518 → ~3 GPU-min per build</div>', '<div class="f">Core-only PR: 518 → ~3 GPU-min per build (P8)</div>')

# ---- F1/F2/F14: staircase ----
rep("    {id:'L1', name:'L1 unit', hw:'CPU', cost:'GHA py3.10–3.13', h:14, c:'series-3', d:'tests/v1/** — no CUDA markers'},",
    "    {id:'L1', name:'L1 unit · CPU', hw:'GHA, advisory', cost:'≈19 min × 5 py', h:14, c:'series-3', d:'GHA test.yml py3.10–3.14, 9,326 tests, not required. Same tests as L1 GPU pod → early-fail signal for it'},")
rep("    {id:'CE', name:'CPU E2E', hw:'CPU, 8 cores', cost:'3.6 min p50', h:26, c:'series-3', d:'vLLM-CPU + opt-125m, 3 transfer modes. Caught PR #5383'},",
    "    {id:'CE', name:'CPU E2E', hw:'CPU, 8 cores', cost:'3.6 min p50', h:26, c:'series-3', d:'REQUIRED: Buildkite cpu_e2e_validation in k3-multiprocess-test (3 transfer modes, caught PR #5383). GHA cpu_device.yml runs the same script, advisory'},\n    {id:'L1G', name:'L1 unit · GPU pod', hw:'1 GPU, required', cost:'25 min queue + 24 min', h:34, c:'series-1', d:'REQUIRED: Buildkite k3-unit-tests. All tests/ incl. cuda-marked, --maxfail=1, 10,257 tests. Only place for GPU kernel + 6.5k lines of storage tests today'},")

# ---- glossary rows ----
rep('''<tr><td class="k"><i style="background:var(--series-3)"></i>L1 unit</td><td>Run one function or class alone, with fake inputs</td><td>CPU · minutes (GHA, py3.10–3.13)</td><td>logic bugs inside one module: hashing, lookup, locks, config</td><td><code>test_store_and_lookup</code> in <code>tests/v1/multiprocess/test_cache_server.py</code></td><td><span class="pill yes">yes</span></td></tr>''',
    '''<tr><td class="k"><i style="background:var(--series-3)"></i>L1 unit · CPU</td><td>One function or class alone, fake inputs</td><td>CPU · ≈19 min × py3.10–3.14 (GHA, advisory)</td><td>logic bugs in one module: hashing, lookup, locks, config</td><td><code>test_hash_tokens_deterministic</code> in <code>tests/v1/multiprocess/test_token_hasher.py</code></td><td><span class="pill yes">yes · not required</span></td></tr>
      <tr><td class="k"><i style="background:var(--series-1)"></i>L1 unit · GPU pod</td><td>Same unit suite + cuda-marked tests, on 1 GPU</td><td>1 GPU · 25 min queue + 24 min (k3-unit-tests)</td><td>GPU kernels, storage suites that need a device today</td><td><code>test_store_and_lookup</code> in <code>tests/v1/multiprocess/test_cache_server.py</code> (cuda)</td><td><span class="pill yes">yes · required</span></td></tr>''')
rep('''<td><code>cpu_e2e_validation</code> with opt-125m (caught PR #5383)</td><td><span class="pill yes">yes</span></td></tr>''',
    '''<td><code>cpu_e2e_validation</code> (Buildkite, required) · same script in GHA <code>cpu_device.yml</code> (advisory)</td><td><span class="pill yes">yes · required</span></td></tr>''')
rep('<td><span class="pill no">XPU only, not CUDA</span></td>', '<td><span class="pill no">XPU only, not CUDA</span> <small style="color:var(--text-muted)">(CPU MLA dummy in GHA cpu_device, advisory)</small></td>')

# ---- F7/F8: matrix ----
rep("  const tiers=['L0 lint','L1 unit','L2 server','CPU E2E','L3 smoke','Layout smoke','Add-ons','Full'];",
    "  const tiers=['L0 lint','L1 CPU','L1 GPU unit','L2 server','CPU E2E','L3 smoke','Layout smoke','Add-ons','Full'];")
rep("""    ['docs','markdown, docs/, examples/',60,'0',[1,0,0,0,0,0,0,0]],
    ['tests_only','tests/**, tools/**',67,'0',[1,1,0,0,0,0,0,0]],
    ['other_platform','XPU/ROCm/MUSA… code',19,'0',[1,1,0,0,0,0,0,0]],
    ['core','lmcache/v1/**, storage, CLI',44,'0 (+7–20 add-on)',[1,1,1,1,0,0,2,0]],
    ['adapter (vLLM / SGLang)','lmcache/integration/**, transfer_context',11,'20.6 – 80.2',[1,1,1,1,1,0,2,0]],
    ['kernel','csrc/cuda/**, gpu_connector',6,'78.6',[1,1,0,0,1,1,0,0]],
    ['kv_layout','MLA / fp8 / hybrid / HMA code',14,'78.6',[1,1,1,1,1,1,0,2]],
    ['deps_ci','requirements, pyproject, MP harness',31,'~535',[1,1,1,1,1,1,1,1]],""",
    """    ['docs','markdown, docs/',60,'0',[1,0,0,0,0,0,0,0,0]],
    ['tests_only','tests/**, tools/**, examples/**.py',67,'0',[1,1,1,0,0,0,0,0,0]],
    ['other_platform','XPU/ROCm/MUSA… code',19,'0',[1,1,1,0,0,0,0,0,0]],
    ['core','lmcache/v1/**, storage, CLI',44,'0 (+7–20 add-on)',[1,1,1,1,1,0,0,2,0]],
    ['adapter (vLLM)','integration/vllm/**, transfer_context',11,'20.6 – 80.2',[1,1,1,1,1,1,0,2,0]],
    ['adapter (SGLang)','integration/sglang/** · no CPU E2E (vLLM-CPU only)','↑','20.6',[1,1,1,1,0,1,0,2,0]],
    ['kernel','csrc/cuda/**, gpu_connector',6,'78.6',[1,1,1,0,0,1,1,0,0]],
    ['kv_layout','MLA / fp8 / hybrid / HMA code',14,'78.6',[1,1,1,1,1,1,1,0,2]],
    ['deps_ci','requirements, pyproject, MP harness',31,'~535',[1,1,1,1,1,1,1,1,1]],""")
rep('<p class="note">Source: outputs/P8/shadow_report.md §2–§4. "PRs" = how many of the last 100 merged PRs touched the class (classes overlap).</p>',
    '<p class="note">PRs = of last 100 merged (classes overlap; ↑ = counted in adapter row above). L1 GPU unit = k3-unit-tests; keep it for core / kernel until the storage suites run on CPU.</p>')

# ---- F3: mindmap tiers ----
rep("""    L1:N('L1 unit tests','One function or class alone, fake inputs. CPU (GHA test.yml, py3.10–3.13)','.github/workflows/test.yml',[
      TC('test_cache_server.py','tests/v1/multiprocess/test_cache_server.py',[
        K('store then lookup finds the chunks','test_store_and_lookup :429',[fLookup(),fPrepStore(),fHash()]),
        K('store → retrieve returns the same bytes','test_store_retrieve_verify :492',[fPrepRet(),fRead()]),
        K('partial miss: only stored prefix is returned','test_retrieve_partial_miss :543',[fLookup(),fFreeLocks()]),
        K('register / unregister KV cache','test_register_unregister_kv_cache :401',[fRegister()]),
        K('store fails closed on incomplete block ids','test_store_fails_closed_on_incomplete_block_ids :455',[fPrepStore()]),
      ]),""",
    """    L1:N('L1 unit · CPU (GHA, advisory)','One function or class alone, fake inputs. GHA test.yml py3.10–3.14, not required','.github/workflows/test.yml',[
      TC('test_token_hasher.py','tests/v1/multiprocess/test_token_hasher.py',[
        K('same tokens → same hash','test_hash_tokens_deterministic :69',[fHash()]),
        K('different tokens → different hash','test_hash_tokens_different_input :74',[fHash()]),
        K('blake3 hasher does not import vLLM','test_init_blake3_does_not_import_vllm :32',[fHash()]),
      ]),""")
rep("""      TC('~60 more files in tests/v1/multiprocess/','tests/v1/multiprocess/',[
        K('gRPC / HTTP / blend / transfer planners …','',[F('see file names','tests/v1/multiprocess/')])
      ])
    ],{t:'tier',g:'cpu'}),
""", """      TC('~500 more files: see CPU view → Explore','tests/',[
        K('feature matrix + test explorer in the CPU view','',[F('CPU view','#cpu/explore')])
      ])
    ],{t:'tier',g:'cpu'}),

    L1G:N('L1 unit · GPU pod (k3-unit-tests, required)','Same suite + cuda-marked tests on 1 GPU, --maxfail=1. 25 min queue + 24 min','.buildkite/k3_tests/unit/run.sh',[
      TC('test_cache_server.py (cuda)','tests/v1/multiprocess/test_cache_server.py',[
        K('store then lookup finds the chunks','test_store_and_lookup :429',[fLookup(),fPrepStore(),fHash()]),
        K('store → retrieve returns the same bytes','test_store_retrieve_verify :492',[fPrepRet(),fRead()]),
        K('partial miss: only stored prefix is returned','test_retrieve_partial_miss :543',[fLookup(),fFreeLocks()]),
        K('register / unregister KV cache','test_register_unregister_kv_cache :401',[fRegister()]),
      ]),
      TC('storage suites skipped on CPU by a device guard','tests/v1/distributed/test_l1_manager.py …',[
        K('L1 / store / prefetch controller logic (~6.5k lines)','',[fWrite(),fRead()])
      ]),
    ],{t:'tier',g:'gpu'}),
""")
rep("    CE:N('CPU E2E','Real vLLM (CPU) + LMCache + opt-125m. CPU 8 cores, ~3.6 min','.github/scripts/run-cpu-e2e-validation.sh',[",
    "    CE:N('CPU E2E','Required: Buildkite cpu_e2e_validation (in k3-multiprocess-test), ~3.6 min. Same script in GHA cpu_device.yml (advisory)','.github/scripts/run-cpu-e2e-validation.sh',[")
rep("""    ['docs','markdown, docs/, examples/',['L0']],
    ['tests_only','tests/**, tools/**',['L0','L1']],
    ['other_platform','XPU / ROCm / MUSA code',['L0','L1']],
    ['core','lmcache/v1/**, storage, CLI',['L0','L1','L2','CE','AO?']],
    ['adapter (vLLM / SGLang)','integration/**, transfer_context',['L0','L1','L2','CE','L3','AO?']],
    ['kernel','csrc/cuda/**, gpu_connector',['L0','L1','L3','LS']],
    ['kv_layout','MLA / fp8 / hybrid / HMA',['L0','L1','L2','CE','L3','LS','FULL?']],
    ['deps_ci','requirements, pyproject, MP harness',['L0','L1','L2','CE','L3','LS','AO','FULL']],
  ];
  const tierOrder=['L0','L1','L2','CE','L3','LS','AO','FULL'];""",
    """    ['docs','markdown, docs/',['L0']],
    ['tests_only','tests/**, tools/**, examples/**.py',['L0','L1','L1G']],
    ['other_platform','XPU / ROCm / MUSA code',['L0','L1','L1G']],
    ['core','lmcache/v1/**, storage, CLI',['L0','L1','L1G','L2','CE','AO?']],
    ['adapter (vLLM)','integration/vllm/**, transfer_context',['L0','L1','L1G','L2','CE','L3','AO?']],
    ['adapter (SGLang)','integration/sglang/**',['L0','L1','L1G','L2','L3','AO?']],
    ['kernel','csrc/cuda/**, gpu_connector',['L0','L1','L1G','L3','LS']],
    ['kv_layout','MLA / fp8 / hybrid / HMA',['L0','L1','L1G','L2','CE','L3','LS','FULL?']],
    ['deps_ci','requirements, pyproject, MP harness',['L0','L1','L1G','L2','CE','L3','LS','AO','FULL']],
  ];
  const tierOrder=['L0','L1','L1G','L2','CE','L3','LS','AO','FULL'];""")
rep('<span><i style="background:var(--series-3)"></i>CPU tier and its tests</span>', '<span><i style="background:var(--series-3)"></i>CPU tier</span>')
rep('<span><i style="background:var(--series-1)"></i>1–2 GPU tier</span>', '<span><i style="background:var(--series-1)"></i>GPU tier (incl. required L1 GPU unit pod)</span>')

rep('<span><i class="sw" style="background:var(--series-1);display:inline-block"></i>1–2 GPU, only when path matches</span>', '<span><i class="sw" style="background:var(--series-1);display:inline-block"></i>GPU: L1 unit pod required today; others only on path match</span>')
# review round 2 (2026-11-09): drop the internal reference
rep('<p class="note">P8 §2–§4. PRs = of last 100 merged', '<p class="note">PRs = of last 100 merged')

open(PAGE, "w", encoding="utf-8").write(s)
print("applied", done, "| not found:", skipped)
