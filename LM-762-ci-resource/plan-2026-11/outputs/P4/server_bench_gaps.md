# P4 / R3 — How far can `lmcache bench server` replace server-level E2E workloads?

Date: 2026-11-04. Source: local clone `third_party/LMCache` (not modified).
All paths below are relative to the repo root. `client.py` = `lmcache/cli/commands/bench/server_bench/client.py`
(same dir for `arguments.py`, `config.py`, `command.py`, `helpers.py`, `cases/*.py`).
Workloads live in `.buildkite/k3_tests/multiprocess/scripts/workloads/`.

## 1. What `lmcache bench server` does today

### 1.1 Shape

| Part | What it does | Where |
|---|---|---|
| Entry | `lmcache bench server ...`; on ImportError prints error, exit 2 | `__init__.py:37-56` |
| Config | frozen `BenchConfig`, validates mode / transfer mode / tp / concurrency / timeout | `config.py:17-91` |
| Orchestrator | build N clients, `start()` each, run case, emit metrics | `command.py:173-243` |
| Case contract | `BenchCase` protocol: `name`, `run(client, log) -> BenchResult` | `cases/base.py:68-90` |
| Result | `BenchResult`: named bool checks + latency lists + `succeeded` property | `cases/base.py:17-65` |
| Only case | `BaselineBenchCase`: per sequence, cold request then warm request | `cases/baseline.py:48-292` |
| Concurrency | one thread per client, shared stop event, merged results | `cases/concurrent.py:20-87` |
| Client | owns ZMQ/gRPC request client, simulated TP workers, KV buffers, block allocator | `client.py:190-1023` |

### 1.2 How it connects

| Item | Detail | Where |
|---|---|---|
| RPC endpoint | `--rpc-url` (default `tcp://localhost:5555`). Scheme picks transport: `tcp://` = ZMQ, `grpc://` = gRPC (factory) | `arguments.py:27-30`, `client.py:829-832` |
| Transports tested in CI | zmq, grpc, grpc-aio, grpc-native (server flag; client URL is `grpc://`) | `.github/scripts/cpu_server_bench_test.sh:47-63` |
| HTTP | `--url` (default `http://localhost:8080`), used ONLY for `POST /cache/checksums` | `arguments.py:183-190`, `helpers.py:165-206` |
| Handshake | `GET_CHUNK_SIZE` RPC; on timeout silently falls back to 256 | `helpers.py:214-219` |
| Register | one `TransferContext.register(...)` per simulated TP rank, `instance_id = 1000 + client_index*tp + rank`, model `test-model`, engine type VLLM | `client.py:921-989`, `helpers.py:24,32` |
| Unregister | on `close()`: flush stores, unregister, close transport | `client.py:608-670` |

### 1.3 Modes

| Flag | Values | Effect | Where |
|---|---|---|---|
| `--mode` | `cpu` / `gpu` (default gpu) | CPU tensors vs CUDA tensors; gpu needs CUDA | `arguments.py:32-40`, `client.py:815-816` |
| `--transfer-mode` | `auto` / `engine_driven` / `lmcache_driven` | auto: gpu→lmcache_driven, cpu→engine_driven | `arguments.py:41-56`, `config.py:83-91` |
| CPU + engine_driven | `EngineDrivenTransferContext` (worker gather/scatter + PREPARE/COMMIT) | | `client.py:938-941` |
| CPU + lmcache_driven | handle path over POSIX SHM | | `client.py:817-821, 943-948` |
| `--isolated-ipc` | GPU only (timeline-semaphore events) | | `arguments.py:57-68`, `config.py:68-69` |
| `--tp-size`, `--use-mla` | simulated TP ranks; MLA = only rank 0 stores, all ranks retrieve | `arguments.py:69-93`, `client.py:911-958` |
| `--kvcache-shape-spec` | multi-group KV layout (engine_driven: 1 group only) | `arguments.py:115-140`, `client.py:964-971` |
| `--concurrency` | N clients, each own connection + own instance IDs, sequences round-robin | `arguments.py:172-182`, `command.py:150-170` |
| `--start/--end/--interval/--num-tokens` | sequence range, sleep, tokens per request | `arguments.py:94-98,154-171` |
| `--flamegraph*` | profile server pid during load | `arguments.py:192-247`, `command.py:84-148` |
| `--format json --output PATH` | common CLI metrics flags (inherited) | `lmcache/cli/commands/base.py:300-326` |

### 1.4 Per-request flow (BaselineBenchCase)

