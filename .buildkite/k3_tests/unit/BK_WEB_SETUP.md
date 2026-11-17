# Buildkite Web UI Setup: Unit Tests

**Steps editor**: paste contents of `buildkite-pipeline.yml`.

**GitHub trigger settings**:
- Filter: `(build.pull_request.labels includes "ci-ready" || build.pull_request.labels includes "full") && build.pull_request.draft != true`
- Rebuild on PR label change: Yes
- Build pull requests when they become ready for review: Yes
- Skip queued / cancel running branch builds: Yes

1-GPU test (~25–35 min). It never runs on a draft PR. When the PR is marked
ready for review with `cuda` ticked in the template's CI scope checklist (or
nothing ticked, which selects `full`), `.github/workflows/pr_ci_scope.yml`
adds the label for a maintainer's PR; for other PRs a maintainer adds it with a
`/ci run` comment (`.github/workflows/ci_run_command.yml`). Auto-merge adds
`full` as well. Converting the PR back to draft cancels its running builds.

`buildkite/k3-unit-tests` is a required check on `dev`. A PR without either
label has no status for it, so it cannot merge until one label is added —
the same model `buildkite/k3-multiprocess-test` uses with `mp` / `full`.

> Builds whose only changes are docs/`*.md`/`LICENSE`/`.github/**` auto-pass
> via the [path filter](../README.md#path-based-skip-auto-pass-on-docs-only-changes).
> Add `force-ci` label to the PR to bypass.
