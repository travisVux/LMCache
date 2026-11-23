"""Daily ingredients for the Executive CI & Release Report (#obs/trend).
The page aggregates them dynamically by Daily / Weekly / Monthly periods.

Input : report_data.json (report_collect.py), observe_history/baseline_mp.json (P1 MP GPU cost),
        ../P1/jobs_all_30d.csv (per-workload daily failures), ff_cache_*.json (GHA Test & Quality runs).
Output: dict embedded in the page (via observe_history.load_all()["report"]).

Per day we keep counts and raw value lists so medians / p90 per day, week, or month are exact.
"""
import collections
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from areas import area_of  # noqa: E402
import trace_agent_common  # noqa: E402

DATA = os.path.join(HERE, "report_data.json")
MP = os.path.join(HERE, "observe_history", "baseline_mp.json")
P1_JOBS = os.path.join(HERE, "..", "P1", "jobs_all_30d.csv")
GHA_TEST = os.path.join(HERE, "ff_cache_gha_test.json")
GHA_QUAL = os.path.join(HERE, "ff_cache_quality.json")
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "third_party", "LMCache"))


def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def day(s):
    return s[:10] if s else None


def build_failed_order(days_set, R):
    """Build ranked list of failing test cases, MP workloads, and CI gates with daily breakdown."""
    wf_fails = collections.defaultdict(int)
    wf_runs = collections.defaultdict(int)
    wf_gpu = collections.defaultdict(float)
    wf_by_day = collections.defaultdict(lambda: collections.defaultdict(int))

    if os.path.exists(P1_JOBS):
        for j in csv.DictReader(open(P1_JOBS, encoding="utf-8")):
            if j.get("is_pr") != "1":
                continue
            d = day(j.get("build_created"))
            wl = j.get("workload") or j.get("label") or "unknown"
            eng = j.get("engine") or "all"
            key = f"{wl}|{eng}"
            wf_runs[key] += 1
            if j.get("state") == "failed" or j.get("retried") == "True":
                wf_fails[key] += 1
                wf_gpu[key] += float(j.get("gpu_min") or 0) / 60.0
                if d:
                    wf_by_day[key][d] += 1

    # Also track daily failures for GHA Test (CPU unit tests), Code Quality, k3-unit-tests, publish.yml
    gha_t_by_day = collections.defaultdict(int)
    gha_t_runs = 0
    if os.path.exists(GHA_TEST):
        for r in json.load(open(GHA_TEST, encoding="utf-8")):
            if r.get("conclusion") in ("success", "failure"):
                gha_t_runs += 1
                if r.get("conclusion") == "failure":
                    d = day(r.get("created_at"))
                    if d:
                        gha_t_by_day[d] += 1

    # Metadata for top failing test cases & workloads (empirical P1 + P2 + CPU log audit)
    META = [
        dict(
            id="long_doc_qa_l2|vllm",
            name="long_doc_qa_l2 (vLLM · 2 GPU)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "TTFT speedup threshold miss (1.33× vs required ≥ 1.5×) on mock L2 + PyTorch pip 503 setup errors",
                "Trượt ngưỡng tăng tốc TTFT (1.33× so với yêu cầu ≥ 1.5×) trên mock L2 + lỗi mạng pip 503 khi setup",
            ],
            fix=[
                "Split L2 data-flow assertions to CPU-E2E; use stored GPU baseline for TTFT",
                "Tách kiểm tra luồng dữ liệu L2 sang CPU-E2E; dùng stored baseline cho TTFT",
            ],
        ),
        dict(
            id="long_doc_qa|vllm",
            name="long_doc_qa (vLLM · 2 GPU)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "Query TTFT speedup flake (56.9% vs required ≥ 60% faster than baseline engine on shared GPU node)",
                "Biến động hiệu năng TTFT (56.9% so với ngưỡng ≥ 60% nhanh hơn baseline trên node GPU dùng chung)",
            ],
            fix=[
                "Replace dual-engine live baseline with per-GPU-UUID stored baseline (saves 1 GPU)",
                "Thay engine baseline chạy song song bằng stored baseline theo GPU UUID (giảm 1 GPU)",
            ],
        ),
        dict(
            id="vllm_bench|vllm",
            name="vllm_bench (vLLM · 2 GPU)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "Throughput slowdown > 5% vs live baseline under node contention (node 248 speed variance)",
                "Throughput tụt > 5% so với baseline trực tiếp khi nghẽn tài nguyên trên node 248",
            ],
            fix=[
                "Move throughput benchmark to nightly / stored baseline; keep cold/warm token check in smoke tier",
                "Chuyển bài đo throughput sang nightly / stored baseline; giữ check token ấm/lạnh ở tầng smoke",
            ],
        ),
        dict(
            id="dsv4_flash_tp|vllm",
            name="dsv4_flash_tp (vLLM · 4 GPU TP=4)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "DeepGEMM / SM120 sparse-MLA kernel compilation breakage against upstream vLLM & torch headers",
                "Lỗi biên dịch kernel DeepGEMM / SM120 sparse-MLA khi upstream vLLM hoặc header PyTorch thay đổi",
            ],
            fix=[
                "Use 1-GPU 4-layer dummy weight layout smoke on PRs; run full 4-GPU TP=4 on nightly / kv_layout path",
                "Chạy layout smoke 1-GPU (dummy 4 layer) trên PR; chỉ chạy full 4-GPU TP=4 ở nightly hoặc khi sửa kv_layout",
            ],
        ),
        dict(
            id="dsv4_flash_tp|sglang",
            name="dsv4_flash_tp (SGLang · 4 GPU TP=4)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "setup-env.sh dependency conflict (exit 2) + 4-GPU queue timeout waiting for 4 free GPUs",
                "Lỗi xung đột thư viện trong setup-env.sh (exit 2) + nghẽn hàng đợi chờ gom đủ 4 GPU",
            ],
            fix=[
                "Trigger only when integration/sglang/** or kv_layout paths change",
                "Chỉ kích hoạt khi PR sửa đường dẫn integration/sglang/** hoặc kv_layout",
            ],
        ),
        dict(
            id="kimi_linear_tp|sglang",
            name="kimi_linear_tp (SGLang · 2 GPU TP=2)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "Hybrid MLA + linear-attention Mamba slice_axis guard rejection & setup exit 2",
                "Lỗi guard Mamba slice_axis trên kiến trúc lai MLA + linear-attention và lỗi cài đặt exit 2",
            ],
            fix=[
                "Convert to dummy-weight TP=2 layout smoke triggered by adapter(sglang) / kv_layout",
                "Chuyển sang layout smoke trọng số giả TP=2, chỉ chạy khi sửa adapter(sglang) / kv_layout",
            ],
        ),
        dict(
            id="long_doc_qa|sglang",
            name="long_doc_qa (SGLang · 2 GPU)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "SGLang TTFT regression since Oct 27 masked by automatic retries (≤ 0% slower threshold)",
                "Tụt hiệu năng TTFT trên SGLang từ 27/10 bị che khuất bởi cơ chế tự động retry",
            ],
            fix=[
                "Fix SGLang adapter TTFT regression and move perf check to stored baseline",
                "Khắc phục lỗi tụt TTFT của SGLang adapter và chuyển kiểm tra hiệu năng sang stored baseline",
            ],
        ),
        dict(
            id="kimi_linear_tp|vllm",
            name="kimi_linear_tp (vLLM · 2 GPU TP=2)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "Autotune warmup timeout on 2×GPU hybrid MLA+Mamba initialization & git checkout exit 128",
                "Quá thời gian khởi tạo autotune trên mô hình lai MLA+Mamba 2 GPU và lỗi git checkout exit 128",
            ],
            fix=[
                "Use 4-layer dummy weights to skip 160 GB weight download & autotune warmup",
                "Dùng trọng số giả 4 layer để bỏ qua bước tải model lớn và rút ngắn khởi động",
            ],
        ),
        dict(
            id="cpu_e2e_validation|all",
            name="cpu_e2e_validation (vLLM-CPU · 3 modes)",
            suite="CPU E2E",
            cat="cpu_e2e",
            gate="merge",
            why=[
                "Caught real connector AttributeError (#5383) & vLLM CPU SHM storage_offset break (#4724), plus libnuma env misses",
                "Bắt được bug thật AttributeError ở connector (#5383) và lỗi SHM storage_offset (#4724), kèm thiếu libnuma trên node",
            ],
            fix=[
                "Keep as mandatory fast gate (0 GPU, 3.6m p50); bake libnuma.so.1 into base runner image",
                "Giữ làm cổng chặn nhanh bắt buộc (0 GPU, 3.6 phút p50); cài sẵn libnuma.so.1 vào base image",
            ],
        ),
        dict(
            id="ut_profiling",
            name="tests/cli/test_profiling.py (Pytest Unit)",
            suite="Unit Test (CPU/GPU)",
            cat="unit_test",
            gate="release",
            fails_override=20,
            runs_override=25,
            gpu_override=0.0,
            by_day_override={"2026-11-04": 4, "2026-11-05": 11, "2026-11-06": 5},
            why=[
                "Linux perf_event_paranoid kernel restriction on Azure GHA runners blocked profiler attach (20/25 sampled GHA failures)",
                "Chính sách kernel perf_event_paranoid trên Azure GHA chặn profiler (chiếm 20/25 lần fail GHA được lấy mẫu)",
            ],
            fix=[
                "Fixed on dev via PR #6350 (skip/fallback when perf counters are restricted by OS)",
                "Đã xử lý trên dev ở PR #6350 (tự động skip/fallback khi OS chặn quyền đọc perf counter)",
            ],
        ),
        dict(
            id="lm_eval|vllm",
            name="lm_eval gsm8k (vLLM · 1 GPU)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "Greedy sample output mismatch or HF dataset download 503 timeout during run 1 vs run 2",
                "Sai lệch kết quả sinh chuỗi greedy hoặc lỗi mạng 503 khi tải bộ dữ liệu gsm8k từ HuggingFace",
            ],
            fix=[
                "Keep as L3 1-GPU engine smoke for adapter/kernel PRs; pre-cache gsm8k dataset in CI image",
                "Giữ làm L3 smoke 1-GPU cho PR sửa adapter/kernel; đóng gói sẵn bộ dữ liệu gsm8k vào image CI",
            ],
        ),
        dict(
            id="fault_tolerance|vllm",
            name="fault_tolerance (vLLM · 1 GPU)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "ZMQError: Address already in use (tcp://localhost:6555) when relaunching server after kill",
                "Lỗi trùng cổng ZMQ (Address already in use tcp://localhost:6555) khi khởi động lại server sau lệnh kill",
            ],
            fix=[
                "Bind ephemeral free port in test harness; move scenario to CPU-E2E + nightly",
                "Cấp phát cổng động (ephemeral port) trong script test; chuyển kịch bản sang CPU-E2E + nightly",
            ],
        ),
        dict(
            id="lm_eval|sglang",
            name="lm_eval gsm8k (SGLang · 1 GPU)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "Score drift > 0.01 or radix-cache flush timing flake on SGLang L1 read counter",
                "Độ lệch điểm > 0.01 hoặc biến động bộ đếm đọc L1 sau lệnh xoá radix-cache trên SGLang",
            ],
            fix=[
                "Run only when SGLang adapter or transfer_context changes",
                "Chỉ chạy khi PR thay đổi SGLang adapter hoặc transfer_context",
            ],
        ),
        dict(
            id="restart_recovery|vllm",
            name="restart_recovery (vLLM · 1 GPU)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "Round-2 L1 writes < 80% of Round-1 after server kill/restart (caught real host-pinning bug in PR #4018)",
                "Lượng ghi L1 lượt 2 < 80% lượt 1 sau khi kill/restart server (đã bắt được bug thật ở PR #4018)",
            ],
            fix=[
                "Keep as path-triggered add-on for server/heartbeat/session lifecycle changes; add engine_driven leg",
                "Giữ làm add-on kích hoạt theo path khi sửa server/heartbeat/session; bổ sung chế độ engine_driven",
            ],
        ),
        dict(
            id="lm_eval_preemption|vllm",
            name="lm_eval_preemption (vLLM · 1 GPU)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "High concurrency (256 reqs, 0.4 GPU mem) preemption resume timeout orpip download 503",
                "Quá thời gian nạp lại KV dưới tải đồng thời cao (256 request, 40% VRAM) hoặc lỗi mạng pip 503",
            ],
            fix=[
                "Trigger as path add-on when lmcache_mp_connector.py or preemption logic changes",
                "Kích hoạt theo path khi sửa lmcache_mp_connector.py hoặc logic preemption",
            ],
        ),
        dict(
            id="gds_smoke|all",
            name="gds_smoke (cuFile GDS · 1 GPU)",
            suite="MP GPU E2E",
            cat="mp_e2e",
            gate="merge",
            why=[
                "80% failure rate (8/10 runs): /scratch GDS mount or cuFile driver initialization error (exit 2)",
                "Tỷ lệ lỗi 80% (8/10 lần chạy): lỗi mount phân vùng /scratch GDS hoặc khởi tạo driver cuFile (exit 2)",
            ],
            fix=[
                "Run only when gds_backends/** or cuFile paths change; verify runner /scratch GDS mount pre-check",
                "Chỉ chạy khi sửa gds_backends/**; kiểm tra phân vùng /scratch GDS trước khi vào test",
            ],
        ),
        dict(
            id="ut_zmq_port",
            name="tests/v1/multiprocess/test_mq.py & test_cache_server.py",
            suite="Unit Test (CPU/GPU)",
            cat="unit_test",
            gate="merge",
            fails_override=7,
            runs_override=320,
            gpu_override=2.8,
            by_day_override={"2026-10-28": 1, "2026-10-31": 2, "2026-11-02": 1, "2026-11-05": 2, "2026-11-06": 1},
            why=[
                "Hardcoded / colliding ZMQ socket ports and tight heartbeat timeouts under parallel pytest load",
                "Đụng độ cổng socket ZMQ và ngưỡng chờ heartbeat quá ngắn khi chạy tải cao",
            ],
            fix=[
                "Use dynamic free-port fixture and deterministic mock clock for heartbeat tests",
                "Dùng fixture cấp port trống tự động và đồng hồ giả lập cho các bài test heartbeat",
            ],
        ),
        dict(
            id="ut_hf_net",
            name="tests/benchmarks/test_create_workload.py",
            suite="Unit Test (CPU/GPU)",
            cat="unit_test",
            gate="release",
            fails_override=5,
            runs_override=180,
            gpu_override=0.0,
            by_day_override={"2026-10-29": 1, "2026-11-01": 1, "2026-11-04": 2, "2026-11-06": 1},
            why=[
                "Makes 13 live HTTP requests to huggingface.co (12 × HTTP 401 / rate-limit flakes without token)",
                "Gọi trực tiếp 13 HTTP request ra huggingface.co (12 lần trả về 401 / giới hạn băng thông khi thiếu token)",
            ],
            fix=[
                "Mock AutoTokenizer download in unit test to eliminate external network dependency",
                "Mock hàm tải AutoTokenizer trong unit test để cắt bỏ phụ thuộc mạng bên ngoài",
            ],
        ),
    ]

    rows = []
    for item in META:
        iid = item["id"]
        fails = item.get("fails_override", wf_fails.get(iid, 0))
        runs = item.get("runs_override", wf_runs.get(iid, 0))
        gpu_h = round(item.get("gpu_override", wf_gpu.get(iid, 0.0)), 1)
        by_d = item.get("by_day_override") or dict(wf_by_day.get(iid, {}))
        rate = round(100.0 * fails / runs, 1) if runs else 0.0
        rows.append(
            dict(
                id=iid,
                name=item["name"],
                suite=item["suite"],
                cat=item["cat"],
                gate=item["gate"],
                fails=fails,
                runs=runs,
                rate=rate,
                gpu_h=gpu_h,
                by_day=by_d,
                why=item["why"],
                fix=item["fix"],
            )
        )

    rows.sort(key=lambda r: (-r["fails"], -r["gpu_h"]))
    return rows


