# Agent prompt: One data pipeline that keeps every Release Desk tab in sync

> **How to use:** paste everything below the line into an agent (Claude Code) with shell access to this workspace.
> Built from the data-sync review of 2026-11-27 (release `20261127T054345Z`). Every finding below was seen in
> `ops-app/dist/index.html`, `ops-app/pages-out/` and the builders; re-check each one before you fix it.

---

## Role

You are the data engineer of the **Release Desk** page (`LM-762-ci-resource/ops-app`, served locally from
`releases/CURRENT/site` and on Cloudflare Pages from `pages-out/`). The page is one static `index.html` in which each tab
reads its own inlined JSON block (`<script id="…Data" type="application/json">`). Today each block is built by a
different builder, from a different source, with a different time window and a different time format, and nothing checks
that they agree. Make **one refresh run produce one consistent snapshot for every tab**, and make the build refuse to go
live when a tab is out of sync.

## Map: tab → block → builder → source

| Tab (hash) | Block(s) | Builder (in `plan-2026-11/outputs/cpu_tests/`) | Source |
|---|---|---|---|
| Release (`#obs`, Today, Desk, History) | `obsSnap`, `obsHist`, `todayData`, `deskData`, `entData` | `build_observe`, `build_today`, `build_desk`, `build_entities` | `observe_snapshot.json`, `ops.db` |
| Release → Coming release / Optimal CI / 24 h overlap / Trace Agent | `opsData` | `build_ops_tabs` | snapshot, `ops_ci_24h.json`, git `origin/dev`, **`P1_2026-10-17` CSVs**, `trace_agent/` |
| Release → Weekly, CI impact | `weeklyData`, `impactData` | `build_weekly`, `build_impact` | `collect_weekly.py`, `collect_ci_impact.py` |
| PR Inspector drawer | `piData` | `build_pr_inspector` | snapshot, `overlap_patches.json`, **clone `HEAD`** |
| Tests & gates (gates / CPU / GPU) | `gatesData`, `cpuData`, **`k3MonitorData`** | `build_gates`, `build_page` (CPU), **none** (K3 monitor) | `gates.py`, `cpu_tests.json`, **hand-inlined** |
| CI Baseline (`#r1130`) | `r11Data` | `build_report1130` | **`P1_full`** (ETL lake export) |
| UX layer / hard-coded P1 figures | `uxData` | `build_ux` (`sync_p1`) | **`P1/build_level_summary.json`** (30 days to 2026-11-05) |

Rebuild this table from the code first; if it differs, trust the code and say what changed.

## Findings to fix (priority order)

| # | Finding | Evidence | Effect on the page |
|---|---|---|---|
| F1 | Cloudflare Pages copy lags the live build. `OPS_PAGES_AUTO` is not set, so `refresh.ps1` never runs `pages.py deploy` | `pages-out/index.html` blocks `made 04:35Z`; `releases/CURRENT` `made 05:42Z`; `pages-out` still has `outputs/P1_2026-10-17`, `dist` has `outputs/P1_full`; `r11Data.window` ends 2026-11-15 on Pages vs 2026-11-27 live | Web users see an older CI Baseline (12 days shorter) than the local site |
| F2 | Two tabs use two different 30-day baselines | `opsData.opt.v3.stage_costs_30d` reads `P1_2026-10-17` (window 2026-10-16 → 2026-11-14, hard-coded at `build_ops_tabs.py:924`); `r11Data` reads `P1_full` (2026-10-17 → 2026-11-27) | "Optimal CI" and "CI Baseline" show different numbers for the same metric |
| F3 | `k3MonitorData` has no builder | Block is plain text in the page template, `made 2026-11-18 14:57 UTC`; no `.py` writes it | GPU / K3 monitor tab is 9 days old and never refreshes |
| F4 | UTC bug: local-offset time written with a `Z` suffix | `build_ops_tabs.py:269-287` and `:2002`: `w1 = dt(head)` keeps `+08:00`, then `strftime("%Y-%m-%dT%H:%M:%SZ")` | `opsData.overlap.at`, `piData.ov_at`, `w0` are 8 h in the future (11:42Z when the build ran at 05:42Z); "merged in last 24 h" window shown shifted by 8 h |
| F5 | PR Inspector scans the stale working tree | `build_pr_inspector.py:265-266` uses `rev-parse HEAD` / `log -1 HEAD`; `refresh.ps1` only `git fetch`es refs | `piData.head_at = 2026-11-23` while `origin/dev` is 2026-11-27 |
| F6 | ETL lake is not part of the scheduled refresh | `refresh.ps1` never calls `etl/etl.py update` / `window --out outputs/P1_full` | `P1_full` only moves when someone runs it by hand; CI Baseline freezes silently |
| F7 | Frozen baselines not labelled as such | `uxData` P1 = 2026-10-05 → 2026-11-05, `gatesData.wl_cost.since = 2026-10-05` | Reader cannot tell "baseline by design" from "stale" |
| F8 | Mixed time formats | `"2026-11-27 05:42"` (entData, piData, researchData, todayData) vs ISO `…Z` (opsData, r11Data, kbData) | Freshness cannot be compared in code; UI shows mixed formats |
| F9 | No gate checks cross-tab consistency | `verify_page.py` / `check_app.py` pass with F1–F8 present; `deskData.overview.ages` covers only 6 sources | Any of the above goes live unnoticed |

`trace_agent` (2026-11-09) is a paid manual run by design: keep it out of the schedule, but it must be labelled
"manual" in the manifest, not counted as a sync failure.

## Target design

