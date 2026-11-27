# Agent prompt: Full product review of the Release Desk, one expert per aspect

> **How to use:** paste everything below the line into an agent (Claude Code) with shell access to this workspace.
> Either one agent runs every aspect in order, or one agent per aspect runs in parallel: give each the
> **Shared context**, **Rules**, **Output format** and its own aspect section. Then one agent merges the reports
> (section **Merge**).

---

## Shared context (verify, do not trust)

**Product.** LMCache **Release Desk**: an internal page that answers "can we ship the next LMCache release, and what
blocks it?" for release managers and CI owners. Views: Release (Now / Today / History / Weekly / CI impact / Coming
release / Optimal CI / 24 h overlap / Trace Agent), Tests & gates (gates, CPU tests, GPU tests, K3 monitor),
CI Baseline (LM-1130), PR Inspector drawer. EN + VI.

**Stack and layout** (all under `release-desk/LM-762-ci-resource/`):

| Part | Where | Notes |
|---|---|---|
| Collectors | `plan-2026-11/outputs/cpu_tests/*_collect.py`, `ops-app/backend/collect_*.py` | GitHub (gh CLI, GraphQL), Buildkite REST, PyPI, Docker Hub |
| ETL lake | `etl/` (`etl.py`, `lake/state.db`, `lake/raw/` ~62 MB) | partitions per day, P1 export → `plan-2026-11/outputs/P1_full` |
| Store | `ops-app/data/ops.db` (SQLite, ~22 MB, 39 tables, ~27k rows) | `backend/schema.sql`, `ingest_files.py`, `model.py` |
| Page builders | `plan-2026-11/outputs/cpu_tests/build_*.py` (18) | write ONE page `plan-2026-11/06_PR_TO_CI_VISUAL.html`; JS/CSS live inside Python strings |
| Frontend/data split | `ops-app/backend/split_page.py` (run by `export_static.py`) | shell ~1 MB + `data/<build>/<id>.json` (18 files, ~10 MB) + `data/manifest.json` |
| Gates | `verify_page.py`, `tests/check_sync.py`, `tests/check_app.py`, `tests/check_d1_sync.py` | fail closed: nothing goes live on FAIL |
| Release PC | `backend/server.py` (stdlib), Caddy, scheduled tasks, `deploy/refresh.ps1`, `publish.py` (atomic `releases/CURRENT`) | Windows host, Python 3.13, no pip installs by policy |
| Web copy | Cloudflare Pages + Functions (`deploy/pages-functions/`), password gate `_middleware.js`, KV queue for "Refresh data" | |
| Database copy | Cloudflare D1 via `deploy/d1_sync.py` | `h_<table>` with `_from/_to` snapshot numbers, view per table, one-statement switch, rollback 7 |
| API | `/api/sync-status`, `/api/db`, `/api/db/<name>?tag=&branch=&env=&range=…`, `POST /api/sync` | same shape in `backend/dbapi.py` and the Functions |

**Known gaps (already labelled, confirm and rate them):** open PR list truncated to 100 of ~740 (`pr_pages=2`);
K3 monitor block is a frozen hand-inlined snapshot (no builder); Trace Agent is manual / paid; tabs still read
pre-built JSON blocks, not `/api/db`; every refresh rebuilds every tab; first D1 push ~10 min, delta push ~15 s.

**Recent prompts / reviews to read first:** `knowledge/prompts/DATA_SYNC_ALL_TABS_PROMPT.md`,
`ops-app/deploy/README.md`, `ops-app/deploy/CLOUDFLARE.md`, `plan-2026-11/outputs/cpu_tests/REVIEW*.md`.

## Rules (every aspect)

1. **Evidence or it did not happen.** Every finding cites `file:line`, a command and its output, a URL path, or a
   number you measured. Run things (read-only) rather than guess: `check_*.py`, `server.py --root ../dist` on a free
   port, headless Chrome (`C:\Program Files\Google\Chrome\Application\chrome.exe`), SQLite read-only queries.
2. **Read-only.** Do not edit code, publish, deploy, push to D1, call `POST /api/sync`, run collectors that hit
   GitHub / Buildkite, or run the Trace Agent. Do not print secrets: report a secret's location and type, never its value.
3. **Judge against the stated constraints** (stdlib Python, one Windows host, Cloudflare free plan, small internal
   audience) before recommending a new tool. If you still recommend one, say what it replaces and what it costs.
4. **Separate** "broken now" from "will break at scale" from "nice to have". No finding without a concrete failure
   scenario (inputs / state → wrong output, outage, leak, or wasted hours).
5. Name what is **good** too (keep-list), so a fix does not remove it.

## Output format (every aspect)

```
### <Aspect> — score 0-5 (5 = matches the best practice below)
Summary: 3 lines max.
| # | Severity | Finding | Evidence | Failure scenario | Recommendation | Effort (S/M/L) |
Severity: P0 (wrong data shown / security exposure / data loss), P1 (likely incident or wrong decision soon),
P2 (quality, cost, maintainability), P3 (polish).
Keep-list: what is already right.
Checks run: command → result (PASS/FAIL/number).
```

