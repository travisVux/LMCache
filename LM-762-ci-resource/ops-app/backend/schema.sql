-- LMCache release & CI history store (SQLite).
-- Rules:
--   1. Facts keep their natural key (tag, run_id, job_id, pr number, pipeline+build number).
--      Re-ingesting the same fact updates it in place (upsert), so history is never duplicated.
--   2. Values that change over time (verdicts, KPIs, open-PR state) are stored per snapshot or per day,
--      so we can always ask "what did we know on day X?".
--   3. Every row points to the snapshot (ingest batch) that last wrote it -> provenance.
--   4. Analysis lives in views (v_*), not in the page code.
PRAGMA foreign_keys = ON;

-- ───────────── provenance ─────────────
CREATE TABLE IF NOT EXISTS snapshot (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  taken_at    TEXT NOT NULL,              -- when the source data was collected (UTC ISO)
  ingested_at TEXT NOT NULL,
  source      TEXT NOT NULL,              -- 'collect:gh', 'collect:pypi', 'file:observe_snapshot.json', ...
  note        TEXT
);

-- ───────────── releases ─────────────
CREATE TABLE IF NOT EXISTS release_line (
  line        TEXT PRIMARY KEY,           -- '0.5.8'
  major INTEGER NOT NULL, minor INTEGER NOT NULL, patch INTEGER NOT NULL,
  target_date TEXT,                       -- decision D4
  lead        TEXT
);

CREATE TABLE IF NOT EXISTS release (
  tag          TEXT PRIMARY KEY,          -- 'v0.5.8rc1', 'v0.5.7', 'v0.5.7.post1' (main tags only, no platform suffix)
  line         TEXT NOT NULL REFERENCES release_line(line),
  kind         TEXT NOT NULL CHECK (kind IN ('rc','final','post')),
  seq          INTEGER NOT NULL,          -- rc number, 0 for final, post number for post
  sort_key     INTEGER NOT NULL,          -- orders rc1 < rc2 < final < post1 inside a line
  sha          TEXT,
  tagged_at    TEXT,                      -- git tag / GitHub release created_at
  published_at TEXT,                      -- GitHub release published_at
  prerelease   INTEGER,
  url          TEXT,
  snapshot_id  INTEGER REFERENCES snapshot(id)
);
CREATE INDEX IF NOT EXISTS ix_release_line ON release(line, sort_key);

-- What a release of each kind is expected to ship. Seeded from backend/config.py.
CREATE TABLE IF NOT EXISTS artifact_spec (
  code      TEXT PRIMARY KEY,             -- 'pypi:lmcache', 'docker:vllm-openai', 'gh:xpu'
  channel   TEXT NOT NULL CHECK (channel IN ('pypi','docker','gh')),
  package   TEXT NOT NULL,                -- PyPI project, Docker repo, or GitHub platform suffix
  label     TEXT NOT NULL,
  for_rc    INTEGER NOT NULL,             -- expected on rc tags
  for_final INTEGER NOT NULL,             -- expected on final and post tags
  ord       INTEGER NOT NULL
);

-- What was actually seen in a registry. One row per (release, spec).
CREATE TABLE IF NOT EXISTS artifact (
  release_tag  TEXT NOT NULL REFERENCES release(tag),
  spec_code    TEXT NOT NULL REFERENCES artifact_spec(code),
  present      INTEGER NOT NULL,          -- 1 found, 0 looked and not found
  ref          TEXT,                      -- version / docker tag / asset count actually found
  detail       TEXT,                      -- e.g. 'multi-arch', 'amd64 only', 'version 0.5.8rc2.dev0 (wrong)'
  ok           INTEGER NOT NULL,          -- present AND correct
  published_at TEXT,
  url          TEXT,
  checked_at   TEXT NOT NULL,
  snapshot_id  INTEGER REFERENCES snapshot(id),
  PRIMARY KEY (release_tag, spec_code)
);

-- ───────────── GitHub Actions ─────────────
CREATE TABLE IF NOT EXISTS workflow (
  id    INTEGER PRIMARY KEY,              -- GitHub workflow id
  name  TEXT NOT NULL,
  role  TEXT                              -- 'publish', 'nightly', 'test', ...
);

