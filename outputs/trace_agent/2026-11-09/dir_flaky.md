<!-- trace_agent_dirs · 2026-11-09T20:51:16+07:00 · default · cost $1.1548479 · 183s -->
# Trace Agent — direction flaky

I looked at the top 3 workloads. All three fail the same way: the test checks a speed ratio and the margin is too thin. Each run takes one measurement and compares it to a fixed pass line. A normal slow run lands just under that line, and the retry lands just over it. Separately, exit 128 is a git checkout error (an infrastructure problem), not a test failure.

I did not look at dsv4_flash_tp or kimi_linear_tp.

## 1. long_doc_qa (74 flaky runs, 46 GPU-h)

The check is that LMCache's time to first token (TTFT) must be at least 60% faster than plain vLLM.

| Build / job | Attempt | LMCache TTFT | Baseline TTFT | Gain | Result |
|---|---|---|---|---|---|
| 6374 `01a1a659-9b88…` | 1 | 0.5959s | 1.3916s | 57.2% | FAIL |
| 6374 `01a1a666-c169…` | 2 | 0.6007s | 1.3937s | 56.9% | FAIL |
| 6374 `01a1a684-6dec…` | 3 | 0.3509s | 1.2886s | 72.8% | PASS |
| 6364 `01a1a5b3-3b65…` | 1 | 0.5946s | 1.3178s | 54.9% | FAIL |

- **The baseline is steady, but LMCache's TTFT jumps between two values.** It is either about 0.35s or about 0.60s, with nothing in between. Plain noise would spread the times out, so something on the LMCache side has a slow mode.
- **The margin has shrunk.** The comment in `.buildkite/k3_tests/multiprocess/scripts/workloads/common/long-doc-qa.sh:29` says recent runs showed a 77–84% gain. Now even the passing run only gets 72.8%.
- The round-time check always passes (30–32%, it only needs 15%).
- **Class: timing.** I could not find what causes the 0.60s mode. A search for cache-hit lines found nothing in either the failed or the passing log.

## 2. long_doc_qa_l2 (95 flaky runs, 67 GPU-h, the biggest cost)

The pass lines are set in `.buildkite/k3_tests/multiprocess/scripts/workloads/common/long-doc-qa-l2.sh:43-45`, and the check is in `long-doc-qa-l2-verify.sh:122-126`.

- 6374 job `01a1a659-9b89…`: `[FAIL] L2 TTFT speedup: 1.27x (need >= 1.5x)`. The other three checks (metrics_snapshot, data_flow, observability) passed.
- 6347 job `01a1a410-cdcc…`: `[FAIL] L2 TTFT speedup: 1.49x (need >= 1.5x)`. Query speedup was 1.43x (pass) and warmup overhead 1.01x (pass).
- The comment at `long-doc-qa-l2.sh:40` says recent runs showed 1.77–2.02x TTFT speedup. The margin has drifted the same way as in long_doc_qa.
- **Class: timing.** Only the TTFT check fails, and the data-flow checks pass, so data is not being lost. It is probably the same slow mode as long_doc_qa, but I have not confirmed that.

## 3. vllm_bench (65 flaky runs, 22.5 GPU-h)

The check is that LMCache throughput may be at most 5% lower than plain vLLM (`.buildkite/k3_tests/multiprocess/scripts/workloads/vllm/vllm-bench.sh:27`, printed at `:186-188`).

- 6366 job `01a1a5c4-8194…`: `Throughput: LMCache is 6.42% slower (max allowed: 5%) FAIL`
- 6378 job `01a1a702-dd0e…`: `Request throughput (req/s): 1.03` for plain vLLM and `0.94` for LMCache, giving `LMCache is 8.90% slower (max allowed: 5%) FAIL`
- **Why it flakes:**
  - It is one run of 50 prompts at about 1 req/s.
  - The log shows `num_warmups=0`, so the first requests run cold.
  - The prompts are random with no reuse, so LMCache only adds cost here and never gets a cache benefit.
  - The seed is `$(date +%s)` (`vllm-bench.sh:30`), so the data changes every run.
  - A 5% limit is inside the normal run-to-run spread.
- **Class: test-bug.**

