# P7 / R6 — GPU/E2E CI acceptance criteria inventory

- Date: 2026-11-04
- Repo: `third_party/LMCache` at `fcd50cea` (dev, 2026-11-04). The clone is **shallow** (boundary commit `521c23b7`, 2026-04-01).
  When blame shows `521c23b7`, the real origin is older: **UNKNOWN**. To find out: `git fetch --unshallow`, then `git log -S'<line>'`.
- Paths below are relative to the repo root. `MP` = `.buildkite/k3_tests/multiprocess`. `W` = `MP/scripts/workloads`.
- Active Buildkite pipelines (from the Buildkite API, 2026-11-04): `k3-multiprocess-test`, `k3-correctness-test`, `k3-comprehensive-test`,
  `k3-blend-test`, `amd-mp-test`, `xpu-mp-test`, `musa-mp-test`, `rbln-mp-test`, `metax-maca-mp-test`.
  Archived (dead code in repo): `deprecated-multiprocessing-test` (2026-09-09), `vllm-integration-tests` (2026-09-11), `k3-integration-test` (2026-10-21).

## 1. How the tiers work today

| Item | Fact | Source |
|---|---|---|
| When K3 pipelines run | On every PR build, if the PR changes relevant paths | `.buildkite/k3_tests/common_scripts/upload-pipeline.sh:40-60` |
| Skip label | `skip expensive ci` skips the pipeline | `.buildkite/k3_tests/common_scripts/helpers.sh:53-70` |
| Force label | `force-ci` overrides the skip and the path filter | `helpers.sh:60`, `upload-pipeline.sh:15` |
| Nightly (comprehensive) | Scheduled build with `NEED_UPLOAD=true` writes new baselines; PR builds compare against them | `.buildkite/k3_tests/comprehensive/BK_WEB_SETUP.md:23-27`, `comprehensive/pipeline.yml:119-126` |
| Nightly (multiprocess) | Only the `VERIFY_AND_PIN_VLLM/SGLANG` canary (runs `vllm_bench`, then pins the engine) | `MP/pipeline.yml:489-602` (`if:` at :496, :528) |
| Retries | `flaky-retry` = 2 retries; `vllm-bench-retry` = 3 retries; comprehensive `perf-retry` = 2 retries | `MP/pipeline.yml:10-24`, `comprehensive/pipeline.yml:5-10` |

So there is **no separate nightly tier** for multiprocess today. Every MP step is a PR step (if paths match).

## 2. Inventory — every PASS threshold

"Effective value" = what really applies at runtime for the named step. "Ovr" = per-step override.

### 2.1 Accuracy / correctness

