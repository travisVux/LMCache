# P5 / R4: Baseline engine decisions

Source: `third_party/LMCache` at `fcd50cea` (2026-11-04).
Short names: `MP/` = `.buildkite/k3_tests/multiprocess/`, `S/` = `MP/scripts/`, `W/` = `S/workloads/`.
Buildkite data: pipeline `k3-multiprocess-test`. The run was read-only, with no retries, triggers, or posts.

Files in this folder:
- `extract_baseline_metrics.py`: downloads the sampled logs (kept in memory only) and saves the extracted numbers.
- `raw/metrics.json`: one record per job (235 jobs).
- `stats.py`: computes the statistics. Its output is in `raw/stats.txt`.

Sample: 235 PR jobs from 2026-10-05 to 2026-11-04. For each of the 4 perf sets (vllm_bench/vLLM, long_doc_qa/vLLM, long_doc_qa/SGLang, long_doc_qa_l2/vLLM) I took 30 jobs that passed inside passed builds (39 distinct passed builds) and 30 failed jobs. Both groups are spread evenly over the 30 days. One log download failed.
Only 2 GPU nodes run these jobs: `yotta-ral-pro-6000-237` and `-248` (all RTX PRO 6000, 94 GB).

---

## 0. Short answer

1. Four workloads start a baseline engine: `vllm_bench`, `long_doc_qa`, `long_doc_qa_l2`, `preemption_correctness` (`S/run-single-test.sh:170-177`). No others do. `p2p` sets `VLLM_BASELINE_PORT` to its second LMCache engine (`W/vllm/p2p.sh:50`), so it is not a baseline. `fault_tolerance` turns the baseline off (`W/vllm/fault-tolerance.sh:68,77`).
2. Three of the four use the baseline for **performance**. `preemption_correctness` uses it for **correctness** (ground truth).
3. **The baseline numbers are stable.** CV is 2-5% for vLLM and 3-7% for SGLang. **The flaky failures do not come from the baseline.** They come from the LMCache side on node **248**, which runs in two speed modes. P1 job table, exit 128 removed:

   | Workload | Fail rate on node 237 | Fail rate on node 248 |
   |---|---|---|
   | vllm_bench | 0% | 17% |
   | long_doc_qa (vLLM) | 0% | 35% |
   | long_doc_qa_l2 | 8% | 39% |

4. A stored baseline (perf) and a same-engine replay (correctness) can move all 4 workloads from 2-GPU to 1-GPU pods. Lower bound: **about 43,000 GPU-min per 30 days**, which is about 23% of PR GPU-min.
5. SGLang `long_doc_qa` is **not a flake**. LMCache TTFT got worse starting around 2026-10-27, and retries are hiding it (section 5).

---

## 1. Baseline role per workload

| Workload | Engine(s) | Baseline role | What the baseline is compared on | Evidence |
|---|---|---|---|---|
| vllm_bench | vLLM (zmq, grpc) | **Performance**: LMCache overhead on traffic with no reuse | `total_token_throughput`. FAIL if LMCache is more than 5% slower (`W/vllm/vllm-bench.sh:27,166-190`). Also FAIL if LMCache is more than 10% **faster** (`:195-216`; `failed=1` at `:216`, so this is a real fail, not a warning as P2 says). Token count and completed count are checked on both servers (`:136-164`) | Baseline runs first, then LMCache, same seed (`:450-461`). A single-instance mode already exists (`:445-478`, `verify_single_instance_result` `:225-248`) |
| long_doc_qa | vLLM, SGLang | **Performance**: the cache-hit gain | `query_ttft_per_prompt`: vLLM must be ≥60% faster, SGLang must be ≤0% slower. `query_round_time_per_prompt`: vLLM must be ≥15% faster, SGLang must be ≤20% slower (`W/common/long-doc-qa.sh:31-32,183-241`; `S/engines/sglang.sh:57-58`) | Baseline run `:248`, LMCache run `:254` |
| long_doc_qa_l2 | vLLM only (SGLang is skipped, `S/engines/sglang.sh:16-21`) | **Performance**: the L2 tier gain | L2 query speedup ≥1.3x, TTFT speedup ≥1.5x, warmup overhead ≤1.2x (`W/common/long-doc-qa-l2.sh:43-45`; `W/common/long-doc-qa-l2-verify.sh:113-138`) | `long-doc-qa-l2.sh:201-215`. "Reuse step-5 baseline" **never happened** in 59 sampled jobs, because the steps run in separate pods |
| preemption_correctness | vLLM, async 0/1 | **Correctness**: plain vLLM at concurrency 3 with no preemption is the ground truth | LMCache at concurrency 40 must give the same answer count, the same request-id set, and 0 different answers (`W/vllm/preemption-correctness.sh:154-177`). The ref run must not preempt (`:128-131`) | `rung "ref ..." "$VLLM_BASELINE_PORT"` at `:180`; D rung at `:191` |

