"""Inject section 9 (CPU tests feature matrix + test explorer) into 06_PR_TO_CI_VISUAL.html.

Idempotent: replaces content between CPU-TESTS markers on re-run.
"""
import json, os, re, sys, collections

S = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, S)
from areas import area_of  # noqa: E402
from area_meta import AREAS, GROUPS  # noqa: E402

from pathlib import Path as _Path  # noqa: E402
# the page sits in Plan/2026-11/, two levels above outputs/cpu_tests/
PAGE = str(_Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
SRC = os.environ.get("LMCACHE_SRC", os.path.join(S, "src"))
d = json.load(open(os.path.join(S, "cpu_tests.json"), encoding="utf-8"))

def cut(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"

SETUP_COLS = ["mock", "monkeypatch", "fake / stub objects", "torch CPU tensors", "parametrize", "tmp files",
              "threads", "asyncio", "subprocess", "ZMQ socket", "gRPC", "HTTP client", "shared memory", "vLLM import"]

files = []
for f in d["files"]:
    a = area_of(f["path"])
    tests = [[t[0]] if (t[1] == 1 and not t[2] and not t[3]) else ([t[0], t[1]] if (not t[2] and not t[3]) else [t[0], t[1], t[2], cut(t[3], 110)]) for t in f["tests"]]
    files.append([f["path"], a, f["pass"], f["skip"], f["secs"], cut(f["doc"], 180),
                  [s for s in f["setup"] if s in SETUP_COLS], tests, f["loc"]])

GPU_USE = re.compile(r"\.cuda\(|device\s*=\s*[\"']cuda|torch_device_type\s*==\s*[\"']cuda|torch\.cuda\.(Stream|Event|synchronize|current_stream)|cuda_ops|lmcache\.c_ops")


def is_candidate(path, r):
    """Skipped only for lack of a device AND the body does not use GPU tensors/kernels."""
    if "needs an accelerator runtime" not in r:
        return False
    name = path.rsplit("/", 1)[-1]
    if "gpu" in name or "cachegen" in name:
        return False
    try:
        code = open(os.path.join(SRC, path.replace("/", os.sep)), encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    return not GPU_USE.search(code)


def reason(path, why):
    try:
        code = open(os.path.join(SRC, path.replace("/", os.sep)), encoding="utf-8", errors="replace").read()
    except OSError:
        return why, 0
    loc = code.count("\n")
    if "def test_" not in code:
        return "no tests (helper / placeholder)", loc
    if why.startswith("marker"):
        return "accelerator marker (" + why.split(": ")[1] + ") → deselected by -m", loc
    if re.search(r"importorskip", code):
        return "module skip: optional dependency not installed", loc
    if re.search(r"(torch_dev|cuda)\.is_available|device_count\(\)|torch\.cuda", code):
        return "module skip: needs an accelerator runtime", loc
    if re.search(r"os\.environ|getenv", code) and "skip" in code:
        return "module skip: opt-in env var / external service", loc
    return "module skip / deselected", loc

notrun = []
for m in d["notrun"]:
    r, loc = reason(m["path"], m["why"])
    notrun.append([m["path"], area_of(m["path"]), r, loc, cut(m.get("doc", ""), 200),
                   int(is_candidate(m["path"], r)), int(r.startswith("no tests"))])
notrun.sort(key=lambda x: -x[3])

areas = []
for gname, ids in GROUPS:
    for aid in ids:
        fs = [x for x in files if x[1] == aid]
        if not fs and aid == "other":
            continue
        setup = collections.Counter(s for x in fs for s in x[6])
        m = AREAS[aid]
        areas.append(dict(id=aid, group=gname, name=m["name"], what=m["what"], why=m["why"], setup=m["setup"], code=m["code"],
                          files=len(fs), passed=sum(x[2] for x in fs), skipped=sum(x[3] for x in fs),
                          secs=round(sum(x[4] for x in fs)), sm={k: setup.get(k, 0) for k in SETUP_COLS},
                          notrun=sum(1 for n in notrun if n[1] == aid and not n[6])))

tot = dict(files=len(files), passed=sum(x[2] for x in files), skipped=sum(x[3] for x in files),
           secs=round(sum(x[4] for x in files)), funcs=sum(len(x[7]) for x in files), notrun=sum(1 for n in notrun if not n[6]),
           helpers=sum(n[6] for n in notrun), cand=sum(n[5] for n in notrun),
           candloc=sum(n[3] for n in notrun if n[5]))
print(tot)
for a in areas:
    print(f"{a['id']:10s} {a['files']:3d} {a['passed']:5d} {a['secs']:4d}s")

DATA = json.dumps(dict(areas=areas, files=files, notrun=notrun, cols=SETUP_COLS, tot=tot), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

CSS = r"""
/* CPU-TESTS:CSS:START */
.cpu-jobs th,.cpu-jobs td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--grid);font-size:12.5px;vertical-align:top}
.cpu-jobs th{color:var(--text-secondary);font-weight:600;font-size:11.5px}
.cpu-jobs td.r{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.fm th,.fm td{padding:6px 8px;border-bottom:1px solid var(--grid);font-size:12.5px;text-align:left;vertical-align:middle}
.fm th{color:var(--text-secondary);font-weight:600;font-size:11.5px}
.fm tr.grp td{background:var(--surface-2);font-weight:650;font-size:12px;color:var(--text-secondary);letter-spacing:.02em}
.fm tr.ar{cursor:pointer}
.fm tr.ar:hover td,.fm tr.ar:focus td{background:var(--surface-2)}
.fm tr.ar:focus{outline:none}
.fm td.nm{font-weight:600}
.no{display:inline-block;min-width:24px;margin-right:6px;font-size:11px;font-weight:650;color:var(--text-muted);font-variant-numeric:tabular-nums}
.tag .no{min-width:0;margin-right:4px}
.hm td.lab .no{float:left}
.tt td.lm{font-size:11.5px;min-width:260px}
.tt td.lm .lmr{color:var(--text-secondary);font-style:italic;margin-bottom:2px}
.tt td.lm ul{margin:0;padding-left:14px}
.tt td.lm li{margin:1px 0}
.fm td.nm .car{display:inline-block;width:14px;color:var(--text-muted);transition:transform .15s}
.fm tr.open td.nm .car{transform:rotate(90deg)}
.fm td.num{font-variant-numeric:tabular-nums;color:var(--text-secondary);text-align:right;white-space:nowrap}
.hb{display:flex;align-items:center;gap:8px;min-width:150px}
.hb i{display:block;height:12px;border-radius:0 4px 4px 0;min-width:2px}
.hb span{font-size:12px;color:var(--text-secondary);font-variant-numeric:tabular-nums;white-space:nowrap}
.fm tr.det td{background:var(--surface-0);padding:12px 14px 14px}
.det-grid{display:grid;grid-template-columns:110px 1fr;gap:6px 12px;font-size:12.5px}
.det-grid b{color:var(--text-secondary);font-weight:600}
.det-files{margin-top:10px;font-size:12px;color:var(--text-secondary)}
.det-files a{color:var(--series-1);cursor:pointer;text-decoration:none}
.det-files a:hover{text-decoration:underline}
.hm{border-collapse:separate;border-spacing:2px}
.hm th{font-size:11px;color:var(--text-secondary);font-weight:600;padding:2px 4px;vertical-align:bottom;text-align:center}
.hm th.rot{height:96px;white-space:nowrap}
.hm th.rot div{transform:rotate(-55deg);transform-origin:left bottom;width:18px;margin-left:14px}
.hm td{width:40px;height:24px;text-align:center;font-size:11px;border-radius:4px;font-variant-numeric:tabular-nums;cursor:default}
.hm td.lab{width:auto;text-align:right;padding-right:8px;font-size:12px;color:var(--text-primary);white-space:nowrap;background:none}
.hm td.c0{background:var(--surface-2);color:transparent}
.ex-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.ex-bar input,.ex-bar select,.ex-bar button{background:var(--surface-1);color:var(--text-primary);border:1px solid var(--border);border-radius:8px;padding:5px 10px;font:inherit;font-size:12.5px}
.ex-bar input[type=search]{width:300px}
.ex-bar label{font-size:12.5px;color:var(--text-secondary)}
.ex-count{font-size:12px;color:var(--text-muted);margin-left:auto}
.ex-empty{padding:12px 14px;border:1px dashed var(--border);border-radius:9px;color:var(--text-secondary);font-size:13px}
details.tf{margin:0;border-bottom:1px solid var(--grid)}
details.tf>summary{list-style:none;display:grid;grid-template-columns:1fr auto auto auto;gap:12px;align-items:center;padding:7px 4px;color:var(--text-primary);font-size:12.5px}
details.tf>summary::-webkit-details-marker{display:none}
details.tf>summary:hover{background:var(--surface-2)}
details.tf>summary .p{font:12px ui-monospace,Consolas,monospace;word-break:break-all}
details.tf>summary .p::before{content:"▸ ";color:var(--text-muted)}
details.tf[open]>summary .p::before{content:"▾ "}
details.tf>summary .n{font-size:11.5px;color:var(--text-secondary);font-variant-numeric:tabular-nums;white-space:nowrap}
.tf-body{padding:4px 8px 12px 22px;font-size:12.5px}
.tf-body .doc{color:var(--text-secondary);margin:2px 0 8px}
.tf-body .tags{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
.tt th,.tt td{padding:3px 6px;border-bottom:1px solid var(--grid);font-size:12px;text-align:left;vertical-align:top}
.tt th{color:var(--text-secondary);font-weight:600;font-size:11px}
.tt td.fn{font:11.5px ui-monospace,Consolas,monospace;word-break:break-all;width:38%}
.tt td.r{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--text-secondary)}
.tt td.sk{color:var(--warning)}
.nr th,.nr td{padding:5px 8px;border-bottom:1px solid var(--grid);font-size:12px;text-align:left;vertical-align:top}
.nr th{color:var(--text-secondary);font-weight:600;font-size:11.5px}
.nr td.p{font:11.5px ui-monospace,Consolas,monospace;word-break:break-all}
.nr td.r{text-align:right;font-variant-numeric:tabular-nums}
.nr tr.cand td{background:color-mix(in oklab,var(--series-3) 10%,transparent)}
.phase th,.phase td{padding:6px 8px;border-bottom:1px solid var(--grid);font-size:12.5px;text-align:left;vertical-align:top}
.phase th{color:var(--text-secondary);font-weight:600;font-size:11.5px}
.phase td.k{font-weight:600;white-space:nowrap}
.ff th,.ff td{padding:7px 8px;border-bottom:1px solid var(--grid);font-size:12.5px;text-align:left;vertical-align:top}
.ff th{color:var(--text-secondary);font-weight:600;font-size:11.5px}
.ff td.n{font-weight:700;color:var(--text-muted);width:24px}
.slow{display:grid;grid-template-columns:minmax(260px,46%) 1fr 54px;gap:4px 10px;align-items:center;margin-top:8px}
.slow .l{font:11.5px ui-monospace,Consolas,monospace;text-align:right;color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;direction:rtl}
.slow .b{height:12px;border-radius:0 4px 4px 0;background:var(--series-2)}
.slow .v{font-size:12px;color:var(--text-secondary);font-variant-numeric:tabular-nums}
/* CPU-TESTS:CSS:END */
"""

HTML = r"""
<!-- CPU-TESTS:START -->
<section class="card" id="cpu">
  <div class="head"><h2>9 · CPU tests: what they check, why they exist, how they are set up</h2>
  <p class="sub">Fast-fail needs to know what each CPU test protects. Source: GitHub Actions <b>Test</b> run <code>42189301949</code> (PR commit <code>05d8eb84</code>, 2026-11-06 snapshot), job <code>test: 3.12</code>; workflow config as on dev 2026-11-27. Every test name, pass/skip and time comes from the pytest log (<code>log_cli=true</code>); "what it checks" comes from the test docstrings. Feature areas and "why" are my grouping.</p></div>
  <div class="tiles" id="cpuTiles"></div>
</section>

<section class="card">
  <div class="head"><h2>9a · Which CI jobs run CPU tests</h2>
  <p class="sub">All are GitHub Actions on hosted runners (no GPU). Required checks on <code>dev</code> are DCO, Check code quality, buildkite/k3-unit-tests and buildkite/k3-multiprocess-test (tasks_2026-11-05/C) — none of the jobs below is required for merge.</p></div>
  <table class="cpu-jobs">
    <thead><tr><th>Job (workflow)</th><th>When it runs</th><th>What it runs</th><th>Setup</th><th class="r">Time</th><th>Blocks</th></tr></thead>
    <tbody>
      <tr><td><b>test: 3.11 … 3.14</b><br><small>test.yml</small></td><td>Started by Check code quality (#6730) on PRs touching <code>**.py</code>, <code>pyproject.toml</code>, <code>requirements/**</code>; drafts run 3.12 only. Also called by <code>publish.yml</code> on release.</td><td><code>pytest -m "not (cuda or musa or xpu or npu or neuron or rbln)"</code> from repo root → <b>everything in this section</b> (tests/ + examples/)</td><td>free disk 136 s · <code>pip install vllm</code> + requirements + <code>NO_GPU_EXT=1 pip install -e .</code> 200 s · FFmpeg</td><td class="r">≈19 min<br><small>× 4 versions</small></td><td>Release publish (needs <code>test</code> success)</td></tr>
      <tr><td><b>gRPC native server tests</b><br><small>test.yml</small></td><td>same filter as above</td><td>4 files: grpc_native_server, grpc_transport, grpc_real_server, worker_liveness</td><td>Python 3.12 + <code>pygrpc-native==0.7.0</code> (native gRPC only installed here)</td><td class="r">≈4 min</td><td>—</td></tr>
      <tr><td><b>Token dropping: allocator (vLLM 0.25.1)</b><br><small>test.yml</small></td><td>token-drop paths changed</td><td><code>tests/v1/test_token_drop_allocator_adapter.py</code></td><td>pinned <code>vllm==0.25.1</code> (asserts the version)</td><td class="r">short</td><td>—</td></tr>
      <tr><td><b>raw-block temp-file tests</b><br><small>test.yml</small></td><td><code>rust/raw_block/**</code>, raw-block adapters changed</td><td>raw_block test_device, test_core, multiprocess test_raw_block_l2_adapter</td><td>Rust toolchain + <code>maturin build</code> of the raw-block extension</td><td class="r">short</td><td>—</td></tr>
      <tr><td><b>Rust unit tests</b><br><small>test.yml</small></td><td>same as raw-block</td><td><code>cargo test</code> for <code>rust/raw_block</code></td><td>Rust toolchain</td><td class="r">short</td><td>—</td></tr>
      <tr><td><b>HF3FS connector native tests</b><br><small>test.yml</small></td><td>HF3FS C++ sources changed</td><td>C++ connector against an SDK double (<code>tests/native/storage_backends/hf3fs/run_tests.py</code>)</td><td>libabsl-dev</td><td class="r">short</td><td>—</td></tr>
      <tr><td><b>CPU device</b> (6 legs)<br><small>cpu_device.yml</small></td><td>PR, lmcache sources changed</td><td>Real <b>vLLM CPU</b> + LMCache server end to end: server bench (2 modes) + vLLM e2e (3 transfer modes) + cache-hit checks — see 9e</td><td>vLLM CPU nightly (resolved pinned), LMCache CPU install, model from GitHub release tarball; Ubuntu 22.04 + macOS; opt-125m + DeepSeek-V2-Lite (dummy, 2 layers); grpc / grpc-aio / grpc-native</td><td class="r">10.6–16 min<br><small>per leg</small></td><td>—</td></tr>
    </tbody>
  </table>
</section>

<section class="card">
  <div class="head"><h2>9b · Feature matrix: CPU tests per LMCache feature</h2>
  <p class="sub">One row per feature area, grouped by layer. Click a row for <b>what it checks · why it must exist · how tests are set up · main code</b>, and its files. "Not on CPU" = test files of this area that never run in this job (GPU-only or skipped at import).</p></div>
  <table class="fm" id="fm">
    <thead><tr><th>Feature area</th><th>Tests passed</th><th>Time in job</th><th class="num">Files</th><th class="num">Skipped</th><th class="num">Not on CPU</th></tr></thead>
    <tbody></tbody>
  </table>
  <p class="note">Tests passed counts every parametrized case. Time = wall time between results in the log (serial run), so fixture setup is included. About 50 more skips are whole-module skips that the log does not itemize (no <code>-rs</code>).</p>
</section>

<section class="card">
  <div class="head"><h2>9c · Setup matrix: how each feature area builds its test world</h2>
  <p class="sub">Cell = number of test files in the area that use the technique (darker = larger share of the area's files). Read across a row to see what a test in that area needs; read down a column to see where e.g. real sockets or subprocesses are used — those are where port / timing flakes come from.</p></div>
  <div style="overflow-x:auto;padding-right:80px"><table class="hm" id="hm"></table></div>
  <div class="legend" id="hmLegend"></div>
  <p class="note">Detected by regex on each test file's source (e.g. <code>MagicMock</code>, <code>monkeypatch</code>, <code>zmq</code>, <code>subprocess</code>, <code>TestClient</code>, <code>from vllm</code>). A match means the file uses it somewhere, not every test.</p>
</section>

<section class="card">
  <div class="head"><h2>9d · Test case explorer</h2>
  <p class="sub">Every file and test function that ran on CPU. Search matches path, test name and docstring. Open a file to see its docstring, setup tags and each test with its docstring (runs = parametrized cases).</p></div>
  <div class="ex-bar">
    <label class="ux-sr" for="exQ">Search tests</label><input type="search" id="exQ" placeholder="Search: eviction, lora, shm, restart, quota…">
    <label class="ux-sr" for="exA">Feature area</label><select id="exA"><option value="">All feature areas</option></select>
    <label><input type="checkbox" id="exSk"> only files with skips</label>
    <label class="ux-sr" for="exSort">Sort tests</label><select id="exSort"><option value="area">Sort: by area</option><option value="secs">Sort: slowest first</option><option value="tests">Sort: most tests</option></select>
    <span class="ex-count" id="exN"></span>
  </div>
  <div id="exList"></div>
  <div style="margin-top:10px"><button type="button" id="exMore" class="theme">Show more</button></div>
</section>

<section class="card">
  <div class="head"><h2>9e · CPU device E2E (cpu_device.yml): what the real-engine CPU check does</h2>
  <p class="sub">The only PR-time check that runs a real vLLM with LMCache, on CPU. Script: <code>.github/scripts/cpu_device_test.sh</code> → <code>run-cpu-e2e-validation.sh</code>.</p></div>
  <table class="phase">
    <thead><tr><th>Step</th><th>What happens</th><th>What it proves</th></tr></thead>
    <tbody>
      <tr><td class="k">Server bench ×2</td><td><code>lmcache bench server</code> in LMCache-driven and engine-driven transfer mode. No model.</td><td>Server KV store/retrieve path works without any engine.</td></tr>
      <tr><td class="k">P2 · 3–4</td><td>Start LMCache server, then <code>vllm serve</code> (opt-125m or DeepSeek-V2-Lite dummy with MLA) with the LMCache MP connector.</td><td>Connector loads in a real vLLM; server and engine can talk (zmq / grpc / grpc-aio / grpc-native).</td></tr>
      <tr><td class="k">P2 · 5–5.5</td><td>Send a request; check the worker really used the expected transport (inline / shm / LMCache-driven).</td><td>The chosen data path is the one exercised (no silent fallback).</td></tr>
      <tr><td class="k">P3 · 1–4</td><td>Reset metrics; request A twice.</td><td>First call stores, second call is an LMCache <b>hit</b>.</td></tr>
      <tr><td class="k">P3 · 5–7</td><td>Reset vLLM's external prefix cache; request A again, then again.</td><td>Miss + store after reset, hit after repopulation.</td></tr>
      <tr><td class="k">P3 · 8–10</td><td>Restart vLLM (instance 2); request A; compare outputs.</td><td>KV survives an engine restart and gives the <b>same output</b>.</td></tr>
      <tr><td class="k">P3 · 11</td><td>Request B (different prompt).</td><td>No false hit.</td></tr>
    </tbody>
  </table>
  <p class="note">6 legs on dev (2026-11-27): Ubuntu + macOS × opt-125m / DeepSeek-V2-Lite over grpc, plus Ubuntu grpc-aio and grpc-native.</p>
</section>

<section class="card">
  <div class="head"><h2>9f · Test files that never run on CPU</h2>
  <p class="sub">Deselected by a GPU marker, or skipped at import (no accelerator, optional dependency, opt-in service). <span class="tag" style="background:color-mix(in oklab,var(--series-3) 18%,transparent)">green rows</span> = skipped only because no accelerator is present, but the area is host-side logic → candidates to make CPU-runnable.</p></div>
  <div style="max-height:460px;overflow:auto"><table class="nr" id="nr"><thead><tr><th>File</th><th>Area</th><th>Why it does not run</th><th class="r">Lines</th></tr></thead><tbody></tbody></table></div>
</section>

<section class="card">
  <div class="head"><h2>9g · What this means for fail-fast</h2></div>
  <table class="ff">
    <thead><tr><th></th><th>Finding</th><th>Evidence</th><th>Next step</th></tr></thead>
    <tbody>
      <tr><td class="n">1</td><td>The CPU <b>Test</b> job is not a merge-required check, but <code>publish.yml</code> needs it. A flaky CPU test blocks a <b>release</b>, not a merge.</td><td>publish.yml <code>needs.test.result == 'success'</code>; required checks list (task C)</td><td>Decide: make it required (then it must be stable) or keep it advisory + rerun policy for release.</td></tr>
      <tr><td class="n">2</td><td>Matrix fail-fast already works: when one Python version fails, the others are cancelled.</td><td>40 failed runs: each version shows ~30 "cancelled" (default <code>fail-fast: true</code>)</td><td>Nothing to add inside the matrix. Gain is in cross-workflow cancel (task C).</td></tr>
      <tr><td class="n">3</td><td>Failures are not Python-version specific. Four classes: dev-wide broken test (<code>tests/cli/test_profiling.py</code>, 2 tests, 20/25 sampled failures), real PR bugs (lazy_offload AttributeError), port collision (<code>ZMQError: Address already in use</code>), missing module.</td><td>gh run logs, 2026-11-04 → 06; 11-05: 43 fail / 41 pass</td><td>"Remove flaky" = quarantine list for classes 1+3 only; keep real-bug failures blocking.</td></tr>
      <tr><td class="n">4</td><td>Each version costs ≈19 min: 136 s free disk + 200 s install + 751 s pytest. 4 versions ≈ 76 runner-min per push (drafts: 3.12 only).</td><td>job 127850987819 step timings</td><td>PR: run 2 versions (oldest + newest), release: all 4.</td></tr>
      <tr><td class="n">5</td><td>A unit test calls the real internet: <code>test_create_workload.py</code> → huggingface.co (401 responses).</td><td>13 HTTP requests in the log during that file</td><td>Mock the tokenizer download; network = flake source.</td></tr>
      <tr><td class="n">6</td><td>The biggest storage-logic suites skip on CPU only because no accelerator is present: <code>test_l1_manager.py</code> (2,532 lines), <code>test_prefetch_controller.py</code> (1,927), <code>test_distributed_storage_manager.py</code> (1,279), <code>test_store_controller.py</code> (802) ≈ 6.5k lines of host-side logic tests that only run on GPU CI.</td><td>module-level <code>pytest.skip</code> on <code>torch_dev.is_available()</code></td><td>Input for task 2 (CPU logic tests): make host-memory logic run with CPU tensors.</td></tr>
      <tr><td class="n">7</td><td>The slowest file is slow because of fixed waits: 14 tests in <code>test_prefix_suffix_tuner.py</code> each take exactly 5.0 s (warmup / two-pass ordering / full run) = 70 s.</td><td>gaps of 5.007 s between results in the log</td><td>Inject a short timeout in tests; easy −1 min per version.</td></tr>
      <tr><td class="n">8</td><td>pytest has no <code>testpaths</code>, so it also collects <code>examples/</code> from the repo root.</td><td>18 results from <code>examples/lmc_external_l2_adapter/tests</code></td><td>Fine today; note it when splitting tiers.</td></tr>
    </tbody>
  </table>
  <h2 style="margin-top:18px;font-size:14px">Slowest 15 test files in the job</h2>
  <div class="slow" id="slow"></div>
</section>
<!-- CPU-TESTS:END -->
"""

JS = r"""
<!-- CPU-TESTS:JS:START -->
<script id="cpuData" type="application/json">__DATA__</script>
<script>
(function(){
  const D=JSON.parse(document.getElementById('cpuData').textContent);
  const $=s=>document.querySelector(s);
  const el=(t,a={},x)=>{const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k==='style')e.style.cssText=v;else if(k==='class')e.className=v;else e.setAttribute(k,v);}if(x!==undefined)e.textContent=x;return e;};
  const fmt=n=>n.toLocaleString('en-US');
  const AN=Object.fromEntries(D.areas.map(a=>[a.id,a.name]));
  // numbering: group 1..N, area g.i (e.g. 2.3) — number lives in its own span so the name still translates
  const GN={},AC={};{let gi=0,ii=0,last=null;D.areas.forEach(a=>{if(a.group!==last){last=a.group;gi++;ii=0;GN[a.group]=String(gi);}AC[a.id]=gi+'.'+(++ii);});}
  const NO=t=>el('span',{class:'no'},t);
  const areaLabel=id=>{const sp=el('span');sp.append(NO(AC[id]||''),document.createTextNode(AN[id]||id));return sp;};
  const tip=$('#tip');
  function showTip(e,v,t,m){tip.replaceChildren(el('div',{class:'tv'},v),el('div',{},t));if(m)tip.appendChild(el('div',{class:'tm'},m));tip.style.display='block';let x=e.clientX+14,y=e.clientY+14;if(e.type==='focus'){const r=e.target.getBoundingClientRect();x=r.left;y=r.bottom+6;}const w=tip.offsetWidth,h=tip.offsetHeight;if(x+w>innerWidth-8)x=innerWidth-w-8;if(y+h>innerHeight-8)y=y-h-28;tip.style.left=x+'px';tip.style.top=y+'px';}
  const hide=()=>{tip.style.display='none'};
  function tipOn(n,v,t,m){n.addEventListener('pointermove',e=>showTip(e,v,t,m));n.addEventListener('pointerleave',hide);n.addEventListener('focus',e=>showTip(e,v,t,m));n.addEventListener('blur',hide);}

  // tiles
  const T=D.tot, tiles=[
    [fmt(T.passed),'tests on CPU (GHA, advisory)','required GPU unit pod: 10,258','cpu/explore'],
    [`${D.areas.length} areas`,`${T.files} test files`,'feature matrix','cpu/tiers'],
    ['18 vs 49 min','CPU job vs required GPU unit pod','same tests · early-fail chance','cpu/cost'],
    ['≈76 min','runner time per push','4 Python versions (drafts: 3.12)','cpu/cost'],
    [`${T.notrun} files`,'excluded from CPU',`${T.cand} CPU-portable (≈${(T.candloc/1000).toFixed(1)}k lines)`,'cpu/tiers'],
  ];
  const tw=$('#cpuTiles'); tiles.forEach(([v,l,s,g],i)=>{const t=el('div',{class:'tile'+(i===0?' hl':'')});if(g){t.dataset.goto=g;t.tabIndex=0;t.setAttribute('role','link');}t.append(el('div',{class:'v'},v),el('div',{class:'l'},l),el('div',{class:'s'},s));tw.appendChild(t);});

  // feature matrix
  const maxP=Math.max(...D.areas.map(a=>a.passed)), maxS=Math.max(...D.areas.map(a=>a.secs));
  const tb=$('#fm tbody'); let lastG='';
  D.areas.forEach(a=>{
    if(a.group!==lastG){lastG=a.group;const g=el('tr',{class:'grp'}),gt=el('td',{colspan:'6'});gt.append(NO(GN[a.group]),document.createTextNode(a.group));g.appendChild(gt);tb.appendChild(g);}
    const tr=el('tr',{class:'ar','data-area':a.id,tabindex:'0','aria-expanded':'false'});
    const nm=el('td',{class:'nm'});nm.append(el('span',{class:'car'},'▸'),NO(AC[a.id]),document.createTextNode(a.name));
    const c1=el('td'),b1=el('div',{class:'hb'});b1.append(el('i',{style:`width:${Math.max(2,140*a.passed/maxP)}px;background:var(--series-1)`}),el('span',{},fmt(a.passed)));c1.appendChild(b1);
    const c2=el('td'),b2=el('div',{class:'hb'});b2.append(el('i',{style:`width:${Math.max(2,110*a.secs/maxS)}px;background:var(--series-2)`}),el('span',{},a.secs+' s'));c2.appendChild(b2);
    tr.append(nm,c1,c2,el('td',{class:'num'},a.files),el('td',{class:'num'},a.skipped||'—'),el('td',{class:'num'},a.notrun||'—'));
    tipOn(b1,fmt(a.passed)+' tests',a.name,`${a.files} files · ${a.skipped} skipped`);
    tipOn(b2,a.secs+' s',a.name,`${(100*a.secs/T.secs).toFixed(1)}% of pytest time`);
    const det=el('tr',{class:'det',hidden:''}),dc=el('td',{colspan:'6'}),g=el('div',{class:'det-grid'});
    [['What it checks',a.what],['Why it must exist',a.why],['How it is set up',a.setup],['Main code',a.code]].forEach(([k,v])=>{g.append(el('b',{},k),el('div',{},v));});
    dc.appendChild(g);
    const fl=el('div',{class:'det-files'});fl.appendChild(document.createTextNode('Files: '));
    D.files.filter(f=>f[1]===a.id).sort((x,y)=>y[2]-x[2]).forEach((f,i)=>{if(i)fl.appendChild(document.createTextNode(' · '));const l=el('a',{},f[0].replace(/^tests\//,'').replace(/\.py$/,'')+` (${f[2]})`);l.addEventListener('click',ev=>{ev.stopPropagation();openFile(f[0]);});fl.appendChild(l);});
    dc.appendChild(fl);const gb=el('button',{class:'goto-btn',type:'button'},`See all ${a.files} files and ${fmt(a.passed)} tests in the Test explorer →`);gb.addEventListener('click',ev=>{ev.stopPropagation();openArea(a.id);});dc.appendChild(gb);det.appendChild(dc);
    const tog=()=>{const o=det.hidden;det.hidden=!o;tr.classList.toggle('open',o);tr.setAttribute('aria-expanded',String(o));};
    tr.addEventListener('click',tog);tr.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();tog();}});
    tb.append(tr,det);
  });

  // setup heatmap
  const hm=$('#hm'),hr=el('tr');hr.appendChild(el('th'));
  D.cols.forEach(c=>{const th=el('th',{class:'rot'});th.appendChild(el('div',{},c));hr.appendChild(th);});hm.appendChild(hr);
  const bins=[0,.2,.4,.6,.8], mix=[18,34,52,72,92];
  D.areas.forEach(a=>{const r=el('tr'),lb=el('td',{class:'lab'});lb.append(NO(AC[a.id]),document.createTextNode(a.name));r.appendChild(lb);
    D.cols.forEach(c=>{const n=a.sm[c],sh=a.files?n/a.files:0;const td=el('td',{tabindex:'0'},n?String(n):'');
      if(!n){td.className='c0';}else{let b=0;bins.forEach((v,i)=>{if(sh>v)b=i;});td.style.background=`color-mix(in oklab, var(--seq-600) ${mix[b]}%, var(--surface-1))`;td.style.color=b>=2?'var(--surface-1)':'var(--text-primary)';}
      tipOn(td,`${n} of ${a.files} files`,`${a.name} · ${c}`,`${Math.round(100*sh)}% of the area's files`);r.appendChild(td);});
    hm.appendChild(r);});
  const lg=$('#hmLegend');lg.appendChild(document.createTextNode('Share of area files:'));
  ['0%','≤20%','≤40%','≤60%','≤80%','>80%'].forEach((t,i)=>{const s=el('span');const sw=el('i',{class:'sw',style:i?`background:color-mix(in oklab, var(--seq-600) ${mix[i-1]}%, var(--surface-1))`:'background:var(--surface-2)'});s.append(sw,document.createTextNode(t));lg.appendChild(s);});

  // explorer
  const sel=$('#exA');D.areas.forEach(a=>sel.appendChild(el('option',{value:a.id},`${AC[a.id]} · ${a.name}`)));
  const order=Object.fromEntries(D.areas.map((a,i)=>[a.id,i]));
  let shown=60,cur=[];
  // "LMCache meaning": area role + up to 3 glossary concepts found in test name / docstring
  const GL=D.gloss, GC=GL.concepts.map(([re,en,vi])=>[new RegExp(re),en,vi]);
  const CUR={};D.curated.rows.forEach(r=>{const m=r[1].match(/^(tests\/\S+?\.py)::.*?(test_\w+)$/);if(m)CUR[m[1]+'|'+m[2]]=r;});
  const curOf=(f,x)=>CUR[f[0]+'|'+x[0].replace(/^.*::/,'').replace(/\[.*$/,'')];
  function lmCell(f,x){const cr=curOf(f,x);if(cr){const v=window.I18N&&I18N.lang==='vi'?1:0;const td=el('td',{class:'lm cur'});td.append(el('div',{},cr[3+v]),el('div',{class:'lmr'},'→ '+cr[5+v]));return td;}const vi=window.I18N&&I18N.lang==='vi',i=vi?1:0;const role=(GL.roles[f[1]]||GL.roles.other)[i];
    const txt=(x[0].replace(/^.*::/,'').replace(/_/g,' ')+' '+(x[3]||'')).toLowerCase();const hit=[];
    for(const c of GC){if(hit.length>=3)break;if(c[0].test(txt))hit.push(c[vi?2:1]);}
    const td=el('td',{class:'lm'});td.appendChild(el('div',{class:'lmr'},role));
    if(hit.length){const ul=el('ul');hit.forEach(h=>ul.appendChild(el('li',{},h)));td.appendChild(ul);}return td;}
  addEventListener('langchange',()=>{const open=[...document.querySelectorAll('details.tf[open]')].map(d=>d.dataset.path);render();
    open.forEach(p=>{const d=document.querySelector(`details.tf[data-path="${CSS.escape(p)}"]`);if(d)d.open=true;});});
  function fileNode(f){
    const d=el('details',{class:'tf','data-path':f[0]}),s=el('summary');
    s.append(el('span',{class:'p'},f[0]),(()=>{const tg=el('span',{class:'tag'});tg.append(NO(AC[f[1]]||''),document.createTextNode(AN[f[1]]||f[1]));return tg;})(),el('span',{class:'n'},`${f[2]} passed${f[3]?' · '+f[3]+' skipped':''}`),el('span',{class:'n'},f[4].toFixed(1)+' s'));
    d.appendChild(s);
    d.addEventListener('toggle',()=>{if(!d.open||d.dataset.r)return;d.dataset.r=1;const b=el('div',{class:'tf-body'});
      b.appendChild(el('div',{class:'doc'},f[5]||'(no module docstring)'));
      const tg=el('div',{class:'tags'});(f[6].length?f[6]:['pure Python']).forEach(x=>tg.appendChild(el('span',{class:'tag'},x)));tg.appendChild(el('span',{class:'tag'},f[8]+' lines'));b.appendChild(tg);
      const t=el('table',{class:'tt'}),h=el('tr');['Test','Runs','Skipped','What it checks (docstring; grey = from the test name)','LMCache meaning (auto, from glossary)'].forEach(x=>h.appendChild(el('th',{},x)));t.appendChild(h);
      f[7].forEach(x=>{const r=el('tr'),fn=el('td',{class:'fn'});if(curOf(f,x))fn.appendChild(el('span',{class:'star',title:'hand-written (gate-critical)'},'★'));fn.appendChild(document.createTextNode(x[0]));r.append(fn,el('td',{class:'r'},x[1]||1),el('td',{class:'r'+(x[2]?' sk':'')},x[2]||''),(x[3]?el('td',{},x[3]):el('td',{style:'color:var(--text-muted)'},x[0].replace(/^.*::/,'').replace(/^test_/,'').replace(/_/g,' '))),lmCell(f,x));t.appendChild(r);});
      b.appendChild(t);d.appendChild(b);});
    return d;}
  function render(){
    const q=$('#exQ').value.trim().toLowerCase(),a=sel.value,sk=$('#exSk').checked,gc=$('#exCur').checked,so=$('#exSort').value;
    cur=D.files.filter(f=>(!a||f[1]===a)&&(!sk||f[3]>0)&&(!gc||f[7].some(t=>curOf(f,t)))&&(!q||f[0].toLowerCase().includes(q)||f[5].toLowerCase().includes(q)||f[7].some(t=>t[0].toLowerCase().includes(q)||(t[3]||'').toLowerCase().includes(q))));
    cur.sort(so==='secs'?(x,y)=>y[4]-x[4]:so==='tests'?(x,y)=>y[2]-x[2]:(x,y)=>(order[x[1]]-order[y[1]])||x[0].localeCompare(y[0]));
    const L=$('#exList');L.replaceChildren();cur.slice(0,shown).forEach(f=>L.appendChild(fileNode(f)));
    if(!cur.length&&q){const nr=D.notrun.find(n=>n[0].toLowerCase()===q||n[0].toLowerCase().endsWith('/'+q));
      const box=el('div',{class:'ex-empty'});
      if(nr){const a=el('a',{href:'#cpu/tiers'},'see section 5 · CPU-excluded suites');box.append(el('span',{},'Not run on CPU: '),el('code',{},nr[0]),el('code',{},' · '+nr[2]+' · '),a);}
      else box.textContent='No file matches. This explorer only lists the files that ran in one CPU job (commit 05d8eb84, 2026-11-06). GPU-only tests and files added later are not here.';
      L.appendChild(box);}
    const nt=cur.reduce((s,f)=>s+f[2],0);$('#exN').textContent=`${cur.length} files · ${fmt(nt)} tests passed${cur.length>shown?` · showing ${shown}`:''}`;
    $('#exMore').hidden=cur.length<=shown;}
  ['#exQ','#exA','#exSk','#exCur','#exSort'].forEach(s=>$(s).addEventListener('input',e=>{if(e.target.id==='exCur'&&e.target.checked)$('#gcFold').open=true;shown=60;render();}));
  $('#exMore').addEventListener('click',()=>{shown+=120;render();});
  function openArea(id){$('#exQ').value='';sel.value=id;$('#exSk').checked=false;$('#exCur').checked=false;shown=60;render();if(window.vizNav)vizNav.show('cpu','explore');}
  window.cpuOpenFile=p=>openFile(p);
  function openFile(p){if(window.vizNav)vizNav.show('cpu','explore',false);$('#exQ').value=p;sel.value='';$('#exSk').checked=false;$('#exCur').checked=false;shown=60;render();const d=document.querySelector(`details.tf[data-path="${CSS.escape(p)}"]`);if(d){d.open=true;d.scrollIntoView({behavior:'smooth',block:'center'});}}
  render();

__JSADD__
  // not run
  $('#nrSub').textContent=`${T.notrun} test files (+${T.helpers} helper files) that never run on the CPU job.`;   // the CPU-portable takeaway is in gates.py DESC
  function drawNR(){const nb=$('#nr tbody');nb.replaceChildren();const oc=$('#nrCand').checked,oh=$('#nrHelp').checked;
    D.notrun.filter(n=>(!oc||n[5])&&(oh||!n[6])).forEach(n=>{const r=el('tr',{class:n[5]?'cand':''});
      const p=el('td',{class:'p'},n[0]);if(n[4])p.title=n[4];const c=el('td',{class:'cd'});if(n[5])c.appendChild(el('span',{class:'badge fix'},'✓ portable'));
      r.append(p,(()=>{const td=el('td');td.appendChild(areaLabel(n[1]));return td;})(),el('td',{},n[2]),c,el('td',{class:'r'},fmt(n[3])));nb.appendChild(r);});}
  ['#nrCand','#nrHelp'].forEach(x=>$(x).addEventListener('change',drawNR));drawNR();

  // slowest files
  const sl=$('#slow'),top=[...D.files].sort((x,y)=>y[4]-x[4]).slice(0,15),mx=top[0][4];
  top.forEach(f=>{const l=el('div',{class:'l',title:f[0]},f[0].replace(/^tests\//,'')),t=el('div'),b=el('div',{class:'b',style:`width:${Math.max(2,100*f[4]/mx)}%`});t.appendChild(b);
    tipOn(b,f[4].toFixed(1)+' s',f[0],`${AN[f[1]]} · ${f[2]} tests`);sl.append(l,t,el('div',{class:'v'},f[4].toFixed(0)+' s'));});
})();
</script>
<!-- CPU-TESTS:JS:END -->
"""

from section9_html import HTML, CSS_ADD, FINDINGS, JS_ADD  # noqa: E402
from lmcache_glossary import AREA_ROLE, CONCEPTS  # noqa: E402
from curated_tests import CURATED, TIERS  # noqa: E402
CSS = CSS.replace("/* CPU-TESTS:CSS:END */", CSS_ADD + "/* CPU-TESTS:CSS:END */")
JS = JS.replace("__JSADD__", JS_ADD)
DATA = json.dumps(dict(areas=areas, files=files, notrun=notrun, cols=SETUP_COLS, tot=tot, findings=FINDINGS, gloss=dict(roles=AREA_ROLE, concepts=CONCEPTS), curated=dict(tiers=TIERS, rows=CURATED)),
                  ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

page = open(PAGE, encoding="utf-8").read()

def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor)
    return page[:i] + block.strip() + "\n" + page[i:] if before else page

page = put(page, "/* CPU-TESTS:CSS:START */", "/* CPU-TESTS:CSS:END */", CSS, "@media (max-width:980px)")
# CPU view comes first: always (re)insert the block right before the GPU KPI tiles.
page = re.sub(r"\n?<!-- CPU-TESTS:START -->.*?<!-- CPU-TESTS:END -->\n?", "\n", page, flags=re.S)
page = put(page, "<!-- CPU-TESTS:START -->", "<!-- CPU-TESTS:END -->", HTML, "<!-- KPI tiles -->")
page = put(page, "<!-- CPU-TESTS:JS:START -->", "<!-- CPU-TESTS:JS:END -->", JS.replace("__DATA__", DATA), "</body>")
open(PAGE, "w", encoding="utf-8").write(page)
print("page bytes", len(page.encode("utf-8")))
import build_nav  # noqa: E402
build_nav.main()
import build_gates  # noqa: E402
build_gates.main()
import build_onboarding  # noqa: E402
build_onboarding.main()
import build_observe  # noqa: E402
build_observe.main()
import build_entities  # noqa: E402  (v2 entity index; build_trace_dirs.py retired 2026-11-13)
build_entities.main()
import build_ops_tabs  # noqa: E402  (Coming release / Optimal CI / 24h overlap + Trace Agent cards)
build_ops_tabs.main()
import build_report1130  # noqa: E402  (Report 1130: LM-1130 baseline + retry waste)
build_report1130.main()
import build_today  # noqa: E402  (v2: Today tab + verdict per release, decisions.py)
build_today.main()
import build_desk  # noqa: E402  (2026-11-15: Now · Release Desk + History tabs from ops-app)
build_desk.main()
import build_weekly  # noqa: E402  (2026-11-26: Weekly full build tab #obs/weekly from ops-app collect_weekly.py)
build_weekly.main()
import build_impact  # noqa: E402  (2026-11-26: CI impact tab #obs/impact, before / after #6730 #6731 #6854)
build_impact.main()
import build_entity_ui  # noqa: E402  (v2: entity card + linkify + link health)
build_entity_ui.main()
import build_pr_map  # noqa: E402  (2026-11-16: PR map overlay: critical path + feature matrix + linked PRs; 6A click + drawer button)
build_pr_map.main()
import build_pr_inspector  # noqa: E402  (2026-11-24: PR Inspector drawer: forward / backward, 5 views, checklist + gates)
build_pr_inspector.main()
import build_research  # noqa: E402  (2026-11-24: Research intake: research_intake/inbox -> 3 report contexts)
build_research.main()
import build_ux  # noqa: E402  (2026-11-24: UX layer: design system, decision banner, search, keyboard, print view)
build_ux.main()
import build_i18n  # noqa: E402
build_i18n.main()
build_ux.sync_p1()   # 2026-11-25 expert review C2: hard-coded P1 figures follow the data
