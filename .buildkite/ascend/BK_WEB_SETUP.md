# Buildkite + host setup: Ascend NPU lane (hardened)

This lane runs on bare-metal hosts with a route into `GPU.intranet.Ascend`, so
it does **not** reuse the convenience pattern of the other vendor lanes
(metax/amd/xpu/musa). Those run `upload-pipeline.sh` out of Buildkite's
automatic checkout, which sits on the **pull-request head** — a PR can rewrite
the upload script, helpers, pipeline YAML, and host runner before the agent runs
them (Poisoned Pipeline Execution). That is tolerated there only because those
agents are disposable cloud/K8s pods. On an intranet-connected host it is not
acceptable, which is the security requirement this lane answers.

## Trust model

The pull request contributes exactly two things, both treated as **data**,
never as orchestration:

1. **Source**, built into a wheel on an off-intranet builder.
2. *(opt-in only)* **test files**, run inside a locked-down sandbox.

Everything that *orchestrates* — the Buildkite "Steps", `trusted-bootstrap.sh`,
`pipeline.yml`, `build-wheel.sh`, `run-tests.sh`, `common-setup.sh` — comes from
the **trusted branch** (`dev`, or a pinned reviewed tag). The chain:

```
BK web "Steps"  ── root of trust (only a BK admin can edit; no PR can touch it)
  └─ clone trusted ref ─ exec trusted trusted-bootstrap.sh   [queue: ascend-bootstrap, no intranet]
       └─ buildkite-agent pipeline upload (from trusted clone)
            ├─ build-wheel.sh   builds PR source → stamped wheel   [queue: ascend-build, no intranet, no device]
            └─ run-tests.sh     verifies + installs wheel, tests   [queue: ascend-npu, intranet host]
                 (each step re-clones the trusted ref before doing anything)
```

Because the test host never *builds* the candidate, the PR's `setup.py` / build
hooks never execute inside the intranet — they run on `ascend-build`, which has
no route to `GPU.intranet.Ascend`. The wheel's compiled code does run on the
device host (that is the test); the **host egress allowlist + sandbox**, not the
branch-of-origin alone, are what contain it.

## Three queues, split along the intranet boundary

| Queue | Network | Device | Privileges |
|---|---|---|---|
| `ascend-bootstrap` | none / public internet for `git clone` only | none | minimal |
| `ascend-build` | GitHub + pip indexes; **no** intranet | none | minimal |
| `ascend-npu` | **only** `GPU.intranet.Ascend` device endpoints | NPU | sandboxed, see below |

## Buildkite web UI

**Steps editor**: paste the contents of `buildkite-pipeline.yml` verbatim. Do
not paste `upload-pipeline.sh`; that is the pattern this lane deliberately
avoids.

**Repository / checkout**: for the pipeline, disable "run builds for pull
requests from forks" **automatically** — this lane must be triggered only by a
committer-applied label (below). If the bootstrap pipeline supports it, also
disable source checkout for the bootstrap step; it clones the trusted ref itself
and does not need the PR checkout at all.

**GitHub trigger filter**:
```
build.pull_request.labels includes "ascend" || build.branch == 'dev'
```
- `build.branch == 'dev'` — trusted branch, runs post-merge unconditionally.
- `ascend` label — committer-only (only LMCache committers can label a PR), a
  deliberate opt-in per PR. **Do not** gate this lane on the broad `full` label:
  `full` is applied by the auto-merge flow and reaches far more PRs than should
  ever touch the intranet. Keep intranet exposure to an explicit, named,
  committer decision.
- Rebuild on PR label change: Yes. Skip queued / cancel running branch builds:
  Yes (single device host; a superseded build just delays feedback).

**Secrets**: scope any intranet credentials to the `ascend-npu` queue's agents
only, and expose them only on the trusted branch / post-label builds — never to
`ascend-bootstrap` or `ascend-build`, and never to fork PR builds.

## Host hardening (`ascend-npu`)

These are host/network-layer controls; they are **not** (and must not be) set in
the repo YAML. `common-setup.sh` only *asserts* them and fails fast if absent.

- **Egress allowlist**: the agent host firewall/proxy permits outbound traffic
  **only** to the `GPU.intranet.Ascend` device endpoints the NPU runtime needs.
  Everything else — the rest of the intranet and the public internet — is
  blocked for the test sandbox. Set `ASCEND_DEVICE_ENDPOINTS` (space-separated
  `host:port`) so the preflight can confirm the needed endpoints are up, and
  leave `ASCEND_ASSERT_NO_INTERNET=1` so it confirms the internet is *not*
  reachable.
- **No broad passwordless sudo**: unlike the metax/CUDA bare-metal lanes, do
  **not** grant the agent `sudo rm -rf` over its workspace. Run the test step in
  an **ephemeral sandbox** (fresh container or user namespace per build) and
  discard it on completion, so cleanup needs no host privilege and a build
  cannot persist state for the next one.
- **CANN toolkit**: set `ASCEND_TOOLKIT_ENV` to this host's
  `ascend-toolkit/set_env.sh`.
- **SDK pins** (test step): set `ASCEND_TORCH_SPEC`, `ASCEND_TORCH_NPU_SPEC`,
  `ASCEND_PLUGIN_SPEC` (the `lmcache_ascend` plugin build), and
  `ASCEND_PIP_INDEX` to match the installed CANN version — same discipline as
  the metax lane pins its MACA torch. Unpinned installs silently drift ahead of
  the host SDK and fail at `import torch_npu`.

## Test tree mode

`ASCEND_TEST_TREE` controls whose tests run against the candidate wheel:

- `trusted` (default): the trusted clone's `tests/ -m npu`. **No PR-authored
  test code runs on the intranet host.** Catches regressions in the candidate's
  compiled behaviour; does not run tests a PR adds.
- `candidate`: the PR's own `tests/` + `pytest.ini`. Runs arbitrary PR Python on
  the host — only acceptable with the sandbox + egress lockdown above fully in
  place. Use when a PR must validate new NPU tests it introduces.

## What runs when

- **PR with `ascend` label** → build wheel off-intranet → NPU **smoke** subset
  (`tests/v1/platform`, `tests/v1/lmcache_native`) `-m npu` on the device host.
- **Post-merge on `dev`** → build wheel → **full** `tests/ -m npu`.
