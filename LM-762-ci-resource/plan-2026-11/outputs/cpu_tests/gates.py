"""Single source of truth for gates, tiers, change classes, E2E workloads and section descriptions.

Every view of 06_PR_TO_CI_VISUAL.html reads these tables (via build_gates.py). Change a gate or a
tier HERE, never in the HTML. Sources: P1 (Buildkite cost, 30 d to 2026-11-04), P2 (coverage),
P7 (criteria), P8 (shadow rule), GHA run 42189301949 + k3-unit-tests #14829 (2026-11-06).
Text fields come in pairs (EN, VI).
"""

# ---------------------------------------------------------------- jobs (who gates what)
# gate: merge | release | advisory ; tier: link to TIERS id
JOBS = [
    dict(id="dco", name="DCO", where="GitHub", gate=["merge"], tier="",
         runs=("GitHub app", "GitHub app"), what=("Signed-off-by on every commit", "Mọi commit có Signed-off-by"), time=("seconds", "vài giây")),
    dict(id="cq", name="Check code quality", where="GHA code_quality_checks.yml", gate=["merge"], tier="L0",
         runs=("CPU", "CPU"), what=("pre-commit (ruff, mypy, codespell, LMCache bans); on pass it starts GHA Test + CPU device (#6730)",
                                    "pre-commit (ruff, mypy, codespell, luật cấm LMCache); pass thì mới chạy GHA Test + CPU device (#6730)"),
         time=("< 1 min", "< 1 phút"), gates_next=["ght", "cpud"]),
    dict(id="k3u", name="k3-unit-tests", where="Buildkite", gate=["merge"], tier="L1G", ready_only=True,   # #6730: builds ready (non-draft) commits only
         runs=("1 GPU pod", "1 GPU pod"), what=("All tests/ incl. cuda-marked, no vLLM, --maxfail=1 · ready PRs only", "Toàn bộ tests/ gồm test cuda, không vLLM, --maxfail=1 · chỉ PR ready"),
         time=("25 min queue + 24 min run", "chờ 25 phút + chạy 24 phút")),
    dict(id="k3mp", name="k3-multiprocess-test", where="Buildkite", gate=["merge"], tier="FULL", part="heavy", ready_only=True,
         runs=("~35 jobs, 0–4 GPU", "~35 job, 0–4 GPU"),
         what=("Heavy MP suite · bypassed on ordinary PRs (green in ~5 s, #6731); runs with label full / force-ci / mp or CI-deps, SGLang, long_doc_qa paths",
               "Bộ MP nặng · bỏ qua trên PR thường (xanh sau ~5 s, #6731); chạy khi có nhãn full / force-ci / mp hoặc đổi path CI-deps, SGLang, long_doc_qa"),
         time=("87 min p50 full · ~5 s bypassed", "87 phút p50 khi đủ · ~5 s khi bỏ qua"), labels=["full", "force-ci", "mp"]),
    dict(id="k3mps", name="k3-multiprocess-smoke", where="Buildkite", gate=["advisory"], tier="MS", part="smoke", ready_only=True,
         runs=("0–1 GPU per job", "0–1 GPU mỗi job"),
         what=("6 GPU workloads + cpu_e2e_validation on every ready PR (#6731) · skipped for docs / tests-only (should-run-expensive-tests.sh) unless force-ci",
               "6 workload GPU + cpu_e2e_validation trên mọi PR ready (#6731) · bỏ qua khi chỉ đổi docs / tests (should-run-expensive-tests.sh), trừ khi có force-ci"),
         time=("~10–30 min", "~10–30 phút")),
    dict(id="ght", name="Test · py3.11–3.14 (drafts: 3.12 only)", where="GHA test.yml, inside the Check code quality run (#6730)", gate=["release", "advisory"], tier="L1", after="cq",
         runs=("CPU, 4 Python versions", "CPU, 4 phiên bản Python"), what=('-m "not (cuda or …)" · 9,326 passed · only place the 327 vLLM-connector tests run', '-m "not (cuda or …)" · 9,326 pass · nơi duy nhất chạy 327 test vLLM connector'),
         time=("≈19 min × 4", "≈19 phút × 4")),
    dict(id="cpud", name="CPU device", where="GHA cpu_device.yml, inside the Check code quality run (#6730)", gate=["advisory"], tier="CE", after="cq",
         runs=("CPU · Ubuntu + macOS", "CPU · Ubuntu + macOS"), what=("cpu_e2e_validation script, 6 legs (opt-125m + MLA dummy; grpc / grpc-aio / grpc-native)", "script cpu_e2e_validation, 6 leg (opt-125m + MLA dummy; grpc / grpc-aio / grpc-native)"),
         time=("11–16 min / leg", "11–16 phút / leg")),
    dict(id="ghsmall", name="gRPC native · token-drop · raw-block · Rust · HF3FS", where="GHA test.yml", gate=["advisory"], tier="",
         runs=("CPU", "CPU"), what=("Small jobs, only when their paths change · skipped on drafts", "Job nhỏ, chỉ chạy khi path của nó đổi · bỏ qua với PR nháp"), time=("1–4 min", "1–4 phút")),
]

