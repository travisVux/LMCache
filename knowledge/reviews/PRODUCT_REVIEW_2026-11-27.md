# Release Desk — full product review, merged report

Date: 2026-11-27. Build reviewed: `aaa55ee8cffa` (`ops-app/dist`, release `20261127T064722Z`).
Method: 12 reviewers, one per aspect of `knowledge/prompts/PRODUCT_REVIEW_PROMPT.md`, working read-only and in
parallel; this report merges them. Paths are relative to `LM-762-ci-resource/` unless stated.

## How to read the "Status" column

| Status | Meaning |
|---|---|
| **Re-checked** | The merging agent reproduced the evidence itself after the reports came in. |
| **Corroborated** | Two or more reviewers found it independently, with their own evidence. |
| **Reviewer only** | One reviewer measured it; not re-run at merge. Treat as credible, not as proven twice. |
| **Unverified** | The reviewer could not confirm a key fact (named in the row). |

Nothing was sent to Cloudflare, GitHub or Buildkite, so every statement about the live web copy, the real D1
database and the Cloudflare dashboard comes from code, logs and offline experiments.

## Verdict in five lines

1. The page can show a wrong ship signal today: tabs disagree on dev health, and a required gate with no data
   renders as green (2 × P0).
2. The system that runs production is not in version control and sits on one disk with its only backups.
3. Nothing tells a human when it breaks: no alert URL, no monitor, tasks that stop at the first reboot, and a web
   chip that stays green however old the data is.
4. The gates fail closed and work, but they test shape and agreement, not correctness: 10 of 30 deliberately broken
   builds passed all three refresh gates.
5. The design underneath is sound (atomic publish, versioned D1 rows, fail-closed order, decision-first first
   screen). Most fixes are small.

## (a) Scorecard

| # | Aspect | Score /5 | Top risk |
|---|---|---|---|
| 1 | Product, IA, UX | 3 | Two tabs give opposite answers on dev health |
| 2 | Data correctness | 2 | Three verdict code paths; absence of data treated as green |
| 3 | Pipeline, orchestration | 3 | Collector failures end as "refresh OK"; `etl_window` never run in the pipeline |
| 4 | Sync and D1 copy | 3 | `d1_verify` never reads the data columns; ~8,000 rows rewritten per push |
| 5 | Backend, API | 2.5 | `/api/db` filters silently ignored (matters when tabs adopt it) |
| 6 | Frontend, performance | 2 | Mobile LCP 15–16 s; failed load shows "Loading data…" for ever |
| 7 | Security, privacy | 3 | Retired Cloudflare token in clear text; shared password cannot be revoked |
| 8 | Reliability, DR | 2 | One PC, one disk, no alerting, logon-only tasks |
| 9 | Code quality | 2 | Live system not in git; generated page is its own only source |
| 10 | Testing, gates | 2.5 | Consistent wrong data passes every gate |
| 11 | Cost, limits | 2 | D1 write quota and GitHub REST quota reachable in one busy day |
| 12 | Docs, governance | 2 | Docs deny a live feature; documented commands fail as typed |

Average 2.4.

## (b) Ranked P0 / P1 findings

Duplicates are merged; the IDs of every reviewer finding a row covers are listed.

### P0 — wrong data shown

| Rank | Finding | Evidence | Failure scenario | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| P0-1 | **Dev health disagrees between tabs.** Desk lists `k3-blend-test` and `k3-comprehensive-test` as open, gating, not-stale blockers; Today's gate verdict counts 0 dev-red; Coming release says "Other dev pipelines green". (A2-1, A1-1) | `deskData.overview.blockers` has both with `gating=True, stale=False`; `todayData.gate.reasons[dev_red].n = 0`; `opsData.coming.dev_red = []`. Builds #4655 / #3805 are from 2026-11-11. Cause: `backend/model.py:100-112` takes the newest `bk_build` row with no age limit; staleness is per file, not per row. The Today tab itself shows "2 of 5 red" in section 0D while its verdict counts 0. | A release manager works the RC checklist on Coming release, sees green ticks and cuts an rc while two dev pipelines are red; or Desk stays red on 16-day-old builds after the real blockers are fixed. | Every gate row carries its own `as_of`; older than N days = "unknown", never red or green. One `dev_health()` used by all three tabs, plus a `check_sync` invariant that they agree. | M | Re-checked |
| P0-2 | **Missing data renders as green or as zero.** "Required checks green on dev (k3-unit-tests, k3-multiprocess-test)" is ok with no `k3-unit-tests` dev build in the snapshot. Same pattern: "✓ Breaking changes listed" beside "No release-notes list yet"; "Decisions 0 open of 0" when no prep doc exists. (A2-2, A1-5) | `obsSnap.bk.dev_builds` holds 3 pipelines, none `k3-unit-tests`; `build_ops_tabs.py:1581-1588` adds to `dev_red` only when a failed build exists, `:584` prints ok when it is empty; `:575,587` empty notes list → ok. Newest `k3-unit-tests` build on `dev` in `ops.db`: 2026-11-11. Why dev builds stopped appearing: unverified. | `k3-unit-tests` breaks on dev or stops running; every tab keeps showing green. | A third state, "no data", distinct from ok and zero, on every checklist row and counter; it counts as not-ok for required gates. | S | Reviewer only (the empty `coming.dev_red` was re-checked) |

