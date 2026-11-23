# P2 — Coverage map: which bugs does each multiprocess workload catch?

Source: `third_party/LMCache` at `fcd50cea` (2026-11-04). All paths are relative to that repo
unless they start with `outputs/`.
Sources for the history: `git log` since 2026-05-04 (6 months), `gh` PR search (~95 calls), and
the P1 job table `outputs/P1/jobs_all_30d.csv` (30 days of k3-multiprocess-test jobs) plus
9 Buildkite log searches.

Words used:
- **Catch** = a workload failed because of a real problem, and someone fixed it.
- **Guard** = a workload added together with a fix, to stop the bug coming back. Nobody has seen it
  fail on a real bug yet.
- **Flake** = it failed, and the next run with no related change passed.

---

## 0. Short answer

1. Over 30 days, PR-time MP failures were mostly **not LMCache bugs**. They were infra problems
   (pip/HF 503, exit 128 checkout, port in use, missing libnuma) or **perf threshold misses**.
   I found **1 confirmed real LMCache code catch** in the 30-day window (PR #5383, connector
   `AttributeError`). It broke *every* engine workload at once, **including the CPU E2E job**.
2. In the 6-month history, real catches come in four groups:
   - **KV layout / hybrid models** (Kimi-Linear, DSV4, gemma-4 HMA, vLLM CPU layout change).
   - **Upstream engine / package breakage** (vLLM nightly, DeepGEMM, torchcodec).
   - **Silent data corruption** that only shows up as wrong output (lm_eval, gsm8k score 0.80 → 0.00).
   - **Lifecycle** (restart re-register, preemption resume).
3. Workloads that the cheaper layers already cover: `cache_stats`, `http_api`, `lazy_offload`,
   `mp_autostart_tp2`, most of `fault_tolerance`, `restart_recovery`, and the data-flow half of
   `long_doc_qa_l2`.
4. Workloads that are the **only** catcher of something: `dsv4_flash_tp`, `kimi_linear_tp`
   (real-model hybrid/MLA/fp8 layout under TP), `preemption_correctness` (resume after
   preemption), `lm_eval*` (silent corruption on a real model, GPU paths), `gds_smoke` (cuFile),
   `p2p` (GPU-to-GPU peer transfer), and the perf workloads (`vllm_bench`, `long_doc_qa`), but only
   for perf.

---

## (a) Assertion table per workload

General rule for all non-self-contained workloads: if the engine or LMCache does not start, the job
fails (`scripts/run-single-test.sh:184-198`). This hidden "it boots" check is behind most
catches.

Baseline engine list: `scripts/run-single-test.sh:170-177`
(`vllm_bench long_doc_qa long_doc_qa_l2 preemption_correctness`). Self-contained workloads
(they start their own processes): `scripts/run-single-test.sh:163` (`mp_autostart_tp2 p2p kimi_linear_tp dsv4_flash_tp`).

SGLang skips some common workloads before any setup (`scripts/engines/sglang.sh:16-21`:
`deadlock`, `lm_eval_preemption`, `long_doc_qa_l2`, `restart_recovery`; exit 0 at `run.sh:47-49`).
So those SGLang matrix jobs test nothing. P1 data shows they cost only about 0.09 min each, so
this is noise, not cost.

`scripts/` below means `.buildkite/k3_tests/multiprocess/scripts/`. `W/` means `scripts/workloads/`.

### dsv4_flash_tp (4 GPU, vLLM + SGLang, no baseline) — pipeline.yml:103-109
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | Probe: plain vLLM (dummy weights, same kernel flags) boots. If not, install the fallback vLLM version | boots within probe timeout | `W/vllm/dsv4-flash-tp.sh:150-199` |
| 2 | vLLM TP=4, `fp8_ds_mla` KV, real weights, becomes ready | `wait_for_server` | `W/vllm/dsv4-flash-tp.sh:245-266` |
| 3 | Cold output == output after APC reset (served from LMCache L1) | byte-identical (`cmp -s`) | `W/verification/l1-round-trip-verification.sh:114-126` |
| 4 | LMCache logged ≥1 new "Retrieved" line (non-vacuous) | after > before | `W/verification/l1-round-trip-verification.sh:128-133` |
| 5 | SGLang: requires lmcache_driven mode | exit 1 otherwise | `W/sglang/dsv4-flash-tp.sh:40-48` |

### kimi_linear_tp (2 GPU TP=2, vLLM + SGLang, no baseline) — pipeline.yml:228-234
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | vLLM TP=2 hybrid MLA + linear-attn (mamba align) boots | ready | `W/vllm/kimi-linear-tp.sh:108-130` |
| 2 | Same L1 round trip (cold == LMCache-served, retrieves > 0) | byte-identical | `W/vllm/kimi-linear-tp.sh:162` → `l1-round-trip-verification.sh:114-133` |
| 3 | SGLang: lmcache_driven only, CHUNK_SIZE % PAGE_SIZE == 0, MAMBA_TRACK_INTERVAL % PAGE_SIZE == 0 | config guards | `W/sglang/kimi-linear-tp.sh:40-56` |

