"""Step 2: flatten the jobs of every fetched build into jobs_all_30d.csv (one row per job attempt; PR and non-PR builds,
is_pr tells them apart). Pipelines: k3-multiprocess-test (MP GPU suite) and k3-unit-tests (required unit tests, 1 GPU)."""
import json, csv, re, os
from datetime import datetime

# GPU count per workload, from pod specs in pipeline.yml (unchanged between 2026-10-05 and 2026-11-04).
GPU = {"dsv4_flash_tp": 4,
       "vllm_bench": 2, "long_doc_qa": 2, "long_doc_qa_l2": 2, "deadlock": 2, "mp_autostart_tp2": 2,
       "p2p": 2, "kimi_linear_tp": 2, "preemption_correctness": 2,  # preemption_correctness sits in the 1-GPU group but uses pod-2gpu
       "lm_eval": 1, "lm_eval_preemption": 1, "fault_tolerance": 1, "restart_recovery": 1, "cache_stats": 1,
       "lazy_offload": 1, "http_api": 1, "gds_smoke": 1,
       "cpu_e2e_validation": 0,
       "hma_lm_eval_gemma4": 2,  # from pipeline.yml at commit 7b29da44
       "unit_tests": 1,  # k3-unit-tests: k3_tests/unit/pipeline.yml limits nvidia.com/gpu "1" (same before 2026-10-05)
       }
PIPES = [("k3-multiprocess-test", "raw/builds_30d.json"), ("k3-unit-tests", "raw/builds_k3-unit-tests_30d.json")]


def keep(slug, name):
    """Jobs that hold test work. MP: the workload steps. Unit: every script step except pipeline upload / fast-fail."""
    if slug == "k3-multiprocess-test":
        return name.startswith(":compression:") or name.startswith(":electric_plug:")
    return not name.startswith(":pipeline:") and not name.startswith(":skull:")

def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None

def parse_label(name):
    if "Unit Tests" in name:
        return "unit_tests", "", "", ""
    if name.startswith(":docker:"):
        return "docker_e2e", "", "", ""
    n = re.sub(r"^:[a-z_]+:\s*", "", name).strip()
    eng = transport = mode = ""
    m = re.match(r"cpu_e2e_validation\s*\((.*)\)", n)
    if m:
        parts = [p.strip() for p in m.group(1).split("/")]
        mode = parts[0].replace("server-side copy", "server_copy")
        transport = parts[1] if len(parts) > 1 else ""
        return "cpu_e2e_validation", eng, mode, transport
    m = re.match(r"preemption_correctness / async=(\d)", n)
    if m:
        return "preemption_correctness", "vllm", "async=" + m.group(1), "zmq"
    parts = [p.strip() for p in n.split("/")]
    if parts[0] in ("vllm", "sglang"):
        eng = parts.pop(0)
    if parts and parts[-1] in ("zmq", "grpc"):
        transport = parts.pop()
    w = parts[0] if parts else n
    if len(parts) > 1:
        mode = parts[1]
    if w.startswith("lm_eval_") and w not in ("lm_eval_preemption",) and w[8:] in ("engine_driven", "lmcache_driven"):
        mode, w = w[8:], "lm_eval"
    if w == "gds_smoke_test":
        w = "gds_smoke"
    if w.startswith("kimi_linear_tp_engine_driven"):
        mode, w = mode or "", "kimi_linear_tp_engine_driven"
    return w, eng, mode, transport

def main():
    builds = []
    for slug, fn in PIPES:
        if os.path.exists(fn):
            for b in json.load(open(fn, encoding="utf-8")):
                b["pipeline_slug"] = slug
                builds.append(b)
    rows = []
    for b in builds:
        is_pr = b.get("pull_request") is not None
        slug = b["pipeline_slug"]
        for j in b["jobs"]:
            if j.get("type") != "script" or not j.get("name"):
                continue
            name = j["name"]
            if not keep(slug, name):
                continue
            w, eng, mode, tr = parse_label(name)
            st, fi, ru = ts(j.get("started_at")), ts(j.get("finished_at")), ts(j.get("runnable_at"))
            wall = (fi - st).total_seconds() / 60 if st and fi else None
            q = (st - ru).total_seconds() / 60 if st and ru else None
            g = GPU.get(w)
            rows.append(dict(
                pipeline=slug, build_number=b["number"], build_state=b["state"], is_pr=int(is_pr),
                pr=(b.get("pull_request") or {}).get("id", ""), branch=b["branch"], build_created=b["created_at"],
                commit=b.get("commit") or "", build_url=b.get("web_url") or "",
                job_id=j["id"], label=name, workload=w, engine=eng, mode=mode, transport=tr,
                gpus="" if g is None else g, state=j["state"], exit_status=j.get("exit_status"),
                soft_failed=j.get("soft_failed"), retried=j.get("retried"), retries_count=j.get("retries_count") or 0,
                retry_source=(j.get("retry_source") or {}).get("job_id", "") if isinstance(j.get("retry_source"), dict) else "",
                retry_type=j.get("retry_type") or "", retried_in_job_id=j.get("retried_in_job_id") or "",
                runnable_at=j.get("runnable_at"), started_at=j.get("started_at"), finished_at=j.get("finished_at"),
                wall_min=None if wall is None else round(wall, 3), queue_wait_min=None if q is None else round(q, 3),
                gpu_min=None if (wall is None or g is None) else round(wall * g, 3),
                node=next((m.split("=", 1)[1] for m in ((j.get("agent") or {}).get("meta_data") or []) if m.startswith("k8s:node=")), ""),
                raw_log_url=j.get("raw_log_url") or ""))
    keys = list(rows[0].keys())
    with open("jobs_all_30d.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, keys); wr.writeheader(); wr.writerows(rows)
    print("rows", len(rows), "ran", sum(1 for r in rows if r["started_at"]))

if __name__ == "__main__":
    main()
