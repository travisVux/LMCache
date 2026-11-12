#!/usr/bin/env bash
# Shared environment setup for the Ascend NPU test step on the bare-metal
# "ascend-npu" queue. Sourced (not executed) by run-tests.sh. Mirrors the
# metax/common-setup.sh pattern (disk guard, fixed recreated venv, localhost
# proxy exemption) and adds the egress preflight the Ascend security model
# depends on.
set -euo pipefail

echo "$PWD" # for debugging

# --- egress preflight -----------------------------------------------------
# The intranet reachability this host needs (GPU.intranet.Ascend) is granted at
# the HOST/network layer, not here -- this file cannot and must not widen it
# (see BK_WEB_SETUP.md "Host hardening"). This block only ASSERTS the expected
# posture so a misconfigured host fails fast instead of running tests with the
# wrong network exposure:
#   - the device endpoint(s) the suite needs are reachable, and
#   - general outbound internet is NOT reachable from the test sandbox.
# ASCEND_DEVICE_ENDPOINTS is a space-separated host:port list the host admin
# sets to whatever the NPU runtime actually talks to.
for ep in ${ASCEND_DEVICE_ENDPOINTS:-}; do
    host="${ep%%:*}"; port="${ep##*:}"
    if ! timeout 5 bash -c ">/dev/tcp/${host}/${port}" 2>/dev/null; then
        echo "ERROR: required Ascend device endpoint ${ep} is not reachable." >&2
        echo "The host's egress allowlist for GPU.intranet.Ascend is misconfigured." >&2
        exit 1
    fi
done
if [[ "${ASCEND_ASSERT_NO_INTERNET:-1}" == "1" ]]; then
    # 203.0.113.1 is TEST-NET-3 (RFC 5737): guaranteed non-routable, so a
    # successful connect would mean egress is wider than the allowlist intends.
    if timeout 5 bash -c ">/dev/tcp/${ASCEND_INTERNET_PROBE_HOST:-203.0.113.1}/80" 2>/dev/null; then
        echo "ERROR: outbound internet is reachable from the test sandbox." >&2
        echo "Lock host egress to GPU.intranet.Ascend only before running untrusted code." >&2
        exit 1
    fi
fi

# --- disk guard -----------------------------------------------------------
MIN_FREE_GB="${ASCEND_MIN_FREE_GB:-10}"
free_gb=$(df -Pk . | awk 'NR==2 {print int($4/1024/1024)}')
if (( free_gb < MIN_FREE_GB )); then
    echo "ERROR: only ${free_gb}GiB free on this host (need >= ${MIN_FREE_GB}GiB)." >&2
    exit 1
fi

# Local HTTP servers some tests spin up must bypass any host proxy, same as the
# metax lane.
export no_proxy="127.0.0.1,localhost,${no_proxy:-}"
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"

# --- Ascend CANN toolkit env ----------------------------------------------
# ASCEND_HOME_PATH / the toolkit set_env.sh location are host-specific. Pin them
# to whatever CANN version this host has installed; an unset/mismatched toolkit
# fails at `import torch_npu`. Defaults follow the standard CANN install layout.
ASCEND_TOOLKIT_ENV="${ASCEND_TOOLKIT_ENV:-/usr/local/Ascend/ascend-toolkit/set_env.sh}"
if [[ ! -f "${ASCEND_TOOLKIT_ENV}" ]]; then
    echo "ERROR: CANN toolkit env not found at ${ASCEND_TOOLKIT_ENV}." >&2
    echo "Set ASCEND_TOOLKIT_ENV to this host's ascend-toolkit/set_env.sh." >&2
    exit 1
fi
# shellcheck disable=SC1090
source "${ASCEND_TOOLKIT_ENV}"

# --- fresh venv -----------------------------------------------------------
rm -rf .venv coverage-test durations .pytest_cache
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
uv venv --python "${ASCEND_PYTHON:-3.10}" .venv
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install --upgrade pip setuptools wheel