How the two engines differ (vLLM): the baseline runs `engine_launch baseline` on `GPU_FOR_BASELINE=1` (`S/launch-processes.sh:104-110`, `S/engines/vllm.sh:32`). It drops only `--kv-transfer-config`, the mamba args, and `--max-num-batched-tokens` (`S/engines/vllm.sh:220-231`). vLLM's own prefix cache (APC) stays on in **both** engines. The perf checks therefore compare **GPU 0 against GPU 1**, not the same GPU.

---

## 2. Perf workloads: baseline and LMCache numbers (Buildkite logs)

### 2.1 Spread of the numbers

All values come from the job logs. "pass" = 30 passed jobs in passed builds. "fail" = 30 failed jobs (fewer have numbers when the failure was not a threshold miss).

| Workload / metric | Side | pass: mean | pass: sd | pass: **CV** | fail: mean | fail: CV |
|---|---|---|---|---|---|---|
| vllm_bench throughput (tok/s) | baseline | 9534 | 488 | **5.1%** | 10049 | 4.6% |
| | LMCache | 9590 | 488 | 5.1% | 9517 | 4.9% |
| long_doc_qa vLLM query TTFT (s) | baseline | 1.370 | 0.065 | **4.8%** | 1.349 | 3.5% |
| | LMCache | 0.386 | 0.038 | 9.8% | 0.633 | 4.1% |
| long_doc_qa vLLM query round (s) | baseline | 2.672 | 0.077 | **2.9%** | 2.663 | 2.1% |
| | LMCache | 1.764 | 0.050 | 2.8% | 1.852 | 2.5% |
| long_doc_qa SGLang query TTFT (s) | baseline | 1.382 | 0.103 | **7.4%** | 1.351 | 6.1% |
| | LMCache | 0.380 | 0.280 | **73.6%** | 1.803 | 16.5% |
| long_doc_qa SGLang query round (s) | baseline | 1.666 | 0.057 | 3.4% | 1.665 | 2.0% |
| long_doc_qa_l2 query TTFT (s) | baseline | 1.396 | 0.048 | **3.4%** | 1.353 | 4.5% |
| | LMCache-L2 | 0.841 | 0.054 | 6.4% | 0.986 | 7.6% |
| long_doc_qa_l2 query round (s) | baseline | 2.696 | 0.062 | **2.3%** | 2.653 | 2.5% |
| | LMCache-L2 | 1.882 | 0.037 | 2.0% | 1.933 | 1.8% |

The baseline is the same on passed and failed runs (means within about 3%). **Failures are caused by the LMCache side**, except in vllm_bench (section 2.3).

### 2.2 Per node: where the noise comes from

All 235 jobs, pass and fail together:

| Metric | Node 237 | Node 248 |
|---|---|---|
| vllm_bench baseline throughput | 9188, **CV 0.5%** | 10050, CV 4.2% (two groups: about 9.4k and about 10.3k) |
| vllm_bench LMCache throughput | 9224, CV 0.8% | 9714, CV 5.2% (same two groups) |
| long_doc_qa vLLM baseline TTFT | 1.420, CV 2.1% | 1.338, CV 3.7% |
| long_doc_qa vLLM LMCache TTFT | 0.379, CV 5.8% | 0.547, **CV 22.3%** (two groups: 0.34-0.49 and 0.59-0.67) |
| long_doc_qa_l2 baseline TTFT | 1.416, CV 1.5% | 1.353, CV 4.5% |
| long_doc_qa_l2 LMCache TTFT | 0.912, CV 9.6% | 0.913, CV 11.3% |