### vllm_bench (2 GPU, vLLM × zmq/grpc, **baseline**) — pipeline.yml:133-139, retry 3
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | total_input_tokens LMCache and baseline | expected ±1% | `W/vllm/vllm-bench.sh:134-150` |
| 2 | completed == NUM_PROMPTS (50), both servers | exact | `W/vllm/vllm-bench.sh:152-164` |
| 3 | LMCache throughput ≥ baseline × (1 − 5%) | `MAX_SLOWDOWN_PERCENT=5` | `W/vllm/vllm-bench.sh:27,166-190` |
| 4 | LMCache > 10% faster on random data | **warning only**, not a fail | `W/vllm/vllm-bench.sh:195-216` |
| 5 | Cold/warm replay: HTTP 200; `cached_token_stats` has 3 non-negative int keys | exact | `W/vllm/vllm-bench.sh:306-310,327-346` |
| 6 | warm `num_lmcache_cached_tokens` > cold and > 0 | strict | `W/vllm/vllm-bench.sh:379-385` |
| 7 | LMCache log "Retrieved N tokens" count grew | after > before | `W/vllm/vllm-bench.sh:396-402` |

### long_doc_qa (2 GPU, vLLM + SGLang, **baseline**) — pipeline.yml:158-164
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | Both result JSON files exist | present | `W/common/long-doc-qa.sh:115-118` |
| 2 | query TTFT vs baseline | vLLM: ≥60% faster; SGLang: ≤0% slower | `W/common/long-doc-qa.sh:31,226-229`; `scripts/engines/sglang.sh:57` |
| 3 | query round time vs baseline | vLLM: ≥15% faster; SGLang: ≤20% slower | `W/common/long-doc-qa.sh:32,230-233`; `scripts/engines/sglang.sh:58` |
| 4 | Missing or invalid number → FAIL | — | `W/common/long-doc-qa.sh:209-211` |

### long_doc_qa_l2 (2 GPU, vLLM only (SGLang skipped), **baseline**) — pipeline.yml:170-176
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | Kill LMCache + engine, relaunch with mock L2 (`skip_l1`, 4 GB/s); engine ready again | ready in 300 s | `W/common/long-doc-qa-l2.sh:76-165` |
| 2 | L2 query round-time speedup vs baseline | ≥1.3× | `W/common/long-doc-qa-l2-verify.sh:113-120` |
| 3 | L2 TTFT speedup | ≥1.5× | `W/common/long-doc-qa-l2-verify.sh:122-129` |
| 4 | Warmup overhead | ≤1.2× | `W/common/long-doc-qa-l2-verify.sh:131-138` |
| 5 | `/metrics` fetchable | 5 tries × 2 s | `W/common/long-doc-qa-l2-verify.sh:167-184` |
| 6 | L1 write, L2 store submitted, store completed, prefetch lookups, L2 hit keys, prefetch loaded | each > 0 | `W/common/long-doc-qa-l2-verify.sh:238-260` |
| 7 | 5 counters + 4 histograms advanced, with labels (`l2_name`, `model_name`, `worker_id`) | > 0 + label present | `W/common/long-doc-qa-l2-verify.sh:341-389` |
Note: it reuses the `long_doc_qa` baseline only if it ran in the same pod (`long-doc-qa-l2.sh:202-215`). In CI the steps run in separate pods, so the baseline is run again.

### deadlock (2 GPU TP=2, vLLM only (SGLang skipped), no baseline) — pipeline.yml:185-191
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | LMCache PID alive before start | alive | `W/common/deadlock.sh:21-25` |
| 2 | `lmcache bench engine` random-prefill, 50 req × 30K tokens, finishes | ≤180 s | `W/common/deadlock.sh:16,54-71` |
Model is **DeepSeek-V2-Lite, dummy weights**, TP=2, block 64, `mq_timeout=60` (`scripts/run-single-test.sh:114-123`; `scripts/engines/vllm.sh:330-360`). This is not Qwen3-14B as `01_ANALYSIS.md` says.

### mp_autostart_tp2 (2 GPU TP=2, vLLM, no baseline) — pipeline.yml:196-202
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | LMCache port free before start | not listening | `W/vllm/mp-autostart-tp2.sh:24-27` |
| 2 | vLLM TP=2 (**dummy weights**) ready | 600 s | `W/vllm/mp-autostart-tp2.sh:84,103-105` |
| 3 | Log has "Auto-starting LMCache MP server" and "became healthy" | grep | `W/vllm/mp-autostart-tp2.sh:108-118` |
| 4 | ZMQ PING to the auto-started server | healthy in 5 s | `W/vllm/mp-autostart-tp2.sh:120-137` |

### p2p (2 GPU, vLLM, two LMCache + two vLLM + coordinator; **not** a baseline engine) — pipeline.yml:210-216
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | LMCache A sees ≥1 P2P peer via `/status` | within MAX_WAIT | `W/vllm/p2p.sh:116-135` |
| 2 | Both vLLM ready | MAX_WAIT | `W/vllm/p2p.sh:142-159` |
| 3 | Engine B `num_lmcache_cached_tokens` > 0 for a prompt only A saw | > 0 | `W/vllm/p2p.sh:193-217` |

