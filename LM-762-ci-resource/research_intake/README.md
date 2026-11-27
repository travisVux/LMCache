# Research intake (contract v1)

The Research App (a separate 8-GPU pipeline, out of scope here) drafts a PR and a benchmark report. It hands the
report to the Release Desk as **one JSON file**. There is no network service: the app writes a file, the page build
reads it.

| Item | Where |
|---|---|
| Contract | `research_report.schema.json` (`lmcache.research_report/v1`, closed: unknown fields are refused) |
| Drop folder | `inbox/` — put `<id>.json` here |
| Validator | `python -X utf8 validate.py inbox/*.json` (stdlib, exit 1 if a file fails) |
| Loader | `plan-2026-11/outputs/cpu_tests/build_research.py` (runs in `build_page.py`) |
| Examples | `samples/` (3 files, one per context, `"sample": true`, shown with a SAMPLE badge; `RESEARCH_SAMPLES=0` hides them) |
| Test | `python -X utf8 check_intake.py` |
| Page | Release Management → **Research intake** (`#obs/research`) |

## The 3 contexts

| `context` | Question the report answers |
|---|---|
| `CI Validation` | Does a CI change keep the gates honest (same coverage, pass rate, time)? |
| `LMCache optimization` | Is LMCache faster or cheaper without losing correctness? |
| `New product feature` | Does the new feature work end to end, and what does it cost? |

## Fields

| Field | Required | Rule |
|---|---|---|
| `schema` | yes | `lmcache.research_report/v1` |
| `id` | yes | `rr-` + lower case letters, digits, dashes; the file name is `<id>.json` |
| `context` | yes | one of the 3 above |
| `title`, `summary` | yes | plain text (8–160, 20–2000 characters) |
| `created_at` | yes | UTC, `2026-11-24T06:00:00Z` |
| `source` | yes | `app`, `run_id`, optional `pipeline` |
| `pr` | no | `number`, optional `title`, `branch`, `state` (draft, open, merged, closed). The page opens the PR Inspector |
| `features`, `areas` | no | `F01`–`F17`; code area ids (`smcore`, `p2p` …) |
| `environment` | yes | `gpus` (0–8), `engine` (vllm, sglang, trtllm, none), optional GPU model, engine version, model, `lmcache_commit` |
| `benchmark` | yes | `name`, `runs`, `metrics[]`: `name`, `unit`, `baseline`, `candidate`, `better` (higher / lower) |
| `ci.gates[]` | no | `name`, `result` (passed, failed, not_run, flaky), optional https `url` |
| `verdict` | yes | improves, regresses, neutral, inconclusive |
| `artifacts[]` | no | `label` + **https** `url` only |

## Refused (privacy and safety)

| Check | Why |
|---|---|
| E-mail address anywhere | no personal data on the page |
| Local path (`C:\...`, `/Users/...`, `/home/...`) | no local paths in anything served |
| Token (`ghp_`, `github_pat_`, `bkua_`, `sk-ant-`) | no secrets |
| Non-https link, unknown field, file name ≠ id | the contract is closed and links must be public |

A refused file is never shown as a report; the page lists its file name and the first errors under the contexts.