# ---------------------------------------------------------------- tiers (matrix order)
# color: cpu | gpu | full ; h = staircase height (0 = not on the staircase) ; exists: (pill class, EN, VI)
# status: applied = a job runs it today · planned = P8 target, no job yet (dashed on the staircase / glossary / matrix)
# p8=False: today-only tier, not a column of the P8 change-class matrix
TIERS = [
    dict(id="L0", status="applied", short="L0 lint", name="L0 lint", color="cpu", h=8, job="Check code quality",
         hw=("CPU", "CPU"), cost=("< 1 min", "< 1 phút"),
         plain=("Read the code without running it", "Đọc code mà không chạy"),
         catches=("style, typos, wrong types, banned patterns (e.g. raw torch.device)", "style, lỗi chính tả, sai kiểu, mẫu bị cấm (ví dụ torch.device thô)"),
         example="pre-commit: ruff, mypy, codespell, SPDX header", exists=("yes", "yes · required", "có · bắt buộc")),
    dict(id="L1", status="applied", short="L1 CPU", name="L1 unit · CPU", color="cpu", h=14, job="GHA Test (advisory)", after="L0",   # #6730: runs only after Check code quality
         hw=("GHA, advisory, after L0", "GHA, tham khảo, sau L0"), cost=("≈19 min × 4 py (drafts: 3.12 only)", "≈19 phút × 4 py (PR nháp: chỉ 3.12)"),
         plain=("One function or class alone, fake inputs", "Một hàm hoặc class riêng lẻ, input giả"),
         catches=("logic bugs in one module: hashing, lookup, locks, config; vLLM connector contracts (only here)", "bug logic trong một module: hashing, lookup, lock, config; contract của vLLM connector (chỉ ở đây)"),
         example="test_hash_tokens_with_prefix · tests/v1/multiprocess/test_token_hasher.py", exists=("part", "yes · not required", "có · không chặn merge")),
    dict(id="L1G", status="applied", short="L1 GPU unit", name="L1 unit · GPU pod", color="gpu", h=34, job="k3-unit-tests",
         hw=("1 GPU, required", "1 GPU, bắt buộc"), cost=("25 min queue + 24 min", "chờ 25 phút + 24 phút"),
         plain=("Same unit suite + cuda-marked tests, on 1 GPU", "Cùng bộ unit test + test cuda, trên 1 GPU"),
         catches=("GPU kernels, storage suites that need a device today", "GPU kernel, bộ test lưu trữ hiện cần thiết bị"),
         example="test_store_and_lookup · tests/v1/multiprocess/test_cache_server.py (cuda)", exists=("yes", "yes · required", "có · bắt buộc")),
    dict(id="L2", status="planned", short="L2 server", name="L2 server scenarios", color="cpu", h=20, job="",
         hw=("CPU", "CPU"), cost=("~25 s / scenario", "~25 s / scenario"),
         plain=("Start the real LMCache server alone (no vLLM/SGLang); fake clients send store / lookup / retrieve", "Chạy LMCache server thật một mình (không vLLM/SGLang); client giả gửi store / lookup / retrieve"),
         catches=("bugs between server modules: restart, metrics, L2 flow, HTTP API, concurrency", "bug giữa các module của server: restart, metric, luồng L2, HTTP API, đồng thời"),
         example="lmcache bench server --scenario restart_reregister", exists=("part", "partly: bench exists, scenarios proposed", "một phần: đã có bench, scenario mới đề xuất")),
    dict(id="CE", status="applied", short="CPU E2E", name="CPU E2E", color="cpu", h=26, job="cpu_e2e_validation (in k3-multiprocess-smoke)",
         hw=("CPU, 8 cores", "CPU, 8 nhân"), cost=("3.6 min p50", "3.6 phút p50"),
         plain=("Real vLLM (CPU build) + LMCache + a tiny model, real requests end to end", "vLLM thật (bản CPU) + LMCache + model rất nhỏ, request thật từ đầu tới cuối"),
         catches=("connector wiring, store → hit → restart flow, identical output", "nối connector, luồng store → hit → restart, output giống hệt"),
         example="cpu_e2e_validation (Buildkite MP smoke, 3 modes) · same script in GHA cpu_device.yml",
         exists=("yes", "yes · in MP smoke on every ready PR, not required yet", "có · trong MP smoke trên mọi PR ready, chưa bắt buộc")),
    dict(id="MS", status="applied", p8=False, short="MP smoke", name="MP smoke", color="gpu", h=40, job="k3-multiprocess-smoke",   # #6731: every ready PR, advisory
         hw=("0–1 GPU per job", "0–1 GPU mỗi job"), cost=("~10–30 min", "~10–30 phút"),
         plain=("One fixed set of 1-GPU MP workloads + CPU E2E on every ready PR, whatever it touches", "Một bộ cố định workload MP 1 GPU + CPU E2E trên mọi PR ready, bất kể PR đụng gì"),
         catches=("connector / server regressions on a real engine while the heavy suite is bypassed", "lỗi connector / server trên engine thật khi bộ nặng được bỏ qua"),
         example="lm_eval · client_wheel · restart_recovery · cache_stats · lazy_offload · http_api",
         exists=("yes", "yes · every ready PR (#6731), not required yet", "có · mọi PR ready (#6731), chưa bắt buộc")),
    dict(id="L3", status="planned", short="L3 smoke", name="L3 engine smoke", color="gpu", h=44, job="",
         hw=("1 GPU", "1 GPU"), cost=("~10 min, ~21 GPU-min", "~10 phút, ~21 GPU-phút"),
         plain=("Real engine on 1 GPU, short accuracy check, only for the engine the PR touches", "Engine thật trên 1 GPU, check độ chính xác ngắn, chỉ cho engine mà PR đụng tới"),
         catches=("GPU transfer corrupting KV silently, engine API changes", "truyền GPU làm hỏng KV âm thầm, engine đổi API"),
         example="lm_eval: gsm8k twice → same answers",
         exists=("part", "planned: path-targeted per engine (today MP smoke runs one fixed set)", "kế hoạch: chọn theo engine PR đụng tới (hôm nay MP smoke chạy một bộ cố định)")),
    dict(id="LS", status="planned", short="Layout smoke", name="Layout smoke", color="gpu", h=52, job="",
         hw=("1–2 GPU", "1–2 GPU"), cost=("est. few min", "ước tính vài phút"),
         plain=("One small or dummy-weight model per KV layout type (MLA, fp8, hybrid, SWA)", "Một model nhỏ hoặc trọng số dummy cho mỗi loại KV layout (MLA, fp8, hybrid, SWA)"),
         catches=("KV shape / layout bugs without loading 160 GB models", "bug shape / layout KV mà không phải load model 160 GB"),
         example="DSV4 dummy 4 layers + hma_bit_correctness.py", exists=("no", "XPU only, not CUDA (CPU MLA dummy in GHA cpu_device, advisory)", "chỉ XPU, chưa có CUDA (MLA dummy trên CPU trong GHA cpu_device, tham khảo)")),
    dict(id="AO", status="planned", short="Add-ons", name="Path add-ons", color="gpu", h=60, job="",
         hw=("1–2 GPU", "1–2 GPU"), cost=("7–20 GPU-min each", "7–20 GPU-phút mỗi cái"),
         plain=("One extra GPU test that runs only when its code area changes", "Một test GPU thêm, chỉ chạy khi vùng code của nó thay đổi"),
         catches=("restart, P2P, GDS, preemption bugs (only these tests catch them)", "bug restart, P2P, GDS, preemption (chỉ các test này bắt được)"),
         example="edit heartbeat.py → add restart_recovery", exists=("part", "tests exist, not path-triggered", "test đã có, chưa chạy theo path")),
    dict(id="FULL", status="applied", short="Full", name="Full · weekly (#6854)", color="full", h=100, job="weekly full build (ci-weekly-full, advisory)",
         hw=("1–4 GPU", "1–4 GPU"), cost=("~535 GPU-min", "~535 GPU-phút"),
         plain=("Everything: big models, multi-GPU, perf vs baseline", "Mọi thứ: model lớn, nhiều GPU, hiệu năng so với baseline"),
         catches=("TP=4 fp8, perf regressions, engine × transport matrix", "TP=4 fp8, tụt hiệu năng, ma trận engine × transport"),
         example="dsv4_flash_tp TP=4, long_doc_qa TTFT", exists=("yes", "weekly on the ci-weekly-full branch (#6854); on a PR only with the label full, force-ci or mp. Advisory, not the required k3-multiprocess-test",
                                                                 "hằng tuần trên nhánh ci-weekly-full (#6854); trên PR chỉ khi có nhãn full, force-ci hoặc mp. Tham khảo, không phải k3-multiprocess-test bắt buộc")),
]

