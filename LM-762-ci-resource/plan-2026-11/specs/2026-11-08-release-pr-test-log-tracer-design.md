# Release → PR → Test Case → Error Log Animated Tracer Design Spec

- **Date**: 2026-11-08
- **Target**: `LM-762-ci-resource/plan-2026-11/06_PR_TO_CI_VISUAL.html` (via `outputs/cpu_tests/report_model.py`, `build_observe.py`, `i18n_vi.py`, `verify_page.py`)
- **Size**: Focused feature addition inside `#obs/release` (with deep-links from `#obs/trend` Executive Report charts)

## 1. Intent & Why
Enable release managers and engineers to trace any release tag (`v0.5.7rc1`, `v0.5.7rc2`, `v0.5.7rc3`, `v0.5.7rc4`, `v0.5.7`, or `dev`) left-to-right across 5 linked stages:
`[1. Release / RC Tag] ══► [2. PRs (#) & Changed Files] ══► [3. Critical Stage & Feature Area] ══► [4. CPU & GPU Test Cases] ══► [5. Error Logs & Actionable Fix]`
so they can immediately deduce where an issue lives, inspect the real error log/stacktrace, and copy a ready-made diagnostic summary into the Daily Report.

## 2. Goals, Non-Goals & Anti-Goals
- **Goals**:
  - Extract real per-tag PR lists (`v0.5.6 → rc1`, `rc1 → rc2`, `rc2 → rc3`, `rc3 → rc4`, `rc4 → v0.5.7`, `v0.5.7 → dev`) from `third_party/LMCache` git history in `report_model.py`, mapping each PR's touched files to the 28 feature areas (`areas.py`), CPU test files (`tests/...`), and GPU E2E workloads (`gates.py`).
  - Embed curated real CI/Release Error Logs & Stacktraces (from Buildkite & GitHub Actions runs on `v0.5.7rc1..rc4` and `dev`, e.g., `k3-blend-test #4348` CUDA IPC pointer error, `rc1` `ubuntu-26.04` `/tmp` disk quota `Errno 122` & PyPI/GitHub release asset collision, `R-3` `setuptools_scm` dirty `0.5.7rc5.dev0` version bump, `rc3` Kafka consumer offset / `<2.16` hang, `rc4` P2P adapter teardown retry & `amd-mp-test #1257` `memcheck` race, `cu129` `torch==2.14.0` resolver failure).
  - Render an interactive **5-Stage Left-to-Right Animated Workflow** (`#obsTracer`) at the top of `#obs/release` (and clickable directly from the Release Train chips and `#obs/trend` chart bars):
    - **Stage 1 (Release / RC Tag)**: Selectable tag cards (`v0.5.7-rc1`, `v0.5.7-rc2`, `v0.5.7-rc3`, `v0.5.7-rc4`, `v0.5.7`, `dev`) with status badge & PR count.
    - **Stage 2 (PRs in Tag)**: Filterable list (`Critical / Suspect PRs` vs. `All PRs in tag`), showing `#PR`, title, author, and touched area badges. Clicking any PR triggers the left-to-right animated connector pulse across Stages 3 → 5.
    - **Stage 3 (Critical Stage & Flow)**: Animated mini step-sequence (e.g. `Trace input → Prefix replay → [CacheBlend analysis] → Report`) highlighting the critical stage and listing the exact source files modified by the selected PR.
    - **Stage 4 (CPU Unit Tests & GPU E2E Gates)**: Exact CPU test files (`tests/...`, clickable to open in `#cpu/explore`) + GPU E2E / publish jobs (`PASS` / `FAIL` / `SMOKE` / `CONDITIONAL` badges). Clicking a test/job focuses Stage 5 on its log.
    - **Stage 5 (Error Log Terminal & Daily Report Snippet)**: Dark terminal viewer showing the exact error log / stacktrace lines, root-cause diagnosis, local reproduce command, and a 1-click **"Copy Daily Report Summary"** button.
- **Non-Goals**:
  - Live-streaming gigabyte raw logs from Buildkite without tokens (curated high-signal log excerpts are embedded offline, with direct links to full Buildkite/GHA run URLs).
- **Anti-Goals**:
  - Re-introducing text clutter into `#obs/trend` (the Executive Report tab stays a pure 8-chart grid; clicking a bar in `Test Case Failed Order` or `Release Cadence` jumps to `#obs/release` and activates the corresponding trace).

## 3. Approaches Considered
1. **Approach 1 (Selected — 5-Stage Left-to-Right Animated Trace Pipeline in `#obs/release` + Deep-Link from `#obs/trend`)**: Full horizontal 5-column animated workflow with SVG/CSS flow beams (`══►`) leading into a dark Error Log terminal.
2. **Approach 2 (Table + Slide-over Drawer)**: Rejected because it hides the end-to-end `Release → PR → Test → Log` chain behind popups.

## 4. Verification & Definition of Done (DoD)
- `report_model.py` generates `RP.release_trace` with real PRs, mapped areas, test files, critical path sequences, and error logs for `v0.5.7rc1..rc4`, `v0.5.7`, and `dev`.
- `verify_page.py` passes with `JS errors: none`, `traceStages == 5`, `tracePRs > 0`, `traceLogs > 0`, `rpCards == 8`, `rpClutter == 0`, and `untranslated in VI: 0`.

