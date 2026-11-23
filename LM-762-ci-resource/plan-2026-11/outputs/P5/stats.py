"""P5: summarize raw/metrics.json -> stdout (mean, stddev, CV, margins)."""
import json, os, statistics as st, collections
HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, "raw", "metrics.json")))
def s(v):
    v = [x for x in v if isinstance(x, (int, float))]
    if len(v) < 2: return f"n={len(v)}"
    m = st.mean(v); sd = st.stdev(v)
    return f"n={len(v)} mean={m:.4f} sd={sd:.4f} CV={100*sd/m:.1f}% min={min(v):.4f} max={max(v):.4f}"
G = collections.defaultdict(list)
for r in R: G[(r["workload"], r["engine"], r["state"])].append(r)
for k in sorted(G):
    rs = G[k]; wl = k[0]
    print("=====", k, "jobs", len(rs), "errs", sum("error" in r for r in rs),
          "vllm", collections.Counter(r.get("vllm_version") for r in rs).most_common(3),
          "nodes", len(set(r["node"] for r in rs)))
    if wl == "vllm_bench":
        print(" base_tp ", s([r.get("base_tp") for r in rs]))
        print(" lmc_tp  ", s([r.get("lmc_tp") for r in rs]))
        print(" slowdown", s([r.get("slowdown_pct") for r in rs]))
        rat = [r["lmc_tp"]/r["base_tp"] for r in rs if r.get("lmc_tp") and r.get("base_tp")]
        print(" lmc/base", s(rat))
        print(" slowdowns", sorted(round(r["slowdown_pct"],2) for r in rs if isinstance(r.get("slowdown_pct"),float)))
    else:
        for m in ("query_ttft_per_prompt", "query_round_time_per_prompt", "warmup_round_time_per_prompt"):
            print(" base", m, s([r.get("base_"+m) for r in rs]))
            print(" lmc ", m, s([r.get("lmc_"+m) for r in rs]))
        ok = [r for r in rs if r.get("lmc_query_ttft_per_prompt") and r.get("base_query_ttft_per_prompt")]
        if wl == "long_doc_qa":
            tt = sorted(round(100*(r["lmc_query_ttft_per_prompt"]/r["base_query_ttft_per_prompt"]-1),1) for r in ok)
            rt = sorted(round(100*(r["lmc_query_round_time_per_prompt"]/r["base_query_round_time_per_prompt"]-1),1) for r in ok)
            print(" ttft diff% ", tt); print(" round diff%", rt)
        else:
            for f in ("l2_query_speedup", "l2_ttft_speedup", "warmup_overhead"):
                print(" ", f, s([r.get(f) for r in rs]), sorted(r.get(f) for r in rs if isinstance(r.get(f), float)))
        # self-baseline: lmc query round / lmc warmup round ; base warmup vs lmc warmup
        sb = [r["lmc_query_round_time_per_prompt"]/r["lmc_warmup_round_time_per_prompt"] for r in ok if r.get("lmc_warmup_round_time_per_prompt")]
        print(" self lmc_query_round/lmc_warmup_round", s(sb))
        sw = [r["lmc_warmup_round_time_per_prompt"]/r["base_warmup_round_time_per_prompt"] for r in ok if r.get("base_warmup_round_time_per_prompt")]
        print(" lmc_warmup/base_warmup", s(sw))
    if k[2] == "failed":
        for r in rs:
            print("  F", r["build_number"], r["retries_count"], r["exit_status"], r.get("vllm_version"), [l for l in r.get("fail_lines", []) if "FAIL" in l][:3])