Tokens = `(seq_no, 9906, 9906, ...)` (`helpers.py:80-85`). Every sequence has a unique first token, so there is
**no shared prefix between sequences**.

| Step | Cold request | Warm request | Where |
|---|---|---|---|
| 1 | LOOKUP + poll QUERY_PREFETCH_STATUS (max 50 x 50 ms) | same | `client.py:327-382`, `helpers.py:110-149` |
| 2 | fill deterministic KV, local checksum, optional server checksum | zero destination blocks | `cases/baseline.py:244-260` |
| 3 | STORE miss range | RETRIEVE hit range | `cases/baseline.py:262-271` |
| 4 | — | local checksum of retrieved blocks, optional server checksum | `cases/baseline.py:273-282` |
| 5 | END_SESSION, free blocks | same | `client.py:313-325` |

### 1.5 Asserts vs measures

| Item | Recorded as check? | Gates exit code? | Where |
|---|---|---|---|
| cold lookup ok, cold full miss, cold store ok | yes | **no** | `cases/baseline.py:141-155` |
| warm lookup ok, warm full hit, warm retrieve ok | yes | **no** | same |
| cold == warm checksum (bytes round trip) | yes | **no** (prints `CHECKSUM MATCH OK` / `MISMATCH`) | `cases/baseline.py:174-214` |
| server-side checksum via HTTP | yes, only lmcache_driven + `--url` | **no** | `client.py:547-606` |
| lookup / store / retrieve latency | measured (mean/min/max/p50/p99) | no | `command.py:246-357` |
| startup / register failure | RuntimeError → exit 1 | yes | `command.py:225-227` |

Key fact: `run_server_bench` never reads `BenchResult.succeeded` (`cases/base.py:58-65`, `command.py:173-243`).
The bench **always exits 0 after a run**. CI makes it a gate by grepping the log for
`CHECKSUM MISMATCH` and counting `CHECKSUM MATCH OK` (`.github/scripts/cpu_server_bench_test.sh:160-169`).
A warm miss also fails this gate (no checksum → no `MATCH OK` line), but only indirectly.

## 2. Local run (CPU mode, WSL Ubuntu-24.04)

**Worked.** CI script passes in both transfer modes (20 s / 25 s wall). Probes confirm: exit code ignores
failed checks (G1); `/metrics` + `/status` give all counters the workloads need; server restart works with
a fresh client; a big concurrency storm is blocked by slow serial client registration (G9).
Details: section "Local run result" at the end of this file.

## 3. Workloads vs server bench

GPU column = Buildkite pod size today (`.buildkite/k3_tests/multiprocess/pipeline.yml:133-410`).

| Workload | GPUs | What it does | What it really tests | Script refs |
|---|---|---|---|---|
| restart_recovery | 1 | engine bench round 1 → scrape `lmcache_mp_l1_write_chunks_total` → kill server, sleep 60, relaunch same port → poll `/status` until context meta non-empty → round 2 → assert round2 > 0 and ≥ 80% of round1 | worker re-register after server restart (vLLM adapter `HeartbeatThread` recover callback) + server restart cleanliness | `common/restart-recovery.sh:6-14, 95-125, 140-217, 288-298`; `lmcache/integration/vllm/vllm_multi_process_adapter.py:714-727`; `lmcache/v1/multiprocess/heartbeat.py:41-145` |
| cache_stats | 1 | cold + warm chat request with `kv_transfer_params.cached_token_stats`; warm LMCache tokens > cold; no stats without opt-in | vLLM connector response plumbing | `vllm/cache-stats.sh:36-208`; tested code `lmcache/integration/vllm/lmcache_mp_connector.py:1685-1697` |
| http_api | 1 | one engine request to warm cache, then ~30 HTTP checks (`/`, `/healthcheck`, `/config`, `/status`, `/metrics`, `/env`, `/loglevel`, `/threads`, `/periodic-threads*`, `/cache/clear`, `/quota` CRUD + errors, `/version`, `/lmc_version`, `/commit_id`) + `lmcache describe kvcache`, `lmcache kvcache clear` | LMCache HTTP server + CLI; engine only fills the cache | `common/http-api.sh:145-166, 168-383, 385-415` |
| deadlock | 2 | TP=2 DeepSeek-V2-Lite (MLA, dummy weights), chunk 256, `MAX_WORKERS=2`, 50 x 30K-token random-prefill, must finish in 180 s | server worker pool / GIL / CUDA IPC stall under heavy concurrent store+retrieve | `common/deadlock.sh:16, 54-71`; `scripts/run-single-test.sh:114-121`; `scripts/engines/vllm.sh:330-358` |
| long_doc_qa_l2 | 2 | relaunch server with `--l2-store-policy skip_l1 --eviction-policy noop --l2-adapter mock(4 GB/s)`, run long_doc_qa vs baseline engine; check perf (speedup ≥1.3x, TTFT ≥1.5x, warmup ≤1.2x) + data flow counters (L1 write, L2 store submitted/completed, L2 prefetch lookup/hit/loaded) + observability metric labels | perf vs baseline engine (needs engine) + L2 data flow (server only) + metric surface (server only) | `common/long-doc-qa-l2.sh:36-45, 105-133`; `common/long-doc-qa-l2-verify.sh:208-262, 341-393` |
| fault_tolerance | 1 | `VLLM_KV_LOAD_FAILURE_POLICY=recompute`; warmup bench, then kill LMCache mid-flight, then bench without LMCache; all prompts must complete | vLLM connector graceful degradation (recompute) | `vllm/fault-tolerance.sh:66, 133-199` |
| lm_eval (hit path only) | 1 | gsm8k twice; optional: clear engine prefix cache, then assert `lmcache_mp_l1_read_chunks_total` grew in run 2; samples/score must match | hit path = server retrieves stored KV; correctness = model output parity | `common/lm-eval.sh:112-133, 232-277` |
| vllm_bench (throughput + warm hit) | 2 | `vllm bench serve` LMCache vs baseline, LMCache ≤5% slower; then cold/warm long prompt: `cached_token_stats` warm > cold and server log retrieve count grew | throughput overhead (needs engine) + warm-hit retrieve (server) | `vllm/vllm-bench.sh:26, 167-189, 389-431` |