Node 248 has two speed groups. In vllm_bench both servers sit in one group or the other. This looks like **two kinds of GPU (or two power/clock settings) on 248**, and the pod gets a random pair. This is a guess, so the cause is **UNKNOWN**. How to find out: print `nvidia-smi --query-gpu=index,uuid,name,power.limit,clocks.max.sm --format=csv` and `nvidia-smi topo -m` in `S/run-single-test.sh` before launch, then join the output with the throughput. The LMCache TTFT mode on 248 may also be a NUMA or PCIe effect on host-to-GPU copy. Same check.

### 2.3 How close failures sit to the threshold

| Workload | Threshold | Passed values | Failed values | Reading |
|---|---|---|---|---|
| vllm_bench | slowdown ≤5% and speedup ≤10% | slowdown −9.3% to +2.1%; 28 of 30 between −2.3% and +2.1% | slowdown **+5.6% to +11.6%** (19 of 21 between +7.1% and +9.4%), one +21.3%; "too fast" fails at **−10.2% to −12.1%** (5 jobs) | Failures are **not near-misses**. They sit on the about 9% gap between the two node-248 GPU groups: LMCache on a slow GPU with the baseline on a fast one, or the other way round. A retry (limit 3, `MP/pipeline.yml:19-24`) just gets a new GPU pair |
| long_doc_qa vLLM | TTFT ≥60% faster | 62.6% to 76.4% faster | **47.8% to 57.0% faster** (all on node 248) | The failures form a separate group about 5-12 points below the line, all caused by LMCache TTFT 0.59-0.67 s. The round-time check (≥15%) never fails: worst pass 26.8%, worst fail 24.6% |
| long_doc_qa_l2 | TTFT speedup ≥1.5x | **1.52** to 1.87 | 1.18 to 1.49 (most 1.29-1.45) | The pass group starts just above the line, so 1.5 sits at the bottom edge of the normal spread. Query speedup ≥1.3x: passes 1.31-1.55, fails 1.29 (2 jobs). The script comment says 1.77-2.02x was seen when it was set (`long-doc-qa-l2.sh:40-42`); the spread has moved down since then |
| long_doc_qa SGLang | TTFT ≤0% slower | 89% to 23% faster | **3% to 83% slower** | A regression, not noise (section 5) |

### 2.4 Can a stored baseline replace the live one?

Rule used: baseline CV < 10% **and** 3 × sd < the threshold margin.

| Workload | Baseline CV | 3 × sd vs margin | Stored baseline OK? |
|---|---|---|---|
| long_doc_qa vLLM | 2.5-4.3% | TTFT: the line is LMCache ≤ 0.40 × baseline. A 3-sd baseline move (±13%) shifts the line about 0.05 s; passes sit at 0.34-0.49 s | **Yes** |
| long_doc_qa SGLang | 2.9-7.0% | TTFT line is LMCache ≤ baseline (1.37 ± 0.29 at 3 sd); passes are far below it | **Yes**, but fix the regression first |
| long_doc_qa_l2 | 2.3-4.3% | TTFT 3 sd ≈ ±13% against the 1.5x line, which is already marginal | **Yes**, together with a threshold fix (section 6) |
| vllm_bench | 5.5% across nodes; 0.5% on node 237 | 3 sd = 16% against a 5% margin across nodes. Per GPU on 237: 1.5% | **Only if keyed per GPU (UUID).** A per-GPU stored baseline is actually **better** than today's GPU0-vs-GPU1 comparison |