### lm_eval_{lmcache_driven, engine_driven} (1 GPU, vLLM + SGLang) — pipeline.yml:245-267
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | vLLM: two gsm8k runs (300 samples, greedy) give **identical sorted samples JSONL** | exact diff | `W/common/lm-eval.sh:64-106,270-273` |
| 2 | SGLang: score mode, drift and floor | drift ≤ 0.01, score ≥ 0.80 | `scripts/engines/sglang.sh:68-69`; `W/common/lm-eval.sh:193-228` |
| 3 | SGLang: L1 read chunks grew in run 2, after a radix-cache flush | after > before | `scripts/engines/sglang.sh:63`; `W/common/lm-eval.sh:238-259` |

### lm_eval_preemption (1 GPU, vLLM only (SGLang skipped), GPU mem 0.4, 256 concurrent) — pipeline.yml:291-313
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | Score drift between run 1 and run 2 | ≤ `SCORE_TOLERANCE` = **0.05** default (pipeline comment says 0.01; nothing sets 0.01 for vLLM) | `W/common/lm-eval.sh:19,175-176`; pipeline.yml:290 |
| 2 | Both scores | ≥ 0.80 | `W/common/lm-eval.sh:20,177-178` |
| 3 | `<preempted>` count grew in run 1 and in run 2 | strict | `W/common/lm-eval.sh:179-182`; `scripts/engines/vllm.sh:296-305` |

### preemption_correctness (2 GPU, vLLM, async 0/1, **baseline** used as ground truth) — pipeline.yml:328-346
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | ref rung (baseline, concurrency 3): 0 preemptions; D rung (LMCache, concurrency 40): >0 | exact | `W/vllm/preemption-correctness.sh:123-132` |
| 2 | ref answered >0 requests | > 0 | `W/vllm/preemption-correctness.sh:144-147` |
| 3 | D answer count == ref | exact | `W/vllm/preemption-correctness.sh:154-157` |
| 4 | D answers == ref answers by request id; same id set | 0 different | `W/vllm/preemption-correctness.sh:168-177` |
| 5 | ≥1 request reloaded KV after preemption (`<resume-load>` log) | > 0 | `W/vllm/preemption-correctness.sh:198-209` |

### fault_tolerance (1 GPU, vLLM) — pipeline.yml:355-361
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | Old processes free their ports; relaunch with `kv_load_failure_policy=recompute` | ports free | `W/vllm/fault-tolerance.sh:60-80,66` |
| 2 | Warmup bench 50/50 completed | exact | `W/vllm/fault-tolerance.sh:117-120,138-141` |
| 3 | Kill LMCache at 40% of warmup time; bench still 50/50 | exact | `W/vllm/fault-tolerance.sh:145,164-181` |
| 4 | Bench with no LMCache at all: 50/50 | exact | `W/vllm/fault-tolerance.sh:189-194` |

### restart_recovery (1 GPU, vLLM × zmq/grpc; SGLang skipped) — pipeline.yml:366-372
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | Round 1 bench: all 100 succeed, 0 failed | exact | `W/common/restart-recovery.sh:88-91,223-226` |
| 2 | Round 1 L1 writes > 0 | > 0 | `W/common/restart-recovery.sh:234-237` |
| 3 | After kill + relaunch: `/healthcheck` OK | 60 s | `W/common/restart-recovery.sh:127-138,248-252` |
| 4 | Worker re-registered (`/status` context meta not empty) | ≤150 s | `W/common/restart-recovery.sh:140-167,254-260` |
| 5 | Round 2: all succeed; L1 writes > 0 and ≥ 80% of round 1 | 80% | `W/common/restart-recovery.sh:267-298` |

### cache_stats (1 GPU, vLLM) — pipeline.yml:377-383
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | Cold + warm requests HTTP 200 | 200 | `W/vllm/cache-stats.sh:52-56` |
| 2 | `kv_transfer_params.cached_token_stats` has 3 non-negative int keys | exact | `W/vllm/cache-stats.sh:70-96` |
| 3 | warm LMCache tokens > cold and > 0 | strict | `W/vllm/cache-stats.sh:126-133` |
| 4 | No opt-in → no `kv_transfer_params` in response | absent | `W/vllm/cache-stats.sh:196-208` |
P1 log markers: the test runs about **2 s** after a **~260 s** engine start (`outputs/P1/raw/log_markers.json`).

### lazy_offload (1 GPU, vLLM, chunk 16) — pipeline.yml:391-397
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | vLLM log shows FIFO lazy offload, threshold 2 | grep | `W/vllm/lazy-offload.sh:156-160` |
| 2 | Chunk counts strictly increase per request | strict | `W/vllm/lazy-offload.sh:169-173` |
| 3 | Requests 1 and 2: L1 write delta == 0; request 3 delta == request 1 chunks | exact | `W/vllm/lazy-offload.sh:196-203` |

### http_api (1 GPU, vLLM + SGLang) — pipeline.yml:402-408
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | Warmup completion through engine | HTTP 200 | `W/common/http-api.sh:151-163` |
| 2 | ~30 HTTP endpoint checks (/, /healthcheck, /config, /status, /metrics, /env, /loglevel incl. 400, threads, cache clear, quota CRUD + 400s, version) | exact code + JSON key | `W/common/http-api.sh:174-374` |
| 3 | `lmcache describe kvcache` and `lmcache kvcache clear` exit 0 and print expected text | exit 0 + text | `W/common/http-api.sh:391-416` |
| 4 | Any failure → exit 1 | count > 0 | `W/common/http-api.sh:431-435` |
The engine is used only for one warmup request.