# ---------------------------------------------------------------- change classes (P8) — 1 required, 2 only on matching sub-path
CLASSES = [
    dict(id="docs", paths="markdown, docs/", prs="60", gpumin="0", tiers={"L0": 1}),
    dict(id="tests_only", paths="tests/**, tools/**, examples/**.py", prs="67", gpumin="0", tiers={"L0": 1, "L1": 1, "L1G": 1}),
    dict(id="other_platform", paths="XPU / ROCm / MUSA … code", prs="19", gpumin="0", tiers={"L0": 1, "L1": 1, "L1G": 1}),
    dict(id="core", paths="lmcache/v1/**, storage, CLI", prs="44", gpumin="0 (+7–20 add-on)", tiers={"L0": 1, "L1": 1, "L1G": 1, "L2": 1, "CE": 1, "AO": 2}),
    dict(id="adapter (vLLM)", paths="integration/vllm/**, transfer_context", prs="11", gpumin="20.6 – 80.2", tiers={"L0": 1, "L1": 1, "L1G": 1, "L2": 1, "CE": 1, "L3": 1, "AO": 2}),
    dict(id="adapter (SGLang)", paths="integration/sglang/** · no CPU E2E (vLLM-CPU only)", prs="↑", gpumin="20.6", tiers={"L0": 1, "L1": 1, "L1G": 1, "L2": 1, "L3": 1, "AO": 2}),
    dict(id="kernel", paths="csrc/cuda/**, gpu_connector", prs="6", gpumin="78.6", tiers={"L0": 1, "L1": 1, "L1G": 1, "L3": 1, "LS": 1}),
    dict(id="kv_layout", paths="MLA / fp8 / hybrid / HMA code", prs="14", gpumin="78.6", tiers={"L0": 1, "L1": 1, "L1G": 1, "L2": 1, "CE": 1, "L3": 1, "LS": 1, "FULL": 2}),
    dict(id="deps_ci", paths="requirements, pyproject, MP harness", prs="31", gpumin="~535", tiers={t: 1 for t in ["L0", "L1", "L1G", "L2", "CE", "L3", "LS", "AO", "FULL"]}),
]

