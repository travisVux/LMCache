# 03 — Approach and plan

## Target test pyramid (after this work)

```
            ┌──────────────────────────────┐
  nightly   │ L4 full: 4-GPU, dual-engine  │  dsv4 TP=4, Kimi, perf vs baseline, engine matrix
            ├──────────────────────────────┤
  label     │ L3 real-engine smoke (1 GPU) │  small/dummy model, adapter/connector PRs only
            ├──────────────────────────────┤
  every PR  │ L2 engine-free server tests  │  standalone LMCache server + simulated clients (CPU or 1 GPU)
            ├──────────────────────────────┤
  every PR  │ L1 unit tests (CPU)          │  existing tests/v1/**
            └──────────────────────────────┘
```

Target: L1 + L2 finish in **≤ 15 min** and catch most core bugs before any engine starts.

---

## WS-A — Engine-agnostic test path (S1)

**Idea:** grow `lmcache bench server` from a perf bench into a *scenario runner*: start the MP server,
drive it with simulated workers/clients, assert behavior. No vLLM/SGLang.

Approach:
1. Add a `--scenario` concept (or new `cases/` entries) to `server_bench`. Each case = setup + traffic + asserts.
2. First scenarios (picked from R3, cheapest + most-run):

| Scenario | Replaces / shadows | Asserts |
|---|---|---|
| `store_lookup_retrieve` | core of lm_eval / long_doc_qa hit path | retrieve bytes == stored bytes; prefix hit length correct |
| `restart_reregister` | restart_recovery | kill server → restart → simulated workers re-register → lookup works |
| `concurrency_storm` | deadlock | N clients × M requests finish under timeout; no stuck locks |
| `stats_http` | cache_stats, http_api | counters match traffic; HTTP endpoints respond |
| `l2_roundtrip` | long_doc_qa_l2 (flow part) | evict L1 → load from L2 → bytes equal |
| `server_down_client_ok` | fault_tolerance | client sees clean miss/timeout, no hang |

3. Run each in CPU mode (GHA, already wired via `cpu_device.yml`) and GPU mode (1 GPU, fake KV buffers via `--kvcache-shape-spec`, `--use-mla`, `--tp-size`).
4. Asserts write a JSON verdict (same format as WS-D) so results are comparable.

Deliverable PRs: `A1` scenario framework + 2 scenarios · `A2` remaining scenarios · `A3` CI wiring (GHA CPU + Buildkite 1-GPU, shadow mode).

## WS-B — Server-bench-ify E2E (S2)

**Idea:** move perf/flow checks from "LMCache-engine vs baseline-engine" to "LMCache server bench vs stored baseline".

Approach:
1. From R4, for each baseline-using workload choose: **stored baseline** (perf) or **same-engine replay** (correctness).
2. First target: `vllm_bench` (2 GPU, retry 3, flakiest by design). Split into:
   - PR tier: `lmcache bench server` throughput + warm-hit retrieve check, compared to rolling stored baseline. 0–1 GPU.
   - Nightly: keep current dual-engine `vllm_bench`.
3. Second target: `long_doc_qa` → 1-GPU, LMCache engine only, compare TTFT to rolling 5-day worst stored baseline (reuse logic from `comprehensive/run-single-config.sh`).
4. Use `LAUNCH_BASELINE=false` (already in `launch-processes.sh`) to move steps from 2-GPU to 1-GPU pods.

Deliverable PRs: `B1` vllm_bench PR-tier twin · `B2` long_doc_qa single-engine + stored baseline · `B3` baseline storage helper shared with comprehensive.

## WS-C — Minimum-sufficient test rule (S3)

**Idea:** write the rule, then encode it.

| Change type (paths) | Required |
|---|---|
| Docs / comments only | lint |
| Tests only (`tests/**`) | changed tests + lint |
| Core (`lmcache/v1/multiprocess/**`, storage, distributed, cache identity) | L1 + L2 |
| Adapter / connector (`lmcache/integration/**`, mp connectors) | L1 + L2 + L3 smoke for the changed engine only |
| Kernels (`csrc/**`, cuda ops) | L1 GPU kernels + L3 smoke |
| KV layout / MLA / fp8 / hybrid | + matching small-model layout smoke; full TP on label |
| Deps / CI (`requirements/**`, `pyproject.toml`, `.buildkite/**`, `.github/**`) | full |
| `force-ci` (or new `mp-full` / `mp-full-tp`) label | full (override). NOT `full`: `automerge-labeler.yml:14-17` adds it to almost every PR (P8) |