### P1 — likely incident or wrong decision soon

| Rank | Finding | Evidence | Failure scenario | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| P1-1 | **The live system is not in git.** One commit (`42ff0dd`, 2026-11-23); all of `ops-app/deploy/` untracked (`refresh.ps1`, `publish.py`, `d1_sync.py`, `pages.py`, `pages-functions/`), plus `dbapi.py`, `split_page.py`, `sync_run.py`, 4 of 5 tests, 23 of 69 builder modules. History is kept as 23 folder copies in `backups-dev/` (191 MB). (A9-1, A9-2, A9-3, A12-1, A8-1, A10-5) | `git log` = 1 line; `git status --short` = 195 lines; `?? LM-762-ci-resource/ops-app/deploy/`. Root `.gitignore` covers only `__pycache__`; `git status -uall` = 35,437 untracked files (~770 MB). The ignore file that hides the two secret files (`ops-app/.gitignore`) is itself untracked. | Disk fault or a wrong `git clean` removes the publish, D1 and Cloudflare code with no history. A plain `git add -A` would add 35k files. | In this order: write the root `.gitignore` (lake, backups-dev, expert_review, .wrangler, third_party, caches), commit `ops-app/.gitignore`, commit in 4–6 topical commits, push, delete `backups-dev/`. | S | Re-checked |
| P1-2 | **Backups never leave the disk.** (A8-2) | `OPS_BACKUP_COPY_TO` not set; `backups/` (4 days, 41 MB) on the same single SSD as `ops.db`, `state.db` and the 67 MB lake. The restore drill reports `ok: true` even when no `.db` was restored (`backup.py:71`). No `d1_sync.py pull` exists (A8-8). | Disk loss takes the database, all backups and the lake together; recovery from D1 needs a script nobody has written. | Set `OPS_BACKUP_COPY_TO`; make the drill fail on an empty or old backup; add `d1_sync.py pull`. | S–M | Reviewer only (key absence re-checked) |
| P1-3 | **No alert reaches anyone.** `OPS_ALERT_URL` / `OPS_DIGEST_URL` unset; fallback is a pop-up on the PC. Nothing calls `/healthz`; `/healthz?strict=1` is permanently 503 because the manual Trace Agent source (435 h old) has the same 48 h limit as automated sources. Task Scheduler history is disabled. (A8-3, A8-4, A5-9) | Key-name scan of `deploy/ops-app.env`; `curl /healthz?strict=1` → 503, `stale: ['trace_agent']`; `model.py:384-390`. Today's 09:01 and 09:06 runs failed with only a pop-up. | The page stops updating and nobody learns; a monitor on strict health would page for ever and be muted. | Set `OPS_ALERT_URL` (ntfy fits the constraints); per-source thresholds so manual sources do not fail `ok`; an external dead-man check on `/api/sync-status` older than 26 h. | S | Corroborated |
| P1-4 | **Everything stops at the first reboot.** All four tasks are logon type Interactive, no auto-logon; the PC has not rebooted since they were created. `deploy/README.md:16` says "start at boot without anyone logged on". The documented installer creates a different task set (adds `ops-app-caddy`, drops the restore drill, does not know `ops-app-webrefresh`). (A8-5, A12-4, A3-4) | `Get-ScheduledTask ops-app*` → 4 tasks, all Interactive; `install-services.ps1:25,88-90`. | Windows Update restarts overnight: no refresh, no backup, web "Refresh data" silently dropped, until someone signs in. | Reinstall as S4U (set `GH_TOKEN` first: whether an S4U session can read the `gh` keyring is unverified), or enable auto-logon; one script that recreates the real task set. | M | Re-checked |
| P1-5 | **A retired Cloudflare API token is kept in clear text; one broad token in two files.** (A7-1) | `deploy/ops-app.env`: a comment line above `CLOUDFLARE_API_TOKEN` ("previous token, kept for rollback"). Live token also in `cloudflare-credentials.txt`, next to the site password. One token covers Pages, KV and D1 edit. Both files are git-ignored, never committed, ACL = SYSTEM / Administrators / Admin. Whether the old token still works: unverified. **During this review two reviewers' key-name filters printed that comment line once each into their own tool output; the value is in two agent transcripts on this PC and in no report.** | Any process running as the user reads one file and can replace the site and rewrite D1. | Revoke the old token today, delete the comment; one copy of the live token; split into a deploy token and a KV-only token for the 2-minute poller. | S | Corroborated |
| P1-6 | **The shared password cannot really be revoked.** No rate limit, lockout or audit; old deployment URLs keep the password they were made with; no minimum length. Related: the gate is a Pages Function on every request with no `_routes.json`, so unauthenticated requests spend the 100,000/day quota. (A7-2, A11-3) | `_middleware.js:27-49`; `CLOUDFLARE.md:23`; `pages.py:185-198`. Fail-open vs fail-closed setting in the Cloudflare dashboard: **unverified**. | A leaver keeps access through any earlier `<hash>.pages.dev` URL. If the project is on fail open, exhausting the quota serves the data with no password until 00:00 UTC. | Check and set "fail closed" now; enforce a minimum password length; delete old deployments after each deploy. Target: Cloudflare Access. | S / M | Reviewer only; quota part unverified |
| P1-7 | **The privacy scan misses most secret types.** (A7-3) | 13 synthetic secrets through `publish.scan`: 2 caught, 11 missed (Cloudflare token, `Authorization` headers, private-key header, webhook, tokens in unlisted extensions). `publish.py:37,44-59`. On today's published site and DB: 0 hits. | A pasted credential line or a collector log lands under `outputs/`; the scan passes; it is uploaded to Pages and D1. | Add those rules and an in-memory compare against the env file's own values; scan every file under a size cap. | S | Reviewer only |
| P1-8 | **Three verdicts, three gate lists, two vocabularies in one table.** Desk uses 5 dev pipelines, Coming release 2, Today every pipeline. The MUSA known issue is non-gating on Desk and a NO-GO reason on Today. `release_verdict` holds `partial` and `old:shipped_fail` style words from two writers. "Blocking" is 4 on Today and 2 on Coming release. (A2-3, A2-10, A1-4, A9-5) | `build_ops_tabs.py:563`; `backend/config.py:76`; `build_today.py:132-154,272-290`; `model.py:57-75,480-496`; `decisions.py:352-369`; `ingest_files.py:286`. `ops.db`: `partial` 508 rows, `old:shipped_fail` 170, `old:blocked` 19. | With only the known MUSA issue left: Desk green/amber, Today NO-GO, Coming release not ready for unrelated reasons. | One `release_gate()` in `decisions.py` returning verdict + reasons, rendered by all three tabs; one blocker definition with a type sub-label; a `source` column instead of the `old:` prefix. | M | Corroborated |
| P1-9 | **The 100-of-740 PR sample is stated as totals, and the sample is biased.** The 100 are the PRs updated in the last 24 h. Tabs say "74 open PRs" (498 non-draft exist); 12 of 28 approved PRs never appear in ready lists. The gap is visible only as a tooltip "3 source error(s)", hidden below 768 px. (A2-4, A1-3, A11-6) | `obsSnap.gh.prs_gql`: 100 nodes of `totalCount` 740, `updatedAt` 11-26 04:17Z → 11-27 04:28Z; `build_observe.py:77` `pr_pages=2`. GraphQL cost of all 15 pages ≈ 30 of 5,000 points; the real cost is the per-PR overlap step (`overlap_collect.py:27-28`). | A PR author whose PR is not in the newest 100 sees no clash and assumes none. A reader takes 74 as the backlog. | Page all open PRs for the cheap fields; keep diffs for recently updated PRs, cached by head SHA; print "n of N" wherever a count is shown; make the chip a popover that lists the errors. | M | Corroborated |
| P1-10 | **Four baseline windows on one page; the "one baseline" gate compares a folder with itself.** (A2-5) | GPU cards 10-05 → 11-05; Optimal CI 10-16 → 11-14 (made 11-15; `report_collect.py` is not in `refresh.ps1`); CI Baseline 10-17 → 11-27; K3 monitor 10-19 → 11-18 (frozen). Retry share 5.4% vs 4.5% under the same name. `tests/check_sync.py:98-106`. | A before/after comparison of a CI change mixes windows. | Schedule `report_collect.py` or derive those metrics from `P1_full`; extend the gate to every block that carries a window. | M | Reviewer only |
| P1-11 | **Collector failures end as "refresh OK", and no gate checks freshness.** (A3-3, A10-3) | `collect_ci_impact.py:650-655` (any exception → exit 0); `observe_collect.py:266-273` (query failed → keeps old snapshot, returns 0); `check_sync.py:84` only rejects times later than the build. Mutation: every snapshot time set 30 days back → all three refresh gates pass. | GitHub fails at 07:00: yesterday's data is republished as a new build with status `ok`. | Collectors write `{source, ok, at, error}`; `check_sync` fails or warns when a snapshot is older than N hours on an online run. | S–M | Corroborated |
| P1-12 | **Gates test agreement, not correctness.** 10 of 30 broken builds pass `verify_page`, `check_sync` and `check_app`: wrong stable release on all tabs, weekly build shown all-passed, GPU numbers ×10, blockers list emptied, and four data blocks empty (`weeklyData`, `impactData`, `kbData`, `uxData`). No test imports `decisions.py` or `model.py`. (A10-1, A10-2) | Mutation run on copies of `dist`, manifest re-hashed; results in the Aspect 10 scratch folder (`mutation_results.json`). | A collector or verdict bug turns a tab green; the refresh publishes it. | Golden dataset: a small frozen `ops.db` + snapshot → expected verdict, blockers, KPIs (stdlib). A minimal schema and row-count floor per block in `check_sync`. | M / S | Reviewer only |
| P1-13 | **`verify_page` fails a healthy build.** It requires at least one inbox row and hard-codes `v0.5.7rc4`. (A10-4) | `verify_page.py:107,141,152`; mutated copies with an empty inbox / without that tag → FAIL. A real empty-inbox day was not observed. | The day the inbox is empty, every refresh fails and the site freezes on old data. | Assert structure and an empty state, not that there is work; derive the tag from the data. | S | Reviewer only |
| P1-14 | **`etl_window` has never run inside the pipeline and uses the unsafe entry point.** `refresh.ps1:134` calls `etl.py window` straight into `outputs/P1_full` instead of `etl/refresh_p1_full.py` (staging + swap). The ETL sleeps up to 60 min for a GitHub rate reset; the step is killed at 40. (A3-1, A11-7) | `grep -l etl_window logs/*.log` → 0 files; last manual window run 2 h 45 min; `etl/core/http.py:74-83`; `etl.py:50-62,144-147` (errors caught, exit 0). | The step is killed mid-write; `P1_full` is half new, half old; the next offline rebuild publishes the mix as the CI Baseline (static analysis, not executed). | Call `refresh_p1_full.py`; exit 1 above a failure threshold; time one real run before trusting 40 min. | S | Corroborated (static) |
| P1-15 | **A failed run leaves collectors running and releases the lock.** (A3-2) | `refresh-20261127-090100.log` FAILED at 09:01:01; its part logs were still being written at 09:06:35; the next run started at 09:06:45. `refresh.ps1:199-212` kills nothing in `catch` / `finally`. | Two collectors write the same cache, snapshot and `ops.db`. | In `finally`, kill every started step still alive and append its part log. | S | Reviewer only |
| P1-16 | **The scheduled run pushed D1 but not Pages.** (A3-4, A4-4, A8-6) | Three reviewers found `OPS_PAGES_AUTO` commented out in `deploy/ops-app.env`. **The file was modified at 14:07 on 2026-11-27, during the review, and the key is now set (line 14); the review did not make that change.** Not yet proven by a scheduled run. | (Before the change) the web page shows yesterday's data under a "Synced 07:0x" chip taken from D1's time. | Confirm on the next 07:00 run that `pages_deploy` appears in the log. | S | Re-checked: appears fixed, awaiting a run |
| P1-17 | **The web copy never says it is old.** The header chip maps status to a green dot and an absolute time, with no age rule; `site/api/overview.json` has `stale:false` baked in at export. (A8-6, A5-7) | `backend/split_page.py:62-69`; `sync-status.js`; `frontend/app.js:48,52`. | PC off for 3 days: a green "Synced" chip over a 3-day-old verdict. | Chip amber over 26 h, red over 48 h, computed in the browser. | S | Corroborated (static) |
| P1-18 | **`d1_verify` never reads the data, runs after the switch, and nothing rolls back.** (A4-1, A4-6) | `d1_sync.py:343-345` compares stored `_k` / `_h` only. Offline experiment: all 1,575 live `pr` titles overwritten → verify True. `refresh.ps1:176-177`: push, then verify, failure = `warn`. | D1 serves different values and the gate says "all equal"; a bad snapshot stays live until the next refresh. | Recompute the hash from the D1 columns for changed tables; verify before the switch or roll back on FAIL. | M | Reviewer only |
| P1-19 | **A failed schema change leaves D1 views missing for good.** (A4-2) | `d1_sync.py:205-243,280-281`: schema recorded first, then ~90 separate calls, before the lock. Experiment: fail the 3rd `CREATE VIEW` → 37 of 44 views; later pushes "succeed"; verify raises every time. | One network error during a schema-changing push: `/api/db/v_*` returns 500 until D1 is fixed by hand. | Record `schema:<t>` only after the views exist; compare with `sqlite_master`; take the lock first. | S | Reviewer only |
| P1-20 | **Every D1 push rewrites ~8,000 unchanged rows.** `snapshot_id` and `last_seen` are part of the row hash. (A4-3, A11-1) | Diff of consecutive releases: only `snapshot_id` changed in `bk_build` (6,514 rows) and `pr`; log line "8019 rows written … 85 calls", 74.8 s (README says 13 calls / 15 s). Free plan: 100,000 rows written / day (Cloudflare pricing page, fetched during the review). Billed writes per push with indexes ≈ 40,000–64,000: **estimate, unverified**; lower bound 16,000. | The 2nd or 3rd push in a UTC day fails; D1 stays old until 00:00 UTC. 21 refreshes ran on 11-27. | Leave bookkeeping columns out of `row_hash`; log rows written per push and refuse above ~70,000 / day. | S | Corroborated |
| P1-21 | **One refresh spends ~2,000 GitHub REST calls; "Refresh data" has no cooldown.** 1,487 of the calls re-fetch job lists with no cache. (A11-2, A7-6) | `observe_ops_collect.py:62,87`; log "gha runs 1487"; snapshot shows 625 calls used 43 s after start; `refresh.js:13-24` limits only to "one queued". | Three online refreshes in an hour exhaust 5,000/h on the operator's own `gh` login; tabs are built from runs with `jobs: None`. | Cache jobs by run id for completed runs (pattern already in `collect_ci_impact.py:330-351`); honour rate-limit headers; a minimum interval for web-triggered refreshes. | M | Reviewer only |
| P1-22 | **A failed data fetch shows "Loading data…" for ever.** (A1-2, A6-1) | Blocking any one of the 18 data files (even the 5 kB `k3MonitorData.json`): no tabs, no error, no Retry, 3 of 3 runs, two reviewers. `split_page.py`: the pill set on `DOMContentLoaded` overwrites the error pill from the `.catch`. | One 404 during a release switch leaves every reader waiting. | Set a failed flag in the catch and skip the loading pill; add a gate case. | S | Corroborated; code re-read at merge |
| P1-23 | **Docs deny a live feature, and documented commands fail as typed.** READMEs say "no refresh button"; the web button, `web_refresh.py`, KV binding and the 2-minute task are live and undocumented, with no record of the decision being reversed. `python` on this host is the Store stub. (A12-2, A12-3) | `deploy/README.md:110`; `HOST_SERVER_PROMPT.md:56-59`; `Get-Command python` → WindowsApps stub; real interpreter found only via `common.ps1:14-20`. | During a bad build the operator types the documented rollback command and gets the Store stub. | A "Web refresh" section and a decision record; a `py.ps1` wrapper used in every doc command. | S | Reviewer only |
| P1-24 | **The generated page is its own only source and is rewritten in place.** ~90 kB outside every marker block and the whole `K3MON` block exist only in `06_PR_TO_CI_VISUAL.html`; 20 non-atomic writes of an 11.6 MB file per build. (A9-4) | 57 marker blocks cover 99.2%; `K3MON:START` is in no `.py`; `build_ops_tabs.py:2860-2868`. | A kill mid-write leaves a truncated page; git has a copy 4 days and 6.8 MB behind. | Extract a tracked `page_base.html`; write to a temp file and `os.replace`. | M | Reviewer only |
| P1-25 | **`/api/db` silently ignores filters and truncates** (matters the day tabs read it; nothing consumes it today). (A5-1, A5-2) | `/api/db/pr?tag=v0.5.8` → 200, same 1,000 rows as no filter; 1,000 of 1,575 with no `total`; 26 of 38 tables have no `ORDER BY`. | A tab asks for one release's PRs and renders all PRs. | 400 for a filter the table cannot apply; add `total` and `next_offset`; a stable sort key. | S–M | Reviewer only |

