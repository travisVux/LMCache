"""Parse CPU pytest CI log + test sources into per-file JSON."""
import ast, json, re, sys, os, collections
from datetime import datetime

S = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("LMCACHE_SRC", os.path.join(S, "src"))
LINE = re.compile(r"^(\S+Z) ([\w./-]+\.py::.*?) (PASSED|SKIPPED|FAILED|XFAIL|XPASS|ERROR)(?: \(.*?\))?\s+\[")
NODE = re.compile(r"^(\S+Z) ([\w./-]+\.py::.*?)\s*$")
STAT = re.compile(r"^(\S+Z) (PASSED|SKIPPED|FAILED|XFAIL|XPASS|ERROR)(?: \(.*?\))?\s+\[")

def ts(s):
    return datetime.strptime(s[:26], "%Y-%m-%dT%H:%M:%S.%f")

files = collections.OrderedDict()
prev = None
pending = None
for raw in open(os.environ.get("CI_LOG", os.path.join(S, "job312.log")), encoding="utf-8", errors="replace"):
    m = LINE.match(raw)
    if not m:
        n = NODE.match(raw)
        if n:
            pending = n.group(2); continue
        st_ = STAT.match(raw)
        if st_ and pending:
            class M:
                pass
            m = M(); g = (None, st_.group(1), pending, st_.group(2)); m.group = lambda i, g=g: g[i]; pending = None
    if not m:
        if prev is None and "test session starts" in raw:
            prev = ts(raw.split(" ", 1)[0])
        continue
    t, node, st = ts(m.group(1)), m.group(2), m.group(3)
    dur = (t - prev).total_seconds() if prev else 0.0
    prev = t
    path, _, rest = node.partition("::")
    func = re.sub(r"\[.*$", "", rest)
    f = files.setdefault(path, {"pass": 0, "skip": 0, "fail": 0, "secs": 0.0, "funcs": collections.Counter(), "fsk": collections.Counter()})
    f["pass" if st in ("PASSED", "XPASS", "XFAIL") else "skip" if st == "SKIPPED" else "fail"] += 1
    f["secs"] += dur
    f["funcs"][func] += 1
    if st == "SKIPPED":
        f["fsk"][func] += 1

def first_para(doc, n=320):
    if not doc:
        return ""
    p = doc.strip().split("\n\n")[0]
    p = " ".join(x.strip() for x in p.splitlines())
    return p[:n] + ("…" if len(p) > n else "")

SIGNALS = [
    ("mock", r"\bunittest\.mock\b|\bMagicMock\b|\bmock\.patch\b|\bmocker\b"),
    ("monkeypatch", r"\bmonkeypatch\b"),
    ("tmp files", r"\btmp_path\b|\btmpdir\b|tempfile"),
    ("subprocess", r"\bsubprocess\b|\bPopen\b"),
    ("multiprocessing", r"\bmultiprocessing\b|mp\.Process|get_context\("),
    ("threads", r"\bthreading\b|ThreadPoolExecutor"),
    ("asyncio", r"\basyncio\b|pytest\.mark\.asyncio|anyio"),
    ("ZMQ socket", r"\bzmq\b"),
    ("gRPC", r"\bgrpc\b"),
    ("HTTP client", r"TestClient|httpx|aiohttp|requests\.(get|post|put|delete|Session)\b|urllib\.request"),
    ("torch CPU tensors", r"\btorch\."),
    ("vLLM import", r"from vllm|import vllm"),
    ("SGLang import", r"from sglang|import sglang"),
    ("fake / stub objects", r"[Ff]ake[A-Z]\w*|[Ss]tub[A-Z]\w*|Dummy[A-Z]\w*"),
    ("shared memory", r"shared_memory|SharedMemory|/dev/shm|shm_"),
    ("redis / fakeredis", r"fakeredis|\bredis\b"),
    ("free port", r"free_port|find_free_port|get_open_port|socket\.socket"),
    ("parametrize", r"pytest\.mark\.parametrize"),
    ("CliRunner / argv", r"CliRunner|main\(\[|sys\.argv|argparse"),
]

out = []
for path, f in files.items():
    src_path = os.path.join(SRC, path.replace("/", os.sep))
    mod_doc, fdocs, cdocs, sig, loc = "", {}, {}, [], 0
    try:
        code = open(src_path, encoding="utf-8").read()
        loc = code.count("\n")
        tree = ast.parse(code)
        mod_doc = first_para(ast.get_docstring(tree))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                cdocs[node.name] = first_para(ast.get_docstring(node), 200)
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        fdocs[f"{node.name}::{sub.name}"] = first_para(ast.get_docstring(sub), 200)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fdocs[node.name] = first_para(ast.get_docstring(node), 200)
        sig = [name for name, rx in SIGNALS if re.search(rx, code)]
    except Exception as e:  # noqa
        sig = ["(source not found)"]
    tests = []
    for fn, cnt in f["funcs"].items():
        tests.append([fn, cnt, f["fsk"].get(fn, 0), fdocs.get(fn, "")])
    out.append({
        "path": path, "pass": f["pass"], "skip": f["skip"], "fail": f["fail"],
        "secs": round(f["secs"], 1), "loc": loc, "doc": mod_doc,
        "classes": {k: v for k, v in cdocs.items() if v}, "setup": sig, "tests": tests,
    })

# test files in tree that produced no result (fully deselected / ignored)
seen = set(files)
missing = []
for root, _, fs in os.walk(os.path.join(SRC, "tests")):
    for fn in fs:
        if fn.startswith("test_") and fn.endswith(".py"):
            rel = os.path.relpath(os.path.join(root, fn), SRC).replace(os.sep, "/")
            if rel not in seen:
                code = open(os.path.join(root, fn), encoding="utf-8", errors="replace").read()
                marks = sorted(set(re.findall(r"pytest\.mark\.(cuda|xpu|musa|npu|neuron|rbln|supa)", code)))
                why = ("marker: " + ",".join(marks)) if marks else ""
                if not why and re.search(r"importorskip|skipif", code):
                    why = "module skip"
                missing.append({"path": rel, "why": why or "not collected", "doc": first_para(ast.get_docstring(ast.parse(code)) if code else "", 200) if True else ""})

json.dump({"files": out, "notrun": missing}, open(os.path.join(S, "cpu_tests.json"), "w", encoding="utf-8"), ensure_ascii=False)
tot = lambda k: sum(x[k] for x in out)
print("files", len(out), "pass", tot("pass"), "skip", tot("skip"), "fail", tot("fail"), "secs", round(tot("secs")), "funcs", sum(len(x["tests"]) for x in out), "notrun", len(missing))
nodoc = sum(1 for x in out if not x["doc"])
print("files without module docstring", nodoc)
