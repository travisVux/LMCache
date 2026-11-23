# Proposal (draft): a database and a small web server for the Release & CI dashboard

Status: draft for discussion · 2026-11-13 · owner: release & CI (LM-762)

## 1. Why

Today the dashboard is one static HTML file. Local collectors write JSON / CSV files, Python generators embed them into
`06_PR_TO_CI_VISUAL.html`, and a person pushes it to GitHub Pages (https://travisvux.github.io/LMCache/).

| Problem today | Effect |
|---|---|
| Data is a snapshot | The Today tab is often 9–15 h old. A person must run 4 collectors + 11 generators, then push. |
| Everything is embedded | The page is 4.5 MB (entity index 1.1 MB, snapshot 0.5 MB). Every new view makes it bigger. |
| Fixed windows | Report 1130 is one 30-day window. Changing the window, pipeline or "queued time on/off" needs a rebuild. |
| No shared state | A reviewer cannot mark "done", add a note, or assign a decision. Two people see the same list and do not know who acts. |
| Fragile build | Order-dependent generators, nested CSS blocks, a formatter or a stray key press can break the page. |

## 2. Goal

1. Fresh data without a person: collectors run on a schedule and write to a database (DB).
2. Interactive views: any date window, filter or switch is a query, not a rebuild.
3. Shared actions: acknowledge a decision, add a note, assign an owner.
4. One logic: `decisions.py`, `build_entities.py` and the Report 1130 formulas stay the single source of rules.
5. Keep the public static page: GitHub Pages stays as a read-only export.

Not a goal (for now): replacing Buildkite / GitHub UIs, alerting, multi-repo support.

## 3. Decision needed first: this changes a current rule

The current rule is **"local runs only: no live API calls from the page, no tokens in the page, no CI/CD"**.
A web server keeps the spirit of that rule (tokens stay on the server, the browser never calls GitHub or Buildkite),
but data would update on a schedule instead of on a person's local run. Please choose one hosting option:

| Option | Where it runs | Who can use it | Fits the current rule? | Effort |
|---|---|---|---|---|
| **A. Local** (recommended to start) | the release owner's machine, `http://localhost:8080` | 1 person | yes: still a local run, now automatic | low |
| A2. Local + shared through a tunnel | the release owner's machine; a tunnel gives the team a login-protected URL (see 3.1) | the team, while the machine is on | partly: still local, but others can reach it | low |
| B. Team VM | a small internal VM, behind GitHub login | the team | partly: needs the team's OK | medium |
| C. Static export only | DB on the local machine, page exported to GitHub Pages | everyone, read-only | yes | low (keeps today's link) |

Recommendation: **A + C** first (local server for daily work, static export keeps the public link), then A2 or B when the team asks for shared actions.

### 3.1 Option A2: share the local server

The server listens only on `127.0.0.1`. A tunnel client on the same machine makes an outbound connection, so no inbound
port is opened and the home / office router is not changed. Every viewer must log in.

| Tunnel | Viewer needs | Login | Notes |
|---|---|---|---|
| **Cloudflare Tunnel + Cloudflare Access** (recommended if a domain is on Cloudflare) | a browser | email one-time code or GitHub, per allow-list | stable URL such as `ci.<domain>`; free for small teams |
| Tailscale (share the machine) | the Tailscale app, invited by the owner | Tailscale account | private network, no public URL at all; check the current free-plan user limits |
| ngrok with OAuth | a browser | Google / GitHub, per allow-list | quick to try; free URLs and limits change |

Not allowed: a public tunnel without login (for example a quick anonymous tunnel), or binding the server to `0.0.0.0` on an open network.

Steps (Cloudflare example):

1. Run the API server on `127.0.0.1:8080` (step S3 / S4 of section 7) in **read-only mode** first.
2. Install `cloudflared`, create a named tunnel to `http://127.0.0.1:8080`, map it to `ci.<domain>`.
3. In Cloudflare Access, add an application for `ci.<domain>` with an allow-list of team emails.
4. Run `cloudflared` and the server as Windows services, so they start after a reboot; stop the machine from sleeping while sharing.
5. Turn on write actions (S5) only after login works; each action stores the logged-in email (Access sends it in a header).

Limits: the page is down when the machine is off or asleep; one machine is a single point of failure;
check that company policy allows running a shared service from this machine. Move to option B when this hurts.

## 4. Architecture

```
GitHub API ─┐                         ┌─► FastAPI server ──► browser (dashboard, interactive)
Buildkite API ├─► collectors (scheduled) ─► Postgres ┤
local git clone ─┘     upsert, incremental           └─► static export ──► GitHub Pages (read-only)
                                                      ▲
                          decisions.py · entity graph · Report 1130 formulas (Python, reused)
```

| Part | Choice | Why |
|---|---|---|
| DB | **PostgreSQL 16** in Docker (SQLite allowed for a first spike) | percentiles in SQL (`percentile_cont`), JSON columns, many readers + writers later; data is small (about 70k job rows / 30 days, < 5 GB / year) |
| Collectors | today's scripts, changed to **upsert into the DB**, incremental by `updated_at` / `created_from` | no new data logic; fewer API calls than full refreshes |
| Scheduler | Windows Task Scheduler (option A) or systemd timer (option B) | no CI/CD needed |
| API server | **FastAPI** (Python) | reuses `decisions.py`, `build_entities.py`, `report_model.py` directly |
| Front end | keep today's page JS; data comes from `fetch('/api/...')` instead of embedded JSON | no rewrite; the same tabs, cards and charts |
| Static export | a script renders the same page with data embedded from the DB | GitHub Pages keeps working |

## 5. Data model (first version)

| Table | Key | Main columns | Source today |
|---|---|---|---|
| `pr` | number | title, author, state, draft, review, mergeable, labels, created / merged at | `observe_snapshot.json`, `pr_30d.csv` |
| `pr_commit` | pr, sha | first CI at, pushes | `pr_commit_30d.csv` |
| `pr_file` | pr, path | status, patch hunks (open PRs) | `pr_files`, `overlap_patches.json` |
| `release` | tag | state (rc / stable), tagged at, previous tag | git tags, releases |
| `release_pr` | tag, pr | relation (contains / shipped_in) | git log of the tag range |
| `bk_build` | pipeline, number | state, branch, commit, pr, created / started / finished | snapshot, `ops_ci_24h.json`, `mp_pr_builds.json`, P1 |
| `bk_job` | job_id | build, label, workload, gpus, state, retried, retry source, **queue_wait_min, wall_min, gpu_min** | `jobs_all_30d.csv` |
| `gha_run`, `gha_job` | run id, job id | workflow, job, conclusion, attempt, exec_min, start_delay_min, required | `gh_jobs_30d.csv`, `ops_ci_24h.json` |
| `fail_signature` | job_id | signature, class (config / test / infra / unknown), log line | `P1/raw/fail_signatures.json` |
| `feature`, `test_file`, `workload` | id / path / name | area, tiers, 30-day fail % | `area_meta.py`, `cpu_tests.json`, `cost_by_workload.csv` |
| `entity_edge` | from, to, relation | strength, proof source | `build_entities.py` |
| `ta_finding` | tag, pr | class, impact, fix PR, report path | `trace_agent/proposals.json` |
| `decision` | object, verb | rule, short reason, computed at | `decisions.py` (computed) |
| `decision_action` | id | decision, who, action (ack / done / snooze / note), when | **new: human input** |
| `collector_run` | id | source, started / finished, rows, errors | **new: data freshness** |

## 6. API (read first, write later)

| Method · path | Returns | Replaces |
|---|---|---|
| `GET /api/today` | decision rows, counts, data age | `today.json` |
| `GET /api/entity/{kind}/{id}` | one card: node, up, down, evidence | `entities.json` (1.1 MB in the page) |
| `GET /api/releases` · `/api/releases/{tag}` | verdict per release, PRs, features, blockers | release verdict block |
| `GET /api/next-release` | scope items, IN / OUT / NEEDS TEST, evidence | `ops_tabs.json → coming.nr` |
| `GET /api/rebase-risk` | open PR vs merges, clash level, diff anchors | `ops_tabs.json → overlap` |
| `GET /api/cost?from=&to=&scope=merged&queued=1&system=gpu` | p50 / p90, histogram | Report 1130 (any window, not only 30 days) |
| `GET /api/retry/never-pass?from=&to=` | tries × outcome, top workloads | Report 1130 retry |
| `GET /api/freshness` | last run and age per collector | the "Data age" tile |
| `POST /api/decisions/{id}/actions` | ack / done / snooze / note | **new** |

Every response carries `data_at` (oldest source time), so the page can keep showing an honest data age.

## 7. Steps

| Step | What | Done when | Effort |
|---|---|---|---|
| **S0 Decide** | Hosting option (A / B / C), DB (Postgres vs SQLite), who uses it | Choices written in this file | 0.5 d |
| **S1 DB + backfill** | Docker Postgres, schema migrations (Alembic), loader from today's JSON / CSV files. No new API calls. | SQL gives the same Report 1130 numbers as `report1130.json` (p50 / p90 per view, equal to 0.1) | 2–3 d |
| **S2 Incremental collectors** | Collectors upsert into the DB; cursors per source; `collector_run` rows; schedule every 30 min (snapshot, 24 h CI) and nightly (30-day tables, logs) | Two runs in a row add only new rows; GitHub rate use < 20% of 5,000 / h | 2–3 d |
| **S3 Read API** | FastAPI app; endpoints of section 6; reuse `decisions.py` and the entity builder | Parity tests: API output equals `today.json`, `entities.json`, release verdicts for the same data | 3 d |
| **S4 Page on the API** | Page loads data with `fetch` (local mode); embedded data stays as the fallback; add a date-window picker and server-side switches | `verify_page.py` PASS in both modes; page < 1 MB in API mode | 3–4 d |
| **S5 Actions** | Ack / done / snooze / note on Today rows and cards; audit log | A done decision leaves Today for everyone until its data changes | 2 d |
| **S6 Export + ops** | Static export from the DB replaces the 11-step generator chain for GitHub Pages; backup of the DB; health page | One command builds and checks the static page; daily backup works | 2–3 d |
| S7 (option B only) | VM, GitHub login (oauth2-proxy), HTTPS; optional GitHub / Buildkite webhooks for near real-time | Team members log in; webhooks update a PR within 1 min | 3 d |

Total for A + C (S0–S6): **about 3 weeks** for one engineer. S7 adds about 3 days.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Two sources of truth during the move | Parity tests in S1 and S3; keep the static chain until S6 is proven for 1 week |
| SQL percentiles differ from Python ones | Use one definition (nearest rank, same as `pct()` today) and test it |
| API rate limits (GitHub 5,000 / h, Buildkite) | Incremental cursors; heavy 30-day jobs only at night |
| Tokens leak | Tokens only in server env vars; the browser never calls GitHub or Buildkite |
| Laptop off = no updates (option A) | The data-age tile stays; move to option B if this hurts |
| Scope creep into a product | Same tabs first; new views only from reviewer requests |

## 9. What stays the same

- The rules: `decisions.py` (verbs and rule text), entity relations, Report 1130 definitions (p90 first, queued time stated).
- The tabs, cards and charts the reviewers already use.
- The public link on GitHub Pages (read-only export).