### Contradictions between reports, and how they were resolved

| Topic | Reports said | Resolution |
|---|---|---|
| Dev-red on Today | Aspect 2: "Today says 0"; Aspect 1: "Today shows 2 of 5 red" | Both true. Today's gate verdict counts 0; Today's section 0D lists the same two red pipelines as Desk. The disagreement exists inside one tab. |
| `OPS_PAGES_AUTO` | Aspects 3, 4, 8, 12: commented out | True when read; the env file changed at 14:07 and the key is now set. See P1-16. |
| Delta push cost | README: 13 calls, ~15 s | Log: 85 calls, 74.8 s, plus 63 s verify. The README is wrong (A4-12, A11-1). |
| Refresh log counts | 17, 20 or 21 OK runs | Different moments; only 30 log files are kept (about 16 h today), so the window moves. |
| `in_sync` | Described two ways | It is defined two ways: page build = D1 build on Cloudflare, D1 label = local release on the PC (A5-3, A4-12). |

## (c) Roadmap

Owner roles: **Op** = Release Desk operator / host owner, **Dev** = Release Desk developer, **RM** = release manager
(decides definitions), **Sec** = whoever owns the Cloudflare account.

### First 30 days — stop the wrong signal, stop the loss risk

| # | Item | Closes | Effort | Owner |
|---|---|---|---|---|
| 1 | Revoke the retired Cloudflare token, delete the comment, keep one copy of the live token | P1-5 | S | Sec |
| 2 | Root `.gitignore`, commit and push the live system, delete `backups-dev/` | P1-1 | S | Dev |
| 3 | Set `OPS_BACKUP_COPY_TO` and `OPS_ALERT_URL`; fix strict health so manual sources do not fail it | P1-2, P1-3 | S | Op |
| 4 | Per-row age on gate rows, a "no data" state, one `dev_health()` | P0-1, P0-2 | M | Dev + RM |
| 5 | Loader failure flag and Retry; chip age rule; chip popover with the error list; "n of N" on counts | P1-22, P1-17, P1-9 (display part) | S | Dev |
| 6 | Check Pages "fail closed"; minimum password length; prune old deployments | P1-6 | S | Sec |
| 7 | Kill started steps in `finally`; call `refresh_p1_full.py`; collectors report `{ok, at, error}` and `check_sync` checks age | P1-15, P1-14, P1-11 | S–M | Dev |
| 8 | Bookkeeping columns out of the D1 row hash; write budget log | P1-20 | S | Dev |
| 9 | `verify_page` asserts structure, not content | P1-13 | S | Dev |
| 10 | Confirm `pages_deploy` on the next scheduled run; fix the README lines that are wrong (refresh button, `python`, task list, push cost) | P1-16, P1-23 | S | Op |