## Exit 128 (an infrastructure issue in several workloads)

In 6366, both retries of vllm_bench (`01a1a5dc-4eae…` and `01a1a5ee-3e2e…`) failed with `git@github.com: Permission denied (publickey)` and then `Checkout failed! … exit status 128 (Attempt 3/3)`. The automatic retries spent GPU time without the test ever running. The SSH key or deploy key on some agents needs checking. Retrying will not fix this.

## Proposed fixes

1. **vllm_bench:**
   - Add `--num-warmups 5`.
   - Run each side 3 times, alternating plain and LMCache, and compare the medians.
   - Raise `MAX_SLOWDOWN_PERCENT` to 10, or make the check use the measured spread (for example, plain-vLLM median minus 2σ).
   - Proof: 30 runs in a row on dev with no first-try failure.
2. **long_doc_qa and long_doc_qa_l2:** Don't just lower the pass line, because that could hide a real slowdown.
   - First, download the uploaded `diagnostics.txt` and `lmcache.log` from a failed and a passing attempt and compare them. Look for cache hits, load time, and the node.
   - Then gate on the median of several query rounds, not one number.
   - Update the threshold comments to match what CI shows today.
3. **Exit 128:** Fix the checkout credentials on the agents. Exit codes 128 and 255 should also be excluded from automatic GPU retries, since the test never ran.

Commands you can run (read-only):
```bash
bk artifacts download --build 6374 --pipeline lmcache/k3-multiprocess-test "ci_results_*/long_doc_qa/lmcache/diagnostics.txt"
bk job view 01a1a659-9b88-4de8-a0f5-91a3dbd4f6cb   # check the node for the failed attempt
bk job view 01a1a684-6dec-460b-b48b-a912fbdb80f9   # check the node for the passing attempt
```