| # | Criterion | Default (effective) | Overrides | File:line | Blame (commit, date, author, PR) | Protects | Pipeline / step |
|---|---|---|---|---|---|---|---|
| A1 | L1 round trip byte-identical (`cmp -s`) | exact | none | `W/verification/l1-round-trip-verification.sh:114` | bc9b1141, 2026-10-20, chunxiaozheng, #5859 | KV layout save/restore for big models (sparse-MLA fp8, hybrid linear) | MP `dsv4_flash_tp` (4 GPU), `kimi_linear_tp` (2 GPU), vLLM + SGLang |
| A2 | Retrieve is non-vacuous (retrieve count grows) | `after > before` | none | `l1-round-trip-verification.sh:127-132` | bc9b1141, #5859 | A1 is not a no-op | same as A1 |
| A3 | lm_eval samples identical (sorted JSONL `diff`) | exact | SGLang switches to score mode (see A4) | `W/common/lm-eval.sh:94` | 521c23b7 boundary → UNKNOWN (older) | KV hit path gives same generations as cold path | MP `lm_eval_{lmcache,engine}_driven` (vLLM); XPU `lm_eval_full_attn` |
| A4 | lm_eval score drift `|s1-s2| <= SCORE_TOLERANCE` | **0.05** | SGLang `lm_eval`: **0.01** (`MP/scripts/engines/sglang.sh:69`); `hma_lm_eval_qwen3_5`: 0.05 (`MP/scripts/run-single-test.sh:100`) | `W/common/lm-eval.sh:19`, check at `:175`, `:220` | ea44ea7d, 2026-07-14, Tony Lin, #4033 | Accuracy does not drift on cache hit / under preemption | MP `lm_eval_preemption` (vLLM, 0.05); MP `lm_eval` (SGLang, 0.01) |
| A5 | lm_eval score floor `SCORE_MIN` | **0.80** | `LM_EVAL_SCORE_MIN_DEFAULT` env (default 0.80, `MP/run.sh:27`). No step sets it today | `W/common/lm-eval.sh:20`, check at `:177`, `:222` | 9384ad22, 2026-09-05, VincyZhang, #4849 (first added in #4033) | Engine/model not broken overall | Only `score` + `preemption` modes. **Not used** in `samples` mode |
| A6 | Preemption really happened | preemptions grow in both runs | none | `W/common/lm-eval.sh:179-182` | ea44ea7d, #4033 | Test is non-vacuous | MP `lm_eval_preemption` |
| A7 | L1 retrieval during 2nd lm_eval run | `after > before` | on when `VERIFY_LMCACHE_RETRIEVAL=true` (SGLang `sglang.sh:63`, XPU `xpu/multiprocess/pipeline.yml:86`) | `W/common/lm-eval.sh:255` | UNKNOWN (not blamed) | Hit came from LMCache, not engine prefix cache | SGLang `lm_eval`, XPU `lm_eval_full_attn` |
| A8 | HMA lm_eval score drift | **0** (exact) | `hma_lm_eval_qwen3_5`: **0.05** (`run-single-test.sh:100`) | `W/vllm/hma-lm-eval.sh:41`, check at `:283` | ae328a66, 2026-06-09, Kuntai Du, #3556; override 65c2ae81, 2026-06-11, Kuntai Du, #3613 | Hybrid-allocator (per-group block size) KV | XPU `lm_eval_gdn` (0.05). MP `hma_lm_eval_gemma4` is **disabled** (`MP/pipeline.yml:353`) |
| A9 | HMA bit correctness: tokens + top-100 logprobs exact | exact | none | `W/vllm/hma_bit_correctness.py:65,94-109,262` | UNKNOWN (not blamed) | KDA/MLA/SWA/DSV4 hybrid restore | XPU `hma_kda_mla_correctness`, `hma_swa_correctness`, `hma_dsv4_correctness` |
| A10 | Preemption ShareGPT answers == reference | 0 different, 0 only-in-one | none | `W/vllm/preemption-correctness.sh:168-176` | 9a7b6050, 2026-09-25, Samuel Shen, #5248 | Preempted+resumed requests reload KV correctly | MP `preemption_correctness` (async 0/1), XPU |
| A11 | Preemption ShareGPT non-vacuous | ref must not preempt; LMCache rung must preempt and reload KV | none | `preemption-correctness.sh:124-131,206` | 9a7b6050, #5248 | Test is non-vacuous | same as A10 |
| A12 | ShareGPT diff vs base vLLM | 0 different, 0 only-in-one | `CORRECTNESS_MAX_ATTEMPTS` (default 3) | `.buildkite/k3_tests/correctness/scripts/run-correctness.sh:216` (retry `correctness/run.sh:27`) | 521c23b7 boundary → UNKNOWN; retry 604a7e5f, 2026-04-22, Samuel Shen, #3100 | LMCache output == vLLM output on real traffic | `k3-correctness-test` (1 GPU, Qwen2.5-14B) |
| A13 | `man bash` half-prefix output equal | exact (`!=`) | none | `correctness/scripts/run-correctness.sh:192` | 521c23b7 boundary → UNKNOWN | Partial prefix hit correctness | `k3-correctness-test` |
| A14 | CPU E2E 5 outputs identical | exact | none | `.github/scripts/run-cpu-e2e-validation.sh:868-880` | 7dac8bcd, 2026-09-18, maobaolong, #5091 | Cache reset / cross-instance hit do not change output | MP `cpu_e2e_validation` (CPU-only, opt-125m) |
| A15 | Restart recovery writes ratio | round2 >= **80%** of round1 L1 writes | none (hardcoded) | `W/common/restart-recovery.sh:294` | 730e8f99, 2026-05-07, Yihua Cheng, #3208 | vLLM re-registers after LMCache restart | MP `restart_recovery`, XPU |
| A16 | Functional exact checks (lazy offload chunk counts, HTTP codes, cache_stats) | exact | none | `W/vllm/lazy-offload.sh:196-206`, `W/common/http-api.sh:85`, `W/vllm/cache-stats.sh` | not blamed | Feature behavior | MP `lazy_offload`, `http_api`, `cache_stats` |

### 2.2 Performance