### Days 31–60 — one definition, tests that know the right answer, survive a reboot

| # | Item | Closes | Effort | Owner |
|---|---|---|---|---|
| 11 | One `release_gate()`; one blocker definition; `source` column for verdicts | P1-8 | M | Dev + RM |
| 12 | Golden-dataset tests for `decisions.py` / `model.py`; per-block schema floor; run `check_d1_sync` and `check_ci_impact` in every refresh | P1-12, A10-6 | M | Dev |
| 13 | Tasks as S4U (or auto-logon), one installer for the real task set, second daily trigger | P1-4, A8-10 | M | Op |
| 14 | `d1_verify` reads the data and runs before the switch; schema change made repairable; unique key on `(_k, _from)` | P1-18, P1-19, A4-5 | M | Dev |
| 15 | Job cache for Actions runs; rate-limit headers; refresh cooldown | P1-21 | M | Dev |
| 16 | Page all open PRs for cheap fields | P1-9 (data part) | M | Dev |
| 17 | One baseline window source; schedule or retire `report_collect.py` | P1-10 | M | Dev |
| 18 | Privacy scan rules; pre-push scan hook | P1-7, A7-7 | S | Dev |
| 19 | `page_base.html` + atomic write (`pagekit.py`) | P1-24, A9-7 | M | Dev |