```json
{"items": [
  {"workload": "long_doc_qa_l2",
   "class": "timing",
   "root_cause": {"en": "The L2 TTFT speedup check (>= 1.5x) fails on a single noisy measurement; observed 1.27x and 1.49x while all data-flow checks pass, and the margin has drifted from the documented 1.77-2.02x.", "vi": "Kiểm tra tăng tốc TTFT của L2 (>= 1.5x) thất bại do chỉ đo một lần và bị nhiễu; đo được 1.27x và 1.49x trong khi mọi kiểm tra luồng dữ liệu đều đạt, và biên độ đã giảm so với mức 1.77-2.02x ghi trong comment."},
   "fix": {"en": "Gate on the median of several query rounds, and compare the diagnostics of failed and passing runs to find why TTFT regressed before re-tuning the 1.5x threshold.", "vi": "Dùng trung vị của nhiều vòng truy vấn, và so sánh diagnostics của lần lỗi và lần đạt để tìm lý do TTFT chậm đi trước khi chỉnh lại ngưỡng 1.5x."},
   "evidence": ["build 6374 job 01a1a659-9b89: '[FAIL] L2 TTFT speedup: 1.27x (need >= 1.5x)'", "build 6347 job 01a1a410-cdcc: '[FAIL] L2 TTFT speedup: 1.49x (need >= 1.5x)'", "build 6347: '[PASS] L2 query speedup: 1.43x', '[PASS] Warmup overhead: 1.01x'", "long-doc-qa-l2.sh:40 comment: '~1.77-2.02x TTFT speedup'"],
   "failing_tests": [".buildkite/k3_tests/multiprocess/scripts/workloads/common/long-doc-qa-l2-verify.sh:122-126"],
   "confidence": "medium"},
  {"workload": "long_doc_qa",
   "class": "timing",
   "root_cause": {"en": "LMCache query TTFT switches between ~0.35s and ~0.60s while the baseline stays at ~1.3s, so the single-shot >= 60% TTFT gate fails whenever the slow mode appears.", "vi": "TTFT truy vấn của LMCache lúc thì ~0.35s lúc thì ~0.60s trong khi baseline ổn định ~1.3s, nên kiểm tra TTFT >= 60% chỉ đo một lần sẽ thất bại mỗi khi rơi vào chế độ chậm."},
   "fix": {"en": "Find the cause of the 0.60s mode by comparing diagnostics.txt and lmcache.log from failed and passing runs, then gate on the median over several rounds instead of one number.", "vi": "Tìm nguyên nhân của chế độ 0.60s bằng cách so sánh diagnostics.txt và lmcache.log giữa lần lỗi và lần đạt, sau đó dùng trung vị của nhiều vòng thay vì một số đo."},
   "evidence": ["build 6374 job 01a1a659-9b88: 'query_ttft_per_prompt: 0.5959s vs baseline 1.3916s (57.2% faster, need >= 60% faster) -- FAIL'", "build 6374 job 01a1a666-c169: '0.6007s vs baseline 1.3937s (56.9% faster) -- FAIL'", "build 6374 job 01a1a684-6dec: '0.3509s vs baseline 1.2886s (72.8% faster) -- PASS'", "build 6364 job 01a1a5b3-3b65: '0.5946s vs baseline 1.3178s (54.9% faster) -- FAIL'"],
   "failing_tests": [".buildkite/k3_tests/multiprocess/scripts/workloads/common/long-doc-qa.sh:31"],
   "confidence": "medium"},
  {"workload": "vllm_bench",
   "class": "test-bug",
   "root_cause": {"en": "One 50-prompt run with no warmup, random no-reuse prompts and a time-based seed is compared against a 5% throughput limit that is inside normal run-to-run noise.", "vi": "Chỉ một lần chạy 50 prompt, không warmup, prompt ngẫu nhiên không tái sử dụng, seed theo thời gian, rồi so với giới hạn throughput 5% nằm trong mức nhiễu bình thường."},
   "fix": {"en": "Add warmups, run each side 3 times alternating and compare medians, and raise the limit to about 10% or derive it from the measured spread; prove it with 30 green first tries.", "vi": "Thêm warmup, chạy mỗi bên 3 lần xen kẽ và so trung vị, nâng giới hạn lên khoảng 10% hoặc tính từ độ dao động đo được; chứng minh bằng 30 lần đạt ngay lần đầu."},
   "evidence": ["build 6366 job 01a1a5c4-8194: 'Throughput: LMCache is 6.42% slower (max allowed: 5%) FAIL'", "build 6378 job 01a1a702-dd0e: 'Request throughput (req/s): 1.03' (baseline) vs '0.94' (LMCache), 'LMCache is 8.90% slower (max allowed: 5%) FAIL'", "build 6366 log Namespace: 'num_warmups=0', 'dataset_name=random'", "vllm-bench.sh:27 MAX_SLOWDOWN_PERCENT=5, vllm-bench.sh:30 RANDOM_SEED=$(date +%s)"],
   "failing_tests": [".buildkite/k3_tests/multiprocess/scripts/workloads/vllm/vllm-bench.sh:186-188"],
   "confidence": "high"}],
 "summary": {"en": "The top three flaky workloads are single-sample performance gates whose thresholds sit inside normal variance, plus a long_doc_qa TTFT slow mode that should be explained before re-tuning. Separately, exit 128 is a git publickey checkout failure that wastes automatic GPU retries and needs an infrastructure fix.", "vi": "Ba workload flaky hàng đầu đều là kiểm tra hiệu năng chỉ đo một lần với ngưỡng nằm trong mức dao động bình thường, cộng thêm chế độ TTFT chậm của long_doc_qa cần được giải thích trước khi chỉnh ngưỡng. Riêng exit 128 là lỗi checkout git (publickey) làm tốn GPU cho các lần retry tự động và cần sửa ở hạ tầng."},
 "unverified": ["(chưa xác minh) Cause of the 0.60s LMCache TTFT mode in long_doc_qa; no cache-hit lines were found in the job logs.", "(chưa xác minh) Whether the failed and passing attempts ran on different nodes; agent IDs differ but hostnames were not checked.", "(chưa xác minh) That long_doc_qa_l2 TTFT drift has the same cause as the long_doc_qa slow mode.", "(chưa xác minh) That the exit-128 failures in builds 6370 and 6371 are the same git publickey error seen in build 6366.", "(chưa xác minh) dsv4_flash_tp and kimi_linear_tp were not investigated."]}
```