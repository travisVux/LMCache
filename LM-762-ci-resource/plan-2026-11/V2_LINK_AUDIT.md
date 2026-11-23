# V2 link audit (P0) — Release & CI page

Made 2026-11-13 from `06_PR_TO_CI_VISUAL.html` built 2026-11-12 23:52. No code or page change.

**How it was measured.** A temp copy of the page was opened in headless Chrome. For every visible tab the probe
counted words, id mentions (by regex on the rendered text) and links (by `href` / `onclick`).
Folded `<details>` were opened for the "all" counts. Clicks for the 3 reviewer tasks are **counted from the page
structure, not timed with a person**.

Level chain: `Release ⇄ PR ⇄ Feature ⇄ CI ⇄ Test ⇄ Bug`.

## 1. Summary

| Fact | Number |
|---|---|
| Sections visible / total | 51 / 62 (11 sit in retired hidden tabs) |
| Words visible / with folds open | 26,426 / 35,006 |
| PR mentions | 771 — 584 are links, **all to GitHub**, 0 open anything on the page |
| Feature mentions | 248 — 83 clickable (3 sections only) |
| Test file mentions | 173 — **0 are links** (60 rows in the Test explorer are the files themselves) |
| Pipeline / workflow mentions | 148 — 4 are links (Buildkite builds, Rebase risk) |
| Release tag mentions | 184 — 0 link to another tab (93 GitHub links in Releases) |
| Buildkite build links | 6 on the whole page |
| GitHub issue mentions | **0** — the Bug level does not exist as an id |
| Cross-tab links | 29 = 27 `opsOpenFeature` (Next release 3C) + 2 (`#gates/tiers` → `#cpu/explore`, `#gpu/tiers`) |
| Links **into** Release Management or Report 1130 from another view | 0 |

Three things stand out:

1. **PR is the only level with links, and every link leaves the page.** The same PR is shown in up to 6 sections with no way to jump between them.
2. **Test and CI are text only.** A reviewer cannot go from a PR or a feature to the test file or the build.
3. **Bug has no id.** Failures are shown as text ("performance threshold missed", Trace Agent prose). No issue number, no signature id on the page.

## 2. Release Management `#obs/…`

| Tab · section | Level | Ids shown (mentions) | Links today | Missing |
|---|---|---|---|---|
| release · 1A Releases | Release | tag 5, workflow 3 | 93 GitHub (release, run, job) | release → its PRs, features, tests |
| release · 1B Release health | Release, Bug | PR 14, tag 8, build 2 | 1 GitHub | PR text not linked; blocker → PR → fix PR; verdict chip |
| trace · 2A Release trace | Release → PR → CI | PR 22, tag 14, test 5, pipeline 8 | 1 PR, 2 Buildkite | 21 PR mentions plain text; test files; feature |
| trace · 2B Failing PRs not explained | PR | PR 12 | 12 GitHub PR | PR → failed build / log; decision |
| coming · 3A Release cockpit (1,155 words) | Release | PR 26 | 13 GitHub PR | 13 PRs plain text; decision → evidence section |
| coming · 3B Scope | Release → Feature | PR 25, feature 22 | 18 GitHub PR | feature chips not clickable |
| coming · 3C Critical path | Feature → PR | PR 84, feature 10 | 66 GitHub PR, 27 feature (`opsOpenFeature`) | feature → tests; PR → CI |
| coming · 3D Tests per feature | Feature → Test | PR 174, feature 27 | 110 GitHub PR, 28 feature rows | **no test file / workload link**; no last CI evidence link |
| coming · 3E rc cut point | Release → PR | PR 19, feature 17 | 17 GitHub PR | feature; shipped-in check |
| coming · 3F RC checklist | Release, CI | PR 7, pipeline 5 | 0 | everything |
| coming · 3G Release-note PRs (4,538 words) | Release → PR → Feature | PR 75, tag 133, feature 50 | 61 GitHub PR | feature; 14 PRs plain text |
| opt_cpu · 4A–4D | CI | workflow 12, PR 3 | **0** | workflow card; tests touched by each solution |
| opt_gpu · 5A–5D | CI | pipeline 25, PR 12 | 11 GitHub PR | pipeline card; workloads |
| overlap · 6A Rebase risk (1,800 / 5,360 words, 114 rows) | PR ⇄ PR | PR 238 (99 unique), 143 level / verb chips | 225 GitHub PR, 4 Buildkite | PR → required-check state; PR → feature; clash → diff hunk in 1 click |

View total: 20 sections, 14,195 visible words, 711 PR mentions, 6 Buildkite links, 0 test links.
`coming` alone is 9,551 visible words.

## 3. Report 1130 `#r1130/…`

| Tab | Level | Ids shown | Links today | Missing |
|---|---|---|---|---|
| baseline (GPU) | CI | pipeline 3, 52 rows | 0 | pipeline card |
| cpu | CI | workflow 1, 62 rows | 0 | workflow / job card |
| green | CI, PR | PR 2, pipeline 7 | 0 | PR, pipeline |
| retry | CI → Bug | pipeline 18, failure text (37 rows) | 0 | **signature id, build, workload, log line** |
| prs (Per PR) | PR | PR 50 | 50 GitHub PR | PR → builds; commit SHA → build |
| track | CI | — | 0 | — |
| repro | — | script names | 0 | — |
| quality | Data | pipeline 8 | 0 | link-health block (planned in 5.6) |

View total: 8 sections, 4,361 visible words, 50 links (all GitHub PR). This view is fully isolated.

## 4. Release Exploration `#gates/…` `#cpu/…` `#gpu/…`