### Days 61–90 — performance, contract, governance

| # | Item | Closes | Effort | Owner |
|---|---|---|---|---|
| 20 | Fetch and render per view; drawer data on open; sections hidden by default | A6-2, A6-3, A6-4 | M | Dev |
| 21 | `/api/db` contract: strict filters, `total`, error model, allow-list of tables, one contract test for both implementations | P1-25, A5-3, A5-4, A5-6, A7-4 | M | Dev |
| 22 | JS out of Python strings into `.js` files; one shared `esc`; drop `unsafe-inline` for scripts | A9-6, A6-7, A7-5 | M–L | Dev |
| 23 | `OWNERS.md`, five decision records, `GLOSSARY.md`, a runbook row per alert, a short VI operations page | A12-7 – A12-10 | M | RM + Op |
| 24 | `d1_sync.py pull` and a "PC is gone" drill on a second machine | A8-8 | M | Op |
| 25 | Cloudflare Access in place of the shared password | P1-6 (target) | M | Sec |

## (d) Keep-list — do not lose these while fixing

- **Fail-closed publish.** Gate order in `refresh.ps1`, atomic `releases/CURRENT`, keep-5 rollback. It worked for
  real on 2026-11-27 09:12 (`verify_page` FAIL left the live build untouched).
- **`refresh.lock`** as an exclusive handle the OS frees on a crash; per-step timeout with process-tree kill.
- **D1 design:** `_from/_to` row versions, one-statement switch, half-way push invisible, dirty-push clean-up,
  rollback, tables read at one pinned snapshot, an offline SQLite target that makes it testable (15/15 PASS).
