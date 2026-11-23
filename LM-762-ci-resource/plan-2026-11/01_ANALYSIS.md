# 01 — Analysis: current state

Source checked: local clone `third_party/LMCache` at `fcd50cea` (2026-11-04).
Paths below are relative to that repo.

## 1. Why this task matters

From the parent PDF: 553 PRs opened / 278 merged in 30 days, 620 open. GPU CI is the bottleneck.
The multiprocess pipeline is the heaviest PR-time GPU consumer, and most of its cost is **starting
engines**, not running LMCache logic:

- Every GPU workload loads a 14B–160GB model (default `Qwen/Qwen3-14B`; DSV4-Flash fp8 TP=4; Kimi-Linear-48B).
- Several workloads start a **second baseline engine** on another GPU just to compare.
- Engine start + model load is often longer than the actual test.

## 2. Multiprocess workload inventory

> Corrected 2026-11-05 with P2/P7 findings (deadlock model, p2p, preemption baseline role, drift value).

From `.buildkite/k3_tests/multiprocess/pipeline.yml`. "Jobs" = matrix expansion.

| Workload | GPUs | Engines × transport | Jobs | Timeout | Baseline engine? | Model | What it really checks |
|---|---|---|---|---|---|---|---|
| dsv4_flash_tp | 4 | vllm, sglang × zmq | 2 | 90 | no | DeepSeek-V4-Flash | sparse-MLA + fp8 KV layout, byte-identical greedy from L1 |
| kimi_linear_tp | 2 | vllm, sglang × zmq | 2 | 60 | no | Kimi-Linear-48B | hybrid/linear-attn KV layout round trip |
| vllm_bench | 2 | vllm × zmq, grpc | 2 | 30 (retry 3) | **yes** | Qwen3-14B | throughput ≤ 5% slower than baseline + warm-hit retrieve |
| long_doc_qa | 2 | vllm, sglang × zmq | 2 | 30 | **yes** | Qwen3-14B | TTFT ≥ 60% faster, round time ≥ 15% faster |
| long_doc_qa_l2 | 2 | vllm, sglang × zmq | 2 | 30 | **yes** | Qwen3-14B | L2 restart, data flow, perf |
| deadlock | 2 | vllm, sglang × zmq | 2 | 30 | no | DeepSeek-V2-Lite (dummy weights) | high-concurrency no-hang (SGLang job self-skips) |
| mp_autostart_tp2 | 2 | vllm × zmq | 1 | 30 | no | Qwen3-14B | connector auto-start with TP=2 |
| p2p | 2 | vllm × zmq | 1 | 30 | no (2 LMCache engines, not a baseline) | Qwen3-14B | peer L2 transfer |
| lm_eval_{mode} | 1 | common × zmq × 2 modes | 2–4 | 30 | no | Qwen3-14B | score drift between 2 runs, score ≥ SCORE_MIN |
| lm_eval_preemption | 1 | × 2 modes | 2–4 | 30 | no | Qwen3-14B | no crash under preemption, drift < 0.01 |
| preemption_correctness | 1 | async on/off | 2 | 45 | **yes** (ground truth for correctness, not perf) | Qwen3-14B | output equality under preemption |
| fault_tolerance | 1 | vllm × zmq | 1 | 30 | no | Qwen3-14B | LMCache server failure → engine keeps serving |
| restart_recovery | 1 | vllm, sglang × zmq, grpc | 4 | 30 | no | Qwen3-14B | server restart + worker re-register |
| cache_stats | 1 | vllm | 1 | 30 | no | Qwen3-14B | stats/metrics endpoints |
| lazy_offload | 1 | vllm | 1 | 30 | no | Qwen3-14B | lazy offload path |
| http_api | 1 | common × zmq | 2 | 30 | no | Qwen3-14B | HTTP API + CLI with live engine |
| gds_smoke | 1 | vllm | 1 | 30 | no | Qwen3-14B | GDS storage |
| cpu_e2e_validation | 0 (8 CPU, 256Gi) | vllm-cpu × 3 modes | 3 | 30 | no | opt-125m | full CPU E2E: shm / inline / server_copy |

**Observation:** roughly 35 GPU jobs per `full`/`mp` build, ~half of them 2–4 GPU. Many of them
check *LMCache server behavior* (restart, stats, HTTP API, deadlock, L2 flow, fault tolerance) that
does not need real model math.

## 3. What already exists that we can build on

