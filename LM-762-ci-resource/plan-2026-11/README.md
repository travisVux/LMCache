# Plan 2026-11 — Lightweight Test Alternatives

Short-term target from [Task.md](../Task.md). Parent goal: [Help LMCache merge more PRs](../../knowledge/inputs/Help%20LMCache%20merge%20more%20PR-English.pdf):
**cut the median PR open → mergeable time without adding GPUs.**

This task attacks the most expensive part of PR CI: multiprocess workloads that start a full
vLLM/SGLang engine (often two: LMCache + baseline) on 1–4 GPUs.

## One-line goal

> For a PR that only changes LMCache core logic, prove it is safe **without starting an inference
> engine** — using the standalone LMCache server + simulated client traffic, on CPU or 1 GPU, in ≤ 15 min.

## Files

| File | What it holds |
|---|---|
| [01_ANALYSIS.md](01_ANALYSIS.md) | Current state: what exists, what each multiprocess workload costs, what it really checks, gaps |
| [02_RESEARCH_DIRECTIONS.md](02_RESEARCH_DIRECTIONS.md) | Open questions to answer before building, and how to answer each |
| [03_APPROACH_AND_PLAN.md](03_APPROACH_AND_PLAN.md) | Approach per subtask, phases, PR list, success metrics, risks |
| [04_AGENT_PROMPTS.md](04_AGENT_PROMPTS.md) | Ready-to-paste prompts for Claude Code agents, one per work item |
| [05_acceptance_profile.draft.yaml](05_acceptance_profile.draft.yaml) | First draft of the machine-readable acceptance config (subtask 4) |

## The 5 subtasks (from Task.md) → work streams

| # | Subtask | Stream | Key existing asset |
|---|---|---|---|
| S1 | Engine-agnostic test path | **WS-A** | `lmcache bench server` (already runs on CPU in GHA `cpu_device.yml`) |
| S2 | Server-bench-ify E2E tests | **WS-B** | `vllm_bench` workload, `server_bench/cases/` |
| S3 | Minimum-sufficient test rule | **WS-C** | path-filter, `full`/`mp` labels, matrix `if:` |
| S4 | Central acceptance criteria | **WS-D** | thresholds spread over `lm-eval.sh`, `long-doc-qa.sh`, `vllm-bench.sh`, `run-single-config.sh`; Issue #4861 |
| S5 | Lightweight loading | **WS-E** | `--load-format dummy`, `VLLM_HF_OVERRIDES`, `cpu_e2e_validation` (opt-125m) |

## Timeline (Nov 2026)

| Week | Dates | Focus | Exit check |
|---|---|---|---|
| W1 | Nov 4–10 | Research + inventory (02), coverage map, baseline cost numbers | Coverage map table done; GPU-minutes per workload known |
| W2 | Nov 11–17 | WS-D acceptance config + WS-E dummy/small-model smoke | Draft PR for acceptance config; dummy-weight smoke runs green |
| W3 | Nov 18–24 | WS-A engine-agnostic cases + WS-B first bench-ified workload | 1 E2E workload has an engine-free twin that catches the same seeded bugs |
| W4 | Nov 25–30 | WS-C rule doc + path mapping, shadow-mode run, report | Shadow-mode data on ≥ 20 real PRs; proposal posted to maintainers |

## Rules for this plan

- **Measure first.** No "faster" claim without before/after numbers (ties to Observability direction).
- **Shadow before gate.** New lightweight tests run *next to* the heavy ones first; we drop heavy ones only after they agree.
- **Never weaken silently.** Every relaxation is written in the acceptance config with a reason and a "full test mandatory when…" rule.
- Upstream style: follow `third_party/LMCache/AGENTS.md` / `CLAUDE.md`, DCO sign-off, small PRs.
