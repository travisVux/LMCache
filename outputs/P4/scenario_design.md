# P4 — Minimal "scenario" extension for `lmcache bench server`

Goal: turn the bench into an engine-free test runner with a real exit code and a JSON verdict.
Keep the current perf mode unchanged (no `--scenario` = today's behavior). Gap IDs (G1-G9) refer to `server_bench_gaps.md`.

## 1. CLI

| Flag | Default | Meaning |
|---|---|---|
| `--scenario NAME[,NAME]` | none (= today's baseline bench) | run named scenarios in order |
| `--verdict-output PATH` | none | write JSON verdict (below); also print one `VERDICT pass=<bool>` line |
| `--manage-server` / `--server-args "..."` | off | bench starts and owns `lmcache server` (needed for restart / L2 scenarios, G3) |
| `--scenario-timeout S` | 300 | wall-clock limit per scenario; on expiry: py-spy dump of server pid (if found), fail |
| `--strict` | on when `--scenario` set | exit 1 if any check fails (G1). Also turn on for the plain baseline bench in CI |

Exit codes: 0 all pass, 1 a check failed, 2 setup error (server did not start, import error).

## 2. Classes (new files under `server_bench/scenarios/`)

| Class | Role | Reuses |
|---|---|---|
| `Check(name, expected, actual, passed)` | one assertion result | — |
| `ScenarioResult(scenario, checks, elapsed_s, artifacts)` | `pass = all(c.passed)` | wraps `BenchResult.checks` (`cases/base.py:17-65`) |
| `ScenarioContext` | config, `make_clients(n)` (**parallel start**, G9), `http` (GET/POST/PUT/DELETE + `metrics()` parser + `status()`), `server` handle | `ServerBenchClient` (`client.py:190`), `_query_checksum` style (`helpers.py:165`) |
| `ServerHandle` | `start()`, `stop()`, `kill()`, `restart()`, `wait_healthy()`; no-op if server is external | logic from `cpu_server_bench_test.sh:89-136` |
| `Scenario` (Protocol) | `name`, `server_args()` (extra flags it needs), `run(ctx) -> ScenarioResult` | same shape as `BenchCase` (`cases/base.py:68-90`) |
| `REGISTRY: dict[str, type[Scenario]]` | name → class | — |

Small fixes in the same PR: make the prefetch poll budget configurable and count "budget exceeded" as a failed check (G6, `helpers.py:129-149`).
Fail on chunk-size timeout instead of falling back to 256 (`helpers.py:214-219`).

## 3. First scenarios (order = build order)

| Scenario | Steps | Main checks | Replaces |
|---|---|---|---|
| `store_lookup_retrieve` | baseline case + shared-prefix seq (half chunks reused) | cold miss, warm full hit, partial hit = expected chunks, checksum equal, `l1_read_chunks_total` delta > 0 | lm_eval / vllm_bench hit path |
| `http_api` | warm with 3 seqs, then endpoint table from `http-api.sh:168-383` + `lmcache describe` / `kvcache clear` | status codes, required keys, lookup after clear = miss | http_api (fully) |
| `stats_metrics` | N seqs cold+warm | `l1_write_chunks_total == N*chunks`, `lookup_hit_tokens_total == warm tokens` | cache_stats (server side) |
| `l2_roundtrip` | server args `--l2-store-policy skip_l1 --eviction-policy noop --l2-adapter '{"type":"mock",...}'` | L2 store submitted/completed > 0, prefetch lookup/hit/loaded > 0, label checks (`long-doc-qa-l2-verify.sh:208-393`), checksum equal | long_doc_qa_l2 flow part |
| `restart_reregister` | round 1 → `server.restart()` → new clients (later: `HeartbeatThread` recover) → round 2 | `/status` context meta > 0, round2 writes ≥ 0.8 x round1 | restart_recovery (server side) |
| `concurrency_storm` | small L1, parallel start, `C` clients x `M` long seqs, `--tp-size 2 --use-mla` | all requests done within timeout, 0 failed transfers, `active_sessions == 0` after | deadlock (CPU; GPU mode later) |
| `server_down_client_ok` | kill server mid-run | client fails within bound (< 60 s), no hang | fault_tolerance (adjunct only) |

## 4. JSON verdict

```json
{
  "scenario": "store_lookup_retrieve",
  "pass": false,
  "elapsed_s": 3.9,
  "config": {"mode": "cpu", "transfer_mode": "engine_driven", "transport": "zmq", "tp_size": 1},
  "checks": [
    {"name": "warm_full_hit", "expected": "2/2 chunks", "actual": "2/2 chunks", "pass": true},
    {"name": "metrics.l1_read_chunks_total.delta", "expected": "> 0", "actual": "12", "pass": true},
    {"name": "cold_full_miss", "expected": "0/2 chunks", "actual": "2/2 chunks", "pass": false}
  ]
}
```

Several scenarios → a JSON list of these objects. Same format as WS-D so results can be compared.

## 5. CI wiring (shadow first)

| Step | Where | Notes |
|---|---|---|
| Add `--strict` to existing bench call; drop grep gate later | `.github/scripts/cpu_server_bench_test.sh:148-169` | keep grep for one release as a double check |
| New step `scenarios` (CPU, zmq + grpc) | `.github/workflows/cpu_device.yml:282-296` (opt-125m leg only) | measured cost: ~20-25 s per run today |
| Shadow on Buildkite 1-GPU (`--mode gpu`) next to the engine workloads | `.buildkite/k3_tests/multiprocess/pipeline.yml` | compare verdicts with engine results for 2 weeks before removing anything |
