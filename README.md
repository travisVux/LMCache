# Release Desk workspace (branch `release-desk`)

Source and data of the LMCache Release & CI Ops page (https://travisvux.github.io/LMCache/), packed so a host machine can serve it.
This branch is an orphan: it has no LMCache history. Same folder layout as the original workspace (paths in the code are relative).

## Get it on the host

```bash
git clone --single-branch --branch release-desk --depth 1 https://github.com/travisvux/LMCache.git release-desk
cd release-desk
git config core.autocrlf false        # 06_PR_TO_CI_VISUAL.html must stay CRLF, byte-exact
```

Then follow `LM-762-ci-resource/ops-app/docs/HOST_SERVER_PROMPT.md`.

## What is here / what is not

| Path | In this branch |
|---|---|
| `LM-762-ci-resource/ops-app/` | yes: backend, frontend, `dist/`, `data/ops.db` |
| `LM-762-ci-resource/plan-2026-11/` | yes: the page + builder chain; **without** `outputs/P1*/raw/` (up to 90 MB files; regenerate with `etl.py window`) |
| `LM-762-ci-resource/etl/` | code only; **no `lake/`** (raw API responses, not published). Backfill on the host if needed |
| `release-0.5.8/` | yes (RELEASE_PREP.md, ROADMAP.md) |
| `knowledge/` | only the 2 files the builders read (feature matrix xlsx, Trace Agent prompt) |
| `third_party/LMCache` | **no**: clone it on the host: `git clone https://github.com/LMCache/LMCache third_party/LMCache` |

Local paths in logs / prompt files were rewritten to `<workspace>` / `<home>`.
Collectors need tokens on the host (`gh auth login`; Buildkite token): `observe_collect.py` reads it from a local file — change that to an env var on the host.
