# Review of 06_PR_TO_CI_VISUAL.html (reviewer: ponytail, 2026-11-06)

Scratch evidence (logs, parsers, screenshots): `<home>\AppData\Local\Temp\claude\82ff7c0a8b56703b\3433c8f2-048a-4018-b935-572463e58c3c\scratchpad\ponytail\` (`job312.log`, `runs/*.log`, `jobs/*.json`, `areas_list.txt`, `*.png`) and `..\scratchpad\myparse2.py`.

## 1. Verdict

**You can trust the page for the numbers. You cannot yet trust it as the model of "what gates a merge".** I checked the Buildkite numbers (P1/P8) and the CPU pass counts myself and they match the sources. Most 9g findings hold up. The big problem is the tier model. The page treats "L1 unit = CPU GitHub Actions `Test`". But the unit-test check that actually blocks a merge is **Buildkite `k3-unit-tests`, which runs on 1 GPU**. The page never describes it, and P8's own tier definition includes it. Fix these 3 things first:
1. Add Buildkite `k3-unit-tests` (1 GPU, whole `tests/`, `--maxfail=1`) as its own tier in 3/3b/4/8. Show how it overlaps with GHA `Test`.
2. Fix 9e: it says it is "the only PR-time real-vLLM check on CPU". That is false, and it conflicts with 3b. The Buildkite `cpu_e2e_validation` workload runs the same script on every MP build.
3. Fix the L1 example and the 9f "green" candidates. Both use GPU-only tests (`test_cache_server.py`, `test_gpu_connector.py`, ...) as if they were CPU tests.

Counts: 3 blockers, 9 major, 13 minor.

## 2. Findings table

| # | Severity | Section | Claim on page | What is actually true | Evidence | Fix |
|---|---|---|---|---|---|---|
| F1 | blocker | 3, 3b, 4, 8 (L1 tier) | L1 unit = "CPU · minutes (GHA, py3.10–3.13)". The staircase colors it CPU-only. | The merge-required unit check is `buildkite/k3-unit-tests`. It runs on a pod with 1 GPU (`nvidia.com/gpu: "1"`), covers all of `tests/` incl. cuda-marked files, uses `--maxfail=1`, and installs no vLLM. GHA `Test` is **not** required. P8 itself defines L1 as "GHA test.yml CPU + Buildkite unit pod 1 GPU" and has a separate `L1_gpu_kernels`. The page dropped both. | `.buildkite/k3_tests/unit/pipeline.yml` (05d8eb84) limits; `unit/run.sh:38-44`; `gh api repos/LMCache/LMCache/branches/dev` → required = DCO, Check code quality, buildkite/k3-multiprocess-test, buildkite/k3-unit-tests; `outputs/P8/ci_rule_shadow.py:20-21` | Split L1 into "L1-CPU (GHA Test, advisory)" and "L1-GPU unit pod (required, 1 GPU)". Add the second to the matrix in 4. The `kernel` row needs it (P8 §3: "L1 GPU kernels (unit pod)"). |
| F2 | blocker | 9e vs 3/3b | 9e: cpu_device.yml is "the only PR-time check that runs a real vLLM with LMCache, on CPU". 3b: CPU E2E = `cpu_e2e_validation`, ~3.6 min. | They are two jobs that run the **same script**. Buildkite MP `cpu_e2e_validation` runs `.github/scripts/run-cpu-e2e-validation.sh` (1,034 runs in 30 d, inside the required `k3-multiprocess-test`). GHA cpu_device.yml runs it too, in 7 legs, 10.6–16 min each, and is not required. The two halves describe different jobs under one tier name. | `.buildkite/k3_tests/multiprocess/pipeline.yml:505-515`; `.github/workflows/cpu_device.yml:81`; `P1/cost_by_workload.csv` row `cpu_e2e_validation` (gpus 0, runs 1034, p50 3.64) | In 9e, say which job is the gate. Merge both into one "CPU E2E" story with two runners (Buildkite = required, 3 transfer modes; GHA = advisory, macOS + MLA + gRPC legs). |
| F3 | blocker | 3b, 8 (L1 example) | L1 example: `test_store_and_lookup` in `tests/v1/multiprocess/test_cache_server.py`. The mindmap L1 node uses this file and says "CPU (GHA test.yml)". | The file has `pytestmark = pytest.mark.cuda`. It is deselected on CPU and listed in the page's own 9f ("marker: cuda"). It only runs in k3-unit-tests (GPU). | `git show fcd50cea:tests/v1/multiprocess/test_cache_server.py` line 38 (same at 05d8eb84); 9f data | Use a CPU-run example (e.g. `tests/v1/multiprocess/test_free_locks.py`, `test_token_hasher.py`), or label this one "L1-GPU". |
| F4 | major | 9f green rows | Green rows are "skipped only because no accelerator… host-side logic → candidates to make CPU-runnable" (16 green rows). | At least 4 green rows are real GPU tests: `inprocess/v1/test_gpu_connector.py` (guard `torch_device_type == "cuda"`, `device=device` tensors), `v1/multiprocess/test_cb_plan_executor_gpu.py`, `v1/multiprocess/test_blocked_scale_format.py` (cuda only), `inprocess/benchmarks/test_cachegen.py` (GPU tensors). The rule is just "area in hostAreas AND regex `is_available`". | `build_page.py:42-43, 336-337`; `git show 05d8eb84:<file>` lines 29/31/19/27 | Mark rows green only if the file body has no `device=`/`.cuda(` use (the 4 storage suites pass this test). Otherwise check by hand. |
| F5 | major | 9 tiles, 9b, 9f | 399 itemized skips; 75 files never run; ≈50 whole-module skips. | The log has **402** itemized skips. `parse.py` LINE regex `(SKIPPED…)\s+\[` misses `SKIPPED (reason) [` lines (3 lines). So `tests/inprocess/v1/compute/test_pos_kernels.py` **did run** (1 skip) but is listed as "never run", and `test_eic.py` shows 1 skip instead of 3. Whole-module skips = 449 − 402 = **47** (pytest prints "collected … / 47 skipped"). 6 of the 75 "never run" files have no tests ("helper or placeholder"). So the real count of never-run test files is **68**. | `grep -c ' SKIPPED' job312.log` = 402; log lines 4316, 4925-4927; log line "collected 10171 items / 443 deselected / 47 skipped"; my re-parse (`myparse2.py`): passes match for all 539 files, only these 2 differ | Change the regex to `(PASSED\|SKIPPED…)(?: \(.*?\))?\s+\[`. Drop no-test files from the "never run" count. Say 47. |
| F6 | major | header tile, 6, 7 | "−80% PR GPU-min, 0 missed bug catches". | The arithmetic matches P8 (36,848 vs 185,936 = 80.2%). But (a) "0 missed" is checked against very few catches: P2 opened only 9 of 59 fail→pass pairs, and there was 1 real code catch in 30 d. (b) It assumes L2 server scenarios that do not exist yet (3b: "partly"). deadlock/http_api/lazy_offload/cache_stats move to "L2 / L1" homes in section 5. (c) 429 retried failures are assumed to be flakes. | `P2/coverage_map.md:374` ("I did 9 of 59"); `P8/shadow_report.md:15,18,225,248-251`; 3b L2 row | Reword the tile: "−80% est. if L2 scenarios are built; checked against 1 known catch in 30 d (9/59 failures inspected)". |
| F7 | major | 4 matrix vs P8 | The single `adapter (vLLM / SGLang)` row requires CPU E2E. `kernel` row = L0+L1+L3+Layout. | P8: SGLang adapter has **no** cpu_e2e (it runs vLLM-CPU only). Kernel needs "L1 GPU kernels (unit pod)", which the page has no column for. | `P8/shadow_report.md` §3 rows "adapter (SGLang)", "kernel" | Split the adapter row. Add an "L1-GPU unit" column. |
| F8 | major | 4 (`docs` class) | `docs` = markdown, docs/, examples/ → L0 lint only. | pytest collects `examples/lmc_external_l2_adapter/tests/test_plugin.py` (18 results). Today GHA runs it because the paths filter is `**.py`. Under the proposed rule an `examples/**.py` change would run no tests. | `pytest.ini` has no `testpaths`; log lines 2571-2588; `test.yml` filter `'**.py'` | Move `examples/**/*.py` into `tests_only` (or core). |
| F9 | major | 4 (`core` class) / 9g#6 | Core PRs need L0+L1+L2+CPU E2E, no GPU. | About 6.5k lines of storage-logic tests (`test_l1_manager.py` etc.) and the cuda kernel tests run **only** in GPU k3-unit-tests. If "L1" ever means GHA-CPU, core PRs to `lmcache/v1/distributed/**` lose them. | 9g#6 + F1 evidence | Keep k3-unit-tests required for `core`, or first finish the CPU port from 9g#6. |
| F10 | major | area_meta `engines` | "These are the only PR-time checks for these engines (no SGLang server in CI)." | SGLang runs for real in the Buildkite MP pipeline (e.g. `lm_eval` SGLang with SCORE_TOLERANCE 0.01, `long_doc_qa` SGLang). This is true only for TensorRT-LLM / ATOM. | `P7/criteria_inventory.md:35` (`MP/scripts/engines/sglang.sh:69`); `P5/baseline_decisions.md:30,93`; `P8/shadow_report.md` "adapter(none): tensorrt_llm, atom" | See section 4. |
| F11 | major | area_meta `code` paths | Main code paths. | 5 paths do not exist at 05d8eb84: `lmcache/v1/lazy_offload/`, `lmcache/v1/multiprocess/blend*`, `lmcache/v1/multiprocess/mq*`, `tools/pre_commit`, `qstore` (it is under `plugin_modules/`). `torch_ops` is under `lmcache/v1/platform/`. | `git cat-file -e 05d8eb84:<path>`; `git ls-tree -r 05d8eb84 lmcache` | See section 4. |
| F12 | major | 9g#3 failure classes | 4 classes; profiling = "dev-wide broken test", 20/25 sampled; class 4 "missing module". | Re-sample of 21 failed runs (11-05 14:15 → 11-06 08:50): profiling 16/21. The profiling failures came from the runner (`kernel.perf_event_paranoid is 4`). **Fixed on dev by c5a285ea (#6350, 2026-11-06 09:24 +0800)**, and it passes in the reference run. The one `ModuleNotFoundError` (`lmcache.sdk.wrapper.contiguous`, run 42138796321) is a PR bug, not a class of its own. So there are 3 classes, and the quarantine target "class 1" is already gone. | `runs/*.log` FAILED lines; `git show -s c5a285ea`; job312.log test_profiling `[on-cpu] PASSED` | Update 9g#3. Base the quarantine on per-test history (see section 6), not on this snapshot. |
| F13 | major | 9g#2 next step | "Nothing to add inside the matrix." | Matrix fail-fast is real (40 failed runs: 3.10 34 cancelled/5 failed, 3.11 30/9, 3.12 30/8, 3.13 32/7, 3.14 29/10). But the failing leg still runs the full 12–15 min, because GHA uses no `--maxfail` (k3-unit uses `--maxfail=1`). Also, fail-fast hides whether a failure is version-specific, so the "run 2 versions" idea has no data behind it. Skip counts differ by version (449–454). | `jobs/*.json` tally; `test.yml` pytest line; `unit/run.sh:38`; `runs/*.log` summaries | Add `--maxfail=N` (or a fast-first ordering), and keep a nightly run with all 5 versions without fail-fast to measure version-specific failures. |
| F14 | minor | 3b vs 9a | L1 "py3.10–3.13", "minutes". | Matrix is 3.10–3.14, ≈19 min per version (pytest alone is 12–15.5 min in failed runs). | `test.yml` matrix; run summaries 753–935 s | Fix the text. |
| F15 | minor | 3b Layout smoke "XPU only, not CUDA" | No layout smoke on PR today. | cpu_device.yml already runs DeepSeek-V2-Lite (dummy, 2 layers, **MLA enabled**) on CPU. That is a cheap MLA layout check, and the page shows it only in 9a/9e. | `cpu_device.yml:111-131` | Mention it in 3b. |
| F16 | minor | 2 | "Env 22% + engine 39% = 61%", "Test body 39%". | Weighted: 22.3% + 38.4% = 60.7%, so 61% is OK. These are GPU-min-weighted p50s of per-job shares from 15 logs per workload, not a measured split of the total. "Test body 39%" is just 100 − 61. | my recompute from `P1/cost_by_workload.csv` | Say "approx., p50 of 15 logs per workload; test body = remainder". |
| F17 | minor | header tile / 2 timeline | "queue wait p50 18.5" drawn as the first 18.5 of an 87-min build. | 18.5 is the p50 **per GPU job** (`queue_wait_p50_all_gpu_jobs`), not per build. Builds queue many jobs in parallel. | `P1/build_level_summary.json`; `aggregate.py:192` | Label it "per job" and do not draw it as a build segment. |
| F18 | minor | 1 Layer 8 | "Core-only PR: 518 → ~3 GPU-min". | P8 gives core = 0 MP GPU-min (+7–20 for add-ons). I found no source for "~3". | `P8/shadow_report.md` §3 | Use "0 (+add-ons)". |
| F19 | minor | 7 | "HF_TOKEN in plain text in Buildkite UI config" (source P1). | No P1 file contains HF_TOKEN (grep count 0 in raw/*.json, csv, out). | grep in `outputs/P1` | Add private evidence, or mark "reported, not in artifacts". A security claim on a shareable page needs care. |
| F20 | minor | 9b per-file time | "Time = gap between results; includes fixture setup." | This is fair for a serial run (sum 728 s vs pytest 740 s). It misleads in 3 ways: (1) module setup/teardown and collection-time import cost go to the first test of the **next** file; (2) GHA batches log timestamps, so fast files can show 0.0 s (lazy area 195 tests = 0.0 s); (3) captured log output is excluded. Use `--durations=0` or `--junitxml` for real per-test time. | `parse.py` dur logic; area totals | Add the caveat and prefer junit durations. |
| F21 | minor | test.yml marker filter | (not on page) | Marker `supa` is declared in `pytest.ini` but missing from `-m "not (cuda or musa or xpu or npu or neuron or rbln)"`. `test_supa_support.py` runs on CPU (11 results, 1 skipped). | `pytest.ini`; job312.log | Note it in 9a/9f. |
| F22 | minor | 9f "Why" column | 4 storage suites are "not collected" in `cpu_tests.json`. | They are collected and then module-skipped (`pytest.skip(allow_module_level=True)`). They are part of the 47 collection skips. build_page relabels them correctly; the JSON is still wrong. | `parse.py` `why` heuristic; test file lines 79-82 | Fix the parse.py label. |
| F23 | minor | 9f / readability | Green rows mark candidates. | The green tint is very faint in dark mode, and color is the only signal (no text tag). | screenshot `cpu_notrun.png` | Add a "CPU candidate" text column. |

## 3. Misclassified CPU test files

| Path (under tests/) | Current area | Correct area | Why |
|---|---|---|---|
| benchmarks/test_xpu_kernels_microbench.py | cli | platform | SYCL/XPU kernel microbench (docstring) |
| v1/test_cache_identity.py | vllm | smcore | imports `distributed.api`, `key_codec` only |
| v1/distributed/test_storage_manager_l2_keys.py | l2 | smcore | tests `StorageManager.l2_adapters()` |
| v1/distributed/test_cache_salt_l2_eviction.py | l2 | smcore | area_meta smcore claims "cache_salt scoped eviction", but the l2 rule wins first |
| v1/distributed/test_l1_l2_state_metrics.py | l2 | smcore (or obs) | cross-tier state metrics |
| v1/distributed/test_multimodel.py | l2 | smcore | "multi-model support in the StoreController" |
| v1/distributed/test_prefetch_controller.py | lookup | smcore | `storage_controllers/prefetch_controller` (9g#6 counts it as storage logic) |
| v1/multiprocess/test_request_auth.py | transport | http | transport **auth** config (`http_auth`, `transport.auth`) |
| v1/multiprocess/test_engine_passthroughs.py | lifecycle | http | "HTTP-layer passthroughs" regression |
| v1/multiprocess/test_usage_telemetry_server.py | build | lifecycle (or obs) | spawns real `run_cache_server` |
| v1/test_mem_kernels.py, v1/test_mp_mem_kernels.py | datapath | layout / kernel | cuda kernel tests (GPU only) |
| v1/multiprocess/test_qstore.py | datapath | modules | `plugin_modules/qstore.py` |
| inprocess/benchmarks/test_xpu_connector_benchmark.py, test_xpu_layerwise_connector_benchmark.py, test_musa_benchmark.py | ip_engine | platform | vendor device benchmarks |

## 4. Area text corrections

| Area | Corrected sentence |
|---|---|
| engines.why | "TensorRT-LLM and ATOM have no engine job in CI, so these are their only PR checks. SGLang also runs for real in the Buildkite MP pipeline (lm_eval, long_doc_qa)." |
| vllm.setup | "Imports real vLLM classes from the default PyPI wheel (vllm 0.33.0, CUDA build, no GPU present, `vllm._C` fails to load)…" (job312.log 1640, collection warnings) |
| lazy.code | "lmcache/integration/vllm/lazy_offload_manager.py, lazy_offload_policy/, lazy_offload_state.py; token drop: lmcache/integration/vllm/experimental/token_drop*.py" |
| blend.code | "lmcache/v1/multiprocess/modules/blend/, lmcache/v1/mp_coordinator/blend_index.py, blend_client.py" |
| transport.code | "lmcache/v1/multiprocess/transport/ (zmq_impl, grpc_impl), protocols/, rpc.py, session.py, futures.py" |
| datapath.code | "lmcache/v1/multiprocess/transfer_context/, modules/*_transfer.py, posix_shm.py, plugin_modules/qstore.py" |
| layout.code | "lmcache/v1/gpu_connector/kv_format/, lmcache/v1/platform/torch_ops/" |
| build.code | "setup_extensions/, tools/check_direct_torch_device.py, tools/check_spdx_header.py" |
| lifecycle.code | "lmcache/v1/multiprocess/server.py, config.py, client_config.py, heartbeat.py" (no `autostart` module name exists) |
| http.why | "Operators and the coordinator drive the server through HTTP. (The CVE-2026-107205 auth regression tests are in the coord area: tests/v1/mp_coordinator/test_http_auth.py.)" |
| coord.setup | "FastAPI TestClient + fake MP servers; several files start real uvicorn/server processes (test_http_auth, test_instances_usage_e2e, test_integration, mp_server_harness)…" |
| ip_engine.why | "…regression tests for issues #3337 and #3318 (#3104 is in ip_ctrl: internal_api_server/test_per_instance_app.py)." |
| l1.setup | "…NOTE: test_l1_manager.py and test_l1_memory_manager.py skip on CPU only because of a `torch_dev.is_available()` guard. The same DramL1Manager/StorageManager already runs on CPU in test_multi_l1_serving.py." |
| platform.why | "…(99 skips = parts that need the real device)." |
| lifecycle.setup | Keep the text, but note that the one observed port collision was in ip_store (`test_p2p_backend_with_controller.py`, run 42189249028), not in lifecycle. |

## 5. Status of every finding in sections 7 and 9g

| Finding | Status | Evidence |
|---|---|---|
| 7: `full` label auto-added to 95/100 PRs | CONFIRMED (vs source) | P8 shadow_report.md:19 |
| 7: MP all-or-nothing, ~35 jobs | CONFIRMED (vs source) | P8 §2 path-filter.sh refs |
| 7: 61% setup + engine start | CONFIRMED (60.7% recomputed); method caveat F16 | cost_by_workload.csv |
| 7: XPU runs 1-device HMA layout smoke | CONFIRMED (vs source) | P6 small_model_set.md:10-12 |
| 7: 2,099 no-op SGLang jobs, ~20 min queue | CONFIRMED | noop_skip_runs 339+680+344+672+64 = 2,099; queue p50 12–21 min |
| 7: preemption_correctness 1-GPU label, 2-GPU pod | CONFIRMED (vs source) | P1/build_jobs_table.py:8 comment |
| 7: SCORE_TOLERANCE 4 defaults, C9, C11 | CONFIRMED (vs source; not re-read in upstream) | P7 criteria_inventory.md:80,87,89 |
| 7: bench server exits 0 on failed checks | CONFIRMED (vs source) | P4 server_bench_gaps.md:75 |
| 7: failures cluster on node 248 | CONFIRMED (vs source) | P5 baseline_decisions.md:21-23 |
| 7: SGLang long_doc_qa TTFT regression ~10-27 | CONFIRMED (vs source) | P5:30,93 |
| 7: HF_TOKEN plaintext | UNVERIFIABLE | no artifact in outputs/P1 (F19) |
| 9g#1 Test not required; publish.yml needs it | CONFIRMED | `gh api repos/LMCache/LMCache/branches/dev` lists the 4 required checks (works now, no 404); publish.yml:183-214 `needs.test.result == 'success'`. Also: publish.yml runs on dev push, so Test also gates dev push artifacts. |
| 9g#2 matrix fail-fast works | CONFIRMED (but see F13 next step) | 40 runs: 29–34 cancelled per version |
| 9g#3 not version-specific, 4 classes | PARTLY | failures spread over all versions (5/9/8/7/10). Profiling class fixed by #6350; "missing module" is a PR bug (F12) |
| 9g#4 ≈19 min = 136 + 200 + 751 s | CONFIRMED for this job | job312.log step timestamps 13:05:55→13:08:11, 13:08:25→13:11:45, 13:11:45→13:24:16; pytest 740 s. Other runs: pytest up to 935 s |
| 9g#5 test_create_workload hits huggingface.co | CONFIRMED | 13 requests (1×200, 12×401) in 2 tests, job312.log ~2938-2956. Tests still pass, so this is a latent flake, not an active one |
| 9g#6 ≈6.5k lines skip only for no accelerator | CONFIRMED | 2532+1927+1279+802 = 6,540 lines. The only device use in each file is the `torch_dev.is_available()` guard. `_allocate_cpu_memory` has a non-CUDA path (`platform/torch_ops/mem_alloc.py:86-113`). test_multi_l1_serving.py builds a real StorageManager and passes 16/16 on CPU. Not executed by me. |
| 9g#7 prefix_suffix_tuner 14 × 5.0 s | CONFIRMED; cause found | `lmcache/cli/commands/bench/engine_bench/workloads/prefix_suffix_tuner.py:164 _EVICTION_SETTLE_SECONDS = 5.0`, slept at `:567` in `warmup()`. Tests do not patch it. Fix: `monkeypatch.setattr(mod, "_EVICTION_SETTLE_SECONDS", 0)` saves ~70 s per version |
| 9g#8 pytest collects examples/ | CONFIRMED | pytest.ini has no testpaths; 18 results (3 pass, 15 skip) |
| 9e "last 100 runs 44/10/22/10/14" | CONFIRMED (now 44/11/22/10/13) | `gh run list -w cpu_device.yml -L 100` |
| 9g "11-05: 43 fail / 41 pass" | CONFIRMED | gh run list by createdAt (UTC) |

## 6. Gaps and suggested additions for the SDD (max 6)

1. **What k3-unit-tests runs.** Get per-file results and durations from Buildkite (`durations/test.html`, junit). Diff them against GHA Test. Which tests run only on GPU, only on GHA (vLLM-importing tests: k3-unit installs no vLLM), or on both? This is the real required CPU-ish gate, and the page has no data on it.
2. **Failure history per test file** over ≥30 days (GHA + k3-unit): fail count, fail-then-pass on rerun, distinct PRs. Without this, "remove flaky tests" has nothing to stand on. Today's sample is 21 runs, and one fixed test dominates it.
3. **Bug-catch history per area**: which areas' tests failed on PRs that were later fixed (a real catch), and which only flaked. Pick L0 smoke on this basis, not on test count.
4. **Version-specific signal**: one nightly run of all 5 versions without fail-fast, plus a list of version-conditional skips (449–454 skips across versions). The "2 versions on PR" decision needs this.
5. **Real per-test durations** (`--durations=0` / junit) instead of log gaps. This is needed to size an L0 smoke under a time budget.
6. **L0 smoke candidates.** From the page data these look best: smcore (240 tests, 0.3 s), lookup (209, 3.4 s), http (179, 1.7 s), layout (227, 1.9 s), serde (80, 1.3 s), engines (87, 0.2 s), vllm (596, 9.8 s). All are fast and mostly pure-Python or TestClient. The page is not enough to decide, because it lacks catch history (gap 3) and the GPU-unit overlap (gap 1). Avoid lifecycle/transport/ip_store for L0: they use real sockets and subprocesses, and the one port collision seen was in ip_store.

## 7. What I could not verify, and why

- Buildkite k3-unit-tests per-test content and timing: I did not query Buildkite (time-box). Only the YAML/run.sh was read.
- Whether the 4 storage suites actually pass on CPU: read-only rules, so I ran nothing. The evidence is static (guard only, CPU allocator path, a sibling suite passes on CPU).
- HF_TOKEN claim: no artifact in the plan folder.
- P7/P5/P4/P6 claims: checked against the plan docs, not re-derived from upstream code or Buildkite logs.
- Section 6 "Removing the baseline engine" per-workload numbers (18,512 etc.) and 43,200 total: not re-derived from jobs_all_30d.csv.
- Mindmap: 12 file:line refs checked at fcd50cea and all correct (lookup.py:188/450, heartbeat.py:16/41, lmcache_mp_connector.py:933/1286, l1_manager/base.py:296/474, cache_api.py:161, kv_layer_groups.py:80, p2p_controller.py:309, token_hasher.py:213). I did not check the rest.
- Page rendering: checked 3 deep links (#gpu/overview, #cpu/notrun, #cpu/failfast) with headless Chrome. They show and hide correctly. I could not capture the console with `--screenshot`, so console errors were not checked.
