"""Settings for the ops-app backend. Paths are relative to this file, so the folder can move."""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent                                   # ops-app/
WORKSPACE = APP.parents[1]                          # CacheAgent/
DB_PATH = APP / "data" / "ops.db"
FRONTEND = APP / "frontend"
DIST = APP / "dist"

# Existing collectors of the old page (read-only inputs for backfill).
OLD = APP.parent / "plan-2026-11" / "outputs" / "cpu_tests"
LMCACHE_CLONE = WORKSPACE / "third_party" / "LMCache"
RELEASE_DIR = lambda line: WORKSPACE / f"release-{line}"   # noqa: E731

REPO = "LMCache/LMCache"
WF_PUBLISH = 157910139
WF_NIGHTLY = 164357863
FIRST_LINE = (0, 5, 5)          # oldest release line we keep in detail

# Main tag: v0.5.8rc1, v0.5.7, v0.5.7.post1. Platform tags add "-xpu", "-rocm", ...
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?(?:\.post(\d+))?(?:-([a-z0-9][a-z0-9.-]*))?$")


def parse_tag(tag):
    """-> dict(line, kind, seq, sort_key, plat, pep440) or None."""
    m = TAG_RE.match(tag or "")
    if not m:
        return None
    a, b, c, rc, post, plat = m.groups()
    a, b, c = int(a), int(b), int(c)
    if rc:
        kind, seq, rank = "rc", int(rc), int(rc)
    elif post:
        kind, seq, rank = "post", int(post), 1000 + int(post)
    else:
        kind, seq, rank = "final", 0, 1000
    return dict(line=f"{a}.{b}.{c}", ver=(a, b, c), kind=kind, seq=seq, plat=plat,
                sort_key=(a * 1_000_000 + b * 1_000 + c) * 10_000 + rank,
                main=tag.split("-")[0] if plat else tag,
                pep440=tag[1:].split("-")[0])


# What each release kind should ship. (code, channel, package, label, for_rc, for_final)
ARTIFACT_SPECS = [
    ("pypi:lmcache",                  "pypi",   "lmcache",                   "PyPI lmcache",           1, 1),
    ("pypi:lmcache-cli",              "pypi",   "lmcache-cli",               "PyPI lmcache-cli",       1, 1),
    ("pypi:lmcache-rust-raw-block-io","pypi",   "lmcache-rust-raw-block-io", "PyPI rust-raw-block-io", 0, 1),
    ("gh:main",                       "gh",     "",                          "GitHub release",         1, 1),
    ("gh:rocm",                       "gh",     "rocm",                      "ROCm wheel",             1, 1),
    ("gh:rocm-torch210",              "gh",     "rocm-torch210",             "ROCm torch2.10 wheel",   1, 1),
    ("gh:xpu",                        "gh",     "xpu",                       "XPU wheel",              1, 1),
    ("gh:rbln",                       "gh",     "rbln",                      "RBLN wheel",             1, 1),
    ("gh:musa",                       "gh",     "musa",                      "MUSA wheel",             1, 1),
    ("gh:cu129",                      "gh",     "cu129",                     "cu12.9 wheel (D2)",      0, 1),
    ("docker:vllm-openai",            "docker", "vllm-openai",               "Docker vllm-openai",     1, 1),
    ("docker:vllm-openai:lightweight","docker", "vllm-openai",               "Docker lightweight",     0, 1),
    ("docker:standalone",             "docker", "standalone",                "Docker standalone",      0, 1),
    ("docker:lmcache-payload",        "docker", "lmcache-payload",           "Docker payload",         0, 1),
    ("docker:sglang",                 "docker", "sglang",                    "Docker sglang",          1, 1),
]
DOCKER_REPOS = ["vllm-openai", "standalone", "lmcache-payload", "sglang"]

# Release gating policy (expert review 2026-11-25, default until the release owner changes it here):
#   gating     = what users get from `pip install lmcache` / the main image: a gap blocks "complete"
#   known issue = platform wheels and optional images: a gap is listed as a known issue, it does not block
#   waits on a decision = an artifact whose need is still an open decision in RELEASE_PREP.md (cu12.9 = D2)
GATING_ARTIFACTS = {"pypi:lmcache", "pypi:lmcache-cli", "gh:main", "docker:vllm-openai"}
ARTIFACT_DECISION = {"gh:cu129": "D2"}
PLATFORM_JOB = r"(?i)\b(musa|rocm|xpu|rbln|cu12\.?9|cu129)\b"
WATCH_DAYS = 7          # after a final tag: Phase 6 Watch for this many days, then the page follows the next line
PYPI_PROJECTS = ["lmcache", "lmcache-cli", "lmcache-rust-raw-block-io"]

# Buildkite pipelines that must be green on dev before the next RC.
DEV_GATE_PIPELINES = ["k3-unit-tests", "k3-multiprocess-test", "k3-blend-test", "k3-comprehensive-test", "k3-correctness-test"]
