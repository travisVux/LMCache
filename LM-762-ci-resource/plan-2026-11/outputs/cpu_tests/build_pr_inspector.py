"""PR Inspector: one drawer for every single-PR detail (2026-11-24, phase A of the PR Inspector plan).

Click a PR number (any [data-ent^="pr:"] link, a [data-pi] button) or a feature chip in a PR row, anywhere in the page.

Two directions:
  Forward   PR -> files / functions -> code areas -> features (F-ids, DRAFT map) -> CI gates (required / conditional / at risk)
  Backward  failing CI run / bug signature / dev regression -> builds -> PR, commit -> feature -> edited functions
Exactly 5 views, each = findings with evidence (file, test, CI run, PR) or "unknown", a reviewer checklist and the gates
that cover it:  1 feature.internal  2 among features  3 flaky & non-deterministic risk  4 race & concurrency
                5 semantic conflict (open PRs, merges of the last 24 h, invariants)

Data (all local, no network):
  entities.json (PR, feature, test, build, bug nodes + edges), overlap_patches.json (patches of open PRs),
  ops_tabs.json (24 h overlap groups, review queue gates, known flaky workloads, critical path + F01-F17),
  gates.py (tiers, change classes), P1*/retry_events_30d.csv, ops-app/data/ops.db (dev builds, read-only),
  third_party/LMCache clone (diffs of merged PRs via `git show`, static scan of the files at HEAD).
Output: pr_inspector.json (also embedded as <script id="piData">), pr_inspector_cache.json (git diffs by sha).

Run inside the build chain (build_page.py) after build_pr_map.py, before build_i18n.py. Plain JS + JSDoc, no toolchain.
"""
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gates  # noqa: E402
import build_ops_tabs as BOT  # noqa: E402  (src_area, parse_hunks: same rules as tab 6A)

