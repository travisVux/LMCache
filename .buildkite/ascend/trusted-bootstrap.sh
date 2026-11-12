#!/usr/bin/env bash
# Trusted bootstrap for the Ascend NPU lane. Runs ONLY from a fresh clone of
# the trusted branch (see buildkite-pipeline.yml), never from the pull-request
# checkout. Its single job is to record the candidate commit under test and
# upload the trusted pipeline definition.
#
# Deliberately self-contained: it does not source helpers.sh / path-filter.sh.
# Keeping the trusted computing base small means fewer files whose integrity the
# whole lane depends on. Path/label admit decisions happen later, in the
# trusted pipeline.yml steps, where they cannot widen intranet exposure.
set -euo pipefail

# --- integrity guard ------------------------------------------------------
# This script must be running from the trusted clone the bootstrap step made,
# not from a PR checkout. A fresh `git clone --branch <ref>` leaves HEAD on the
# ref tip with a clean tree; refuse to proceed if that is not what we see, so a
# misconfigured Buildkite "Steps" editor (e.g. pointing at the auto-checkout)
# fails loudly instead of silently running untrusted code.
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: trusted-bootstrap.sh is not running inside a git work tree." >&2
    exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: trusted clone is dirty -- refusing to bootstrap from an untrusted tree." >&2
    exit 1
fi

# --- candidate (the thing under test) -------------------------------------
# BUILDKITE_COMMIT is the commit that triggered this build: the PR head for a
# PR build, or the branch tip for a dev build. It is the ONLY PR-derived input
# the trusted side consumes, and only as an opaque identifier.
CANDIDATE_COMMIT="${BUILDKITE_COMMIT:?BUILDKITE_COMMIT must be set by Buildkite}"
CANDIDATE_PR="${BUILDKITE_PULL_REQUEST:-false}"

echo "--- :lock: Trusted bootstrap"
echo "trusted ref : $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD)"
echo "candidate   : ${CANDIDATE_COMMIT} (PR: ${CANDIDATE_PR})"

# Hand the candidate to downstream trusted steps via Buildkite metadata rather
# than re-deriving it from a checkout they must not trust.
buildkite-agent meta-data set "ascend:candidate_commit" "${CANDIDATE_COMMIT}"
buildkite-agent meta-data set "ascend:candidate_pr" "${CANDIDATE_PR}"

# --- upload the trusted pipeline ------------------------------------------
# Read from this trusted clone. buildkite-agent sends the YAML content to
# Buildkite, so the step definitions that run later are trusted regardless of
# what the PR checkout on each agent contains.
echo "--- :pipeline: Uploading trusted Ascend pipeline"
exec buildkite-agent pipeline upload .buildkite/ascend/pipeline.yml