CREATE TABLE IF NOT EXISTS wf_run (
  run_id       INTEGER PRIMARY KEY,
  workflow_id  INTEGER REFERENCES workflow(id),
  workflow     TEXT,                      -- name, kept when workflow id is unknown
  event        TEXT,
  head_branch  TEXT,
  head_sha     TEXT,
  release_tag  TEXT REFERENCES release(tag), -- set when head_branch is a main release tag
  status       TEXT,
  conclusion   TEXT,
  attempt      INTEGER,
  title        TEXT,
  created_at   TEXT,
  updated_at   TEXT,
  url          TEXT,
  snapshot_id  INTEGER REFERENCES snapshot(id)
);
CREATE INDEX IF NOT EXISTS ix_run_wf ON wf_run(workflow_id, created_at);
CREATE INDEX IF NOT EXISTS ix_run_tag ON wf_run(release_tag);

CREATE TABLE IF NOT EXISTS wf_job (
  job_id       INTEGER PRIMARY KEY,
  run_id       INTEGER NOT NULL REFERENCES wf_run(run_id),
  name         TEXT NOT NULL,
  status       TEXT,
  conclusion   TEXT,
  started_at   TEXT,
  completed_at TEXT,
  url          TEXT,
  error_line   TEXT,                      -- first meaningful error line of the log (failed jobs only)
  snapshot_id  INTEGER REFERENCES snapshot(id)
);
CREATE INDEX IF NOT EXISTS ix_job_run ON wf_job(run_id);

-- ───────────── Buildkite ─────────────
CREATE TABLE IF NOT EXISTS bk_pipeline (
  slug TEXT PRIMARY KEY,
  name TEXT,
  hw   TEXT                               -- 'GPU' / 'CPU' / vendor
);

CREATE TABLE IF NOT EXISTS bk_build (
  pipeline     TEXT NOT NULL REFERENCES bk_pipeline(slug),
  number       INTEGER NOT NULL,
  state        TEXT,
  branch       TEXT,
  commit_sha   TEXT,
  source       TEXT,
  pr           INTEGER,                   -- PR number (no FK: PR may be unknown)
  created_at   TEXT,
  started_at   TEXT,
  finished_at  TEXT,
  wait_min     REAL,                      -- queue wait before the first job started
  url          TEXT,
  snapshot_id  INTEGER REFERENCES snapshot(id),
  PRIMARY KEY (pipeline, number)
);
CREATE INDEX IF NOT EXISTS ix_bk_branch ON bk_build(branch, pipeline, created_at);

-- Weekly full suite (k3-multiprocess-test with WEEKLY_FULL=true). One row per build.
-- verdict comes from the build's own verdict step (meta-data `weekly-verdict`).
-- 'pass' only when that step said pass AND the build passed; a build without a
-- verdict (canceled, died before the end) is 'no_verdict', never a pass.
-- kind='reference' marks the last full dev build before the weekly run existed.
CREATE TABLE IF NOT EXISTS weekly_run (
  pipeline     TEXT NOT NULL,
  number       INTEGER NOT NULL,
  kind         TEXT NOT NULL CHECK (kind IN ('weekly','reference')),
  trigger      TEXT,                      -- schedule / ui / api
  verdict      TEXT NOT NULL,             -- pass / fail / no_verdict / running
  required     INTEGER,
  passed       INTEGER,
  flaky        INTEGER,
  failed       INTEGER,
  missing      INTEGER,
  skipped      INTEGER,
  allowed_skip INTEGER,
  problems     TEXT,                      -- JSON list [{label, state}] of jobs that did not pass
  duration_min REAL,
  snapshot_id  INTEGER REFERENCES snapshot(id),
  PRIMARY KEY (pipeline, number),
  FOREIGN KEY (pipeline, number) REFERENCES bk_build(pipeline, number)
);
-- weekly_run above is the first design (Buildkite meta-data weekly-full=true); kept for history, no longer filled.