### gds_smoke (1 GPU, vLLM, GDS L1 slab on /scratch) — pipeline.yml:413-419
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | 4 cold + 4 warm requests HTTP 200 | 4/4 | `W/vllm/gds-smoke.sh:52` |
| 2 | `/reset_prefix_cache` HTTP 200 | 200 | `W/vllm/gds-smoke.sh:72-77` |
| 3 | "Retrieved" log count grew | after > before | `W/vllm/gds-smoke.sh:89-93` |
| 4 | warm text == cold text for each prompt | byte-identical | `W/vllm/gds-smoke.sh:99-111` |

### cpu_e2e_validation (0 GPU, vLLM-CPU, opt-125m, shm / inline / server_copy) — pipeline.yml:447-467
Script: `.github/scripts/run-cpu-e2e-validation.sh`. The same script runs in GHA `cpu_device.yml`
(opt-125m and **DeepSeek-V2-Lite dummy 2-layer MLA**, `.github/workflows/cpu_device.yml:102-133`).
| # | What is checked | Threshold | file:line |
|---|---|---|---|
| 1 | Server in the right transport; response structure OK | exact | `run-cpu-e2e-validation.sh:610,682-686` |
| 2 | Transport mode in log (lmcache_driven / shm / inline) | grep | `run-cpu-e2e-validation.sh:703-717` |
| 3 | First request: L1 write ≥1 chunk (store) | ≥1 | `run-cpu-e2e-validation.sh:773-777` |
| 4 | Second request: L1 read ≥1 (hit) | ≥1 | `run-cpu-e2e-validation.sh:788-791` |
| 5 | External prefix-cache reset succeeds; then no stale read, and a re-store happens | read=0, write≥1 | `run-cpu-e2e-validation.sh:801-829` |
| 6 | Hit after repopulate; hit after **vLLM restart** (cross-instance) | ≥1 | `run-cpu-e2e-validation.sh:841-864` |
| 7 | All 5 outputs identical (temp 0) | exact | `run-cpu-e2e-validation.sh:870-880` |
| 8 | Different prompt → no hit (negative test) | read=0 | `run-cpu-e2e-validation.sh:897-901` |

### Engine-free reference: `lmcache bench server` (GHA `cpu_device.yml:282-296`, `.github/scripts/cpu_server_bench_test.sh:148-168`)
Checks lookup success, store/retrieve success per worker rank, and **server-side checksums** of
deterministic KV (`lmcache/cli/commands/bench/server_bench/cases/baseline.py:24-33,175-215,252,280`;
`client.py:432-606`). Options: `--mode cpu|gpu`, `--tp-size`, `--use-mla`, `--kvcache-shape-spec`,
`--concurrency` (see `outputs/P4/server_bench_gaps.md`).

---

## (b) Evidence: real catches and guards

### b1. Confirmed or likely catches (30-day Buildkite data + log search)

From `outputs/P1/jobs_all_30d.csv`: 59 "failed then passed later on the same PR" pairs. I opened the
logs of the ones that look real.

| Evidence | What failed | Root cause (from log) | Class | Real? | Cheapest layer that also failed |
|---|---|---|---|---|---|
| PR #5383, build 5634 (2026-10-13) | ~11 jobs: long_doc_qa, mp_autostart_tp2, lm_eval ×2, lm_eval_preemption ×2, preemption_correctness ×2, fault_tolerance, cpu_e2e ×3 | `AttributeError: 'LMCacheMPSchedulerAdapter' object has no attribute 'experimental'` at `lmcache_mp_connector.py:743` in connector `__init__` (log of cpu_e2e shm job) | connector/engine API | **Yes** | **cpu_e2e_validation** (0 GPU). A UT that builds the connector would also catch it (guess) |
| PR #4018 (closed), build 5466 (2026-10-06) | restart_recovery ×2, long_doc_qa_l2 | `FAIL: round 2 only 25.9% of round 1 writes (threshold: 80%)` — PR changed host pinning to start at worker registration | restart/lifecycle | **Likely** (PR was closed, not merged) | restart_recovery only. No cheaper layer restarts the server with a real worker |
| PR #5150, build 5757 | lm_eval_preemption, vllm_bench, long_doc_qa_l2 | `setup-env.sh failed … Failed to fetch download.pytorch.org` | CI infra | No | — |
| PR #5556, build 6183 | mp_autostart_tp2 | pip 503 from download.pytorch.org | CI infra | No | — |
| PR #5556, build 6183 | long_doc_qa_l2 | `L2 TTFT speedup: 1.33x (need >= 1.5x)` on an unrelated L2-adapter PR | perf threshold | No (flake) | — |
| PR #5150, build 6089 | long_doc_qa ×3 attempts | `query_ttft 56.9% faster, need >= 60%` | perf threshold | No (flake) | — |
| PR #5557, build 5530 | fault_tolerance | `ZMQError: Address already in use tcp://localhost:6555` after relaunch | CI infra (test harness) | No | — |
| PR #5524, build 5609 | cpu_e2e shm | `libnuma.so.1 is unavailable` | CI infra | No | — |
| PR #5795, build 5834 | dsv4_flash_tp ×3 attempts | DeepGEMM build failed against torch 2.14 headers; fixed on dev by #5829 | packaging/deps | Yes, but upstream/env, not LMCache code | dsv4 only |
| PR #6234, build 6371 | ~22 jobs, exit 128 | checkout/git error on the whole build | CI infra | No | — |
| Many PRs, exit 2 (kimi sglang ×6, dsv4 sglang ×6, gds ×4) | — | exit 2 = `setup-env.sh` dependency install failure (checked 2 samples) | CI infra | No (guess for unsampled ones) | — |

