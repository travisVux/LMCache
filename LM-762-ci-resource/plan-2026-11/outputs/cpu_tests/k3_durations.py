"""Time per test in k3-unit-tests, split by "also passes on GHA CPU" vs "k3-only".

Input : k3_<BUILD>.raw.log (Buildkite log with `_bk;t=<ms>` line timestamps; fetched if missing)
        job312.log (GHA CPU job, same commit) -> which tests are CPU-portable
Output: k3_durations.json + a short print.

Time of one test = timestamp of the next test line - timestamp of its own line
(includes setup / teardown / fixtures, so the sum equals pytest wall time).

  python -I -X utf8 k3_durations.py
"""
import collections
import json
import os
import re
import sys

S = os.path.dirname(os.path.abspath(__file__))
BUILD, JOB = "14829", "01a1b003-f6d6-44c7-8a16-94609e4567b9"
RAW = os.path.join(S, f"k3_{BUILD}.raw.log")

if not os.path.exists(RAW):
    sys.path.insert(0, os.path.join(S, "..", "P1"))
    import bk_api
    body, _ = bk_api.get(f"organizations/lmcache/pipelines/k3-unit-tests/builds/{BUILD}/jobs/{JOB}/log.txt", accept="text/plain", raw=True)
    open(RAW, "wb").write(body)

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TS = re.compile(r"\x1b_bk;t=(\d+)\x07")
TEST = re.compile(r"((?:tests|examples)/[\w./-]+\.py::\S.*?) (PASSED|SKIPPED|FAILED|XFAIL|XPASS|ERROR)")
NAME = re.compile(r"((?:tests|examples)/[\w./-]+\.py::\S+)")
STATE = re.compile(r"\b(PASSED|SKIPPED|FAILED|XFAIL|XPASS|ERROR)\b")

raw = open(RAW, encoding="utf-8", errors="replace").read()
events = []  # (ts_ms, test, state)
first_ts = last_ts = None
cur_ts = None
pending = None
for line in raw.split("\n"):
    m = TS.search(line)
    if m:
        cur_ts = int(m.group(1))
        first_ts = first_ts or cur_ts
        last_ts = cur_ts
    clean = ANSI.sub("", TS.sub("", line))
    t = TEST.search(clean)
    if t:
        events.append([cur_ts, t.group(1), t.group(2)]); pending = None; continue
    n = NAME.search(clean)
    if n and not STATE.search(clean):
        pending = [cur_ts, n.group(1)]; continue
    s = STATE.match(clean.strip())
    if s and pending:
        events.append([pending[0], pending[1], s.group(1)]); pending = None

# pytest end = the "== N passed ... in Xs ==" summary line
end_ts = None
for line in raw.split("\n"):
    if re.search(r"=+ .*\d+ passed.* in [\d.]+s", ANSI.sub("", line)):
        m = TS.search(line)
        end_ts = int(m.group(1)) if m else None
end_ts = end_ts or last_ts

dur = {}
for i, (ts, name, st) in enumerate(events):
    nxt = events[i + 1][0] if i + 1 < len(events) else end_ts
    dur[name] = (max(0, (nxt - ts)) / 1000.0, st)


def gha_results(path):
    res = {}; pend = None
    L = re.compile(r"((?:tests|examples)/[\w./-]+\.py::.*?) (PASSED|SKIPPED|FAILED|XFAIL|XPASS|ERROR)(?: \(.*?\))?\s+\[")
    N = re.compile(r"((?:tests|examples)/[\w./-]+\.py::.*?)\s*$")
    T = re.compile(r"^\s*(?:\S+Z )?(PASSED|SKIPPED|FAILED|XFAIL|XPASS|ERROR)(?: \(.*?\))?\s+\[")
    for r in open(path, encoding="utf-8", errors="replace"):
        m = L.search(r)
        if m: res[m.group(1)] = m.group(2); pend = None; continue
        t = T.search(r)
        if t and pend: res[pend] = t.group(1); pend = None; continue
        n = N.search(r)
        if n and "::" in n.group(1): pend = n.group(1)
    return res


OK = ("PASSED", "XPASS", "XFAIL")
gha = gha_results(os.path.join(S, "job312.log"))
gha_ok = {k for k, v in gha.items() if v in OK}

buckets = collections.defaultdict(lambda: [0, 0.0])  # name -> [count, seconds]
by_file = collections.defaultdict(lambda: collections.defaultdict(float))
for name, (sec, st) in dur.items():
    if st in OK:
        b = "cpu_portable" if name in gha_ok else "k3_only"
    elif st == "SKIPPED":
        b = "skipped"
    else:
        b = "failed"
    buckets[b][0] += 1; buckets[b][1] += sec
    by_file[b][name.split("::")[0]] += sec

pytest_s = (end_ts - events[0][0]) / 1000.0 if events else 0
job_s = (last_ts - first_ts) / 1000.0
tot = sum(v[1] for v in buckets.values())
out = dict(
    build=BUILD, job=JOB,
    job_wall_s=round(job_s), pytest_wall_s=round(pytest_s), setup_s=round(job_s - pytest_s),
    tests_timed=len(dur),
    buckets={k: dict(tests=v[0], seconds=round(v[1]), share_of_pytest=round(v[1] / tot, 4) if tot else 0) for k, v in buckets.items()},
    top_files={k: [[f, round(s)] for f, s in sorted(d.items(), key=lambda x: -x[1])[:12]] for k, d in by_file.items()},
    top_tests=[[n, round(s, 1), st] for n, (s, st) in sorted(dur.items(), key=lambda x: -x[1][0])[:25]],
)
json.dump(out, open(os.path.join(S, "k3_durations.json"), "w"), indent=1)
print(f"job {job_s/60:.1f} min = setup {(job_s-pytest_s)/60:.1f} + pytest {pytest_s/60:.1f} | tests timed {len(dur)}")
for k, v in sorted(buckets.items(), key=lambda x: -x[1][1]):
    print(f"  {k:13s} {v[0]:6d} tests  {v[1]/60:6.1f} min  {100*v[1]/tot:5.1f}% of pytest")
for k in ("cpu_portable", "k3_only"):
    print(k, "top files:", out["top_files"].get(k, [])[:5])
