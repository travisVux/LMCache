<!-- trace_agent_dirs · 2026-11-09T21:10:32+07:00 · default · cost $1.3876602999999998 · 234s -->
# Trace Agent — direction gpuload

# GPU cost review: `k3-multiprocess-test`, top 3 changes

**Bottom line:** The biggest saving is not on the list you gave me. In the most expensive workload, `preemption_correctness`, about 62% of each job's time goes to a plain-vLLM "reference" run that doesn't use LMCache at all. It also runs one after the other with the LMCache run, even though the two use separate GPUs. Fixing flaky tests and fast-fail are the next two, at about 188 GPU-h each. Fast-fail is only half done: it exists only as uncommitted changes in your local clone, and it has a likely bug.

## Step 1: How workloads are chosen

- **Whole pipeline on or off, nothing per workload.** The only path rule for multiprocess is `.buildkite/k3_tests/common_scripts/path-filter.sh:139-151`, called from `upload-pipeline.sh:54`. Any change under `lmcache/**` uploads all of `pipeline.yml`.
- **Labels:** `skip expensive ci` and `force-ci` (`helpers.sh:53-75`, `upload-pipeline.sh:39-50`). Builds 6458 and 6459 were skipped by the label.
- **Inside `pipeline.yml`:** the only `if:` conditions are the VERIFY_AND_PIN switches (`pipeline.yml:95,132,249,459`). No workload is chosen by path.
- **No draft-PR check:** `helpers.sh` has no `draft` check.

## Steps 3–4: The levers and where the minutes go

**Where time goes in `preemption_correctness / async=1` (build 6457).** Times come from log timestamps:

| Phase | Time | Source |
|---|---|---|
| Checkout + install vLLM (44 s) + install LMCache from source (75 s) + probes | 2.4 min | "Environment ready" at +145.5 s |
| Start both servers ("vLLM with LMCache is ready! (took 120s)") | 2.35 min | log row 19753 |
| **`ref` rung (plain vLLM, concurrency 3, 99 requests)** | **17.7 min** | rows 19770→19771 |
| `D` rung (LMCache, concurrency 40, 53 preemptions) | 6.0 min | rows 19771→19773 |
| Whole job | 28.6 min on 2 GPUs | |

- **Setup is not the problem.** Only about 17% of the job is setup.
- **The `ref` rung uses no LMCache.** The script says "ref   plain vLLM … no preemption, no LMCache" (`preemption-correctness.sh:6`).
- **The two rungs run in sequence on separate GPUs.** `ref` runs first on port 9000 (`:180`), then `D` on port 8000 (`:191`).
- **This job finished last in 6457.** It ended at 08:27:09 after waiting 17.7 min for a 2-GPU pod.
- **Your table agrees.** It shows 108.58 GPU-min per build, about 54 per job; I measured 57.

**Status of each lever:**

| Lever | Status | Evidence |
|---|---|---|
| **Fast-fail** (LM-1062) | **Partly done, not committed** | See the four points below. |
| **Fix flaky workloads** (LM-762) | Open | 67.1 + 46.0 + 37.9 + 22.5 + 14.4 = 187.9 GPU-h, which matches the table. In 6457, `vllm_bench/grpc` failed with "Verification failed" but "Failed requests: 0". That is the throughput-noise case the comment at `pipeline.yml:17-18` describes. The retry cost 9.0 min of the failed run, 3.4 min waiting again, then a 12.2 min rerun. |
| **Cancel the build when a newer commit arrives** (LM-1115) | Done | 0.9 GPU-h left (from your cache). |
| **Path gating for `preemption_correctness`** | Open, small gain | It tests the MP connector's preemption and resume path. Most PRs in the list are `[MP]` changes that would trigger it anyway. No path→workload map exists. |

Fast-fail details:
- **Uncommitted:** all the changes are in `git diff` and `.buildkite/scripts/fast_fail_cancel.py` is untracked.
- **Wrong trigger, probably:** the MP "Fast Fail" step uses `if: build.state == "failing"` (`pipeline.yml:626`). Buildkite checks step `if:` conditions when the pipeline is uploaded, when the build isn't failing yet. So the step would probably never run **(chưa xác minh)**.
- **Missing workflow:** GHA "Test" has no hook; only lint (`code_quality_checks.yml`) and k3-unit do.
- **Token risk:** `fast_fail_cancel.py:29-38` falls back to reading a Buildkite token from `~\.claude.json.bak-buildkite`. Remove this before committing. I did not open that file.