PAGE = str(Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
CLONE = Path(__file__).resolve().parents[4] / "third_party" / "LMCache"
OPSDB = Path(__file__).resolve().parents[3] / "ops-app" / "data" / "ops.db"
OUT = os.path.join(HERE, "pr_inspector.json")
CACHE = os.path.join(HERE, "pr_inspector_cache.json")
REQUIRED = ["DCO", "Check code quality", "k3-unit-tests", "k3-multiprocess-test"]   # report_model.REQUIRED_CHECKS (branch protection, 2026-11-09)
MAX_FILES, MAX_FUNCS = 60, 10

CONC = [("lock", r"\b(?:R?Lock|Semaphore|BoundedSemaphore|Condition|Barrier)\(|std::mutex|lock_guard|unique_lock"),
        ("thread", r"\bthreading\.|\bThread\(|ThreadPoolExecutor|concurrent\.futures|daemon=True"),
        ("async", r"\basync def\b|\bawait\b|asyncio\.(?:gather|create_task|Lock|Event|Queue|wait_for|run)"),
        ("process", r"\bmultiprocessing\b|ProcessPoolExecutor|\bmp\.Process\b|shared_memory|SharedMemory"),
        ("queue", r"\bqueue\.(?:Queue|SimpleQueue)|\bQueue\(\)"),
        ("event", r"threading\.Event\(|\.wait\(timeout|\.set\(\)\s*$"),
        ("cuda_stream", r"cuda\.Stream\(|torch\.cuda\.synchronize|record_stream|cuda\.Event\(|wait_stream|\.synchronize\(\)"),
        ("atomic", r"std::atomic|\batomic\b")]
NONDET = [("sleep", r"\btime\.sleep\(|asyncio\.sleep\("),
          ("clock", r"\btime\.time\(|datetime\.now\(|datetime\.utcnow\("),   # monotonic / perf_counter = timing, not a risk (review M5)
          ("random", r"\brandom\.(?!Random\(\w)\w+\(|np\.random\.(?!default_rng\(\w|seed\()|torch\.rand|uuid\.uuid4|secrets\."),
          ("timeout", r"\btimeout\s*=\s*[\d.]+"),
          ("port", r"\bport\s*=\s*\d{3,5}\b|\.bind\(\(|socket\.socket\("),
          ("env", r"os\.environ(?:\.get)?\["),
          ("set_order", r"\bfor \w+ in (?:set\(|\{)"),
          ("gc", r"\bgc\.collect\(")]
CONC_RX = [(k, re.compile(r)) for k, r in CONC]
NONDET_RX = [(k, re.compile(r)) for k, r in NONDET]
DEF_RX = re.compile(r"^(\s*)(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)")
PRNUM_RX = re.compile(r"\(#(\d{3,5})\)")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def clone_text(path):
    """(text, ref) of a file of the local clone: origin/dev first (fresh after the refresh's git fetch), else the working tree."""
    t = git("show", f"origin/dev:{path}")
    if t:
        return t, "origin/dev"
    fp = CLONE / path
    return (fp.read_text(encoding="utf-8", errors="replace"), "HEAD") if fp.is_file() else ("", None)


def git(*args, timeout=60):
    try:
        r = subprocess.run(["git", "-C", str(CLONE), *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def split_diff(text):
    """`git show -U0` output -> [(path, status, patch)]."""
    out, cur = [], None
    for ln in text.splitlines():
        if ln.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*?) b/(.*)$", ln)
            cur = [m.group(2) if m else ln[11:], "modified", []]
            out.append(cur)
        elif cur is None:
            continue
        elif ln.startswith("new file mode"):
            cur[1] = "added"
        elif ln.startswith("deleted file mode"):
            cur[1] = "removed"
        elif ln.startswith("rename from"):
            cur[1] = "renamed"
        elif ln.startswith(("@@", "+", "-", " ")) and not ln.startswith(("+++", "---")):
            cur[2].append(ln)
    return [(p, s, "\n".join(b)) for p, s, b in out]


def file_rec(path, status, patch):
    """One changed file -> [path, status, added, removed, funcs, classes, area, first_new_line]."""
    hunks = BOT.parse_hunks(patch or "")
    funcs, classes, add, rem = [], [], 0, 0
    for h in hunks:
        add += len(h["add"]); rem += len(h["rem"])
        for f in sorted(h["funcs"]):
            if f not in funcs:
                funcs.append(f)
        for c in sorted(h["classes"]):
            if c not in classes:
                classes.append(c)
    m = re.search(r"^@@ -\d+(?:,\d+)? \+(\d+)", patch or "", re.M)
    area = "tests" if path.startswith("tests/") else BOT.src_area(path)
    return [path, status, add, rem, funcs[:MAX_FUNCS], classes[:4], area, int(m.group(1)) if m else 0, added_hits(path, patch)]


def added_hits(path, patch):
    """Expert review round 2 (F4): concurrency / non-determinism matches in the lines this PR ADDS (patch '+' lines),
    with their new line numbers. None = no patch text (then the page falls back to the file at HEAD and says so)."""
    if not patch:
        return None
    if not path.endswith((".py", ".pyx", ".cu", ".cpp", ".cc", ".h", ".hpp", ".rs")):
        return []
    hits, ln = [], 0
    for x in patch.splitlines():
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", x)
        if m:
            ln = int(m.group(1))
            continue
        if x.startswith("+") and not x.startswith("+++"):
            code = x[1:]
            code = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', code)       # string literals out
            code = re.sub(r"#.*$" if path.endswith((".py", ".pyx")) else r"//.*$", "", code)
            if code.strip():
                for cat, rxs in (("c", CONC_RX), ("n", NONDET_RX)):
                    for k, rx in rxs:
                        if rx.search(code):
                            hits.append([cat, k, ln, ""])
                            break
            ln += 1
        elif not x.startswith("-"):
            ln += 1
    return hits[:20]


def code_only(text, suffix):
    """The file with comments and string literals (docstrings included) blanked, line numbers kept (review M5)."""
    if suffix in (".py", ".pyx"):
        import io
        import tokenize
        lines = text.splitlines()
        out = [list(ln) for ln in lines]
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type in (tokenize.COMMENT, tokenize.STRING) or tok.type == getattr(tokenize, "FSTRING_MIDDLE", -1):
                    (r0, c0), (r1, c1) = tok.start, tok.end
                    for r in range(r0, r1 + 1):
                        if r - 1 >= len(out):
                            break
                        a = c0 if r == r0 else 0
                        b = c1 if r == r1 else len(out[r - 1])
                        for c in range(a, min(b, len(out[r - 1]))):
                            out[r - 1][c] = " "
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return lines
        return ["".join(x) for x in out]
    t = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    t = re.sub(r"//[^\n]*", "", t)
    t = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', t)
    return t.splitlines()


def codeowners():
    """[(regex, [owners])] from .github/CODEOWNERS of the clone; the last matching rule wins (GitHub rules). Review m4."""
    f = CLONE / ".github" / "CODEOWNERS"
    rules = []
    if not f.is_file():
        return rules
    for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        pat, *own = ln.split()
        rx = re.escape(pat.lstrip("/")).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        rx = ("^" if pat.startswith("/") else "(^|/)") + rx + ("" if pat.endswith("/") else "($|/)")
        rules.append((re.compile(rx), own))
    return rules


def owners_of(paths, rules):
    out = []
    for pth in paths:
        hit = None
        for rx, own in rules:
            if rx.search(pth):
                hit = own
        for o in hit or []:
            if o not in out:
                out.append(o)
    return out[:24]   # round 2 F9: no silent cut at 6 (13 owners on some PRs); the page lists them all


def scan_file(path, cache):
    """Static scan of the file at the clone HEAD: concurrency (c) and non-determinism (n) lines, with the function they sit in.
    Heuristic: text match on code with comments and strings removed."""
    if path in cache:
        return cache[path]
    fp = CLONE / path
    res = None
    # origin/dev first (fresh after the refresh's git fetch), the working tree only without it: same ref as `head`
    if fp.suffix in (".py", ".pyx", ".cu", ".cpp", ".cc", ".h", ".hpp", ".rs") and (raw := clone_text(path)[0]):
        lines, code = raw.splitlines(), code_only(raw, fp.suffix)
        hits, defs, stack = [], {}, []
        for i, ln in enumerate(lines, 1):
            d = DEF_RX.match(ln)
            if d:
                ind = len(d.group(1))
                while stack and stack[-1][0] >= ind:
                    stack.pop()
                stack.append((ind, d.group(3)))
                defs.setdefault(d.group(3), i)
            elif ln.strip() and not ln.lstrip().startswith(("#", ")", "]", "}", '"', "'")) and stack:
                ind = len(ln) - len(ln.lstrip())   # a statement at or left of a def's indent closes it (brackets / strings do not)
                while stack and stack[-1][0] >= ind:
                    stack.pop()
            fn = stack[-1][1] if stack else ""
            if ln.lstrip().startswith("#"):
                continue
            cl = code[i - 1] if i - 1 < len(code) else ln
            for cat, rxs in (("c", CONC_RX), ("n", NONDET_RX)):
                for k, rx in rxs:
                    if rx.search(cl):
                        hits.append([cat, k, i, fn])
                        break
        res = {"h": hits[:60], "nh": len(hits), "d": defs}
    cache[path] = res
    return res


def main():
    made = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    E = load(os.path.join(HERE, "entities.json"), {})
    nodes, edges = E.get("nodes", {}), E.get("edges", [])
    OT = load(os.path.join(HERE, "ops_tabs.json"), {})
    OP = load(os.path.join(HERE, "overlap_patches.json"), {})
    cache = load(CACHE, {})
    git_cache = cache.setdefault("git", {})
    # the commit every scan and diff of this page reads: origin/dev (refreshed by git fetch), else the checked-out HEAD
    ref = "origin/dev" if git("rev-parse", "--verify", "--quiet", "origin/dev").strip() else "HEAD"
    head = git("rev-parse", ref).strip()
    head_at = git("log", "-1", "--format=%cI", ref).strip()
    if head_at:
        head_at = datetime.fromisoformat(head_at).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    out_e, in_e = defaultdict(list), defaultdict(list)
    for e in edges:
        out_e[e["from"]].append(e); in_e[e["to"]].append(e)

    # ---------------------------------------------------------------- shared tables
    cp = ((OT.get("coming") or {}).get("nr") or {}).get("cp") or {}
    feats = {f["id"]: {k: f.get(k) for k in ("name", "step", "dep", "crit", "risk", "gate", "cpu", "gpu")} for f in cp.get("features") or []}
    area_f = cp.get("area_f") or {}
    journeys = [dict(id=j["id"], name=j.get("name"), steps=j.get("steps") or [], f=(cp.get("node_f") or {}).get(j["id"]) or [])
                for j in cp.get("journeys") or []]
    # gate = the CI job that runs a tier TODAY. Proposed MP tiers (L2, L3, LS, AO, FULL) have no job of their own yet: their
    # workloads run inside k3-multiprocess-test (all-or-nothing for code changes, gates.py JOBS); CE runs there too.
    def job_of(t):
        j = t.get("job") or ""
        return "k3-multiprocess-test" if ("k3-multiprocess-test" in j or (not j and t["id"] in ("L2", "CE", "L3", "LS", "AO", "FULL"))) else j or t["id"]
    tiers = {t["id"]: dict(name=t.get("name"), job=job_of(t), req=job_of(t) in REQUIRED, wl=gates.TIER_WORKLOADS.get(t["id"]) or [],
                           plain=list(t.get("plain") or []))   # review P2-13: plain words of L0 / L1 / ... for the tooltips
             for t in gates.TIERS}
    classes = {c["id"]: dict(paths=c["paths"], tiers=c["tiers"]) for c in gates.CLASSES}
    ov = OT.get("overlap") or {}
    review = ov.get("review") or {}
    rev_by = {}
    for grp in ("queue", "running"):
        for x in review.get(grp) or []:
            rev_by[str(x.get("num"))] = dict(sub=x.get("sub") or grp, g=x.get("gates") or {}, level=x.get("level"))

    # areas: feature nodes, F-ids (DRAFT), change class, tests covering them
    areas, area_open = {}, defaultdict(list)
    for k, n in nodes.items():
        if n.get("kind") != "feature":
            continue
        a = n["id"]
        tests = [e["to"] for e in out_e[k] if e["rel"] == "covered_by"]
        areas[a] = dict(t=n.get("title"), F=area_f.get(a) or [], cls=gates.AREA_CLASS.get(a, "core"), st=n.get("status"),
                        nt=len(tests), tests=tests)
    for k, n in nodes.items():
        if n.get("kind") == "pr" and n.get("state") == "open":
            for e in out_e[k]:
                if e["rel"] == "changes":
                    area_open[e["to"].split(":", 1)[1]].append(int(n["id"]))

    # ---------------------------------------------------------------- per PR
    patches = OP.get("prs") or {}
    retry = defaultdict(list)
    import baseline   # the same retry events as the CI Baseline tab (one folder: no overlap, no double count)
    for d in (baseline.pick(),):
        p = os.path.join(HERE, "..", d, "retry_events_30d.csv")
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8")):
                if r.get("pr"):
                    retry[r["pr"]].append([r["pipeline"], r["step"], r["cls"], r.get("evidence_line") or r.get("evidence") or "",
                                           r["link"], r.get("lost_gpu_min") or r.get("lost_min"), r.get("then"), d])
    groups = {str(g["p"]): g for g in ov.get("groups") or []}
    # required checks on the head commit of open PRs, from the observe snapshot (prs_gql statusCheckRollup)
    snap_ck = {}
    SNAP = load(os.path.join(HERE, "observe_snapshot.json"), {})
    # One vocabulary for check states (review 2026-11-26, P0-1), shared with the drawer (window.PI.stateWord):
    #   ok      SUCCESS, and SKIPPED / NEUTRAL (a skipped job does not block the merge)
    #   fail    FAILURE, ERROR, TIMED_OUT, ACTION_REQUIRED, STARTUP_FAILURE
    #   cancel  CANCELLED, STALE (re-run it)
    #   running PENDING, EXPECTED, QUEUED / IN_PROGRESS / WAITING (not completed)
    #   missing a required check that never reported on the head commit (ready PR)
    #   label   k3-multiprocess-test never reported and the PR has none of its trigger labels (BOT.LABEL_TRIGGERED)
    #   draft   draft PR: k3-unit-tests and the MP pipelines build ready commits only (#6730 / #6731)
    #   bypass  k3-multiprocess-test passed in < 60 s: the #6731 bypass (heavy suite skipped), not a real MP run
    # A check name that appears more than once on the head commit takes its WORST state.
    CK = {"DCO": "dco", "Check code quality": "quality", "buildkite/k3-unit-tests": "unit", "buildkite/k3-multiprocess-test": "mp",
          "buildkite/k3-multiprocess-smoke": "smoke"}
    REQ_KEYS = ("dco", "quality", "unit", "mp")   # branch protection of dev (REQUIRED); smoke is tracked, not required yet
    SEV = {"fail": 7, "cancel": 6, "running": 5, "missing": 4, "label": 3, "draft": 2, "bypass": 1, "ok": 0}
    MP_TRIGGER = next((v for k, v in BOT.LABEL_TRIGGERED.items() if k.endswith("k3-multiprocess-test")), ("full",))
    MP_TRIGGER = set(MP_TRIGGER if isinstance(MP_TRIGGER, (tuple, list)) else (MP_TRIGGER,))
    BYPASS_S = 60

    def ck_state(c):
        if c.get("__typename") == "StatusContext" or ("context" in c and "name" not in c):
            s = (c.get("state") or "").upper()
            return {"SUCCESS": "ok", "FAILURE": "fail", "ERROR": "fail", "PENDING": "running", "EXPECTED": "running"}.get(s, "running")
        st, co = (c.get("status") or "").upper(), (c.get("conclusion") or "").upper()
        if st and st != "COMPLETED":
            return "running"
        if not co:
            return "running"
        return {"SUCCESS": "ok", "NEUTRAL": "ok", "SKIPPED": "ok", "CANCELLED": "cancel", "STALE": "cancel"}.get(co, "fail")

    # timing of k3-multiprocess-test builds (the snapshot keeps no start / finish time): mp_pr_builds.json, by commit
    mp_dur = {}
    for b in (load(os.path.join(HERE, "mp_pr_builds.json"), {}) or {}).get("builds") or []:
        try:
            s = (datetime.fromisoformat(b["finished_at"].replace("Z", "+00:00")) - datetime.fromisoformat(b["started_at"].replace("Z", "+00:00"))).total_seconds()
        except Exception:  # noqa: BLE001  (running / not started builds have no times)
            continue
        prev = mp_dur.get(b.get("commit"))
        if not prev or b.get("number", 0) > prev[0]:
            mp_dur[b.get("commit")] = (b.get("number", 0), b.get("state"), s)
    for nd in ((SNAP.get("gh") or {}).get("prs_gql") or {}).get("nodes") or []:
        cs = (((nd.get("commits") or {}).get("nodes") or [{}])[-1].get("commit") or {})
        roll = cs.get("statusCheckRollup") or {}
        g = {}
        for c in (roll.get("contexts") or {}).get("nodes") or []:
            name = c.get("name") or c.get("context")
            if name in CK:
                k, v = CK[name], ck_state(c)
                if k not in g or SEV[v] > SEV[g[k]]:   # duplicates: the worst state wins
                    g[k] = v
                if v in ("fail", "cancel") and (c.get("targetUrl") or c.get("detailsUrl")):   # round 2 F8: link of the failing run
                    g.setdefault("_url", {})[k] = c.get("targetUrl") or c.get("detailsUrl")
        draft = bool(nd.get("isDraft"))
        labs = {x.get("name") for x in (nd.get("labels") or {}).get("nodes") or []}
        bd = mp_dur.get(cs.get("oid"))
        if g.get("mp") == "ok" and bd and bd[1] == "passed" and bd[2] < BYPASS_S:
            g["mp"] = "bypass"
            g["_mp_s"] = round(bd[2], 1)
        for k in REQ_KEYS:
            if k in g:
                continue
            if draft and k in ("unit", "mp"):
                g[k] = "draft"
            elif k == "mp" and not (labs & MP_TRIGGER):
                g[k] = "label"
            else:
                g[k] = "missing"
        if draft and "smoke" not in g:
            g["smoke"] = "draft"
        snap_ck[str(nd.get("number"))] = dict(g=g, sha=(cs.get("oid") or "")[:8], state=roll.get("state"),
                                              rd=nd.get("reviewDecision"), mg=nd.get("mergeable"), dr=draft)
    prs, scan, builds_used = {}, {}, set()
    OWN_RULES = codeowners()
    n_git = 0
    for k, n in nodes.items():
        if n.get("kind") != "pr":
            continue
        num = n["id"]
        files, src = [], None
        if num in patches:
            src = "patch"
            files = [file_rec(x["f"], x.get("s") or "modified", x.get("p") or "") for x in patches[num][:MAX_FILES]]
        elif n.get("sha") and n.get("state") == "merged" and head:
            sha = n["sha"]
            if sha not in git_cache:
                txt = git("show", "-U0", "--format=", "--no-color", "--no-ext-diff", sha)
                git_cache[sha] = [file_rec(p, s, pt) for p, s, pt in split_diff(txt)[:MAX_FILES]] if txt else None
                n_git += 1
            if git_cache[sha]:
                src, files = "git", git_cache[sha]
        rel = [e["to"].split(":", 1)[1] for e in out_e[k] if e["rel"] == "shipped_in"]
        b = [e["to"] for e in out_e[k] if e["rel"] == "ran"]
        builds_used.update(b)
        rec = dict(t=n.get("title"), st=n.get("state"), url=n.get("url"), au=n.get("author"), sha=n.get("sha"),
                   lab=n.get("labels") or [], at=n.get("at"), nf=n.get("nfiles"), rel=rel, src=src, f=files,
                   ar=[[e["to"].split(":", 1)[1], e.get("strength")] for e in out_e[k] if e["rel"] == "changes"],
                   te=[e["to"] for e in out_e[k] if e["rel"] == "edits"], b=b, rt=retry.get(num, [])[:12])
        if num in rev_by:
            rec["rv"] = rev_by[num]
        if num in snap_ck:   # both: the review-queue gates and the snapshot check rollup (review decision, mergeable)
            rec["ck"] = snap_ck[num]
        own = owners_of([f[0] for f in files], OWN_RULES)
        if own:
            rec["own"] = own
        g = groups.get(num)
        if g:
            rec["c24"] = [dict(m=i["m"], t=i.get("m_title"), at=i.get("m_at"), ci=i.get("m_ci"), lv=i.get("level"),
                               same=i.get("same"), sh=i.get("shared") or []) for i in g.get("items") or []][:12]
        prs[num] = rec
        for f in files:
            scan_file(f[0], scan)

    # open vs open (the 24 h overlap only compares open PRs with recent merges): shared files, same functions, nearby lines
    by_file = defaultdict(list)
    for num, x in prs.items():
        if x["st"] == "open" and x["src"] == "patch":
            for f in x["f"]:
                by_file[f[0]].append(num)
    pair = defaultdict(lambda: dict(files=[], funcs=set()))
    for path, nums in by_file.items():
        if len(nums) < 2 or len(nums) > 12:      # files every PR touches (lockfiles, changelogs) are noise
            continue
        for a in nums:
            for b in nums:
                if a < b:
                    fa = next(f for f in prs[a]["f"] if f[0] == path)
                    fb = next(f for f in prs[b]["f"] if f[0] == path)
                    p_ = pair[(a, b)]
                    p_["files"].append(path)
                    p_["funcs"] |= set(fa[4]) & set(fb[4])
    for (a, b), v in pair.items():
        for me, other in ((a, b), (b, a)):
            prs[me].setdefault("oc", []).append(dict(m=int(other), files=v["files"][:8], funcs=sorted(v["funcs"])[:8]))
    for x in prs.values():
        if "oc" in x:
            x["oc"].sort(key=lambda c: (-len(c["funcs"]), -len(c["files"])))
            x["oc"] = x["oc"][:10]

    # concurrency tests per area (test file uses threads / asyncio / processes at HEAD, or its name says so)
    area_tests = {a: set(v["tests"]) for a, v in areas.items()}
    for a, v in areas.items():
        ct = []
        for t in v.pop("tests"):
            path = t.split(":", 1)[1]
            s = scan_file(path, scan)
            if (s and any(h[0] == "c" for h in s["h"])) or re.search(r"concurren|thread|async|race|lock|parallel|multiproc", path, re.I):
                ct.append(path)
        v["ct"] = ct[:12]; v["nct"] = len(ct)
        v["open"] = sorted(set(area_open.get(a, [])))[:20]

    # bug signatures and builds (backward direction)
    bugs, builds = {}, {}
    for k, n in nodes.items():
        if n.get("kind") == "bug":
            bl = [e["from"] for e in in_e[k] if e["rel"] == "failed_with"]
            builds_used.update(bl)
            bugs[n["id"]] = dict(t=n.get("title"), cls=n.get("cls"), n=n.get("n_30d"), line=n.get("line"), b=bl[:40],
                                 te=[e["from"] for e in in_e[k] if e["rel"] == "fails_with"],
                                 fx=[e["to"].split(":", 1)[1] for e in out_e[k] if e["rel"] == "fixed_by"])
    for a, v in areas.items():   # failure signatures seen on tests that cover this area (phase C: FRS known risks)
        v["bugs"] = sorted(sig for sig, b in bugs.items() if area_tests.get(a, set()) & set(b["te"]))[:12]
    for bk in builds_used:
        n = nodes.get(bk) or {}
        prs_of = [e["from"].split(":", 1)[1] for e in in_e[bk] if e["rel"] == "ran"]
        sigs = [e["to"].split(":", 1)[1] for e in out_e[bk] if e["rel"] == "failed_with"]
        builds[bk] = dict(st=n.get("state"), url=n.get("url"), sha=n.get("sha"), at=n.get("at"), br=n.get("branch"), pr=prs_of, sig=sigs)

    # dev regressions: last green -> first red per dev pipeline (ops.db, read-only) -> commits in that range (local clone)
    reg = []
    if OPSDB.exists() and head:
        con = sqlite3.connect(f"{OPSDB.resolve().as_uri()}?mode=ro", uri=True)
        for pipe in ("k3-unit-tests", "k3-multiprocess-test", "k3-comprehensive-test", "k3-correctness-test"):
            rows = con.execute("select number,state,commit_sha,created_at,url from bk_build where pipeline=? and branch='dev' "
                               "and state in ('passed','failed') order by number", (pipe,)).fetchall()
            found = 0
            for i in range(len(rows) - 1, 0, -1):
                if rows[i][1] == "failed" and rows[i - 1][1] == "passed":
                    g, r = rows[i - 1], rows[i]
                    # most dev builds carry no commit in ops.db: use the dev commit just before the build was created (approx)
                    def sha_of(row):
                        if row[2]:
                            return row[2], False
                        return (git("rev-list", "-1", f"--before={row[3]}", "HEAD").strip() if row[3] else ""), True
                    g_sha, g_apx = sha_of(g)
                    red_sha, r_apx = sha_of(r)
                    if not red_sha or not g_sha:
                        continue
                    log = git("log", "--format=%h\t%s", f"{g_sha}..{red_sha}") if g_sha != red_sha else ""
                    commits = [ln.split("\t", 1) for ln in log.splitlines() if "\t" in ln][:30]
                    reg.append(dict(pipe=pipe, green=dict(num=g[0], sha=g_sha[:10], at=g[3], url=g[4], approx=g_apx),
                                    red=dict(num=r[0], sha=red_sha[:10], at=r[3], url=r[4], approx=r_apx),
                                    commits=commits, prs=[int(m) for c in commits for m in PRNUM_RX.findall(c[1])]))
                    found += 1
                    if found >= 3:
                        break
        con.close()

    # phase B: multi-step CI changes (new.CI) -> ordered pipeline steps at HEAD + which steps this PR touched
    import ci_seq  # noqa: E402
    ci_cache = cache.setdefault("ci", {})
    seq = {}
    CI_RX = re.compile(r"^(\.buildkite/|\.github/workflows/).*\.ya?ml$")
    for num, x in prs.items():
        ents = []
        for f in x["f"]:
            if not CI_RX.match(f[0]):
                continue
            # review M2: the hunk line numbers belong to the file AS OF the PR's commit, not the clone HEAD: parse that version
            vk = f"v:{x.get('sha') or ''}:{f[0]}"
            if x.get("sha") and not ci_cache.get(vk):
                ci_cache[vk] = git("show", f"{x['sha']}:{f[0]}") or ""
            text = (ci_cache.get(vk) if x.get("sha") else "") or clone_text(f[0])[0]   # P2-15: a file new on origin/dev counts
            if not text:
                continue
            steps = ci_seq.parse(f[0], text)
            n_cond = sum(1 for st in steps if st["cond"])
            if len(steps) < 3 or n_cond < 2:          # "many conditional steps" only
                continue
            if x["src"] == "patch":
                patch = next((y.get("p") or "" for y in patches.get(num, []) if y["f"] == f[0]), "")
            else:
                ck = f"{x['sha']}:{f[0]}"
                if ck not in ci_cache:
                    ci_cache[ck] = git("show", "-U0", "--format=", "--no-color", x["sha"] or "HEAD", "--", f[0])
                patch = ci_cache[ck]
            rng = [(int(m.group(1)), int(m.group(1)) + max(int(m.group(2) or 1), 1) - 1)
                   for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", patch, re.M)]
            for st in steps:
                st["chg"] = any(a <= st["end"] and b >= st["line"] for a, b in rng)
                for k in ("label", "cond", "cmd", "deps", "g"):
                    st[k] = (st[k] or "")[:220]
            ents.append(dict(file=f[0], steps=steps[:28], n=len(steps), n_cond=n_cond, n_chg=sum(1 for st in steps if st["chg"]),
                             at=("patch" if x["src"] == "patch" else "merge")))
        if ents:
            ents.sort(key=lambda e: (-e["n_chg"], -e["n_cond"]))
            seq[num] = ents[:2]

    # phase C: CI pipeline facts per gate job (what an FRS watches: a pipeline edit changes them -> FRS update proposal)
    ci = {}
    # review P2-15: read the pipelines from origin/dev (refreshed by the refresh's own "git fetch" of the clone) so new
    # files such as smoke-pipeline.yml (#6731) are seen even when the checked-out tree is older; else the working tree
    for job, path in (("k3-multiprocess-test", ".buildkite/k3_tests/multiprocess/pipeline.yml"),
                      ("k3-multiprocess-smoke", ".buildkite/k3_tests/multiprocess/smoke-pipeline.yml"),
                      ("k3-unit-tests", ".buildkite/k3_tests/unit/pipeline.yml")):
        text, ref = clone_text(path)
        if text:
            st = [x for x in ci_seq.parse(path, text) if x["kind"] != "group"]
            ci[job] = dict(file=path, ref=ref, steps=[[re.sub(r":[a-z_]+:\s*", "", x["label"])[:120], (x["cond"] or "")[:160], x["line"]] for x in st][:60],
                           n=len(st), n_cond=sum(1 for x in st if x["cond"]))

    # keep only the scans of touched files, and only the defs of touched functions
    touched_funcs = defaultdict(set)
    for x in prs.values():
        for f in x["f"]:
            touched_funcs[f[0]].update(f[4]); touched_funcs[f[0]].update(f[5])
    scan_out = {}
    for path, s in scan.items():
        if not s:
            continue
        keep = touched_funcs.get(path, set())
        # hits inside a touched function first (the views name them), then a few more of the file for context
        hs = [h for h in s["h"] if h[3] in keep] + [h for h in s["h"] if h[3] not in keep][:4]
        if not hs:
            scan_out[path] = dict(nh=0)   # scanned, nothing found (not the same as "not in the clone" = unknown)
            continue
        scan_out[path] = dict(h=hs[:24], nh=s["nh"], d={k: v for k, v in s["d"].items() if k in keep})

    data = dict(made=made, head=head, head_ref=ref, head_at=head_at, snap_at=E.get("snap_at"), patches_at=OP.get("at"),
                ov_at=ov.get("at"), w0=ov.get("w0"), req=REQUIRED, tiers=tiers, classes=classes, tw=gates.TIER_WORKLOADS,
                areas=areas, F=feats, journeys=journeys, cp_src=cp.get("src"), flaky=ov.get("known_flaky") or [],
                scan=scan_out, prs=prs, bugs=bugs, builds=builds, reg=reg, seq=seq, ci=ci)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))

    # phase C: living knowledge base (ops-app/backend/kb.py): generate / propose in ops.db, then export for the page
    kb = {}
    KB = Path(__file__).resolve().parents[3] / "ops-app" / "backend" / "kb.py"
    if KB.exists() and os.environ.get("PI_NO_KB") != "1":
        r1 = subprocess.run([sys.executable, "-X", "utf8", str(KB), "build"], cwd=str(KB.parent), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
        r2 = subprocess.run([sys.executable, "-X", "utf8", str(KB), "export", "--out", os.path.join(HERE, "kb.json")], cwd=str(KB.parent),
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        print((r1.stdout.strip() or r1.stderr.strip()[-400:]) + ("" if r2.returncode == 0 else " · kb export failed: " + r2.stderr.strip()[-300:]))
        kb = load(os.path.join(HERE, "kb.json"), {})

    page = open(PAGE, encoding="utf-8").read()
    if "PRMAP:JS:END" not in page:
        raise SystemExit("build_pr_inspector: run build_pr_map.py first")
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    kblob = json.dumps(kb, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = BOT_put(page, "<!-- PI:DATA:START -->", "<!-- PI:DATA:END -->",
                   f'<!-- PI:DATA:START -->\n<script id="piData" type="application/json">{blob}</script>\n'
                   f'<script id="kbData" type="application/json">{kblob}</script>\n<!-- PI:DATA:END -->',
                   "<!-- PRMAP:JS:END -->", before=False)
    import pr_inspector_ui as UI  # noqa: E402  (CSS + JS of the drawer, kept apart so this file stays about data)
    page = BOT_put(page, "/* PI:CSS:START */", "/* PI:CSS:END */", UI.CSS, "</style>")
    page = BOT_put(page, "<!-- PI:JS:START -->", "<!-- PI:JS:END -->", UI.JS, "<!-- PI:DATA:END -->", before=False)
    import pr_inspector_seq as SEQ  # noqa: E402  (phase B: flow animation + sequence diagrams)
    page = BOT_put(page, "/* PISEQ:CSS:START */", "/* PISEQ:CSS:END */", SEQ.CSS, "</style>")
    page = BOT_put(page, "<!-- PISEQ:JS:START -->", "<!-- PISEQ:JS:END -->", SEQ.JS, "<!-- PI:JS:END -->", before=False)
    import pr_inspector_kb as KBUI  # noqa: E402  (phase C: RFC / FRS panel)
    page = BOT_put(page, "/* PIKB:CSS:START */", "/* PIKB:CSS:END */", KBUI.CSS, "</style>")
    page = BOT_put(page, "<!-- PIKB:JS:START -->", "<!-- PIKB:JS:END -->", KBUI.JS, "<!-- PISEQ:JS:END -->", before=False)
    open(PAGE, "w", encoding="utf-8").write(page)
    n_open = sum(1 for x in prs.values() if x["st"] == "open")
    print(f"pr inspector: {len(prs)} PRs ({n_open} open; files from patch {sum(1 for x in prs.values() if x['src'] == 'patch')}, "
          f"git {sum(1 for x in prs.values() if x['src'] == 'git')}, none {sum(1 for x in prs.values() if not x['src'])}; "
          f"{n_git} new git diffs) · {len(scan_out)} files scanned · {len(bugs)} bug signatures · {len(reg)} dev regressions · "
          f"data {len(blob) // 1024} KB")


def BOT_put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor)
    return page[:i] + block.strip() + "\n" + page[i:] if before else page[:i + len(anchor)] + "\n" + block.strip() + page[i + len(anchor):]


if __name__ == "__main__":
    main()
