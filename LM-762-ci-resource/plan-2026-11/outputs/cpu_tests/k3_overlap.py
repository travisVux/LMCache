import sys, re, json, collections
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "P1"))
import bk_api
"""Per-test overlap: Buildkite k3-unit-tests job log vs GHA job312.log (same commit). Edit BUILD / JOB for a new refresh."""
import os
S = os.path.dirname(os.path.abspath(__file__))
BUILD, JOB = "14829", "01a1b003-f6d6-44c7-8a16-94609e4567b9"
body, _ = bk_api.get(f"organizations/lmcache/pipelines/k3-unit-tests/builds/{BUILD}/jobs/{JOB}/log.txt", accept="text/plain", raw=True)
txt = body.decode("utf-8", "replace")
txt = re.sub(r"\x1b\[[0-9;]*[A-Za-z]|\x1b_bk;t=\d+\x07|_bk;t=\d+", "", txt)
open(S + f"/k3_{BUILD}.log", "w", encoding="utf-8").write(txt)

def results(lines):
    res = {}; pending = None
    L = re.compile(r"((?:tests|examples)/[\w./-]+\.py::.*?) (PASSED|SKIPPED|FAILED|XFAIL|XPASS|ERROR)(?: \(.*?\))?\s+\[")
    N = re.compile(r"((?:tests|examples)/[\w./-]+\.py::.*?)\s*$")
    T = re.compile(r"^\s*(?:\S+Z )?(PASSED|SKIPPED|FAILED|XFAIL|XPASS|ERROR)(?: \(.*?\))?\s+\[")
    for raw in lines:
        m = L.search(raw)
        if m: res[m.group(1)] = m.group(2); pending = None; continue
        t = T.search(raw)
        if t and pending: res[pending] = t.group(1); pending = None; continue
        n = N.search(raw)
        if n and "::" in n.group(1): pending = n.group(1)
    return res

k3 = results(txt.splitlines())
gha = results(open(S + "/job312.log", encoding="utf-8", errors="replace").read().splitlines())
ok = lambda d: {k for k, v in d.items() if v in ("PASSED", "XPASS", "XFAIL")}
sk = lambda d: {k for k, v in d.items() if v == "SKIPPED"}
kp, gp = ok(k3), ok(gha)
both = kp & gp
gha_only = gp - kp
k3_only = kp - gp
print("k3 passed", len(kp), "skipped", len(sk(k3)), "| gha passed", len(gp), "skipped", len(sk(gha)))
print("passed on BOTH", len(both), f"({100*len(both)/len(gp):.1f}% of GHA, {100*len(both)/len(kp):.1f}% of k3)")
print("GHA-only passed", len(gha_only), "| of those skipped on k3:", len(gha_only & sk(k3)), "| not present on k3:", len(gha_only - set(k3)))
print("k3-only passed", len(k3_only), "| of those deselected/absent on GHA:", len(k3_only - set(gha)), "| skipped on GHA:", len(k3_only & sk(gha)))
f = lambda s: collections.Counter(x.split("::")[0] for x in s).most_common(8)
print("GHA-only top files:", f(gha_only))
print("k3-only top files:", f(k3_only))
json.dump({"both": len(both), "gha_only": len(gha_only), "k3_only": len(k3_only), "gha_only_files": f(gha_only), "k3_only_files": f(k3_only)}, open(S + "/k3_overlap.json", "w"))
