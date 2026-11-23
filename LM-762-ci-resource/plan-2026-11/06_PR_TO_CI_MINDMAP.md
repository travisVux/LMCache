# 06 — Mindmap: PR → CI layers

How a PR reaches "mergeable", layer by layer: today vs proposed. Numbers come from P1–P8 (30 days, 2026-10-05 → 11-04).
**Polished visual (recommended):** [06_PR_TO_CI_VISUAL.html](06_PR_TO_CI_VISUAL.html). Raw Mermaid diagrams: [06_PR_TO_CI_MINDMAP.html](06_PR_TO_CI_MINDMAP.html) or a VS Code Mermaid preview.

## Layers at a glance

| # | Layer | Question it answers | Source |
|---|---|---|---|
| 1 | PR event | What changed, who pushed, which labels? | GitHub |
| 2 | Trigger + labels | Does CI start at all? | `BK_WEB_SETUP.md:6`, `helpers.sh:53-71`, `automerge-labeler.yml:14-17` |
| 3 | Path filter / classifier | Which change class is this PR? | today `path-filter.sh`; proposed [P8 ci_rule_shadow.py](outputs/P8/ci_rule_shadow.py) |
| 4 | Test tier | Which test layers are required for this class? | [03](03_APPROACH_AND_PLAN.md), [P8 §3](outputs/P8/shadow_report.md) |
| 5 | Workload / job | Which concrete jobs run, on what hardware? | `pipeline.yml`, [P1](outputs/P1/cost_by_workload.csv) |
| 6 | Acceptance criteria | What does PASS mean for each job? | [05 YAML](05_acceptance_profile.draft.yaml), [P7](outputs/P7/criteria_inventory.md) |
| 7 | Verdict + retry | Is a red job a real bug, flake or infra? | [P1](outputs/P1/), [P2](outputs/P2/coverage_map.md), [P5](outputs/P5/baseline_decisions.md) |
| 8 | Mergeable | Time-to-green, GPU-min per PR | Observability direction (parent PDF) |

---

## 1. Mindmap (whole picture)

```mermaid
mindmap
  root((PR to mergeable))
    1 PR event
      open or push
      changed files
      labels
        full: auto-added to 95 of 100 PRs
        mp
        force-ci
        skip expensive ci
    2 Triggers
      GitHub Actions
        test.yml: CPU unit, py3.10-3.13
        cpu_device.yml: server bench + CPU vLLM E2E
      Buildkite
        k3-multiprocess-test: label mp or full, or dev push
        k3 unit, correctness, comprehensive, blend
        nightly: pin canary, baseline upload
    3 Classify by path
      Today: all or nothing
      Proposed classes
        docs
        tests_only
        other_platform
        core
        adapter vLLM or SGLang
        kernel
        kv_layout
        deps_ci
    4 Test tiers
      L0 lint
      L1 unit tests on CPU
      L2 engine-free server scenarios
      CPU E2E: vLLM-CPU + opt-125m
      L3 1-GPU real-engine smoke
      layout smoke: small or dummy model
      add-ons: restart, p2p, gds, preemption
      Full: 4-GPU TP, dual engine, perf
    5 Workloads
      4-GPU: dsv4_flash_tp
      2-GPU: vllm_bench, long_doc_qa, long_doc_qa_l2, kimi_linear_tp, p2p, deadlock, mp_autostart_tp2, preemption_correctness
      1-GPU: lm_eval, lm_eval_preemption, restart_recovery, http_api, cache_stats, lazy_offload, gds_smoke, fault_tolerance
      CPU: cpu_e2e_validation x3, server bench
    6 Acceptance
      byte-identical greedy
      lm_eval drift 0.05 and SCORE_MIN
      TTFT and throughput vs baseline
      5-day worst baseline
      ShareGPT diff
      scenario verdict JSON - new
    7 Verdict
      real bug: 1 in 30 days, PR 5383
      flake: retry passes 49-91 pct
      infra: exit 128, pip 503, port busy
      node 248 slow GPU group
      no-op SGLang jobs: 2,099
    8 Outcome
      3,099 GPU-h per 30 days
      518 GPU-min per build
      87 min p50 build, 288 p90
      queue 18.5 min p50
```

---

## 2. Today: how a PR flows (all-or-nothing)

```mermaid
flowchart LR
  PR[PR push] --> LBL{labels?}
  LBL -- "skip expensive ci" --> SKIP[MP skipped]
  LBL -- "mp / full (auto) / force-ci" --> PF{path-filter.sh}
  LBL -- none --> GHAONLY[GHA only]
  PR --> GHA[GHA: test.yml CPU unit + cpu_device.yml]
  PF -- "only docs / tests / other suite" --> SKIP
  PF -- "any code file" --> ALL[ALL ~35 MP jobs<br/>4-GPU + 2-GPU + 1-GPU + CPU]
  ALL --> Q[k8s GPU queue<br/>p50 18.5 min, 4-GPU 46 min]
  Q --> RUN[run.sh: setup + engine start<br/>~61% of GPU-min]
  RUN --> TEST[test body]
  TEST --> CRIT[thresholds hardcoded<br/>in 15+ scripts]
  CRIT -- fail --> RETRY[auto retry x2-3<br/>9,938 GPU-min]
  RETRY --> CRIT
  CRIT -- pass --> GREEN[green: 518 GPU-min / build]
  GHA --> GREEN
```

---

## 3. Proposed: class → tier → workload → acceptance