---

## Aspect 1 — Product, information architecture and UX

**Best practice:** decision-first dashboards (answer → reason → evidence, one click to the source); one primary
question per view; progressive disclosure; consistent terms across tabs; Nielsen's 10 heuristics; content that names
owner and next action; empty / loading / error states never shown as zero.

Check: Does the first screen answer "ship or not, why, who acts"? Do the same concepts carry the same names on every
tab (stable, RC, blocker, gate, verdict)? Navigation depth and dead ends; hash routes shareable; EN/VI parity (untranslated
strings, truncation in VI); what a first-time reader misreads (glossary coverage); notification of stale or partial data
(header sync chip, STALE marks); mobile (390 px) usability beyond "no horizontal scroll".
Evidence: screenshots per view (desktop + 390 px), a task walkthrough for 3 personas (release manager, CI owner,
PR author) with time-to-answer.

## Aspect 2 — Data correctness and single source of truth

**Best practice:** one definition per metric (metric layer / glossary with formula, unit, window, source); every
aggregate derived from the same rows the detail list shows; reconciliation tests between layers; explicit
`as_of` and window on every number; no hand-written figures in text.

Check: list every number shown on 2+ tabs and prove they agree (extend `tests/check_sync.py` mentally: which
invariants are missing?); baselines and windows (`baseline.py`, `P1_full`, `P1`, `P1_2026-10-17`); hard-coded
numbers in builders (`build_ux.sync_p1` rewrites text by regex — risk?); time zones and formats; truncation
(100/740 PRs) and what each tab then claims; verdict logic (`decisions.py`, `model.py`) vs what the UI says.
Evidence: a reconciliation table (metric → tab A value → tab B value → source rows → verdict).

## Aspect 3 — Data pipeline and orchestration

**Best practice:** idempotent steps with unique keys; retries with backoff and rate-limit awareness; timeouts;
explicit dependencies (DAG); atomic publish; freshness SLOs per source with alerts; lineage (which source row feeds
which number); backfill and replay; one run id across all outputs.

Check: `refresh.ps1` order, parallel steps and their shared writes (ops.db `busy_timeout`, lake); what happens on
partial collector failure (GitHub-only mode, Buildkite token missing); `etl_window` cost and failure mode; run id
(`sync_run.py`, `RD_RUN_ID`) present in every output; lock handling (`refresh.lock`, D1 lock row); step timeouts
(40 min) vs real durations (read `logs/refresh-*.log`); what is NOT scheduled and why.
Evidence: a DAG drawing of the real run with durations; a failure-mode table (step fails → what users see).

## Aspect 4 — Sync, database copy and consistency (release PC ↔ Cloudflare)

**Best practice:** a single writer; snapshot isolation for readers; atomic switch; idempotent, resumable delta
sync; verification by content hash; bounded rollback; schema evolution without downtime; documented RPO / RTO.

Check: `deploy/d1_sync.py` invariants (`_from/_to`, orphan clean-up, lock expiry, GC vs rollback window, schema
change path incl. dropped / renamed columns and type changes, D1 limits: 100 kB statement, bound parameters,
rows-written quota); ordering of `d1_push` vs `pages_deploy` (can the web page and the database disagree, for how
long, and is it visible via `in_sync`?); `/api/db/<name>` pinned to one snapshot vs views reading `current` at query
time; what `d1_verify` does not cover (views, rd_meta). Run `tests/check_d1_sync.py` and propose missing cases.
Evidence: a timeline of one refresh with the exact moments each copy changes.

## Aspect 5 — Backend and API design

**Best practice:** one contract (schema per endpoint), consistent filters and pagination, stable error model
(status + code + message), versioning, cache headers that match mutability, read-only by default, input validation,
least data exposure.

Check: `backend/server.py`, `backend/dbapi.py`, `functions/api/**` and `lib/api.js` return the same shape (diff them
on the same snapshot); filter semantics (`tag`, `branch`, `env`, `range`) are meaningful on every table or silently
ignored; `limit` / `offset` vs keyset; what `/api/db` exposes (every table: should all be public to signed-in users?);
error bodies; `X-Sync-Id`; `/healthz`; old API (`/api/overview`, `/api/sql?view=`) vs new one — duplication?
Evidence: an endpoint matrix (endpoint × local × Cloudflare × status codes × cache header × schema).

## Aspect 6 — Frontend architecture and performance

**Best practice:** Core Web Vitals (LCP < 2.5 s, INP < 200 ms, CLS < 0.1); load only what the view needs; immutable
cached assets; no blocking parse of megabytes; code in real `.js` files (lintable, testable); one client store keyed
by snapshot and filters; URL as state.

Check: the loader in `split_page.py` (fetches all 18 blocks, ~10 MB, before any script runs); per-tab need vs load;
compression on Pages and Caddy; main-thread time of `JSON.parse` + builders' render; memory on mobile; the parked-script
replay (readyState shim, synthetic DOMContentLoaded) — fragile cases; JS inside Python strings (`build_*.py`): lint,
tests, duplication; `frontend/app.js` shell vs the big page — two frontends?
Evidence: Lighthouse or Chrome trace numbers for 3 views, desktop and throttled mobile; bytes per view.

