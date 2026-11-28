# Release Desk on a self-hosted server

This folder holds what is needed to run the LMCache Release & CI Ops page on our own Windows host, in place of the
GitHub Pages copy (https://travisvux.github.io/LMCache/). The page is the same: same 3 views, same tabs. Only where
it is served from changed.

## What runs

| Part | What | Where |
|---|---|---|
| `ops-app-server` (scheduled task) | `backend/server.py`: Python stdlib, read-only. Serves `releases/<CURRENT>/site` and the API from that release's `ops.db` | `127.0.0.1:8765` (local only) |
| `ops-app-caddy` (scheduled task) | Caddy 2: TLS (Let's Encrypt), basic auth, gzip/zstd, refuses every method except GET/HEAD | `:80`, `:443` → `127.0.0.1:8765` |
| `ops-app-refresh` (scheduled task) | `refresh.ps1`, mode C: collect → build → check → publish | daily at 07:00 host time = 07:00 Viet Nam time (host is UTC+7); `install-services.ps1 -RefreshEveryMin 60` = hourly |
| `ops-app-backup` (scheduled task) | `backup.py`: `data/ops.db` and `etl/lake/state.db` → `backups/<date>/`, keeps 14 | daily 03:00 |

All 4 tasks run as a normal user (not admin, not SYSTEM). They start at boot without anyone logged on.
The server and Caddy restart within 1 minute if they stop.

## Files

| File | What |
|---|---|
| `Caddyfile` | Reverse proxy: TLS, auth, gzip, security headers, access log (`logs/caddy-access.log`, 10 MB × 5) |
| `ops-app.env.example` | Settings and secrets template. Copy it to `ops-app.env` (git-ignored, ACL locked by the installer) |
| `install-services.ps1` | Installs or updates the 4 tasks and the firewall rule. Run as administrator. `-Uninstall` removes them |
| `run-server.ps1`, `run-caddy.ps1` | Start the server or Caddy by hand (for debugging) |
| `refresh.ps1` | Mode C refresh. `-Offline` rebuilds from local files only (no GitHub or Buildkite calls) |
| `publish.py` | `publish` / `rollback` / `list` / `scan`. The only way a build goes live |
| `sync.ps1`, `sync.sh` | Mode A: build on another PC, then publish into the host's `releases/` share |
| `backup.py` | SQLite backups and restore |
| `common.ps1` | Paths, Python and Caddy lookup, loads `ops-app.env` (for the other scripts) |

## Install (once)

| # | Step | Command / note |
|---|---|---|
| 1 | Get the code | `git clone --single-branch --branch release-desk --depth 1 https://github.com/travisvux/LMCache.git release-desk`, then `git config core.autocrlf false`, then `git clone https://github.com/LMCache/LMCache third_party/LMCache` |
| 2 | Python 3.11+ and Caddy | `winget install -e --id Python.Python.3.13 --scope user` and `winget install -e --id CaddyServer.Caddy`. No `pip install` needed |
| 3 | Copy the raw baseline files (once) | From the old PC copy `plan-2026-11/outputs/P1/raw/` and `plan-2026-11/outputs/P1_2026-10-17/raw/` to the same paths here. They are not in git (up to 90 MB). **Without them `verify_page` fails, so every refresh is refused** (the live build stays as it is). On this host only `fail_signatures.json` was rebuilt (from the `gh-pages` branch, see `P1/raw/SOURCE.md`); that is enough for `verify_page` to pass |
| 4 | DNS and ports | A DNS name (A record) points to the public IP. The router forwards TCP 80 and 443 to this PC. Port 80 is needed for the Let's Encrypt check |
| 5 | Settings | `copy ops-app.env.example ops-app.env`, then fill in `OPS_DOMAIN`, `OPS_AUTH_USER`, `OPS_AUTH_HASH` (`caddy hash-password --plaintext '<password>'`), `GH_TOKEN`, `BUILDKITE_API_TOKEN` |
| 6 | First release | `python -X utf8 publish.py publish --note "first"` (publishes the current `dist/` + `data/ops.db`) |
| 7 | Tasks | In an **elevated** PowerShell: `powershell -ExecutionPolicy Bypass -File install-services.ps1` (options: `-RefreshAt 07:00,19:00`, `-NoRefresh` for mode A/B) |
| 8 | Check | `curl.exe -s https://<domain>/healthz`, then open `https://<domain>/` and log in |

## Start / stop

| Action | Command (PowerShell) |
|---|---|
| Status | `Get-ScheduledTask ops-app-* \| Get-ScheduledTaskInfo \| ft TaskName,LastRunTime,LastTaskResult,NextRunTime` |
| Stop / start the site | `Stop-ScheduledTask ops-app-server`, `Start-ScheduledTask ops-app-server` (same for `ops-app-caddy`) |
| Refresh now | `Start-ScheduledTask ops-app-refresh`, or run `refresh.ps1` by hand |
| Logs | `ops-app/logs/`: `access.log` (server), `caddy-access.log`, `refresh-<time>.log` (last 30 are kept) |
| Health | `GET /healthz` (no login): `ok`, `status` (ok / stale / db error), release name, page build time, data age per source, `stale` list (older than 48 h). `ok` is false when any source is stale; `/healthz?strict=1` answers 503 then (use it for an uptime monitor); a broken DB is always 503. Through the proxy it leaves out the Python version and git sha |
| Refresh outcome | `logs/last-refresh.json`: status `ok`, `warn` (GitHub only: Buildkite data not refreshed), `failed` or `busy`. Set `OPS_ALERT_URL` (an ntfy topic or a webhook taking a plain-text POST) to get one line for every run that is not `ok`. Each step is killed after `-StepTimeoutMin` (40) minutes |
| Publish safety | `publish.py` holds `releases/.publish.lock` (one publish or rollback at a time, whoever starts it), checks free disk, scans `dist/` and `ops.db` (hits are printed as file + rule + hash, never the text), retries the `CURRENT` switch while Windows holds the file, refuses `--keep` below 2 and a rollback to an incomplete release |
| User-level tasks (no admin, this host) | `ops-app-server` at logon, restart every minute on failure (`run-server.ps1`); `ops-app-backup` daily 06:30 (`run-backup.ps1`: backup + restore drill into a temp folder, result in `logs/backup-drill.json`); `ops-app-refresh` daily 07:00. They run while the user is logged on; `install-services.ps1` (admin) makes S4U tasks that also run when logged off |
| Backups off this disk | set `OPS_BACKUP_COPY_TO` to a folder on another disk / NAS / synced drive; until then the run says "backups stay on this disk only" |
| Alerts | `OPS_ALERT_URL` (ntfy / webhook) for every run that is not ok; without it a failed or busy refresh shows a local pop-up (`msg.exe`), nothing leaves the machine. `/healthz` shows `last_refresh` and is `ok:false` after a failed refresh |
| Exposure | Caddy answers only `OPS_ALLOW_IPS` (default private ranges + Tailscale 100.64.0.0/10); prefer Tailscale / Cloudflare Access to a router port-forward |
| Release decisions | `backend/decide.py record <blocker> --action post1\|upload\|known_issue\|accept --reason … --by …` (append-only table `release_decision`); known issue / accepted gap stop gating; the banner shows the decision | 
| Daily digest | `deploy/digest.py` after each refresh: `logs/digest-<day>.md` (verdict, top blocker + owner role, rebase, red gates, oldest data); posted only if `OPS_DIGEST_URL` is set |
| Web access (no domain) | Cloudflare Pages + Access: `pages.py deploy` uploads `releases/CURRENT/site` (never ops.db) only after a privacy scan and a check that `<project>.pages.dev` and its preview names answer with an Access sign-in; `OPS_PAGES_AUTO=1` runs it after each refresh. Steps in [CLOUDFLARE.md](CLOUDFLARE.md) |
| Web access (own domain) | Cloudflare Tunnel + Access (company e-mail domain, one-time PIN): `run-tunnel.ps1`, steps in [CLOUDFLARE.md](CLOUDFLARE.md); server.py answers 403 to tunnel requests that did not pass Access |
| Server hardening | Host must be localhost or `OPS_DOMAIN` / `OPS_ALLOWED_HOSTS` (DNS rebinding); X-Forwarded-For trusted from 127.0.0.1 only; dotfiles and `:` stream names refused; 15 s idle timeout; Caddy adds CSP and Permissions-Policy |

## Update data

| Mode | How | Network |
|---|---|---|
| **C (chosen)**: scheduled on the host | `ops-app-refresh` runs `refresh.ps1`. Order: `observe_collect`, `observe_ops_collect`, `overlap_collect`, `mp_pr_collect` (`--no-build`), `collect_release`, `collect_weekly`, `ingest_files`, `build_page`, `verify_page` (must PASS), `build_today`, `export_static`, `check_app` (all views OK), `publish.py` | GitHub (via `GH_TOKEN`) and Buildkite, read-only |
| B: by hand on the host | `refresh.ps1` (same steps). For a rebuild without network use `refresh.ps1 -Offline` (sets `NR_NO_GH=1`, `TRD_NO_GH=1`) | yes / no |
| A: built on another PC | Share `ops-app\releases` on the host, then on the build PC run `sync.ps1 -HostReleases \\HOST\share` (or `sync.sh /mnt/share`) | no |

**Frontend / data split (2026-11-27).** `export_static.py` runs `backend/split_page.py`: `index.html` and `legacy.html`
are the frontend only (~1 MB, no data); every tab's data is in `data/<build>/<id>.json` (`<build>` = hash of the data,
so the path changes when the data changes and is cached as immutable) plus `data/manifest.json` (no-cache). Open pages
poll the manifest every 5 minutes and show "New data is live · Reload" when a newer build is published, locally or on
Pages. The builders and `verify_page.py` still work on the single page in `plan-2026-11/`; only the published copy is
split. The split page needs HTTP (`server.py`, Caddy or Pages), not `file://`.

**One snapshot everywhere (2026-11-27).** Each refresh is one sync run (`backend/sync_run.py`, table `sync_run` in
ops.db, id in `RD_RUN_ID`). Order: collectors (+ `etl_window`: the ETL lake and the shared baseline `P1_full`) →
build → `verify_page` → `export_static` → **`check_sync`** (every tab from one collector snapshot, one baseline window,
the same stable release / merged-in-24 h / open-PR counts, no future or zone-less times, PR Inspector on origin/dev;
FAIL = nothing goes live; known gaps go to `manifest.json` `partial_errors`) → `check_app` → `publish` →
**`d1_push` + `d1_verify`** → `pages_deploy`.

| Database copy on Cloudflare | |
|---|---|
| What | `deploy/d1_sync.py` copies the live release's `ops.db` to Cloudflare D1 (`OPS_D1_DB`). Each ops.db table `t` is `h_t` in D1 with `_from` / `_to` snapshot numbers, and a view `t` shows the current snapshot, so ops.db's queries and views run unchanged there |
| Atomic | a push writes only changed rows (invisible until the switch), then ONE `UPDATE rd_meta` makes the new snapshot current. A push that stops half way is invisible and is cleaned by the next push. `d1_sync.py rollback [--to N]` goes back (last `OPS_D1_KEEP`=7 kept) |
| Public window | the local `ops.db` keeps all history; D1 (the public copy) gets only the last `OPS_D1_DAYS`=90 days, counted from the snapshot time. Event tables by their own time (`pr`, `wf_run`, `bk_build`, `kpi_daily`, …), child tables follow their parent (`pr_label` → `pr`, `wf_job` → `wf_run`), open PRs always kept, definition / state / KB tables whole. `d1_sync.py verify` compares with the same window. `OPS_D1_DAYS=0` = everything |
| Cost | first push ~27k rows (~10 min); a daily push writes only the delta (no change: 13 calls, ~15 s). `d1_verify` compares every row hash (~1 min) |
| If it fails | the local site stays live, D1 keeps its last snapshot, `last-refresh.json` says `warn` and the run is `partial` |
| API (same shape on the release PC and on Pages) | `GET /api/sync-status` → `{sync_id, label, last_synced_at, sync_status, partial_errors, data_build, page_build, in_sync}`; `GET /api/db` (tables, views, columns); `GET /api/db/<name>?tag=&branch=&env=&range=30d&since=&until=&<column>=&limit=&offset=` (rows of one snapshot, header `X-Sync-Id`); `POST /api/sync` (= `/api/refresh`) |
| Page | the header shows the sync status (Synced / partial / Syncing / Error · time · snapshot #) from `/api/sync-status`; a newer data build shows "New data is live · Reload" |
| Setup (once) | `d1_sync.py init` → put `OPS_D1_DB=…` in `ops-app.env` → `d1_sync.py push` → `d1_sync.py bind` (binding `RD_DB` on the Pages project; checks no other binding or secret was lost) → `pages.py deploy` (uploads the functions in `pages-functions/`) |
| Tests | `tests/check_d1_sync.py` (delta, half-way push, rollback, new column, views equal), `tests/check_sync.py` (cross-tab gate) |

Without a GitHub login (`GH_TOKEN` or `gh auth login`) `refresh.ps1` stops before the first collector.
Without `BUILDKITE_API_TOKEN` it runs **GitHub only**: `overlap_collect` and `collect_release` (tags, publish runs, PyPI,
Docker Hub). `observe_collect`, `observe_ops_collect`, `mp_pr_collect` and `collect_weekly` are skipped, because without a
token they still exit 0 but write snapshots with the Buildkite half empty. The Buildkite files keep their last values and
the page marks them `STALE` after 48 h. The release note says `scheduled refresh (GitHub only)`.

Task created on this host on 2026-11-24 without admin rights: `ops-app-refresh`, daily 07:00, logon type *Interactive*
(it runs only while this user is logged on; if the PC was off it runs at the next logon). Run `install-services.ps1` as
administrator to replace it with the S4U version that runs without anyone logged on.
If any step fails, nothing is published and the last good build stays live. The reason is in `logs/refresh-<time>.log`.
The page itself never calls GitHub or Buildkite. There is no refresh button and no token in the browser.
The Trace Agent (paid LLM runs) is **not** part of the schedule.

## How a build goes live (`publish.py publish`)

| # | Step | Why |
|---|---|---|
| 1 | Privacy scan of `dist/`: local user paths, the old PC name, e-mails (except `git@github.com` / noreply), GitHub, Buildkite and Anthropic tokens, files > 15 MB | Any hit stops the publish. Extra words: `OPS_PRIVACY_WORDS` in `ops-app.env` |
| 2 | Copy to `releases/.staging-<time>/` (`site/`, `ops.db` via the SQLite backup API, `release.json`) | Never served while it is being copied |
| 3 | Rename to `releases/<time>/` | |
| 4 | Write `CURRENT.tmp`, then rename it over `CURRENT` | Atomic: each request sees the old build or the new one, never half of each |
| 5 | Keep the newest 5 (always the live one and the one before it) | Rollback |

## Rollback

| Action | Command (in `deploy/`) |
|---|---|
| List builds (`*` = live) | `python -X utf8 publish.py list` |
| Back to the previous build | `python -X utf8 publish.py rollback` |
| To a given build | `python -X utf8 publish.py rollback --to 20261123T094935Z` |

No restart is needed. The server reads `CURRENT` on every request.

## Backup and restore

| Action | Command (in `deploy/`) |
|---|---|
| Backup now | `python -X utf8 backup.py` → `ops-app/backups/<YYYY-MM-DD>/` (integrity checked, 14 days kept) |
| Restore | Stop `ops-app-refresh`, then run `python -X utf8 backup.py --restore 2026-11-20 [--what ops]`. The old file is kept as `*.db.before-restore`. Then run `refresh.ps1 -Offline` to rebuild the page from the restored DB |

## Server options (`backend/server.py`)

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address. Keep it local: Caddy is the only public entry |
| `--port` | `8765` | |
| `--root` | `live` | `live` = sources as on the old PC. A folder with `CURRENT` = release mode. Any other folder = a static site such as `dist/` |
| `--db` | the release's `ops.db` | SQLite file for `/api/*`, opened read-only (`mode=ro`, `query_only`) |
| `--log` | stderr | Access log file, rotated at 10 MB, 5 kept |

Caching: HTML gets `no-cache` (always revalidated by ETag, so a new build shows at once). `outputs/*`, css, js and
static `api/*.json` get `max-age=300`. Every response has an `ETag` and `Last-Modified`. Any path with a `..`
segment gets 400. `/api/sql` only answers the 5 listed views.

## Checks

| Check | Command | Result on this host (2026-11-23) |
|---|---|---|
| All views, console + 390 px | `python -X utf8 tests/check_app.py --base http://127.0.0.1:8765 --site releases/<CURRENT>/site --lang en` (and `--lang vi`) | 18/18 OK in both EN and VI |
| Same page as GitHub Pages | compare `data-view`/`data-tab` sections | 28 tabs, 59 sections, same |
| Privacy | `python -X utf8 publish.py scan releases/<CURRENT>/site` | 0 hits |
| Read-only API | `POST` → 405 (Caddy) / 501 (server); write through the read-only connection is refused by SQLite | ok |
| Traversal | `/outputs/../index.html`, `%2e%2e`, `..%5c` | 400 |
