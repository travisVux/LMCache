# 04 — Agent prompts

Copy-paste prompts for Claude Code. Run from `<workspace>`.
Each prompt is self-contained (an agent starts with no context).

## Shared context block (paste at the top of every prompt)

```text
CONTEXT
- Project: LMCache (KV cache layer for vLLM/SGLang). Local clone: third_party/LMCache.
  Read third_party/LMCache/AGENTS.md and CLAUDE.md first and follow their rules.
- Parent goal: reduce PR open→mergeable time without adding GPUs.
- This task: "Lightweight test alternatives" — replace expensive multiprocess E2E tests
  (full vLLM/SGLang engine, often a 2nd baseline engine, 1–4 GPUs) with engine-free or
  small-model tests for PRs that don't need a real engine.
- Plan docs: LM-762-ci-resource/plan-2026-11/ (README, 01_ANALYSIS, 02_RESEARCH_DIRECTIONS, 03_APPROACH_AND_PLAN).
- Key files:
  .buildkite/k3_tests/multiprocess/pipeline.yml            (all MP workloads, GPU counts, matrices)
  .buildkite/k3_tests/multiprocess/scripts/workloads/**     (workload scripts + asserts)
  .buildkite/k3_tests/multiprocess/scripts/launch-processes.sh (LAUNCH_BASELINE flag)
  lmcache/cli/commands/bench/server_bench/**                (engine-free server bench)
  .github/scripts/cpu_server_bench_test.sh, run-cpu-e2e-validation.sh
  .github/workflows/cpu_device.yml
- Buildkite: org `lmcache`. Use REST API with token from env BUILDKITE_API_TOKEN
  (the remote MCP returns 401 — do not rely on it).
RULES
- Read-only on upstream unless the prompt says to edit. Never push, never open PRs.
- Write outputs into LM-762-ci-resource/plan-2026-11/outputs/<prompt-id>/.
- Simple English, tables over prose. Cite file:line for every claim about code.
- If something is unknown, write "UNKNOWN" and how to find out. Do not guess numbers.
```

---

## P1 — Cost baseline (R1)

```text
<shared context>
TASK: Measure what the multiprocess pipeline costs per PR.
1. Find the Buildkite pipeline slug that runs .buildkite/k3_tests/multiprocess/pipeline.yml
   (check .buildkite/pipeline.yml and BK_WEB_SETUP.md).
2. Using the Buildkite REST API, fetch builds from the last 30 days for PR branches.
   Reuse/extend scripts/pull_buildkite_telemetry.py if it fits.
3. For every job: label, state, started_at, finished_at, retried / retries_count,
   GPU count (from the group name "Multiprocess (N-GPU)"), queue wait (runnable_at→started_at).
4. For a sample of 30 jobs per workload, fetch logs and find the timestamp where the engine
   becomes ready (wait-for-servers.sh output). Compute startup share = startup / total.
5. Output: outputs/P1/cost_by_workload.csv and summary.md with a table:
   workload | jobs/build | p50 wall | p90 wall | GPU-min p50 | startup % | first-try fail % | pass-after-retry %.
   Add a short "Top 5 by GPU-min" list.
```

## P2 — Coverage map, static + git history (R2a, R2b)

```text
<shared context>
TASK: Build a coverage map: which bug classes does each multiprocess workload catch?
1. For each workload in pipeline.yml, read its script under scripts/workloads/ and list
   every assertion (what is checked, threshold, file:line).
2. git log over the last 6 months in third_party/LMCache: find commits/PRs whose message or
   diff mentions a multiprocess workload name, or that fix something found by MP CI
   (search "fix", "regression", workload names, "deadlock", "restart", "l2", "mla").
   If gh is available, also list PRs where an MP step failed then passed after a code change.
3. Classify each real catch into a bug class (cache identity, lookup, store, L2, restart,
   concurrency/deadlock, KV layout, kernel, connector/engine API, perf, packaging).
4. For each bug class, mark which layers could catch it: UT (tests/v1/**), server bench,
   CPU E2E, 1-GPU 1-engine, dual-engine. Justify with existing tests (file names).
5. Output outputs/P2/coverage_map.md: matrix bug class × layer, and a list
   "workloads whose catches are fully covered by cheaper layers".
```

## P3 — Mutation test (R2c) — run after P2 and P4

