# PR Inspector, tab merge, knowledge base, research intake (2026-11-24)

Goal: a reviewer decides on a PR faster, with less code reading, and what is learned from each PR is kept for
later bug / error analysis. Everything runs on local data; the page makes no live API call.

## Tab merge (approved table, 28 → 23 tabs)

| View | Before | After |
|---|---|---|
| Release Management | 8 | 7: Now, History, Releases & trace, Next release, CI cost (CPU / GPU switch), Rebase risk, Research intake (new) |
| Release Exploration | 12 | 8: Gates 2 · CPU: Overview, Coverage & explorer, Cost & findings · GPU: Overview & findings, Workloads & cost, Mindmap |
| Report 1130 | 8 | 8 (unchanged) |

Sections keep their own `data-view` / `data-tab` / `data-ops`; the nav groups old tabs into a merged tab
(`MEMBERS` in `build_nav.py`). Every old hash still opens (`ALIAS` + `SUBT` scrolls to the old section or picks the
CPU / GPU half). Per-PR detail lives in the Inspector only: 6A shows "N shared files · Inspect", Today links to the
ready-for-'full' queue on Rebase risk, 3F links the open decisions to Now · Release Desk.

## PR Inspector

| How to open | What opens |
|---|---|
| Any PR number link (`data-ent="pr:N"`), `#e/pr/N` | Inspector of PR N (forward, view 1) |
| 6A "Inspect" button, a PR in 6A | view 5 (semantic conflict) |
| A feature chip in a row that names one PR (PR.feature) | view 1, that feature highlighted |
| "Start from a failure" buttons, `piOpen('bug:<sig>')`, `piOpen('reg:<i>')` | backward: failure → builds → PR, commit, feature, logic |

| Part | Content |
|---|---|
| Forward flow | modules → code areas → features (draft F map) → CI gates (● required, ◐ conditional, ○ advisory, check state) |
| 5 views | 1 feature.internal · 2 among features · 3 flaky & non-deterministic · 4 race & concurrency · 5 semantic conflict |
| Each view | findings (each with evidence: file:line, test, CI run, PR) or an explicit **unknown** with the reason · reviewer checklist · CI gates that cover it (required / conditional / at risk / advisory) |
| Backward | builds of the PR, failure signatures, fixes, dev regressions whose commit range contains the PR (approximate when ops.db has no commit), retries |
| Phase B | "Animate impact" (off by default, Pause): step highlight of the flow; click a chip = its whole path. Sequence diagram for new.CI PRs (pipeline steps, `if:` conditions, edited steps ✎) and for multi-stage cache journeys; click a step = payload, condition, code location. Under 600 px: cards |
| Phase C | "RFC / FRS" button: RFC of the PR, FRS of its code areas, versions, open proposals with diff |
| Phase D | "Research" button when a research report names the PR |

### Data (local only)

| Source | Used for |
|---|---|
| `entities.json` | PR state, author, sha, releases, areas, edited tests, builds, failure signatures, fixes |
| `overlap_patches.json` | files, hunks, functions of 100 open PRs |
| `third_party/LMCache` clone | diffs of merged PRs (`git show`, cached by sha), static scan at HEAD (locks, threads, asyncio, CUDA streams; sleep, clock, random, ports), pipeline files, dev regression ranges |
| `ops_tabs.json` | 24 h overlap with merges, review queue gate states, known flaky workloads, critical path and F01–F17 |
| `gates.py` | tiers, change classes, which job runs a tier today |
| `P1*/retry_events_30d.csv`, `ops-app/data/ops.db` | retries; dev builds for regressions (read-only) |

Known limits (shown as "unknown" or noted on the page): the F map is a draft (`next_release.py AREA_F`); 457 PRs
have no local file list; the PR snapshot is from the observe snapshot date; the static scan reads files at the clone
HEAD, not at the PR head; there is no list of invariants and no import graph yet.

## Files

| File | Role |
|---|---|
| `outputs/cpu_tests/build_pr_inspector.py` | data (`pr_inspector.json`, `piData`), runs `kb.py`, injects the UI |
| `outputs/cpu_tests/pr_inspector_ui.py` / `pr_inspector_seq.py` / `pr_inspector_kb.py` | drawer + 5 views / animation + sequence diagrams / RFC-FRS panel (plain JS + JSDoc, `pi-` classes) |
| `outputs/cpu_tests/ci_seq.py` | Buildkite / GitHub Actions pipeline → ordered steps (stdlib, no YAML package) |
| `outputs/cpu_tests/build_research.py`, `research_intake/` | research intake loader, contract, validator, samples |
| `ops-app/backend/kb.py`, `schema.sql` (`kb_*`), `docs/ERD.md` | living knowledge base |

All run inside the normal chain (`build_page.py` → `verify_page.py` → `build_today.py` → `export_static.py`).

## Checks

| Check | Command (in `outputs/cpu_tests/` unless noted) |
|---|---|
| Whole page | `python -I -X utf8 verify_page.py` |
| Old hashes | `python -I -X utf8 check_redirects.py` |
| No fact lost in the merge | `python -I -X utf8 prove_facts.py --old <page before the merge>` |
| Inspector + phase B | `python -I -X utf8 check_inspector.py [PR ...]` |
| Knowledge base | `python -X utf8 ops-app/tests/check_kb.py` |
| Research intake | `python -X utf8 research_intake/check_intake.py` |
| Phone width, themes | `python -X utf8 check_mobile.py --theme light` and `--theme dark` |
| Shell views | `python -X utf8 ops-app/tests/check_app.py --lang en` and `--lang vi` |