30-day totals (final attempts, all branches, `outputs/P1/jobs_all_30d.csv`): exit 128 ≈ 47 jobs,
exit 2 ≈ 20, exit 1 ≈ 75 (mixed). Retried attempts are concentrated in perf workloads:
long_doc_qa_l2 131, long_doc_qa 108, vllm_bench 92, dsv4 76, kimi 50.

### b2. Catches and guards from 6 months of PR history

| PR / commit | Date | What happened | Class | Workload | Type |
|---|---|---|---|---|---|
| #4801 | 08-29 | "every k3-multiprocess build has failed `dsv4_flash_tp`": vLLM 0.28.1rc1 nightly broke DSV4 sparse-MLA on SM120 (`eidx must be contiguous`). The canary verifies only `vllm_bench`, so it pinned a bad version | packaging/deps (upstream kernel) | dsv4_flash_tp | **Catch** (upstream) |
| #4851 | 09-01 | Follow-up: scoped the vLLM 0.27.1 pin to dsv4 only | packaging/deps | dsv4_flash_tp | Fix of catch |
| #5829 | 10-18 | DeepGEMM external build broke (Buildkite #5819); switched to bundled DeepGEMM | packaging/deps | dsv4_flash_tp | **Catch** (env) |
| #4724 | 08-25 | "All `cpu_e2e_validation (server_copy)` legs fail": vLLM nightly put all layers in one buffer (`storage_offset != 0`), CPU SHM path asserted | KV layout (engine API change) | cpu_e2e_validation | **Catch** (real LMCache fix in `lmcache/v1/platform/cpu/shm.py`) |
| #3538 | 06-05 | Hot fix: pin vLLM commit for the CPU MP test (vLLM #42082 broke it) | packaging/deps | cpu_e2e_validation | **Catch** (upstream) |
| #4037 | 07-07 | vLLM nightly imports torchcodec → needs FFmpeg; `vllm serve` fails | packaging/deps | cpu_e2e_validation | **Catch** (env) |
| #5100 | 09-14 | Buildkite CPU job used an unverified vLLM-CPU nightly and failed | packaging/deps | cpu_e2e_validation | **Catch** (env) |
| #5822 | 10-19 | `grep -q` + pipefail gave false "missing library" (builds 5795, 5562) | CI infra | cpu_e2e_validation | Flake fix |
| #4488 | 08-11 | hma_lm_eval (gemma-4) broke after #3869/#4437 flipped the `separate_object_groups` default → wrong per-group store/retrieve | KV layout (hybrid) / config | hma_lm_eval_gemma4 (now disabled, pipeline.yml:353) | **Catch** |
| #4219 | 07-24 | Kimi-Linear MLA+Mamba under TP: rank-0-only store made other ranks load the wrong mamba shard → wrong output. Fix + new `kimi_linear_tp` test | KV layout (hybrid/MLA) | kimi_linear_tp | **Guard** (found outside CI — UNKNOWN how) |
| #5892 | 10-20 | SGLang Kimi-Linear did not start (Mamba `slice_axis=1` rejected). Found while adding SGLang kimi test (#5862) | KV layout / connector (SGLang) | kimi_linear_tp (sglang) | **Catch** during test bring-up |
| #4406 | 08-04 | Kimi test flaky: raise timeout, pin autotune | CI infra | kimi_linear_tp | Flake fix |
| #3208 | 05-07 | LMCache restart → workers must re-register. Fix + `restart_recovery` test | restart/lifecycle | restart_recovery | **Guard** |
| #4072 | 11-02 | Restarting MP server killed a production vLLM (engine_driven SHM close race). Found in production (#4069), UT added | restart/lifecycle, concurrency | — (not caught by CI) | **Miss**: restart_recovery runs lmcache_driven only (`restart-recovery.sh:143-145` supports engine_driven, but the pipeline matrix has no mode axis, pipeline.yml:366-372) |
| #5248 | 09-26 | Preemption handling: resumed requests reload KV; store must wait before blocks are reused. Added `preemption_correctness` | store / preemption | preemption_correctness | **Guard** |
| #4033 | 07-13 | Added lm_eval_preemption | preemption | lm_eval_preemption | Guard |
| #4830 | 09-03 | Engine-driven async copies reused buffers mid-copy: **gsm8k 0.80 → 0.00, no error**. Found manually on 8×H100 with the pickle transport | store/retrieve data corruption (kernel/stream) | lm_eval-type check (manual, not CI) | Catch by the *lm_eval method*, not by CI. UT added (`tests/v1/multiprocess/test_engine_driven_async_copy_lifetime.py`) |
| #5091 | 09-18 | MP cache reset wired; verified through CPU E2E (zmq + grpc) | connector/engine API | cpu_e2e_validation | Guard (CPU) |
| #3336, #3382 | 05-26, 06-03 | store/retrieve CUDA×GIL deadlock (found on MI350X); block-exhaustion deadlock (found on MI355X) | concurrency/deadlock | — (found on AMD, outside this pipeline) | `deadlock` workload is the guard for this class (comment `W/common/deadlock.sh:5-7`) |
| #6256 | 11-03 | One blocked ZMQ client froze others (hang) | concurrency | — (UT in `tests/v1/multiprocess/test_mq.py`) | UT catch |
| #5457, #5469, #5911, #5976, #3382, #4262 | 06–10 | Found on Kimi-K3 / AgentX / DSV4.1 / NVFP4 production-size runs (MI355X, B200, TP8) | lookup locks, multi-group failure, store bound, SWA prefix, hang | — | **Miss** by MP CI (scale/model not covered). Fixed with UTs |
| #3405 | 05-27 | Thresholds tightened ("Recent CI runs show 77–84% TTFT improvement") | perf | long_doc_qa, l2 | Tuning |
| #3816, #5227, #3498 | 06–09 | Retry policies and longer timeouts for flaky MP steps | CI infra | all, vllm_bench | Flake fixes |
| #3910 | 06-29 | Pin vLLM to canary-verified version (canary = `vllm_bench`) | packaging/deps | vllm_bench (as canary) | Infra |