```text
<shared context>
TASK: Seed bugs in LMCache core and see which test layers catch them.
1. Create a git worktree of third_party/LMCache (do not touch the main checkout).
2. Write 10–15 small mutations, one per branch, in core paths found in P2 (examples:
   off-by-one in prefix hit length, wrong chunk hash seed, skip async store, drop L2 write,
   forget to release lock on retrieve, skip worker re-register on restart, wrong dtype size).
3. For each mutation run: relevant unit tests (pytest -k), and `lmcache bench server --mode cpu`
   via .github/scripts/cpu_server_bench_test.sh (and new scenarios if WS-A exists).
   GPU/engine layers: mark "needs GPU run" and list the exact command; do not fake results.
4. Output outputs/P3/mutation_results.md: mutation | file:line | UT caught? | server bench caught? | notes.
```

## P4 — Server bench gap analysis (R3)

```text
<shared context>
TASK: Decide how far `lmcache bench server` can replace server-level E2E workloads.
1. Read lmcache/cli/commands/bench/server_bench/** fully (arguments, client, config, cases).
2. Run it locally in CPU mode with .github/scripts/cpu_server_bench_test.sh (Linux/WSL).
   Record the command, runtime, and output.
3. For each workload: restart_recovery, cache_stats, http_api, deadlock, long_doc_qa_l2,
   fault_tolerance, lm_eval (hit path only) — list what the workload does and what the
   server bench would need to simulate it (multi-worker register, server kill/restart,
   L2 backend config, metrics scrape, concurrency storm, HTTP calls).
4. Output outputs/P4/server_bench_gaps.md: workload | needed feature | exists? (file:line) |
   effort S/M/L | can replace fully / partly / no.
5. Propose a minimal design for a "scenario" extension (class + CLI flag), max 1 page.
```

## P5 — Baseline engine removal (R4)

```text
<shared context>
TASK: For workloads that start a baseline engine, decide if we can drop it.
Workloads: vllm_bench, long_doc_qa, long_doc_qa_l2, p2p, preemption_correctness
(grep BASELINE_PORT under scripts/workloads to confirm the list).
1. For each, read the script: is the baseline used for correctness (output equality) or
   performance (ratio)? Cite file:line.
2. Performance: using P1 data (or the Buildkite API), collect baseline-side numbers over the
   last 30 days. Report mean, stddev, CV. If CV < 10%, propose a stored rolling baseline
   (reuse the 5-day worst logic in .buildkite/k3_tests/comprehensive/scripts/run-single-config.sh ~L328-420).
3. Correctness: can a cache-disabled replay on the same engine replace the baseline engine?
   What would break?
4. Output outputs/P5/baseline_decisions.md: workload | baseline role | decision
   (stored / same-engine replay / keep) | GPU saved per run | risk.
```

## P6 — Small-model set (R5)

```text
<shared context>
TASK: Define a representative small-model set for lightweight smoke.
1. List KV layout families used in MP CI: MHA/GQA (Qwen3-14B), MLA, sparse-MLA+fp8
   (DeepSeek-V4-Flash), hybrid/linear (Kimi-Linear), SWA/HMA (gemma). Check workload scripts
   and engine adapters for launch flags.
2. For each family find: (a) the smallest public model with the same layout, (b) a
   `--load-format dummy` + `--hf-overrides` config that shrinks layers/experts but keeps
   the same per-layer KV shape. See .github/scripts/run-cpu-e2e-validation.sh for existing knobs
   and .buildkite/configs/*.yaml for dummy precedents.
3. For each, state: GPU memory estimate, fits 1 GPU?, fits CPU?, which existing checks stay
   valid with dummy weights (byte-identical KV round trip: yes; lm_eval score: no).
4. Output outputs/P6/small_model_set.md and a YAML snippet in the format of
   LM-762-ci-resource/plan-2026-11/05_acceptance_profile.draft.yaml (profiles: section).
```

## P7 — Acceptance criteria survey (R6)

