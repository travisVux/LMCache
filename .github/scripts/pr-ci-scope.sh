#!/usr/bin/env bash
# Resolve the CI scope a PR author picked in the "CI scope" checklist of
# .github/PULL_REQUEST_TEMPLATE.md.
#
# Inputs (env):
#   PR_BODY    PR description. Untrusted: only matched as data, never evaluated.
#   PR_LABELS  JSON array of the PR's current label names.
#
# Outputs (appended to $GITHUB_OUTPUT):
#   test=true|false   run test.yml (CPU unit tests, every Python version)
#   cpu=true|false    run cpu_device.yml
#   labels=<list>     space-separated labels that start the Buildkite lanes
#
# No box checked, or a `full` label already on the PR, selects everything;
# the Buildkite lanes then start through the single `full` label.
set -euo pipefail

checked=$(printf '%s\n' "${PR_BODY}" | tr -d '\r' \
  | sed -nE 's/^[[:space:]]*[-*] \[[xX]\] `(test|cpu|cuda|mp|amd|xpu|musa|maca|rbln)`.*/\1/p' \
  | sort -u)

if [[ -z "${checked}" ]] || jq -e 'any(.[]; . == "full")' <<<"${PR_LABELS}" >/dev/null; then
  test=true
  cpu=true
  labels=full
else
  test=false
  cpu=false
  labels=""
  for lane in ${checked}; do
    case "${lane}" in
      test) test=true ;;
      cpu) cpu=true ;;
      cuda) labels+="${labels:+ }ci-ready" ;;
      *) labels+="${labels:+ }${lane}" ;;
    esac
  done
fi

{
  echo "test=${test}"
  echo "cpu=${cpu}"
  echo "labels=${labels}"
} | tee -a "${GITHUB_OUTPUT}"
