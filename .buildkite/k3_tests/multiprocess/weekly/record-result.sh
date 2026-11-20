#!/usr/bin/env bash
# Record one job's outcome for the weekly full-suite verdict.
#
# Usage: record-result.sh <passed|failed|skipped> [reason]
#
# Writes build meta-data key `weekly-result-<job id>` with a JSON value
# {label, status, retry, reason}. The verdict step (verdict.py) reads every
# such key and compares it with the jobs the pipeline schedules.
#
# This is a no-op unless WEEKLY_FULL=true and buildkite-agent is available,
# so PR builds and local runs are unchanged. It never fails the caller: the
# verdict treats a job without a record as "missing", which already fails
# the weekly run.

status="${1:?Usage: record-result.sh <passed|failed|skipped> [reason]}"
reason="${2:-}"

[[ "${WEEKLY_FULL:-}" == "true" ]] || exit 0
command -v buildkite-agent > /dev/null 2>&1 || exit 0
[[ -n "${BUILDKITE_JOB_ID:-}" ]] || exit 0

retry="${BUILDKITE_RETRY_COUNT:-0}"
[[ "$retry" =~ ^[0-9]+$ ]] || retry=0

if command -v jq > /dev/null 2>&1; then
    # jq (installed in ci-base) escapes every control character correctly.
    value="$(jq -nc --arg label "${BUILDKITE_LABEL:-}" --arg status "$status" \
        --argjson retry "$retry" --arg reason "$reason" \
        '{label: $label, status: $status, retry: $retry, reason: $reason}')"
else
    json_escape() {
        # Drop control characters (\r, \t, ...) first, then escape \ and ".
        local value
        value="$(printf '%s' "$1" | tr -d '\000-\037')"
        value="${value//\\/\\\\}"
        value="${value//\"/\\\"}"
        printf '%s' "$value"
    }
    value="$(printf '{"label":"%s","status":"%s","retry":%s,"reason":"%s"}' \
        "$(json_escape "${BUILDKITE_LABEL:-}")" \
        "$(json_escape "$status")" \
        "$retry" \
        "$(json_escape "$reason")")"
fi

buildkite-agent meta-data set "weekly-result-${BUILDKITE_JOB_ID}" "$value" \
    || echo "warning: could not record weekly result for ${BUILDKITE_LABEL:-}" >&2
exit 0
