# Pure Chart Grid Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the `#obs/trend` Executive Report view in `06_PR_TO_CI_VISUAL.html` into a clean, uniform 2-column grid of 8 metric charts (including `Test Case Failed Order` as a horizontal bar chart SVG), removing all duplicate Hero KPI cards, text summary blocks, per-card description paragraphs, and secondary sections.

**Architecture:**
- `outputs/cpu_tests/build_observe.py`:
  - Remove Section 2 (`Empirical CI Optimization Verification`) from `HTML` under `data-tab="trend"`, leaving a single clean `<section class="card" data-view="obs" data-tab="trend">` with `#obsTrendP` and `#obsTrendBody`.
  - Update `build_nav.py` tab badge for `Executive Report` from `'1–2'` to `'1'` and renumber sections `2..8` across `now`, `prs`, `release`, `ci`.
  - In `build_observe.py` (`rTrend`), render a single `.rp-grid` containing 8 pure chart cards:
    - Each card has `.rp-top` (Metric Title + right-aligned current value `.rp-v-inline` & compact delta badge `.rp-d`), optional 1-line mini legend `.rp-leg` (for stacked bars), and the SVG chart (`chart()` for the 7 time-series metrics; `failOrderChart()` for the horizontal bar chart of top failing test cases/workloads).
- `outputs/cpu_tests/verify_page.py` & `i18n_vi.py`:
  - Update `verify_page.py` widget assertions (`rpCards == 8`, `rpBars > 0`, `rpFailBars > 0`, remove obsolete `measured` widget check) and add any new heading strings to `i18n_vi.py`.

**Tech Stack:** Python 3 build pipeline (`build_page.py`, `verify_page.py`), Vanilla JS + SVG inside standalone HTML.

---

### Task 1: Update `verify_page.py` for the Pure Chart Report Contract (TDD Red Step)

**Files:**
- Modify: `LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/verify_page.py`

- [ ] **Step 1: Update `verify_page.py` to assert the pure-chart report contract**
  - Assert `#obsTrendBody .rp-card` count is `8`.
  - Assert `#obsTrendBody .rp-hbar` (horizontal bar SVG rects in the `Test Case Failed Order` chart card) count `> 0`.
  - Assert zero `.rp-hero-grid`, `.rp-sum`, `.rp-w`, `.rp-src` elements inside `#obsTrendBody` (`rpClutter == 0`).
- [ ] **Step 2: Run `verify_page.py` and confirm it fails on the old UI**
  - Run: `python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/verify_page.py`
  - Expected: `FAIL` (`rpHbars: 0`, `rpClutter > 0`).

### Task 2: Refactor `build_nav.py`, `build_observe.py`, and `i18n_vi.py` to Pure Chart Grid (TDD Green Step)

**Files:**
- Modify: `LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/build_nav.py`
- Modify: `LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/build_observe.py`
- Modify: `LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/i18n_vi.py`

- [ ] **Step 1: Update `build_nav.py` tab numbering for `obs`**
  - `TABS.obs`: `[['trend','Executive Report','1'],['now','Live Overview','2–3'],['prs','PR Queue','4–5'],['release','Release Train','6'],['ci','Pipeline Health','7–8']]`.
- [ ] **Step 2: Update `HTML`, `CSS`, and `rTrend()` in `build_observe.py`**
  - Keep a single `<section class="card" data-view="obs" data-tab="trend">` in `HTML` and renumber `now` (`2–3`), `prs` (`4–5`), `release` (`6`), `ci` (`7–8`).
  - Add `failOrderCard(cur)` which builds a `.rp-card` with a crisp horizontal bar SVG (`failOrderChart`) showing the top 8 failing test cases/workloads ordered highest → lowest, with `.rp-hbar` bars and hover tooltips.
  - Simplify `rTrend()` to render the period bar (`Daily` / `Weekly` / `Monthly`) and the single 8-card `.rp-grid` (4 Core metrics including `Test Case Failed Order` right after `Successful CI Runs`, followed by the 4 Repo/Release metrics).
- [ ] **Step 3: Sync `i18n_vi.py` translations for renumbered section headers**
- [ ] **Step 4: Rebuild and run `verify_page.py`**
  - Run: `python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/build_page.py ; python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/verify_page.py`
  - Expected: `RESULT: PASS` (`JS errors: none`, `rpCards: 8`, `rpHbars: 8`, `rpClutter: 0`, `untranslated in VI: 0`).

### Task 3: Deploy Updated `06_PR_TO_CI_VISUAL.html` to `fork/gh-pages`

**Files:**
- Modify: `index.html` on `fork/gh-pages` (`https://github.com/travisVux/LMCache.git`)

- [ ] **Step 1: Update `index.html` in temporary `gh-pages` worktree, commit, and push to `fork`**
  - Verify `git log -n 1 fork/gh-pages` shows the new commit.
