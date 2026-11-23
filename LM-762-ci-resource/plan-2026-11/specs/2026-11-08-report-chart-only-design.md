# Executive Report (`#obs/trend`) — Pure Chart Grid Design Spec

- **Date**: 2026-11-08
- **Target**: `LM-762-ci-resource/plan-2026-11/06_PR_TO_CI_VISUAL.html` (generated via `outputs/cpu_tests/build_observe.py`, `i18n_vi.py`, `verify_page.py`)
- **Size**: Small change (single view refactor in `build_observe.py`)

## 1. Intent & Why
Simplify the **Executive Report (`#obs/trend`)** tab so that engineers and release managers can scan repository health at a glance without reading walls of text. Every metric is represented purely by a clean card containing its title, current period value, and chart.

## 2. Goals, Non-Goals & Anti-Goals
- **Goals**:
  - Present all report metrics in a unified 2-column chart grid (`.rp-grid`) controlled by the top `Daily` / `Weekly` / `Monthly` selector.
  - Each card shows only: **Metric Title**, **Selected Period Value** (with compact delta badge & mini legend if stacked), and the **SVG Chart**.
  - Render **Test Case Failed Order** as a horizontal bar chart SVG card inside the same 2-column grid (ranked highest to lowest failures, with full details on hover tooltip).
- **Non-Goals**:
  - Changing data collection scripts (`report_collect.py`, `report_model.py`) or other tabs (`now`, `prs`, `release`, `ci`, `gates`, `cpu`, `gpu`).
- **Anti-Goals**:
  - Do NOT render duplicate Hero KPI cards at the top of the report.
  - Do NOT render the 3-column text summary block (`Needs attention` / `Improved` / `Shipped`).
  - Do NOT render verbose `Measures: ...` or `Source: ...` paragraphs inside metric cards.
  - Do NOT show Section 2 (`Empirical CI Optimization Verification`) or collapsible raw data tables on the `#obs/trend` tab.

## 3. Approaches Considered
1. **Approach 1 (Selected — Unified 2-Column Chart Grid)**: All 8 metrics (including `Test Case Failed Order` as an SVG horizontal bar chart) live in one uniform 2-column `.rp-grid`. Compact, scannable in one viewport, zero visual clutter.
2. **Approach 2 (Time-Series Grid + Full-Width Leaderboard Card)**: Time-series charts in a 2-column grid with a wide full-row horizontal chart at the bottom for failing tests. Rejected because it breaks grid uniformity.

## 4. Specification of the 8 Chart Cards in `#obs/trend`
All 8 cards render inside `#obsTrendBody > .rp-grid`:
1. **PR Volume (Success vs. Failed)** (`pr_vol`): Stacked vertical bar chart (`Merged` in green vs. `Failed CI / Unmerged` in red) per Day/Week/Month.
2. **Time PR to Merge (Median)** (`ttm`): Vertical bar chart of median hours/days from PR creation to merge (`p90` in sub-label/tooltip).
3. **Successful CI Runs (Median / Day)** (`ci_med`): Vertical bar chart of median daily passed CI runs (total passed & median runs/PR in sub-label/tooltip).
4. **Test Case Failed Order (Top Failing)** (`fail_order`): Horizontal bar chart SVG of top 8 failing test cases/workloads ordered highest → lowest for the selected period (or baseline window if period has 0 per-test logs), with hover tooltip showing full test name, fail rate %, GPU-h waste, and root cause.
5. **PR First-Pass CI Rate** (`ci_fp`): Vertical bar chart of first-build pass rate `%` on `k3-unit-tests`.
6. **Active Contributors & PR Velocity** (`contrib`): Stacked/grouped vertical bar chart of merged PRs & active contributors per period.
7. **Release Cadence & Publish Success Rate** (`rel_ship`): Vertical bar chart of `publish.yml` success rate `%` + release tag count in period.
8. **GPU Cost per Merged PR** (`gpu_eff`): Vertical bar chart of multiprocess E2E `GPU-h / merged PR` (with retry/cancel waste `%` in sub-label/tooltip).

## 5. Verification & Definition of Done (DoD)
- `python build_page.py` regenerates `06_PR_TO_CI_VISUAL.html` cleanly.
- `python verify_page.py` passes with `JS errors: none`, all widgets rendered, and `untranslated in VI: 0`.