## 4. Gap table

Effort: S = < 1 day, M = 1-3 days, L = > 3 days or needs new non-bench code.

| Workload | Needed capability | Exists? (file:line) | Effort | Replace? + reason |
|---|---|---|---|---|
| **http_api** | fill cache without engine | yes — baseline cold store (`cases/baseline.py:244-271`) | S | **Fully.** Engine is used only for warmup (`http-api.sh:145-166`). Run bench `--end 3`, then the same curl/CLI checks. The checks can be reused as-is. |
| | HTTP GET/POST/PUT/DELETE check helper | partial — only `POST /cache/checksums` (`helpers.py:165-206`) | S | |
| | exit code from checks | **no** — `succeeded` never used (`command.py:173-243`) | S | |
| **lm_eval (hit path)** | store then retrieve same tokens, bytes equal | yes — cold/warm + checksum (`cases/baseline.py:141-214`) | S | **Partly (hit path fully).** Server bench already proves store→lookup→retrieve with byte equality, stronger than "L1 read counter grew". Model output parity (samples/score) still needs an engine. |
| | assert `lmcache_mp_l1_read_chunks_total` grew | no `/metrics` scrape in bench | S | |
| | shared-prefix / partial-hit lookup | no — tokens unique per seq (`helpers.py:80-85`); `is_partial_hit` defined but unused (`client.py:107-110`) | S | |
| **vllm_bench (warm hit)** | cold miss → warm full hit → retrieve OK | yes (`cases/baseline.py:141-155`) | S | **Partly.** Warm-hit part fully replaceable (bench checks are stronger than "log line count grew", `vllm-bench.sh:389-404`). Throughput "LMCache ≤5% slower than vLLM baseline" needs an engine → move to stored-baseline perf (WS-B) using bench latencies (`command.py:305-330`). |
| | stored perf baseline compare | no | M | |
| **cache_stats** | lookup hit count cold=0, warm=all | yes (`cases/baseline.py:147-152`) | S | **Partly / low value.** Server side hit counting is covered, but the workload tests vLLM connector response fields (`lmcache_mp_connector.py:1685-1697`). Best replacement: a unit test on the connector `request_finished` path, not server bench. |
| | assert `lmcache_mp_lookup_hit_tokens_total` / `requested_tokens_total` match traffic | no metrics scrape | S | |
| **long_doc_qa_l2 (flow + metrics)** | start server with L2 flags (`--l2-adapter mock`, `skip_l1`, `noop`) | **no** — bench never starts a server; CI script does (`cpu_server_bench_test.sh:89-96`) | M | **Partly.** Data-flow checks (`long-doc-qa-l2-verify.sh:208-262`) and observability checks (`:341-393`) are 100% server metrics → fully replaceable. Perf thresholds (speedup, TTFT vs baseline engine) → no. |
| | `/metrics` scrape + counter/histogram/label asserts | no in bench; logic exists in shell/python (`long-doc-qa-l2-verify.sh:201-215, 297-340`) | S | |
| | longer prefetch wait for slow L2 | no — 2.5 s cap then treated as 0 hits (`helpers.py:129-149`, `client.py:364-366`) | S | |
| | L2 bytes equality (evict L1, load from L2) | yes once server uses skip_l1 — warm retrieve checksum works the same | S | |
| **restart_recovery** | server lifecycle: start / kill / restart same port, wait `/healthcheck` | **no** in bench (shell only: `cpu_server_bench_test.sh:89-136`) | M | **Partly.** Server side ("new server accepts re-register, counter resets, stores work") fully testable. The real recovery trigger lives in the vLLM adapter (`HeartbeatThread` recover callback, `vllm_multi_process_adapter.py:714-727`) — bench client has no heartbeat. Can reuse `HeartbeatThread` (`heartbeat.py:41-145`) in the bench client to cover it. |
| | client survives server death and re-registers | **no** — after a timeout the client sets `_transfer_uncertain` and refuses all use until `close()` (`client.py:734, 997-1000`) | M | |
| | poll `/status` for `cache_context_meta` / `non_cuda_context_meta` | no | S | |
| | compare L1 write counter round1 vs round2 | no metrics scrape | S | |
| **deadlock** | many concurrent clients, heavy tokens, global timeout | partial — `--concurrency`, `--num-tokens`, `--tp-size 2 --use-mla` exist (`arguments.py:69-98,172-182`); no global wall-clock timeout (only per-transfer `--transfer-timeout`, `arguments.py:108-113`) | S | **Partly.** CPU mode covers server thread-pool / lock / GIL stalls (`MAX_WORKERS=2`, chunk 256). The CUDA-driver/IPC part needs `--mode gpu` (1 GPU, no engine) — still a big saving vs 2 GPUs + model. Engine-side scheduling pattern (chunked prefill, 32 seqs) is only approximated. |
| | py-spy dump on hang | no (flamegraph only, `command.py:84-148`) | S | |
| | fast parallel client start (local probe P4: 16 workers did not finish registering in 180 s) | **no** — serial start (`command.py:209-212`), see G9 | S-M | |
| **fault_tolerance** | kill server mid-run, client gets bounded error, no hang | partial — per-transfer timeout exists (`client.py:700-736`); lookup has 10 s RPC timeout (`helpers.py:40, 110-126`) | M | **No (for the real goal).** Workload tests vLLM `recompute` policy in the connector (`fault-tolerance.sh:66`). Bench can only add a cheap "client does not hang when server dies" check (`server_down_client_ok`). Local probe P6: server down → rc 1 after 42 s, no hang. Keep engine test, maybe nightly. |