-- Weekly full build, GitHub Actions design (2026-11-26, collect_weekly.py): workflow weekly_full_build.yml on dev,
-- one job per device lane (CUDA, XPU, later AMD / RBLN); each lane uploads report.json
-- (.github/scripts/weekly_full_build.py) = Buildkite child pipelines and the problems that fail the run.
-- verdict: passed / failed / timed_out / running / cancelled.  Re-runs replace the rows of a run (latest attempt).
CREATE TABLE IF NOT EXISTS weekly_gha_run (
  run_id       INTEGER PRIMARY KEY,       -- GitHub Actions run id
  run_number   INTEGER,
  attempt      INTEGER,
  event        TEXT,                      -- schedule / workflow_dispatch
  status       TEXT,
  conclusion   TEXT,
  verdict      TEXT NOT NULL,
  head_branch  TEXT,
  head_sha     TEXT,
  created_at   TEXT,
  started_at   TEXT,                      -- start of the latest attempt
  updated_at   TEXT,
  first_job_at TEXT,                      -- wall time = first job start .. last job end
  last_job_at  TEXT,
  prepare_conclusion TEXT,                -- "Prepare ci-weekly-full branch" job
  url          TEXT,
  snapshot_id  INTEGER REFERENCES snapshot(id)
);
CREATE INDEX IF NOT EXISTS ix_wgr_created ON weekly_gha_run(created_at);
-- state: passed / failed / timed_out / running / cancelled / not_run
CREATE TABLE IF NOT EXISTS weekly_gha_lane (
  run_id        INTEGER NOT NULL,
  device        TEXT NOT NULL,            -- cuda / xpu / amd / rbln
  job_id        INTEGER,
  job_name      TEXT,
  status        TEXT,
  conclusion    TEXT,
  state         TEXT NOT NULL,
  started_at    TEXT,
  completed_at  TEXT,
  url           TEXT,
  artifact_name TEXT,
  artifact_id   INTEGER,
  report        INTEGER,                  -- 1 = report.json read (live or from the cache)
  report_passed INTEGER,
  timed_out     INTEGER,
  commit_sha    TEXT,
  branch        TEXT,
  earlier_reports INTEGER,                -- reports of earlier attempts of this lane (re-runs)
  earlier_failed  INTEGER,
  log_notes     TEXT,                     -- JSON list
  snapshot_id   INTEGER REFERENCES snapshot(id),
  PRIMARY KEY (run_id, device)
);
CREATE TABLE IF NOT EXISTS weekly_gha_pipeline (
  run_id   INTEGER NOT NULL,
  device   TEXT NOT NULL,
  slug     TEXT NOT NULL,                 -- Buildkite pipeline
  name     TEXT,
  number   INTEGER,                       -- Buildkite build number
  url      TEXT,
  state    TEXT,
  retried  TEXT,                          -- JSON list of job labels that passed only after a retry
  ord      INTEGER,
  PRIMARY KEY (run_id, device, slug)
);
-- kind: build / failed / soft_failed / not_run / missing / suite_skipped / workload_skipped
CREATE TABLE IF NOT EXISTS weekly_gha_problem (
  run_id      INTEGER NOT NULL,
  device      TEXT NOT NULL,
  slug        TEXT NOT NULL,
  idx         INTEGER NOT NULL,
  kind        TEXT,
  label       TEXT,
  state       TEXT,
  exit_status INTEGER,
  url         TEXT,
  job_id      TEXT,
  detail      TEXT,
  PRIMARY KEY (run_id, device, slug, idx)
);
CREATE TABLE IF NOT EXISTS weekly_gha_meta (
  key   TEXT PRIMARY KEY,                 -- collected_at, schedule_enabled, cron, workflow, weeks
  value TEXT
);

-- ───────────── code changes ─────────────
CREATE TABLE IF NOT EXISTS pr (
  number      INTEGER PRIMARY KEY,
  title       TEXT,
  author      TEXT,
  created_at  TEXT,
  merged_at   TEXT,
  closed_at   TEXT,
  state       TEXT,                       -- open / merged / closed
  draft       INTEGER,
  url         TEXT,
  snapshot_id INTEGER REFERENCES snapshot(id)
);

CREATE TABLE IF NOT EXISTS pr_label (
  pr    INTEGER NOT NULL REFERENCES pr(number),
  label TEXT NOT NULL,
  PRIMARY KEY (pr, label)
);

CREATE TABLE IF NOT EXISTS feature (
  id    TEXT PRIMARY KEY,                 -- 'vllm', 'transport', ...
  title TEXT,
  stage TEXT,
  klass TEXT
);