| Tab · section | Level | Ids shown | Links today | Missing |
|---|---|---|---|---|
| gates/guide · 0a, 0b, 1 | Feature, CI | feature 31, pipeline 12 | 0 real | feature → tests, PRs |
| gates/tiers · 2–4 | Test tier | test 2 | 0 | — |
| gates/tiers · 5 Change impact | Feature → Test | feature 27 | 2 cross (`#cpu/explore`, `#gpu/tiers`) | feature → open PRs |
| cpu/overview · 1, 2 | CI, Test | PR 3 | 0 | — |
| cpu/tiers · 3 Feature matrix | Feature → Test | 28 area rows, 568 test names | 568 `<a>` with no `href` (in-tab expand) | test → explorer; feature → PRs |
| cpu/tiers · 4, 5 | Test | feature 27, test 68 | 0 | test file link |
| cpu/cost, cpu/findings | CI | pipeline 9 | 0 | pipeline |
| cpu/explore · 8 Test explorer | Test | test file 95 (69 unique), feature 27 | 60 file rows (`data-path`) | pipelines that run it, 30-day result, PRs, bugs |
| gpu/overview, gpu/cost, gpu/findings | CI | — | 0 | pipeline, builds |
| gpu/tiers · 3 Workload matrix | Test (GPU) | 18 workloads | 0 | workload → job, fail %, PRs, bugs |
| gpu/explore · 8 Mindmap | all | pipeline 8 | 0 (in-map only) | — |

View total: 23 sections, 7,870 visible words, 2 cross-tab links, 0 external links, 0 PR links.

## 5. The 3 reviewer tasks today

| Task | Path today | Clicks to evidence | Words on the way | Leaves the page? |
|---|---|---|---|---|
| **Merge decision** — "can I merge PR X now?" | `#obs/overlap` → find the PR row → GitHub PR → Checks → job log | 3–4 | about 1,800 (the tab) | yes, at click 1. Required-check state and approval are **not** on any visible tab |
| **Release readiness** — "is feature F of v0.5.8 tested?" | `#obs/coming` → 3D row → (no link) → switch view to `#cpu/explore` → search the feature → open file | 4+ | about 9,500 (the tab) + 700 | no link to the last CI run at all; GPU evidence needs Buildkite by hand |
| **Red-dev triage** — "is this red new, real or flaky?" | No visible tab lists red dev runs. `#obs/overlap` merge row chip → GitHub PR → commit checks → Buildkite → log; then `#r1130/retry` by eye to compare the failure text | 4–5 | about 1,800 + 920 | yes. Flaky check is a manual text match |

Target for v2: ≤ 2 clicks, decision row ≤ 8 words, first click stays on the page.

## 6. Top 10 missing links (ranked by how often a reviewer needs them)

| # | Missing link | Needed for | Where it bites | Data already local? |
|---|---|---|---|---|
| 1 | PR → required checks + approval state (card on the page) | merge, every PR, every day | overlap, r1130/prs, coming | yes: snapshot `prs_gql`, `bk` |
| 2 | PR → its CI builds / failed job → log line | merge, triage | overlap, trace 2B, r1130/prs | partly: `ops_ci_24h.json`, `P1/jobs_all_30d.csv`; log lines only where parsed |
| 3 | Same PR across tabs (one PR card with "Seen in") | all | 771 mentions, 99 unique PRs in overlap alone | yes |
| 4 | Failure → signature id → other builds with the same failure (real or flaky?) | triage | r1130/retry, trace | yes: `P1/raw/fail_signatures.json` (not embedded as ids) |
| 5 | Feature → required tests → last evidence run | release readiness | coming 3D, gates/tiers 5 | tests yes (`cpu_tests.json`, `gates.CLASSES`); evidence partly (see `v058-dev-mp-evidence-gap`) |
| 6 | PR → feature, clickable everywhere (today only 3 sections) | merge, release scope | overlap, 3B, 3E, 3G, r1130/prs | yes: `pr_files` × `SRC_AREA` |
| 7 | Clash chip (P0/P1/P2) → the diff hunk in 1 click | rebase decision | overlap | yes: `overlap_patches.json` (folded today) |
| 8 | Release → PRs → features → open blockers, with a verdict chip | release owner, weekly | release 1A / 1B, trace 2A | yes: `release_trace`, git tag range |
| 9 | Test file / GPU workload → pipelines that run it, 30-day fail % and flaky % | CI owner, quarantine decision | cpu/explore, gpu/tiers | GPU yes (P1 CSVs); CPU per-file only where logs were parsed |
| 10 | Pipeline / workflow → cost row → tests it runs | CI owner | opt_cpu, opt_gpu, r1130 baseline (0 links in 16 sections) | yes |

Not ranked, but a blocker for the Bug level: **GitHub issues are not on the page at all** (0 mentions).
Checked in the data: the collector stores `closingIssuesReferences` as `gh.pr_files[<pr>].issues` in
`observe_snapshot.json`. 24 of 177 PRs have a linked issue, so `bug:issue/*` nodes can be built from local data
(only as "issue → fixing PR"; issue title and state are not collected). `bug:sig/*` nodes come from
`P1/raw/fail_signatures.json` (452 job entries, 10 signatures).

## 7. Notes for P1

- Reusable keys already in the DOM: `data-pr` (168 elements, Next release 3C/3D only), `data-area` (56), `data-path` (60), `data-stage`.
- Only 2 open helpers exist: `opsOpenFeature`, `cpuOpenFile`. No helper for PR, build, workload or bug.
- The 11 retired hidden sections (`now`, `prs`, `ci`, `trend`, `flaky`, `gpuload`, `bug`) hold the only PR-check and dev-health tables. The Today tab (5.3) needs that data; reuse the collectors, not the hidden HTML.
- Workload counts by regex were noisy (names like `rag`, `blend` match other words), so they are not reported here.