```text
<shared context>
TASK: Collect every PASS threshold used by GPU/E2E CI.
1. grep in .buildkite/, .github/, benchmarks/, tests/tools/ for: SCORE_, TOLERANCE, THRESHOLD,
   SLOWDOWN, MAX_, MIN_, baseline, byte-identical, diff.
2. For each: name, default, per-step overrides in pipeline YAML, file:line, git blame
   (who/when/PR), and what it protects.
3. Flag conflicts (e.g. lm-eval.sh SCORE_TOLERANCE default 0.05 vs pipeline comment "drift < 0.01").
4. Read Issue #4861 (gh issue view 4861 -R LMCache/LMCache --comments) and summarize what
   maintainers said about shared model profiles and result formats.
5. Update LM-762-ci-resource/plan-2026-11/05_acceptance_profile.draft.yaml with real values
   (keep comments with file:line sources). Output outputs/P7/criteria_inventory.md.
```

## P8 — Path rule classifier (R7, WS-C2)

```text
<shared context>
TASK: Write a read-only classifier that says which test tiers a PR needs.
1. Map lmcache/ and csrc/ directories into classes: docs, tests-only, core, adapter, kernel,
   kv-layout, deps/ci. Use the table in 03_APPROACH_AND_PLAN.md (WS-C) as the starting rule.
2. Write tools/ci_rule_shadow.py in LM-762-ci-resource/plan-2026-11/outputs/P8/ (NOT in upstream):
   input = list of changed files (or a PR number via gh), output = JSON {class, required_tiers, reason}.
3. Run it on the last 100 merged PRs (gh pr list --state merged -L 100 --json number,files).
   Join with P1/P2 data: for PRs where an MP step failed for a real code reason, would the rule
   still have run a layer that catches it?
4. Output outputs/P8/shadow_report.md: % PRs per class, estimated GPU-min saved, list of
   "would have missed" PRs (must be empty or explained).
```

## P9 — Implement WS-A scenario framework (after P4, G2 passed)

```text
<shared context>
TASK: Implement engine-free scenarios in `lmcache bench server` in a git worktree of
third_party/LMCache, on a new branch `ci/server-bench-scenarios`.
1. Follow the design from outputs/P4/server_bench_gaps.md.
2. Implement 2 scenarios first: store_lookup_retrieve and restart_reregister.
   Each must: start/attach to the MP server, simulate workers/clients, assert, and write a
   JSON verdict {scenario, pass, checks:[{name, expected, actual}]}.
3. Add unit tests under tests/ that run in CPU-only CI (no CUDA markers).
4. Extend .github/scripts/cpu_server_bench_test.sh with an optional SCENARIO env var.
5. Run pre-commit / format.sh and the new tests locally. Show results.
6. Do not push. Write a PR description draft (simple English, motivation + numbers from P1)
   to outputs/P9/PR_DESCRIPTION.md. Commits must have DCO sign-off.
```

## P10 — Implement WS-D acceptance config loader (after P7, maintainer feedback)

```text
<shared context>
TASK: Add a central acceptance config with zero behavior change, in a worktree branch
`ci/acceptance-profiles`.
1. Put the YAML at the location agreed in Issue #4861 (default: .buildkite/profiles/acceptance.yaml,
   matching VincyZhang's proposed .buildkite/profiles/ layout — see outputs/P7/criteria_inventory.md;
   state the assumption if maintainers have not confirmed).
2. Write a small Python loader + CLI: `python -m <module> get <criterion> [--profile X] [--tier pr]`
   printing one value, usable from bash. Include schema validation and unit tests.
3. Migrate ONLY common/lm-eval.sh to read SCORE_TOLERANCE and SCORE_MIN from the loader,
   with env vars still overriding. Defaults must equal today's values.
4. Prove no change: run the lm-eval verdict python blocks with stub inputs before/after.
5. Draft PR description in outputs/P10/PR_DESCRIPTION.md. Do not push.
```

## P11 — Weekly status (run every Friday)

```text
<shared context>
TASK: Write the weekly status for this plan.
Read LM-762-ci-resource/plan-2026-11/** and outputs/**. Produce outputs/status/<YYYY-MM-DD>.md:
- Done this week (with links), numbers moved (GPU-min, time-to-signal), gates G1–G3 status,
  blockers, next week's 3 priorities. Max 1 page, tables first.
```

---

## Suggested run order

| Week | Prompts | Can run in parallel? |
|---|---|---|
| W1 | P1, P2, P4, P7 | yes (independent) |
| W1–W2 | P5 (needs P1), P6, P8 (needs P1/P2) | P6 independent |
| W2 | P10 (after P7 + Issue #4861 reply) | — |
| W3 | P3 (needs P2, P4), P9 (needs P4 + G2) | P3 ∥ P9 |
| Every Fri | P11 | — |