-- A PR ships in exactly one release: the first main tag whose range contains it.
CREATE TABLE IF NOT EXISTS pr_release (
  pr          INTEGER NOT NULL REFERENCES pr(number),
  release_tag TEXT NOT NULL REFERENCES release(tag),
  PRIMARY KEY (pr, release_tag)
);

CREATE TABLE IF NOT EXISTS pr_feature (
  pr       INTEGER NOT NULL REFERENCES pr(number),
  feature  TEXT NOT NULL REFERENCES feature(id),
  strength TEXT,                          -- 'strong' = source file changed, 'weak' = tests only
  PRIMARY KEY (pr, feature)
);

-- Who owns a PR now (GitHub assignees; empty for most PRs -> the page falls back to the author).
CREATE TABLE IF NOT EXISTS pr_assignee (
  pr    INTEGER NOT NULL REFERENCES pr(number),
  login TEXT NOT NULL,
  PRIMARY KEY (pr, login)
);

-- Open-PR state over time (review queue analysis).
CREATE TABLE IF NOT EXISTS pr_state (
  snapshot_id INTEGER NOT NULL REFERENCES snapshot(id),
  pr          INTEGER NOT NULL REFERENCES pr(number),
  review      TEXT,
  mergeable   TEXT,
  ci_state    TEXT,
  PRIMARY KEY (snapshot_id, pr)
);

-- ───────────── release control ─────────────
CREATE TABLE IF NOT EXISTS decision (
  id          TEXT PRIMARY KEY,           -- '0.5.8:D1'
  line        TEXT NOT NULL REFERENCES release_line(line),
  code        TEXT NOT NULL,              -- 'D1'
  question    TEXT NOT NULL,
  options     TEXT,
  status      TEXT NOT NULL CHECK (status IN ('open','decided','dropped')),
  choice      TEXT,
  decided_at  TEXT,
  source      TEXT,                       -- file the row came from
  snapshot_id INTEGER REFERENCES snapshot(id)
);

CREATE TABLE IF NOT EXISTS blocker (
  id          TEXT PRIMARY KEY,           -- '0.5.8:C1', '0.5.8:pr#5458', '0.5.8:ci:k3-blend-test'
  line        TEXT NOT NULL REFERENCES release_line(line),
  code        TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('carryover','pr','ci','publish','artifact')),
  title       TEXT NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('open','fixed','waived')),
  fix_ref     TEXT,
  evidence    TEXT,                       -- URL
  opened_at   TEXT,
  closed_at   TEXT,
  source      TEXT,
  snapshot_id INTEGER REFERENCES snapshot(id)
);

-- Release decisions recorded by a person (backend/decide.py, expert review round 2). Append-only; the newest row per
-- blocker is the one the page shows. known_issue / accept make the blocker non-gating.
CREATE TABLE IF NOT EXISTS release_decision (
  id          INTEGER PRIMARY KEY,
  blocker_id  TEXT NOT NULL,
  line        TEXT,
  action      TEXT NOT NULL CHECK (action IN ('post1','upload','known_issue','accept','yank','rerun')),
  reason      TEXT NOT NULL CHECK (length(trim(reason)) > 0),
  decided_by  TEXT NOT NULL CHECK (length(trim(decided_by)) > 0),
  decided_at  TEXT NOT NULL
);

-- Verdict history: what the page concluded about a release, per snapshot.
CREATE TABLE IF NOT EXISTS release_verdict (
  snapshot_id INTEGER NOT NULL REFERENCES snapshot(id),
  release_tag TEXT NOT NULL REFERENCES release(tag),
  verdict     TEXT NOT NULL,              -- shipped / partial / publish_failed / bug_after / in_progress / no_data
  reason      TEXT,
  PRIMARY KEY (snapshot_id, release_tag)
);

-- ───────────── daily metrics (long format) ─────────────
CREATE TABLE IF NOT EXISTS kpi_daily (
  day     TEXT NOT NULL,                  -- 'YYYY-MM-DD' (UTC)
  key     TEXT NOT NULL,                  -- 'prs.open', 'queue.k3-unit-tests.w90', 'cost.GPU_failed', ...
  value   REAL,
  unit    TEXT,
  source  TEXT,
  PRIMARY KEY (day, key)
);