- **Decision-first first screen:** verdict, top blocker, do next, copy command in 0 clicks; sticky "Blocked" chip.
- **PR Inspector drawer** and `#pr/<n>` deep links; search with a useful empty state; aliases for retired tab links.
- **`decisions.py`:** one small pure function per rule, rule text checked against docstrings, EN and VI from one table.
- **Marker blocks** (`X:START … X:END`): each builder idempotent, 57 blocks cover 99.2% of the page.
- **Manifest** with sha256 per block, `partial_errors` in the header, content-addressed data files served `immutable`.
- **Read path safety:** read-only SQLite, bound parameters, identifiers checked against the exposed list, Host
  allow-list, traversal refusal, loopback-only refresh endpoints.
- **Security basics already right:** secret files git-ignored, never committed, tight ACLs; token masked in wrangler
  output; privacy hits reported as hashes; gate answers 503 when no password is set; pre- and post-deploy gate check.
- **Lake design:** atomic partition files, final / watermark, per-partition retry state; Buildkite 429 handling.
- **Stdlib-only, no build step.** Nothing in this report needs a new tool; ntfy and one GitHub Actions job are the
  only additions suggested, both free.
- **EN/VI parity:** no VI-only truncation on 19 mobile routes; 0 JS errors across 76 page loads.
- **Honest "known gap" notes** in the docs, and accurate docstring headers in the newest scripts.