Not found: any PR in 6 months whose text says `cache_stats`, `http_api`, `lazy_offload`,
`gds_smoke`, `fault_tolerance`, `p2p` or `mp_autostart_tp2` caught a bug (gh searches in
`scratchpad/gh_search1.txt`). These only show up as "test added" or "CI refactor" PRs.
UNKNOWN: catches that never reached a PR text (an author fixes before pushing again). To find out,
mine every PR with an MP failure in `outputs/P1/jobs_all_30d.csv` and open the logs for all of them
(I opened 9).

---

## (c) Matrix: bug class × layer

Layers:
- **UT** = `tests/v1/**`. Buildkite UT pod: 1 GPU, no vLLM (`.buildkite/k3_tests/unit/run.sh:3,29`).
  GHA UT: CPU, with vLLM installed (`.github/workflows/test.yml:117,129`).
- **SB** = `lmcache bench server` (CPU in GHA; GPU mode exists).
- **CPU-E2E** = cpu_e2e_validation (vLLM-CPU, opt-125m; GHA also DSV2-Lite dummy MLA).
- **1G1E** = 1 GPU, 1 engine (lm_eval, cache_stats, restart_recovery, …).
- **2G+** = dual-engine or multi-GPU (baseline, TP, p2p).

Marks: ✅ = can catch, with an existing test as proof. ◐ = partly, or only with a small new test.
❌ = cannot.

