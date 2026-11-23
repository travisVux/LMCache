"""Step 4: for up to N passed PR jobs per workload, download the raw log (in memory only),
extract marker timestamps, and save the extraction to raw/log_markers.json. Full logs are not kept."""
import csv, json, re, os, sys, random
from concurrent.futures import ThreadPoolExecutor, as_completed
import bk_api

N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
TS = re.compile(rb"\x1b_bk;t=(\d+)\x07")
FIRST = {  # first occurrence of each marker
    "env_ready": re.compile(r"Environment ready"),
    "launch": re.compile(r"=== Launching native processes ===|\[Phase 2 / Step 3\] Starting LMCache server"),
    "test_start": re.compile(r"=== Running test: |\[Phase 2 / Step 5\] Sending E2E test request"),
    "test_passed": re.compile(r"=== Test \S+ passed! ===|ALL .*PASSED|All .*validation.* passed", re.I),
    "cleanup": re.compile(r"=== Cleaning up background processes ===|\[Phase 3 / Step 12\] Cleaning up"),
}
WAIT = re.compile(r"is ready! \(took (\d+)s\)|ready on port \d+ \((\d+)s\)|Application startup complete")
PAIR_START = re.compile(r"Starting vLLM server\.\.\.|=== Launching vLLM servers ===|=== Probing ambient vLLM")
PAIR_READY = re.compile(r"vLLM server is ready|vLLM B is ready|Probe verdict:")
EVENT = re.compile(r"^(=== .{3,140} ===|--- .{3,100}|\[Phase .{3,100}|Probe verdict.*|.{0,60}(is ready|ready on port|startup complete).{0,60})$")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

def extract(body):
    out = {"first_ts": None, "last_ts": None, "waits": [], "pairs": [], "events": []}
    open_start = None
    for line in body.split(b"\n"):
        m = TS.search(line)
        if not m:
            continue
        t = int(m.group(1)) / 1000.0
        if out["first_ts"] is None:
            out["first_ts"] = t
        out["last_ts"] = t
        s = ANSI.sub("", TS.sub(b"", line).decode("utf-8", "replace"))
        for k, rx in FIRST.items():
            if k not in out and rx.search(s):
                out[k] = t
        if PAIR_START.search(s):
            open_start = t
        elif open_start is not None and PAIR_READY.search(s):
            out["pairs"].append([open_start, t]); open_start = None
        ss = s.strip()
        if len(out["events"]) < 1500 and EVENT.match(ss):
            out["events"].append([t, ss[:150]])
        w = WAIT.search(s)
        if w:
            secs = w.group(1) or w.group(2)
            out["waits"].append([t, int(secs) if secs else None, s.strip()[:120]])
    return out

def main():
    rows = [r for r in csv.DictReader(open("jobs_all_30d.csv", encoding="utf-8"))
            if r["is_pr"] == "1" and r["state"] == "passed" and r["raw_log_url"]
            and r["wall_min"] and float(r["wall_min"]) >= 1.0]  # skip adapter no-op jobs
    cache_path = "raw/log_markers.json"
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    random.seed(42)
    by_w = {}
    for r in rows:
        by_w.setdefault(r["workload"], []).append(r)
    todo = []
    for w, rs in sorted(by_w.items()):
        # round-robin over label variants (engine/mode/transport) so each gets coverage
        variants = {}
        for r in rs:
            variants.setdefault(r["label"], []).append(r)
        for v in variants.values():
            random.shuffle(v)
        pick, vs = [], list(variants.values())
        while len(pick) < N and any(vs):
            for v in vs:
                if v and len(pick) < N:
                    pick.append(v.pop())
        todo += pick
    need = [r for r in todo if r["job_id"] not in cache]
    print(f"sample {len(todo)} jobs, {len(need)} to fetch", flush=True)

    def work(r):
        body, _ = bk_api.get(r["raw_log_url"], accept="text/plain", raw=True)
        e = extract(body)
        e.update({k: r[k] for k in ("workload", "label", "engine", "mode", "transport", "build_number",
                                     "started_at", "finished_at", "wall_min", "gpus")})
        e["log_bytes"] = len(body)
        return r["job_id"], e

    done = 0
    with ThreadPoolExecutor(6) as ex:
        futs = [ex.submit(work, r) for r in need]
        for f in as_completed(futs):
            try:
                jid, e = f.result()
                cache[jid] = e
            except Exception as ex_:
                print("ERR", ex_, flush=True)
            done += 1
            if done % 20 == 0:
                json.dump(cache, open(cache_path, "w", encoding="utf-8"))
                print(f"{done}/{len(need)}", flush=True)
    json.dump(cache, open(cache_path, "w", encoding="utf-8"))
    print("saved", len(cache))

if __name__ == "__main__":
    main()