# which MP workloads each tier runs (for the impact lookup)
TIER_WORKLOADS = {
    "CE": ["cpu_e2e_validation"], "MS": ["lm_eval", "client_wheel", "restart_recovery", "cache_stats", "lazy_offload", "http_api", "cpu_e2e_validation"], "L3": ["lm_eval", "client_wheel", "restart_recovery", "cache_stats", "lazy_offload"], "LS": ["dsv4_flash_tp (dummy)", "kimi_linear_tp (dummy)"],
    "AO": ["restart_recovery", "p2p", "gds_smoke", "lm_eval_preemption"], "FULL": ["all MP workloads"],
}

# feature area (unit-test view) -> change class (P8 path classes). Cross-link unit tests ↔ tiers ↔ workloads.
AREA_CLASS = {
    "vllm": "adapter (vLLM)", "engines": "adapter (SGLang)", "lazy": "adapter (vLLM)", "datapath": "adapter (vLLM)",
    "layout": "kv_layout", "platform": "other_platform", "gds": "kernel", "build": "deps_ci",
}  # every other area -> core

# ---------------------------------------------------------------- E2E workloads (P1 cost + P2 checks)
def _p1_cost():
    """Round 2 G4: workload GPU-min are read at build time from P1/cost_by_workload.csv (no hard-coded
    snapshot), with the P1 window and the MP PR total that the CI cost home shows (build_level_summary.json).
    The P8 'Today' figure of the GPU cost tab is parsed from P8/shadow_report.md so it can be labelled."""
    import csv
    import datetime as _dt
    import json
    import os
    import re as _re
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    gm = {r["workload"]: float(r["gpu_min_total_30d"] or 0) for r in csv.DictReader(open(os.path.join(out, "P1", "cost_by_workload.csv"), encoding="utf-8"))}
    w = json.load(open(os.path.join(out, "P1", "window.json"), encoding="utf-8"))
    since = w["since"][:10]
    last = str(_dt.date.fromisoformat(w["until"][:10]) - _dt.timedelta(days=1))  # until is exclusive
    tot = json.load(open(os.path.join(out, "P1", "build_level_summary.json"), encoding="utf-8"))["gpu_min_total_pr"]
    p8 = {}
    try:
        md = open(os.path.join(out, "P8", "shadow_report.md"), encoding="utf-8").read()
        # the report has a 100-PR sample table and the all-PR table: take the Total row with the most PRs
        rows = _re.findall(r"\| \*\*Total\*\* \| \*\*(\d+)\*\* \| \*\*[\d,]+\*\* \| \*\*([\d,]+)\*\* \|", md)
        d = _re.search(r"^Date: (\d{4}-\d\d-\d\d)", md, _re.M)
        if rows:
            prs, g = max(rows, key=lambda r: int(r[0]))
            p8 = dict(prs=int(prs), gpu_min=int(g.replace(",", "")), date=d.group(1) if d else "?")
    except OSError:
        pass
    return gm, since, last, tot, p8


P1_WL_GPUMIN, P1_SINCE, P1_LAST, P1_PR_GPU_MIN, P8_TODAY = _p1_cost()