**Another way for long_doc_qa and long_doc_qa_l2: in-run self-baseline.** The warmup round on the LMCache engine is a cold run. Measured: `lmc_warmup_round / baseline_warmup_round` = **1.01, CV 2.8%** (vLLM). The ratio `lmc_query_round / lmc_warmup_round` = **0.636, CV 1.8%** on passes (0.9% even on vLLM fails). A check like "query round ≤ 0.85 × own warmup round" needs **no baseline at all**. For TTFT, `benchmarks/long_doc_qa/long_doc_qa.py:597-601` would also need to output a warmup TTFT. This is a small change, but that number is **UNKNOWN** today: it is not in the JSON. The baseline query TTFT (1.36 s) is **not** a cold number, because the baseline has vLLM APC hits, so the threshold must be calibrated again from a few runs.

---

## 3. Correctness: can `preemption_correctness` use a same-engine replay?

Proposal: run the `ref` rung on the **LMCache** engine at concurrency 3. This is the same as the existing ladder rung "B" (`W/vllm/preemption-correctness.sh:184`). Then clear both caches: `POST /cache/clear` with `force=true` (`lmcache/v1/multiprocess/http_apis/cache_api.py:160-188`), and vLLM `POST /reset_prefix_cache`, which is available because `VLLM_SERVER_DEV_MODE=1` (`S/engines/vllm.sh:239,293`). Then run D at concurrency 40. Use a 1-GPU pod.

| Concern | Holds? | Detail |
|---|---|---|
| Determinism | **Better** | Today ref runs on GPU 1 and D on GPU 0. Both are RTX PRO 6000, but node 248 shows the GPUs are not identical (section 2.2). On one GPU, the comparison only depends on the batch-invariance settings that are already pinned: `VLLM_BATCH_INVARIANT=1` (`S/engines/vllm.sh:19,27,240`), `ENFORCE_EAGER=1`, FLASH_ATTN (`MP/pipeline.yml:343-345`) |
| Batch invariance (c=3 vs c=40) | Same as today | The current test already relies on it (ref at c=3 vs D at c=40). Nothing changes |
| Preemption timing in ref | Small risk | `NUM_GPU_BLOCKS_OVERRIDE=1024` applies in both modes (`S/engines/vllm.sh:143-146`), so c=3 still fits. With `async=1` and the connector, vLLM frees blocks at the end of the step (`S/engines/vllm.sh:152-155`), so ref on the LMCache engine *could* preempt. The script then FAILs loudly (`:128-131`), it does not pass silently. Whether rung B ever preempted with async=1: **UNKNOWN**. Find out with one manual build using `PREEMPT_FULL_LADDER=1` |
| Cold cache for D (`:188-190`) | Needs care | ref stores KV. If the clear is incomplete (in-flight stores, an L2 tier, or `force` not set), D gets prefix hits on first admission. Then D does less prefill, may preempt less (the `>0` check at `:123` could fail), and a resume may load ref's KV instead of its own. Fix: clear with `force=true`, wait, then assert that LMCache L1 usage is 0 before D |
| **What is lost** | **Real loss** | The oracle is no longer "plain vLLM". A bug where *storing KV changes generation* (ladder case "A passes, B fails", `:34`) would be in both ref and D, so it would be **hidden**. Other workloads do not cover this: lm_eval (vLLM) and the L1 round-trip checks also compare LMCache against LMCache (P2 coverage map) |

**Stored golden answers** (another option, not chosen): the key would need model, exact vLLM build, dataset slice hash, `MAX_MODEL_LEN`, block override, eager, attention backend, batch invariance, async flag, and GPU SKU. vLLM changed more than 15 times in 30 days (sample: 0.30.1rc1.dev647 → 0.33.0). Every change makes the golden file stale, and any GPU difference (node 248) can break an exact match. The risk is too high.

**Decision:** PR tier uses the same-engine replay (1 GPU). Keep the plain-vLLM baseline run once a day (nightly, or the `dev` branch) with `PREEMPT_FULL_LADDER=1`. That restores the "storing changes generation" check at low cost.

---

## 4. Decision table