| Asset | Where | Why it matters |
|---|---|---|
| `lmcache bench server` | `lmcache/cli/commands/bench/server_bench/` | Talks to a standalone LMCache MP server **with no engine**. Has `--mode cpu`, `--transfer-mode`, `--tp-size`, `--use-mla`, `--kvcache-shape-spec`, `--concurrency`. Cases: `baseline.py`, `concurrent.py`. **This is the seed of WS-A.** |
| CPU server bench in GHA | `.github/scripts/cpu_server_bench_test.sh`, `.github/workflows/cpu_device.yml` | Already a PR gate on Ubuntu + macOS. Proof that engine-free path works in CI. |
| `lmcache bench engine` / `quality_bench` | `lmcache/cli/commands/bench/` | Traffic generator + quality analysis — reusable for simulated client traffic. |
| `cpu_e2e_validation` | `.github/scripts/run-cpu-e2e-validation.sh` | Real vLLM-CPU + LMCache. Already supports `VLLM_LOAD_FORMAT=dummy` and `VLLM_HF_OVERRIDES` (shrink layers/experts). |
| `--load-format dummy` configs | `.buildkite/configs/*.yaml` | Precedent for random weights in CI. |
| Workload framework | `scripts/workloads/{common,vllm,sglang,verification}` + `workload-discovery.sh` | Name → script discovery; `LAUNCH_BASELINE` flag already exists in `launch-processes.sh`. |
| CPU-tested verifier | `long-doc-qa-l2-verify.sh` + `tests/tools/test_long_doc_qa_l2_verify.py` | Precedent: assertion logic split out and tested on CPU with stub inputs. |
| Many MP unit tests | `tests/v1/multiprocess/` (~60+ files: cache server, gRPC, HTTP, lookup, blend…) | Core logic is already well unit-tested; gap is the *process-level integration* layer. |

## 4. Acceptance criteria today (scattered)

| Criterion | Where it lives now | Value |
|---|---|---|
| Byte-identical greedy output | `dsv4-flash-tp.sh`, `kimi-linear-tp.sh`, `verification/l1-round-trip-verification.sh` | exact |
| lm_eval score drift | `common/lm-eval.sh` `SCORE_TOLERANCE` | **0.05** applies at runtime on vLLM; the "< 0.01" pipeline comment is wrong (only SGLang sets 0.01, and SGLang skips preemption) — see outputs/P7 C1 |
| lm_eval minimum score | `common/lm-eval.sh` `SCORE_MIN` | 0.80 default, overridable per model |
| TTFT / round time vs baseline | `common/long-doc-qa.sh` | TTFT −60%, round −15% |
| Throughput vs baseline | `vllm/vllm-bench.sh` `MAX_SLOWDOWN_PERCENT` | 5% |
| Rolling 5-day worst baseline | `comprehensive/scripts/run-single-config.sh` | max of last N days, adaptive threshold |
| ShareGPT output diff | `correctness/scripts/run-correctness.sh` | diff vs no-cache run |

Problem: no single place to see "what does PASS mean", which values are relaxed, and when a full run
is mandatory. This blocks equivalence-class decisions (Issue #4861 asks for shared model profiles).

## 5. Gaps

1. **No engine-free twin** for server-level workloads (restart, stats, HTTP, deadlock, L2, fault tolerance).
2. **Baseline engine used for perf comparisons** where a stored baseline (5-day worst) would do.
3. **No coverage map**: we don't know which bug classes each heavy workload catches that UT +
   server bench miss. Without it, any reduction is a guess.
4. **No rule** mapping changed paths → required test layer.
5. **Small-model set not defined** for the GPU smoke (only opt-125m on CPU).

## 6. Mapping to the critical path (from feature matrix)

| Critical path step | Engine needed to test? | Engine-free option |
|---|---|---|
| Connector + cache identity (F02) | no | UT + server bench with fixed token IDs |
| KV lookup hit/miss (F03) | no | server bench lookup/prefix cases |
| Async store (F06) | no | server bench store → lookup → retrieve |
| Load CPU/L2 KV (F05, F07) | no | server bench with L2 backend configured |
| GPU KV transfer (F04) | GPU yes, engine no | server bench `--mode gpu` with fake KV buffers |
| Resume inference / output parity (F12) | **yes** | small model / dummy weights smoke |
| TTFT (F14) | perf: yes | keep on nightly, compare to stored baseline |
| P2P (F08) | GPU yes, engine maybe | 2 servers + bench client (research item) |
