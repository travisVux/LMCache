# LMCache v0.5.8 — Roadmap ("Coming in v0.5.8")

Saved 2026-11-08. This is the template for the "next release" section of each sprint: it lists what is on `dev` after the last stable tag and will ship in the next one.

## As given (draft text)

> **Coming in v0.5.8.** The following changes were merged to `dev` after v0.5.7 was cut (tag commit `236f3ee`). They are available in nightly builds and will ship in v0.5.8, not in the v0.5.7 wheel.
>
> **Features & integrations**
> - vLLM sleep mode with VMM-shared KV caches (#6358)
> - valkey_rdma L2 adapter (#5556)
> - Request matching tags through object identity (#6199, #5843)
> - fd-based sharing of VMM-mapped memory regions (#6266)
> - Store TP-replicated KV groups once per TP group (#6125)
> - HF3FS shard_dirs to spread stores (#6261)
> - `--isolated-ipc` for lmcache bench server (#5931)
> - Token dropping: allocate from resident KV length (#5871)
> - GLM-5.3-Flash recipe (#6372); Kimi K3.1 KDA + correctness (#6318)
>
> **Refactor**
> - Remove in-tree InProcess implementation (#6254)
>
> **Bug fixes**
> - Isolate CLI profiling tests from host deps (#6350)
> - Padded per-layer (K,V) KV tuples on Ascend (#6241)
> - Stop vendoring Intel compiler runtime into XPU wheel (#6281)
> - Keep engine alive on gRPC/ZMQ failures (#6275, #6331); RESP env fallbacks (#6294)

## Check (2026-11-08, `dev` = `a4a68882`)

All 18 PRs are **merged into `dev`**, and none is in `v0.5.7` (`236f3eec` = the rc4 commit).

| PR | Merged | Commit | Title on GitHub |
|---|---|---|---|
| #5556 | 11-03 | `ca439cad` | feat: add the valkey_rdma L2 adapter |
| #5843 | 11-03 | `e0ef91d2` | [Feat][MP] Add matching tags to object identity |
| #6199 | 11-04 | `453a6c6a` | [Feat][MP] Propagate matching tags from requests |
| #5931 | 11-04 | `c2188b68` | [Feat][CLI] Add --isolated-ipc to lmcache bench server |
| #6241 | 11-04 | `d3beca27` | [Bugfix][Core][Ascend] Accept padded per-layer (K, V) KV tuples |
| #6275 | 11-04 | `9060d959` | [Bugfix][MP] Don't crash the engine when a gRPC transfer fails |
| #6266 | 11-05 | `298140c4` | [core] Enable fd-based sharing of the vmm mapped memory regions |
| #6125 | 11-05 | `dc8c116d` | [MP] Store tensor-parallel replicated KV groups once per TP group |
| #6261 | 11-05 | `c9d773f7` | [Core][HF3FS] Add shard_dirs option to spread stores |
| #5871 | 11-05 | `e4d87942` | [Token Dropping] [MVP 02/21] Allocate from resident KV length |
| #6281 | 11-05 | `cf2ef4b5` | [Build][XPU] Stop vendoring the Intel compiler runtime |
| #6331 | 11-05 | `b9a1447b` | [Bugfix][MP] Don't crash the engine when the ZMQ server rejects a request |
| #6294 | 11-05 | `ea517d29` | [Bugfix][MP] Honor the RESP L2 host and port env var fallbacks |
| #6358 | 11-06 | `012965f8` | [Feature][MP] Support vLLM sleep mode with VMM-shared KV caches |
| #6372 | 11-06 | `cf87a1ca` | [Doc] Add a GLM-5.3-Flash recipe |
| #6318 | 11-06 | `3e47dfbe` | [Bugfix][vLLM] Tile Kimi K3.1 KDA state + add K3.1 correctness workload |
| #6254 | 11-06 | `5b9db86f` | [Refactor] Remove in-tree InProcess implementation |
| #6350 | 11-06 | `c5a285ea` | [Bugfix][CLI] Isolate profiling failure tests from host deps |

## Gaps in the draft

`236f3eec..dev` has **71 commits**; the draft covers 18. Items worth adding:

### Must add: breaking change

| PR | Why it is breaking | Note for users |
|---|---|---|
| #6254 (+ follow-ups #6258, #6286, #6394, #6407, #6412) | Removes `lmcache/inprocess`, its packaging entry points, examples and docs. Moved to the separate repo `LMCache/LMCache_inprocess`. #6412 also removes `calculate_local_rank_and_world_size()` and `_vllm_local_device_index()` | Put under **Breaking changes**, not "Refactor". Say what InProcess users must install instead ❓ (package name / install command of `LMCache_inprocess`) |

### Should add

| Group | PRs |
|---|---|
| Features | #5770 gRPC API key authentication for sync and aio servers; #5865 native MUSA CacheGen codec; #5981 CPU-only server Kubernetes example |
| Correctness fixes (cache key / identity) | #5713 isolate vLLM MP cache keys per LoRA adapter; #6267 carry model revision as an `lmcache.tag` identity tag (fixes #6253) |
| Reliability fixes | #6256 one blocked ZMQ client no longer freezes the others; #6278 gRPC no longer goes through an env proxy; #6387 skip unsupported FD channels at startup; #6382 log gRPC handler errors; #4934 isolate malformed MQ requests; #6234 check `cudaLaunchHostFunc` return; #6369 delete NIXL scratch files on close; #4697 raw-block: bound outstanding I/O; #6002 HF3FS key-buffer misses |
| CLI fixes | #5902, #6306 HTTP body errors; #6343 URL scheme case; #6302 cache salt in quota URLs; #6303 flamegraph failure exit code; #5639 L2 bench timeout |
| Platforms | #6283 MUSA IPC handles; #5035 ROCm hipify guard; #6265 device backend resolved once |
| SDK | #6282 exclude prompt tokens from `output_tokens` |

### Internal only (leave out of user notes)

MP refactors #6244, #6270, #6383, #6384, #6390, #6269; tests #5174, #6231, #6279, #6413; CI #6143, #6326, #6377, #6397, #4105, #4549; docs/agent #3992, #6054, #6391, #6454; bench/tooling #6260, #5697; #4812, #6252.

## Rule for each sprint

1. Range = last stable tag commit → `dev` HEAD (`git log <tag>..origin/dev`), not by date. Tags can sit on an older commit than the tag date (`v0.5.7` = rc4 commit).
2. Check every PR is merged and not in the tag (`git merge-base --is-ancestor <commit> <tag>` must fail).
3. Sections: **Breaking changes** first, then Features, Bug fixes, Platforms, Internal (optional).
4. Re-run on the RC commit: anything merged after the RC is "next release" again.