# group: cpu (→ CPU / no engine) | gpu (→ smaller GPU job on PR) | cond (→ path match / label / nightly)
# only: what ONLY this workload catches (P2 §d2) ; covered: what cheaper layers already cover
WORKLOADS = [
    dict(name="preemption_correctness", gpus="2", group="gpu", home="same-engine replay on PR (1 GPU); full plain-vLLM run nightly",
         checks=("Under heavy preemption, LMCache answers == plain vLLM answers by request id; ≥ 1 request reloaded KV after preemption", "Khi preemption dồn dập, câu trả lời LMCache == vLLM thuần theo request id; ≥ 1 request nạp lại KV sau preemption"),
         only=("resume after preemption", "tiếp tục sau preemption"), covered=("", "")),
    dict(name="dsv4_flash_tp", gpus="4", group="gpu", home="layout smoke (dummy 4 layers, 1 GPU); TP=4 nightly / label",
         checks=("DeepSeek-V4 TP=4 fp8 MLA: cold output == LMCache-served output (byte-identical), retrieves > 0", "DeepSeek-V4 TP=4 fp8 MLA: output lạnh == output do LMCache phục vụ (giống từng byte), có retrieve > 0"),
         only=("real-model MLA / fp8 layout under TP", "layout MLA / fp8 của model thật khi chạy TP"), covered=("", "")),
    dict(name="long_doc_qa", gpus="2", group="gpu", home="1 GPU + stored baseline",
         checks=("TTFT vs baseline engine (vLLM ≥ 60% faster, SGLang ≤ 0% slower), round time", "TTFT so với engine baseline (vLLM nhanh hơn ≥ 60%, SGLang chậm hơn ≤ 0%), thời gian mỗi lượt"),
         only=("TTFT performance regressions", "tụt hiệu năng TTFT"), covered=("", "")),
    dict(name="lm_eval", gpus="1", group="gpu", home="L3 smoke for adapter / kernel / layout PRs",
         checks=("vLLM: two greedy gsm8k runs give identical samples; SGLang: score drift ≤ 0.01, ≥ 0.80, L1 reads grew", "vLLM: 2 lần gsm8k greedy cho mẫu giống hệt; SGLang: điểm lệch ≤ 0.01, ≥ 0.80, số đọc L1 tăng"),
         only=("silent KV corruption on a real model (GPU paths)", "hỏng KV âm thầm trên model thật (đường GPU)"), covered=("", "")),
    dict(name="long_doc_qa_l2", gpus="2", group="gpu", home="perf: stored baseline · data flow → L2 scenario",
         checks=("Relaunch with mock L2: round ≥ 1.3×, TTFT ≥ 1.5× faster; L2 store / prefetch counters > 0 with labels", "Chạy lại với L2 giả: lượt nhanh ≥ 1.3×, TTFT ≥ 1.5×; counter store / prefetch L2 > 0 kèm label"),
         only=("L2 performance", "hiệu năng L2"), covered=("data-flow half → L2 server scenario", "nửa luồng dữ liệu → L2 server scenario")),
    dict(name="vllm_bench", gpus="2", group="gpu", home="stored baseline keyed per GPU UUID",
         checks=("LMCache throughput ≥ baseline − 5%; warm cached tokens > cold", "Throughput LMCache ≥ baseline − 5%; token cache khi ấm > khi lạnh"),
         only=("throughput regressions", "tụt throughput"), covered=("", "")),
    dict(name="kimi_linear_tp", gpus="2", group="gpu", home="layout smoke, dummy 4 layers, keeps TP=2",
         checks=("Kimi-Linear TP=2 (hybrid MLA + linear attention): L1 round trip byte-identical", "Kimi-Linear TP=2 (hybrid MLA + linear attention): ghi-đọc L1 giống từng byte"),
         only=("hybrid layout under TP", "layout hybrid khi chạy TP"), covered=("", "")),
    dict(name="lm_eval_preemption", gpus="1", group="cond", home="add-on when lmcache_mp_connector.py changes",
         checks=("gsm8k with forced preemption: score drift ≤ 0.05, both ≥ 0.80, preempted count grew", "gsm8k có preemption ép buộc: điểm lệch ≤ 0.05, cả hai ≥ 0.80, số preempted tăng"),
         only=("accuracy under preemption", "độ chính xác khi có preemption"), covered=("", "")),
    dict(name="deadlock", gpus="2", group="cpu", home="L2 server scenario (concurrency storm)",
         checks=("50 requests × 30K tokens finish in ≤ 180 s", "50 request × 30K token xong trong ≤ 180 s"),
         only=("", ""), covered=("concurrency_storm L2 scenario (proposed)", "L2 scenario concurrency_storm (đề xuất)")),
    dict(name="restart_recovery", gpus="1", group="cond", home="add-on for lifecycle paths; server side → L2",
         checks=("Kill + relaunch: /healthcheck ok, worker re-registered, round 2 writes ≥ 80% of round 1", "Kill + chạy lại: /healthcheck ok, worker đăng ký lại, lượt 2 ghi ≥ 80% lượt 1"),
         only=("re-register after restart (#4018 failed only here)", "đăng ký lại sau restart (#4018 chỉ fail ở đây)"), covered=("server side → restart_reregister L2 scenario", "phía server → L2 scenario restart_reregister")),
    dict(name="http_api", gpus="1", group="cpu", home="L2 server scenario (bench warms cache)",
         checks=("~30 HTTP endpoints: status codes + JSON keys; lmcache describe / kvcache clear exit 0", "~30 endpoint HTTP: status code + key JSON; lmcache describe / kvcache clear thoát mã 0"),
         only=("", ""), covered=("engine only warms the cache → L2 scenario", "engine chỉ để làm nóng cache → L2 scenario")),
    dict(name="p2p", gpus="2", group="cond", home="add-on when p2p / transfer_channel paths change",
         checks=("LMCache A sees a peer; engine B gets cached tokens for a prompt only A saw", "LMCache A thấy peer; engine B nhận token đã cache cho prompt chỉ A từng thấy"),
         only=("GPU-to-GPU peer transfer", "truyền ngang hàng GPU-GPU"), covered=("", "")),
    dict(name="fault_tolerance", gpus="1", group="cond", home="nightly (no catch in 6 months)",
         checks=("Kill LMCache mid-run: bench still 50/50; without LMCache 50/50", "Kill LMCache giữa chừng: bench vẫn 50/50; không có LMCache 50/50"),
         only=("", ""), covered=("mostly covered by cheaper layers", "phần lớn đã có tầng rẻ hơn bao phủ")),
    dict(name="mp_autostart_tp2", gpus="2", group="cond", home="nightly / label",
         checks=("vLLM TP=2 auto-starts the LMCache server; ZMQ ping healthy", "vLLM TP=2 tự khởi động LMCache server; ZMQ ping khoẻ"),
         only=("", ""), covered=("unit tests of MP server auto-start", "unit test auto-start của MP server")),
    dict(name="gds_smoke", gpus="1", group="cond", home="add-on when gds paths change",
         checks=("GDS L1 slab: warm text == cold text, Retrieved count grew", "GDS L1 slab: text ấm == text lạnh, số Retrieved tăng"),
         only=("cuFile (GPU Direct Storage) path", "đường cuFile (GPU Direct Storage)"), covered=("", "")),
    dict(name="lazy_offload", gpus="1", group="cpu", home="L2 server scenario",
         checks=("FIFO lazy offload log; L1 writes happen only when blocks are about to be reused", "Log lazy offload FIFO; ghi L1 chỉ xảy ra khi block sắp bị tái sử dụng"),
         only=("", ""), covered=("lazy offload unit tests (feature 1.3)", "unit test lazy offload (feature 1.3)")),
    dict(name="cache_stats", gpus="1", group="cpu", home="L1 connector unit test (test body ~2 s)",
         checks=("cached_token_stats has 3 keys; warm > cold — test body ~2 s after a ~260 s engine start", "cached_token_stats có 3 key; ấm > lạnh — thân test ~2 s sau ~260 s khởi động engine"),
         only=("", ""), covered=("connector unit test", "unit test connector")),
    dict(name="cpu_e2e_validation", gpus="0", group="cpu", home="stays: CPU E2E tier (required)",
         checks=("vLLM-CPU + opt-125m: store → hit → reset → restart, 5 identical outputs, no false hit", "vLLM-CPU + opt-125m: store → hit → reset → restart, 5 output giống hệt, không hit nhầm"),
         only=("real connector wiring on every PR, cheaply (caught PR #5383)", "nối connector thật cho mọi PR, giá rẻ (đã bắt PR #5383)"), covered=("", "")),
]
for _w in WORKLOADS:
    _w["gpumin"] = round(P1_WL_GPUMIN.get(_w["name"].split(" ")[0], 0))
