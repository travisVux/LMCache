# LMCache v0.5.8 — Release management prep

Prepared 2026-11-08. Input for the v0.5.8 runbook (made from `knowledge/release-playbook/templates/RELEASE_RUNBOOK_TEMPLATE.md` once the decisions below are made). Scope of changes: [ROADMAP.md](ROADMAP.md).

## 1. Where we start

| Item | State |
|---|---|
| Last stable | `v0.5.7` = `236f3eec` (rc4 commit; no rc5). GitHub Release published 2026-11-05, 22 assets |
| `dev` | `a4a68882` (2026-11-08), 71 commits after `v0.5.7` |
| PyPI `lmcache` / `lmcache-rust-raw-block-io` | `0.5.7` ✅ |
| PyPI `lmcache-cli` | **`0.5.8.dev0`** ❌ — published by the `v0.5.7` run (blocker B1 of 0.5.7 happened). No clean `0.5.7` exists |
| Docker `v0.5.7` | Per-arch tags only. Multi-arch `v0.5.7`, `latest`, `*-cu129` **missing** (run 42131253314: standalone cu12.9 failed → manifests skipped). Pushed images use vLLM 0.33 / torch 2.14, not the 0.5.7 pin |
| Milestone / labels | No `v0.5.8` milestone; no `release`, `release-blocker` labels |

## 2. Decisions needed (before any RC)

| # | Decision | Options | Input |
|---|---|---|---|
| D1 | Fix 0.5.7 with `v0.5.7.1`, or roll the fixes into 0.5.8? | (a) `v0.5.7.1` from a `release-0.5.7` branch with only the image + CLI fixes. (b) Skip; ship everything in 0.5.8 and say so in notes | 0.5.7 users have no multi-arch tag and a wrong CLI version today |
| D2 | torch / vLLM stack for 0.5.8 (LM-1078) | (a) torch 2.14 + vLLM 0.33.0, **drop cu12.9** (PyTorch has no cu129 torch 2.14). (b) stay torch 2.13 + vLLM 0.32.0 with cu12.9 | Task A patch pins 0.32.0 via `docker/vllm-stable.env`; option (a) = change that file + `RELEASE_CU129=false` |
| D3 | InProcess removal (#6254) | Ship as breaking change with migration note, or revert/defer | Need install path of `LMCache_inprocess` ❓ |
| D4 | Release date T and Release Lead | — | ❓ |

## 3. Carry-over blockers from 0.5.7 (none merged on `dev` `a4a68882`)

| ID | Problem | Fix | State |
|---|---|---|---|
| C1 | Release images not pinned (standalone = vLLM nightly, vllm-openai unpinned, lightweight `:latest`) — **caused the 0.5.7 image failure** | Task A / LM-1077: `docker/vllm-stable.env` + `--build-arg VLLM_VERSION` on all 6 builds + `--index-strategy unsafe-best-match` | Local commit `07702b32`, not pushed, no PR |
| C2 | `lmcache-cli` gets the next dev version on a stable tag | Set `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LMCACHE_CLI` from the tag in `build_cli_artifacts.yml` (0.5.7 runbook B1) | Not done |
| C3 | RC tags skip `publish-image`, so stable-only images are never tested | Run `publish-image` on RC with push gated (0.5.7 runbook B5) | Not done |
| C4 | Smoke tests do not load native code or check torch | `assert_release_image.py` (in Task A patch) or 0.5.7 runbook B4 | In Task A patch |
| C5 | Weekly `sync_torch_version.yml` follows vLLM GitHub `releases/latest` (can be an rc) | Task A patch makes it follow the pin | In Task A patch. Cron next run **2026-11-09 02:00 UTC** |
| C6 | XPU wheel change #6281 was planned for 0.5.7 (runbook G8) but is not in it | Intel contact checks the 0.5.8 RC XPU wheel | Open |

## 4. Prep checklist

| # | Step | Verify |
|---|---|---|
| 1 | Decide D1–D4 | Written in this file |
| 2 | Create milestone `v0.5.8` and labels `release-blocker`, `release` | `gh api repos/LMCache/LMCache/milestones --jq '.[].title'` lists `v0.5.8` |
| 3 | Open PRs for C1 (Task A) and C2, C3 | PRs green with label `full` |
| 4 | Copy the runbook template to `release-0.5.8/LMCACHE_V0.5.8_RELEASE_RUNBOOK.md`; fill from this file and the template's COMMON MISTAKES | Audit with `knowledge/release-playbook/templates/RUNBOOK_AUDIT_PROMPT.md` |
| 5 | Start the daily check (`daily_release_check.sh`) with `BASE=236f3eec` | New PRs land in ROADMAP.md "Gaps" or Internal |
| 6 | Triage open bugs filed after 2026-11-05 | Each has blocker / known issue / ignore |
| 7 | Final release notes from ROADMAP.md (breaking changes first) | Re-run the range on the RC commit |

## 5. Links to tracker

| Ticket | Part of 0.5.8 |
|---|---|
| LM-1073 | Closes the 0.5.7 leftovers (D1) |
| LM-1077 | C1, C4, C5 (Task A) |
| LM-1078 | D2 |
| LM-781 | Vendor wheels on PyPI — only if the design is signed off before T |