### 4.1 Cross-cutting gaps (needed by most scenarios)

| # | Gap | Where | Effort |
|---|---|---|---|
| G1 | Exit code ignores checks — always 0 after run | `command.py:173-243` vs `cases/base.py:58-65` | S |
| G2 | No machine-readable verdict (pass + per-check expected/actual) — metrics JSON has counts, not verdict | `command.py:246-332` | S |
| G3 | No server lifecycle control (start, kill, restart, health wait) inside bench | only in `cpu_server_bench_test.sh:89-136` | M |
| G4 | No `/metrics` and `/status` scrape helpers | `helpers.py` has only `/cache/checksums` | S |
| G5 | Only one case and one token pattern (unique prefix per seq) | `command.py:150-170`, `helpers.py:80-85` | S |
| G6 | Silent fallbacks hide failures: chunk size 256 on timeout; prefetch poll budget → 0 hits | `helpers.py:214-219`, `helpers.py:129-149` | S |
| G7 | Client cannot recover after a timeout/server death | `client.py:997-1000` | M |
| G8 | Server-side checksum only in lmcache_driven + `--url` | `client.py:560-562` | — (OK, by design) |

## 5. Ranking (easiest replacements first)

| Rank | Workload | Replace | GPU saved per run | Effort |
|---|---|---|---|---|
| 1 | http_api | fully | 1 | S (G1, G4, port checks) |
| 2 | lm_eval hit path / vllm_bench warm-hit | hit path fully (already exists, needs G1) | 0 now (still need engine for parity/throughput), but lets PR tier drop to nightly | S |
| 3 | long_doc_qa_l2 data-flow + observability | flow/metrics fully, perf no | 2 for the flow part | M (G3 server flags, G4, G6 poll) |
| 4 | restart_recovery (server side) | partly | 1 | M (G3, G7) |
| 5 | deadlock (CPU, then 1-GPU no engine) | partly | 1-2 | S-M |
| 6 | cache_stats | partly; better as connector unit test | 1 | S |
| 7 | fault_tolerance | no (connector behavior) | 0 | — |