## Appendix — P2 / P3 findings by aspect (one line each)

**Aspect 1.** A1-6 P2 Rebase risk unreadable at 390 px (PR numbers 13–23 px wide). A1-7 P2 no owner or next step
on dev-gate rows. A1-8 P2 mixed time bases in the header, one future time. A1-9 P3 unknown hashes fall back to
Today silently; K3 monitor has no nav entry. A1-10 P3 four untranslated strings, one plural.

**Aspect 2.** A2-6 P2 "30 d" label on a 42-day window with a partial day; baseline age is negative (−17 h).
A2-7 P2 mixed-zone time strings sorted as text (10 of 86 pairs out of order). A2-8 P2 `build_ux.sync_p1` regex
rewrite passes on 0 matches. A2-9 P2 "merged in 24 h" ends at the newest commit, not the snapshot.
A2-11 P3 `gha_capped` flag wrong.

**Aspect 3.** A3-5 P2 run id only in `manifest.json`; published `sync_run` row says `running`. A3-6 P2 `ops.db`
write transaction held across network calls. A3-7 P2 task limit (2 h) shorter than the sum of step limits.
A3-8 P2 lake has no lock or busy timeout. A3-9 P2 fixed window start, build time 41 s → 84 s in 12 days.
A3-10 P3 parallel-step durations logged wrong. A3-11 P3 collector outputs written in place.

**Aspect 4.** A4-5 P2 retried `INSERT` not idempotent. A4-7 P2 dropped table / column / type change not handled.
A4-8 P2 one row above ~90 kB breaks every push. A4-9 P2 lock has no owner check, expires before the step
timeout. A4-10 P2 every read scans all row versions. A4-11 P3 views not pinned to the reported snapshot.
A4-12 P3 `in_sync` has two meanings; three unlinked rollbacks.