| # | Criterion | Default (effective) | Overrides | File:line | Blame | Protects | Pipeline / step |
|---|---|---|---|---|---|---|---|
| P1 | long_doc_qa TTFT vs live baseline | **-60%** (LMCache must be ≥60% faster) | SGLang: **0** (`sglang.sh:57`) | `W/common/long-doc-qa.sh:31`, check `:226-229` | 61aa2025, 2026-05-27, Yihua Cheng, #3405 | Cache hit really saves prefill | MP `long_doc_qa` (2 GPU, vLLM+SGLang); XPU `long_doc_qa` (Qwen3-8B) |
| P2 | long_doc_qa query round time vs live baseline | **-15%** | SGLang: **+20%** (`sglang.sh:58`) | `W/common/long-doc-qa.sh:32` | 61aa2025, #3405 | End-to-end gain | same as P1 |
| P3 | vllm_bench throughput slowdown | **5%** | AMD: **10%** (`.buildkite/scripts/amd-vllm-bench.sh:133`) | `W/vllm/vllm-bench.sh:27`, check `:170-189` | 1a430626, 2026-08-21, maobaolong, #4641 (moved; first value older → UNKNOWN) | LMCache overhead on no-reuse traffic | MP `vllm_bench` (2 GPU, zmq+grpc), nightly canary, AMD, XPU |
| P4 | vllm_bench "too fast" sanity | FAIL if LMCache > **10%** faster | none (hardcoded `local`) | `W/vllm/vllm-bench.sh:195`, fail at `:216` | 521c23b7 boundary → UNKNOWN | Benchmark setup is symmetric | same as P3 |
| P5 | vllm_bench input tokens | ±**1%** of expected | none (hardcoded) | `W/vllm/vllm-bench.sh:136-148` | 9cb6322d, 2026-04-14, Samuel Shen, #3030 | Both servers got the same load | same as P3 |
| P6 | vllm_bench completed count | == `NUM_PROMPTS` (50) | `NUM_PROMPTS` env | `W/vllm/vllm-bench.sh:150-162` | not blamed | No dropped requests | same as P3 |
| P7 | vllm_bench warm retrieve | retrieve log lines grow | none | `W/vllm/vllm-bench.sh:389-396` | not blamed | Real cache hit | same as P3 |
| P8 | L2 query speedup | ≥ **1.3x** | env `MIN_L2_SPEEDUP` | `W/common/long-doc-qa-l2.sh:43` **and** `W/common/long-doc-qa-l2-verify.sh:28` | 61aa2025, #3405; verify copy 1956cbec, 2026-10-14, Yang Bai, #5413 | L2 tier gives gain | MP `long_doc_qa_l2` (vLLM; SGLang blacklisted), XPU |
| P9 | L2 TTFT speedup | ≥ **1.5x** | env `MIN_L2_TTFT_SPEEDUP` | `long-doc-qa-l2.sh:44`, `long-doc-qa-l2-verify.sh:29` | same as P8 | same | same |
| P10 | L2 warmup overhead | ≤ **1.2x** | env `MAX_WARMUP_OVERHEAD` | `long-doc-qa-l2.sh:45`, `long-doc-qa-l2-verify.sh:30` | same as P8 | Store path not too slow | same |
| P11 | Rolling worst baseline (comprehensive) | actual ≤ max(last baselines) × T; T = 1.2 + 0.1×(5−N), N = baseline file count | none | `.buildkite/k3_tests/comprehensive/scripts/run-single-config.sh:328-421` (formula `:388-391`) | 521c23b7 boundary → UNKNOWN | Perf regression vs recent nightly | `k3-comprehensive-test` PR builds (10+ configs) |
| P12 | Baseline window | **5 days** (prune) | none | `comprehensive/scripts/upload-baselines.sh:14,82-84` | 521c23b7 boundary → UNKNOWN | Baseline stays fresh | nightly `NEED_UPLOAD=true` |
| P13 | Which metric is checked | per config `checking-fields` | per config YAML | `run-single-config.sh:246-257`; configs `.buildkite/configs/*.yaml` (e.g. `local_cpu.yaml:22-23`, `p2p.yaml:68-69`) | 521c23b7 boundary → UNKNOWN | — | comprehensive |
| P14 | Memory leak (comprehensive) | pinned objs == 0; hot/active counts consistent | skipped for p2p, multi_device, layerwise | `run-single-config.sh:440-527` | not blamed | No leaked memory objects | comprehensive |

### 2.3 Dead code (in repo, pipeline archived)

| Item | File:line | Note |
|---|---|---|
| `MAX_SLOWDOWN_PERCENT=5` copy | `.buildkite/scripts/multiprocessing-test/run-vllm-bench.sh:25` | pipeline `deprecated-multiprocessing-test` archived 2026-09-09 |
| Absolute `MAX_LMCACHE_TTFT=0.22`, `MAX_LMCACHE_QUERY_ROUND_TIME=0.50` (soft-fail) | `.buildkite/scripts/multiprocessing-test/run-long-doc-qa.sh:30-31,333` | same; do not copy into the new config |

