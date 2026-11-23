# 5-Stage Animated Release → PR → Test Case → Error Log Tracer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive 5-Stage Left-to-Right Animated Tracer (`Release/RC Tag ══► PRs (#) ══► Critical Stage & Files ══► CPU/GPU Test Cases ══► Error Log Terminal & Daily Report Fix`) inside `06_PR_TO_CI_VISUAL.html` (local update first), powered by real git commit/PR/test mappings from `third_party/LMCache` and curated Buildkite/GHA failure logs.

**Architecture:**
- `outputs/cpu_tests/report_model.py`:
  - Add `build_release_trace()` which queries `third_party/LMCache` git history across `v0.5.6..v0.5.7rc1`, `v0.5.7rc1..v0.5.7rc2`, `v0.5.7rc2..v0.5.7rc3`, `v0.5.7rc3..v0.5.7rc4`, `v0.5.7rc4..v0.5.7`, and `v0.5.7..dev`.
  - Maps each PR's modified files via `areas.classify()` to its feature areas, CPU test files (`tests/...`), and GPU E2E suites, and attaches rich critical-path flow definitions + real error log/stacktrace excerpts (`k3-blend-test #4348`, `publish.yml rc1 Errno 122 & asset collision`, `R-3 setuptools_scm dirty version`, `rc3 Kafka consumer offset`, `rc4 P2P teardown & amd-mp-test #1257 memcheck race`, `cu129 torch 2.14 resolver`).
- `outputs/cpu_tests/build_observe.py` & `i18n_vi.py`:
  - Add `<div id="obsTracer"></div>` inside `<section class="card" data-view="obs" data-tab="release">` right below `#obsTrain`.
  - Render the 5-stage horizontal animated pipeline (`.tr-pipe` with 5 `.tr-stage` columns connected by animated SVG/CSS beam arrows `.tr-beam`, pulsing left-to-right whenever a tag, PR, or test case is clicked).
  - Connect `#obsTrain` tag pills and `#obs/trend` chart bars (`#rp-fail_order`, `#rp-rel_ship`) so clicking a tag or failing test jumps straight to `#obsTracer` and highlights that exact trace.

**Tech Stack:** Python 3 (`report_model.py`, `build_page.py`, `verify_page.py`), Vanilla JS + CSS keyframe flow animations inside standalone HTML.

---

### Task 1: Add Tracer Widget Assertions to `verify_page.py` (TDD Red Step)

**Files:**
- Modify: `LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/verify_page.py`

- [x] **Step 1: Add `traceStages`, `tracePRs`, and `traceLog` checks to `verify_page.py`**
  - Assert `traceStages: document.querySelectorAll('#obsTracer .tr-stage').length` (`== 5`).
  - Assert `tracePRs: document.querySelectorAll('#obsTracer .tr-pr').length` (`> 0`).
  - Assert `traceLog: document.querySelectorAll('#obsTracer .tr-term').length` (`> 0`).
- [x] **Step 2: Run `verify_page.py` and confirm it fails (Red)**

### Task 2: Build `release_trace` Data Model in `report_model.py`

**Files:**
- Modify: `LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/report_model.py`

- [x] **Step 1: Implement `build_release_trace()` in `report_model.py`**
  - Extract real PRs (`num`, `sha`, `title`, `author`, `date`, `files`, `tests`, `areas`) per release range (`v0.5.7rc1`, `v0.5.7rc2`, `v0.5.7rc3`, `v0.5.7rc4`, `v0.5.7`, `dev`) from `third_party/LMCache` (with fallback if git repo is absent).
  - Attach critical-path 4-step flow sequences (`flow`), CPU & GPU test case gates (`gates`), and multi-line real error log / stacktrace blocks (`logs`) + root-cause & fix summary (`why`, `fix`, `repro`).
- [x] **Step 2: Run `report_model.py` and verify `report_data.json` contains `release_trace`**

### Task 3: Render 5-Stage Animated Tracer in `build_observe.py` & Verify Local HTML

**Files:**
- Modify: `LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/build_observe.py`
- Modify: `LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/i18n_vi.py`

- [x] **Step 1: Add `#obsTracer` container, CSS left-to-right beam animations, and `rTracer()` in `build_observe.py`**
- [x] **Step 2: Wire deep-links from `#obsTrain` tags and `#obs/trend` (`#rp-fail_order` bars) to `openTrace(tag, prNum)`**
- [x] **Step 3: Update `i18n_vi.py` and run `build_page.py` + `verify_page.py`**
  - Expected: `RESULT: PASS` (`JS errors: none`, `traceStages: 5`, `rpClutter: 0`, `untranslated in VI: 0`).
