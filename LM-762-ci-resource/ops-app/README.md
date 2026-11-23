# ops-app — LMCache Release Desk

> **2026-11-15 (latest): the main UI is the page `plan-2026-11/06_PR_TO_CI_VISUAL.html`** with its 3 views. Its Release Management view now has the tabs *Now · Release Desk* (`#obs/today`) and *History* (`#obs/hist`), drawn by `build_desk.py` from this backend's `release_desk.json`. `server.py` serves that page at `/` (and `dist/index.html` is that page). The single-bar shell below is optional, at `/shell.html`. Checked 2026-11-15 against the live GitHub Pages copy: Release Exploration (23 sections + data) and Report 1130 (8 sections; data differs only in build time) are identical; only Release Management changed.

The unified Release Desk: one navigation for **every** view. Native views (`#now`, `#history`) come from the SQLite history store; every view of the existing page `plan-2026-11/06_PR_TO_CI_VISUAL.html` runs unchanged inside it (embed mode: only its own title and tab bar are hidden; language, theme, "Descriptions" and "Show all sections" are driven from the shell). Nothing is removed: the page also still works on its own.

| Group | Hash | View | Source |
|---|---|---|---|
| Release management | `#now` (landing) | Where we are, $GOOD, decisions + evidence, blockers (owner, copy `gh run rerun` / `gh pr view`), ready-for-'full' queue, artifact matrix, dev gates + LKG, release history | ops.db |
| | `#history` | KPI cards, nightly, publish per week, dev pass rate, release cycle, failing jobs | ops.db |
| | `#today` | Today inbox (Go/No-Go strip, verbs, stale chips) | page `#obs/today` |
| | `#releases` | Verdict per release + registry line + artifact matrix, publish.yml, nightly | page `#obs/release` |
| | `#trace` | Release → PR → failed check → fix, Trace Agent | page `#obs/trace` |
| | `#coming` | Next release cockpit | page `#obs/coming` |
| | `#ci-cost/cpu`, `#ci-cost/gpu` | CI cost | page `#obs/opt_cpu`, `#obs/opt_gpu` |
| | `#rebase-risk` | Ready-for-'full' queue (approved first, owner, copy cmd) + overlap pairs + rebase list | page `#obs/overlap` |
| Explore & baseline | `#gates/guide`, `#gates/tiers` | Quality gates | page `#gates/*` |
| | `#tests/cpu-…`, `#tests/gpu-…` (10) | CPU / GPU test explorer, workloads, mindmap | page `#cpu/*`, `#gpu/*` |
| | `#r1130/…` (8) | Report 1130 | page `#r1130/*` |

Header: data-age badge per source (ops.db, observe_snapshot.json, ops_ci_24h.json, Trace Agent, report1130.json, RELEASE_PREP.md); older than 48 h = `STALE`, and the rows that use that source carry a `STALE (Nd)` chip.

| | |
|---|---|
| Ticket / mission | LM-762 (M5), M4 release control, M6 history |
| Status (2026-11-15) | 🟡 Phase 1 runs locally: release view + trends. Not published |
| Stack | Python 3.13 stdlib only (`sqlite3`, `http.server`), plain HTML/JS. No `pip install` |

## Run

```bash
cd LM-762-ci-resource/ops-app/backend
python -X utf8 ingest_files.py      # backfill from the page's JSON files (offline)
python -X utf8 collect_release.py   # GitHub + PyPI + Docker Hub (network)
python -X utf8 collect_weekly.py    # Buildkite: weekly full-suite builds (WEEKLY_FULL=true) + reference #6196 → weekly_run
python -X utf8 server.py            # http://127.0.0.1:8765/  (also serves /legacy.html and the page's outputs/ links)
python -X utf8 export_static.py     # dist/: shell + api/*.json + legacy.html + linked outputs/ files (serve over http)
cd .. && python -X utf8 tests/check_app.py [--lang en]   # every hash: console errors at 1280 px, overflow at a real 390 px
```

Rebuild the page first when its data changed (`plan-2026-11/outputs/cpu_tests/build_page.py`, then `verify_page.py`); `build_today.py` refreshes `release_desk.json` from ops.db.

## Folders

| Path | What |
|---|---|
| `backend/schema.sql` | Tables and analysis views. Model explained in [`docs/ERD.md`](docs/ERD.md) |
| `backend/config.py` | Paths, repo, workflow ids, **what each release should ship** (`ARTIFACT_SPECS`), dev gate pipelines |
| `backend/ingest_files.py` | Reads `observe_snapshot.json`, `report_cache/`, `observe_history/`, `ops_hist/`, `entities.json`, `today.json`, `release-<line>/RELEASE_PREP.md` |
| `backend/collect_release.py` | Release facts: all tags, publish runs + jobs + first error line, PyPI versions, Docker Hub tags → `artifact` |
| `backend/collect_weekly.py` | Weekly full suite: `k3-multiprocess-test` builds with meta-data `weekly-full=true`, their `weekly-verdict` → `weekly_run`. Shown as section 4 of *Now · Release Desk* and a strip in *History* |
| `backend/model.py` | Verdicts, decision hints, blockers, history. All page logic is here, not in the JS |
| `backend/server.py` | `GET /api/overview`, `/api/history`, `/api/release/<tag>`, `/api/sql?view=v_…` |
| `backend/legacy.py` | The existing page in embed mode + its relative `outputs/` files |
| `frontend/` | `index.html`, `app.js`, `style.css`: shell, nav, native views, page sync. EN / VI, light / dark |
| `tests/check_app.py` | Console + phone-width check of every view |
| `data/ops.db` | The database (created on first run) |

## Page: what is on it, top to bottom

| # | Section | Answers |
|---|---|---|
| 0 | Where we are | Stable that users have, latest tag, phase, open decisions, blocker count |
| 1 | Decide | D1–D4 from the prep doc, plus ⚑ evidence when facts show a decision was made in practice |
| 2 | Blocking the next RC | Publish job errors (with the first error line), missing artifacts, dev gate red, open bugs, carry-over C1–C6 (with facts, e.g. C2 = wrong CLI version on PyPI) |
| 3 | What users actually got | Artifact matrix from registries: ✓ correct, ! present but wrong, ✗ missing, — not expected |
| 4 | dev gate pipelines | Last 10 dev builds per gate pipeline |
| 5 | Release history | Verdict per tag, publish runs, bugs found later; click for PRs, changed areas, verdict history |
| Trends | | KPI cards (definition, value, change), nightly streak, publish per week, dev pass rate heat strip, release cycle, jobs that fail most |

## Verdict words (fixes the old "SHIP KÈM LỖI" label)

| Verdict | Meaning |
|---|---|
| Shipped | every expected artifact is present and correct |
| Missing artifacts | some expected artifacts are missing or wrong |
| Not shipped | nothing expected was found |
| Publishing | a publish run is still running |
| Not checked | registries were never checked for this tag |

The publish run result is shown next to the verdict, not mixed into it.

## Next

| Step | What |
|---|---|
| P2 | Model tests, fail signatures and sprints (see ERD "Not modeled yet") |
| P3 | Write decisions back: a "decided" choice in the page → `RELEASE_PREP.md` row |
| P4 | Move more page inputs (trends, flaky signatures) to `release_desk.json`; never remove a page tab |
| P5 | Publish the static copy to GitHub Pages (only after the user says yes) |