WORKLOADS.sort(key=lambda w: -w["gpumin"])
_WL_SHOWN = sum(w["gpumin"] for w in WORKLOADS)
_WL_ALL = round(sum(P1_WL_GPUMIN.values()))
_WL_OTHER = sorted(k for k in P1_WL_GPUMIN if k not in {w["name"] for w in WORKLOADS})
# shown on the E2E tabs next to the workload values (gatesData.wl_cost)
WL_COST = dict(since=P1_SINCE, last=P1_LAST, shown=_WL_SHOWN, n_shown=len(WORKLOADS), all=_WL_ALL, n_all=len(P1_WL_GPUMIN),
               other=_WL_OTHER, pr_total=round(P1_PR_GPU_MIN), pr_total_h=round(P1_PR_GPU_MIN / 60, 1), p8=P8_TODAY)
_WIN = f"{P1_SINCE} → {P1_LAST}"
_RECON_EN = (f"P1 cost_by_workload.csv, {_WIN} (UTC): the {len(WORKLOADS)} workloads shown = {_WL_SHOWN:,} GPU-min; all {len(P1_WL_GPUMIN)} workloads = {_WL_ALL:,}; "
             f"MP PR total = {round(P1_PR_GPU_MIN):,} GPU-min = {P1_PR_GPU_MIN / 60:,.1f} GPU-h (CI cost home, row 'PR GPU time, MP pipeline only'; the gap is jobs not attributed to a workload)")
_RECON_VI = (f"P1 cost_by_workload.csv, {_WIN} (UTC): {len(WORKLOADS)} workload hiển thị = {_WL_SHOWN:,} GPU-phút; cả {len(P1_WL_GPUMIN)} workload = {_WL_ALL:,}; "
             f"tổng PR của MP = {round(P1_PR_GPU_MIN):,} GPU-phút = {P1_PR_GPU_MIN / 60:,.1f} GPU-giờ (bảng chi phí CI, dòng 'Thời gian GPU của PR, chỉ pipeline MP'; phần chênh là job không gán được workload)")