## 3. Conflicts and duplicates

| ID | Severity | What | Effective at runtime | Evidence |
|---|---|---|---|---|
| **C1** | High | `lm_eval_preemption`: pipeline comment says "drift < 0.01"; script default is 0.05 | **0.05**. The step env sets no `SCORE_TOLERANCE` (`MP/pipeline.yml:308-316`). `vllm.sh` has no `engine_configure_workload`. SGLang does not run this test (blacklisted `sglang.sh:16-21`). `run-single-test.sh:44-46` only sets the verify mode. Both the comment and the 0.05 came in the **same PR #4033** (ea44ea7d) — inconsistent since day one | `MP/pipeline.yml:290`, `W/common/lm-eval.sh:19` |
| **C2** | High | One env name `SCORE_TOLERANCE`, four defaults: 0.05 (lm-eval.sh), 0.01 (SGLang lm_eval), 0 (hma-lm-eval.sh), 0.05 (qwen3_5 override) | depends on test + engine | `lm-eval.sh:19`, `sglang.sh:69`, `hma-lm-eval.sh:41`, `run-single-test.sh:100` |
| C3 | Medium | `hma-lm-eval.sh:37-40` says "raise LIMIT ... rather than loosening this" (0 = exact). `run-single-test.sh:96-101` loosens to 0.05 for qwen3_5 (GDN not bit-exact) | 0.05 on XPU `lm_eval_gdn` | intent conflict, not a bug |
| C4 | Medium | Same step name `lm_eval` = different criteria per engine: vLLM = exact samples (A3, no SCORE_MIN); SGLang = drift 0.01 + SCORE_MIN 0.80 | per engine | `run.sh:26`, `sglang.sh:63-69` |
| C5 | Medium | long_doc_qa: vLLM −60%/−15% vs SGLang 0%/+20%. XPU uses vLLM defaults with Qwen3-8B, 10 docs; the comment says the values were calibrated on "recent CI runs" (Qwen3-14B, CUDA) | per engine; XPU = CUDA values | `long-doc-qa.sh:28-32`, `sglang.sh:57-58`, `xpu/multiprocess/pipeline.yml:338-350`. XPU pass rate: **UNKNOWN** — check `xpu-mp-test` builds via Buildkite API |
| C6 | Medium | vllm_bench slowdown 5% (CUDA) vs 10% (AMD). Hidden hardcoded checks: max speedup 10%, token ±1% (not overridable) | 5 / 10 | `vllm-bench.sh:27,136,195`, `amd-vllm-bench.sh:133` |
| C7 | Medium | Duplicate L2 thresholds in two files (same values today; can drift) | 1.3 / 1.5 / 1.2 | `long-doc-qa-l2.sh:43-45`, `long-doc-qa-l2-verify.sh:28-30` (`l2.sh:234` exports, so l2.sh wins) |
| C8 | Medium | SCORE_MIN default defined twice (`run.sh:27` and fallback in `lm-eval.sh:20`) | 0.80 | duplicate, same value |
| **C9** | High | Comprehensive TTFT gate never runs: code looks for `warmup_ttft_per_prompt` in `checking-fields` but the metric it checks is `query_ttft_per_prompt`; no config lists either | TTFT **not gated** in comprehensive | `run-single-config.sh:254-257,396`; configs only list `query_round_time_per_prompt` / `warmup_round_time_per_prompt` |
| C10 | Low | `expected-latency-gain: true` in a config is stripped and never checked | no effect | `.buildkite/configs/local_cpu_with_v3.yaml:4`, `run-single-config.sh:240-242` |
| C11 | Medium | "5-day worst" is really "all files on `benchmarks-main` for this feature" (pruned to 5 days by nightly). Undated legacy file also matches and counts toward N. **No baseline → PASS silently** | relaxed when nightly is broken | `run-single-config.sh:341,345-351`, `upload-baselines.sh:14` |
| C12 | Medium | "Byte-identical" is really "identical in 1 of N attempts": ShareGPT diff retried 3× in-script (known bimodal 0 or ~50 diffs); MP byte-identical steps also have `flaky-retry` (2 retries) | pass if any attempt passes | `correctness/run.sh:19-36`, `MP/pipeline.yml:10-16,110,235,268` |
| C13 | Low | Dead copies of thresholds in archived legacy pipeline (section 2.3) | not run | — |

## 4. Issue #4861 summary