GPU-min = PR GPU-min over 30 days (P1 `outputs/P1/jobs_all_30d.csv`, split by engine). "Saved" is a **lower bound**: going from 2 GPUs to 1 at the same wall time gives 50%. The real saving is higher, because the baseline benchmark phase also goes away for perf workloads. How long that phase takes is **UNKNOWN**. Measure it from the log timestamps between `=== Benchmark: Baseline` and `=== Benchmark: ... with LMCache` (P1 `sample_logs.py` pattern).

| Workload | Baseline role | Decision | PR GPU-min / 30 d now | GPU-min saved / 30 d (≥) | Risk | Evidence |
|---|---|---|---|---|---|---|
| long_doc_qa (vLLM) | Perf | **Stored** rolling baseline (later: in-run self-baseline) | 11,620 | **5,810** | Low. Baseline CV 2.5-4.8%. Failures are LMCache-side and unchanged by this | §2.1-2.4; `W/common/long-doc-qa.sh:248-254` |
| long_doc_qa (SGLang) | Perf | **Stored**, after the regression in §5 is fixed | 10,213 | **5,107** | Medium. Baseline TTFT CV 7.4%. The current failures are a real regression | §2.1, §5 |
| long_doc_qa_l2 (vLLM) | Perf | **Stored** + change the TTFT threshold (§6) | 14,274 (SGLang 71, a no-op) | **7,137** | Low-Med. Baseline CV 2.3-4.5%. The 1.5x line is marginal | §2.3; `long-doc-qa-l2-verify.sh:113-138` |
| vllm_bench (vLLM) | Perf (overhead) | **Stored, keyed per GPU UUID**. Use the existing single-instance mode (`vllm-bench.sh:445-478`). If per-GPU keys are not possible, **keep** the live baseline and run it on the **same GPU** | 13,281 | **6,640** | Medium. A cross-node key flakes (3 sd = 16% > 5%). Needs the GPU identity logged first | §2.2-2.3 |
| preemption_correctness | Correctness | **Same-engine replay** on PR; keep the plain-vLLM ladder nightly | 37,025 | **18,512** (the rungs already run one after the other, `:180,191`, so wall time stays about the same) | Medium. Loses the "storing changes output" check on PRs (§3) | §3 |
| **Total** | | | 86,413 | **≈43,200** (≈23% of 185,936 PR GPU-min) | | |

Extra saving: perf retries cost 6,723 GPU-min per 30 days (long_doc_qa 2,523 + long_doc_qa_l2 3,146 + vllm_bench 1,055, P1 `cost_by_workload.csv`). Most of them are node-248 failures, and fixing §5/§6 removes most of this.

### 4.1 Stored rolling baseline: design that avoids C9 and C11

| Item | Proposal | Why |
|---|---|---|
| Producer | A daily job on `dev` (not PR) runs the baseline engine **N=5 times** for each key and stores the **median and MAD**, plus n, date, and commit | PRs never write. The median is robust, unlike today's comprehensive **max** (`comprehensive/scripts/run-single-config.sh:356-367`), which makes the gate loose |
| Key (exact match) | workload, engine name + **exact engine version** (e.g. `0.33.0` / commit), model + HF revision, **GPU SKU + GPU UUID** (vllm_bench) or GPU SKU + node (long_doc_qa*), driver/CUDA, a hash of the workload params (doc length, num docs, output len, repeat, inflight, num prompts, input len), a hash of the engine flags (gpu-mem-util, batch-invariant, eager, attention backend, APC on/off, async) | Today the key is only `feat_type` (`run-single-config.sh:339-341`). Two nodes already differ by 4-9% in throughput (§2.2) |
| C9 (wrong field name means the check never runs) | The checked metric names come from **one shared list** used by both the producer and the checker. The checker FAILS if any listed field is missing in the stored file or in the current result. Add a unit test with a fixture | C9: `warmup_ttft_per_prompt` vs `query_ttft_per_prompt` (`run-single-config.sh:254-257,396`) |
| C11 (no baseline means a silent PASS) | No matching key, fewer than 3 samples, older than 7 days (by the `generated_at` field inside the file, not the file name), or a git fetch error → **fall back to the live 2-GPU baseline path** and print `BASELINE_FALLBACK reason=...` in a Buildkite annotation. Never `return 0`. Reject undated or legacy files | C11: `run-single-config.sh:341,345-351` (`|| true` on fetch, `return 0` when nothing is found, the legacy file counts toward N) |
| Version bumps | When the engine pin changes, the first PR builds have no key, so they run the live path (fallback). The next daily job fills the key | No silent window |
| Traceability | Print the key, the file used, n, median, and MAD in the log | The failures in this report were only analysable because the logs print both numbers |