-- ───────────── analysis views ─────────────
DROP VIEW IF EXISTS v_release_cycle;
CREATE VIEW v_release_cycle AS
SELECT line,
       MIN(CASE WHEN kind='rc'    THEN COALESCE(published_at, tagged_at) END) AS first_rc_at,
       MIN(CASE WHEN kind='final' THEN COALESCE(published_at, tagged_at) END) AS final_at,
       SUM(kind='rc')   AS n_rc,
       SUM(kind='post') AS n_post,
       ROUND(julianday(MIN(CASE WHEN kind='final' THEN COALESCE(published_at, tagged_at) END))
           - julianday(MIN(CASE WHEN kind='rc' THEN COALESCE(published_at, tagged_at) END)), 1) AS rc_to_final_days
FROM release GROUP BY line;

DROP VIEW IF EXISTS v_artifact_matrix;
CREATE VIEW v_artifact_matrix AS
SELECT r.tag, r.line, r.kind, s.code, s.label, s.channel, s.ord,
       CASE WHEN (r.kind='rc' AND s.for_rc=0) OR (r.kind<>'rc' AND s.for_final=0) THEN 0 ELSE 1 END AS expected,
       a.present, a.ok, a.ref, a.detail, a.url, a.checked_at
FROM release r CROSS JOIN artifact_spec s
LEFT JOIN artifact a ON a.release_tag = r.tag AND a.spec_code = s.code;

DROP VIEW IF EXISTS v_publish_weekly;
CREATE VIEW v_publish_weekly AS
SELECT strftime('%Y-W%W', created_at) AS week, event,
       COUNT(*) AS runs,
       SUM(conclusion='success')   AS ok,
       SUM(conclusion='failure')   AS failed,
       SUM(conclusion='cancelled') AS cancelled
FROM wf_run WHERE workflow_id = 157910139 GROUP BY week, event;

DROP VIEW IF EXISTS v_dev_pipeline_daily;
CREATE VIEW v_dev_pipeline_daily AS
SELECT substr(created_at,1,10) AS day, pipeline,
       COUNT(*) AS builds,
       SUM(state='passed') AS passed,
       SUM(state='failed') AS failed,
       ROUND(100.0*SUM(state='passed')/NULLIF(SUM(state IN ('passed','failed')),0),1) AS pass_pct
FROM bk_build WHERE branch='dev' GROUP BY day, pipeline;

DROP VIEW IF EXISTS v_failing_jobs;
CREATE VIEW v_failing_jobs AS
SELECT j.name, COUNT(*) AS failures, MAX(r.created_at) AS last_at,
       (SELECT j2.error_line FROM wf_job j2 JOIN wf_run r2 ON r2.run_id=j2.run_id
         WHERE j2.name=j.name AND j2.error_line IS NOT NULL ORDER BY r2.created_at DESC LIMIT 1) AS last_error
FROM wf_job j JOIN wf_run r ON r.run_id=j.run_id
WHERE j.conclusion='failure' GROUP BY j.name;

