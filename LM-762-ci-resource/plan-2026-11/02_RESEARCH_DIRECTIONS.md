# 02 — Research directions

Answer these before writing production code. Each item has: question → method → output → owner (agent prompt ID in [04](04_AGENT_PROMPTS.md)).

## R1. Real cost baseline (do first)

| | |
|---|---|
| Question | How many GPU-minutes and wall-minutes does each multiprocess step use per PR? Which part is engine startup vs test body? |
| Method | Buildkite REST API (org `lmcache`, pipeline for multiprocess). Pull last 30 days of builds with `full`/`mp`. Per job: `started_at`, `finished_at`, `retried`, GPU count from label/group. Parse logs for "engine ready" timestamp to split startup vs body. Reuse `scripts/pull_buildkite_telemetry.py`. |
| Output | Table: workload × {p50 wall, p90 wall, GPU-min, startup share %, retry rate}. CSV in `LM-762-ci-resource/ci-analysis/data/ci_telemetry/`. |
| Prompt | P1 |

## R2. Coverage map: what does each heavy workload actually catch?

| | |
|---|---|
| Question | For each workload, which bug classes does it catch that UT + `lmcache bench server` + `cpu_e2e_validation` do not? |
| Method | (a) Read each workload script and list its assertions. (b) Git-mine: last ~6 months of PRs/commits where a multiprocess step failed on first push and the fix touched code (not infra). Classify root cause. (c) Optional: mutation test — seed 10–15 bugs in core paths (lookup off-by-one, wrong chunk hash, skip store, drop L2 write, leak on restart) and see which layers catch them. |
| Output | Matrix: bug class × test layer (UT / server bench / CPU E2E / GPU 1-engine / GPU dual-engine). Mark "only caught by engine". |
| Prompt | P2 (static + git), P3 (mutation) |

## R3. How far does `lmcache bench server` already go?

| | |
|---|---|
| Question | Can the existing server bench client simulate the request patterns of: restart_recovery, cache_stats, http_api, deadlock, long_doc_qa_l2, fault_tolerance? What is missing (multi-worker register, kill/restart server, L2 config, metric scraping, concurrency storm)? |
| Method | Read `server_bench/{client,config,cases/*}.py`, `cpu_server_bench_test.sh`. Try locally in CPU mode (WSL/Linux; macOS also supported). |
| Output | Gap list per workload + estimate (S/M/L). |
| Prompt | P4 |

## R4. Can we drop the baseline engine?

| | |
|---|---|
| Question | For `vllm_bench`, `long_doc_qa`, `long_doc_qa_l2`, `p2p`, `preemption_correctness`: is the baseline used for **correctness** (output equality) or **performance** (ratio)? |
| Method | Read scripts. For perf: check variance of baseline numbers across builds (R1 data). If stable → stored rolling baseline (like comprehensive 5-day worst). For correctness: can a no-cache second request on the *same* engine replace a separate baseline engine (clear prefix cache, `LMCACHE` disabled per request)? |
| Output | Per workload: "baseline → stored", "baseline → same-engine replay", or "baseline required (why)". GPU saving estimate. |
| Prompt | P5 |

## R5. Small-model / dummy-weight equivalence

| | |
|---|---|
| Question | Which small models cover the same KV layouts as the big ones? Does `--load-format dummy` + `--hf-overrides` (fewer layers/experts) keep the KV layout identical so layout bugs still show? |
| Method | List KV layout families: standard MHA/GQA, MLA, sparse-MLA+fp8, hybrid/linear (Kimi), SWA (gemma), HMA. For each, pick the smallest public model or a dummy-shrunk config. Verify layout = same `kvcache-shape-spec` as big model. Check byte-identical test still meaningful with dummy weights (yes for KV round trip; no for lm_eval scores). |
| Output | "Representative small-model set" table: family → model/config → GPU mem → which tests it can replace. |
| Prompt | P6 |

## R6. Acceptance criteria survey

| | |
|---|---|
| Question | Full list of thresholds, their defaults, per-step overrides, and who set them / why (git blame). Which ones conflict (e.g. drift 0.05 vs 0.01)? |
| Method | grep `SCORE_*`, `MAX_*SLOWDOWN*`, `THRESHOLD`, `TOLERANCE` across `.buildkite/`, `.github/`, `benchmarks/`. Read Issue #4861 thread for maintainer preferences. |
| Output | Input for [05_acceptance_profile.draft.yaml](05_acceptance_profile.draft.yaml). |
| Prompt | P7 |

## R7. Path → test-layer rule

| | |
|---|---|
| Question | Which directories are "core" (engine-agnostic) vs "adapter/connector" vs "kernel" vs "infra"? |
| Method | Map `lmcache/` tree: `v1/multiprocess/*`, `v1/distributed/*`, storage backends → core; `integration/vllm/*`, `integration/sglang/*`, mp connectors → adapter; `csrc/*` → kernel. Cross-check with R2: which past bugs in "core" were only caught by engine tests? |
| Output | Path rules table + list of exceptions. |
| Prompt | P8 |

## R8. Upstream alignment (non-code)

- Read Issue #4861 discussion and any linked PRs; ask maintainers whether acceptance config should live in `tests/` or `benchmarks/` or a new `ci/profiles/`.
- Check open PRs touching `.buildkite/k3_tests/multiprocess/` to avoid conflicts.
- Find who owns the multiprocess pipeline (git log authors) — reviewer for our PRs.

## Decision gates after research

| Gate | Pass if | If fail |
|---|---|---|
| G1 (end W1) | R1 shows engine startup ≥ 40% of GPU-min for ≥ 5 workloads | Shift focus to queue/splitting directions instead |
| G2 (end W2) | R2 shows ≥ 3 workloads whose catches are fully covered by engine-free layers (+ small gaps fixable) | Only do WS-D + WS-E; stop WS-B |
| G3 (end W3) | Mutation test: engine-free twin catches ≥ 90% of seeded bugs the heavy test catches | Keep heavy test in PR tier, use twin only as early-fail gate |