---

## 5. Note: SGLang long_doc_qa is a regression, not a flake

LMCache query TTFT on SGLang was **0.18-0.23 s** up to about 2026-10-24. From about 2026-10-27 it is **0.6-1.0 s on passes and 1.4-2.4 s on fails**. All 17 threshold fails in the sample are from builds 6160-6332 (2026-10-27 to 11-03), on node 237. The baseline did not move (1.24-1.58 s). The cause is **UNKNOWN**. How to find out: compare the SGLang version and LMCache commits between build 6153 (10-26, fast) and 6160 (10-27, slow), using `compare_builds` or the log header. Retries (`flaky-retry`, `MP/pipeline.yml:10-16`) turn this real slowdown into green builds.

---

## 6. Flaky perf thresholds: findings and recommendation

| # | Finding | Evidence |
|---|---|---|
| F1 | Perf failures are **not** baseline noise. Baseline CV is 2-5% (vLLM). | §2.1 |
| F2 | They are concentrated on **node 248**: vllm_bench 17% fail vs 0% on 237; long_doc_qa 35% vs 0%; long_doc_qa_l2 39% vs 8%. | P1 job table; §2.2 |
| F3 | Failed values form a **separate group**, not a tail near the line: vllm_bench +7-9% (the gap between GPU groups); long_doc_qa TTFT 48-57% vs 60%. | §2.3 |
| F4 | The L2 TTFT line (1.5x) is at the **bottom edge** of the passing spread (min pass 1.52x). | §2.3 |
| F5 | Retries hide a real SGLang regression. | §5 |

**Recommendation (in order):**
1. **Log the GPU identity** (`nvidia-smi` name/UUID/power limit/clocks, `topo -m`) in every perf job. Confirm the node-248 hypothesis, then fix the node, or label it and schedule perf jobs only on matching GPUs. This one step should remove most of the 6,723 retry GPU-min.
2. **vllm_bench:** stop comparing GPU 0 against GPU 1. Use the stored per-GPU baseline (§4.1). Until that exists, the 5% gate is smaller than the hardware gap on 248.
3. **long_doc_qa_l2:** move TTFT from a fixed 1.5x to a calibrated line: stored median − 3 × MAD, or about 1.35x for now. Or use the in-run self-baseline ratio, which has CV ≤3%. Also remove the duplicate thresholds (C7).
4. **Retries on perf steps:** keep `-1`/infra retries. For threshold misses, the retry result must be **visible**: annotate "passed on retry N, first value X". Fail when 2 of 3 attempts miss, rather than passing on any 1 of 4. Today a real regression (§5) looks the same as a flake.
5. Open an issue for the SGLang TTFT regression (§5) before switching SGLang long_doc_qa to a stored baseline.

---

## 7. UNKNOWN items and how to find out

| Item | How to find out |
|---|---|
| Why node 248 has two speed groups (GPU SKU, power cap, NUMA?) | Add the `nvidia-smi` / `topo` print (§2.2). Or ask the infra owner what hardware is in `yotta-ral-pro-6000-248` |
| How long the baseline phase takes in perf jobs (upper-bound saving) | Log timestamps between the `=== Benchmark: Baseline` and `... with LMCache` markers (P1 `sample_logs.py` method) |
| Whether ref on the LMCache engine with async=1 preempts | One manual build with `PREEMPT_FULL_LADDER=1` (rung B, `:184`) |
| Warmup TTFT value for the self-baseline | Add `warmup_ttft_per_prompt` to the `long_doc_qa.py` JSON (`:597-601`) and collect about 10 runs |
| Cause of the SGLang TTFT regression | Diff builds 6153 and 6160 (§5) |