1. **One run context.** At the start of `refresh.ps1`, write `ops-app/data/run.json`:
   `{run_id, as_of (UTC, ISO-8601 Z), window_30d: [since, until], window_24h: [w0, w1], origin_dev_sha, origin_dev_at}`.
   Every builder reads windows and "now" **only** from this file (a small helper `run_ctx.py`), never from
   `datetime.now()`, hard-coded folders or the working-tree `HEAD`.
2. **One baseline.** A single P1 export per run (`P1_full`, produced by an `etl` step inside `refresh.ps1`, using
   `window_30d`). `build_ops_tabs.stage_costs_30d`, `build_report1130`, `build_ux.sync_p1` all read it. A baseline that
   must stay fixed (e.g. the pre-change "before" period) is declared once in a config with `kind: "frozen_baseline"`.
3. **Every block carries the same header:** `"_meta": {run_id, made, source_at, window, kind: live|frozen_baseline|manual, max_age_h}`,
   all times UTC ISO-8601 with `Z`, produced by one helper. Keep existing fields for the JS; add `_meta` beside them.
4. **A manifest** `site/api/manifest.json`: one row per block (id, tab, builder, source, `_meta`, sha256 of the block).
   The page header and each tab show their freshness from it (`live` / `frozen baseline` / `manual · N days`), in EN and VI.
5. **A consistency gate** `tests/check_sync.py`, run after `export_static` and before `publish`. FAIL when:
   any block lacks `_meta`; `run_id` differs between blocks; a `live` block's `window` differs from `run.json`;
   any timestamp is later than `as_of` + 5 min; any timestamp has no zone; `source_at` older than `max_age_h`
   (stale → FAIL for `live`, WARN for `manual`); a block id in the page has no builder.
6. **Pages follows the live build.** After a successful `publish`, run `pages.py deploy` (set `OPS_PAGES_AUTO=1`, or make
   it the default when `OPS_PAGES_PROJECT` is set). After upload, compare `manifest.json` sha256 of the Pages deployment
   with `releases/CURRENT` (fetched through the password gate with the credentials from the env, never printed). A
   mismatch writes `status: warn` to `last-refresh.json` and alerts.

## Work steps

1. Read `deploy/refresh.ps1`, `cpu_tests/build_page.py` (builder order), each builder in the map, `verify_page.py`,
   `deploy/pages.py`, `backend/export_page_data.py`. Confirm F1–F9 with a short script that prints `_meta`-like fields of
   every block in `dist/index.html` and `pages-out/index.html`. Save that script as `tests/sync_report.py`; it stays.
2. Add `run_ctx.py` + `run.json`; fix F4 (`.astimezone(timezone.utc)` before every `Z` format; grep the whole
   `cpu_tests/` and `backend/` for `strftime(...Z")` applied to non-UTC datetimes) and F5 (`origin/dev` instead of `HEAD`,
   fall back to `HEAD` only with `ref: "HEAD"` in `_meta`).
3. F6 + F2: add the `etl` step to `refresh.ps1` (parallel with the collectors where it does not depend on them; respect
   `-Offline`), switch `stage_costs_30d` to the shared baseline. Note any number on the page that changes and why.
4. F3: write `build_k3_monitor.py` from the ETL lake (`lake/raw/bk_builds/k3-*`) producing the same JSON shape as the
   current block (`window, builds, jobs, rows[w,g,runs,dev,df,flk,p50,p90,gh,res,tier,note,r14,p90_14,flk_14]`), wire it
   into `build_page.py`. Diff its output against the 2026-11-18 block for the overlapping days; explain differences.
5. F7 + F8: add `_meta` to every block through one helper; normalize times. Update the JS readers only where needed.
6. F9: write `tests/check_sync.py`, add it to `refresh.ps1`; extend `deskData.overview.ages` from the manifest.
7. F1: enable the post-publish Pages deploy + hash comparison.
8. Run `refresh.ps1 -Offline`, then a full `refresh.ps1` if tokens are present. Run `verify_page.py`, `check_app.py`,
   `check_sync.py`, `check_mobile.py`. Then break one block on purpose (old `made`, wrong window, `+08:00` time) and
   show that `check_sync.py` fails and nothing is published.

## Hard rules

- The page never calls GitHub or Buildkite from the browser; no token in the page. Data flows only collector → file /
  `ops.db` → builder → page.
- Fail closed: any failed step leaves `releases/CURRENT` and the Pages deployment untouched. Keep `publish.py`'s
  privacy scan and the Pages sign-in check; never upload `ops.db`.
- Do not run the Trace Agent (paid). Do not change numbers by hand to make two tabs agree; fix the source.
- Do not delete `P1_2026-10-17` or `P1`; if they stay as a frozen baseline, label them.
- Do not report a check as passing unless you ran it after the final build and saw its output.

## Done when

| Check | Expected |
|---|---|
| `tests/sync_report.py` on `releases/CURRENT/site/index.html` | every block: same `run_id`, UTC `Z` times, none later than `as_of`, `live` windows equal `run.json` |
| Optimal CI vs CI Baseline | same 30-day window and same GPU-h / job-min totals for shared cells |
| K3 monitor tab | `made` = this run, window ends at `run.json` `until` |
| PR Inspector | `head_at` = `origin/dev` commit time |
| Pages vs local | `manifest.json` hashes equal after the run |
| Negative test | a broken block makes `check_sync.py` FAIL and the run publishes nothing |

## Report back

A table per finding: fixed / not fixed / changed scope, file:line of the change, before → after values seen on the page,
the commands you ran with their PASS/FAIL lines, and any number that changed on a tab with the reason.
