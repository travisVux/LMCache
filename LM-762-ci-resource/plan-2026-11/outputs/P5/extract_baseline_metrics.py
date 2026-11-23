"""P5: sample PR jobs of baseline perf workloads, download raw logs in memory only,
extract baseline-side and LMCache-side metrics. Writes P5/raw/metrics.json. Token never printed."""
import csv, json, re, sys, os
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "P1"))
import bk_api

N_PASS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
N_FAIL = int(sys.argv[2]) if len(sys.argv) > 2 else 30
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b_bk;t=\d+\x07")
F = r"([-+0-9.eE]+)"
rows = list(csv.DictReader(open(os.path.join(HERE, "..", "P1", "jobs_all_30d.csv"), encoding="utf-8")))
SETS = [("vllm_bench", "vllm"), ("long_doc_qa", "vllm"), ("long_doc_qa", "sglang"), ("long_doc_qa_l2", "vllm")]

def spread(lst, n):
    lst = sorted(lst, key=lambda x: x["build_created"])
    if len(lst) <= n: return lst
    return [lst[int(i * len(lst) / n)] for i in range(n)]

picks = []
for wl, eng in SETS:
    base = [x for x in rows if x["workload"] == wl and x["engine"] == eng and x["is_pr"] == "1"]
    p = [x for x in base if x["state"] == "passed" and x["build_state"] == "passed"]
    f = [x for x in base if x["state"] == "failed"]
    picks += [(wl, eng, x) for x in spread(p, N_PASS)] + [(wl, eng, x) for x in spread(f, N_FAIL)]

def grab(rx, s, cast=float, last=False):
    m = re.findall(rx, s, re.M)
    if not m: return None
    v = m[-1] if last else m[0]
    try: return cast(v)
    except Exception: return v

def parse(wl, s):
    d = {"vllm_version": grab(r"Pinned vLLM version: (\S+)", s, str),
         "sglang_version": grab(r"sglang[=-]=?([0-9][\w.]+)", s, str),
         "gpu_mem_mb": grab(r"Detected GPU memory: \d+GB \((\d+)MB\)", s, int),
         "fail_lines": [l.strip()[:200] for l in s.split("\n") if re.search(r"\bFAIL\b|FAILED|Traceback|Error:", l)][:8]}
    if wl == "vllm_bench":
        d["lmc_tp"] = grab(r"=== LMCache Results ===\n.*\n.*\n\s+total_token_throughput: " + F, s)
        d["base_tp"] = grab(r"=== Baseline Results ===\n.*\n.*\n\s+total_token_throughput: " + F, s)
        d["slowdown_pct"] = grab(r"Throughput: LMCache is " + F + r"% slower", s)
        d["seed"] = grab(r"Using random seed: (\d+)", s, int)
    elif wl == "long_doc_qa":
        for k in ("query_ttft_per_prompt", "query_round_time_per_prompt", "warmup_round_time_per_prompt"):
            m = re.search(r"^" + k + r"\s+" + F + r"\s+" + F + r"\s+" + F + "%", s, re.M)
            if m:
                d["base_" + k], d["lmc_" + k] = float(m.group(1)), float(m.group(2))
    else:
        for k in ("query_ttft_per_prompt", "query_round_time_per_prompt", "warmup_round_time_per_prompt"):
            m = re.search(r"^" + k + r" \(s\)\s+" + F + r"\s+" + F, s, re.M)
            if m:
                d["base_" + k], d["lmc_" + k] = float(m.group(1)), float(m.group(2))
        d["l2_query_speedup"] = grab(r"L2 query speedup: " + F + "x", s)
        d["l2_ttft_speedup"] = grab(r"L2 TTFT speedup: " + F + "x", s)
        d["warmup_overhead"] = grab(r"Warmup overhead: " + F + "x", s)
        d["reused_step5_baseline"] = "Reusing baseline from step 5" in s
    return d

def work(t):
    wl, eng, x = t
    rec = {k: x[k] for k in ("build_number", "build_state", "build_created", "job_id", "label", "state", "exit_status", "retried", "retries_count", "retry_type", "node", "transport")}
    rec.update(workload=wl, engine=eng)
    try:
        body, _ = bk_api.get(x["raw_log_url"], accept="text/plain", raw=True)
        s = ANSI.sub("", body.decode("utf-8", "replace")).replace("\r", "")
        rec.update(parse(wl, s))
    except Exception as e:
        rec["error"] = str(e)[:200]
    return rec

with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(work, picks))
os.makedirs(os.path.join(HERE, "raw"), exist_ok=True)
json.dump(out, open(os.path.join(HERE, "raw", "metrics.json"), "w"), indent=1)
print("jobs", len(out), "errors", sum(1 for r in out if "error" in r))