## Aspect 7 — Security and privacy

**Best practice:** OWASP ASVS L1/L2 for the web parts; least privilege tokens; secrets out of the repo and out of
the page; strong authentication for internal data (SSO / Access over a shared password); CSP without `unsafe-inline`
where feasible; privacy scan before anything leaves the host; audit trail.

Check: secret files under `ops-app/deploy/` (`ops-app.env`, `cloudflare-credentials.txt`) — git-ignored? ACLs? in
backups or `releases/`? Token scopes (GitHub, Buildkite, Cloudflare: Pages, KV, D1). The shared Basic-auth gate
(`_middleware.js`): brute force, rotation, sharing; preview deployment URLs; `POST /api/sync` CSRF and abuse (queue
flooding); `/api/db` data exposure (PR authors, KB text); `publish.scan_db` / `scan` rules vs what D1 and Pages now
hold; CSP in `pages.py` HEADERS and Caddy; server hardening in `server.py`. Never print a secret value.
Evidence: a threat model table (asset → threat → control → gap).

## Aspect 8 — Reliability, operations and disaster recovery

**Best practice:** SLOs for freshness and availability with alerts; health endpoints used by a monitor; runbooks;
backups tested by restore; no single point of failure for what matters; graceful degradation.

Check: one Windows PC runs everything (power, logon-only tasks, updates); `install-services.ps1` S4U vs interactive
tasks; `OPS_ALERT_URL` / `OPS_DIGEST_URL` set or not; `/healthz?strict=1` wired to a monitor?; `backup.py` + restore
drill (`logs/backup-drill.json`), backups off-disk (`OPS_BACKUP_COPY_TO`); what the web copy shows when the PC is off
for 3 days; rollback paths (publish, D1, Pages); log retention.
Evidence: RPO / RTO per component; a "PC is gone" walkthrough.

## Aspect 9 — Code quality and maintainability

**Best practice:** small modules with one job; generated code separated from templates; typed boundaries
(dataclasses / JSON Schema); lint + format; no dead code; clear ownership; commits that tell why.

Check: size and coupling of `build_*.py` (some > 2,000 lines with HTML/JS/CSS inline); duplicated logic between
builders and `model.py`; `_retired/` and backups in the tree; uncommitted changes (`git status`) and binary data in
the repo (`ops.db`, `state.db`, lake raw, `backups/`); config spread (`config.py`, env files, constants in builders);
naming consistency. Suggest the extraction order with the best payoff.
Evidence: a hotspot table (file → lines → change frequency from git → risk).

## Aspect 10 — Testing and quality gates

**Best practice:** test pyramid (unit for metrics, contract for API, end-to-end for views), golden datasets,
negative tests, deterministic fixtures, gates in CI not only on the host.

Check: what `verify_page.py`, `check_sync.py`, `check_app.py`, `check_d1_sync.py`, `check_kb.py`,
`check_ci_impact.py`, `check_mobile.py` cover and miss; is anything run outside the host (GitHub Actions)?; flaky
risks (headless Chrome virtual time, timing); a mutation-style test: break one block on purpose — which gate catches it?
Run the gates on the current `dist/` and report.
Evidence: a coverage matrix (risk → test → catches it yes/no).

## Aspect 11 — Cost, limits and scalability

**Best practice:** know every quota you depend on, measure headroom, design for 10× growth of the main driver.

Check: GitHub GraphQL / REST rate use per refresh (and with 740 PRs instead of 100); Buildkite API pages; Cloudflare
free plan: Pages files and size, Functions requests, KV ops, D1 rows read / written per day and DB size (verify the
current limits on Cloudflare's pricing pages; do not trust memory); refresh duration trend; page weight growth.
Evidence: a quota table (limit → current use → at 10× → action).

## Aspect 12 — Documentation, onboarding and governance

**Best practice:** a README that gets a new operator from zero to a refresh in < 1 hour; runbooks for every alert;
decision records (why D1, why stdlib, why split); data dictionary; named owners per source and per tab.

Check: `ops-app/README.md`, `deploy/README.md`, `CLOUDFLARE.md`, `HUONG_DAN_VAN_HANH.md` — accurate today? (try the
steps read-only); is there a glossary / data dictionary for every metric on the page; who owns what; how a change to
a metric is reviewed.
Evidence: an onboarding dry run log with every point where the docs were wrong or silent.

---

## Merge (final agent)

1. Collect the 12 reports. Remove duplicates (keep the one with the best evidence) and resolve contradictions by
   re-checking the evidence.
2. Produce: **(a)** a scorecard (aspect → score → top risk); **(b)** a single ranked list of P0 / P1 findings;
   **(c)** a 30 / 60 / 90-day roadmap where each item names the finding numbers it closes, its effort and its owner role;
   **(d)** the keep-list.
3. Mark every finding you could not reproduce as **unverified** instead of dropping or upgrading it.
