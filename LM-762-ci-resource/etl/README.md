# CI data ETL

This ETL fetches CI data once and keeps it. Any later window only fetches what is missing, what changed, or what failed. It replaces the one-shot fetch scripts in `plan-2026-11/outputs/P1*/fetch_*.py`.

The transforms that compute the numbers did not change. They still read the same files.

```
 SOURCES (APIs)             LAKE (etl/lake/)                    SINK                         TRANSFORMS (unchanged)
 Buildkite REST   ──┐       raw/<source>/<key>.json.gz          export --window ──► P1 folder ──► build_jobs_table.py
 GitHub GraphQL   ──┼──►    state.db  (one row per partition:              (raw/*.json,        sample_fail_logs.py
 GitHub REST      ──┘        status, attempts, fetched_at,                 window.json)        aggregate.py
                             final, watermark, error)                                          build_pr_table.py
                            cache/  (log evidence)                                             ──► build_report1130.py
```

## Code layout

| Path | What it does |
|---|---|
| `etl.py` | Command line: `status`, `update`, `backfill`, `retry`, `ingest-legacy`, `export`, `window` |
| `core/http.py` | HTTP client with retry and rate-limit handling, for Buildkite REST, GitHub REST and GitHub GraphQL |
| `core/lake.py` | Partition files (atomic write) and the SQLite state table |
| `core/pipeline.py` | `Source` contract, and the runner that decides what to fetch, fetches in parallel and records failures |
| `sources.py` | The 4 sources: `bk_builds`, `gh_prs`, `gh_commits`, `gh_run_jobs` |
| `sinks.py` | Exports a window from the lake to the P1 file format. Also loads old P1 folders into the lake |
| `transforms/p1/` | The single source of truth for the P1 transform scripts. `window` copies them into the output folder |
| `lake/` | Data only (not code). Safe to delete; it can be rebuilt with `backfill` |

## Sources and partitions

Sources run in this order, because each one plans its partitions from what the earlier ones stored.

| Source | API | Partition key | Final (never fetched again) when |
|---|---|---|---|
| `bk_builds` | Buildkite `builds?created_from&created_to` | `<pipeline>/<UTC day>` | fetched at least 3 days after the day ended, and no build was unfinished |
| `gh_prs` | GraphQL: PR, last 100 commits, every check suite / run | `<PR number>` | PR is closed, fetched at least 1 day after its last change, and every suite has concluded |
| `gh_commits` | GraphQL `object(oid)` for commits that Buildkite built but the PR no longer lists (force-push) | `<sha>` | fetched at least 1 day after its last suite change, and every suite has concluded |
| `gh_run_jobs` | REST `actions/runs/{id}/jobs?filter=all` | `<run id>` | every job is completed |

A partition is fetched again when:
- it is **new**;
- its last fetch **failed**;
- it is **not final** yet (recent or still running);
- its **watermark moved**: the PR or suite `updatedAt` is later than our last fetch, for example a re-run;
- `--refresh` is given.

## Retry and failure rules

| Level | What happens |
|---|---|
| HTTP request | 5xx, timeout or network error: backoff 2, 4, 8 … up to 120 s, max 8 tries. Rate limit spent: sleeps until the reset time (this does not count as a try). 401/403/404/422: no retry |
| Partition | An error is written to `state.db` (`status=failed`, `attempts+1`, `error`), and the run continues with the other partitions. After 5 failed attempts the status is `dead`, and it is only retried with `retry --dead` |
| Whole run | Safe to stop at any time. Each partition is written atomically, so the next run continues where it stopped |

Before this ETL, one GitHub `HTTP 504` stopped `fetch_gh_checks.py`, and all ~1,100 PRs had to be fetched again.

## Commands

```
cd LM-762-ci-resource/etl
python -X utf8 etl.py status
python -X utf8 etl.py update   --since 2026-10-17 --until 2026-11-16 --dry-run   # what would be fetched, and why
python -X utf8 etl.py window   --since 2026-10-17 --until 2026-11-16 --out ../plan-2026-11/outputs/P1_2026-10-17
python -X utf8 etl.py retry                                                       # only failed partitions
python -X utf8 etl.py backfill --since 2026-09-01 --until 2026-10-17              # older range, same rules
python -X utf8 etl.py ingest-legacy ../plan-2026-11/outputs/P1                    # load an old P1 folder (keeps newer lake data)
```

`--until` is exclusive. All dates are UTC days. The `ETL_LAKE` variable moves the lake to another folder.

## Cost of a new 30-day window

| Data | First time | Next window (shifted by a few days) |
|---|---|---|
| Buildkite builds | 60 day-partitions, about 10 min | only new days, plus the last 3 days that are not final yet |
| GitHub PRs | about 1,100 PRs | only PRs that are new, open, or changed since the last fetch |
| GitHub run jobs (runner queue) | about 13,000 runs, about 2.7 h (5,000 REST calls per hour) | only new runs, plus runs that were re-run |

## Rules for adding a source

1. Subclass `Source` in `sources.py` and set `name` and `workers`.
2. Write `plan(ctx, since, until)` so it returns `Part(key, day, watermark)`.
3. Write `fetch(ctx, part)` so it returns `(payload, rows, watermark, final)`.
4. Strip secrets in `fetch` before returning (`env`, pipeline config).
5. Add the source to `SOURCES` in run order.
6. If a transform needs the data, add the export to `sinks.export_window`.