**Other things I noticed:**
- **Skipped jobs still wait for GPU pods.** In 6457, six sglang jobs were skipped as unsupported and ended in about 5 s. One, `sglang/long_doc_qa_l2`, waited 35 min for a 2-GPU pod first (created 07:40:47, started 08:16:07). Excluding those matrix combinations in the YAML would save almost no GPU-h but would free queue slots.
- **The live pipeline doesn't match your clone.** Build 6457 ran `hma_dsv4_correctness` and no `dsv4_flash_tp` job, but the local `pipeline.yml:103` still has `dsv4_flash_tp`. Some of the 37.9 retry GPU-h for `dsv4_flash_tp` may already be gone **(chưa xác minh)**.

## Step 5: Ranking

**1. Stop re-running the `preemption_correctness` reference on every PR: about 450 GPU-h per 30 days (estimated)**
- **Change:** Store `ref.txt`, keyed by vLLM version + model + dataset hash + env flags + GPU model. Refresh it on the scheduled `dev` build. Run only rung `D` on a 1-GPU pod.
- **Formula:** new job = 2.4 + 2.35 + 6.0 ≈ 10.9 GPU-min, versus 2 × 28.6 = 57.2 today. That saves 81%, and 0.81 × 617.1 = 500 GPU-h. Minus about 57 GPU-h for daily refreshes, roughly 450 net.
- **Easier first step, no coverage change:** run `ref` and `D` at the same time on their two GPUs. That saves 6.0 of 28.6 min per job: 21% × 617.1 = **about 129 GPU-h**.
- **Merge speed:** the job goes from 28.6 to about 11 min. It was the last job to finish in 6457, so a build's duration could drop by up to about 17 min. Fewer 2-GPU slots taken should also shorten queues.
- **Risk:** a stored reference can go stale or be non-deterministic across nodes, which would cause false failures. The reference only covers vLLM, not LMCache, so a vLLM regression would be caught by the nightly build instead of on the PR.

**2. Fix the top flaky workloads: 187.9 GPU-h (measured, from your cache)**
- Retries sit on the critical path of builds that would otherwise pass, so this helps every PR, not just failing ones.

**3. Finish fast-fail: 188.4 GPU-h, or 136.9 if limited to the two required checks (measured, from your cache)**
- **Fixes needed:** the `if:` trigger, the token fallback, and the missing GHA "Test" hook.
- **Merge speed:** it only helps PRs that are already red, by freeing GPUs for others.
- **Risk to test:** the local changes add `cancel_on_build_failing: true` to all steps. If one flaky first attempt marks the build "failing" before its automatic retry, this could cancel sibling jobs **(chưa xác minh)**.

## Commands to verify (read-only)

To check whether the reference answers are deterministic, compare the `ref.txt` files that past builds already uploaded. They are saved by `pipeline.yml:362`, so no rerun is needed:

```bash
for b in 6457 6454 6456; do
  curl -s -H "Authorization: Bearer $BUILDKITE_API_TOKEN" \
    "https://api.buildkite.com/v2/organizations/lmcache/pipelines/k3-multiprocess-test/builds/$b/artifacts?per_page=100" \
  | jq -r '.[] | select(.path|endswith("preemption_correctness/ref.txt")) | "\(.job_id) \(.sha1sum)"'
done
```

If the sha1 values match for the same vLLM version and `async` value, change 1 is safe. To check the fast-fail `if:` after it lands, look at the `:skull:` step in a red build. If it shows `broken / conditional_failed`, it never ran.

