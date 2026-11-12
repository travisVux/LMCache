#!/usr/bin/env bash
# Build the LMCache wheel from the CANDIDATE commit on the off-intranet
# "ascend-build" queue, stamp it with its source commit, and upload both as
# Buildkite artifacts for the intranet test step to consume.
#
# This is the one place the pull request's own build code (setup.py, any build
# hooks) executes. It runs here -- on a disposable builder with no route into
# GPU.intranet.Ascend and no NPU device -- precisely so that execution cannot
# reach the intranet. LMCache has no NPU native extension of its own (the NPU
# c_ops live in the external `lmcache_ascend` plugin, installed at test time),
# so this is a plain source wheel built with NO_GPU_EXT=1.
#
# Invoked from a trusted clone (see pipeline.yml). The candidate source is
# fetched into an isolated subdir and is the only untrusted input.
set -euo pipefail

CANDIDATE_COMMIT="$(buildkite-agent meta-data get ascend:candidate_commit)"
if [[ ! "${CANDIDATE_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ERROR: candidate commit '${CANDIDATE_COMMIT}' is not a 40-hex sha." >&2
    exit 1
fi

echo "--- :git: Fetching candidate source ${CANDIDATE_COMMIT}"
src="candidate-src"
rm -rf "${src}"
git clone --no-checkout "${ASCEND_TRUSTED_REPO:-https://github.com/LMCache/LMCache.git}" "${src}"
pushd "${src}" >/dev/null
# Fetch the exact candidate commit by sha. For a fork PR this commit is pushed
# into the upstream repo's refs/pull/<n>/head by GitHub, so a sha fetch against
# the canonical repo resolves it without ever adding the fork as a remote.
git fetch --depth 1 origin "${CANDIDATE_COMMIT}"
git checkout --detach "${CANDIDATE_COMMIT}"
echo "candidate tree: $(git rev-parse HEAD)"

echo "--- :package: Building wheel (NO_GPU_EXT=1)"
uv venv --python "${ASCEND_BUILD_PYTHON:-3.10}" .venv-build
# shellcheck disable=SC1091
source .venv-build/bin/activate
uv pip install --upgrade pip setuptools wheel build
# The shallow single-commit fetch above carries no release tag, so setuptools-scm
# cannot derive a version. Pin a throwaway version for this CI test wheel. This
# override is for validation wheels only -- never for release artifacts.
export SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LMCACHE="${ASCEND_WHEEL_VERSION:-0.0.0}"
# Source-only accelerator-agnostic wheel: the NPU backend is contributed by the
# external lmcache_ascend plugin at install time on the device host, not built
# here. NO_GPU_EXT=1 keeps the NVIDIA GPU backend out of this builder's wheel.
NO_GPU_EXT=1 python -m build --wheel --no-isolation --outdir ../dist
popd >/dev/null

wheel="$(ls -1 dist/*.whl | head -n1)"
if [[ -z "${wheel}" || ! -f "${wheel}" ]]; then
    echo "ERROR: no wheel produced in dist/." >&2
    exit 1
fi
echo "built: ${wheel}"

# Stamp the source commit next to the wheel so the intranet step can refuse any
# artifact that does not match the commit it was told to test (defence against
# a wheel being swapped between build and test).
echo "${CANDIDATE_COMMIT}" > dist/SOURCE_COMMIT
sha256sum "${wheel}" > "dist/$(basename "${wheel}").sha256"

echo "--- :buildkite: Uploading wheel artifact"
buildkite-agent artifact upload "dist/*"