-- ───────────── living knowledge base (PR Inspector phase C, 2026-11-24) ─────────────
-- RFC (one per PR) and FRS (one per code area / feature) generated from local PR analysis (kb.py).
-- A version is never overwritten: a fact change (CI pipeline, gates, tests, PRs) creates a proposal with a diff;
-- a person accepts or rejects it (kb.py accept / reject). Human edits are new versions with author='human'.
CREATE TABLE IF NOT EXISTS kb_doc (
  doc_id          TEXT PRIMARY KEY,          -- 'frs:smcore' | 'rfc:6572'
  kind            TEXT NOT NULL CHECK (kind IN ('rfc','frs')),
  subject         TEXT NOT NULL,             -- entity key: 'feature:smcore' | 'pr:6572'
  title           TEXT,
  status          TEXT NOT NULL DEFAULT 'draft',   -- draft | reviewed
  current_version INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kb_version (
  doc_id      TEXT NOT NULL REFERENCES kb_doc(doc_id),
  version     INTEGER NOT NULL,
  body_md     TEXT NOT NULL,                 -- the document (markdown)
  facts_json  TEXT NOT NULL,                 -- the facts it was generated from
  facts_hash  TEXT NOT NULL,
  author      TEXT NOT NULL,                 -- 'generator' | 'human'
  reason      TEXT,
  created_at  TEXT NOT NULL,
  PRIMARY KEY (doc_id, version)
);

-- links PR <-> feature <-> CI gate <-> RFC/FRS <-> bug / error analysis
CREATE TABLE IF NOT EXISTS kb_link (
  doc_id  TEXT NOT NULL REFERENCES kb_doc(doc_id),
  ref     TEXT NOT NULL,                     -- 'pr:6572' 'feature:smcore' 'gate:k3-unit-tests' 'bug:sig/test_failed' 'F05' 'analysis:3'
  rel     TEXT NOT NULL,                     -- about | covers | gated_by | spec_of | risk | analyses | changes
  PRIMARY KEY (doc_id, ref, rel)
);

CREATE TABLE IF NOT EXISTS kb_proposal (
  proposal_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id         TEXT NOT NULL REFERENCES kb_doc(doc_id),
  base_version   INTEGER NOT NULL,
  trigger        TEXT NOT NULL,              -- ci_change | gate_change | feature_change | pr_change | test_change
  changes_json   TEXT NOT NULL,              -- [{fact, before, after}]
  diff           TEXT NOT NULL,              -- unified diff of body_md (base -> proposed)
  new_body_md    TEXT NOT NULL,
  new_facts_json TEXT NOT NULL,
  new_facts_hash TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'open',   -- open | accepted | rejected | superseded
  created_at     TEXT NOT NULL,
  decided_at     TEXT
);

-- bug / error analysis (backward direction of the Inspector): a failure signature or a dev regression and its suspects
CREATE TABLE IF NOT EXISTS kb_analysis (
  analysis_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  ref           TEXT NOT NULL UNIQUE,        -- 'bug:sig/test_failed' | 'reg:k3-unit-tests/14727'
  summary       TEXT,
  suspects_json TEXT NOT NULL,               -- [{pr, commit, features, functions, why}]
  updated_at    TEXT NOT NULL
);

DROP VIEW IF EXISTS v_kb_open_proposals;
CREATE VIEW v_kb_open_proposals AS
SELECT p.proposal_id, p.doc_id, d.kind, d.subject, p.base_version, p.trigger, p.created_at
FROM kb_proposal p JOIN kb_doc d ON d.doc_id = p.doc_id WHERE p.status = 'open';

-- Before / after CI impact of the merged CI changes (#6730, #6731, #6854), filled by collect_ci_impact.py (tab #obs/impact).
-- One row per metric; before / after use the same method (ci_impact.py). status: ok / collecting / insufficient / new / no_data.
CREATE TABLE IF NOT EXISTS ci_impact_metric (
  key        TEXT PRIMARY KEY,
  ord        INTEGER,
  family     TEXT,                       -- gpu / mp / gha / rel
  label_en   TEXT,
  label_vi   TEXT,
  unit       TEXT,
  better     TEXT,                       -- down / up / info
  before     REAL,
  after      REAL,
  n_before   INTEGER,
  n_after    INTEGER,
  min_n      INTEGER,
  status     TEXT,
  delta      REAL,
  delta_pct  REAL,
  note       TEXT,
  after_only INTEGER
);
CREATE TABLE IF NOT EXISTS ci_impact_meta (
  key   TEXT PRIMARY KEY,                -- collected_at, before, after, cutoffs, heavy_reasons, decisions, weekly, scope (JSON values)
  value TEXT
);

-- 2026-11-26 v2: CI improvement versions (ci_versions.json). v0 = baseline; each version = [its start, next start).
CREATE TABLE IF NOT EXISTS ci_impact_version (
  id TEXT PRIMARY KEY, ord INTEGER, title_en TEXT, title_vi TEXT, prs TEXT, since TEXT, until TEXT, days REAL
);
CREATE TABLE IF NOT EXISTS ci_impact_def (
  key TEXT PRIMARY KEY, ord INTEGER, family TEXT, label_en TEXT, label_vi TEXT, unit TEXT, better TEXT, min_n INTEGER,
  after_only INTEGER, headline INTEGER
);
CREATE TABLE IF NOT EXISTS ci_impact_value (
  key TEXT NOT NULL, version TEXT NOT NULL, value REAL, n INTEGER, status TEXT,
  d_base REAL, d_base_pct REAL, d_prev REAL, d_prev_pct REAL, note TEXT,
  PRIMARY KEY (key, version)
);
