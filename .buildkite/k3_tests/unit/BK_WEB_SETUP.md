# Buildkite Web UI Setup: Unit Tests

**Steps editor**: paste contents of `buildkite-pipeline.yml`.

**GitHub trigger settings**:
- Filter: `build.pull_request.labels includes "ci-ready" || build.pull_request.labels includes "full"`
- Rebuild on PR label change: Yes
- Skip queued / cancel running branch builds: Yes

1-GPU test (~25–35 min). It runs once a reviewer labels the PR `ci-ready`
(directly, or with a `/ci run` comment handled by
`.github/workflows/ci_run_command.yml`), and again when auto-merge adds `full`.
It does not run on every pre-review push.

`buildkite/k3-unit-tests` is a required check on `dev`. A PR without either
label has no status for it, so it cannot merge until one label is added —
the same model `buildkite/k3-multiprocess-test` uses with `mp` / `full`.

> Builds whose only changes are docs/`*.md`/`LICENSE`/`.github/**` auto-pass
> via the [path filter](../README.md#path-based-skip-auto-pass-on-docs-only-changes).
> Add `force-ci` label to the PR to bypass.