```mermaid
flowchart LR
  subgraph S1[1-2 PR + labels]
    PR[PR push / per-build diff]
    FORCE[force-ci / mp-full / mp-full-tp]
  end

  subgraph S3[3 Classifier ci_rule_shadow.py]
    DOC[docs]
    TST[tests_only]
    OTH[other_platform]
    CORE[core]
    LIFE[core + lifecycle paths]
    P2PG[core + p2p / gds paths]
    ADV[adapter vLLM]
    ADS[adapter SGLang]
    ADA[adapter all<br/>transfer_context]
    KER[kernel]
    KVL[kv_layout]
    DEP[deps_ci]
  end

  subgraph S4[4 Tiers]
    L0[L0 lint]
    L1[L1 unit CPU]
    L2[L2 engine-free<br/>server scenarios]
    CE[CPU E2E<br/>vLLM-CPU opt-125m]
    L3V[L3 smoke vLLM 1-GPU<br/>lm_eval x2 modes]
    L3S[L3 smoke SGLang 1-GPU]
    LS[layout smoke<br/>small / dummy models]
    AO[add-ons<br/>restart_recovery / p2p / gds /<br/>lm_eval_preemption]
    FULL[Full / nightly<br/>dsv4 TP4, kimi TP2,<br/>perf vs baseline, engine matrix]
  end

  subgraph S6[6 Acceptance config]
    ACC[05_acceptance_profile.yaml<br/>criteria + profiles + tiers +<br/>relaxation rules]
  end

  subgraph S7[7-8 Verdict]
    V[JSON verdict per job<br/>bug / flake / infra]
    M[mergeable<br/>core PR: ~3 GPU-min]
  end

  PR --> S3
  FORCE --> FULL
  DOC --> L0
  TST --> L0 & L1
  OTH --> L0 & L1
  CORE --> L0 & L1 & L2 & CE
  LIFE --> AO
  P2PG --> AO
  ADV --> L1 & L2 & CE & L3V
  ADS --> L1 & L2 & L3S
  ADA --> L3V & L3S & AO
  KER --> L1 & L3V & LS
  KVL --> L1 & L2 & CE & L3V & LS
  DEP --> FULL

  L1 & L2 & CE & L3V & L3S & LS & AO & FULL --> ACC
  ACC --> V --> M
```

---

## 4. Workload → future home (from P2, P4, P5, P6, P8)

```mermaid
flowchart TB
  subgraph NOW[Today: every code PR]
    W1[cache_stats 98% startup]
    W2[http_api 97%]
    W3[lazy_offload 97%]
    W4[gds_smoke 96%]
    W5[restart_recovery]
    W6[deadlock]
    W7[long_doc_qa_l2 24% flaky]
    W8[long_doc_qa]
    W9[vllm_bench]
    W10[preemption_correctness 19.9% GPU]
    W11[dsv4_flash_tp 4-GPU]
    W12[kimi_linear_tp]
    W13[lm_eval]
    W14[fault_tolerance]
    W15[p2p]
    W16[mp_autostart_tp2]
  end

  subgraph NEW[Future home]
    U[L1 connector unit test]
    SB[L2 server scenario]
    STORED[1-GPU + stored baseline]
    REPLAY[same-engine replay on PR,<br/>full on nightly]
    LSM[layout smoke 1-GPU]
    SMK[L3 smoke]
    ADD[add-on by path]
    NIGHT[nightly / label]
  end

  W1 --> U
  W2 --> SB
  W3 --> SB
  W4 --> ADD
  W5 --> ADD
  W5 -. server side .-> SB
  W6 --> SB
  W7 -- data flow --> SB
  W7 -- perf --> STORED
  W8 --> STORED
  W9 --> STORED
  W10 --> REPLAY
  W11 --> LSM
  W11 --> NIGHT
  W12 --> LSM
  W13 --> SMK
  W14 --> NIGHT
  W15 --> ADD
  W16 --> NIGHT
```

---

## 5. Where each finding plugs in

| Layer | Finding | Action | Source |
|---|---|---|---|
| 1 Labels | `full` label auto-added to 95/100 PRs → not a real signal | Use `force-ci` / new `mp-full` | P8 §1 |
| 3 Classifier | MP is all-or-nothing today | Path classes → tiers; saves ~80% PR GPU-min, 0 missed catches | P8 |
| 4 Tiers | ~61% of GPU-min is setup + engine start | Move server-level checks to L2 (no engine) | P1, P4 |
| 4 Tiers | XPU already runs 1-device HMA layout smoke | Port to CUDA as layout smoke | P6 |
| 5 Workloads | 2,099 no-op SGLang jobs (~20 min queue each) | Remove from matrix | P1, P2 |
| 5 Workloads | `preemption_correctness` labeled 1-GPU, uses 2-GPU pod | Fix label; replay on PR | P1, P5 |
| 6 Acceptance | 4 defaults for one `SCORE_TOLERANCE`; TTFT check never runs (C9); empty baseline passes (C11) | Central YAML + small fix PRs | P7 |
| 6 Acceptance | `lmcache bench server` exits 0 on failed checks | Fix exit code before using as gate | P4 |
| 7 Verdict | Failures cluster on node 248; SGLang long_doc_qa regression since ~10-27 hidden by retry | Log GPU identity; report regression | P5 |
| 7 Verdict | Only 1 real code catch in 30 days (PR #5383) — and CPU E2E caught it too | Supports cheaper default tiers | P2 |
| — Security | HF_TOKEN plaintext in Buildkite UI config | Ask maintainers to rotate | P1 |
