"""Step 1c: evidence for retry causes. For every PR job attempt that failed and was retried (Buildkite 'retried' flag),
and every failed job of a failed PR build that was followed by another build of the same commit,
download the last 400 KB of its log (HTTP Range, in memory only), match known failure signatures, and keep only the
matched line. Writes raw/fail_signatures.json {job_id: {sig, cls, line}}. Full logs are never stored.

  python -I -X utf8 outputs/P1/sample_fail_logs.py

cls is one of:
  infra   - the log shows an infrastructure cause (network, GPU not free, agent / pod lost, disk, registry)
  test    - the log shows a test assertion, a failed test, or a missed performance threshold (timing-sensitive),
            and no infrastructure signature
  config  - the job could not run its test at all (missing script, bad argument): a code / config error
  unknown - no signature matched (also when the log could not be read)
Only the failure region is searched (the 120 lines before the last agent error line); signatures are tried in SIGS order.
A re-run keeps earlier results and only retries jobs whose log could not be read, so the file is stable."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import csv, json, re, urllib.request
from concurrent.futures import ThreadPoolExecutor
import bk_api

HERE = _os.path.dirname(_os.path.abspath(__file__))
SIGS = [  # (signature id, class, regex) in priority order: the first signature found in the failure region wins
    ("git", "infra", r"Checkout failed|cloning git repository|Permission denied \(publickey\)|fatal: (could not read|the remote end hung up|early EOF)|error: RPC failed"),
    ("gpu_not_free", "infra", r"No suitable GPU found|Timeout: No suitable GPU"),
    ("network", "infra", r"Could not resolve host|Temporary failure in name resolution|Connection reset by peer|TLS handshake timeout|HTTP Error 5\d\d|"
                         r"50[234] (Bad Gateway|Service Unavailable|Gateway Time)|fatal: unable to access|RemoteDisconnected|429 Too Many Requests"),
    ("disk", "infra", r"No space left on device"),
    ("registry", "infra", r"toomanyrequests|ImagePull|manifest unknown|Error response from daemon"),
    ("gpu_memory", "infra", r"CUDA out of memory|OutOfMemoryError|CUDA error: out of memory|cudaErrorMemoryAllocation"),
    ("agent_lost", "infra", r"agent (was )?lost|Agent lost|The agent .* disconnected|pod .*(evicted|deleted)"),
    ("not_implemented", "config", r"is not implemented for|No such file or directory: .*\.sh|command not found"),
    ("perf_threshold", "test", r"Threshold verification FAILED|need >= .*-- FAIL|slower \(max allowed|Verification failed"),
    ("test_assert", "test", r"FAILED tests/|AssertionError|=+ \d+ failed|Expected .* got"),
    ("interrupted", "infra", r"interrupted by a signal|signal: terminated"),
    ("engine_start", "unknown", r"(Timed out|Timeout) waiting for .*(server|vLLM|SGLang|ready)|server (failed|did not) start|failed to start"),
    ("test_failed", "test", r"\btest failed\s*$|=== Test \S+ failed|\bTest FAILED\b"),
]
RX = [(a, c, re.compile(x)) for a, c, x in SIGS]
END = re.compile(r"Error: |exited with status|interrupted by a signal")
CLEAN = re.compile(rb"\x1b_bk;t=\d+\x07|\x1b\[[0-9;]*[A-Za-z]")


def tail(url, n=400000):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + bk_api._token(), "Range": f"bytes=-{n}", "User-Agent": "CacheAgent-P1"})
    for i in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return CLEAN.sub(b"", r.read()).decode("utf-8", "replace")
        except Exception:
            import time; time.sleep(4 * (i + 1))
            continue
    return None


def classify(row):
    t = tail(row["raw_log_url"]) if row["raw_log_url"] else None
    if t is None:
        return row["job_id"], dict(sig="no_log", cls="unknown", line="")
    # failure region: the 120 lines before the last agent error line (artifact upload lines dropped)
    lines = [ln for ln in t.splitlines() if ln.strip() and "Uploading" not in ln and "artifact" not in ln]
    ends = [i for i, ln in enumerate(lines) if END.search(ln)]
    e = ends[-1] if ends else len(lines) - 1
    region = lines[max(0, e - 120):e + 1]
    for sig, cls, rx in RX:
        hit = [ln for ln in region if rx.search(ln)]
        if hit:
            return row["job_id"], dict(sig=sig, cls=cls, line=hit[-1].strip()[:200])
    return row["job_id"], dict(sig="none", cls="unknown", line="")


def main():
    allr = list(csv.DictReader(open(_os.path.join(HERE, "jobs_all_30d.csv"), encoding="utf-8")))
    rows = [r for r in allr if r["retried"] == "True" and r["is_pr"] == "1"]
    # plus: failed jobs of a failed PR build that was followed by another build of the same commit
    seq = {}
    for r in allr:
        if r["is_pr"] == "1" and r["commit"]:
            seq.setdefault((r["pipeline"], r["commit"]), {})[r["build_number"]] = (r["build_created"], r["build_state"])
    nxt = set()
    for (pl, sha), bs in seq.items():
        order = sorted(bs.items(), key=lambda kv: kv[1][0])
        nxt |= {(pl, n) for (n, (c, st)), _ in zip(order, order[1:]) if st == "failed"}
    rows += [r for r in allr if (r["pipeline"], r["build_number"]) in nxt and r["state"] in ("failed", "timed_out") and r["retried"] != "True"]
    print("retried PR job attempts:", len(rows), flush=True)
    fn = _os.path.join(HERE, "raw", "fail_signatures.json")
    old = json.load(open(fn, encoding="utf-8")) if _os.path.exists(fn) and "--fresh" not in _sys.argv else {}
    todo = [r for r in rows if (old.get(r["job_id"]) or {}).get("sig") in (None, "no_log")]
    print("to read:", len(todo), flush=True)
    with ThreadPoolExecutor(8) as ex:
        out = {r["job_id"]: old[r["job_id"]] for r in rows if r["job_id"] in old}
        out.update(dict(ex.map(classify, todo)))
    json.dump(out, open(fn, "w", encoding="utf-8"), indent=0)
    import collections
    print(collections.Counter((v["cls"], v["sig"]) for v in out.values()).most_common())


if __name__ == "__main__":
    main()
