# Review: Release & CI Ops (`#obs/*`), 2026-11-09

- **Target:** all 9 tabs (Monitor: now, release, prs, ci · Trace: trace, flaky, gpuload, bug · Report: trend)
- **Mode:** `critique` (nothing changed). The `{{TARGET}}` / `{{MODE}}` placeholders were not filled, so `all` + `critique` were used.
- **Path:** two isolated sub-agents (A = UX/release, B = data-viz/implementation), then merged here. No degraded mode.
- **Not run:** paid agents (`trace_agent_*`). VI screenshots were taken but A reviewed EN only. Failure states (token, GitHub, Buildkite errors) not exercised. Real 390 px layout not measurable in headless Chrome (min window 500 px).
- **Raw reports:** `scratchpad\assessment_A.md`, `scratchpad\assessment_B.md` (under `<home>\AppData\Local\Temp\claude\82ff7c0a8b56703b\90270ac7-e622-45a3-bd4e-0f9ca5806f45\scratchpad\`)
- **Screenshots** (`<lang>_<tab>_<width>_<fold|full>.png`, tabs now, release, prs, ci, trace, flaky, gpuload, bug, trend), all in `<home>\AppData\Local\Temp\claude\82ff7c0a8b56703b\90270ac7-e622-45a3-bd4e-0f9ca5806f45\scratchpad\shots\`:
  - EN/VI 1280 fold + full, e.g. `...\shots\en_now_1280_fold.png`, `...\shots\vi_trend_1280_full.png`
  - EN 390 full, e.g. `...\shots\en_now_390_full.png`
- `verify_page.py`: **RESULT: PASS** (JS errors none, untranslated in VI: 0). It checks structure and i18n only, not numbers, data age, axes, partial periods or contrast.

## Health score: 34 / 56

| Heuristic (A) | Score | | Technical (B) | Score |
|---|---|---|---|---|
| Visibility of status | 2 | | Accessibility | 2 |
| Match real world | 3 | | Responsive | 3 |
| User control | 3 | | Theming | 3 |
| Consistency | 2 | | Performance | 3 |
| Error prevention | 3 | | | |
| Recognition vs recall | 2 | | | |
| Flexibility | 2 | | | |
| Minimalist design | 2 | | | |
| Error recovery | 2 | | | |
| Help | 2 | | | |
| **Sum** | **23 / 40** | | **Sum** | **11 / 16** |

## What works (keep)

1. Snapshot bar on every tab: age, lamp, API budget, source pills, plus the "Data is 21.7 h old" alert.
2. Trace flow ends in fix, fix PR, confidence and "blocks release". It is the only tab that gives a cause.
3. Flaky/GPU KPI cards carry definition, direction and source; lever chips separate spent / measured / not measured and never sum them. Trend cards have delta, better/worse, n, p90, partial-period tooltip.
4. Release tag chain with X marks and rc1→stable days. Status colours always have a text label.
5. Numbers traced to source match: 696/217/26/14 (`gh.counts`), 4,091 GPU-h, 28% waste, 297/480 flaky. Tab keyboard (← →), focus rings, tokens dominate (197 `var(--)` vs 9 hard-coded), polling pauses when hidden.

## Reader questions (A)

| # | Time | Where answered | What blocked |
|---|---|---|---|
| R1 shippable? | 3–5 min, 3 tabs | now → release → trace | No verdict word. `publish.yml` red is unexplained; trace explains a different failure |
| R2 real vs noise | 2–3 min, partial | trace, flaky | "11 failing · 1 proposed" does not say which are noise |
| R3 cause+fix+PR | 1–2 min for ONE PR | trace inspector | Only 1 of 12 PRs has a proposal; log excerpt hand-entered (`build_observe.py:1226`) |
| R4 do today | **not answerable** | bottom of trace tab only | No ordered to-do |
| R5 dev health / queue | ~1 min | ci | Data 22 h old |
| R6 biggest saving | ~1 min + scroll | gpuload | Top lever "already spent 801 GPU-h" is not a saving; real top is fail-fast 188 (an estimate) |
| R7 week vs week | 1 min "what", no "why" | trend | Defaults to W44 (see P1-5) |

## Priority issues

**P0: none proven.** A proposed three; I checked them in source and downgraded:
- "Report defaults to W44": by design it picks the last *full* week (`build_observe.py:954`). The real problem is that no data age is shown (P1-4).
- "Ages use `Date.now()`": `ago(finished_at)` against the clock is the true event age. Not wrong data. The snapshot-stale alert already warns (`:421`, `:635`).
- "2/2 gates green uses latest run only": a labelled design choice ("dev CI green"), not a data error. Kept as P2-1 because it can mislead.

### P1: R1–R4 not answerable in under 1 minute

1. **No go/no-go line for the newest release.** Evidence: `en_now_1280_fold.png` (8 tiles, no verdict). Hurts R1. Fix: one verdict banner (shippable / blocked by X) above the tiles. File: `build_observe.py` `rTiles` / `rAlerts` (~543–550).
2. **`publish.yml` failure not explained or linked to the trace.** Tile says `publish.yml: fail` only. Hurts R1, R3. Fix: link the failed job and its trace stream from the tile and alert. File: `build_observe.py` (`rTiles`).
3. **No ordered to-do.** The "next rc must include #6266 or cherry-pick" action is only at the bottom of tab 8 (`en_trace_1280_full.png`). Hurts R4. Fix: "Today" list with order, owner and link. File: `build_observe.py:543-550`.
4. **Pill age is wrong for several tabs.** Pill says "22 h ago" on all tabs. Flaky/gpuload data window ends 11-04 (5 d older); trace agent ran 11-09 10:22 (~11 h); trend data ends 11-07 with no age shown. Hurts R5, R7. Fix: per-tab "Data window · made <age>" strip. Files: `build_observe.py` renderBar (~600), `build_trace_dirs.py`.
5. **Trend default week hides how old the report is** (W44 = 10-26..11-01, data end 11-07). Fix: show the week range and "report ends 11-07" in the card header. File: `build_observe.py:954`.
6. **Fix proposals buried; only 1 of 12 PRs has one.** Hurts R3. Fix: per-failure table (PR, cause, fix PR, confidence, agent status). File: `build_observe.py` trace section.
7. **"Measured saving 188.4 GPU-h" for fast-fail is an estimate** (B: `trace_dirs_model.py` ~205–215; the footer admits it). Hurts R6. Fix: chip text "estimated". File: `build_trace_dirs.py` lever chips.
8. **Hand-entered data mixed with live data** (`build_observe.py:1220, 1226`), flagged only by a small warning. Fix: a visible "manual" badge per row.

### P2: friction, inconsistency, missing states

1. "Dev CI green" tile uses latest run per pipeline; k3-multiprocess-test is a MERGE GATE with 2/4 passes in the squares (`en_ci_1280_fold.png`). Add n of last runs.
2. Ready-to-merge "2/100" mixes the 100-PR sample with 696 open; chips sum to 99, header says 100 (`build_observe.py`, `gh.prs_gql`).
3. CI queue table titled "PR builds" includes non-PR builds (no filter at `build_observe.py:536-537`); "Build p50" is created→finished (`:537`), not started→finished (9.3 vs 12 min).
4. Two definitions of "wait for GPU agent" (19/57 min per GPU job, 30 d vs 4 s/29 min per build, last 20).
5. Waste 28% (GPU tab) vs 8% (Report); 8.0 vs 9.1–9.6 GPU-h/PR, no basis note (`build_trace_dirs.py:181`, `trace_dirs_model.py:235`). gpuload "617 PR builds" but p50 is over 263 passed builds.
6. Partial periods in Trend only dimmed, no visible label (`build_observe.py:872-884`); Release Cadence "+75 pts better" on n=2 tags, no low-n guard.
7. gpuload weekly "canceled+failed" is teal-green (`build_trace_dirs.py:190`) while result bars use red/grey: colour should follow the entity.
8. 136 last-10 squares are colour-only, grey undefined, no legend; tooltips are native `title` (mouse-only).
9. Accessibility: no `tabpanel` / `aria-controls`; contrast 3.3–3.6:1 on `.gch`, `.rp-d.bad` (dark), `.rp-d.good` (light) at 10–11 px.
10. 11 flaky/gpuload KPIs have no delta or "no period"; now/release/prs tiles lack definition, direction, source, n.
11. Mobile: right edge clipped (`en_now_390_full.png`, `en_trace_390_full.png`; B measured scrollWidth 489 at 504 px, so true 390 px not verified). Tracer SVG is 1061 px wide.
12. Alerts do not link to the matching trace (#1359 vs #1257); "Ready 2/100" shows green despite "1 blocked"; Releases tab dumps ~90 job tiles (`build_observe.py:712`); 15+ controls before content.
13. Empty Bug tab (7 "waiting" tiles) takes a primary slot.

### P3: polish

Missing legend for "opt" / "BOTTLENECK"; weak Refresh prompt; "Toggle dark / light" wraps to 2 lines; 9 hard-coded colours (`build_observe.py:370-378, 495, 1229`); 99 PR rows unvirtualised; ticket ids LM-1115/1062/762 untitled; jargon in the Trace Agent summary line and Flaky "258 / 39".

## Personas

- **Release owner on release day:** no go/no-go; the action is at the bottom of tab 8; 3 tabs to answer R1.
- **New engineer, day one:** no glossary or "start here"; ticket ids and gate names unexplained.
- **Manager on a phone:** clipped right edge, wide tables scroll in wrappers, trace flow needs horizontal scroll.

## Design specificity

Mixed. Release-specific: tag lanes, publish job grid, MERGE GATE strips, trace flow. Generic: KPI cards and the dark SaaS look; no blocker owners.

## Minor notes

The queue p50/p90 numbers for k3-unit (4 s) and k3-mp (29 min) recompute correctly. Freshness table is in P1-4.

## Fixes applied (`critique+fix`, 2026-11-09)

Scope: your "go ahead" on my suggestion. Defaults used for my open questions: verdict banner on `now`, Bug tab untouched. Generators only; HTML rebuilt with `build_page.py`.

| Issue | Change | File |
|---|---|---|
| P1-1, P1-2 | New verdict banner on `now`: BLOCKED / UNKNOWN / NO BLOCKER FOUND for the newest tag. Checks `publish.yml` of that tag + dev merge gates, lists each blocker with `open →` and `why? trace →`, and says what it does not check and how old the snapshot is. It never says "shippable". | `build_observe.py` (`rVerdict`, `.obs-verdict`) |
| P1-3 (partial) | "Needs attention" is now "Do next, most urgent first" with numbered items (already sorted crit → warn → info → ok). Still status lines, not verbs with owners. | `build_observe.py` `rAlerts` |
| P1-4, P1-5 | Flaky, GPU load and Report tabs show "data window ends X (N d ago), built Y; the Snapshot age does not cover this tab", in warning colour at 3+ days. Report also says it opens on the last full week and that dimmed bars are partial (P2-6). | `build_trace_dirs.py` (`fresh`), `build_observe.py` `rTrend` |
| P1-7 | Fast-fail lever chip is now "estimated saving (replay)" with a tooltip. Basis changed from `measured` to `estimated`: `fastfail_savings.py` replays real builds to ask how many GPU-h a cancel *would* save. | `trace_dirs_model.py`, `build_trace_dirs.py` |
| P2-1, P2-2 (partial) | Gate tile label says "latest run of each". "Ready to merge" tile is amber, not green, when any PR is blocked. | `build_observe.py` `rTiles` |

**Not done:** full to-do with owners (P1-3), per-failure proposal table (P1-6), manual-data badge (P1-8), P2-3 to P2-5, P2-7 to P2-13, all P3. They need design decisions or larger changes. The Trace tab (8) still has no age strip; its agent card shows its run time.

**After screenshots** are in `<home>\AppData\Local\Temp\claude\82ff7c0a8b56703b\90270ac7-e622-45a3-bd4e-0f9ca5806f45\scratchpad\after\`: `en_now_1280.png`, `en_flaky_1280.png`, `en_gpuload_1280.png`, `en_trend_1280.png`, `vi_now_1280.png`, `en_now_390.png`. I looked at `en_now_1280.png` and `en_flaky_1280.png`; the others were taken but not inspected.

**Evidence lost:** the scratchpad folder was deleted during the session (not by me). It held the "before" screenshots, `assessment_A.md`, `assessment_B.md` and my generator backups. The screenshot and assessment paths in the header above no longer exist, so there is no before/after pair and no backup of the generators. The before state is described in the findings.

**Re-timing (my estimate, not measured):** R1 goes from 3–5 min to about 10 s on `now` (verdict plus `why? trace →`). R4 improves only a little (order exists, no verbs or owners). R5 and R7 now show data age. R2, R3, R6 unchanged.

**verify_page.py: FAIL, not caused by my edits.** 8 untranslated VI strings (13 before my first edit). They are English agent text in the new trace-agent data, such as "Fast-fail: cancel MP build when lint/unit/GHA Test fails". Another session was editing `build_observe.py`, `build_trace_dirs.py` and the directions data while I worked (modified 21:47–21:49, line numbers shifted by about 110), so the rebuilt page includes their changes. JS errors: none.

## Batch 2 (2026-11-09, "more useful, easier to use")

| Issue | Change |
|---|---|
| P1-6, R2, R3 | New table on `now` under the verdict: **Failing PRs in the newest release: noise or real?** One row per PR with failing checks: failed checks, verdict (real / noise / not analysed, plus "blocks release"), what to do (Rerun / Fix the test / Revert...), fix PR link, agent confidence. Sorted real first. For v0.5.7: 8 of 12 PRs fail checks, 2 real (#5035, #6231, both already fixed by #6279), 6 noise. Data: `trace_agent/proposals.json`; redraws when the agent file updates. |
| P1-3 | Verdict now has a "→ do this" line per blocker (publish.yml failure, red merge gate). |
| P1-4 | Trace tab shows the age of the Trace Agent data (warning after 24 h). |
| P2-3 | Queue table heading now says PR and dev builds are mixed, last 20 per pipeline. |
| P2-7 | GPU weekly chart: waste series uses the warning colour, not a green-teal. |
| P2-8 | CI health tab has a legend for the squares (passed / failed / canceled / running). |
| i18n | 8 English-only agent strings added to `i18n_vi.py` (they come from `directions.json`; a new agent run with new text will need new entries or `[en, vi]` pairs). |
| mobile | Table hides the "Failed checks" column below 640 px (not verified at a real 390 px). |

Still open: P1-8 manual-data badge, P2-2/4/5/6 (mixed scopes and definitions), P2-9 ARIA tabpanel and contrast, P2-10 KPI deltas, P3. `verify_page.py`: **PASS**, JS errors none, untranslated VI 0.
The scratchpad was deleted a second time; the latest screenshots are in `...\scratchpadfter2\` if it still exists.

## Batch 3 (2026-11-09)

| Change | Where |
|---|---|
| Tab `#obs/now` renamed **Release verdict** (EN) / **Kết luận release** (VI); hash id unchanged. Section 1 is now "Release verdict: can we ship?", with the verdict, the failing-PR table, then the number tiles. | `build_nav.py`, `build_observe.py`, `i18n_vi.py` |
| **MANUAL / NHẬP TAY** chip on the tracer's hand-entered log excerpt and hand-entered gate list (was a small grey line). | `build_observe.py` |
| KPI deltas on Flaky and GPU load: flaky count, GPU-h and waste share show change vs the previous full week with better/worse text. KPIs with no weekly series now say "no previous period (30-day window)" instead of nothing. | `build_trace_dirs.py` (`wk`, `dl`) |
| Definitions aligned by text, not by changing numbers: waste (GPU tab 28% = all canceled/failed builds vs Report 8% = retry + cancel of PR builds), GPU per PR build (median of green builds vs total / merged PRs), wait (per GPU job over 30 d vs longest job wait per build, last 20). Each tab now says how it differs from the other. | `build_trace_dirs.py`, `build_observe.py` |
| "617 PR builds" under Green PR build time now says it is timed over passed builds only (the exact passed count is not in `directions.json`). | `build_trace_dirs.py` |

`verify_page.py`: PASS, JS errors none, untranslated VI 0. Screenshots (EN `now`, VI `now`, EN `flaky`, EN `gpuload`) in `...\scratchpadfter3\`; I looked at VI `now` and EN `gpuload`.

Still open: ARIA tabpanel and contrast (P2-9), "Ready 2/100" vs 99 vs 696 scope (P2-2), partial-week legend on Report bars, low-n guard on Release Cadence, P3. The numbers behind the two "waste" and two "wait" figures still differ; they are labelled, not merged.

## Batch 4 (2026-11-09)

| Change | Where |
|---|---|
| **ARIA tabs:** each tab button has an id and `aria-controls` (all 9 obs tabs); the sections of the open tab get `role="tabpanel"` + `aria-labelledby`. Checked in the rendered DOM: 2 tabpanels on `#obs/now`, 9 of 13 tab buttons with `aria-controls` (the other 4 are the view switcher, not tabs with panels). | `build_nav.py` |
| **Contrast:** new text-only tokens `--good-text`, `--crit-text`, `--muted-text` (light and dark), existing colour tokens untouched. Computed ratios: good 5.4 / 7.4, critical 6.0 / 5.9, muted 5.7 / 6.8 (light / dark); before: 3.27 (good light), 3.62 (critical dark). Used by delta chips, failed chips, KPI direction chip, measured chip. | `build_observe.py`, `build_trace_dirs.py` |
| **Low-n guard on Report deltas:** if either period has n < 3, the chip is grey and says "too few data points (n=…), not a trend" instead of better/worse (Release Cadence had "+75 pts better" on n=2). | `build_observe.py` `delta` |
| **"Ready to merge 2 / 100" scope:** sub-line now says "sample: the 99 latest updated of 696 open PRs". | `build_observe.py` |
| "Toggle dark / light" button no longer wraps to 2 lines. | `build_observe.py` CSS |
| Partial periods on Report: already covered by the warning strip from batch 1 (dimmed bars named as partial); no separate legend added. | |

`verify_page.py`: PASS, JS errors none, untranslated VI 0. Screenshots: `...\scratchpadfter4\en_trend_1280.png` (inspected), `en_now_1280.png` (not inspected).

Not done: real 390 px check, Report chart tooltips are mouse-only (`title`), the 136 squares are still colour-only for screen readers (legend added), unvirtualised 99-row PR table, P3 left-overs. Not verified: the dark/light contrast on the tracer's hard-coded terminal colours.

## Questions for you

1. Should the first tab be a new go/no-go "Release verdict" view, or a banner on top of `now`?
2. Should the Bug tab stay a main tab while it is empty (`#6530` upcoming), or move behind a "Soon" group?
3. Do you want me to run `critique+fix` next: P1-1 to P1-4 and P1-7 first (about half a day), then the P2s under 30 minutes?