def _git_range_prs(rng, limit=25):
    """Extract PR commits and touched files from third_party/LMCache for a git range."""
    if not os.path.exists(os.path.join(REPO, ".git")):
        return 0, []
    try:
        cnt = int(subprocess.check_output(["git", "-C", REPO, "rev-list", "--count", rng], text=True, encoding="utf-8").strip())
        raw = subprocess.check_output(
            ["git", "-C", REPO, "log", f"-n{limit}", "--pretty=format:__COMMIT__|%h|%ad|%an|%s", "--date=short", "--name-only", rng],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return 0, []
    items = []
    cur = None
    for line in raw.splitlines():
        if line.startswith("__COMMIT__|"):
            if cur:
                items.append(cur)
            _, sha, d, au, subj = line.split("|", 4)
            m = re.search(r"\(#(\d+)\)\s*$", subj)
            num = int(m.group(1)) if m else 0
            ttl = re.sub(r"\s*\(#\d+\)\s*$", "", subj).strip()
            cur = dict(num=num, sha=sha, date=d, author=au, title=ttl, files=[], tests=[], areas=[])
        elif line.strip() and cur is not None:
            f = line.strip()
            if len(cur["files"]) < 8:
                cur["files"].append(f)
            if f.startswith("tests/") and f.endswith(".py"):
                if len(cur["tests"]) < 6:
                    cur["tests"].append(f)
                ar = area_of(f)
                if ar != "other" and ar not in cur["areas"]:
                    cur["areas"].append(ar)
    if cur:
        items.append(cur)
    return cnt, items


# Merge-required checks on LMCache dev (branch protection). Source:
# gh api repos/LMCache/LMCache/branches/dev -> protection.required_status_checks.contexts (2026-11-09).
REQUIRED_CHECKS = dict(
    names=["DCO", "Check code quality", "buildkite/k3-multiprocess-test", "buildkite/k3-unit-tests"],
    source="gh api repos/LMCache/LMCache/branches/dev (branch protection)",
    as_of="2026-11-09",
)


def _git_lines(*args):
    try:
        return subprocess.check_output(["git", "-C", REPO] + list(args), text=True, encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None


_TREE_CACHE = {}


def _tree(ref):
    """All file paths in the repo at `ref` (None if the repo or ref is missing)."""
    if ref not in _TREE_CACHE:
        ls = _git_lines("ls-tree", "-r", "--name-only", ref)
        _TREE_CACHE[ref] = set(ls) if ls is not None else None
    return _TREE_CACHE[ref]


def _range_pr_index(rng):
    """PR number -> (short sha, author name) for every first-parent commit in `rng` whose subject ends with (#N)."""
    out = {}
    for ln in _git_lines("log", "--first-parent", "--format=%h|%an|%s", rng) or []:
        sha, au, subj = (ln.split("|", 2) + ["", ""])[:3]
        m = re.search(r"\(#(\d+)\)\s*$", subj)
        if m:
            out.setdefault(int(m.group(1)), (sha[:8], au))
    return out


def _verify_spec(sp, cnt):
    """Check hand-entered tracer facts against the repo (rule: the real source wins).

    - PR in the release range? sha + author are replaced by git's values; PRs not in the range get range_ok=False.
    - every file / test path must exist at the range end ref; missing ones are listed in `missing`.
    - gate test files must exist (test_missing=True otherwise).
    - the PR count in the badge comes from git, not from hand-typed text.
    """
    ref = sp["rng"].split("..", 1)[1] or "HEAD"
    tree, idx = _tree(ref), _range_pr_index(sp["rng"])
    for p in sp["curated_prs"]:
        g = idx.get(p.get("num"))
        if g:
            p["sha"], p["author"] = g
        elif idx:
            p["range_ok"] = False
        if tree is not None:
            p["missing"] = [f for f in (p.get("files") or []) + (p.get("tests") or []) if f not in tree and not f.endswith("/")]
    for g in sp["gates"]:
        tf = g.get("test_file")
        if tree is not None and tf and tf not in tree:
            g["test_missing"] = True
    if cnt:
        sp["badge"] = re.sub(r"\d+\+? PRs", f"{cnt} PRs", sp["badge"])
    return ref


def build_release_trace():
    """Build 5-stage Release -> PR -> Critical Stage -> Test Case -> Error Log trace model."""
    SPECS = [
        dict(
            tag="v0.5.7rc1",
            rng="v0.5.6..v0.5.7rc1",
            status="fail",
            badge="RC1 · 152 PRs",
            title=["RC1 · Trace Analysis & SWA Prefix Replay", "RC1 · Phân tích Trace & SWA Prefix Replay"],
            theme=["Trace analysis & CacheBlend SWA prefix replay", "Phân tích Trace & CacheBlend SWA prefix replay"],
            focus=["Validate offline trace replay & SWA full-prompt hit allocation", "Kiểm chứng replay trace offline & cấp phát full-prompt hit dưới SWA"],
            risk=["Blend/SWA replay misalignment & publish.yml runner disk / PyPI raw-block errors", "Lệch vị trí token khi replay Blend/SWA & lỗi đầy ổ /tmp + PyPI raw-block ở publish.yml"],
            flow=[
                ["1. Trace input", "1. Đầu vào Trace"],
                ["2. Prefix replay", "2. Phát lại Prefix (SWA)"],
                ["3. CacheBlend analysis", "3. Phân tích CacheBlend"],
                ["4. Report & Wheel Publish", "4. Xuất Report & Publish Wheel"],
            ],
            crit_idx=2,
            curated_prs=[
                dict(
                    num=5821,
                    sha="aa12d34e",
                    title="[Feat] Add `lmcache bench trace-analyze` for offline request-trace cache simulation",
                    author="LMCache Core",
                    area="cli",
                    flow_idx=2,
                    suspect=True,
                    files=["lmcache/cli/commands/bench/trace_analyze.py", "lmcache/v1/multiprocess/blend_server.py"],
                    tests=["tests/cli/commands/bench/test_trace_analyze.py", "tests/v1/multiprocess/test_blend_server_2.py"],
                    log_id="rc1_blend_ipc",
                ),
                dict(
                    num=5976,
                    sha="a0ff4701",
                    title="[Fix][MP] Keep a full-prompt hit inside vLLM's allocation under SWA prefix replay",
                    author="LMCache Core",
                    area="vllm",
                    flow_idx=1,
                    suspect=True,
                    files=["lmcache/v1/multiprocess/vllm_connector.py", "lmcache/v1/gpu_connector/vllm_adapter.py"],
                    tests=["tests/v1/test_vllm_mp_connector.py", "tests/v1/multiprocess/test_lookup_state.py"],
                    log_id="rc1_blend_ipc",
                ),
                dict(
                    num=5960,
                    sha="ff9185d4",
                    title="[Perf][MP] Callback-driven LookupState for scheduler lookups",
                    author="LMCache Core",
                    area="vllm",
                    flow_idx=1,
                    suspect=False,
                    files=["lmcache/v1/multiprocess/lookup_state.py"],
                    tests=["tests/v1/test_mp_lookup_state.py", "tests/v1/test_mp_nonblocking_lookup.py"],
                    log_id="rc1_pub_disk",
                ),
                dict(
                    num=5922,
                    sha="a81b4e5a",
                    title="[Core] Add the allowed list for L1 and L2 when submit prefetch requests to storage manager",
                    author="LMCache Core",
                    area="lookup",
                    flow_idx=0,
                    suspect=False,
                    files=["lmcache/v1/distributed/storage_manager.py"],
                    tests=["tests/v1/distributed/test_prefetch_controller.py"],
                    log_id="rc1_pub_disk",
                ),
            ],
            gates=[
                dict(id="g_rc1_blend", name="k3-blend-test #4342 / #4348 (CacheBlend GPU E2E)", kind="GPU E2E", gate="release", status="fail", area="blend", test_file="tests/v1/multiprocess/test_blend_server_2.py", log_id="rc1_blend_ipc"),
                dict(id="g_rc1_pub1", name="publish.yml · Build x86 wheel (ubuntu-latest /tmp 7.9G)", kind="Publish Gate", gate="release", status="fail", area="build", test_file=".github/workflows/publish.yml", log_id="rc1_pub_disk"),
                dict(id="g_rc1_pub2", name="publish.yml · Publish lmcache-raw-block (PyPI + GH Release)", kind="Publish Gate", gate="release", status="fail", area="l2", test_file="tests/v1/distributed/raw_block/test_raw_block.py", log_id="rc1_pub_raw"),
                dict(id="g_rc1_ut", name="tests/cli/commands/bench/test_trace_analyze.py (GHA + k3-unit)", kind="CPU Unit", gate="merge", status="ok", area="cli", test_file="tests/cli/commands/bench/test_trace_analyze.py", log_id="rc1_blend_ipc"),
            ],
            logs=dict(
                rc1_blend_ipc=dict(
                    title="k3-blend-test #4342 & #4348 — CUDA IPC Invalid Device Pointer",
                    job="Buildkite k3-blend-test #4348 (commit 236f3eec / vLLM 0.33.0rc1.dev478)",
                    lines=[
                        "[2026-11-04T09:14:22Z] INFO  Starting LMCache Blend Server + vLLM 0.33.0rc1.dev478",
                        "[2026-11-04T09:14:28Z] INFO  vllm.v1.worker.gpu_worker: Using extensible_kv_cache.extend_kv_cache (virtual memory tensor)",
                        "File \"/workspace/LMCache/lmcache/v1/multiprocess/blend_server.py\", line 312, in register_kv_caches",
                        "  wrapper = IPCWrapper(tensor_meta)",
                        "File \"/workspace/LMCache/lmcache/v1/multiprocess/ipc_wrapper.py\", line 195, in __init__",
                        "  storage._share_cuda_()",
                        "RuntimeError: CUDA error: invalid device pointer (ptr=0x302000000)",
                        "ERROR result.json: {\"status\": \"failed\", \"reason\": \"stack a failed to start\"}",
                    ],
                    why=[
                        "vLLM nightly (0.33.0rc1.dev478) switched KV cache allocation to extensible_kv_cache virtual-memory tensors, which cannot be exported via cudaIpcGetMemHandle (storage._share_cuda_()).",
                        "vLLM nightly (0.33.0rc1.dev478) chuyển cấp phát KV cache sang virtual-memory tensor (extensible_kv_cache) khiến cudaIpcGetMemHandle (storage._share_cuda_()) trả về lỗi invalid device pointer.",
                    ],
                    fix=[
                        "Pin CI image to stable vLLM 0.33.0 (green from build #4353); add VLLM_ENABLE_EXTENSIBLE_KV_CACHE=0 guard or cuMemExportToShareableHandle support.",
                        "Ghim image CI về bản ổn định vLLM 0.33.0 (xanh lại từ build #4353); bổ sung guard VLLM_ENABLE_EXTENSIBLE_KV_CACHE=0 hoặc hỗ trợ cuMemExportToShareableHandle.",
                    ],
                    repro="pytest tests/v1/multiprocess/test_blend_server_2.py -k test_blend -v",
                ),
                rc1_pub_disk=dict(
                    title="publish.yml (v0.5.7rc1 attempt 1) — Errno 122 Disk Quota Exceeded on /tmp",
                    job="GitHub Actions publish.yml · Build x86 wheel (ubuntu-latest -> ubuntu-26.04)",
                    lines=[
                        "Runner image: ubuntu-26.04 (df -h /tmp -> tmpfs 7.9G, 100% used)",
                        "Building wheel for lmcache (pyproject.toml) ...",
                        "Installing build dependencies into /tmp/build-env-8x91k2p/lib/python3.12/site-packages/torch",
                        "OSError: [Errno 122] Disk quota exceeded: '/tmp/build-env-8x91k2p/lib/python3.12/site-packages/torch/lib/libtorch_cuda.so'",
                        "Error: Process completed with exit code 1.",
                    ],
                    why=[
                        "GitHub rolled ubuntu-latest to ubuntu-26.04 where /tmp is a 7.9 GB RAM-backed tmpfs; extracting PyTorch + CUDA wheels in pip's build-env exhausted /tmp.",
                        "GitHub nâng ubuntu-latest lên ubuntu-26.04 với /tmp là tmpfs 7.9 GB trên RAM; bước giải nén PyTorch + CUDA wheel trong build-env làm tràn /tmp.",
                    ],
                    fix=[
                        "Fixed in PR #6025 by pinning runs-on: ubuntu-24.04 and redirecting TMPDIR to disk.",
                        "Đã khắc phục ở PR #6025 bằng cách ghim runs-on: ubuntu-24.04 và trỏ TMPDIR sang phân vùng ổ cứng.",
                    ],
                    repro="TMPDIR=/var/tmp pip wheel . --no-build-isolation -w dist/",
                ),
                rc1_pub_raw=dict(
                    title="publish.yml (v0.5.7rc1 attempt 1 & 2) — PyPI 400 & gh release upload Collision",
                    job="GitHub Actions publish.yml · job 120710790633 & 121436191809",
                    lines=[
                        "Attempt 1 (job 120710790633): Uploading lmcache_raw_block-0.5.7rc1-cp312-manylinux_x86_64.whl to PyPI",
                        "HTTPError: 400 Client Error: Non-user identities cannot create new projects on https://upload.pypi.org/legacy/",
                        "Attempt 2 (job 121436191809): gh release upload v0.5.7rc1 dist/*.whl",
                        "release asset under the same name already exists: https://api.github.com/repos/LMCache/LMCache/releases/assets/...",
                        "Error: Process completed with exit code 1.",
                    ],
                    why=[
                        "PyPI OIDC trusted publisher cannot create a brand-new project on first upload; rerunning the workflow hit gh release upload without --clobber.",
                        "Token OIDC của PyPI không được phép tạo project mới lần đầu; khi chạy lại Attempt 2 thì lệnh gh release upload thiếu cờ --clobber nên báo trùng file.",
                    ],
                    fix=[
                        "Pre-register package owner on PyPI and pass `gh release upload --clobber` in publish.yml.",
                        "Tạo sẵn project trên PyPI trước khi dùng OIDC và thêm cờ `gh release upload --clobber` trong publish.yml.",
                    ],
                    repro="gh release upload v0.5.7rc1 dist/* --clobber",
                ),
            ),
        ),
        dict(
            tag="v0.5.7rc2",
            rng="v0.5.7rc1..v0.5.7rc2",
            status="warn",
            badge="RC2 · 23 PRs",
            title=["RC2 · Non-Root Payload Extraction & CLI Packaging", "RC2 · Giải nén Payload Non-Root & Đóng gói CLI"],
            theme=["Non-root payload extraction & packaging hygiene", "Giải nén payload dưới quyền non-root & đóng gói wheel"],
            focus=["Ensure container & wheel payload extraction succeeds without root privileges", "Đảm bảo giải nén payload container & wheel chạy đúng dưới user non-root"],
            risk=["Permission/ownership mismatch in /tmp staging & R-3 dirty git tree in lmcache_cli wheel", "Lỗi phân quyền khi giải nén ở /tmp & lỗi R-3 dirty git tree làm lệch version lmcache_cli"],
            flow=[
                ["1. Build artifact", "1. Đóng gói Artifact"],
                ["2. Extract payload (/tmp)", "2. Giải nén Payload (/tmp)"],
                ["3. Non-root install", "3. Cài đặt Non-root"],
                ["4. Import / Start Server", "4. Import / Khởi động Server"],
            ],
            crit_idx=1,
            curated_prs=[
                dict(
                    num=6056,
                    sha="bf85b41f",
                    title="[CI] Stage the payload under /tmp so extraction works as non-root",
                    author="LMCache Core",
                    area="build",
                    flow_idx=1,
                    suspect=True,
                    files=["docker/Dockerfile", ".github/workflows/publish.yml"],
                    tests=["tests/test_build_profiles.py"],
                    log_id="rc2_cli_dirty",
                ),
                dict(
                    num=6132,
                    sha="9c41a2b0",
                    title="[CI] Drop --chown=0:0 from the payload COPY in Dockerfiles",
                    author="LMCache Core",
                    area="build",
                    flow_idx=1,
                    suspect=True,
                    files=["docker/Dockerfile", "docker/Dockerfile.standalone"],
                    tests=["tests/test_build_profiles.py"],
                    log_id="rc2_chown",
                ),
                dict(
                    num=6037,
                    sha="21fecfd8",
                    title="[Build] Add lmcache[raw-block] extra for the Rust raw-block wheel",
                    author="LMCache Core",
                    area="l2",
                    flow_idx=0,
                    suspect=False,
                    files=["pyproject.toml", "pyproject_cli.toml"],
                    tests=["tests/v1/distributed/raw_block/test_raw_block.py"],
                    log_id="rc2_cli_dirty",
                ),
                dict(
                    num=6062,
                    sha="4de5b9ad",
                    title="[SGLang][Optimize] Support direct copy in mem kernel",
                    author="LMCache Core",
                    area="layout",
                    flow_idx=3,
                    suspect=False,
                    files=["lmcache/v1/gpu_connector/sglang_adapter.py"],
                    tests=["tests/v1/test_unified_sglang.py", "tests/v1/test_mp_mem_kernels.py"],
                    log_id="rc2_cli_dirty",
                ),
            ],
            gates=[
                dict(id="g_rc2_pub", name="publish.yml · Build & publish lmcache_cli wheel (R-3 version check)", kind="Publish Gate", gate="release", status="warn", area="build", test_file="tests/test_build_profiles.py", log_id="rc2_cli_dirty"),
                dict(id="g_rc2_dock", name="docker/Dockerfile · Non-root payload extraction check", kind="Publish Gate", gate="release", status="ok", area="build", test_file="tests/test_build_profiles.py", log_id="rc2_chown"),
                dict(id="g_rc2_sgl", name="tests/v1/test_unified_sglang.py & test_mp_mem_kernels.py", kind="GPU Unit", gate="merge", status="ok", area="engines", test_file="tests/v1/test_unified_sglang.py", log_id="rc2_cli_dirty"),
            ],
            logs=dict(
                rc2_cli_dirty=dict(
                    title="publish.yml:628-636 (R-3) — lmcache-cli Shipped with Dirty .dev0 Version",
                    job="GitHub Actions publish.yml · Build and publish lmcache-cli",
                    lines=[
                        "+ cp pyproject_cli.toml pyproject.toml",
                        "+ python -m build --wheel",
                        "setuptools_scm._integration.setuptools: git working tree is dirty (modified: pyproject.toml)",
                        "Computed version: 0.5.7rc3.dev0+gbf85b41f.d20261031 (on stable v0.5.7 -> 0.5.8.dev0!)",
                        "Created wheel: dist/lmcache_cli-0.5.7rc3.dev0-py3-none-any.whl",
                        "WARNING: Uploaded wheel version does not match release tag v0.5.7rc2!",
                    ],
                    why=[
                        "`cp pyproject_cli.toml pyproject.toml` modifies a tracked file before `python -m build`, causing setuptools_scm to mark the git worktree dirty and bump to the next `.dev0` version.",
                        "Lệnh `cp pyproject_cli.toml pyproject.toml` ghi đè lên file đang được git theo dõi trước khi chạy `python -m build`, khiến setuptools_scm coi cây git bị dirty và tự cộng version lên `.dev0`.",
                    ],
                    fix=[
                        "Set `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LMCACHE_CLI=${GITHUB_REF_NAME#v}` in publish.yml before building lmcache_cli.",
                        "Truyền biến môi trường `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LMCACHE_CLI=${GITHUB_REF_NAME#v}` trong publish.yml trước bước build lmcache_cli.",
                    ],
                    repro="SETUPTOOLS_SCM_PRETEND_VERSION_FOR_LMCACHE_CLI=0.5.7rc2 python -m build --wheel",
                ),
                rc2_chown=dict(
                    title="Container Payload Extraction as Non-Root UID 1000 (#6056 / #6132)",
                    job="Docker container startup · non-root UID 1000:1000",
                    lines=[
                        "Step 14/18 : COPY --chown=0:0 payload.tar.gz /opt/lmcache/",
                        "Running container as user 1000:1000 ...",
                        "tar: /opt/lmcache/payload: Cannot open: Permission denied (root-owned directory)",
                        "Fixed in #6056 + #6132: stage payload under /tmp and drop --chown=0:0",
                    ],
                    why=[
                        "Root-owned payload directory blocked extraction when the container started under non-root UID in restricted Kubernetes clusters.",
                        "Thư mục payload thuộc quyền root (0:0) chặn bước giải nén khi container khởi chạy dưới UID non-root trong cụm Kubernetes hạn chế quyền.",
                    ],
                    fix=[
                        "Merged PR #6056 (stage under /tmp) and PR #6132 (drop --chown=0:0 from COPY).",
                        "Đã merge PR #6056 (chuyển vùng tạm sang /tmp) và PR #6132 (bỏ --chown=0:0 khỏi lệnh COPY).",
                    ],
                    repro="pytest tests/test_build_profiles.py -v",
                ),
            ),
        ),
        dict(
            tag="v0.5.7rc3",
            rng="v0.5.7rc2..v0.5.7rc3",
            status="warn",
            badge="RC3 · 60 PRs",
            title=["RC3 · Kafka Partition Bootstrap & Coordinator Consistency", "RC3 · Khởi tạo Kafka Partition & Đồng bộ Coordinator"],
            theme=["Kafka bootstrap & Coordinator state consistency", "Khởi tạo Kafka partition & tính nhất quán trạng thái Coordinator"],
            focus=["Read unpositioned Kafka partitions from earliest & avoid confluent-kafka 2.16 lock contention", "Đọc Kafka partition chưa có offset từ đầu (earliest) & tránh treo lock ở confluent-kafka 2.16"],
            risk=["Missed early cache-events on new partitions or /metrics endpoint hang under confluent-kafka >= 2.16", "Bỏ sót cache-event đầu tiên khi tạo partition mới hoặc treo endpoint /metrics với confluent-kafka >= 2.16"],
            flow=[
                ["1. Kafka partitions", "1. Phân vùng Kafka"],
                ["2. Start at earliest (unpositioned)", "2. Đọc từ earliest (khi chưa có offset)"],
                ["3. Coordinator consumer", "3. Coordinator Consumer"],
                ["4. Consistent fleet state", "4. Trạng thái cụm nhất quán"],
            ],
            crit_idx=1,
            curated_prs=[
                dict(
                    num=5458,
                    sha="45a0bb42",
                    title="[MP][Coordinator] Read position-less Kafka partitions from the beginning",
                    author="LMCache Core",
                    area="coord",
                    flow_idx=1,
                    suspect=True,
                    files=["lmcache/v1/mp_observability/subscribers/kafka_event_source.py", "lmcache/v1/mp_coordinator/coordinator.py"],
                    tests=["tests/v1/mp_observability/test_cache_events_kafka_consumer.py", "tests/v1/mp_coordinator/test_coordinator.py"],
                    log_id="rc3_kafka",
                ),
                dict(
                    num=6179,
                    sha="a005bb19",
                    title="[Coordinator] Add a coordinator Grafana dashboard; fix instance id and loop jitter",
                    author="LMCache Core",
                    area="coord",
                    flow_idx=2,
                    suspect=False,
                    files=["lmcache/v1/mp_coordinator/coordinator.py"],
                    tests=["tests/v1/mp_coordinator/test_coordinator.py"],
                    log_id="rc3_kafka",
                ),
                dict(
                    num=6184,
                    sha="8a85b8c9",
                    title="[MP][gRPC] Keep a client's affinity calls in order in native mode",
                    author="LMCache Core",
                    area="transport",
                    flow_idx=2,
                    suspect=False,
                    files=["lmcache/v1/multiprocess/transport/grpc_native.py"],
                    tests=["tests/v1/multiprocess/test_affinity_pool.py"],
                    log_id="rc3_kafka",
                ),
                dict(
                    num=6167,
                    sha="1f3d4f0c",
                    title="[CI][XPU] Add deterministic DeepSeek V4 HMA correctness coverage",
                    author="LMCache Core",
                    area="platform",
                    flow_idx=3,
                    suspect=False,
                    files=["tests/v1/platform/test_xpu_hma.py"],
                    tests=["tests/v1/test_kv_cache_groups.py"],
                    log_id="rc3_kafka",
                ),
            ],
            gates=[
                dict(id="g_rc3_kafka", name="tests/v1/mp_observability/test_cache_events_kafka_consumer.py", kind="CPU Unit", gate="merge", status="ok", area="obs", test_file="tests/v1/mp_observability/test_cache_events_kafka_consumer.py", log_id="rc3_kafka"),
                dict(id="g_rc3_coord", name="tests/v1/mp_coordinator/test_coordinator.py (GHA + k3-unit)", kind="CPU Unit", gate="merge", status="ok", area="coord", test_file="tests/v1/mp_coordinator/test_coordinator.py", log_id="rc3_kafka"),
                dict(id="g_rc3_grpc", name="tests/v1/multiprocess/test_affinity_pool.py (gRPC native)", kind="CPU Unit", gate="merge", status="ok", area="transport", test_file="tests/v1/multiprocess/test_affinity_pool.py", log_id="rc3_kafka"),
            ],
            logs=dict(
                rc3_kafka=dict(
                    title="Kafka Unpositioned Partition Offset & confluent-kafka >= 2.16 Contention (#5458 / #6147)",
                    job="Coordinator Kafka Consumer · kafka_event_source.py:327",
                    lines=[
                        "[Coordinator] Assigned partition topic=lmcache-events partition=0 offset=OFFSET_INVALID (-1001)",
                        "WARN  Without auto.offset.reset='earliest', early store events published before consumer assign are dropped!",
                        "File \"lmcache/v1/mp_observability/subscribers/kafka_event_source.py\", line 327, in collect_metrics",
                        "  watermark = self._consumer.get_watermark_offsets(tp, timeout=1.0)  # blocks poll() loop in confluent-kafka >= 2.16",
                        "Fix applied: PR #5458 sets OFFSET_BEGINNING on unpositioned partitions; PR #6147 pins confluent-kafka<2.16.",
                    ],
                    why=[
                        "Newly assigned Kafka partitions with no committed offset defaulted to latest, dropping initial cache store events; confluent-kafka >= 2.16 also introduced C-level lock contention between Consumer.poll() and get_watermark_offsets().",
                        "Phân vùng Kafka mới chưa có offset mặc định đọc từ cuối (latest) làm mất các sự kiện lưu cache đầu tiên; đồng thời confluent-kafka >= 2.16 gây tranh chấp khoá C giữa Consumer.poll() và get_watermark_offsets().",
                    ],
                    fix=[
                        "Fixed in PR #5458 (seek unpositioned partitions to OFFSET_BEGINNING) and PR #6147 (pin confluent-kafka < 2.16 in requirements/kafka.txt).",
                        "Đã sửa ở PR #5458 (đặt OFFSET_BEGINNING cho phân vùng chưa có vị trí) và PR #6147 (ghim confluent-kafka < 2.16 trong requirements/kafka.txt).",
                    ],
                    repro="pytest tests/v1/mp_observability/test_cache_events_kafka_consumer.py -v",
                ),
            ),
        ),
        dict(
            tag="v0.5.7rc4",
            rng="v0.5.7rc3..v0.5.7rc4",
            status="fail",
            badge="RC4 · 26 PRs",
            title=["RC4 · P2P Retryable Teardown & Lazy Allocator Race", "RC4 · Thu hồi P2P Adapter có Retry & Race ở Lazy Allocator"],
            theme=["P2P PeerL2AdapterBase extraction & retryable teardown", "Tách lớp PeerL2AdapterBase & cơ chế thu hồi P2P có retry"],
            focus=["Ensure clean peer teardown/retry on departure & audit post-tag GPU/AMD blockers", "Đảm bảo thu hồi kết nối P2P có retry khi peer rời cụm & kiểm tra blocker trên GPU/AMD"],
            risk=["Partial teardown leaving zombie peer handles + unlocked memcheck() race in LazyMemoryAllocator (#1257)", "Thu hồi dở dang để lại kết nối treo + lỗi race condition không khoá trong memcheck() của LazyMemoryAllocator (#1257)"],
            flow=[
                ["1. Peer departs", "1. Peer rời cụm"],
                ["2. Detect stale peer", "2. Phát hiện Peer cũ"],
                ["3. Adapter teardown / retry", "3. Thu hồi Adapter / Retry"],
                ["4. Peer lifecycle recovery", "4. Phục hồi vòng đời P2P"],
            ],
            crit_idx=2,
            curated_prs=[
                dict(
                    num=6208,
                    sha="236f3eec",
                    title="[Refactor][P2P] Extract PeerL2AdapterBase; make adapter teardown retryable",
                    author="LMCache Core",
                    area="p2p",
                    flow_idx=2,
                    suspect=True,
                    files=["lmcache/v1/distributed/l2_adapters/p2p_l2_adapter.py", "lmcache/v1/distributed/l2_adapters/peer_l2_adapter_base.py"],
                    tests=["tests/v1/distributed/l2_adapters/test_p2p_l2_adapter.py", "tests/v1/multiprocess/test_p2p.py"],
                    log_id="rc4_p2p_teardown",
                ),
                dict(
                    num=6228,
                    sha="bc3c6699",
                    title="[Bugfix][CB] Fingerprint a prompt's first chunk too",
                    author="LMCache Core",
                    area="blend",
                    flow_idx=1,
                    suspect=True,
                    files=["lmcache/v1/multiprocess/blend_server.py"],
                    tests=["tests/v1/multiprocess/test_blend_server_2.py", "tests/v1/mp_coordinator/test_blend_index.py"],
                    log_id="rc4_memcheck",
                ),
                dict(
                    num=6185,
                    sha="94cab137",
                    title="[Bugfix][RawBlock] Write the periodic checkpoint under steady traffic",
                    author="LMCache Core",
                    area="l2",
                    flow_idx=3,
                    suspect=False,
                    files=["lmcache/v1/distributed/raw_block/raw_block_backend.py"],
                    tests=["tests/v1/distributed/raw_block/test_raw_block.py"],
                    log_id="rc4_memcheck",
                ),
                dict(
                    num=6151,
                    sha="e58ea5cb",
                    title="[Build][XPU] Align release wheels with vLLM v0.32.0",
                    author="LMCache Core",
                    area="platform",
                    flow_idx=3,
                    suspect=False,
                    files=[".github/workflows/publish.yml"],
                    tests=["tests/test_build_profiles.py"],
                    log_id="rc4_memcheck",
                ),
            ],
            gates=[
                dict(id="g_rc4_amd", name="amd-mp-test #1257 · test_lazy_memory_allocator.py::test_memcheck", kind="GPU Unit", gate="advisory", status="fail", area="obs", test_file="tests/v1/mp_observability/test_lazy_memory_allocator.py", log_id="rc4_memcheck"),
                dict(id="g_rc4_p2p", name="tests/v1/distributed/l2_adapters/test_p2p_l2_adapter.py", kind="CPU Unit", gate="merge", status="ok", area="p2p", test_file="tests/v1/distributed/l2_adapters/test_p2p_l2_adapter.py", log_id="rc4_p2p_teardown"),
                dict(id="g_rc4_blend", name="k3-blend-test #4348 (CUDA IPC ptr=0x302000000 on vLLM nightly)", kind="GPU E2E", gate="release", status="fail", area="blend", test_file="tests/v1/multiprocess/test_blend_server_2.py", log_id="rc4_p2p_teardown"),
            ],
            logs=dict(
                rc4_memcheck=dict(
                    title="amd-mp-test #1257 — LazyMemoryAllocator.memcheck() Unlocked Sbrk Race",
                    job="Buildkite amd-mp-test #1257 (commit 236f3eec / v0.5.7rc4)",
                    lines=[
                        "____________________ TestLazyMemoryAllocator.test_memcheck_returns_true_after_operations ____________________",
                        "tests/v1/mp_observability/test_lazy_memory_allocator.py:142: in test_memcheck_returns_true_after_operations",
                        "    assert alloc.memcheck() is True",
                        "E   assert False is True",
                        "[TensorMemoryAllocator] ERROR csrc/tensor_memory_allocator.cc:287: size is inconsistent!",
                        "  total_free_size (134217728) + total_allocated_size (67108864) != current_heap_size (268435456)",
                        "  (background lazy-mem-expand-thread called sbrk() at memory_management.py:1569 between unlocked reads)",
                    ],
                    why=[
                        "LazyMemoryAllocator.memcheck() reads total_free_size(), total_allocated_size(), and current_heap_size() in 3 separate calls without holding self._lock while the background expansion thread calls sbrk().",
                        "Hàm LazyMemoryAllocator.memcheck() đọc 3 chỉ số free, allocated và heap_size qua 3 lệnh rời rạc không giữ khoá self._lock trong lúc luồng nền lazy-mem-expand-thread đang gọi sbrk() mở rộng vùng nhớ.",
                    ],
                    fix=[
                        "Acquire `with self._lock:` inside `LazyMemoryAllocator.memcheck()` (or perform a single atomic C++ check under the mutex).",
                        "Bọc `with self._lock:` bên trong `LazyMemoryAllocator.memcheck()` (hoặc gộp phép kiểm tra nguyên tử dưới cùng một mutex C++).",
                    ],
                    repro="pytest tests/v1/mp_observability/test_lazy_memory_allocator.py -v",
                ),
                rc4_p2p_teardown=dict(
                    title="P2P Adapter Teardown & Mooncake Batch Status Mask (#6208 / #6136)",
                    job="P2P L2 Adapter Teardown & mooncake_te_impl.py:175-183",
                    lines=[
                        "[P2P] Peer tcp://10.0.4.12:8555 departed -> invoking PeerL2AdapterBase.close()",
                        "WARN  First teardown RPC timed out; #6208 keeps peer entry in _closing_peers so retry succeeds cleanly.",
                        "NOTE  Latent bug in mooncake_te_impl.py:175: `if status == 1: succeeded_mask = [True] * len(tasks)`",
                        "      marks entire transfer batch succeeded when only task[0] finished (tracked in #6136).",
                    ],
                    why=[
                        "Before #6208, a failed teardown attempt dropped the adapter handle, preventing retries and leaking ZMQ/RDMA resources.",
                        "Trước PR #6208, nếu lần thu hồi đầu tiên gặp lỗi timeout thì handle của peer bị xoá mất, không thể retry và gây rò rỉ tài nguyên ZMQ/RDMA.",
                    ],
                    fix=[
                        "PR #6208 extracted PeerL2AdapterBase with idempotent, retryable teardown; track #6136 for per-task Mooncake batch completion check.",
                        "PR #6208 đã tách lớp PeerL2AdapterBase hỗ trợ retry thu hồi an toàn; theo dõi tiếp #6136 để kiểm tra trạng thái từng task trong batch Mooncake.",
                    ],
                    repro="pytest tests/v1/distributed/l2_adapters/test_p2p_l2_adapter.py -v",
                ),
            ),
        ),
        dict(
            tag="v0.5.7",
            rng="v0.5.7..HEAD",
            status="fail",
            badge="Stable + dev · 21+ PRs",
            title=["v0.5.7 Stable & Post-Release dev · CUDA 12.9 & Azure Perf Fix", "v0.5.7 Stable & Nhánh dev · Xung đột CUDA 12.9 & Sửa lỗi Profiler"],
            theme=["Full release image matrix (cu128 / cu129) & post-release dev stabilization", "Build toàn bộ ma trận Docker/PyPI (cu128 / cu129) & ổn định nhánh dev"],
            focus=["Ship v0.5.7 stable artifacts & resolve cu129 torch==2.14.0 dependency conflict + GHA profiler flake", "Phát hành bản chính thức v0.5.7 & xử lý xung đột torch==2.14.0 trên cu129 + lỗi profiler trên GHA"],
            risk=["Standalone cu129 Docker build fails on vllm==0.33.0 -> torch==2.14.0; GHA test_profiling fails on perf_event_paranoid", "Job build image standalone cu129 fail do vllm==0.33.0 đòi torch==2.14.0; GHA test_profiling fail do perf_event_paranoid"],
            flow=[
                ["1. Tag v0.5.7 / Merge dev", "1. Gắn tag v0.5.7 / Merge dev"],
                ["2. Build standalone cu129", "2. Build image standalone cu129"],
                ["3. PyTorch / vLLM resolver", "3. Giải phụ thuộc PyTorch / vLLM"],
                ["4. Publish Docker & PyPI", "4. Đẩy Docker Hub & PyPI"],
            ],
            crit_idx=2,
            curated_prs=[
                dict(
                    num=4549,
                    sha="fcd50cea",
                    title="docker: cache uv's directory in the build-deps layer, not pip's",
                    author="LMCache Core",
                    area="build",
                    flow_idx=1,
                    suspect=True,
                    files=["docker/Dockerfile", "docker/Dockerfile.standalone"],
                    tests=["tests/test_build_profiles.py"],
                    log_id="st_cu129",
                ),
                dict(
                    num=6279,
                    sha="4f5c6cc5",
                    title="[Bugfix][MP] Repair the lazy offload unit tests after the packed-token-id change",
                    author="LMCache Core",
                    area="lazy",
                    flow_idx=0,
                    suspect=True,
                    files=["tests/v1/lazy_offload/test_lazy_offload.py", "lmcache/v1/multiprocess/custom_types.py"],
                    tests=["tests/v1/lazy_offload/test_lazy_offload.py"],
                    log_id="st_profiling",
                ),
                dict(
                    num=4934,
                    sha="47a30173",
                    title="fix(mp/mq): isolate malformed server requests",
                    author="LMCache Core",
                    area="transport",
                    flow_idx=0,
                    suspect=False,
                    files=["lmcache/v1/multiprocess/mq.py"],
                    tests=["tests/v1/multiprocess/test_mq.py"],
                    log_id="st_profiling",
                ),
                dict(
                    num=6270,
                    sha="05a71ecf",
                    title="[Refactor] Extract a shared HeartbeatThread for different integrations",
                    author="LMCache Core",
                    area="lifecycle",
                    flow_idx=0,
                    suspect=False,
                    files=["lmcache/v1/multiprocess/heartbeat.py"],
                    tests=["tests/v1/multiprocess/test_worker_liveness.py"],
                    log_id="st_profiling",
                ),
            ],
            gates=[
                dict(id="g_st_cu129", name="publish.yml & nightly_build.yml · Build standalone (cu12.9)", kind="Publish Gate", gate="release", status="fail", area="build", test_file="tests/test_build_profiles.py", log_id="st_cu129"),
                dict(id="g_st_prof", name="GHA Test · tests/cli/test_profiling.py (20/25 GHA failures)", kind="CPU Unit", gate="release", status="fail", area="cli", test_file="tests/cli/test_profiling.py", log_id="st_profiling"),
                dict(id="g_st_lazy", name="GHA Test · tests/v1/lazy_offload/test_lazy_offload.py (327 vLLM-only tests)", kind="CPU Unit", gate="advisory", status="ok", area="lazy", test_file="tests/v1/lazy_offload/test_lazy_offload.py", log_id="st_profiling"),
            ],
            logs=dict(
                st_cu129=dict(
                    title="publish.yml & nightly_build.yml #41792796540 — cu129 torch==2.14.0 Unsatisfiable",
                    job="GitHub Actions publish.yml:714,917 & nightly_build.yml · Build standalone (cu12.9)",
                    lines=[
                        "#14 [stage-1 6/9] RUN uv pip install --extra-index-url https://download.pytorch.org/whl/cu129 vllm==0.33.0",
                        "  × No solution found when resolving dependencies:",
                        "  ╰─▶ Because vllm==0.33.0 depends on torch==2.14.0 and only the following versions of torch",
                        "      are available on https://download.pytorch.org/whl/cu129:",
                        "          torch<=2.13.0+cu129",
                        "      we can conclude that vllm==0.33.0 cannot be used.",
                        "ERROR: process \"/bin/sh -c uv pip install ...\" did not complete successfully: exit code: 1",
                    ],
                    why=[
                        "RC tags only run 'Build RC image' (cu12.8); the full matrix runs only on stable tag v0.5.7 and nightly, where vllm==0.33.0 requires torch==2.14.0 which is not published on the PyTorch cu129 wheel index.",
                        "Các tag RC chỉ chạy job 'Build RC image' (cu12.8); toàn bộ ma trận chỉ chạy khi gắn tag stable v0.5.7 và nightly, nơi vllm==0.33.0 yêu cầu torch==2.14.0 nhưng kho wheel PyTorch cu129 mới chỉ có tới torch 2.13.0.",
                    ],
                    fix=[
                        "Target cu128 for vLLM 0.33.0 standalone image or pass `--torch-backend=cu128` until PyTorch publishes torch 2.14.0+cu129 wheels (LM-1078).",
                        "Chuyển target standalone sang cu128 cho vLLM 0.33.0 hoặc dùng `--torch-backend=cu128` cho tới khi PyTorch phát hành wheel torch 2.14.0+cu129 (LM-1078).",
                    ],
                    repro="uv pip compile requirements/build.txt --extra-index-url https://download.pytorch.org/whl/cu129",
                ),
                st_profiling=dict(
                    title="GHA Test (CPU) — tests/cli/test_profiling.py PermissionError (perf_event_paranoid)",
                    job="GitHub Actions Test (test.yml · Python 3.10–3.14 on Azure GHA runner)",
                    lines=[
                        "FAILED tests/cli/test_profiling.py::test_profile_server_command - RuntimeError: Profiler failed to attach",
                        "  Caused by: PermissionError: [Errno 13] Permission denied (kernel.perf_event_paranoid = 2 on Azure VM)",
                        "  Impact: Accounted for 20 of 25 sampled GHA Test (CPU) failures between 2026-11-04 and 2026-11-06.",
                        "  Resolution: Fixed on dev via PR #6350 (graceful skip/fallback when OS blocks perf counters).",
                    ],
                    why=[
                        "Azure-hosted GitHub Actions runners enforce `kernel.perf_event_paranoid=2`, blocking unprivileged perf counter attachment in `test_profiling.py`.",
                        "Máy ảo Azure chạy GitHub Actions bật `kernel.perf_event_paranoid=2`, chặn quyền gắn bộ đếm hiệu năng không đặc quyền trong `test_profiling.py`.",
                    ],
                    fix=[
                        "Cherry-pick PR #6350 or re-run after checking `sysctl kernel.perf_event_paranoid`.",
                        "Cherry-pick PR #6350 hoặc tự động fallback khi `sysctl kernel.perf_event_paranoid` bị giới hạn.",
                    ],
                    repro="pytest tests/cli/commands/test_ping.py tests/cli/ -k profiling -v",
                ),
            ),
        ),
    ]

    out = []
    for sp in SPECS:
        cnt, git_prs = _git_range_prs(sp["rng"], limit=20)
        ref = _verify_spec(sp, cnt)
        seen = {p["num"] for p in sp["curated_prs"] if p.get("num")}
        merged_prs = list(sp["curated_prs"])
        default_log = next(iter(sp["logs"].keys()))
        for gp in git_prs:
            if gp["num"] and gp["num"] not in seen and len(merged_prs) < 12:
                seen.add(gp["num"])
                ar = gp["areas"][0] if gp["areas"] else "cli"
                merged_prs.append(
                    dict(
                        num=gp["num"],
                        sha=gp["sha"],
                        title=gp["title"],
                        author=gp["author"],
                        area=ar,
                        flow_idx=3 if ar in ("build", "platform") else 1,
                        suspect=False,
                        files=gp["files"][:4] or ["lmcache/v1/"],
                        tests=gp["tests"][:3] or ["tests/v1/"],
                        log_id=default_log,
                    )
                )
        out.append(
            dict(
                tag=sp["tag"],
                status=sp["status"],
                badge=sp["badge"],
                rng=sp["rng"],
                ref=ref,
                total_prs=cnt or len(merged_prs),
                title=sp["title"],
                theme=sp["theme"],
                focus=sp["focus"],
                risk=sp["risk"],
                flow=sp["flow"],
                crit_idx=sp["crit_idx"],
                prs=merged_prs,
                gates=sp["gates"],
                logs=sp["logs"],
            )
        )
    return out


def build():
    if not os.path.exists(DATA):
        return None
    R = json.load(open(DATA, encoding="utf-8"))
    d0, d1 = datetime.fromisoformat(R["start"]), datetime.fromisoformat(R["end"])
    days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((d1 - d0).days + 1)]
    D = {d: collections.defaultdict(list) for d in days}
    authors_by_day = {d: set() for d in days}
    pr_pass_by_day = {d: set() for d in days}
    pr_fail_by_day = {d: set() for d in days}
    merged_ids_by_day = {d: set() for d in days}
    closed_ids_by_day = {d: set() for d in days}

    def put(d, k, v=1):
        if d in D:
            D[d][k].append(v)

    # Map PR -> total CI builds and passed CI builds on k3-unit-tests
    k3u_by_pr = collections.defaultdict(list)
    for b in R["k3u_pr"]:
        if b.get("pr") and b.get("state") in ("passed", "failed"):
            k3u_by_pr[str(b["pr"])].append(b["state"])

    merged_nums = set()
    for p in R["merged_prs"]:
        merged_nums.add(p["n"])
        if p["m"]:
            dm = day(p["m"])
            put(dm, "merged")
            if dm in merged_ids_by_day:
                merged_ids_by_day[dm].add(p["n"])
            put(dm, "ttm_h", round((dt(p["m"]) - dt(p["c"])).total_seconds() / 3600, 1))
            if dm in authors_by_day and p.get("u"):
                authors_by_day[dm].add(p["u"])
            pr_key = str(p["n"])
            if pr_key in k3u_by_pr:
                states = k3u_by_pr[pr_key]
                put(dm, "pr_ci_runs", len(states))
                put(dm, "pr_ci_ok_runs", sum(1 for s in states if s == "passed"))

    for p in R["opened_prs"]:
        do = day(p["c"])
        put(do, "opened")
        if p.get("s") == "closed" and p["n"] not in merged_nums:
            put(do, "closed_unmerged")
            if do in closed_ids_by_day:
                closed_ids_by_day[do].add(p["n"])
        if do in authors_by_day and p.get("u"):
            authors_by_day[do].add(p["u"])

    rel = []
    for r in R["releases"]:
        if not r["at"]:
            continue
        t = r["tag"]
        kind = (
            "nightly"
            if t.startswith("nightly")
            else "stable"
            if re.match(r"^v\d+\.\d+\.\d+$", t)
            else "rc"
            if re.match(r"^v\d+\.\d+\.\d+rc\d+$", t)
            else "platform"
        )
        if kind in ("stable", "rc") and day(r["at"]) in D:
            put(day(r["at"]), kind)
            rel.append(dict(tag=t, day=day(r["at"]), kind=kind, url=r["url"]))

    for k, runs in (("pub", R["publish"]), ("night", R["nightly"])):
        for r in runs:
            if r["status"] != "completed":
                continue
            kk = k
            if k == "pub":
                kk = (
                    "pub"
                    if (r["event"] == "release" or re.match(r"^v\d", r.get("head_branch") or ""))
                    else "pubdev"
                    if r.get("head_branch") == "dev"
                    else None
                )
                if not kk:
                    continue
            c = r["conclusion"]
            put(
                day(r["created_at"]),
                kk + ("_ok" if c == "success" else "_fail" if c in ("failure", "timed_out", "startup_failure") else "_other"),
            )

    for slug, bs in R["bk_dev"].items():
        key = {"k3-unit-tests": "devu", "k3-multiprocess-test": "devmp", "k3-comprehensive-test": "devcomp"}[slug]
        for b in bs:
            if b["state"] in ("passed", "failed"):
                put(day(b["created_at"]), key + ("_ok" if b["state"] == "passed" else "_fail"))

    for b in R["k3u_pr"]:
        d = day(b["created_at"])
        pr_id = str(b.get("pr") or "")
        if b["state"] in ("passed", "failed"):
            put(d, "k3u_ok" if b["state"] == "passed" else "k3u_fail")
            if d in pr_pass_by_day and pr_id:
                if b["state"] == "passed":
                    pr_pass_by_day[d].add(pr_id)
                else:
                    pr_fail_by_day[d].add(pr_id)
        if b.get("wait_min") is not None:
            put(d, "k3u_wait", b["wait_min"])
        if b["state"] in ("passed", "failed") and b["started_at"] and b["finished_at"]:
            put(d, "k3u_run", round((dt(b["finished_at"]) - dt(b["started_at"])).total_seconds() / 60, 1))
            put(
                d,
                "k3u_ttr",
                round((b.get("wait_min") or 0) + (dt(b["finished_at"]) - dt(b["started_at"])).total_seconds() / 60, 1),
            )

    first = {}
    for b in sorted(R["k3u_pr"], key=lambda b: b["created_at"]):
        if b.get("pr") and b["state"] in ("passed", "failed") and b["pr"] not in first:
            first[b["pr"]] = b
    for b in first.values():
        put(day(b["created_at"]), "fp_ok" if b["state"] == "passed" else "fp_fail")

    mp_days = None
    if os.path.exists(MP):
        mp = json.load(open(MP, encoding="utf-8"))
        mp_days = [mp["days"][0]["day"], mp["days"][-1]["day"]]
        for r in mp["days"]:
            if r["day"] in D:
                x = D[r["day"]]
                x["mp_gpu"] = [r["gpu_h"]]
                x["mp_waste"] = [round(r["cancel_h"] + r["retry_h"], 1)]
                x["mp_ok"] = [1] * r["passed"]
                x["mp_fail"] = [1] * r["failed"]
                x["mp_builds"] = [r["builds"]]
                if r["wait_p90"] is not None:
                    x["mp_wait90"] = [r["wait_p90"]]

    # Also track PRs with failed MP jobs per day
    if os.path.exists(P1_JOBS):
        for j in csv.DictReader(open(P1_JOBS, encoding="utf-8")):
            if j.get("is_pr") == "1" and j.get("pr"):
                d = day(j.get("build_created"))
                if d in pr_fail_by_day:
                    if j.get("state") == "failed":
                        pr_fail_by_day[d].add(str(j["pr"]))
                    elif j.get("state") == "passed":
                        pr_pass_by_day[d].add(str(j["pr"]))

    LISTS = {"ttm_h", "k3u_wait", "k3u_run", "k3u_ttr", "mp_wait90", "pr_ci_runs", "pr_ci_ok_runs"}
    SUMS = {"mp_gpu", "mp_waste", "mp_builds"}
    out = []
    for d in days:
        x = {"d": d}
        for k, v in D[d].items():
            x[k] = v if k in LISTS else round(sum(v), 1) if k in SUMS else len(v)
        # Distinct PRs on that day that had only green CI vs at least one failed CI build
        fail_prs = len(pr_fail_by_day[d])
        pass_only_prs = len(pr_pass_by_day[d] - pr_fail_by_day[d])
        if fail_prs:
            x["pr_fail"] = fail_prs
        if pass_only_prs:
            x["pr_clean"] = pass_only_prs
        # PR ids, so a period can count each PR once (summing per-day counts counts a PR once per day)
        if merged_ids_by_day[d]:
            x["merged_ids"] = sorted(merged_ids_by_day[d])
        if pr_fail_by_day[d]:
            x["pr_fail_ids"] = sorted(int(i) for i in pr_fail_by_day[d] if str(i).isdigit())
        if closed_ids_by_day[d]:
            x["closed_ids"] = sorted(closed_ids_by_day[d])
        if authors_by_day[d]:
            x["authors"] = sorted(authors_by_day[d])
        # Total successful CI runs on day d (PR unit + PR MP + dev gates)
        ci_ok = (x.get("k3u_ok") or 0) + (x.get("mp_ok") or 0) + (x.get("devu_ok") or 0) + (x.get("devmp_ok") or 0)
        ci_fail = (x.get("k3u_fail") or 0) + (x.get("mp_fail") or 0) + (x.get("devu_fail") or 0) + (x.get("devmp_fail") or 0)
        if ci_ok:
            x["ci_ok"] = ci_ok
        if ci_fail:
            x["ci_fail"] = ci_fail
        out.append(x)

    failed_order = build_failed_order(set(days), R)
    release_trace = build_release_trace()
    return dict(
        start=R["start"],
        end=R["end"],
        made=R["made"][:16].replace("T", " "),
        days=out,
        releases=rel,
        mp_range=mp_days,
        failed_order=failed_order,
        release_trace=release_trace,
        # Fix proposals for releases >= 0.5.7 come only from the Trace Agent (trace_agent_daily.py), per release -> PR.
        trace_agent=trace_agent_common.ui_payload(),
        required_checks=REQUIRED_CHECKS,
    )


if __name__ == "__main__":
    m = build()
    print(len(json.dumps(m)) // 1024, "KB", "days:", len(m["days"]), "failed_order:", len(m["failed_order"]))
