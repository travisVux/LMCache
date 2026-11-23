# ops-app data model (ERD)

One SQLite file (`data/ops.db`) holds the release and CI history. Schema: [`backend/schema.sql`](../backend/schema.sql).

## Design rules

| Rule | Why |
|---|---|
| Every fact keeps its natural key (tag, run id, job id, PR number, pipeline + build number) | Re-running a collector updates rows; history is never duplicated |
| Things that change over time are stored per snapshot or per day (`release_verdict`, `pr_state`, `kpi_daily`) | We can answer "what did we know on day X?" and draw trends |
| Every row points to the `snapshot` that last wrote it | Provenance: which run, which file, when |
| "What should ship" (`artifact_spec`) is separate from "what we saw" (`artifact`) | A red CI run is not the same as a missing artifact. The 0.5.8rc1 run was red, but the RC image was on Docker Hub |
| Analysis lives in SQL views (`v_*`) | The page and ad-hoc queries use the same definitions |
| No network in the page. Collectors run locally | Matches the local-only rule for the Ops page |

## Diagram

```mermaid
erDiagram
    snapshot ||--o{ release : "last wrote"
    release_line ||--o{ release : has
    release_line ||--o{ decision : "needs (D1..)"
    release_line ||--o{ blocker : "blocked by (C1.., #pr, ci)"
    release ||--o{ artifact : "seen in registry"
    artifact_spec ||--o{ artifact : "expected as"
    release ||--o{ wf_run : "publish runs (head_branch = tag)"
    workflow ||--o{ wf_run : runs
    wf_run ||--o{ wf_job : has
    release ||--o{ pr_release : contains
    pr ||--o| pr_release : "ships in"
    pr ||--o{ pr_feature : changes
    feature ||--o{ pr_feature : "changed by"
    pr ||--o{ pr_label : has
    pr ||--o{ pr_state : "open state per snapshot"
    bk_pipeline ||--o{ bk_build : has
    pr ||--o{ bk_build : "PR builds (pr = number)"
    bk_build ||--o| weekly_run : "weekly full suite verdict"
    release ||--o{ release_verdict : "verdict per snapshot"
    snapshot ||--o{ release_verdict : at
    snapshot ||--o{ pr_state : at

    release { text tag PK; text line FK; text kind "rc|final|post"; int seq; int sort_key; text sha; text published_at }
    artifact_spec { text code PK; text channel "pypi|gh|docker"; text package; int for_rc; int for_final }
    artifact { text release_tag PK; text spec_code PK; int present; int ok; text ref; text detail; text checked_at }
    wf_run { int run_id PK; int workflow_id FK; text event; text head_branch; text release_tag FK; text conclusion; int attempt }
    wf_job { int job_id PK; int run_id FK; text name; text conclusion; text error_line }
    bk_build { text pipeline PK; int number PK; text state; text branch; int pr; real wait_min }
    weekly_run { text pipeline PK; int number PK; text kind; text verdict; int required; int failed; int missing; int skipped }
    pr { int number PK; text title; text author; text created_at; text merged_at; text state }
    decision { text id PK; text line FK; text code; text question; text status; text choice }
    blocker { text id PK; text line FK; text kind "carryover|pr|ci|publish|artifact"; text status; text evidence }
    kpi_daily { text day PK; text key PK; real value; text source }
```

## Tables

| Table | One row = | Key | Filled by |
|---|---|---|---|
| `snapshot` | one ingest batch | id | every collector |
| `release_line` | a version line, e.g. `0.5.8` | line | derived from tags |
| `release` | one main tag (`v0.5.8rc1`, `v0.5.7`, `v0.5.7.post1`). Platform tags (`-xpu`) are artifacts, not releases | tag | GitHub releases, entity graph |
| `artifact_spec` | one thing a release should ship, and for which tag kind | code | `config.py` |
| `artifact` | what we found in PyPI / GitHub / Docker Hub for one tag | tag + spec | `collect_release.py` |
| `workflow`, `wf_run`, `wf_job` | GitHub Actions runs and jobs. A failed job stores its first error line | run id, job id | GitHub API, old snapshots |
| `bk_pipeline`, `bk_build` | Buildkite builds (dev and PR) | pipeline + number | old snapshots, report cache |
| `weekly_run` | Weekly full-suite verdict per build (`kind` weekly / reference) | pipeline + number | `collect_weekly.py` (Buildkite meta-data `weekly-verdict`) |
| `pr`, `pr_label`, `pr_feature` | pull requests, labels, changed feature areas | number | GitHub, entity graph |
| `pr_release` | the first release that contains a PR | pr + tag | entity graph (git first-parent log) |
| `pr_state` | review / mergeable / CI state of an open PR at a snapshot | snapshot + pr | GraphQL PR list |
| `decision` | a release decision (D1–D4) | `line:code` | `release-<line>/RELEASE_PREP.md` |
| `blocker` | something that blocks the line: carry-over (C1–C6), PR bug, dev CI red | id | prep doc, Trace Agent, Buildkite |
| `release_verdict` | the verdict for a tag at a snapshot | snapshot + tag | `model.record_verdicts` |
| `kpi_daily` | one daily metric value (long format: day, key, value) | day + key | `observe_history/`, `ops_hist/` |

## Views (ready for analysis)

| View | Answers |
|---|---|
| `v_release_cycle` | Days from the first RC to final, number of RCs and posts, per line |
| `v_artifact_matrix` | Expected vs found, per tag and artifact |
| `v_publish_weekly` | publish.yml runs per week and event: ok / failed / cancelled |
| `v_dev_pipeline_daily` | dev pass rate per pipeline per day |
| `v_failing_jobs` | Jobs that fail most, with the last error line |

Example queries:

```sql
-- Which artifacts failed most often over all releases?
SELECT label, SUM(expected AND NOT ok) AS times_missing FROM v_artifact_matrix GROUP BY label ORDER BY 2 DESC;
-- How long was dev red on a gate pipeline before each RC?
SELECT r.tag, b.pipeline, MAX(b.created_at) AS last_red FROM release r JOIN bk_build b
  ON b.branch='dev' AND b.state='failed' AND b.created_at < r.published_at GROUP BY r.tag, b.pipeline;
-- Did a verdict change over time?
SELECT s.taken_at, v.verdict FROM release_verdict v JOIN snapshot s ON s.id=v.snapshot_id WHERE v.release_tag='v0.5.8rc1';
```

## Not modeled yet (phase 2)

| Entity | Source today | Value |
|---|---|---|
| `test`, `build_test` (build runs test) | `entities.json` edges `runs`, `runs_suite` | Which tests each release really ran |
| `fail_signature`, `build_fail` | `P1/raw/fail_signatures.json` | Flaky vs real failures per release |
| `sprint`, `sprint_pr` | `ROADMAP.md` | Planned vs shipped per sprint |
| Buildkite jobs (per job wait and duration) | `bk.recent` | Queue cost per pipeline over time |