> Refined rule table, classifier and shadow results: [outputs/P8/shadow_report.md](outputs/P8/shadow_report.md).

Approach: doc first (`docs/` or CONTRIBUTING section) → shadow script that prints "what this rule would run" for each PR → compare to what failed in reality (R2 data) → only then wire into path-filter / Buildkite `if:`.

Deliverable PRs: `C1` rule doc · `C2` shadow classifier script (read-only) · `C3` wiring (after data).

## WS-D — Central acceptance config (S4)

**Idea:** one machine-readable file holds every PASS threshold + when it may be relaxed. Scripts read it instead of hardcoding.

Approach:
1. Draft schema: see [05_acceptance_profile.draft.yaml](05_acceptance_profile.draft.yaml). Keys: `criteria` (what PASS means), `profiles` (model + launch args + which criteria), `tiers` (pr / label / nightly), `relaxation` (allowed when / mandatory when).
2. Align with Issue #4861 "model profile" idea — post the draft as a comment first, get maintainer buy-in on location and shape.
3. Small loader (`python -m ...acceptance get <criterion> <profile>`) usable from bash.
4. Migrate one script at a time (start with `lm-eval.sh`, then `long-doc-qa.sh`, `vllm-bench.sh`). Default values unchanged → zero behavior change in first PR.
5. Fix the drift mismatch (0.05 default vs "< 0.01" comment) explicitly in the config with a note.

Deliverable PRs: `D1` schema + loader + unit tests (no script change) · `D2` migrate lm-eval · `D3` migrate perf scripts.

## WS-E — Lightweight loading (S5)

Approach:
1. From R5, define a **representative small-model set** (one per KV layout family).
2. Add a 1-GPU `layout_smoke` workload: dummy weights + `--hf-overrides` (few layers) for MLA/sparse-MLA/hybrid → byte-identical L1 round trip. This is the PR-tier stand-in for dsv4_flash_tp / kimi_linear_tp; full TP stays nightly / on matching paths.
3. Extend `cpu_e2e_validation` matrix with one dummy MLA config (script already supports it).
4. Note: dummy weights are valid for **KV round trip / byte-identical** checks, **not** for lm_eval scores — record this in WS-D relaxation rules.

Deliverable PRs: `E1` small-model set doc + profiles · `E2` layout_smoke workload · `E3` CPU dummy-MLA matrix entry.

---

## Rollout: shadow → gate → drop

| Step | What | Who decides |
|---|---|---|
| 1. Shadow | New L2/L3 tests run alongside existing ones, `soft_fail: true` | us |
| 2. Compare | ≥ 20 PRs / 2 weeks: every heavy-test failure — did the light test also fail? | data |
| 3. Gate | Light test becomes required (hard fail) | maintainers |
| 4. Move heavy | Heavy step moves to `full` label / nightly for matching path classes | maintainers |

## Success metrics

| Metric | Now | Target (end Dec) |
|---|---|---|
| GPU-minutes per core-only PR (multiprocess) | measure in R1 | −50% |
| Time-to-first-signal for core PR | measure | ≤ 15 min |
| Workloads with engine-free twin | 0 (server bench perf only) | ≥ 5 |
| Thresholds in central config | 0 | all multiprocess thresholds |
| Escaped bugs (caught on nightly, not PR) | measure | no increase |

## Risks

| Risk | Mitigation |
|---|---|
| Engine-free tests miss connector/engine bugs | WS-C rule keeps L3 smoke for adapter paths; shadow phase measures misses |
| Maintainers prefer another layout (Issue #4861) | Post design in issue before code; D1 is a pure addition |
| Stored baselines drift (hardware change) | Rolling worst-of-N + adaptive threshold (existing pattern); per-queue keying |
| Dummy weights hide numeric bugs | Only use for byte-identical KV checks; keep real-weight lm_eval in L3/nightly |
| Big PRs stall in review | One PR per row above, each < ~400 lines, shadow-only first |
