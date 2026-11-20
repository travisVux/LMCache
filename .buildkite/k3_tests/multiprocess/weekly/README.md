# Weekly full suite

Once a week, the `k3-multiprocess-test` pipeline runs every multiprocess test
on the newest `dev` commit. That includes the full-size DeepSeek-V4-Flash
correctness test: real 160 GB fp8 weights, TP=4. Per-PR builds keep the
reduced 6-layer DSV4 check and the label-gated subset.

The weekly build is the checkpoint for that week. If next week's build fails,
the regression came in between the two builds' commits.

## How to run

| Way | How |
|---|---|
| Scheduled | Buildkite schedule on `k3-multiprocess-test` (see below) |
| By hand | Buildkite → `k3-multiprocess-test` → **New Build**, branch `dev` (or any branch), commit `HEAD`, environment `WEEKLY_FULL=true` |

`WEEKLY_FULL=true` does three things:

1. Turns off the path filter and the `skip expensive ci` label, so a build
   started by hand on a docs-only commit still runs everything.
2. Adds the group **Weekly full: DSV4 full-size (4-GPU)**
   (`dsv4_flash_tp` for vLLM and SGLang).
3. Adds the step **Weekly full verdict** at the end of the build.

`WEEKLY_FULL=true` together with `VERIFY_AND_PIN_*` is refused at upload,
because the nightly canary flags skip every test group.

## When is a weekly run "passed"

The verdict step (`verdict.py`) builds the list of required jobs from
`pipeline.yml`: every command step that runs in a weekly build, with each
matrix expanded (43 jobs today, `python3 verdict.py --list`). Each job records
its own result through `record-result.sh`. The run passes only if every
required job recorded `passed`.

| Job result | Weekly run |
|---|---|
| passed | ✅ |
| passed after a retry | ✅, listed as **flaky** in the summary |
| failed | ❌ |
| missing (never ran, timed out, agent lost, canceled) | ❌ |
| skipped at preflight (engine does not support the workload) | ❌, unless listed in `allowed-skips.txt` |

A preflight skip shows as a green job in Buildkite, so before this verdict,
a skip looked like a pass. Every entry in `allowed-skips.txt` is coverage the
weekly run does not have; the summary lists them every week.

The DSV4 full-size jobs retry only on a lost agent (`exit_status: -1`), so
a failed correctness check stays red. Other steps keep their PR retry policy.

## Results and logs

| What | Where |
|---|---|
| Summary | Build annotation **weekly-verdict** |
| Per-job table | Artifact `weekly_verdict.json` (+ `weekly_verdict.md`) |
| Short result for dashboards | Build meta-data `weekly-verdict`, for example `{"verdict":"pass","required":43,"passed":39,...}`; `weekly-full=true` marks the build |
| Test logs and outputs | Each job's artifacts (`*.log`, `ci_results_*/<test>/**`) |

## Schedule (Buildkite admin)

Create on pipeline `k3-multiprocess-test` → Settings → Schedules:

| Field | Value |
|---|---|
| Label | `Weekly full suite` |
| Cron interval | `0 20 * * 0` (Sunday 20:00 UTC) |
| Branch | `dev` |
| Commit | `HEAD` |
| Environment | `WEEKLY_FULL=true` |

Sunday 20:00 UTC is Monday 04:00 in UTC+8 and Sunday 12:00 in US Pacific
(PST). From the k3 builds of 2026-10-05 to 2026-11-15, Sunday 17:00–24:00 UTC
was the quietest time of the week: on average about one job running, and
near-zero queue wait. It does not overlap the nightly canaries (05:05 and
06:05 UTC). The last full dev build took about 2h20m, so results are ready
before the Monday stand-up in both time zones.

## Changing the suite

- New step in `pipeline.yml`: it is required automatically. Nothing to update.
- New kind of `if:` condition: `verdict.py` fails loudly (`unsupported if
  clause`); extend `eval_if`.
- A job that now runs again: remove it from `allowed-skips.txt` (the summary
  tells you).
- Every job in a weekly build needs a unique label, and `parallelism > 1` is
  not supported: shards share one label, so one passing shard could hide a
  missing one. `verdict.py` stops with an error in both cases.
- Jobs must run in their own pod (queue `k8s`). On timeout or cancel the pod
  is removed with all its processes, the job writes no result, and the
  verdict counts it as missing.