**Aspect 5.** A5-3 P2 seven local-vs-Cloudflare differences. A5-4 P2 no stable error model. A5-5 P2 input
validation fails open (`range=30` → all rows). A5-6 P2 every table exposed by deny-list. A5-7 P2 two APIs.
A5-8 P2 no versioning, no contract test. A5-10 P3 `no-store` plus a computed ETag.

**Aspect 6.** A6-2 P2 every view waits for all 18 blocks (mobile LCP 15.3–15.9 s, throttled). A6-3 P2 all 78
sections rendered in one 3.8–4.2 s mobile task. A6-4 P2 CLS 0.20–0.77. A6-5 P2 same JSON parsed up to 4 times.
A6-6 P2 one cache key for all blocks. A6-7 P2 JS not lintable; 11 `esc` copies in two variants. A6-8 P2 two
frontends. A6-9 P3 cache-busted `proposals.js` on every view. A6-10 P3 `server.py` HTTP/1.0, no compression.

**Aspect 7.** A7-4 P2 `/api/db` deny-list exposure; docs still say `ops.db` never leaves the host. A7-5 P2 CSP
allows inline script; viewer tokens in `localStorage` (injection test: 0 of 7,167 executed, limited coverage).
A7-6 P2 no refresh cooldown or requester. A7-7 P2 no privacy gate on `git push`; `ops.db` tracked.
A7-8 P3 tunnel mode checks only header presence. A7-9 P3 loopback responses lack CSP; data cached for a year.

**Aspect 8.** A8-7 P2 crashed web refresh leaves KV `running` for ever. A8-8 P2 restore drill proves little; no
restore from D1. A8-9 P2 rollback and log windows counted in runs (3 h 50 min of releases today). A8-10 P2 one
attempt per day, no retry. A8-11 P2 `npx wrangler@4` downloaded at run time. A8-12 P3 orphan part logs.

**Aspect 9.** A9-5 P2 two verdict engines. A9-6 P2 40% of source is HTML/JS/CSS in Python strings, no linter.
A9-7 P2 `put()` in 17 files with 6 bodies. A9-8 P2 705-line `analyze`; 1 of 777 functions typed. A9-9 P2 40 env
keys in code, 21 in the example file. A9-10 P3 14 orphan scripts; generated outputs tracked; CRLF/LF flips.

**Aspect 10.** A10-5 P2 gates only on the host, 6 of 9 untracked. A10-6 P2 six gates manual. A10-7 P2
`check_app` covers 20 of 31 routes, EN only. A10-8 P2 console check has no positive control. A10-9 P2 published
bytes are not the verified bytes; `publish.py` does not require a passed gate. A10-10 P3 gates write into what
they check.

**Aspect 11.** A11-4 P2 each open tab polls every 60 s, hidden or not (≈34 tabs exhaust KV reads).
A11-5 P2 snapshot reads cannot use an index. A11-8 P3 Buildkite list stops at 1,000 builds silently.
A11-9 P3 79 MB JSON cache rewritten whole each refresh.

**Aspect 12.** A12-5 P2 Cloudflare docs disagree and omit D1 / KV; 10 env keys missing from the template.
A12-6 P2 entry READMEs stale ("Not published", old step order). A12-7 P2 Vietnamese guide covers no operations
and has old paths. A12-8 P2 no owners, no decision records. A12-9 P2 no data dictionary; ERD omits 8 of 39
tables. A12-10 P2 no runbook per alert.

## Gates on the current build (run on copies where a gate writes)

| Gate | Result |
|---|---|
| `check_sync.py` | PASS, 9 passed, 3 warnings |
| `check_app.py --lang en` | PASS, 20/20 |
| `verify_page.py` | PASS |
| `check_d1_sync.py` | PASS, 15/15 |
| `check_ci_impact.py` | PASS, 42 checks |
| `check_kb.py` | PASS |
| `check_inspector.py`, `check_redirects.py` | PASS |
| `check_mobile.py` (VI) | PASS, 24/24 tabs |

## Not covered

- The live Cloudflare deployment, the real D1 state and the Cloudflare dashboard (usage, fail open / closed, token
  expiry, old deployments).
- GitHub and Buildkite token scopes.
- A real `etl_window` run and a real scheduled 07:00 run after the 14:07 env change.
- A value-level search for secrets in logs, backups and shell history.
- Real-device mobile performance (numbers are throttled desktop Chrome, medians of 3, ±20%).
