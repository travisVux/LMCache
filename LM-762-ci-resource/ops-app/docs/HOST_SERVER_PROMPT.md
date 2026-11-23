# Prompt: move the Release Desk from GitHub Pages to a self-hosted web server

Copy everything below the line into the agent on the NEW host machine.

---

## Role and goal

You are a coding agent on a new host machine. Your job: build and run a web server that hosts the
LMCache "Release & CI Ops" UI and its data, replacing the GitHub Pages copy at
https://travisvux.github.io/LMCache/ (repo `travisvux/LMCache`, branch `gh-pages`).

Today the page is a static build: data is baked into the HTML at build time (`<script type="application/json">`
blocks) plus files under `outputs/` and `api/*.json`. On the new machine the same UI must be served by a real
server, with the data (SQLite + JSON files) living on that machine.

## Fill in before you start (ask the user if a value is empty — ask all at once, then do not stop again)

| Key | Value |
|---|---|
| HOST_OS | (Linux distro / Windows) |
| ACCESS | internal LAN only / VPN / public internet |
| DOMAIN / IP | |
| TLS | none (LAN) / Let's Encrypt via Caddy / existing cert |
| AUTH | none / basic auth / SSO proxy |
| DATA_REFRESH | (A) built on the old PC and copied over (default) · (B) collectors run on the host by hand · (C) scheduled on the host |
| TOKENS ON HOST | gh CLI login? Buildkite API token? (only needed for B/C) |
| KEEP GH PAGES | yes (both live) / no (turn off after cutover) |

## What exists (source workspace, copy it with the same folder layout)

Workspace root = `CacheAgent/`. Paths in `ops-app/backend/config.py` are relative (`WORKSPACE = APP.parents[1]`),
so keep this tree shape:

| Path | What | Size |
|---|---|---|
| `LM-762-ci-resource/ops-app/` | Release Desk: `backend/` (stdlib Python: `server.py`, `model.py`, `db.py`, `schema.sql`, `collect_*.py`, `export_*.py`, `legacy.py`), `frontend/`, `dist/`, `tests/check_app.py`, `docs/ERD.md` | dist ≈ 37 MB |
| `LM-762-ci-resource/ops-app/data/ops.db` | SQLite history store (releases, artifacts, publish runs, weekly runs, snapshots) | |
| `LM-762-ci-resource/plan-2026-11/06_PR_TO_CI_VISUAL.html` | The main page (3 views: Release Management · Exploration · Report 1130) | |
| `LM-762-ci-resource/plan-2026-11/outputs/` | Page builder chain (`cpu_tests/build_*.py`, `build_page.py`, `verify_page.py`) and the JSON it reads (`observe_snapshot.json`, `release_desk.json`, `trace_agent/proposals.js`, …) | |
| `LM-762-ci-resource/etl/` | ETL: `etl.py`, `core/`, `sources.py`, `sinks.py`, `lake/` (raw `*.json.gz` + `state.db`) | ≈ 26 MB |
| `third_party/LMCache` | git clone of LMCache/LMCache, read by `build_ops_tabs.py` | |
| `release-*/RELEASE_PREP.md` | Read by `ingest_files.py` | |

Current server (`ops-app/backend/server.py`, Python 3.13 stdlib `ThreadingHTTPServer`):
- `/` and `/index.html` → the 3-view page
- `/shell.html`, `/legacy.html` (page in embed mode, `legacy.py`)
- `/outputs/*` → relative links of the page
- `GET /api/overview`, `/api/history`, `/api/release/<tag>`, `/api/sql?view=v_…` (read-only, whitelisted views)
- It binds to `127.0.0.1:8765` only.

## Rules you must keep (user decisions — do not change them)

1. **Upgrade, don't replace.** Keep every view and tab of the page as it is. The server feeds the existing page;
   do not write a new UI or drop tabs.
2. **No browser-side refresh.** No Refresh button, no auto refresh, no tokens in the browser, no live GitHub /
   Buildkite calls from the page (`CONFIG.local_only=True` in `build_observe.py` stays). Data changes only when a
   person runs the collectors/builders on a machine (DATA_REFRESH A or B). A schedule (C) only if the user
   explicitly picks C. Never add a GitHub Action or Buildkite step that refreshes or deploys this data.
3. **No network calls without the user's yes.** For a local-only rebuild set `NR_NO_GH=1` and `TRD_NO_GH=1`.
   Collectors that hit the network: `collect_release.py`, `collect_weekly.py`, `observe_collect.py`,
   `observe_ops_collect.py`, `overlap_collect.py`, `mp_pr_collect.py`, `etl.py window`.
4. **Stdlib first.** Backend stays Python stdlib (no `pip install` needed to run). A reverse proxy
   (Caddy or nginx) in front is fine and is where TLS, gzip and auth go.