## Local run result

Setup: WSL `Ubuntu-24.04`, Python 3.12.3, 8 CPU, 19 GB RAM, no GPU. Repo copied with rsync to
`~/lmcache-p4/LMCache` (excluding `.venv*`, `build`, `dist`), uv venv, `torch` CPU wheel,
`requirements/{build,common,cli}.txt`, `NO_GPU_EXT=1 uv pip install -e . --no-deps --no-build-isolation`.
Install + native CPU build: **105 s total** (build step about 50 s). No errors.
Setup / probe scripts: `<home>\AppData\Local\Temp\claude\82ff7c0a8b56703b\5c57bfc3-9ec2-4421-8bf2-c9ee2232a6bf\scratchpad\{setup_p4.sh,run_p4.sh,probe_p4.sh,probe2_p4.sh}`. Logs: WSL `~/lmcache-p4/out/`.

### R1. CI script as-is (`.github/scripts/cpu_server_bench_test.sh`, 3 requests x 512 tokens, zmq)

| Transfer mode | Exit | Wall time (server start → teardown) | Server healthy after | Bench elapsed | Checksum | Server checksum |
|---|---|---|---|---|---|---|
| engine_driven | 0 | 20.1 s | 5 s | 4.74 s | 3/3 OK | skipped (by design) |
| lmcache_driven | 0 | 25.3 s | 5 s | 6.02 s | 3/3 OK | 6/6 OK |

Latency (engine_driven, mean ms): cold lookup 12.4, cold store 73.9, warm lookup 2.5, warm retrieve 29.8.
Most of the bench time is `--interval 0.5` sleeps (2 per sequence).

### R2. Extra probes (one server, engine_driven, zmq)

| Probe | Command (short) | Result | What it proves |
|---|---|---|---|
| P1 | fresh run, `--end 2 --interval 0` | rc 0, 2x `CHECKSUM MATCH OK` | baseline OK |
| P2 | **same seqs again** (cold is now a hit → `cold_full_miss` check fails) + `--format json --output` | **rc 0**, 0x `MATCH OK`, JSON `pass_rate: 0.0`, no pass/fail field | **G1 confirmed**: failed checks do not change exit code; JSON has no verdict |
| P3 | `GET /status`, `GET /metrics` after P1+P2 | `/status` has `non_cuda_context_meta`, `registered_non_cuda_instance_ids`, `worker_liveness`, `active_sessions`. `/metrics`: `l1_write_chunks_total 4`, `l1_read_chunks_total 12`, `lookup_requested_tokens_total 4096`, `lookup_hit_tokens_total 3072` | all counters restart_recovery / lm_eval / long_doc_qa_l2 read are present on a CPU-only server and match traffic (2 seq x 2 chunks written) |
| P5 | kill server, start new one on same port, new bench run | rc 0, 2x `MATCH OK`, new `l1_write_chunks_total 4` | server-side restart path works with a fresh client (no heartbeat needed for this half) |
| P4 | storm: `--concurrency 8 --tp-size 2 --num-tokens 4096`, 32 seqs, server `--max-workers 2 --l1-size-gb 2` | **timeout 180 s (rc 124) before first request** | clients start one by one (`command.py:209-212`); each worker register created a 2 GB `EngineDrivenContextShm` and took 7-25 s; 12 of 16 registered in 180 s |
| P4b | storm: `--concurrency 16 --num-tokens 30000` | killed at 300 s, no requests run | same: startup cost, not a server deadlock |
| P6 | server down, run bench | rc 1 after 42 s, `UNREGISTER_KV_CACHE failed ... timeout` | no hang, bounded failure; but slow (10 s RPC timeouts in series, chunk size silently falls back to 256, `helpers.py:217-218`) |

New gap from P4 (add to 4.1):

| # | Gap | Where | Effort |
|---|---|---|---|
| G9 | Client startup is serial and each engine_driven register is slow (SHM pool sized to server L1, 7-25 s each on WSL). A deadlock/storm scenario must start clients in parallel, use small `--l1-size-gb`, and time only the load phase. Root cause of the per-register cost: UNKNOWN — find out by timing `EngineDrivenTransferContext.register` with `--l1-size-gb 0.25` vs `2` (`py-spy dump` during register). | `command.py:209-212`, `client.py:938-941, 973-989` | S-M |
