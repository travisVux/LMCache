# P8 / R7 — Shadow run of the WS-C "minimum-sufficient test" rule

Date: 2026-11-05. Repo: `third_party/LMCache` at `fcd50cea` (read-only). All repo paths are relative to that clone.
Inputs: `outputs/P1/jobs_all_30d.csv` (30 days, 2026-10-05 → 11-04, pipeline k3-multiprocess-test),
`outputs/P2/coverage_map.md`, `outputs/P4/server_bench_gaps.md`, `outputs/P6/small_model_set.md`.
Outputs in this folder: `ci_rule_shadow.py` (rule + classifier + self-tests), `shadow_analysis.py` (batch run + join),
`shadow_per_pr.csv` (269 PRs), `shadow_failed_jobs.csv` (551 failed MP jobs), `raw/` (gh + log caches).

---

## 0. Short answer

| Question | Answer |
|---|---|
| GPU-min the rule would save (30-day scale, all 223 PRs with MP jobs) | **149,088 of 185,936 PR GPU-min (80%)**. Worse-case estimate (new tiers cost 2×, and a perf canary on every code PR): 111,853 (60%). See §5.3 |
| Last 100 merged PRs | 53 of them used MP GPU (45,985 GPU-min). Rule: 8,036 → **82% saved**. Only 11 of 100 still need `full` |
| Core-only PR, GPU-min per MP build | 518 now → about 3 (all new checks run on CPU). Target in plan was −50% |
| Would the rule have missed a real bug catch? | **No. The list is empty.** Every real catch in P2 is still caught by a layer the rule keeps (§6.1). All 37 skipped non-infra final failures in 30 days are explained: flake, env, stale branch, or already caught by a kept layer (§6.2) |
| Biggest rule change vs WS-C draft | (1) `full` label must **not** be an override: it is auto-added to every auto-merge PR (95/100). (2) `cpu_e2e` goes into core + adapter tiers (it caught #5383). (3) `transfer_context/**` and multi-group transfer code count as adapter + kv_layout. (4) Restart and preemption get small 1-GPU add-ons, not the full suite |
| Biggest risk | Perf workloads (`vllm_bench`, `long_doc_qa*`) leave the PR tier. No real perf catch in 6 months (P2 d2), but this is a policy choice, not a data result (§7, Q1) |

---

## 1. How MP CI decides what to run today

| Step | What happens | Evidence |
|---|---|---|
| Trigger | MP build starts only if the PR has label `mp` or `full`, or on a `dev` push | `.buildkite/k3_tests/multiprocess/BK_WEB_SETUP.md:6` |
| `full` label | Added **automatically** when auto-merge is turned on | `.github/workflows/automerge-labeler.yml:14-17` |
| `skip expensive ci` label | Upload step exits green, no MP jobs | `.buildkite/k3_tests/common_scripts/helpers.sh:53-71`, `upload-pipeline.sh:39-50` |
| `force-ci` label | Skips both checks above, runs the full suite | `helpers.sh:60-63`, `path-filter.sh:313-317` |
| Path filter | Skip MP if every file is trivial (`*.md`, `docs/`, `asset/`, `.github/`, LICENSE...) or unrelated (`tests/**`, `examples/**`, other `.buildkite/k3_tests/<suite>/`) | `path-filter.sh:42-54`, `139-151` |
| Unknown file | Treated as relevant (runs the full MP suite) | `path-filter.sh:221-223` |
| Granularity | All or nothing. There is no per-step `if:` by path in `k3_tests/multiprocess/pipeline.yml`. The only `if:` lines are for the nightly vLLM/SGLang pin mode | `pipeline.yml:95,131,241,442,496,528` |
| GHA | `test.yml` and `cpu_device.yml` use `dorny/paths-filter` (any `**.py`, `lmcache/**`, `requirements/**`) | `.github/workflows/test.yml:43-52`, `cpu_device.yml:61-80` |

What the data says about labels (last 100 merged PRs, `raw/merged100.json`): 95 have `full`, 40 have `skip expensive ci`,
12 have `xpu`. So on the merge path, MP runs on almost every PR unless a human adds `skip expensive ci`.

---

## 2. Path → class map

Classes: `docs`, `tests_only`, `core`, `adapter`, `kernel`, `kv_layout`, `deps_ci`, plus one extra class
`other_platform` (non-CUDA devices and other suites; the CUDA MP pipeline never tests them).
A file can have 2 classes (for example `adapter` + `kv_layout`). A PR's classes = union over files.
Full table with ~75 ordered rules: top of `ci_rule_shadow.py` (`RULES`).

| Path | Class | Why / evidence |
|---|---|---|
| `*.md`, `*.rst`, `docs/**`, `asset/**`, LICENSE, CODEOWNERS, `.claude/` etc. | docs | same as `path-filter.sh:42-54` |
| `examples/**` | docs | MP never runs examples (`path-filter.sh:144-146`) |
| `tests/**` (not non-CUDA device tests) | tests_only | test code only |
| `benchmarks/**` (not `long_doc_qa`), `tools/**` | tests_only (L1) | not used by MP |
| `requirements/**` (not maca/rocm), `pyproject.toml`, `setup.py`, `CMakeLists.txt`, `setup_extensions/**` (not non-CUDA profiles) | deps_ci → full | pins go into the CI base image (`.buildkite/k3_harness/ci-base.Dockerfile:31-32`) |
| `.buildkite/k3_harness/**`, `.buildkite/k3_tests/common_scripts/**`, `.buildkite/k3_tests/multiprocess/{pipeline.yml,run.sh,scripts/engines,...}` | deps_ci → full | shared harness and MP pipeline |
| `.buildkite/k3_tests/multiprocess/scripts/workloads/<eng>/<x>.sh` | deps_ci → **that workload only** | e.g. `cache-stats.sh` → `cache_stats`. `lm-eval.sh` → `lm_eval` + `lm_eval_preemption`; `verification/` → dsv4 + kimi; `hma*` → layout_smoke |
| `.buildkite/k3_tests/<other suite>/**`, legacy `.buildkite/{configs,cases,scripts,...}` | other_platform | not k3-multiprocess |
| `.github/workflows/**` | deps_ci → lint only | Buildkite MP does not read them (`path-filter.sh:51`) |
| `.github/scripts/run-cpu-e2e-validation.sh` / `cpu_server_bench_test.sh` / `pin-tested-vllm.sh` | deps_ci → cpu_e2e / L2 / full | these scripts *are* MP or L2 inputs |
| `docker/**` | deps_ci → L1 | MP pods use `lmcache/ci-base` from k3_harness, not `docker/` (`pipeline.yml:117`) |
| `operator/**` | other_platform | own CI (`operator_ci.yml`) |
| `csrc/cuda/**`, other `csrc/*` | kernel | CUDA kernels |
| `csrc/{engine_kv_format.h,kv_transfer_plan_types.h,kv_transfer_types.h}` | kernel + kv_layout | KV format headers |
| `csrc/lmcache_native/**`, `csrc/storage_backends/**`, `rust/**` | core | CPU native helpers, L2 backends (raw_block: `test.yml:56-66`) |
| `csrc/sycl/**`, `lmcache/v1/platform/devices/{xpu,musa,rbln,npu,hpu,mlu,neuron,supa,rocm}/**` | other_platform | non-CUDA |
| `lmcache/v1/platform/devices/cpu/**` | core | this is what cpu_e2e runs |
| `lmcache/v1/platform/{base,devices/cuda,...}`, `lmcache/v1/gpu_connector/**` | kernel | CUDA device / copy layer |
| `lmcache/v1/gpu_connector/kv_format/**`, `kv_layer_groups.py`, `kv_codec/**`, `serde/fp8.py`, `serde/turboquant/**`, `platform/torch_ops/_kv_format.py` | kv_layout (+kernel/core) | layout grouping by identity (P6 §2); #5994 FP8 kernel |
| `lmcache/integration/vllm/{kv_cache_groups,kv_cache_group_edits,utils}.py` | adapter(vllm) + kv_layout | `utils.py` holds `mla_only()` (P6 §2, #4219); #4437 → #4488 gemma-4 break |
| `lmcache/integration/vllm/**` | adapter(vllm) | connector + worker adapter |
| `lmcache/integration/sglang/**` | adapter(sglang) | `unified_kv_adapter.py` also kv_layout |
| `lmcache/integration/{tensorrt_llm,atom}/**` | adapter(none) | no MP CI job for these engines → L1 only |
| `lmcache/v1/multiprocess/transfer_context/**` | adapter(all) + kv_layout | runs in the engine worker. #4018, #4830, #5248, #4072, multi-group #4410/#6124 |
| `lmcache/v1/multiprocess/{modules/engine_driven_transfer,server_transfer,lmcache_driven_transfer,object_group_transfer,group_view}.py` | core + kv_layout | per-group transfer plan; GPU IPC is not in CPU E2E (P2 d2) |
| `lmcache/v1/multiprocess/{server,engine_context,heartbeat,session}.py`, `modules/management.py`, `lmcache/v1/memory_allocators/**` | core + lifecycle add-on | restart_recovery is the only catcher of restart bugs (P2 b1 #4018) |
| any path with `p2p` / `transfer_channel`; any path with `gds` | core + `p2p` / `gds_smoke` add-on | only those workloads test GPU peer fetch / cuFile (P2 d2) |
| rest of `lmcache/v1/**`, `lmcache/inprocess/**`, `lmcache/cli/**`, rest of `lmcache/**` | core | `lmcache/inprocess` is still imported by `lmcache/v1/kv_layer_groups.py`, `protocol.py`, `rpc_utils.py` |
| keyword pass: file name under `lmcache/` or `csrc/` matching `mla|mamba|hybrid|hma_|fp8|kv_format|kv_layout|kv_cache_group` | + kv_layout | catches new layout files |
| anything else | deps_ci → full | safe default (no file in 269 PRs hit this) |

---

## 3. Refined rule: class → required tiers

Tiers are defined in the `ci_rule_shadow.py` docstring. "MP GPU-min" is the estimated GPU cost per MP build
(P1 `cost_by_workload.csv` p50; P6 §5 for the new layout smoke set).

| Class | Required tiers | MP GPU-min / build | Change vs WS-C draft (03_APPROACH_AND_PLAN.md:62-71) | Evidence |
|---|---|---|---|---|
| docs | lint | 0 | same | — |
| tests_only | lint + changed tests (L1) | 0 | same | — |
| other_platform | lint + L1 (their own pipeline) | 0 | new class | path-filter already skips these for MP |
| core | lint + L1 + L2 + **cpu_e2e** | 0 | **+cpu_e2e** (0 GPU) | P2 matrix: cpu_e2e catches identity / lookup / store / connector start |
| core + lifecycle paths | + `restart_recovery` (vLLM, zmq + grpc) | 19.6 | **new add-on** | P2 b1: #4018 failed only in restart_recovery |
| core + p2p / gds paths | + `p2p` or `gds_smoke` | 14.6 / 7.0 | **new add-on** | P2 d2: only catcher |
| adapter (vLLM) | lint + L1 + L2 + **cpu_e2e** + L3 smoke vLLM (`lm_eval` lmcache_driven + engine_driven) | 20.6 | **+cpu_e2e** | **#5383**: connector `AttributeError` was caught by cpu_e2e (P2 b1) |
| adapter (SGLang) | lint + L1 + L2 + L3 smoke SGLang | 20.6 | no cpu_e2e (vLLM-CPU only) | — |
| adapter (all / transfer_context) | both engines' L3 smoke + `lm_eval_preemption` + `restart_recovery` | 80.2 | **wider** | #4830 (GPU corruption, lm_eval method), #5248 (preemption), #4018 |
| `lmcache_mp_connector.py` | + `lm_eval_preemption` (vLLM) | +19.4 | new add-on | #5248 preemption code lives here |
| kernel | lint + L1 + L1 GPU kernels (unit pod) + L3 smoke vLLM + **layout_smoke** | 78.6 | **+layout_smoke** | kernels are layout-specific (`engine_kv_format.h`, P6 §2) |
| kv_layout | lint + L1 + L2 + cpu_e2e + L3 smoke (engine) + layout_smoke | 78.6 | full TP only by label `mp-full-tp` (new) or nightly | P6 §5-6; #4488 (gemma-4 HMA), #4219 (kimi TP) |
| deps_ci | full (some sub-paths narrower, see §2) | ~535 | narrower for `.github/workflows`, `docker/`, single workload scripts | — |
| label `force-ci` / proposed `mp-full` | full | ~535 | **`full` label removed as override** | `automerge-labeler.yml:14-17` |
| dev push / nightly | full (unchanged) | — | the rule is for PR builds only | catches of upstream breaks (#4724, #4801, #5829) came from every build incl. dev |

Not in any PR tier now: `vllm_bench`, `long_doc_qa`, `long_doc_qa_l2` (perf), `dsv4_flash_tp`, `kimi_linear_tp`
(full TP), `preemption_correctness`, `deadlock`, `http_api`, `cache_stats`, `lazy_offload` (unless their own
path matches), `mp_autostart_tp2` (unless `mp_server_launcher.py`), `fault_tolerance`. They run on
`deps_ci` PRs, `force-ci`, dev push and nightly.

---

## 4. Class distribution

### 4.1 Last 100 merged PRs (2026-10-29 → 11-04)

Classes present (a PR can have several):

| Class | PRs |
|---|---|
| tests_only | 67 |
| docs | 60 |
| core | 44 |
| deps_ci | 31 |
| other_platform | 19 |
| kv_layout | 14 |
| adapter | 11 |
| kernel | 6 |

Highest tier per PR:

| Highest tier | PRs | MP builds that used GPU | Actual GPU-min | Rule GPU-min | Saved |
|---|---|---|---|---|---|
| lint only | 14 | 0 | 0 | 0 | 0 |
| changed tests only | 10 | 0 | 0 | 0 | 0 |
| L1 | 8 | 3 | 1,898 | 0 | 1,898 |
| L1 + L2 + cpu_e2e (0 GPU) | 24 | 22 | 13,291 | 0 | 13,291 |
| single MP workload | 9 | 14 | 6,390 | 222 | 6,168 |
| L3 smoke | 8 | 6 | 3,871 | 157 | 3,714 |
| layout_smoke (+L3) | 16 | 30 | 15,695 | 2,817 | 12,878 |
| full | 11 | 8 | 4,840 | 4,840 | 0 |
| **Total** | **100** | **83** | **45,985** | **8,036** | **37,948 (82.5%)** |

Only 53 of the 100 merged PRs used MP GPU in the P1 window (the rest: `skip expensive ci`, path filter, or
builds before 10-05). Most common class sets: `core;docs;tests_only` 17, `core;tests_only` 13, `docs` 10,
`tests_only` 8.

### 4.2 Why `full` is still needed (31 PRs in the 30-day set)

| Trigger file type | PRs |
|---|---|
| MP `pipeline.yml` / `run.sh` / `engines/*.sh` / `run-single-test.sh` | 13 |
| `pyproject.toml` / `setup.py` | 10 |
| `requirements/*.txt` | 6 |
| shared `common_scripts/` (path-filter, upload) | 5 |
| `setup_extensions/**` | 4 |
| `k3_harness/setup-*.sh` | 2 |

`pyproject.toml` is the top single file (9 PRs). Many of those edits are lint config or version only (see Q4).

---

## 5. GPU-min saved

Method (`shadow_analysis.py`): for each PR with MP jobs in P1, sum `gpu_min` per build (only builds that used GPU).
Rule cost per build = `full` → actual; otherwise min(actual, rule estimate). File list = the PR's current final
diff (`gh pr view --json files`, paged with `gh api` for the 3 PRs with >100 files: #6238, #6135, #6007).
Actual includes retries and canceled jobs. The rule estimate does not include retries, which helps the rule a bit.

### 5.1 30-day scale (all 223 PRs in P1, 373 builds that used GPU)

| Highest tier | PRs | Builds | Actual GPU-min | Rule GPU-min | Saved |
|---|---|---|---|---|---|
| lint | 1 | 0 | 0 | 0 | 0 |
| L1 | 12 | 19 | 9,948 | 0 | 9,948 |
| L1 + L2 + cpu_e2e | 85 | 122 | 63,446 | 0 | 63,446 |
| single MP workload | 11 | 21 | 10,939 | 325 | 10,614 |
| L3 smoke | 27 | 66 | 26,645 | 2,771 | 23,874 |
| layout_smoke (+L3) | 56 | 98 | 50,690 | 9,484 | 41,206 |
| full | 31 | 47 | 24,268 | 24,268 | 0 |
| **Total** | **223** | **373** | **185,936** | **36,848** | **149,088 (80.2%)** |

### 5.2 Biggest single savings

| PR | Title (short) | Classes | Actual | Rule |
|---|---|---|---|---|
| #5383 | Skip lookup of APC-covered prefix | adapter, core | 8,133 (29 builds) | 1,448 |
| #5489 | bench: kv-tier-pressure workload | core | 4,285 | 0 |
| #5556 | valkey_rdma L2 adapter | core | 4,154 | 0 |
| #4410 | Engine-driven multi-group transfers | adapter, kernel, kv_layout, deps_ci* | 3,788 | 967 |
| #5150 | token ids as packed uint32 | adapter, core | 3,318 | 522 |

*#4410's final diff has `deps_ci` only from `.github/scripts/run-cpu-e2e-validation.sh` and a workload script, which do not force `full`.

### 5.3 Sensitivity (the new tiers are not measured yet)

| Scenario | Actual | Rule | Saved |
|---|---|---|---|
| Base (P1 p50 + P6 §5 estimates: layout_smoke 58, L3 smoke 20.6) | 185,936 | 36,848 | 149,088 (80.2%) |
| layout_smoke ×2 (116) and L3 smoke ×2 (41.2) | 185,936 | 45,753 | 140,183 (75.4%) |
| Above + keep a perf canary (`vllm_bench` + `long_doc_qa`, 99.7) on every code PR | 185,936 | 74,083 | 111,853 (60.2%) |

Even in the worst case the target "−50% GPU-min per core-only PR" (03_APPROACH_AND_PLAN.md:115) is met.

---

## 6. "Would have missed" check

### 6.1 Every real catch from P2: does the rule still run a layer that catches it?

| Catch (P2 ref) | Bug PR / source | Layer that caught it | Rule output for that PR | Still caught? |
|---|---|---|---|---|
| **#5383** connector `AttributeError` (P2 b1, build 5634) | #5383 itself | cpu_e2e (and ~11 GPU jobs) | adapter(vLLM) + core → cpu_e2e, L3 vLLM, lm_eval_preemption, restart_recovery | **Yes** — cpu_e2e failed in build 5634 (`shadow_failed_jobs.csv`: cpu_e2e rows `rule_runs_it=yes`) |
| #4018 restart round-2 writes 25.9% (P2 b1, build 5466, likely) | #4018 (closed) | restart_recovery | memory_allocators + transfer_context → `restart_recovery@vllm` kept | **Yes** — its 3 restart_recovery failures are `rule_runs_it=yes` |
| #4488 gemma-4 HMA broke (P2 b2) | #3869 / #4437 flipped `separate_object_groups` | hma_lm_eval_gemma4 (now disabled) | both → kv_layout → layout_smoke (incl. `swa_mixed` gemma-4 dummy, P6 §5) | **Yes, if** P6 `layout_smoke/swa_mixed` is built. Today the CUDA job is disabled, so today's CI would also miss it |
| #5892 SGLang Kimi start fail (P2 b2) | found while adding test #5862 | kimi_linear_tp (SGLang) | #5862 touches MP `pipeline.yml` → full | **Yes** |
| #4724 vLLM single-buffer layout (`storage_offset`) | vLLM nightly, no LMCache PR | cpu_e2e server_copy | cpu_e2e is in core / adapter / kv_layout tiers; dev push = full | **Yes** |
| #4801 / #5829 / #3538 / #4037 / #5100 upstream or env breaks | vLLM nightly, DeepGEMM, FFmpeg | dsv4 / cpu_e2e on every build | dev push and nightly stay full; cpu_e2e on most PRs | **Yes** (seen on dev / nightly instead of on random PRs — less noise) |
| #4830 GPU async-copy corruption (gsm8k 0.80 → 0.00) | manual on 8×H100, not CI | lm_eval method | transfer_context → L3 smoke both engines (lm_eval engine_driven) | Not a CI catch. Rule keeps the method that would catch it |
| #4219 Kimi TP rank-0 store (guard) | found outside CI | — | `utils.py` + MP pipeline → full; layout_smoke keeps kimi TP2 | n/a (guard) |
| #5248 preemption (guard) | — | — | `lmcache_mp_connector.py` → lm_eval_preemption; PR also touched pipeline → full | n/a (guard). `preemption_correctness` itself leaves the PR tier (Q2) |
| #4072 engine_driven SHM restart race | production | none | same as today: restart_recovery has no engine_driven mode | Miss today and with the rule (P2 d3). Not caused by the rule |

**Result: the "would have missed" list is empty.**

### 6.2 Every failed final-attempt MP job in 30 days that the rule would NOT have run

122 final-attempt failed jobs on PR builds (not retried later, not soft-fail). 27 were in workloads the rule keeps.
4 are dsv4/kimi (layout_smoke stand-in only). 54 have infra exit codes (128, 2, -1, 255; P2 b1). The other **37 jobs (18 PR builds)**
have exit 1. I opened the logs (`raw/log_checks.txt`) or matched them to P2 evidence:

| PR / build | Skipped jobs | Root cause | Real bug the rule misses? |
|---|---|---|---|
| #5395 / 5959 | 11 SGLang jobs | `scripts/engines/sglang.sh not found`: stale PR branch from before the SGLang adapter | No (stale branch) |
| #3766 / 5481 | 8 jobs (restart_recovery, gds, p2p, ...) | Whole build broken; cpu_e2e server_copy failed too, with the #4724 `storage_offset` error | No. Rule keeps cpu_e2e, so the build is still red |
| #5383 / 5634 | mp_autostart_tp2, preemption_correctness ×2, fault_tolerance | The real #5383 bug | No. Same build, cpu_e2e failed (kept) |
| #5383 / 5712 | gds_smoke "no LMCache retrieve recorded" | Same head passed in builds 5696 and 5739, and no new commit came before 5739 (`gh pr view 5383 --json commits`) | Likely flake. **UNKNOWN**: needs a re-run to be sure |
| #5795, #5802, #5823, #5825, #5830, #5831 / 5819-5834 | dsv4_flash_tp ×6 | DeepGEMM build vs torch 2.14, fixed on dev by #5829 (P2 b1/b2) | No (env; dev build shows it) |
| #5874 / 5886 | dsv4_flash_tp | `Automatic merge failed` (pre-merge conflict) | No (infra) |
| #5532 / 5479, #5557 / 5530 | fault_tolerance | `ZMQError: Address already in use :6555` (P2 b1) | No (harness) |
| #5637 / 6085 | restart_recovery | `Failed to download triton==3.8.0`, setup-env.sh exit 1 | No (network) |
| #4549 / 6361 | cpu_e2e server_copy | #4724 `storage_offset` error on a docker-only PR | No (not caused by the PR's change) |
| #5150 / 6089, #6001 / 6237 | long_doc_qa, long_doc_qa_l2 | `query_ttft 56.9% < 60%`, `L2 TTFT 1.33x < 1.5x` (P2 b1) | No (perf flake) |
| #4410 / 5843 | kimi_linear_tp_engine_driven (pickle) | New workload in bring-up. The workload is only in that PR's intermediate pipeline. Rule on that build's diff would be `full` | No (see edge case E1) |

Retried failures (429 more) are mostly perf workloads that passed on retry (long_doc_qa_l2 89, long_doc_qa 77,
vllm_bench 52, dsv4 34). P2 b1 found these to be flakes. Dropping them from the PR tier also removes most PR retry
GPU cost (P1: retry GPU-min 30d: long_doc_qa_l2 3,146, long_doc_qa 2,523, dsv4 2,199, vllm_bench 1,055).

---

## 7. Edge cases and open rule questions

### Edge cases found in the data

| # | Edge case | What the shadow does | Proposal |
|---|---|---|---|
| E1 | The file list changes during a PR (#4410 added and removed pipeline edits) | Uses the final diff | When wired in, classify **per build** with the same merge-base diff as `path-filter.sh:269-303` |
| E2 | Stale PR branches fail on old harness or old vLLM (#5395, #3766, #4549) | Not a rule issue | Keep `merge_pr_base_branch` (`helpers.sh:81`) on; maybe block builds whose base is very old |
| E3 | Layout bug inside a non-layout file: #5976 "SWA prefix replay" only touched `lmcache_mp_connector.py` → adapter, no layout_smoke | L3 vLLM + lm_eval_preemption only | Open question Q3: add `layout_smoke/swa` to `lmcache_mp_connector.py`, or accept the gap |
| E4 | Before refinement, #6124 (DSV4 compressed KV groups) and #4410 (multi-group) did **not** get kv_layout: their files are `engine_driven_transfer.py`, `server_transfer.py`, `transfer_context/**` | Fixed: these paths are now kv_layout | Keep a "title/label hint" check in the shadow phase to find more misses like this |
| E5 | Big mixed PRs (#6135: 184 files, #6007: 172) always end in `full` | full | Fine. Rare and the safe answer |
| E6 | `tests/**` changes skip MP today (`path-filter.sh:148-150`), and also with the rule. Tests for MP harness scripts (`.buildkite/k3_tests/multiprocess/scripts/tests/`) | L1 only | OK |
| E7 | `transfer_context/**` gets the most expensive non-full tier (80–138 GPU-min) and is touched often | conservative | After shadow data, maybe drop SGLang L3 when no SGLang file changed |
| E8 | Engines without an MP CI job (`tensorrt_llm`, `atom`) | L1 only | Same as today; say so in the rule doc |

### Open questions for maintainers

| # | Question | Data we have | Suggested default |
|---|---|---|---|
| Q1 | Can perf workloads (`vllm_bench`, `long_doc_qa`, `long_doc_qa_l2`) leave the PR tier? | No real perf catch in 6 months; they are the top retried jobs (P2 b1, d2). `vllm_bench` is also the vLLM-nightly canary (#3910) | Nightly + `deps_ci` PRs + label. If maintainers want a PR perf signal: one `vllm_bench` job on core storage paths (scenario 3 in §5.3 still saves 60%) |
| Q2 | `preemption_correctness` (2 GPU, 108 GPU-min/build, the most expensive) — PR tier or not? | Guard only (#5248), no catch yet | Run on `lmcache_mp_connector.py` + `transfer_context/**` in the shadow phase, measure, then decide |
| Q3 | Should `layout_smoke` run on every adapter change, not just kv_layout? | #5976 (E3) | Only `layout_smoke/swa` + `mla` (≈9 GPU-min) on `lmcache_mp_connector.py` |
| Q4 | `pyproject.toml` forces `full` in 9 of 31 full PRs. Most are tool config | — | Diff-content check: only `[project] dependencies` / `[build-system]` changes → full; else L1 |
| Q5 | Which label means "run everything"? | `full` is auto-added (`automerge-labeler.yml:17`) | Use `force-ci` (exists) or new `mp-full`; add `mp-full-tp` for dsv4/kimi TP |
| Q6 | Full TP (`dsv4_flash_tp`, `kimi_linear_tp`) on kv_layout PRs touching `mla_only` / slot-compression code? | P6 §6 suggests yes for matching paths | Start label-only; revisit after layout_smoke has run on ≥20 PRs |
| Q7 | `L2` (server bench) and `cpu_e2e` are assumed to be 0 GPU-min | P4: server bench runs on CPU in GHA; cpu_e2e is a CPU pod | Confirm the L2 scenarios from P4 are on CPU |
| Q8 | Where do new tiers live (Buildkite `if:` per step vs a dynamic upload)? | Today MP is all-or-nothing (`upload-pipeline.sh:80-81`) | Generate the step list from this classifier in the upload step (03_APPROACH C3) |

---

## 8. How to re-run

| Task | Command (run in `outputs/P8/`) |
|---|---|
| Self-tests (18 cases) | `python ci_rule_shadow.py --selftest` |
| One PR | `python ci_rule_shadow.py --pr 5383` (add `--verbose` for per-file output) |
| A file list | `python ci_rule_shadow.py --files lmcache/v1/multiprocess/server.py csrc/cuda/mem_kernels.cu` |
| Full batch + join | `python shadow_analysis.py` → `shadow_per_pr.csv`, `shadow_failed_jobs.csv` (gh results cached in `raw/prs/`) |
| Last 100 merged list | `gh pr list -R LMCache/LMCache --state merged -L 100 --json number,title,mergedAt,labels,files,changedFiles,baseRefName > raw/merged100.json` |