5. **Never hand-edit `06_PR_TO_CI_VISUAL.html`.** It is generated (CRLF line endings). Rebuild it with the whole
   chain (`build_page.py`, then `verify_page.py`); never run `build_gates` / `build_onboarding` / `build_observe`
   alone. Exclude it from format-on-save.
6. **Privacy.** No personal email, tokens, or local paths (`C:/Users/...`, user names) in anything served.
   Rewrite them to `<workspace>` / `<home>` and grep the served tree for them = 0 before going live.
   `etl/lake/` and raw P1 JSON files > 15 MB are not served.
7. Docs in simple English with scannable tables. Chat with the user in Vietnamese.

## Work plan

### Phase 0 — inventory (read-only, no network)
- Read `ops-app/README.md`, `ops-app/docs/ERD.md`, `backend/server.py`, `backend/legacy.py`, `backend/export_static.py`, `etl/README.md`.
- Check Python version (3.13 used on the old PC; 3.11+ should work — verify), `sqlite3` version, git, gh.
- Grep the copied tree for absolute Windows paths and `<user>`; list any that the server or builders use
  (known: some old scripts under `ci-analysis/` and `ci-gate-rfc/` — not needed by the server).
- Output: a short table "what runs where" + gaps. Then continue.

### Phase 1 — run it as-is on the host
- Start `server.py` locally on the host, open every hash with `tests/check_app.py` (console errors at 1280 px,
  overflow at real 390 px). Fix only portability problems (paths, encoding: always `python -X utf8`, CRLF).
- Compare with the live GitHub Pages copy: same tabs, same sections, data differs only by build time.

### Phase 2 — production server
- Add to `server.py`: `--host` (default still `127.0.0.1`), `--port`, `--root` (serve from `dist/` or from live
  sources), `GET /healthz` (returns DB path, data age per source, build time), correct `Content-Type`,
  `ETag` / `Last-Modified` + `Cache-Control` (HTML: no-cache; `outputs/*`, css/js: short cache), gzip handled by proxy,
  path-traversal guard on `/outputs/*`, request log to a file with rotation.
- `/api/*` stays read-only. Open SQLite read-only (`file:...?mode=ro`, `uri=True`) in the request path.
- Reverse proxy config (Caddy preferred: auto TLS) in `ops-app/deploy/`: TLS, auth per AUTH, gzip, proxy to
  `127.0.0.1:8765`.
- Service unit: systemd (`ops-app.service`, restart on failure, non-root user) on Linux, or NSSM / Task Scheduler
  on Windows. Put files in `ops-app/deploy/`.

### Phase 3 — data path (per DATA_REFRESH)
- **A (default):** on the old PC run the chain (`build_page.py` → `verify_page.py` → `build_today.py` →
  `export_static.py`), then sync `dist/` + `data/ops.db` to the host. Write `ops-app/deploy/sync.ps1` (and `.sh`):
  privacy scan → copy to a new release folder `releases/<timestamp>/` → atomic switch of a `current` symlink /
  folder rename → keep last 5 for rollback. No half-copied state is ever served.
- **B:** same chain runs on the host by hand. Document the exact command order and env vars
  (`NR_NO_GH`, `TRD_NO_GH`), and that `gh` needs `--allow-escape-sequences` for job logs.
- **C:** only if chosen: a host-local scheduler runs B, writes a run log, and on failure keeps the last good
  build live (never serves a broken page). Show the data age badge as today (`STALE` after 48 h).
- Back up `ops.db` and `etl/lake/state.db` daily (sqlite `.backup`, keep 14).

### Phase 4 — cutover
- Smoke test on the host URL: every hash, EN/VI, light/dark, 390 px, `/healthz`, `/api/overview`.
- Privacy grep of the served tree = 0 hits.
- If KEEP GH PAGES = no: ask the user before touching `gh-pages` (push a small index.html that links to the new
  URL; keep the branch README.md). Do not delete the branch.

## Deliverables

| File | What |
|---|---|
| `ops-app/deploy/README.md` | Install, start/stop, update data, rollback, backup restore — simple English, tables |
| `ops-app/deploy/Caddyfile` (or nginx conf) | Proxy, TLS, auth |
| `ops-app/deploy/ops-app.service` (or Windows equivalent) | Service |
| `ops-app/deploy/sync.ps1`, `sync.sh` | Data sync with privacy scan + atomic switch (mode A) |
| `server.py` changes | host/port/root flags, `/healthz`, caching headers, read-only DB, traversal guard |
| Test output | `check_app.py` all hashes green on the host URL |

## Done when
- The host URL shows the same 3 views and all tabs as the GitHub Pages copy, with no console errors.
- Data age badge and `/healthz` show the right build time.
- One data update (mode A or B) goes live with an atomic switch, and a rollback to the previous build works.
- Privacy scan = 0, `/api/*` cannot write, `/outputs/../` is refused.

Report at the end: what is running (URL, service name, ports), how to update data, what is left open.