```json
{"items": [
  {"lever": "preemption_correctness: cache plain-vLLM ref rung, run D on 1 GPU (fallback: run ref and D in parallel)",
   "gpu_h_30d": 450,
   "basis": "estimated",
   "merge_effect": {"en": "Job 28.6 -> ~11 min; it was the last job in build 6457, so build duration up to -17 min; frees 2-GPU slots", "vi": "Job 28.6 -> ~11 phút; là job xong cuối trong build 6457, nên thời gian build giảm tới ~17 phút; giải phóng slot 2-GPU"},
   "change": {"en": "Store ref.txt keyed by vLLM version+model+dataset+flags+GPU model, refresh it on the nightly dev build, and run only rung D on a 1-GPU pod. Quick first step: run ref and D at the same time (~129 GPU-h, no coverage change).", "vi": "Lưu ref.txt theo khóa phiên bản vLLM+model+dataset+flags+loại GPU, làm mới ở build dev hằng đêm, PR chỉ chạy rung D trên pod 1 GPU. Bước nhanh trước: chạy ref và D song song (~129 GPU-h, không mất coverage)."},
   "where": ".buildkite/k3_tests/multiprocess/scripts/workloads/vllm/preemption-correctness.sh:180-191; pipeline.yml:338-362",
   "risk": {"en": "A stale or non-deterministic ref causes false failures; vLLM-only regressions are caught by the nightly build, not the PR. LMCache paths still fully tested by rung D.", "vi": "ref cũ hoặc không tất định gây fail giả; lỗi chỉ thuộc vLLM sẽ được build nightly bắt thay vì PR. Đường LMCache vẫn được rung D kiểm tra đầy đủ."},
   "ticket": "",
   "confidence": "medium"},
  {"lever": "Fix top flaky workloads (long_doc_qa_l2, long_doc_qa, dsv4, vllm_bench, kimi)",
   "gpu_h_30d": 187.9,
   "basis": "measured",
   "merge_effect": {"en": "Each retry adds one queue wait + one more run; build 6457: vllm_bench retry = 9.0 min failed run + 3.4 min queue + 12.2 min rerun", "vi": "Mỗi retry thêm một lần chờ queue + một lần chạy; build 6457: retry vllm_bench = 9.0 phút chạy lỗi + 3.4 phút chờ + 12.2 phút chạy lại"},
   "change": {"en": "Fix the root causes of first-try failures (e.g. vllm_bench fails 'Verification failed' with 0 failed requests, a throughput-noise check), then lower the retry limits.", "vi": "Sửa nguyên nhân lỗi lần đầu (vd vllm_bench báo 'Verification failed' dù 0 request lỗi, do nhiễu throughput), sau đó giảm số lần retry."},
   "where": ".buildkite/k3_tests/multiprocess/pipeline.yml:10-24 (retry anchors), :134-187",
   "risk": {"en": "Making a threshold looser may hide real performance or cache-hit regressions; keep the metric and log it.", "vi": "Nới ngưỡng có thể che lỗi hiệu năng/cache-hit thật; vẫn giữ và ghi log chỉ số."},
   "ticket": "LM-762",
   "confidence": "medium"},
  {"lever": "Fast-fail: cancel MP build when lint/unit/GHA Test fails on the same commit",
   "gpu_h_30d": 188.4,
   "basis": "measured",
   "merge_effect": {"en": "No gain for the red PR; frees GPU pods for other PRs (queue effect not measured)", "vi": "Không nhanh hơn cho PR đỏ; giải phóng pod GPU cho PR khác (chưa đo ảnh hưởng queue)"},
   "change": {"en": "Commit the local work after fixing it: the step 'if: build.state' is likely checked at upload time, the script reads a token from a local Claude config backup, and the GHA Test workflow has no hook.", "vi": "Commit phần làm local sau khi sửa: 'if: build.state' có thể bị đánh giá lúc upload, script đọc token từ file backup cấu hình Claude, và workflow GHA Test chưa có hook."},
   "where": ".buildkite/k3_tests/multiprocess/pipeline.yml:624-652 (local diff); .buildkite/scripts/fast_fail_cancel.py:29-38",
   "risk": {"en": "No coverage is lost (the build would fail anyway); cancel_on_build_failing with automatic retry may cancel siblings on a flaky first attempt.", "vi": "Không mất coverage (build vốn sẽ fail); cancel_on_build_failing cùng auto-retry có thể hủy job khác khi lần đầu lỗi do flaky."},
   "ticket": "LM-1062",
   "confidence": "medium"}],
 "summary": {"en": "The biggest saving is inside preemption_correctness: about 62% of each job is a plain-vLLM reference run that does not test LMCache and runs one after the other with the LMCache run. Fixing flaky workloads and finishing fast-fail (now only uncommitted local work with a likely trigger bug) add about 190 GPU-h each.", "vi": "Khoản tiết kiệm lớn nhất nằm trong preemption_correctness: ~62% mỗi job là lần chạy tham chiếu vLLM thuần không kiểm tra LMCache và chạy nối tiếp với lần chạy LMCache. Sửa test flaky và hoàn thiện fast-fail (hiện chỉ là thay đổi local chưa commit, có thể lỗi điều kiện kích hoạt) mỗi việc thêm ~190 GPU-h."},
 "unverified": [
  "Lever totals 188.4 / 136.9 / 187.9 / 801.4 GPU-h and '229 of 235 canceled by build_skipping' come from the cache and were not recomputed",
  "Job timing measured in only one full PR build (6457); builds 6458 and 6459 were skipped by the 'skip expensive ci' label",
  "ref rung output is deterministic across nodes and runs for the same vLLM version",
  "Whether ASYNC_SCHEDULING also changes the baseline server (decides if one ref can serve both matrix jobs)",
  "Buildkite step 'if: build.state == failing' is checked at upload time, so the fast-fail step never runs",
  "Whether cancel_on_build_failing cancels sibling jobs before an automatic retry",
  "dsv4_flash_tp was missing from build 6457 (hma_dsv4_correctness ran instead); it may be removed upstream and the local clone may be behind",
  "Effect on queue wait p90 for all changes (not measured)"]}
```