Title: "Discussion: How should LMCache organize CI across platforms?" — OPEN, labels `Testing, discussion, ci/cd, hardware`, opened 2026-09-01 by VincyZhang. 6 comments, **last activity 2026-09-04** (2 months quiet).

| Who | Role | What they said |
|---|---|---|
| VincyZhang (author) | collaborator | Proposes `.buildkite/profiles/` with `models/`, `workloads/`, `capabilities/`, `executions/`, `schema.json`, plus `common_scripts/resolve-profile.py` and `validate-profiles.py`. **Acceptance criteria live in the `executions/` variant**, because "these values vary by machine class". Example: `variants[].acceptance.correctness.require_zero_errors: true`, with `tier: pr`. Profiles "select validated configurations; they do not generate Buildkite YAML". |
| VincyZhang | — | Proposes a **result contract** JSON: `capability, workload, commit, status, cache_hit_validation, baseline_comparison, duration_seconds` — same shape for K8s, Docker, bare metal. |
| maobaolong | collaborator | Likes the tier table (PR = fast smoke; full/pre-merge = multi-device correctness; nightly = larger matrix; release = wheel validation). Wants to discuss **how to define "fast"** and **when a pipeline becomes `required`**. Suggested the Chinese community meeting. |
| VincyZhang | — | Partly done in #4177 (path filtering, merged 2026-09-18) and #4849 (shared device-parameterized MP runner, merged 2026-09-05). Plan: XPU first; step 5 = profile schema + resolution. |
| rebel-jinhwan (RBLN) | contributor | Wants vendor-controlled runs (approval before running), label-gated (`rbln`), only pass/fail back. Likes the result contract. |
| ApostaC (Yihua Cheng) | **Committer** (`MAINTAINERS.md:5`) | Wants PR gates so platform PyPI package builds do not break. (He also authored threshold PR #3405.) |
| liyuanz-luna | contributor | Jenkins POC (poll/webhook, commit status + PR comment). |

Not said (UNKNOWN): no maintainer has commented on acceptance **values**, on a separate acceptance file, or approved the `.buildkite/profiles/` location. `.buildkite/profiles/` does **not exist** in the repo yet. Only one cross-referenced item (#5422, RBLN, closed). To find out: ask in #4861 or the community meeting.

## 5. Recommendation — location and shape

| Question | Recommendation | Why |
|---|---|---|
| Location | `.buildkite/profiles/acceptance.yaml` (criteria definitions + defaults) | Matches #4861 layout. Do **not** use `.buildkite/k3_tests/acceptance.yaml` (P10 default) — #4861 wants profiles shared by k3 / docker / baremetal |
| Per-machine values | Later: `executions/<model>/<capability>.yaml` → `variants[].acceptance: {<criterion_id>: <override>}` | #4861 says acceptance varies by machine class (C5, C6 prove it) |
| Shape | `criteria:` keyed by stable id; each has `kind`, `default`, `overrides` (by `engine`, `test`, `capability`), `source` (file:line), `valid_with_dummy_weights` | One id per check removes C2 (one env name, many meanings) |
| Env vars | Keep: env var > config. First PR = zero behavior change | Same as WS-D plan |
| Result format | Each check writes one JSON verdict compatible with #4861 result contract, plus `criterion`, `value`, `threshold`, `pass` | Lets maintainers compare light vs heavy tests (rollout step 2) |
| First fixes to propose (separate small PRs) | (1) C1: fix pipeline comment to "drift <= 0.05" or set `SCORE_TOLERANCE: "0.01"` in the step env — maintainer decides; (2) C9: fix `warmup_ttft_per_prompt` key; (3) C11: make "no baseline" a visible soft-fail; (4) C7: keep thresholds in one file | Each is 1–3 lines |

### When relaxation is allowed vs full testing mandatory (inputs for the config)

| Rule | Basis |
|---|---|
| Dummy weights OK only for exact/byte-identical KV round-trip checks (A1, A2, A9, A14, P5–P7). Never for score checks (A4, A5, A8) or perf (P1–P11) | Score needs real weights; perf thresholds calibrated on real model |
| Stored rolling baseline may replace live baseline for perf on PR tier (P1–P3) only if "no baseline" fails visibly (fix C11 first) | C11 |
| Thresholds may differ by engine/capability only via explicit `overrides` with a source + reason | C2, C5, C6 |
| Full (heavy) run mandatory: `force-ci` label, deps/CI paths, KV-layout code, engine pin change (canary), release | Existing `force-ci` + canary; WS-C rule |
| Retries: byte-identical checks should report "passed on attempt k" in the verdict, so "1 of 3" is visible | C12 |
