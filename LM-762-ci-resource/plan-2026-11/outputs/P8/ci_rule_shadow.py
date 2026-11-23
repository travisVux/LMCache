#!/usr/bin/env python3
"""ci_rule_shadow.py -- shadow classifier for the WS-C "minimum-sufficient test" rule.

Read-only. Prints what the rule WOULD run for a PR. It never changes CI.

Usage:
    python ci_rule_shadow.py --pr 5383                  # files + labels via `gh`
    python ci_rule_shadow.py --files a.py b/c.py        # explicit file list
    python ci_rule_shadow.py --files-from list.txt      # one path per line ("-" = stdin)
    python ci_rule_shadow.py --pr 5383 --labels force-ci  # extra labels
    python ci_rule_shadow.py --selftest

Output (JSON on stdout):
    {"pr": 5383, "classes": [...], "required_tiers": [...], "reasons": [...],
     "mp_workloads": [...], "est_gpu_min_per_build": 20.6}

Tiers (cheap -> expensive):
    lint             pre-commit / code_quality_checks.yml
    L1_changed       only the changed test files
    L1               unit tests (GHA test.yml CPU + Buildkite unit pod 1 GPU, not the MP pipeline)
    L1_gpu_kernels   GPU kernel unit tests in the Buildkite unit pod (tests/v1/test_mem_kernels.py ...)
    L2               engine-free server scenarios (`lmcache bench server`, see P4)
    cpu_e2e          cpu_e2e_validation (vLLM-CPU, 0 GPU)
    L3_smoke:<eng>   1-GPU real-engine smoke for that engine (today: lm_eval lmcache_driven + engine_driven)
    L3_preempt:vllm  1-GPU lm_eval_preemption (both transfer modes)
    L3_lifecycle:vllm 1-GPU restart_recovery (server restart -> worker re-register)
    layout_smoke     P6 small-model layout smoke set (dummy weights, mostly 1 GPU, kimi TP2)
    mp_workload:<w>  just one existing MP workload (when only its script changed)
    full             the whole k3-multiprocess pipeline (today's behaviour)

Notes:
  * `full` label is NOT an override: .github/workflows/automerge-labeler.yml:14-17
    adds it to every auto-merge PR (95 of the last 100 merged PRs carry it).
    Overrides are `force-ci` (path-filter.sh:313-317) and the proposed `mp-full`.
  * Unknown paths -> `full` (same safe default as path-filter.sh:221-223).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# RULES TABLE  (first match wins; order matters)
#   pattern        : regex on repo-relative path (forward slashes)
#   classes        : tuple of change classes
#   engine         : for adapter / kv_layout: vllm | sglang | all | none
#   extra          : extra tiers added on top of the class default
#   tiers          : if set, REPLACES the class default tiers for this file
#   why            : short reason, with evidence where it exists
# ---------------------------------------------------------------------------
NON_CUDA_DEV = r"(xpu|musa|rbln|npu|hpu|mlu|neuron|supa|rocm|maca)"


@dataclass(frozen=True)
class Rule:
    pattern: str
    classes: tuple
    why: str
    engine: str = "none"
    extra: tuple = ()
    tiers: tuple | None = None


R = Rule
RULES: list[Rule] = [
    # ---- docs -----------------------------------------------------------
    R(r"\.(md|rst|txt\.example)$", ("docs",), "markdown / rst only"),
    R(r"^(docs|asset)/", ("docs",), "docs/ and asset/ (path-filter.sh:49-50)"),
    R(r"^(LICENSE|NOTICE)(\..*)?$|^(CODEOWNERS|DCO|\.mailmap|\.gitattributes|\.gitignore|\.editorconfig)$",
      ("docs",), "repo meta file (path-filter.sh:45-48)"),
    R(r"^\.(claude|cursor|gemini|agents)/", ("docs",), "agent config, not shipped"),
    R(r"^examples/", ("docs",), "examples are not run by MP (path-filter.sh:144-146)"),
    R(r"^(format\.sh|\.pre-commit-config\.yaml|\.clang-format|\.isort\.cfg)$", ("docs",),
      "lint config: lint job covers it", tiers=("lint",)),
    # ---- CI / deps --------------------------------------------------------
    R(r"^requirements/(maca_core|rocm_core)\.txt$", ("other_platform",), "non-CUDA platform pins"),
    R(r"^requirements/", ("deps_ci",), "dependency pins change every engine env (ci-base.Dockerfile:31-32)"),
    R(r"^(pyproject\.toml|setup\.py|CMakeLists\.txt|MANIFEST\.in)$", ("deps_ci",), "build / packaging"),
    R(r"^setup_extensions/build_profiles/(rocm|sycl|rbln|maca|musa)\.py$", ("other_platform",),
      "non-CUDA build profile"),
    R(r"^setup_extensions/", ("deps_ci",), "native extension build"),
    R(r"^(pyproject_cli\.toml|pytest\.ini)$", ("deps_ci",), "CLI pkg / pytest config only",
      tiers=("lint", "L1")),
    R(r"^\.buildkite/k3_harness/setup-blend-env\.sh$", ("deps_ci",), "blend suite only (path-filter.sh:173)",
      tiers=("lint",)),
    R(r"^\.buildkite/k3_harness/", ("deps_ci",), "shared harness: setup-env / pinned engine versions"),
    R(r"^\.buildkite/k3_tests/common_scripts/", ("deps_ci",), "shared upload / filter code (path-filter.sh:65-69)"),
    # MP workload scripts: run only the workload whose script changed
    R(r"^\.buildkite/k3_tests/multiprocess/scripts/workloads/common/lm-eval\.sh$", ("deps_ci",),
      "lm-eval.sh drives lm_eval + lm_eval_preemption",
      tiers=("lint", "mp_workload:lm_eval", "mp_workload:lm_eval_preemption")),
    R(r"^\.buildkite/k3_tests/multiprocess/scripts/workloads/common/long-doc-qa-l2", ("deps_ci",),
      "long_doc_qa_l2 scripts", tiers=("lint", "mp_workload:long_doc_qa_l2")),
    R(r"^\.buildkite/k3_tests/multiprocess/scripts/workloads/common/long[-_]doc[-_]qa", ("deps_ci",),
      "long_doc_qa scripts", tiers=("lint", "mp_workload:long_doc_qa", "mp_workload:long_doc_qa_l2")),
    R(r"^\.buildkite/k3_tests/multiprocess/scripts/workloads/verification/", ("deps_ci",),
      "L1 round-trip verifier used by dsv4 + kimi",
      tiers=("lint", "mp_workload:dsv4_flash_tp", "mp_workload:kimi_linear_tp")),
    R(r"^\.buildkite/k3_tests/multiprocess/scripts/tests/", ("deps_ci",), "harness self-tests",
      tiers=("lint", "L1")),
    R(r"^\.buildkite/k3_tests/multiprocess/scripts/workloads/(vllm|sglang)/(hma[-_]|hma_bit)", ("deps_ci",),
      "hma_* correctness scripts = layout smoke checkers (P6 sec.5)", tiers=("lint", "layout_smoke")),
    R(r"^\.buildkite/k3_tests/multiprocess/scripts/workloads/(vllm|sglang|common)/[^/]+\.sh$", ("deps_ci",),
      "single workload script -> that workload only", tiers=("lint", "mp_workload:<from_script>")),
    R(r"^\.buildkite/k3_tests/multiprocess/", ("deps_ci",),
      "MP pipeline.yml / run.sh / engines / helpers -> all MP steps"),
    R(r"^\.buildkite/k3_tests/unit/", ("deps_ci",), "unit suite only", tiers=("lint", "L1")),
    R(r"^\.buildkite/k3_tests/[^/]+/", ("other_platform",), "other k3 suite (xpu/amd/integration/...): not MP"),
    R(r"^\.buildkite/(pipeline\.yml|pipelines/unit-tests)", ("deps_ci",), "unit upload pipeline",
      tiers=("lint", "L1")),
    R(r"^\.buildkite/(configs|cases|correctness|coordinator_controllers|metax|operator|scripts|pipelines)/",
      ("other_platform",), "legacy / other Buildkite suites, not k3-multiprocess"),
    R(r"^\.buildkite/", ("deps_ci",), "unknown Buildkite file: safe default"),
    R(r"^\.github/scripts/run-cpu-e2e-validation\.sh$", ("deps_ci",), "the CPU E2E script itself",
      tiers=("lint", "cpu_e2e")),
    R(r"^\.github/scripts/cpu_server_bench_test\.sh$", ("deps_ci",), "server-bench CI script", tiers=("lint", "L2")),
    R(r"^\.github/scripts/pin-tested-vllm\.sh$", ("deps_ci",), "decides which vLLM all MP jobs use"),
    R(r"^\.github/", ("deps_ci",), "GHA only: Buildkite MP not affected (path-filter.sh:51)", tiers=("lint",)),
    R(r"^docker/", ("deps_ci",), "release images; MP pods use lmcache/ci-base from k3_harness (pipeline.yml:117)",
      tiers=("lint", "L1")),
    R(r"^operator/", ("other_platform",), "k8s operator has its own CI (operator_ci.yml)"),
    R(r"^benchmarks/long_doc_qa/", ("deps_ci",), "long_doc_qa benchmark used by MP (path-filter.sh:141)",
      tiers=("lint", "mp_workload:long_doc_qa", "mp_workload:long_doc_qa_l2")),
    R(r"^(benchmarks|tools)/", ("tests_only",), "bench / tool scripts, not MP", tiers=("lint", "L1")),
    # ---- tests ------------------------------------------------------------
    R(rf"^tests/v1/platform/devices/{NON_CUDA_DEV}/", ("other_platform",), "non-CUDA device tests"),
    R(r"^tests/", ("tests_only",), "test code only"),
    # ---- kernels / native -------------------------------------------------
    R(r"^csrc/(engine_kv_format\.h|kv_transfer_plan_types\.h|kv_transfer_types\.h)$", ("kernel", "kv_layout"),
      "KV format / transfer-plan headers shared by kernels", engine="vllm"),
    R(r"^csrc/sycl/", ("other_platform",), "XPU kernels"),
    R(r"^csrc/(lmcache_native|storage_manager)/", ("core",), "CPU native helpers (bitmap/fold/ttl lock)"),
    R(r"^csrc/storage_backends/", ("core",), "native L2 storage backends"),
    R(r"^csrc/", ("kernel",), "CUDA kernels / bindings"),
    R(r"^rust/", ("core",), "raw_block L2 adapter (GHA raw_block job, test.yml:56-66)"),
    # ---- platform ---------------------------------------------------------
    R(r"^lmcache/v1/platform/torch_ops/_kv_format\.py$", ("kv_layout",), "KV format torch ops", engine="vllm"),
    R(rf"^lmcache/v1/platform/devices/{NON_CUDA_DEV}/", ("other_platform",), "non-CUDA device backend"),
    R(r"^lmcache/v1/platform/devices/cpu/", ("core",), "CPU device path = what cpu_e2e runs"),
    R(r"^lmcache/v1/platform/", ("kernel",), "CUDA device / stream / cache-context layer"),
    # ---- KV layout --------------------------------------------------------
    R(r"^lmcache/v1/gpu_connector/kv_format/detectors/sglang\.py$", ("kv_layout",), "SGLang KV format",
      engine="sglang"),
    R(r"^lmcache/v1/gpu_connector/kv_format/detectors/(atom|trtllm)\.py$", ("kv_layout",),
      "KV format of an engine with no MP CI job", engine="none"),
    R(r"^lmcache/v1/gpu_connector/kv_format/", ("kv_layout",), "KV format specs / detection", engine="vllm"),
    R(r"^lmcache/v1/gpu_connector/gds_backends/", ("kernel",), "GDS / cuFile path",
      extra=("mp_workload:gds_smoke",)),
    R(r"^lmcache/v1/gpu_connector/", ("kernel",), "GPU connector copy paths"),
    R(r"^lmcache/v1/kv_layer_groups\.py$", ("kv_layout", "core"), "layer grouping by identity (P6 sec.2)",
      engine="vllm"),
    R(r"^lmcache/v1/kv_codec/", ("kv_layout",), "KV codec (asym k16/v8)", engine="vllm"),
    R(r"^lmcache/v1/distributed/serde/fp8\.py$", ("kv_layout", "core"), "fp8 serde", engine="vllm"),
    R(r"^lmcache/v1/distributed/serde/turboquant/", ("kernel", "kv_layout"),
      "quantized KV store kernels (#5994 FP8 key store on SM80)", engine="vllm"),
    # ---- adapters / connectors ------------------------------------------
    R(r"^lmcache/integration/vllm/(kv_cache_groups|kv_cache_group_edits)\.py$", ("adapter", "kv_layout"),
      "vLLM HMA kv_cache_groups (#4437 -> #4488 gemma-4 break)", engine="vllm"),
    R(r"^lmcache/integration/vllm/utils\.py$", ("adapter", "kv_layout"),
      "holds mla_only() (P6 sec.2; #4219)", engine="vllm"),
    R(r"^lmcache/integration/sglang/unified_kv_adapter\.py$", ("adapter", "kv_layout"), "SGLang KV adapter",
      engine="sglang"),
    R(r"^lmcache/integration/vllm/lazy_offload", ("adapter",), "lazy offload policy", engine="vllm",
      extra=("mp_workload:lazy_offload",)),
    R(r"^lmcache/integration/vllm/mp_server_launcher\.py$", ("adapter",), "MP autostart", engine="vllm",
      extra=("mp_workload:mp_autostart_tp2",)),
    R(r"^lmcache/integration/vllm/vllm_multi_process_adapter\.py$", ("adapter",),
      "worker adapter: re-register on restart (#3208, #4018)", engine="vllm",
      extra=("L3_lifecycle:vllm",)),
    R(r"^lmcache/integration/vllm/lmcache_mp_connector\.py$", ("adapter",),
      "scheduler connector: #5383 crash, #5248 preemption", engine="vllm", extra=("L3_preempt:vllm",)),
    R(r"^lmcache/integration/vllm/", ("adapter",), "vLLM integration", engine="vllm"),
    R(r"^lmcache/integration/sglang/", ("adapter",), "SGLang integration", engine="sglang"),
    R(r"^lmcache/integration/(tensorrt_llm|atom)/", ("adapter",), "engine without an MP CI job", engine="none"),
    R(r"^lmcache/integration/", ("adapter",), "shared integration code", engine="all"),
    R(r"^lmcache/inprocess/integration/", ("other_platform",), "legacy in-process connector (not MP)"),
    # worker-side MP code runs inside the engine process / GPU transfer path
    R(r"^lmcache/v1/multiprocess/transfer_context/", ("adapter", "kv_layout"),
      "engine-side transfer ctx (#4018 restart, #4830 async copy, #5248 preempt, #4072; multi-group #4410/#6124)",
      engine="all", extra=("L3_lifecycle:vllm", "L3_preempt:vllm")),
    R(r"^lmcache/v1/multiprocess/(modules/(engine_driven_transfer|server_transfer|lmcache_driven_transfer)|object_group_transfer|group_view)\.py$",
      ("core", "kv_layout"), "per-group transfer plan (multi-group #4410, dsv4 groups #6124); GPU IPC not in CPU E2E (P2 d2)",
      engine="vllm", extra=("L3_smoke:vllm",)),
    R(r"^lmcache/v1/multiprocess/(posix_shm|native_completion)\.py$",
      ("core",), "GPU/SHM transfer path: CPU E2E does not cover GPU IPC (P2 d2)",
      extra=("L3_smoke:vllm",)),
    R(r"^lmcache/v1/multiprocess/(server|engine_context|heartbeat|session)\.py$|^lmcache/v1/multiprocess/modules/management\.py$",
      ("core",), "server lifecycle / registration (restart_recovery only real catcher, P2 b1 #4018)",
      extra=("L3_lifecycle:vllm",)),
    R(r"^lmcache/v1/memory_allocators/", ("core",), "host pinning / allocator (#4018)",
      extra=("L3_lifecycle:vllm",)),
    R(r"(^|/)[^/]*p2p[^/]*(/|$)|^lmcache/v1/distributed/transfer_channel/", ("core",),
      "P2P peer transfer: only p2p workload covers GPU peer fetch (P2 d2)", extra=("mp_workload:p2p",)),
    R(r"(^|/)[^/]*gds[^/]*(/|$)", ("core",), "GDS path (P2 d2)", extra=("mp_workload:gds_smoke",)),
    # ---- core (catch-all for lmcache/) ------------------------------------
    R(r"^lmcache/v1/", ("core",), "LMCache v1 core (MP server, storage, distributed, identity)"),
    R(r"^lmcache/inprocess/", ("core",), "legacy pkg, still imported by lmcache/v1 (kv_layer_groups.py, protocol.py)"),
    R(r"^lmcache/", ("core",), "LMCache package (cli / sdk / frontend / tools)"),
]

# A second pass: keyword tags that ADD kv_layout to lmcache/ or csrc/ files.
KV_LAYOUT_KEYWORDS = re.compile(r"(mla|mamba|hybrid|hma_|fp8|kv_format|kv_layout|kv_layer_group|kv_cache_group)",
                                re.I)

ENGINES_WITH_MP_JOB = ("vllm", "sglang")


def _class_tiers(cls: str, engine: str) -> list[str]:
    """Default tiers per change class (refined WS-C table)."""
    eng = list(ENGINES_WITH_MP_JOB) if engine == "all" else ([engine] if engine in ENGINES_WITH_MP_JOB else [])
    if cls == "docs":
        return ["lint"]
    if cls == "tests_only":
        return ["lint", "L1_changed"]
    if cls == "other_platform":
        return ["lint", "L1"]
    if cls == "core":
        # P2: cpu_e2e (0 GPU) catches identity / lookup / store / connector start
        return ["lint", "L1", "L2", "cpu_e2e"]
    if cls == "adapter":
        t = ["lint", "L1", "L2"]
        if engine in ("vllm", "all"):
            t.append("cpu_e2e")  # P2 b1: #5383 connector crash caught by cpu_e2e
        t += [f"L3_smoke:{e}" for e in eng]
        return t
    if cls == "kernel":
        return ["lint", "L1", "L1_gpu_kernels", "L3_smoke:vllm", "layout_smoke"]
    if cls == "kv_layout":
        t = ["lint", "L1", "L2", "cpu_e2e", "layout_smoke"]
        t += [f"L3_smoke:{e}" for e in (eng or [])]
        return t
    if cls == "deps_ci":
        return ["full"]
    return ["full"]


OVERRIDE_LABELS = {"force-ci", "mp-full"}
FULL_TP_LABELS = {"mp-full-tp"}
SKIP_LABELS = {"skip expensive ci"}

TIER_ORDER = ["lint", "L1_changed", "L1", "L1_gpu_kernels", "L2", "cpu_e2e", "L3_smoke:vllm", "L3_smoke:sglang",
              "L3_preempt:vllm", "L3_lifecycle:vllm", "layout_smoke", "full_tp", "full"]

# Which TODAY's MP workloads each tier corresponds to (for cost + "would it still catch").
TIER_WORKLOADS = {
    "cpu_e2e": [("cpu_e2e_validation", None)],
    "L3_smoke:vllm": [("lm_eval", "vllm")],
    "L3_smoke:sglang": [("lm_eval", "sglang")],
    "L3_preempt:vllm": [("lm_eval_preemption", "vllm")],
    "L3_lifecycle:vllm": [("restart_recovery", "vllm")],
    "full_tp": [("dsv4_flash_tp", None), ("kimi_linear_tp", None)],
    "layout_smoke": [("hma_dsv4_correctness", None)],  # new set; nearest existing job
}

# Estimated GPU-min per build for each tier (P1 cost_by_workload.csv p50, P6 sec.5 estimates).
TIER_GPU_MIN = {
    "lint": 0.0, "L1_changed": 0.0, "L1": 0.0, "L1_gpu_kernels": 0.0,  # not in the MP pipeline
    "L2": 0.0, "cpu_e2e": 0.0,
    "L3_smoke:vllm": 2 * 10.29, "L3_smoke:sglang": 2 * 10.29,  # lm_eval gpu_min_p50 x 2 modes
    "L3_preempt:vllm": 2 * 9.70,  # lm_eval_preemption p50 x 2 modes
    "L3_lifecycle:vllm": 2 * 9.81,  # restart_recovery p50 x zmq+grpc
    "layout_smoke": 58.0,  # P6 sec.5: 5+5+15+16+8+4+5 (UNKNOWN until measured)
    "full_tp": 86.6 + 28.68,  # dsv4 + kimi gpu_min_per_pr_build
    "full": 535.0,  # sum of gpu_min_per_pr_build over all workloads (P1)
}
WORKLOAD_GPU_MIN_PER_BUILD = {  # P1 cost_by_workload.csv gpu_min_per_pr_build
    "cache_stats": 6.83, "cpu_e2e_validation": 0.0, "deadlock": 19.36, "dsv4_flash_tp": 86.6,
    "fault_tolerance": 12.29, "gds_smoke": 7.04, "http_api": 17.43, "kimi_linear_tp": 28.68,
    "lazy_offload": 6.88, "lm_eval": 39.44, "lm_eval_preemption": 18.96, "long_doc_qa": 62.35,
    "long_doc_qa_l2": 41.15, "mp_autostart_tp2": 8.52, "p2p": 14.63, "preemption_correctness": 108.58,
    "restart_recovery": 19.22, "vllm_bench": 37.36,
}

SCRIPT_TO_WORKLOAD = {  # workloads/<eng>/<script>.sh -> workload key
    "cache-stats": "cache_stats", "dsv4-flash-tp": "dsv4_flash_tp", "fault-tolerance": "fault_tolerance",
    "gds-smoke": "gds_smoke", "kimi-linear-tp": "kimi_linear_tp", "lazy-offload": "lazy_offload",
    "mp-autostart-tp2": "mp_autostart_tp2", "p2p": "p2p", "preemption-correctness": "preemption_correctness",
    "vllm-bench": "vllm_bench", "deadlock": "deadlock", "http-api": "http_api",
    "restart-recovery": "restart_recovery", "high-concurrency": "deadlock",
}


@dataclass
class Result:
    pr: int | None
    classes: list = field(default_factory=list)
    required_tiers: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    mp_workloads: list = field(default_factory=list)
    est_gpu_min_per_build: float = 0.0
    files: list = field(default_factory=list)
    per_file: list = field(default_factory=list)


def _match(path: str) -> Rule | None:
    for rule in RULES:
        if re.search(rule.pattern, path):
            return rule
    return None


def classify_file(path: str) -> tuple[list[str], list[str], str]:
    """Return (classes, tiers, reason) for one file."""
    path = path.replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    rule = _match(path)
    if rule is None:
        return ["deps_ci"], ["full"], f"{path}: unmatched -> full (safe default, path-filter.sh:221-223)"
    classes = list(rule.classes)
    engine = rule.engine
    if (path.startswith("lmcache/") or path.startswith("csrc/")) and "kv_layout" not in classes \
            and "other_platform" not in classes and "docs" not in classes \
            and KV_LAYOUT_KEYWORDS.search(path.rsplit("/", 1)[-1]):
        classes.append("kv_layout")
        if engine == "none":
            engine = "vllm"
    if rule.tiers is not None:
        tiers = list(rule.tiers)
        if "mp_workload:<from_script>" in tiers:
            stem = path.rsplit("/", 1)[-1][:-3]
            wl = SCRIPT_TO_WORKLOAD.get(stem)
            tiers.remove("mp_workload:<from_script>")
            tiers.append(f"mp_workload:{wl}" if wl else "full")
    else:
        tiers = []
        for c in classes:
            tiers += _class_tiers(c, engine)
    tiers += list(rule.extra)
    return classes, sorted(set(tiers), key=_tier_key), f"{path}: {'+'.join(classes)} -- {rule.why}"


def _tier_key(t: str):
    if t in TIER_ORDER:
        return (TIER_ORDER.index(t), t)
    return (TIER_ORDER.index("layout_smoke") + 0.5, t)  # mp_workload:* sits between layout and full


def classify(files: list[str], labels: list[str] | None = None, pr: int | None = None) -> Result:
    labels = [x.strip() for x in (labels or []) if x.strip()]
    res = Result(pr=pr, files=list(files))
    classes, tiers = set(), set()
    for f in files:
        c, t, why = classify_file(f)
        classes.update(c)
        tiers.update(t)
        res.per_file.append({"file": f, "classes": c, "tiers": t})
        res.reasons.append(why)
    if not files:
        tiers.add("full")
        res.reasons.append("no changed files known -> full (path-filter.sh:331-334)")
    lab = set(labels)
    if lab & OVERRIDE_LABELS:
        tiers.add("full")
        res.reasons.append(f"label {sorted(lab & OVERRIDE_LABELS)} -> full override")
    if lab & FULL_TP_LABELS:
        tiers.add("full_tp")
        res.reasons.append("label mp-full-tp -> add dsv4_flash_tp + kimi_linear_tp")
    if "full" in lab and not (lab & OVERRIDE_LABELS):
        res.reasons.append("label 'full' ignored: auto-added on auto-merge (automerge-labeler.yml:14-17)")
    if lab & SKIP_LABELS and not (lab & OVERRIDE_LABELS):
        res.reasons.append("label 'skip expensive ci' -> today MP is skipped (helpers.sh:65-67); rule output shown "
                           "for comparison only")
    if "full" in tiers:
        tiers = {"lint", "L1", "full"} | {t for t in tiers if t in ("L2", "cpu_e2e", "layout_smoke")}
    res.classes = sorted(classes)
    res.required_tiers = sorted(tiers, key=_tier_key)
    res.mp_workloads = mp_workloads_for(res.required_tiers)
    res.est_gpu_min_per_build = round(estimate_gpu_min(res.required_tiers), 2)
    return res


def mp_workloads_for(tiers: list[str]) -> list[str]:
    if "full" in tiers:
        return ["ALL"]
    out = []
    for t in tiers:
        if t.startswith("mp_workload:"):
            out.append(t.split(":", 1)[1])
        for wl, eng in TIER_WORKLOADS.get(t, []):
            out.append(f"{wl}" + (f"@{eng}" if eng else ""))
    return sorted(set(out))


def estimate_gpu_min(tiers: list[str]) -> float:
    if "full" in tiers:
        return TIER_GPU_MIN["full"] + (TIER_GPU_MIN["layout_smoke"] if "layout_smoke" in tiers else 0.0)
    total = 0.0
    for t in tiers:
        if t.startswith("mp_workload:"):
            total += WORKLOAD_GPU_MIN_PER_BUILD.get(t.split(":", 1)[1], 0.0)
        else:
            total += TIER_GPU_MIN.get(t, 0.0)
    return total


# ---------------------------------------------------------------------------
# gh helpers (read-only)
# ---------------------------------------------------------------------------
def gh_pr_files_labels(pr: int, repo: str = "LMCache/LMCache") -> tuple[list[str], list[str]]:
    out = subprocess.run(["gh", "pr", "view", str(pr), "-R", repo, "--json", "files,labels,changedFiles"],
                         check=True, capture_output=True, text=True, encoding="utf-8").stdout
    d = json.loads(out)
    files = [f["path"] for f in d.get("files", [])]
    if d.get("changedFiles", 0) > len(files):  # gh caps files at 100 -> paginate REST
        out = subprocess.run(["gh", "api", "--paginate", f"repos/{repo}/pulls/{pr}/files?per_page=100",
                              "--jq", ".[].filename"], check=True, capture_output=True, text=True,
                             encoding="utf-8").stdout
        files = [x for x in out.splitlines() if x.strip()]
    return files, [lb["name"] for lb in d.get("labels", [])]


# ---------------------------------------------------------------------------
# self-tests
# ---------------------------------------------------------------------------
def selftest() -> None:
    def t(files, labels=None):
        return classify(files, labels)

    r = t(["docs/source/mp/configuration.rst", "README.md"])
    assert r.classes == ["docs"] and r.required_tiers == ["lint"], r
    r = t(["tests/v1/multiprocess/test_mq.py"])
    assert r.classes == ["tests_only"] and "L1_changed" in r.required_tiers and r.est_gpu_min_per_build == 0
    r = t(["lmcache/v1/multiprocess/modules/lookup.py"])
    assert r.classes == ["core"] and "cpu_e2e" in r.required_tiers and "full" not in r.required_tiers
    # PR #5383 file set: the connector bug must still get cpu_e2e (the layer that caught it)
    r5383 = t(["lmcache/integration/vllm/lmcache_mp_connector.py", "lmcache/v1/multiprocess/modules/lookup.py",
               "tests/v1/test_vllm_mp_adapter.py", "docs/design/v1/multiprocess/modules/apc_covered_lookup.md"])
    assert "adapter" in r5383.classes and "cpu_e2e" in r5383.required_tiers
    assert "L3_smoke:vllm" in r5383.required_tiers and "L3_smoke:sglang" not in r5383.required_tiers
    # PR #4018-like change: allocator + worker transfer -> restart_recovery kept
    r = t(["lmcache/v1/memory_allocators/lazy_memory_allocator.py",
           "lmcache/v1/multiprocess/transfer_context/worker_transfer.py"])
    assert "L3_lifecycle:vllm" in r.required_tiers and "restart_recovery@vllm" in r.mp_workloads
    r = t(["lmcache/integration/sglang/unified_lmcache_mp_connector.py"])
    assert r.required_tiers == ["lint", "L1", "L2", "L3_smoke:sglang"], r.required_tiers
    r = t(["csrc/cuda/mp_mem_kernels.cu"])
    assert r.classes == ["kernel"] and "layout_smoke" in r.required_tiers and "L1_gpu_kernels" in r.required_tiers
    r = t(["lmcache/integration/vllm/kv_cache_groups.py"])
    assert {"adapter", "kv_layout"} <= set(r.classes) and "layout_smoke" in r.required_tiers
    r = t(["lmcache/v1/foo/mamba_state.py"])
    assert "kv_layout" in r.classes  # keyword pass
    r = t(["requirements/common.txt"])
    assert r.required_tiers[-1] == "full" and r.mp_workloads == ["ALL"]
    r = t([".github/workflows/test.yml"])
    assert r.required_tiers == ["lint"]
    r = t([".buildkite/k3_tests/multiprocess/scripts/workloads/vllm/cache-stats.sh"])
    assert r.mp_workloads == ["cache_stats"], r.mp_workloads
    r = t([".buildkite/k3_tests/multiprocess/pipeline.yml"])
    assert "full" in r.required_tiers
    r = t(["lmcache/v1/multiprocess/server.py"], labels=["full"])
    assert "full" not in r.required_tiers  # 'full' label is auto-added: not an override
    r = t(["lmcache/v1/multiprocess/server.py"], labels=["force-ci"])
    assert "full" in r.required_tiers
    r = t(["some_new_top_level_file.cfg"])
    assert "full" in r.required_tiers  # safe default
    r = t(["lmcache/v1/platform/devices/xpu/foo.py", "tests/v1/platform/devices/musa/test_x.py"])
    assert r.classes == ["other_platform"] and r.est_gpu_min_per_build == 0
    r = t([])
    assert "full" in r.required_tiers
    print("selftest: OK (18 cases)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pr", type=int)
    g.add_argument("--files", nargs="+")
    g.add_argument("--files-from")
    g.add_argument("--selftest", action="store_true")
    ap.add_argument("--labels", nargs="*", default=[])
    ap.add_argument("--repo", default="LMCache/LMCache")
    ap.add_argument("--verbose", action="store_true", help="include per-file detail")
    a = ap.parse_args(argv)
    if a.selftest:
        selftest()
        return 0
    labels = list(a.labels)
    if a.pr:
        files, gh_labels = gh_pr_files_labels(a.pr, a.repo)
        labels += gh_labels
    elif a.files:
        files = a.files
    else:
        fh = sys.stdin if a.files_from == "-" else open(a.files_from, encoding="utf-8")
        files = [x.strip() for x in fh if x.strip()]
    r = classify(files, labels, a.pr)
    out = {"pr": r.pr, "classes": r.classes, "required_tiers": r.required_tiers, "reasons": r.reasons,
           "mp_workloads": r.mp_workloads, "est_gpu_min_per_build": r.est_gpu_min_per_build}
    if a.verbose:
        out["per_file"] = r.per_file
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