| Bug class | UT | SB | CPU-E2E | 1G1E | 2G+ | Proof (existing tests) |
|---|---|---|---|---|---|---|
| Cache identity / hash | ✅ | ✅ | ✅ | ✅ | ✅ | `tests/v1/test_cache_identity.py`, `tests/v1/multiprocess/test_token_hasher.py`, `test_key_resolver.py`, `tests/v1/distributed/test_object_key_identity.py`; SB checksums; CPU-E2E negative test `run-cpu-e2e-validation.sh:897-901` |
| Lookup / prefix | ✅ | ✅ | ✅ | ✅ | ✅ | `tests/v1/multiprocess/test_apc_covered_lookup.py`, `test_query_lookup_hits.py`, `test_lookup_wait_prefetch.py`, `tests/v1/test_mp_nonblocking_lookup.py`; CPU-E2E hit/miss `:788-901` |
| Store (async, bounds) | ✅ | ✅ | ✅ | ✅ | ✅ | `tests/v1/test_mp_tracker_store_bound.py`, `tests/v1/test_mp_connector_kv_roles.py`; CPU-E2E `:773-777` |
| L2 / storage data flow | ✅ | ◐ (needs L2 config, see P4) | ◐ (no L2 configured) | ✅ (l2 is 2G only because of the baseline) | ✅ | `tests/v1/distributed/l2_adapters/*`, `test_l1_l2_state_metrics.py`, `tests/tools/test_long_doc_qa_l2_verify.py` |
| Restart / lifecycle (server restart, worker re-register) | ◐ | ◐ (no kill/restart scenario yet) | ◐ (only vLLM restart, `:848-864`) | ✅ | — | `tests/v1/test_vllm_mp_adapter.py` (re-register callback), `tests/v1/multiprocess/test_worker_liveness.py`, `test_transfer_ctx_guard.py`, `test_sigterm_cleanup.py` |
| Fault tolerance (server dies, engine keeps serving) | ◐ | ❌ | ◐ | ✅ | — | `tests/v1/test_mp_connector_kv_roles.py` (failure policy, #5469), `test_kv_load_policy.py` |
| Concurrency / deadlock / hang | ✅ (logic) | ✅ (`--concurrency`) | ◐ | ◐ | ✅ (TP=2 + CUDA events) | `tests/v1/multiprocess/test_mq.py`, `test_completion_recorder.py`, `test_free_locks.py`, `tests/v1/platform/devices/cuda/test_timeline_semaphore_event_ipc.py` |
| Preemption / resume | ◐ | ❌ | ❌ | ✅ (lm_eval_preemption) | ✅ (preemption_correctness) | `tests/v1/test_decode_save_and_preemption.py`, `test_mp_connector_kv_roles.py` |
| KV layout: MLA / fp8 / hybrid (real model, TP) | ◐ (shape logic) | ◐ (`--use-mla`, `--kvcache-shape-spec`, no real engine) | ◐ (DSV2-Lite dummy MLA in GHA; vLLM CPU layout catch #4724) | ◐ | ✅ only real proof (dsv4, kimi) | `tests/v1/test_vllm_kv_cache_group_edits_mla.py`, `test_vllm_kv_cache_groups.py`, `test_vllm_mamba_unified_view_layouts.py`, `tests/v1/gpu_connector/test_kv_format_*.py`, `test_unified_sglang_kv_adapter.py` |
| Kernel / CUDA / stream ordering | ✅ (GPU UT pod) | ✅ (`--mode gpu`) | ❌ | ✅ | ✅ | `tests/v1/test_mem_kernels.py`, `test_mp_mem_kernels.py`, `tests/v1/multiprocess/test_engine_driven_async_copy_lifetime.py`, `test_direct_copy_transfer_gpu.py` |
| Silent corruption seen only in model output | ❌ | ◐ (checksums catch byte errors, not wrong block mapping inside the engine) | ✅ (5 outputs identical) | ✅ (lm_eval, gds_smoke) | ✅ | CPU-E2E `:870-880`; `W/common/lm-eval.sh:64-106` |
| Connector / engine API (startup, hooks, kv_transfer_params) | ◐ (GHA CPU UT with vLLM: `tests/v1/test_mp_connector_*.py`, `test_vllm_mp_adapter.py`) | ❌ | ✅ (PR #5383 proof) | ✅ | ✅ | `tests/v1/test_mp_connector_autostart.py`, `test_mp_server_autostart.py`, `test_mp_connector_kv_roles.py` (cached_token_stats) |
| HTTP API / CLI / metrics surface | ✅ | ✅ (`--url` HTTP) | ✅ (metrics scrape) | ✅ | ✅ | `tests/v1/multiprocess/http_apis/*`, `test_http_server.py`, `test_http_quota_endpoints.py`, `tests/v1/mp_observability/*` |
| P2P peer transfer | ✅ (controller, adapter) | ◐ (two servers + client, research item) | ❌ | ❌ | ✅ | `tests/v1/distributed/l2_adapters/test_p2p_l2_adapter_integration.py`, `tests/v1/multiprocess/test_p2p_controller.py` |
| GDS / cuFile | ✅ (UT pod has /scratch GDS) | ◐ | ❌ | ✅ | — | `tests/v1/gpu_connector/gds_backends/test_cufile.py`, `tests/v1/distributed/test_gds_l1_config.py` |
| Perf (TTFT, throughput) | ❌ | ◐ (server-side latency only) | ❌ | ◐ (stored baseline, see P5) | ✅ today | — |
| Packaging / deps (vLLM nightly, DeepGEMM, FFmpeg) | ◐ (imports only) | ◐ | ✅ for vLLM-CPU | ✅ for vLLM-GPU | ✅ for model-specific kernels (dsv4) | #4801, #4724, #4037, #5829 |
| CI infra (pip 503, git 128, ports) | n/a | n/a | n/a | n/a | n/a | Causes most red MP jobs (b1) |

---

## (d) Conclusions

### d1. Workloads whose catches are fully covered by cheaper layers

| Workload | GPUs × jobs | Why the cheaper layer is enough | Cheaper layer |
|---|---|---|---|
| `cache_stats` | 1 × 1 | Checks only that `cached_token_stats` exists and grows. Connector UT covers the fields (`tests/v1/test_mp_connector_kv_roles.py`). The CPU-E2E hit check covers hit counting. The test body runs ~2 s after a ~260 s engine start | UT + CPU-E2E (add one `cached_token_stats` curl to CPU-E2E) |
| `http_api` | 1 × 2 | The engine is used for one warmup request only. All ~30 checks are server HTTP/CLI (`tests/v1/multiprocess/http_apis/*`) | UT + SB (server + HTTP, no engine) |
| `lazy_offload` | 1 × 1 | FIFO policy logic is in UT (`tests/v1/lazy_offload/test_fifo_policy.py`, `test_mp_connector.py`). E2E only counts L1 writes | UT + CPU-E2E (vLLM-CPU supports the same connector config) *(guess: not tried on CPU)* |
| `mp_autostart_tp2` | 2 × 1 | Already uses **dummy weights** (`mp-autostart-tp2.sh:84`). Checks a log line + ZMQ ping. UT: `tests/v1/test_mp_connector_autostart.py`, `test_mp_server_autostart.py`. The TP=2 part is only "two ranks share one autostart" | UT + CPU-E2E with autostart; keep a TP=2 dummy run only on nightly |
| `fault_tolerance` | 1 × 1 | No catch in 6 months. Its 30-day failures were port reuse (infra). Engine-side recompute policy has UT (#5469 tests). Needs a real engine, but **any** small engine works | CPU-E2E + "kill server mid-run" step |
| `restart_recovery` | 1 × 4 | One likely catch (#4018). The check is "server restart → worker re-register → writes resume", which a vLLM-CPU engine can do. It is not GPU-specific for lmcache_driven IPC *(guess)* | CPU-E2E + restart step (or SB scenario, P4) |
| `long_doc_qa_l2` (data-flow + observability part) | 2 × 1 | Metrics and data-flow checks (`long-doc-qa-l2-verify.sh:238-389`) are not perf. They can run on CPU-E2E with a mock L2. Only the 1.3×/1.5×/1.2× perf part needs GPU and baseline | CPU-E2E with mock L2 + nightly perf |
| `deadlock` | 2 × 1 (SGLang job skipped) | Uses dummy DSV2-Lite. The class it guards (CUDA-driver×GIL, #3336/#2952) needs a GPU and CUDA events, but not a real model or TP=2 *(guess)*. SB `--mode gpu --concurrency` exercises the same server store/retrieve callbacks | SB GPU mode, 1 GPU; keep the TP=2 run on nightly |

### d2. Workloads that are the only catcher of something

| Workload | What only it catches | Evidence |
|---|---|---|
| `dsv4_flash_tp` | Sparse-MLA + fp8 + slot-compression layout with a **real** model at TP=4; model-specific kernel / vLLM breakage (DeepGEMM, flashinfer SM120) | #4801, #5829, `W/vllm/dsv4-flash-tp.sh:1-49` |
| `kimi_linear_tp` | Hybrid MLA + sharded mamba state across TP ranks (rank-0-only bug class); SGLang hybrid startup | #4219 (guard), #5892 (catch) |
| `preemption_correctness` | Exact-answer correctness when vLLM preempts and resumes with a KV reload (`<resume-load>`) | #5248, `W/vllm/preemption-correctness.sh:198-209` |
| `lm_eval_*` (GPU) | Silent corruption in **GPU** transfer paths (lmcache_driven IPC, engine_driven GPU) on a real model. CPU-E2E covers the CPU paths only | #4830 (score 0.80 → 0.00, no error) |
| `lm_eval_preemption` | Preemption + concurrency 256 without crash, on both transfer modes | #4033 |
| `gds_smoke` | cuFile GDS L1 read path is correct end to end | `W/vllm/gds-smoke.sh:89-111` (no catch found in history) |
| `p2p` | Real GPU-to-GPU peer fetch between two servers via coordinator | `W/vllm/p2p.sh:193-217` (no catch found) |
| `vllm_bench`, `long_doc_qa`, `long_doc_qa_l2` perf | Throughput / TTFT regressions. Also `vllm_bench` is the vLLM-nightly canary (#3910) | No real perf catch found in 6 months. Flaky (b1: 1.33× vs 1.5×, 56.9% vs 60%) |
| `cpu_e2e_validation` | Already the **cheapest** catcher of connector-startup and vLLM API/layout breaks | #5383, #4724, #3538 |

### d3. Gaps (bugs that every layer missed)

| Found where | Example | Missing layer |
|---|---|---|
| Production / large runs | #5457, #5469, #5911, #5976 (Kimi-K3, AgentX, DSV4.1, TP8) | Long-running agentic trace, multi-group failure injection |
| Restart in engine_driven SHM | #4072 | `restart_recovery` with `LMCACHE_MP_TRANSFER_MODE=engine_driven` |
| AMD deadlocks | #3336, #3382 | Only the AMD pipeline would see these (UNKNOWN whether it runs per PR — check `.buildkite/k3_tests/amd/pipeline.yml`) |

### d4. Other findings

1. `lm_eval_preemption` drift: the pipeline comment says "< 0.01" (pipeline.yml:290), but vLLM uses
   the default **0.05** (`W/common/lm-eval.sh:19`). Only SGLang sets 0.01 (`scripts/engines/sglang.sh:69`),
   and SGLang skips this workload. So the comment is wrong, or the check is looser than intended.
2. The `deadlock` model is DeepSeek-V2-Lite dummy, not Qwen3-14B (fix row in `01_ANALYSIS.md`).
3. `p2p` starts two LMCache engines, not a baseline. `preemption_correctness` uses the baseline as
   **ground truth** (correctness, not perf).
4. `vllm_bench` speedup > 10% is a warning only (`vllm-bench.sh:213-216`).
5. Most PR-time MP red is infra: exit 128 checkout, exit 2 pip/HF 503, port reuse. A retry or a
   cached wheel mirror would remove more red than any test change.

---

## How to check or extend this

| Question | How |
|---|---|
| More real catches in 30 days | For each fail→pass pair in `outputs/P1/jobs_all_30d.csv`, run `mcp__buildkite__search_logs` with pattern `FAIL\|Error\|Traceback` (I did 9 of 59) |
| Was #4018's restart failure real? | Re-run `restart_recovery` on PR #4018's head `9e934666` |
| Can CPU-E2E replace restart/fault/lazy | P3 mutation tests: seed "skip re-register" in `lmcache/integration/vllm/vllm_multi_process_adapter.py` and run `.github/scripts/run-cpu-e2e-validation.sh` with a restart step |
