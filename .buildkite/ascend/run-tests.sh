#!/usr/bin/env bash
# Ascend NPU test runner, on the bare-metal "ascend-npu" host inside the
# intranet. Invoked from a trusted clone (see pipeline.yml), so this script and
# the test tree it runs are trusted. It installs the PREBUILT candidate wheel
# (no build on this host -> no PR setup.py runs here) and exercises it.
#
# Trust model recap (full version in BK_WEB_SETUP.md):
#   - Orchestration + tests come from the trusted branch (this clone).
#   - The candidate contributes compiled code only, as a commit-verified wheel.
#   - The wheel's code DOES run here (that is the test); the host's egress
#     allowlist + sandbox are what contain it. common-setup.sh asserts that
#     posture before anything untrusted loads.
set -euo pipefail

# shellcheck source=./common-setup.sh
source "$(dirname "${BASH_SOURCE[0]}")/common-setup.sh"

CANDIDATE_COMMIT="$(buildkite-agent meta-data get ascend:candidate_commit)"
CANDIDATE_PR="$(buildkite-agent meta-data get ascend:candidate_pr || echo false)"

# --- fetch + verify the prebuilt wheel ------------------------------------
rm -rf dist && mkdir -p dist
buildkite-agent artifact download "dist/*" dist/

stamped="$(cat dist/SOURCE_COMMIT)"
if [[ "${stamped}" != "${CANDIDATE_COMMIT}" ]]; then
    echo "ERROR: wheel was built from ${stamped}, but this build tests ${CANDIDATE_COMMIT}." >&2
    exit 1
fi
wheel="$(ls -1 dist/*.whl | head -n1)"
( cd dist && sha256sum -c "$(basename "${wheel}").sha256" )
echo "--- :white_check_mark: Verified wheel ${wheel} built from ${CANDIDATE_COMMIT}"

# --- install: prebuilt wheel + NPU runtime, NO build ----------------------
# torch / torch_npu / lmcache_ascend versions are host-specific; pin them to the
# installed CANN SDK (same discipline as the metax lane pins its MACA torch).
: "${ASCEND_TORCH_SPEC:?set ASCEND_TORCH_SPEC to the torch build matching this host's CANN}"
: "${ASCEND_TORCH_NPU_SPEC:?set ASCEND_TORCH_NPU_SPEC to the torch_npu build matching this host's CANN}"
: "${ASCEND_PLUGIN_SPEC:?set ASCEND_PLUGIN_SPEC to the lmcache_ascend plugin build for this host}"
extra_index=(); [[ -n "${ASCEND_PIP_INDEX:-}" ]] && extra_index=(--extra-index-url "${ASCEND_PIP_INDEX}")

uv pip install "${extra_index[@]}" "${ASCEND_TORCH_SPEC}" "${ASCEND_TORCH_NPU_SPEC}"
uv pip install -r requirements/common.txt -r requirements/test.txt
# The candidate under test: install the compiled wheel only (--no-deps so the
# pinned torch stack above is not silently overridden).
uv pip install --no-deps "${wheel}"
# NPU compiled ops plugin (external package; provides lmcache_ascend.c_ops).
uv pip install "${extra_index[@]}" "${ASCEND_PLUGIN_SPEC}"
uv pip freeze
python -c "import lmcache, torch, torch_npu; import lmcache_ascend.c_ops" \
    && echo "import OK: lmcache + torch_npu + lmcache_ascend.c_ops"

# --- which tests run ------------------------------------------------------
# Default "trusted": run THIS trusted clone's NPU tests against the candidate
# wheel, so no PR-authored test code executes on the intranet host. Opt into
# "candidate" (PR's own tests) only with the host sandbox fully locked down --
# it runs arbitrary PR Python here. See BK_WEB_SETUP.md.
TEST_TREE_MODE="${ASCEND_TEST_TREE:-trusted}"
if [[ "${TEST_TREE_MODE}" == "candidate" ]]; then
    echo "--- :warning: Running CANDIDATE (PR-authored) tests inside the sandbox"
    src="candidate-tests"
    rm -rf "${src}"
    git clone --no-checkout "${ASCEND_TRUSTED_REPO:-https://github.com/LMCache/LMCache.git}" "${src}"
    ( cd "${src}" && git fetch --depth 1 origin "${CANDIDATE_COMMIT}" \
        && git checkout "${CANDIDATE_COMMIT}" -- tests pytest.ini )
    test_root="${src}"
else
    echo "--- :shield: Running TRUSTED test tree against the candidate wheel"
    test_root="."
fi

# Smoke subset on PRs for fast feedback; full NPU suite post-merge on dev.
if [[ "${CANDIDATE_PR}" != "false" ]]; then
    scope=(tests/v1/platform tests/v1/lmcache_native)
    echo "--- :test_tube: NPU smoke tests (PR) -m npu"
else
    scope=(tests)
    echo "--- :test_tube: NPU full suite (post-merge) -m npu"
fi

LMCACHE_TRACK_USAGE="false" \
pytest -m npu --maxfail=1 \
    --cov=lmcache --cov-report term \
    --cov-report=html:coverage-test --cov-report=xml:coverage-test.xml \
    --html=durations/test.html \
    --rootdir="${test_root}" \
    "${scope[@]/#/${test_root}/}"