_P8_EN = (f"Today = P8 shadow snapshot made {P8_TODAY.get('date', '?')} on {P8_TODAY.get('prs', '?')} PRs, {_WIN}: {P8_TODAY.get('gpu_min', 0):,} GPU-min. "
          f"The current P1 export gives {round(P1_PR_GPU_MIN):,} GPU-min for the same window (CI cost home). P5 baseline study")
_P8_VI = (f"Hôm nay = bản chụp mô phỏng P8 lập ngày {P8_TODAY.get('date', '?')} trên {P8_TODAY.get('prs', '?')} PR, {_WIN}: {P8_TODAY.get('gpu_min', 0):,} GPU-phút. "
          f"Bản xuất P1 hiện tại cho {round(P1_PR_GPU_MIN):,} GPU-phút cùng khung (bảng chi phí CI). Nghiên cứu baseline P5")

# ---------------------------------------------------------------- section descriptions (Help text)
# view -> {number: (key takeaway EN, key takeaway VI, data source EN, data source VI)}
# Convention: the section's <p class="sub"> says in one short line WHAT the table / chart is; DESC never repeats it and
# only adds what to do with it (key takeaway) and where the numbers come from.
# Two dates on purpose: unit-test numbers are a snapshot of commit 05d8eb84 (2026-11-06); workflow / gate config is dev on 2026-11-27.
_SNAP_EN, _SNAP_VI = "unit-test snapshot of commit 05d8eb84 (2026-11-06)", "ảnh chụp unit test ở commit 05d8eb84 (2026-11-06)"
_CFG_EN, _CFG_VI = "workflow config of dev on 2026-11-27", "cấu hình workflow của dev ngày 2026-11-27"
DESC = {
    "gates": {
        1: ("Merge needs DCO, code quality, k3-unit-tests and k3-multiprocess-test. GHA Test blocks only the release, yet it is the only place the 327 vLLM-connector tests run.",
            "Merge cần DCO, code quality, k3-unit-tests và k3-multiprocess-test. GHA Test chỉ chặn release, nhưng là nơi duy nhất chạy 327 test vLLM connector.",
            f"Branch protection of dev (2026-11-06) + {_CFG_EN}", f"Branch protection của dev (2026-11-06) + {_CFG_VI}"),
        2: ("A PR climbs only as high as its change class needs and stops at the first failing step. Today every ready code PR runs the solid steps; the dashed ones do not exist yet.",
            "PR chỉ leo tới mức loại thay đổi của nó cần và dừng ở bậc fail đầu tiên. Hôm nay mọi PR code ready chạy các bậc nét liền; bậc nét đứt chưa có.",
            "P1 (p50 wall, 30 d to 2026-11-04), P4, P6, P8", "P1 (p50 thực, 30 ngày tới 2026-11-04), P4, P6, P8"),
        3: ("Rule: a test lives in the lowest tier that can still catch its bug.",
            "Luật: test đặt ở tầng thấp nhất mà vẫn bắt được bug của nó.",
            "gates.py (single source)", "gates.py (nguồn duy nhất)"),
        4: ("A PR touching several classes takes the union. Until P8 ships, every ready code PR runs the same required checks plus MP smoke, whatever its class.",
            "PR đụng nhiều loại thì lấy hợp các tầng. Tới khi P8 được áp dụng, mọi PR code ready chạy cùng các check bắt buộc cộng MP smoke, bất kể loại thay đổi.",
            "P8 shadow rule on the last 100 merged PRs", "Luật mô phỏng P8 trên 100 PR merge gần nhất"),
        5: ("Change here → run exactly this: test impact analysis on the P8 target tiers.",
            "Đổi ở đây → chạy đúng những thứ này: test impact analysis trên các tầng mục tiêu P8.",
            "gates.py AREA_CLASS + CLASSES + TIER_WORKLOADS; unit counts from GHA run 42189301949", "gates.py AREA_CLASS + CLASSES + TIER_WORKLOADS; số unit test từ GHA run 42189301949"),
    },
    "cpu": {
        1: ("9,326 tests on GHA CPU vs 10,258 on the required GPU unit pod, 540 files in 28 areas. The CPU job is done ≈30 min before the GPU pod starts.",
            "9,326 test trên GHA CPU so với 10,258 trên GPU unit pod bắt buộc, 540 file trong 28 nhóm. Job CPU xong ≈30 phút trước khi GPU pod bắt đầu.",
            f"GHA run 42189301949 + k3-unit-tests #14829, {_SNAP_EN}; Python versions and legs: {_CFG_EN}",
            f"GHA run 42189301949 + k3-unit-tests #14829, {_SNAP_VI}; số phiên bản Python và leg: {_CFG_VI}"),
        2: ("8,994 tests run on both (87.7% of k3), so the CPU job can fail fast for the GPU pod.",
            "8,994 test chạy ở cả hai (87.7% của k3), nên job CPU có thể fail sớm thay cho GPU pod.",
            f"k3_overlap.py: k3 #14829 log vs GHA job 127850987819, {_SNAP_EN}", f"k3_overlap.py: log k3 #14829 so với GHA job 127850987819, {_SNAP_VI}"),
        3: ("Click a row for what · why · setup · code · files, and the tiers / workloads a change there needs.",
            "Click một dòng: gì · vì sao · setup · code · file, và đổi ở đó cần qua tầng / workload nào.",
            f"pytest log, GHA job 127850987819, {_SNAP_EN}", f"log pytest, GHA job 127850987819, {_SNAP_VI}"),
        4: ("Subprocess and socket columns are where port collisions and timing flakes come from.",
            "Cột subprocess và socket là nơi sinh lỗi trùng port và test flake do timeout.",
            "regex scan of test sources at 05d8eb84", "quét regex source test ở 05d8eb84"),
        5: ("13 files (≈9.7k lines, mostly storage logic) are CPU-portable: excluded only by a device guard.",
            "13 file (≈9.7k dòng, chủ yếu logic lưu trữ) chạy được trên CPU: chỉ bị loại vì guard thiết bị.",
            "test sources at 05d8eb84", "source test ở 05d8eb84"),
        6: ("If the CPU job fails, cancel the queued GPU unit build: it would start only at minute 25.",
            "Job CPU fail thì huỷ build GPU unit đang chờ: nó chỉ bắt đầu ở phút 25.",
            f"GHA job step timings + Buildkite job timestamps, {_SNAP_EN}", f"thời gian từng bước GHA + mốc thời gian job Buildkite, {_SNAP_VI}"),
        7: ("First: gate the 327 vLLM tests. Quick wins: 70 s hardcoded sleep, Hugging Face call, --maxfail.",
            "Trước hết: gate 327 test vLLM. Làm nhanh: hardcoded sleep 70 s, lệnh gọi Hugging Face, --maxfail.",
            "REVIEW_ponytail.md + own measurements", "REVIEW_ponytail.md + đo thực tế"),
        8: ("Search names and docstrings, filter by feature area, sort by slowest. ★ = hand-written explanation of a gate-critical test.",
            "Tìm theo tên và docstring, lọc theo nhóm feature, sắp xếp chậm nhất. ★ = giải thích viết tay cho test quyết định merge.",
            "pytest log + docstrings + lmcache_glossary.py + curated_tests.py", "log pytest + docstring + lmcache_glossary.py + curated_tests.py"),
    },
    "gpu": {
        1: ("The bottom line of each lane is where today's path loses time or GPU.",
            "Dòng cuối mỗi cột là nơi đường hiện tại mất thời gian hoặc GPU.",
            "P1, P2, P7, P8", "P1, P2, P7, P8"),
        2: ("About 61% is setup + engine start; only ~39% actually tests LMCache.",
            "Khoảng 61% là setup + khởi động engine; chỉ ~39% thật sự test LMCache.",
            "P1: 288 sampled logs, 30 d to 2026-11-04", "P1: 288 log mẫu, 30 ngày tới 2026-11-04"),
        3: ("Workloads that are the only catcher stay (smaller); the rest move to L2 / unit / nightly.",
            "Workload là nơi duy nhất bắt lỗi thì giữ (thu nhỏ); còn lại chuyển sang L2 / unit / nightly.",
            f"P2 coverage_map.md (checks + catches), P1 cost {_WIN}", f"P2 coverage_map.md (check + lần bắt lỗi), chi phí P1 {_WIN}"),
        4: ("Buildkite runs it in MP smoke on every ready PR; GHA cpu_device.yml runs the same script on more platforms. Neither is required yet.",
            "Buildkite chạy nó trong MP smoke trên mọi PR ready; GHA cpu_device.yml chạy cùng script trên nhiều nền tảng hơn. Chưa cái nào bắt buộc.",
            f".github/scripts/run-cpu-e2e-validation.sh; P1 (1,034 runs / 30 d); {_CFG_EN}", f".github/scripts/run-cpu-e2e-validation.sh; P1 (1,034 lần chạy / 30 ngày); {_CFG_VI}"),
        5: ("Colour = destination (CPU, smaller GPU job, or only on path / label / nightly).",
            "Màu = nơi chuyển tới (CPU, job GPU nhỏ hơn, hoặc chỉ khi path / label / nightly).",
            _RECON_EN + "; homes from P2, P4–P6, P8", _RECON_VI + "; nơi chuyển từ P2, P4–P6, P8"),
        6: ("−80% is an estimate: it needs the L2 scenarios built and was checked against 1 real catch.",
            "−80% là ước tính: cần xây xong L2 scenario và mới đối chiếu với 1 lần bắt bug thật.",
            _P8_EN, _P8_VI),
        7: ("Bugs in acceptance checks and a hidden TTFT regression come first; hover for the source.",
            "Bug trong check tiêu chí pass và một lần tụt TTFT bị che đi cần xử lý trước; rê chuột xem nguồn.",
            "P1, P2, P4–P8", "P1, P2, P4–P8"),
        8: ("Search a test, check or function to open the path to it.",
            "Tìm một test, check hoặc hàm để mở đường dẫn tới nó.",
            "P2 workload assertions, P4, P6; code at fcd50cea", "assert của workload P2, P4, P6; code ở fcd50cea"),
    },
}
