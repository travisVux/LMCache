> **Bắt đầu ở đây:** [HUONG_DAN_VAN_HANH.md](HUONG_DAN_VAN_HANH.md) — hướng dẫn vận hành end-to-end (tiếng Việt).

# CPU test map — generator for section 9 of 06_PR_TO_CI_VISUAL.html

Source: GitHub Actions `Test` run 42189301949, job `test: 3.12` (PR commit 05d8eb84, 2026-11-06).

Rebuild with a newer run:

```bash
# 1. log of one CPU test job (strip ANSI codes)
gh api --allow-escape-sequences repos/LMCache/LMCache/actions/jobs/<JOB_ID>/logs | sed 's/\x1b\[[0-9;]*m//g' > job312.log
# 2. test sources of the same commit
git -C third_party/LMCache fetch origin <SHA> && git -C third_party/LMCache archive <SHA> tests examples | tar -x -C src
# 3. parse + inject (idempotent, replaces the CPU-TESTS marker blocks)
LMCACHE_SRC=<path-to-src> python -I parse.py && python -I build_page.py   # build_page also runs build_nav
```

| File | Role |
|---|---|
| parse.py | log + sources → cpu_tests.json (per file: pass/skip/time, tests, docstrings, setup tags) |
| areas.py | path → feature area rules (first match wins) |
| area_meta.py | what / why / setup / main code per area (hand-written) |
| build_page.py | writes section 9 into the HTML page (PAGE path at top), then calls build_nav |
| section9_html.py | CPU view template (sections 1–9), compact CSS, fail-fast finding cards, timeline JS |
| fix_gpu.py | one-time fixes for the GPU view (review F1–F19, renumber 1–9, shorter text); safe to re-run |
| REVIEW_ponytail.md | independent review; fixes applied 2026-11-06 |
| i18n_vi.py | EN → VI dictionary (626 strings) + regex rules for strings with numbers. Add a key here when you add page text |
| build_i18n.py | EN / VI switch (key `L`), translation engine, mindmap label hook; called at the end of build_page |
| verify_page.py | Chrome headless check: JS errors, tabs, widgets, untranslated VI text; `--shots DIR` for screenshots |
| **gates.py** | **Single source** for gates (jobs), tiers L0→Full, change classes → tiers, feature area → class, E2E workload matrix, section descriptions (EN/VI). Change gates/tiers HERE only |
| build_gates.py | Builds the 3-view layout from gates.py: Gates view, impact lookup, workload matrix, descriptions; rewires staircase / class matrix / mindmap to gates.py; keeps DOM order stable |
| build_nav.py | GPU / CPU view switch + sub-tabs (tags each section with data-view/data-tab; URL hash `#cpu/explore`) |
| **build_observe.py** | **PR / Release watch** view (`#obs/now`, `#obs/prs`, `#obs/release`, `#obs/ci`; key `O`). `CONFIG` = repo, workflows, gate check-name patterns, pipelines, alert thresholds, PR GraphQL query. Page JS refreshes live from GitHub + Buildkite (Refresh / key `R` / auto 1–15 min; optional tokens kept in the viewer's browser) |
| observe_collect.py | Runs the same requests with `gh` + Buildkite token → `observe_snapshot.json` (embedded, so the page works offline), then rebuilds the page. `python -I -X utf8 observe_collect.py` |
| report_collect.py | **PR / Release report** data, 60 days: merged / opened PRs, releases, publish.yml + nightly runs, Buildkite dev builds, k3-unit PR builds with GPU wait (10 per page, cached in `report_cache/`; Buildkite resets big pages) → `report_data.json`. ~1 h first run |
| report_model.py | `report_data.json` + P1 MP baseline → per-day counts and value lists, embedded in the page; the Report tab (`#obs/trend`) groups them by day / week / month. Metric definitions live in build_observe.py (`MET`) |
| observe_history.py | `add_point()` keeps one snapshot summary per day in `observe_history/<day>.json` (for later); `--baseline` → `observe_history/baseline_mp.json` from ../P1 (30 d MP GPU cost) |
| k3_durations.py | Time per test from k3-unit-tests line timestamps, split CPU-portable vs k3-only → `k3_durations.json` (2026-11-07: 12.5 of 23.9 min is CPU-portable) |
| fastfail_savings.py | Real fast-fail saving: MP GPU-min after the first failed GHA Test / Code Quality / k3 unit per commit → `fastfail_savings.json` (2026-11-07: 188 GPU-h = 6.1% of 3,099; caches `ff_cache_*.json`) |

Page layout: CPU view first, then GPU. Each view numbers its sections 1–9 and has the same tabs: Overview · Tiers & coverage · Cost & time · Findings · Explore (deep links `#cpu/tiers`, `#gpu/explore`).

Language: EN / VI switch in the nav bar (remembered; default = browser language). File paths, code, test names and test docstrings stay in English.

Layout (2026-11-07): 4 views — **Gates & tiers** (shared, `#gates/...`), **Unit tests** (`#cpu/...`), **E2E workloads** (`#gpu/...`), **PR / Release watch** (`#obs/...`, live data). Build chain: build_page → build_nav → build_gates → build_observe → build_i18n. Rebuilds are byte-stable.
