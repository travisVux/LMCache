"""Release Management tabs 3-5 + Trace Agent panels on every tab (idempotent, local data only).

  3 Coming release  (#obs/coming)  candidate PRs + bugs / errors / feature changes in the next release scope
  4 Optimal CI      (#obs/optimal) A. PRs: Open PR -> Human review (optional) -> Merge PR, CPU vs GPU
                                   B. Public CI: CPU (GitHub Actions) vs GPU (Buildkite) runner-minutes
  5 24h overlap     (#obs/overlap) PRs merged in 24 h vs in-flight PRs: race, semantic conflict,
                                   duplicate, flaky; can CI of older dev commits be cancelled?
  + "Trace Agent" card on all 5 tabs (proposals from outputs/trace_agent/proposals.json, mapped by
    class / impact, plus rule checks computed here)
  + "Tasks & metrics" strip on tabs 3-5: metric, definition, 30-day baseline, target, after, task.
    Tasks are classified into tabs later (9task-tensor.docx); TASKS below stays empty until then.

Inputs (all local files, no API calls here):
  observe_snapshot.json  <- observe_collect.py     (open PRs, merged PRs + files, dev builds)
  ops_ci_24h.json        <- observe_ops_collect.py (24 h of GHA runs + jobs, Buildkite builds + jobs)
  observe_history load_all()                        (60-day daily report -> 30-day baselines)
  ../trace_agent/proposals.json                     (Trace Agent proposals)

  python -I -X utf8 build_ops_tabs.py    # analyse -> ops_tabs.json -> rewrite the OPS blocks of the page
Run after build_observe.py (build_page.py calls it).
"""
import collections
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # -I drops the script dir
PAGE = str(Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
SNAP = os.path.join(HERE, "observe_snapshot.json")
OPS = os.path.join(HERE, "ops_ci_24h.json")
PROPS = os.path.join(HERE, "..", "trace_agent", "proposals.json")
OUT = os.path.join(HERE, "ops_tabs.json")

# Filled in later, after the 9 tasks (LM-1130..1138) are classified. Shape:
#   {"optimal": [{"key": "LM-1131", "title": "...", "metric": "gpu_min_pr", "target": "-40%", "status": "To Do", "after": None}]}
TASKS = {}

# ------------------------------------------------------------------ helpers
def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def mins(a, b):
    a, b = dt(a) if isinstance(a, str) else a, dt(b) if isinstance(b, str) else b
    return (b - a).total_seconds() / 60 if a and b else None


def pct(a, p):
    a = sorted(x for x in a if x is not None)
    return a[min(len(a) - 1, int(p * (len(a) - 1) + .5))] if a else None


def r1(x):
    return None if x is None else round(x, 1)


def load(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


TYPE_RX = [("feature", r"\[(feat|feature|new)\b"), ("bug", r"\[(fix|bugfix|bug|hotfix)\b"), ("perf", r"\[perf\b"),
           ("refactor", r"\[(refactor|cleanup|chore|misc)\b"), ("ci", r"\[(ci|ci/cd|build|infra|docker|release)\b"),
           ("docs", r"\[(doc|docs)\b"), ("test", r"\[(test|tests|ut|unittest)\b")]


def ptype(title, labels=()):
    t = (title or "").lower()
    for k, rx in TYPE_RX:
        if re.search(rx, t):
            return k
    cc = re.match(r"^(feat|feature|fix|bugfix|hotfix|perf|refactor|chore|ci|build|docs?|tests?)(\([^)]*\))?!?:", t)  # conventional commit
    if cc:
        return {"feat": "feature", "feature": "feature", "fix": "bug", "bugfix": "bug", "hotfix": "bug", "perf": "perf", "refactor": "refactor",
                "chore": "refactor", "ci": "ci", "build": "ci", "doc": "docs", "docs": "docs", "test": "test", "tests": "test"}[cc.group(1)]
    lab =" ".join((x.get("name") or "").lower() for x in labels or [])
    if re.match(r"(fix|bugfix|hotfix)\b", t) or "bug" in lab:
        return "bug"
    if re.match(r"(add|support|feat)\b", t) or "feature" in lab or "enhancement" in lab:
        return "feature"
    if "documentation" in lab:
        return "docs"
    return "other"


PCLS = [("docs", r"^docs/|\.(md|rst)$"), ("ci", r"^(\.github/|\.buildkite/|docker/|requirements/|pyproject\.toml$|setup\.(py|cfg)$|\.pre-commit)"),
        ("tests", r"^(tests|examples|benchmarks)/"), ("kernel", r"^csrc/|gpu_connector"),
        ("adapter", r"/integration/(vllm|sglang)/|lmcache_mp_connector|transfer_context"), ("rust", r"^rust/"), ("core", r"^lmcache/")]


def pclass(path):
    for k, rx in PCLS:
        if re.search(rx, path):
            return k
    return "other"


def risk(files):
    """Change class of a PR from its paths (same idea as gates.py CLASSES, simplified)."""
    if not files:
        return "unknown"
    c = {pclass(f) for f in files}
    if c <= {"docs"}:
        return "docs"
    if c <= {"docs", "tests"}:
        return "tests"
    if c & {"kernel", "adapter"}:
        return "gpu"
    if "ci" in c:
        return "ci"
    return "core"


CI_PIPE_RX = re.compile(r"^(\.github/|\.buildkite/|\.pre-commit)")


def ci_only(files):
    """Only CI pipeline files (plus docs / tests): users never see it. Build / dependency files (docker, requirements,
    pyproject, setup) are NOT ci_only: they change what users install."""
    return bool(files) and any(CI_PIPE_RX.search(f) for f in files) and all(CI_PIPE_RX.search(f) or pclass(f) in ("docs", "tests") for f in files)


# What a change class needs (from gates.py CLASSES / tiers): CPU-only or GPU, and whether it may skip human approval.
NEEDS = {"docs": ("none", True), "tests": ("cpu+gpu-unit", True), "core": ("cpu+gpu-unit+cpu-e2e", False),
         "ci": ("full", False), "gpu": ("gpu-smoke", False), "unknown": ("full", False)}

# label-triggered required check -> labels that start its full run (#6731: 'full', 'force-ci' or 'mp'; the first one is
# the name shown in the queue). Without one of them the heavy MP suite is bypassed (green in ~5 s) or, on heads older
# than #6731, never reported.
LABEL_TRIGGERED = {"buildkite/k3-multiprocess-test": ("full", "force-ci", "mp")}
REQ_CPU = re.compile(r"^(DCO|Check code quality)$")
REQ_GPU = re.compile(r"^buildkite/k3-(unit-tests|multiprocess-test)$")


def ctx_state(c):
    if c.get("__typename") == "StatusContext" or "context" in c:
        return {"SUCCESS": "ok", "PENDING": "run", "EXPECTED": "run", "FAILURE": "fail", "ERROR": "fail"}.get(c.get("state"), "skip")
    if c.get("status") and c["status"] != "COMPLETED":
        return "run"
    return {"SUCCESS": "ok", "NEUTRAL": "ok", "SKIPPED": "ok", "CANCELLED": "cancel", "STALE": "cancel"}.get(c.get("conclusion"), "fail")


def worst(states):
    for s in ("fail", "cancel", "missing", "run"):
        if s in states:
            return s
    return "ok" if states else None


def agg(states):
    if not states:
        return "none"
    for s in ("fail", "run", "cancel"):
        if s in states:
            return s
    return "ok"


def words(t):
    t = re.sub(r"\[[^\]]*\]", " ", (t or "").lower())
    return {w for w in re.findall(r"[a-z0-9_]{3,}", t)} - {"the", "and", "for", "with", "add", "fix", "from", "when", "into", "use"}


# ------------------------------------------------------------------ coming release: external list + git scope
WS = Path(HERE).parents[3]                      # CacheAgent workspace root
LMC = WS / "third_party" / "LMCache"            # local clone (read only, no fetch here)
GH_PR = "https://github.com/LMCache/LMCache/pull/"
BREAK_RX = re.compile(r"\b(remove[sd]?|deprecat\w*|rename[sd]?|breaking)\b", re.I)


def maybe_breaking(title):
    """Heuristic only: removes / deprecates / renames something, and is not a bug fix, test, doc or CI change."""
    return bool(BREAK_RX.search(title or "")) and ptype(title) not in ("bug", "test", "docs", "ci") \
        and not re.search(r"\b(tests?|UT|docs?|scratch|stale)\b", title, re.I)


def vkey(v):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(x) for x in m.groups()) if m else None


def find_roadmap(stable):
    """External candidate list. COMING_RELEASE_SRC wins; else the lowest release-<ver>/ folder above the stable tag."""
    env = os.environ.get("COMING_RELEASE_SRC")
    if env:
        return Path(env)
    sk = vkey(stable) or (0, 0, 0)
    best = None
    for p in list(WS.glob("release-*/ROADMAP.md")) + list(WS.glob("release-*/COMING*.md")):
        k = vkey(p.parent.name)
        if k and k > sk and (best is None or k < best[0]):
            best = (k, p)
    return best[1] if best else None


def parse_roadmap(path):
    """Parse a 'Coming in vX' list: section lines without PR numbers, item lines with (#n). Works on markdown
    (bullets, blockquote, **bold** sections) and on plain pasted text. If the file has a '## As given' heading,
    only that part is the draft; PR numbers elsewhere in the file count as 'mentioned in review'."""
    text = open(path, encoding="utf-8").read()
    m = re.search(r"^##\s+As given.*?$(.*?)(?=^##\s)", text, re.M | re.S)
    draft = m.group(1) if m else text
    ver = re.search(r"Coming in v?(\d+\.\d+\.\d+)", text)
    tagc = re.search(r"tag commit\s*`?([0-9a-f]{7,40})", draft)
    sec, items = None, []
    for raw in draft.splitlines():
        line = re.sub(r"\*\*|__|`", "", raw.strip().lstrip(">").strip()).strip()
        if not line:
            continue
        if not re.search(r"#\d{3,5}", line):
            tail = line.rsplit(":", 1)[-1].strip() if ":" in line else ""  # pasted text: "...wheel:Features & integrations"
            if len(line) <= 40 and not line.lower().startswith("coming in"):
                sec = line.rstrip(":")
            elif 0 < len(tail) <= 40:
                sec = tail
            continue
        line = re.sub(r"^[-*•]\s*", "", line)
        for part in re.split(r";\s*", line):
            nums = [int(x) for x in re.findall(r"#(\d{3,5})", part)]
            if nums:
                items.append(dict(section=sec or "Other", text=re.sub(r"\s*\(\s*#\d+(?:\s*,\s*#\d+)*\s*\)", "", part).strip(), prs=nums))
    listed = {n for it in items for n in it["prs"]}
    mentioned = {int(x) for x in re.findall(r"#(\d{3,5})", text)} - listed
    st = os.stat(path)
    return dict(path=str(path), rel=os.path.relpath(path, WS).replace("\\", "/"), version=ver.group(1) if ver else None,
                tag_commit=tagc.group(1) if tagc else None, items=items, listed=sorted(listed), mentioned=sorted(mentioned),
                mtime=datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def git(*args):
    p = subprocess.run(["git", "-C", str(LMC), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout if p.returncode == 0 else None


def git_scope(tag, end="origin/dev"):
    """PRs in <tag>..<end> from the local clone (squash commits end with '(#n)'). end = origin/dev while the target
    release is not tagged; the target tag once it is (expert review round 2, A1: notes of a shipped release)."""
    if not (LMC / ".git").exists() or not tag or git("rev-parse", "--verify", "-q", tag) is None:
        return None
    out = git("log", "--format=__C__|%h|%cI|%an|%s", "--name-only", f"{tag}..{end}") or ""
    prs, cur = [], None
    for ln in out.splitlines():
        if ln.startswith("__C__|"):
            _, sha, at, au, subj = ln.split("|", 4)
            m = re.search(r"\(#(\d+)\)\s*$", subj)
            cur = dict(num=int(m.group(1)) if m else None, sha=sha, at=at, author=au, title=re.sub(r"\s*\(#\d+\)\s*$", "", subj), files=[])
            prs.append(cur)
        elif ln.strip() and cur:
            cur["files"].append(ln.strip())
    in_tag = {int(x) for x in re.findall(r"\(#(\d+)\)\s*$", git("log", "--format=%s", tag) or "", re.M)}
    head = (git("log", "-1", "--format=%h|%cI", end) or "|").strip().split("|")
    return dict(tag=tag, tag_sha=(git("rev-parse", "--short", tag + "^{commit}") or "").strip(), head=head[0], head_at=head[1],
                prs=prs, in_tag=in_tag, repo=os.path.relpath(LMC, WS).replace("\\", "/"), end=end)


def git_merged_window(hours):
    """PRs merged into origin/dev in the last `hours` before origin/dev HEAD (squash commit time = merge time)."""
    head = (git("log", "-1", "--format=%cI", "origin/dev") or "").strip()
    if not head:
        return None
    w1 = dt(head).astimezone(timezone.utc)   # %cI keeps the committer's offset (+08:00); every "...Z" below must be UTC
    w0 = w1 - timedelta(hours=hours)
    out = git("log", "--format=__C__|%h|%cI|%s", "--name-only", f"--since={w0.isoformat()}", "origin/dev") or ""
    prs, cur = [], None
    for ln in out.splitlines():
        if ln.startswith("__C__|"):
            _, sha, at_, subj = ln.split("|", 3)
            m = re.search(r"\(#(\d+)\)\s*$", subj)
            cur = dict(num=int(m.group(1)) if m else None, sha=sha, at=at_, title=re.sub(r"\s*\(#\d+\)\s*$", "", subj), files=[]) if m else None
            if cur and dt(at_) >= w0:
                prs.append(cur)
        elif ln.strip() and cur:
            cur["files"].append(ln.strip())

    def merged_since(snap_at):
        since = (dt(snap_at) - timedelta(days=2)).isoformat() if snap_at else w0.isoformat()
        subj = git("log", "--format=%s", f"--since={since}", "origin/dev") or ""
        return {int(x) for x in re.findall(r"\(#(\d+)\)\s*$", subj, re.M)}
    return dict(w0=w0.strftime("%Y-%m-%dT%H:%M:%SZ"), w1=w1.strftime("%Y-%m-%dT%H:%M:%SZ"), prs=prs, merged_since_snap=merged_since)


# ------------------------------------------------------------------ 24h overlap: code-level review of each pair
OV_PATCH = os.path.join(HERE, "overlap_patches.json")
HUNK_RX = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
DEF_RX = re.compile(r"^\s*(?:async\s+)?(?:pub\s+)?(def|class|fn|struct|impl)\s+(\w+)")
SRC_EXT = (".py", ".cu", ".cuh", ".cpp", ".cc", ".h", ".hpp", ".rs", ".pyx")


IMPORT_RX = re.compile(r"^\s*(from\s+\S+\s+import\b|import\s+\S|#|$|\)|\w+,\s*$|\w+\s+as\s+\w+,?\s*$)")


def parse_hunks(patch):
    """Unified diff -> hunks with old line range, the functions (def/fn) and classes that contain an EDITED line,
    added / removed lines. A def that only shows up in a context line (or in git's hunk header while the edit sits
    in a later function) does not count: only the function in force at each +/- line is recorded."""
    hunks, cur = [], None

    def track(body, h, where):
        d = DEF_RX.match(body)
        if d:
            if d.group(1) in ("class", "struct", "impl"):
                h["_cls"], h["_fn"] = d.group(2), None
            else:
                h["_fn"] = d.group(2)
            if where:
                h[where + "_defs"].add(d.group(2))
        if where:  # an edited line: record where it sits
            if h["_fn"]:
                h["funcs"].add(h["_fn"])
            if h["_cls"]:
                h["classes"].add(h["_cls"])
    for ln in (patch or "").splitlines():
        m = HUNK_RX.match(ln)
        if m:
            a, b = int(m.group(1)), int(m.group(2) or 1)
            cur = dict(old=(a, a + max(b, 1) - 1), funcs=set(), classes=set(), add=[], rem=[], rem_defs=set(), add_defs=set(), _fn=None, _cls=None)
            ctx = DEF_RX.search(re.sub(r"^.*?(?=\b(async\s+)?(def|class|fn|struct|impl)\b)", "", m.group(5) or ""))
            if ctx:
                if ctx.group(1) in ("class", "struct", "impl"):
                    cur["_cls"] = ctx.group(2)
                else:
                    cur["_fn"] = ctx.group(2)
            hunks.append(cur)
            continue
        if cur is None or ln.startswith(("+++", "---")):
            continue
        body = ln[1:]
        if ln.startswith("+"):
            cur["add"].append(body.strip()); track(body, cur, "add")
        elif ln.startswith("-"):
            cur["rem"].append(body.strip()); track(body, cur, "rem")
        else:
            track(body, cur, None)
    for h in hunks:
        h["imports_only"] = all(IMPORT_RX.match(x) for x in h["add"] + h["rem"])
    return hunks


def merged_patch(sha, path):
    return git("show", "--format=", "-U3", sha, "--", path) or ""


def review_pair(m_sha, p_patches, shared, p_sub):
    """Compare the merged PR's diff with the other PR's diff, file by file.
    stop  = same function edited by both, edits a few lines apart (not imports), or a removed / renamed symbol still used
    rerun = same source file (or same class, other methods): no direct clash, but the PR was tested without the merge
    go    = only tests / docs / config shared, or only import lines touched"""
    same_func, same_cls, near, broken, dup_lines, src_files, imp = [], [], [], [], 0, [], []
    unknown, cfg = [], []   # review M4: a shared source file without a patch is unknown, not "no clash"; shared build / CI config counts
    for f in shared:
        if re.search(r"(^|/)(pyproject\.toml|setup\.py|setup\.cfg|requirements[^/]*\.txt|CMakeLists\.txt)$|^\.buildkite/|^\.github/workflows/", f):
            cfg.append(f.rsplit("/", 1)[-1])
        if not f.endswith(SRC_EXT):
            continue
        mp_, pp_ = merged_patch(m_sha, f), p_patches.get(f, "")
        if not mp_ or not pp_:
            unknown.append(f.rsplit("/", 1)[-1])
            src_files.append(f)
            continue
        mh = parse_hunks(mp_)
        ph = parse_hunks(pp_)
        mc = [h for h in mh if not h["imports_only"]]
        pc = [h for h in ph if not h["imports_only"]]
        if not mc or not pc:
            if mh and ph:
                imp.append(f.rsplit("/", 1)[-1])
            continue
        src_files.append(f)
        short = f.rsplit("/", 1)[-1]
        mf = set().union(*[h["funcs"] for h in mc]); pf = set().union(*[h["funcs"] for h in pc])
        same_func += [f"{short}:{fn}()" for fn in sorted(mf & pf)]
        same_func.sort(key=lambda x: x.startswith("test_"))  # source functions first
        mcl = set().union(*[h["classes"] for h in mc]); pcl = set().union(*[h["classes"] for h in pc])
        same_cls += [f"{short}:{c}" for c in sorted(mcl & pcl)]
        for x in mc:
            for y in pc:
                if x["old"][0] - 5 <= y["old"][1] and y["old"][0] - 5 <= x["old"][1] and not (x["funcs"] & y["funcs"]):
                    near.append(f"{short}:~L{x['old'][0]}")
                    break
        gone = set().union(*[h["rem_defs"] for h in mh]) - set().union(*[h["add_defs"] for h in mh])
        p_add = " ".join(x for h in ph for x in h["add"])
        broken += [g for g in sorted(gone) if re.search(rf"\b{re.escape(g)}\b", p_add)]
        ma = {x for h in mc for x in h["add"] if len(x) > 15}
        pa = {x for h in pc for x in h["add"] if len(x) > 15}
        dup_lines += len(ma & pa)
    near = sorted(set(near))
    is_t = lambda x: x.split(":")[0].startswith("test_") or "/tests/" in x
    sf_src = [x for x in same_func if not is_t(x)]
    nr_src = [x for x in near if not is_t(x)] + [x for x in same_cls if not is_t(x)]
    test_hit = [x for x in same_func + near if is_t(x)]
    src_hit = broken or sf_src or nr_src
    # P0 will break · P1 same function · P2 nearby code / same class · P3 same file or same test · P4 no code clash
    level = "p0" if broken else "p1" if sf_src else "p2" if nr_src else "p3" if (src_files or test_hit or cfg) else "p4"
    same_func = [x for x in same_func if not is_t(x)] + [x for x in same_func if is_t(x)]
    return dict(level=level, test_only=bool(test_hit) and not src_hit, same_func=same_func[:3], same_cls=same_cls[:4], near=near[:4], broken=broken[:4], dup_lines=dup_lines,
                src=src_files, imports=imp, inactive="inactive" if p_sub in ("draft", "old", "conflict") else None,
                unknown=unknown[:4], config=cfg[:4])


def pair_text(r, m, p, sub_label):
    """Agent review sentences: does it touch the same code, what goes wrong on a plain re-run, the decision."""
    sf = ", ".join(r["same_func"]) or None
    if r.get("test_only"):
        same = [f"Tests only: {sf or ', '.join(r['near'])}.", f"Chỉ test: {sf or ', '.join(r['near'])}."]
    elif r["broken"]:
        same = [f"#{m} removed {', '.join(r['broken'])}; #{p} still uses it.", f"#{m} đã xoá {', '.join(r['broken'])}; #{p} vẫn dùng."]
    elif sf and r["level"] in ("p1",):
        same = [f"Same function: {sf}.", f"Cùng hàm: {sf}."]
    elif sf:  # only test functions are shared; the level comes from the production code
        prod = ", ".join(r.get("same_cls") or r["near"] or [x.rsplit("/", 1)[-1] for x in r["src"][:3]])
        same = [f"Same test function: {sf}. Code: {prod}.", f"Cùng hàm test: {sf}. Code: {prod}."]
    elif r["near"]:
        same = [f"Nearby lines: {', '.join(r['near'])} (≈).", f"Dòng gần nhau: {', '.join(r['near'])} (≈)."]
    elif r.get("same_cls"):
        same = [f"Same class: {', '.join(r['same_cls'])}.", f"Cùng class: {', '.join(r['same_cls'])}."]
    elif r["src"]:
        same = [f"Same file: {', '.join(x.rsplit('/', 1)[-1] for x in r['src'][:3])}.", f"Cùng file: {', '.join(x.rsplit('/', 1)[-1] for x in r['src'][:3])}."]
    elif r.get("imports"):
        same = [f"Imports only: {', '.join(r['imports'][:3])}.", f"Chỉ import: {', '.join(r['imports'][:3])}."]
    else:
        same = ["Only tests / docs / config shared.", "Chỉ chung test / docs / config."]
    if r["level"] in ("p0", "p1", "p2"):
        rerun = [f"A plain re-run tests #{p} on its old base, without #{m}. A green result proves nothing about the two together; after a rebase git may conflict or the code may not import / behave the same.",
                 f"Chạy lại nguyên trạng là test #{p} trên base cũ, không có #{m}. Kết quả xanh không chứng minh hai PR chạy được cùng nhau; sau khi rebase git có thể xung đột hoặc code không import / chạy như cũ."]
        dec = ["Stop its CI now. Rebase on dev, fix, then run CI once.", "Dừng CI của PR này ngay. Rebase lên dev, sửa, rồi chạy CI một lần."]
        if r["inactive"]:
            dec = [f"PR is {sub_label[0].lower()}: no CI to stop; rebase before it moves on.", f"PR đang {sub_label[1].lower()}: không có CI để dừng; rebase trước khi đi tiếp."]
    elif r["level"] == "p3":
        rerun = [f"Low conflict risk, but imports or shared state in the file changed with #{m}. A re-run without rebase still misses #{m}.",
                 f"Ít rủi ro xung đột, nhưng import hoặc state dùng chung trong file đã đổi theo #{m}. Chạy lại mà không rebase vẫn thiếu #{m}."]
        dec = ["Let the current CI finish. Rebase and re-run once before merge.", "Để CI hiện tại chạy xong. Rebase và chạy lại một lần trước khi merge."]
        if r["inactive"]:
            dec = [f"PR is {sub_label[0].lower()}: rebase before it moves on.", f"PR đang {sub_label[1].lower()}: rebase trước khi đi tiếp."]
    else:
        rerun = ["No code clash; a re-run gives the same answer.", "Không đụng code; chạy lại cho cùng kết quả."]
        dec = ["Keep going. No action.", "Tiếp tục. Không cần làm gì."]
    if r["dup_lines"] >= 3:
        same = [same[0] + f" {r['dup_lines']} identical added lines: possible duplicate.", same[1] + f" {r['dup_lines']} dòng thêm giống hệt: có thể trùng."]
    return same, rerun, dec


INTERNAL_TYPES = {"refactor", "test", "ci", "docs"}


def roadmap_check(rm, sc, open_nums):
    """Cross-check the external list against the git scope and the open PRs."""
    by = {p["num"]: p for p in (sc or {}).get("prs") or [] if p["num"]}
    def status(n):
        if n in by:
            return "in_scope"
        if sc and n in sc["in_tag"]:
            return "in_tag"
        if n in open_nums:
            return "open"
        return "not_found"
    items = []
    for it in rm["items"]:
        prs = []
        for n in it["prs"]:
            p = by.get(n)
            t = p["title"] if p else ""
            brk = bool(p) and maybe_breaking(t)
            prs.append(dict(num=n, status=status(n), title=t, at=p["at"] if p else None, type=ptype(t) if p else None,
                            breaking=brk and "break" not in (it["section"] or "").lower()))
        items.append(dict(section=it["section"], text=it["text"], prs=prs))
    listed = set(rm["listed"])
    missing = []
    for n, p in by.items():
        if n in listed:
            continue
        ty, rk = ptype(p["title"]), risk(p["files"])
        internal = ty in INTERNAL_TYPES or rk in ("docs", "tests") or ci_only(p["files"])
        missing.append(dict(num=n, title=p["title"], at=p["at"], author=p["author"], type=ty, risk=rk, internal=internal,
                            mentioned=n in set(rm["mentioned"]), breaking=maybe_breaking(p["title"])))
    missing.sort(key=lambda x: x["at"], reverse=True)
    missing.sort(key=lambda x: (x["internal"], x["mentioned"]))  # user-facing and not reviewed first, newest first
    cnt = collections.Counter(x["status"] for it in items for x in it["prs"])
    listed_ = set(rm["listed"])
    uf = [p for p in by.values() if p["num"] in listed_ or not (ptype(p["title"]) in INTERNAL_TYPES or risk(p["files"]) in ("docs", "tests") or ci_only(p["files"]))]
    return dict(src=dict((k, rm[k]) for k in ("rel", "version", "tag_commit", "mtime")), items=items, status=dict(cnt), listed_all=sorted(listed),
                n_items=len(items), n_listed=len(listed), missing=missing, n_missing_user=sum(1 for x in missing if not x["internal"]),
                n_missing_int=sum(1 for x in missing if x["internal"]), n_user=len(uf),
                n_user_listed=sum(1 for p in uf if p["num"] in listed),
                breaking=[x for it in items for x in it["prs"] if x["breaking"]] + [x for x in missing if x["breaking"] and not x["internal"]])


def topdirs(files, n=2):
    """Most-touched code areas, e.g. 'lmcache/v1/multiprocess' (3 levels for lmcache/, 1 otherwise)."""
    c = collections.Counter("/".join(f.split("/")[:3 if f.startswith("lmcache/") else 1]) for f in files
                            if "/" in f and not re.match(r"(docs|tests|examples|benchmarks|\.github|\.buildkite)/", f))
    return [d for d, _ in c.most_common(n)]


TYPE_WORD = {"feature": ["a new feature", "tính năng mới"], "bug": ["a bug fix", "bản sửa bug"], "perf": ["a performance change", "thay đổi hiệu năng"],
             "refactor": ["a refactor", "một refactor"], "ci": ["a build / CI change", "thay đổi build / CI"], "docs": ["a docs change", "thay đổi docs"],
             "test": ["a test change", "thay đổi test"], "other": ["a change", "một thay đổi"]}
RISK_WORD = {"docs": ["docs only", "chỉ docs"], "tests": ["tests only", "chỉ test"], "core": ["LMCache core code", "code core của LMCache"],
             "ci": ["build / dependency files", "file build / dependency"], "gpu": ["a GPU / engine path", "đường GPU / engine"], "unknown": ["unknown files", "file chưa rõ"]}


def why_fits(c, m, stable, tag_sha, ver):
    """Short, PR-specific reason why it belongs (or not) in the target release, from data only."""
    ty, rk = c.get("type") or "other", c.get("risk") or "unknown"
    if c["origin"] == "open":
        return [f"Approved, not merged yet. {TYPE_WORD[ty][0].capitalize()} in {RISK_WORD[rk][0]}: fits {ver} only if it merges before the RC is cut.",
                f"Đã duyệt, chưa merge. {TYPE_WORD[ty][1].capitalize()} ở {RISK_WORD[rk][1]}: chỉ vào {ver} nếu merge trước khi cắt RC."]
    if not m:
        return ["Not on dev after the tag, so it cannot ship in this release as written.", "Không có trên dev sau tag, nên không thể ship trong release này như đã ghi."]
    d = ", ".join(m.get("dirs") or []) or RISK_WORD[rk][0]
    dv = ", ".join(m.get("dirs") or []) or RISK_WORD[rk][1]
    sec = c.get("section") or ""
    notes = " ".join(n[1] for n in c.get("notes") or [])
    en, vi = [], []
    if c["origin"] == "suggested":
        pass   # round 3 (B_content #48): "merged after the tag, the notes miss it" is said once, in the 3G picker summary
    if "Possibly breaking" in notes:
        en.append(f"It removes or renames something in {d}; users may have to change their setup, so it belongs under 'Breaking changes', not '{sec}'.")
        vi.append(f"Nó xoá hoặc đổi tên một phần trong {dv}; người dùng có thể phải đổi cách cài đặt, nên thuộc 'Breaking changes', không phải '{sec}'.")
    elif rk == "tests" or ty == "test":
        en.append("Only tests change: users do not see it. Keep it out of the notes or put it under Internal.")
        vi.append("Chỉ đổi test: người dùng không thấy. Bỏ khỏi release note hoặc để ở mục Nội bộ.")
    elif rk == "ci" or ty == "ci":
        en.append(f"Build / CI change ({d}): users notice it only if what they install changes (wheels, images, dependencies). Keep it under Platforms / Build if so.")
        vi.append(f"Thay đổi build / CI ({dv}): người dùng chỉ thấy nếu thứ họ cài đặt thay đổi (wheel, image, dependency). Nếu có thì để ở mục Nền tảng / Build.")
    elif rk == "docs" or ty == "docs":
        en.append("Docs change: users read it, so a Docs line fits when it is a guide or a recipe.")
        vi.append("Thay đổi docs: người dùng đọc được, nên hợp với một dòng Docs nếu đó là hướng dẫn hoặc recipe.")
    elif ty == "other" and c["origin"] == "listed":
        en.append(f"Changes {d}, which users see. The title has no type prefix, so '{sec}' (chosen in the list) is accepted.")
        vi.append(f"Thay đổi {dv}, người dùng thấy được. Tiêu đề không có tiền tố loại, nên chấp nhận mục '{sec}' đã chọn trong danh sách.")
    elif ty == "other":
        en.append(f"Changes {d}, which users see. The title has no type prefix: pick the section by hand.")
        vi.append(f"Thay đổi {dv}, người dùng thấy được. Tiêu đề không có tiền tố loại: chọn mục bằng tay.")
    elif "Title says" in notes:
        want = "Bug fixes" if ty == "bug" else "Features"
        en.append(f"{TYPE_WORD[ty][0].capitalize()} in {d}: users see it, but it is listed under '{sec}'; '{want}' fits better.")
        vi.append(f"{TYPE_WORD[ty][1].capitalize()} ở {dv}: người dùng thấy được, nhưng đang nằm ở '{sec}'; '{want}' hợp hơn.")
    else:
        en.append(f"{TYPE_WORD[ty][0].capitalize()} in {d}: users see it, so it fits '{sec}'.")
        vi.append(f"{TYPE_WORD[ty][1].capitalize()} ở {dv}: người dùng thấy được, nên hợp với '{sec}'.")
    return [" ".join(en), " ".join(vi)]


def parse_prep(path):
    """Open decisions (D1..) and carry-over blockers (C1..) from release-<ver>/RELEASE_PREP.md tables."""
    if not path or not path.exists():
        return None
    rows = [[x.strip() for x in ln.strip().strip("|").split("|")] for ln in open(path, encoding="utf-8") if re.match(r"\|\s*[DC]\d+\s*\|", ln)]
    done = re.compile(r"^\W*(✅|done|decided|merged|closed|fixed)\b", re.I)  # "Not done" stays open
    dec = [dict(id=r[0], text=re.sub(r"[*`]", "", r[1]), open=not any(done.match(c) for c in r[2:])) for r in rows if r[0].startswith("D")]
    blk = [dict(id=r[0], text=re.sub(r"[*`]", "", r[1]), state=re.sub(r"[*`]", "", r[-1]), open=not done.match(r[-1])) for r in rows if r[0].startswith("C")]
    return dict(rel=os.path.relpath(path, WS).replace("\\", "/"), decisions=dec, blockers=blk)


GATE_PIPES = ("k3-unit-tests", "k3-multiprocess-test")


def target_summary(coming, rm, ta, stable, prep):
    """Top card: what the target release contains and whether it is ready for an RC."""
    ver = "v" + rm["src"]["version"] if rm and rm["src"].get("version") else "next release"
    mg = coming["merged"]
    lst = set((rm or {}).get("listed_all") or [])
    user = [m for m in mg if m["num"] in lst or not (m["type"] in INTERNAL_TYPES or m["risk"] in ("docs", "tests") or m.get("ci_only"))]
    bt = collections.Counter(m["type"] for m in user)
    gate_red = [d["pipeline"] for d in coming["dev_red"] if d["pipeline"] in GATE_PIPES]
    other_red = [d["pipeline"] for d in coming["dev_red"] if d["pipeline"] not in GATE_PIPES]
    brk = sorted({x["num"] for x in (rm or {}).get("breaking", [])})
    blocks = [x for x in ta.get("release", []) + ta.get("coming", []) if x["impact"] == "blocks-release" and x.get("fix_status") not in ("merged", "done")]
    blocks = list({x["key"]: x for x in blocks}.values())
    ready_open = [c for c in coming.get("cands") or [] if c["origin"] == "open"]
    dup_dec = [d for d in (prep or {}).get("decisions", []) if d["open"] and any(f"#{n}" in d["text"] for n in brk)]
    od = [d for d in (prep or {}).get("decisions", []) if d["open"] and d not in dup_dec]
    ob = [b for b in (prep or {}).get("blockers", []) if b["open"]]
    chk = [
        ("ok" if coming["scope"]["src"] == "git" else "warn", [f"Scope fixed by git: {stable} ({coming['scope'].get('tag_sha')})..origin/dev ({coming['scope'].get('head')})", f"Phạm vi cố định bằng git: {stable} ({coming['scope'].get('tag_sha')})..origin/dev ({coming['scope'].get('head')})"]),
        ("ok" if not gate_red else "bad", [f"Required checks green on dev ({', '.join(GATE_PIPES)})" + (f": red on {', '.join(gate_red)}" if gate_red else ""), f"Check bắt buộc xanh trên dev ({', '.join(GATE_PIPES)})" + (f": đỏ ở {', '.join(gate_red)}" if gate_red else "")]),
        ("ok" if not other_red else "warn", [f"Other dev pipelines green" + (f": red on {', '.join(other_red)}" if other_red else ""), f"Pipeline dev khác xanh" + (f": đỏ ở {', '.join(other_red)}" if other_red else "")]),
        ("ok" if rm and not rm["n_missing_user"] else "warn" if rm else "bad", [f"Release notes cover user-facing PRs: {rm['n_user_listed']}/{rm['n_user']}" if rm else "No release-notes list yet", f"Release note có đủ PR người dùng thấy được: {rm['n_user_listed']}/{rm['n_user']}" if rm else "Chưa có danh sách release note"]),
        ("ok" if not brk else "bad", ["Breaking changes listed under 'Breaking changes'" + (f": check {', '.join('#' + str(n) for n in brk)}" if brk else ""), "Thay đổi không tương thích (breaking) nằm ở 'Breaking changes'" + (f": kiểm tra {', '.join('#' + str(n) for n in brk)}" if brk else "")]),
        ("ok" if not blocks else "bad", [f"No open Trace Agent 'blocks-release' finding" + (": " + "; ".join(f"#{x['num']} shipped in {x['tag']}, found {(x.get('run_at') or '')[:10]}: re-check if dev is still red" for x in blocks) if blocks else ""),
                                          f"Không còn phát hiện 'blocks-release' của Trace Agent" + (": " + "; ".join(f"#{x['num']} đã ship trong {x['tag']}, phát hiện {(x.get('run_at') or '')[:10]}: kiểm tra lại dev còn đỏ không" for x in blocks) if blocks else "")]),
        ("ok" if not ready_open else "warn", [f"Approved open PRs decided (merge or drop): {len(ready_open)} pending", f"PR mở đã duyệt được quyết định (merge hay bỏ): còn {len(ready_open)}"]),
    ]
    if prep:
        dd = "".join(f" ({d['id']} is the breaking-change row above)" for d in dup_dec)
        ddv = "".join(f" ({d['id']} chính là dòng thay đổi không tương thích ở trên)" for d in dup_dec)
        chk.append(("ok" if not od else "bad", [f"Release decisions made ({prep['rel']}): " + (", ".join(d["id"] for d in od) + " open" if od else "all done") + dd, f"Đã chốt quyết định release ({prep['rel']}): " + (", ".join(d["id"] for d in od) + " còn mở" if od else "xong hết") + ddv]))
        chk.append(("ok" if not ob else "bad", [f"Carry-over blockers fixed: " + (", ".join(b["id"] for b in ob) + " open" if ob else "all done"), f"Blocker tồn từ bản trước đã sửa: " + (", ".join(b["id"] for b in ob) + " còn mở" if ob else "xong hết")]))
    nbad = sum(1 for c in chk if c[0] == "bad")
    verdict = "ready" if not nbad and not any(c[0] == "warn" for c in chk) else "almost" if not nbad else "not_ready"
    return dict(ver=ver, stable=stable, n_scope=len(mg), n_user=len(user), n_internal=len(mg) - len(user), by_type=dict(bt), breaking=brk,
                verdict=verdict, n_bad=nbad, checks=[dict(lvl=c[0], t=c[1]) for c in chk], prep=prep, blocks=[dict(num=x["num"], tag=x["tag"], title=x["title"]) for x in blocks],
                n_listed=len(lst))


# ------------------------------------------------------------------ feature + critical path of a PR (Coming release)
# Source path -> feature area (ids of the Explore view, area_meta.AREAS). Tests use areas.area_of().
SRC_AREA = [(re.compile(rx), a) for rx, a in [
    # build / CI files first: '.buildkite/k3_tests/xpu/...' is a CI pipeline, not the XPU platform code
    (r"^(setup\.py|pyproject\.toml|requirements/|docker/|\.github/|\.buildkite/)", "build"),
    (r"integration/vllm/.*(lazy|token_drop)|token_drop", "lazy"), (r"blend", "blend"), (r"integration/vllm/|vllm_multi_process|lmcache_mp_connector|lmcache_mp_metadata", "vllm"),
    (r"integration/(sglang|trtllm|tensorrt|atom)|/sglang", "engines"),
    (r"(multiprocess|client)/transport/|grpc|zmq|/mq\.py", "transport"), (r"plugin_modules|ext_server_module|multiprocess/modules/(?!lmcache_driven|engine_driven)", "modules"),
    (r"lmcache_driven|engine_driven|transfer_context|/sdk/|gpu_connector|ring_", "datapath"), (r"multiprocess/(lookup|prefetch)|token_hasher|token_codec|hash", "lookup"),
    (r"multiprocess/(http|api)|/auth", "http"), (r"gds|cufile", "gds"), (r"l2_adapters|nixl|/resp|valkey|hf3fs|mooncake", "l2"),
    (r"serde|compress|encrypt|cachegen", "serde"), (r"transfer_channel|p2p|peer", "p2p"), (r"orchestrat", "orch"),
    (r"storage_manager|storage_controllers|eviction|prefetch_controller|shadow", "smcore"), (r"memory_management|memory_obj|allocator|/l1|borrowed", "l1"),
    (r"mp_coordinator|coordinator", "coord"), (r"observab|metrics|stats|/events|tracing|trace_", "obs"),
    (r"layout|kv_format|kv_layer_groups|kv_cache_groups|group_view|mla|hybrid", "layout"), (r"worker_transfer", "datapath"),
    (r"v1/transport/|rpc_utils|v1/protocol|security/api_key", "transport"), (r"memory_manager", "l1"), (r"kv_event_subscriber|usage_telemetry", "obs"),
    (r"distributed/(api|config)\.py", "smcore"), (r"client/(heartbeat|client_config|__init__)", "lifecycle"), (r"lmcache/tools/", "cli"), (r"v1/platform|/xpu|/rocm|/musa|/npu|/rbln|ascend", "platform"),
    (r"^csrc/|^rust/|native", "native"), (r"lmcache/inprocess|v1/cache_engine|v1/storage_backend", "ip_store"),
    (r"lmcache/cli/|/bench", "cli"), (r"frontend", "frontend"), (r"multiprocess/", "lifecycle"),
    (r"^(setup\.py|pyproject\.toml|requirements/|docker/|\.github/|\.buildkite/)", "build")]]

# The KV request path through LMCache (the "flow"); a feature on one of these stages is on the critical path.
FLOW = [("engine", ["Engine connector", "Kết nối engine"], {"vllm", "engines", "lazy", "blend"}),
        ("rpc", ["Request transport", "Truyền request"], {"transport", "http"}),
        ("lookup", ["Lookup & prefetch", "Lookup & prefetch"], {"lookup"}),
        ("transfer", ["KV transfer GPU ↔ CPU", "Chuyển KV GPU ↔ CPU"], {"datapath", "layout", "native", "platform"}),
        ("l1", ["L1 memory", "Bộ nhớ L1"], {"l1", "smcore", "orch"}),
        ("l2", ["L2 / remote storage", "L2 / lưu trữ ngoài"], {"l2", "serde", "p2p", "gds"})]
STAGE_OF = {a: i for i, (_, _, s) in enumerate(FLOW) for a in s}
CPU_TIERS, GPU_TIERS = ("L1", "L2", "CE"), ("L1G", "L3", "LS", "AO", "FULL")


def src_area(path):
    if path.startswith(("tests/", "examples/")) or "/tests/" in path:
        from areas import area_of
        a = area_of(path)
        return None if a == "other" else a
    if path.startswith("docs/") or path.endswith((".md", ".rst")):
        return None
    for rx, a in SRC_AREA:
        if rx.search(path):
            return a
    return "other" if path.startswith("lmcache/") else None


def pr_feature(files):
    """Primary feature, related features, critical stage on the KV flow, change class and CPU / GPU test scope."""
    from gates import AREA_CLASS, CLASSES
    src = [f for f in files if not (f.startswith(("tests/", "docs/", "examples/")) or f.endswith((".md", ".rst")))]
    cnt = collections.Counter(a for a in (src_area(f) for f in (src or files)) if a)
    feats = [a for a, _ in cnt.most_common()]
    prim = feats[0] if feats else None
    rel = feats[1:5]
    stages = sorted({STAGE_OF[a] for a in feats if a in STAGE_OF})
    stage = STAGE_OF.get(prim)  # the PR's own feature decides the stage; related features only add context
    rk = risk(files)
    klass = "docs" if rk == "docs" else "tests_only" if rk == "tests" else "deps_ci" if (prim == "build" or rk == "ci") else AREA_CLASS.get(prim, "core")
    tiers = next((c["tiers"] for c in CLASSES if c["id"] == klass), {})
    def scope(names):
        req = [t for t in names if tiers.get(t) == 1]
        cond = [t for t in names if tiers.get(t) == 2]
        return dict(level="required" if req else "conditional" if cond else "none", tiers=req + [t + "?" for t in cond])
    gpu = scope(GPU_TIERS)
    if any(tiers.get(t) == 1 for t in ("L3", "LS", "FULL")):
        gpu["level"] = "required"      # a real engine / layout run on GPU
    elif any(tiers.get(t) == 2 for t in GPU_TIERS):
        gpu["level"] = "conditional"   # GPU add-on only when its path changes
    elif tiers.get("L1G") == 1:
        gpu["level"] = "unit"          # GPU unit tests only
    return dict(prim=prim, rel=rel, stage=stage, stages=stages, on_path=stage is not None, klass=klass, cpu=scope(CPU_TIERS), gpu=gpu)


SEC_TYPE = [("break", "breaking"), ("feature", "feature"), ("integration", "feature"), ("bug", "bug"), ("fix", "bug"), ("refactor", "refactor"), ("platform", "platform")]


def sec_type(sec):
    s = (sec or "").lower()
    return next((t for k, t in SEC_TYPE if k in s), None)


def candidate_list(rm, merged, open_prs, ta, stable, tag_sha=None, files_of=None):
    """One list for the Coming release tab: PRs in the external list + suggested additions + ready open PRs,
    each with agent review notes [level, en, vi]. Order: needs action first."""
    by_scope = {m["num"]: m for m in merged}
    by_open = {p["num"]: p for p in open_prs}
    props = collections.defaultdict(list)
    for x in [y for t in ta.values() for y in t]:
        if x["key"] not in {p["key"] for p in props[x["num"]]}:
            props[x["num"]].append(x)
    saved = (rm or {}).get("src", {}).get("mtime")
    out = []

    def add(num, title, origin, section, notes, at=None, ty=None, rk=None, ci=None):
        for x in props.get(num, []):
            notes.append(["warn" if x["impact"] in ("blocks-release", "shipped-bug") else "info",
                          f"Trace Agent ({x['tag']}): {x['cls']}{', ' + x['impact'] if x['impact'] and x['impact'] != 'none' else ''}",
                          f"Trace Agent ({x['tag']}): {x['cls']}{', ' + x['impact'] if x['impact'] and x['impact'] != 'none' else ''}"])
        lv = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
        tap = [dict(tag=x["tag"], cls=x["cls"], impact=x["impact"], root=x["root"], fix=x["fix"], conf=x["conf"]) for x in props.get(num, [])]
        out.append(dict(num=num, title=title, origin=origin, section=section, at=at, type=ty, risk=rk, ci=ci, notes=notes, ta=tap,
                        rank=min((lv[n[0]] for n in notes), default=3)))

    if rm:
        for it in rm["items"]:
            for p in it["prs"]:
                n, notes = [], []
                if p["status"] == "in_scope":
                    md = ((by_scope.get(p["num"]) or {}).get("at") or "")[5:10]
                    notes.append(["ok", f"Merged {md}, after {stable}: ships", f"Merge {md}, sau {stable}: sẽ ship"])
                elif p["status"] == "in_tag":
                    notes.append(["bad", f"Already shipped in {stable}: remove from the list", f"Đã ship trong {stable}: bỏ khỏi danh sách"])
                elif p["status"] == "open":
                    notes.append(["warn", "Not merged yet: ships only if merged before the RC", "Chưa merge: chỉ ship nếu merge trước RC"])
                else:
                    notes.append(["bad", "Not found on dev or in open PRs: check the number", "Không thấy trên dev hay trong PR mở: kiểm tra lại số PR"])
                if p["breaking"]:
                    notes.append(["bad", "Possibly breaking: move to 'Breaking changes' and add a user note", "Có thể không tương thích (breaking): chuyển lên 'Breaking changes' và ghi chú cho người dùng"])
                want = sec_type(it["section"])
                if p["type"] in ("feature", "bug") and want in ("feature", "bug") and p["type"] != want:
                    notes.append(["info", f"Title says {p['type']}, listed under '{it['section']}'", f"Tiêu đề là {p['type']}, đang nằm ở '{it['section']}'"])
                m = by_scope.get(p["num"]) or {}
                add(p["num"], p["title"] or it["text"], "listed", it["section"], notes, m.get("at"), m.get("type"), m.get("risk"))
                out[-1]["note_text"] = it["text"]  # the curated release-note wording; the export uses it, not the PR title
        for x in rm["missing"]:
            if x["internal"]:
                continue
            late = bool(saved and x["at"] and x["at"] > saved)
            why_en = "merged after the list was saved" if late else "noted in the file's review part" if x["mentioned"] else "not mentioned anywhere in the file"
            why_vi = "merge sau khi lưu danh sách" if late else "đã ghi ở phần review của file" if x["mentioned"] else "chưa nhắc tới ở đâu trong file"
            notes = [["warn", f"Add it: user-facing, {why_en}", f"Thêm vào: người dùng thấy được, {why_vi}"]]
            if x["breaking"]:
                notes.insert(0, ["bad", "Possibly breaking: add under 'Breaking changes'", "Có thể không tương thích (breaking): thêm vào 'Breaking changes'"])
            sect = {"feature": "Features", "bug": "Bug fixes", "perf": "Features"}.get(x["type"], "section to pick")
            add(x["num"], x["title"], "suggested", sect, notes, x["at"], x["type"], x["risk"])
    if not rm:   # round 2 D2: the next line has no prep doc yet -> every user-facing PR merged after the stable tag is a candidate
        for m in merged:
            if m.get("num") and m.get("type") in ("feature", "bug", "perf"):
                add(m["num"], m["title"], "suggested", {"feature": "Features", "bug": "Bug fixes", "perf": "Features"}[m["type"]],
                    [["warn", f"Merged after {stable}: ships in the next line, which has no prep doc yet", f"Merge sau {stable}: sẽ ship ở dòng tiếp theo, dòng này chưa có tài liệu chuẩn bị"]],
                    m.get("at"), m.get("type"), m.get("risk"))
    listed = {c["num"] for c in out}
    for p in open_prs:
        if p["num"] in listed or p["sub"] != "ready":
            continue
        add(p["num"], p["title"], "open", "—", [["warn", "Approved, not merged: merge before the RC or drop", "Đã duyệt, chưa merge: merge trước RC hoặc bỏ"]],
            None, p["type"], p["risk"], dict(cpu=p["cpu"], gpu=p["gpu"]))
    ver = "v" + rm["src"]["version"] if rm and rm["src"].get("version") else "the next release"
    for c in out:
        c["why"] = why_fits(c, by_scope.get(c["num"]) or {}, stable, tag_sha, ver)
        f_ = (files_of or {}).get(c["num"])
        c["feat"] = pr_feature(f_) if f_ else None
    order = {"suggested": 0, "listed": 1, "open": 2}
    out.sort(key=lambda c: (c["rank"] if c["rank"] < 1 else 1, order[c["origin"]], -(dt(c["at"]).timestamp() if c["at"] and c["origin"] == "suggested" else 0)))
    return out


# ------------------------------------------------------------------ Optimal CI: costs + ranked opportunities
def jmin(a, b):
    v = mins(a, b)
    return max(0.0, v) if v is not None else 0.0  # skipped jobs can have completed < started


def gh_os(labels):
    s = " ".join(labels or []).lower()
    return "macOS" if "macos" in s else "Linux arm" if "arm" in s else "Linux x64"


def ci_costs(O):
    """Job-minutes in the collector window, split by outcome. One unit everywhere: job-minutes
    (GitHub = runner-minutes; Buildkite = job-minutes, GPUs per job not known here)."""
    if not O:
        return None
    rows = collections.defaultdict(lambda: dict(runs=0, pr=0, push=0, other=0, ok=0.0, failed=0.0, cancelled=0.0, rerun=0.0,
                                                n_cancel=0, n_fail=0, n_rerun=0, n_action=0, total=0.0, release_rerun=0.0, versions=set(), jobs_per_run=[]))
    os_min = collections.Counter()
    for r in O.get("gha") or []:
        x = rows[("CPU", "GitHub Actions", r["name"])]
        x["runs"] += 1
        ev = r.get("event")
        x["pr" if ev in ("pull_request", "pull_request_target") else "push" if ev in ("push", "schedule", "workflow_dispatch") else "other"] += 1
        c = r.get("conclusion")
        x["n_cancel"] += c == "cancelled"
        x["n_fail"] += c in ("failure", "timed_out", "startup_failure")
        x["n_action"] += c == "action_required"
        # a re-run of a release (tag push / published release) is a deliberate retry of the publish, not a flaky test
        is_rel = ev == "release" or (ev == "push" and bool(re.match(r"v\d", r.get("head_branch") or "")))
        n_latest = 0
        for j in r.get("jobs") or []:
            v = jmin(j.get("started_at"), j.get("completed_at"))
            os_min[gh_os(j.get("labels"))] += v
            x["total"] += v
            if (j.get("run_attempt") or 1) < (r.get("run_attempt") or 1):
                x["release_rerun" if is_rel else "rerun"] += v  # earlier attempt of a re-run: spent again later
                continue
            n_latest += 1
            jc = j.get("conclusion")
            x["cancelled" if jc == "cancelled" else "failed" if jc in ("failure", "timed_out") else "ok"] += v
            m = re.search(r"\b3\.(\d{1,2})\b", j.get("name") or "")
            if m:
                x["versions"].add(m.group(0))
        x["n_rerun"] += (r.get("run_attempt") or 1) > 1 and not is_rel
        x["jobs_per_run"].append(n_latest)
    for b in O.get("bk") or []:
        slug = (b.get("pipeline") or {}).get("slug") or "?"
        hw = "GPU" if slug.startswith("k3-") else "Accel" if re.match(r"(amd|xpu|musa|rbln|metax|unit-tests-)", slug) else "Other"
        x = rows[(hw, "Buildkite", slug)]
        x["runs"] += 1
        x["pr" if b.get("pull_request") else "push" if b.get("branch") == "dev" else "other"] += 1
        s = b.get("state")
        x["n_cancel"] += s in ("canceled", "canceling", "skipped")
        x["n_fail"] += s in ("failed", "failing")
        for j in b.get("jobs") or []:
            if j.get("type") != "script":
                continue
            v = jmin(j.get("started_at"), j.get("finished_at"))
            x["total"] += v
            if j.get("retried"):
                x["rerun"] += v
                x["n_rerun"] += 1
                continue
            js = j.get("state")
            x["cancelled" if js in ("canceled", "canceling") else "failed" if js in ("failed", "timed_out") else "ok"] += v
    out = []
    for (hw, sysn, name), v in rows.items():
        v["versions"] = sorted(v["versions"])
        jpr = v.pop("jobs_per_run")
        out.append(dict(hw=hw, sys=sysn, name=name, jobs_per_run=round(sum(jpr) / len(jpr), 1) if jpr else None,
                        **{k: (round(vv, 1) if isinstance(vv, float) else vv) for k, vv in v.items()}))
    out.sort(key=lambda x: -x["total"])
    tot = collections.defaultdict(float)
    for x in out:
        for k in ("total", "ok", "failed", "cancelled", "rerun"):
            tot[f"{x['hw']}_{k}"] += x[k]
    first = min((r["created_at"] for r in O.get("gha") or [] if r.get("created_at")), default=O.get("since"))
    span_h = max(1.0, (dt(O["at"]) - dt(first)).total_seconds() / 3600) if O.get("at") and first else float(O.get("hours") or 24)
    return dict(rows=out, tot={k: round(v, 1) for k, v in tot.items()}, os=dict((k, round(v)) for k, v in os_min.items()),
                at=O.get("at"), since=O.get("since"), first=first, span_h=round(span_h, 1), per_day=24 / span_h,
                n_gha=len(O.get("gha") or []), n_bk=len(O.get("bk") or []), errors=O.get("errors") or [])


STAGES3 = [("created", ["Pre-merge CI (every push)", "CI trước merge (mỗi lần push)"]), ("approve", ["Approval gate ('full' label → MP suite)", "Cổng duyệt (nhãn 'full' → bộ MP)"]),
           ("merge", ["Post-merge (dev, nightly, publish)", "Sau merge (dev, nightly, publish)"])]


def stage_costs(O):
    """Job-minutes per day in each PR stage, split CPU (GitHub Actions) / GPU (Buildkite k3 + other accelerators).
    created = PR-triggered runs except the MP GPU suite; approve = k3-multiprocess-test on PRs (starts after review with
    the 'full' label); merge = runs on dev pushes, schedules and tags."""
    if not O:
        return None
    first = min((r["created_at"] for r in O.get("gha") or [] if r.get("created_at")), default=O.get("since"))
    span = max(1.0, (dt(O["at"]) - dt(first)).total_seconds() / 3600) if O.get("at") and first else 24.0
    k = 24 / span
    cell = {(st, hw): dict(total=0.0, cancelled=0.0, failed=0.0, runs=0, top=collections.Counter()) for st, _ in STAGES3 for hw in ("CPU", "GPU")}
    for r in O.get("gha") or []:
        ev = r.get("event")
        st = "created" if ev in ("pull_request", "pull_request_target") else "merge" if ev in ("push", "schedule", "workflow_dispatch", "release") else None
        if not st:
            continue
        c = cell[(st, "CPU")]
        c["runs"] += 1
        for j in r.get("jobs") or []:
            v = jmin(j.get("started_at"), j.get("completed_at"))
            c["total"] += v
            c["top"][r["name"]] += v
            jc = j.get("conclusion")
            c["cancelled" if jc == "cancelled" else "failed" if jc in ("failure", "timed_out") else "x"] = c.get("cancelled" if jc == "cancelled" else "failed" if jc in ("failure", "timed_out") else "x", 0) + v
    for b in O.get("bk") or []:
        slug = (b.get("pipeline") or {}).get("slug") or "?"
        if not (slug.startswith("k3-") or re.match(r"(amd|xpu|musa|rbln|metax|unit-tests-)", slug)):
            continue
        st = ("approve" if slug == "k3-multiprocess-test" else "created") if b.get("pull_request") else "merge"
        c = cell[(st, "GPU")]
        c["runs"] += 1
        for j in b.get("jobs") or []:
            if j.get("type") != "script":
                continue
            v = jmin(j.get("started_at"), j.get("finished_at"))
            c["total"] += v
            c["top"][slug] += v
            js = j.get("state")
            if js in ("canceled", "canceling"):
                c["cancelled"] += v
            elif js in ("failed", "timed_out"):
                c["failed"] += v
    out = {}
    for (st, hw), c in cell.items():
        out[f"{st}|{hw}"] = dict(total=round(c["total"] * k), cancelled=round(c["cancelled"] * k), failed=round(c["failed"] * k), runs=round(c["runs"] * k),
                                 top=[[n, round(v * k)] for n, v in c["top"].most_common(3)])
    return dict(cells=out, stages=[dict(id=i, name=n) for i, n in STAGES3], span_h=round(span, 1), stamp=sample_stamp(O))


WD = [("Mon", "Thứ hai"), ("Tue", "Thứ ba"), ("Wed", "Thứ tư"), ("Thu", "Thứ năm"), ("Fri", "Thứ sáu"), ("Sat", "Thứ bảy"), ("Sun", "Chủ nhật")]


def sample_stamp(O):
    """Round 2 G2: when the 24 h sample was taken, and which weekdays it covers (EN, VI)."""
    if not O or not O.get("at"):
        return None
    to = dt(O["at"])
    first = min((r["created_at"] for r in O.get("gha") or [] if r.get("created_at")), default=O.get("since"))
    fr = dt(first) if first else to - timedelta(hours=24)
    a, b = WD[fr.weekday()], WD[to.weekday()]
    return dict(at=O["at"], date=O["at"][:10], wd=[f"{a[0]} → {b[0]}" if a != b else a[0], f"{a[1]} → {b[1]}" if a != b else a[1]])


_S30 = {}


def stage_costs_30d():
    """Round 2 G2: the same PR-stage cells as stage_costs(), from the baseline CSVs (baseline.py: the folder the CI Baseline tab reads), as
    job-min per day: mean, median and the lowest / highest 7-day mean (the range shown as the headline).
    GitHub Actions: gh_jobs_30d.csv exec_min of PR-event jobs (created|CPU). Buildkite: jobs_all_30d.csv wall_min
    (job-min, not GPU-min, to match the 24 h cells): k3-unit-tests PR builds = created|GPU, k3-multiprocess-test PR
    builds = approve|GPU, non-PR k3 builds = merge|GPU. Post-merge GitHub Actions runs are not in the 30-day files.
    Also the 'Run 2 Python versions' saving of the Test workflow, per PR run: version legs x (n - 2) / n."""
    if "v" in _S30:
        return _S30["v"]
    import csv
    import statistics
    import baseline   # the same folder as the CI Baseline tab (build_report1130): one window, one set of totals
    base, src = baseline.folder(), baseline.pick()
    try:
        lo, hi = baseline.data_range(base)   # the days the data covers: the same window as the CI Baseline tab
        d0, d1 = datetime.fromisoformat(lo[:10]).date(), datetime.fromisoformat(hi[:10]).date()
        days = [str(d0 + timedelta(days=i)) for i in range((d1 - d0).days)]
        cells = collections.defaultdict(collections.Counter)
        runs = collections.defaultdict(list)
        for r in csv.DictReader(open(os.path.join(base, "gh_jobs_30d.csv"), encoding="utf-8")):
            if r["event"] not in ("pull_request", "pull_request_target"):
                continue
            st, v = (r["started"] or "")[:10], float(r["exec_min"] or 0)
            cells["created|CPU"][st] += v
            m = re.match(r"test: (3\.\d+)", r["job"] or "")
            if r["workflow"] == "Test" and m:
                runs[r["run_url"]].append((st, m.group(1), v))
        for r in csv.DictReader(open(os.path.join(base, "jobs_all_30d.csv"), encoding="utf-8")):
            k = ("approve|GPU" if r["pipeline"] == "k3-multiprocess-test" else "created|GPU") if r["is_pr"] == "1" else "merge|GPU"
            cells[k][(r["started_at"] or "")[:10]] += float(r["wall_min"] or 0)
    except (OSError, KeyError, ValueError):
        _S30["v"] = None
        return None

    def summ(c):
        s = [c.get(d, 0.0) for d in days]
        r7 = [sum(s[i:i + 7]) / 7 for i in range(len(s) - 6)] or [sum(s) / max(1, len(s))]
        return dict(mean=round(sum(s) / len(s)), median=round(statistics.median(s)), lo=round(min(r7)), hi=round(max(r7)),
                    dmin=round(min(s)), dmax=round(max(s)))
    save, legs, n_legs, vers = collections.Counter(), 0.0, 0, set()
    for L in runs.values():
        n = len({x[1] for x in L})
        vers |= {x[1] for x in L}
        legs += sum(x[2] for x in L)
        n_legs += len(L)
        if n > 2:
            save[L[0][0]] += sum(x[2] for x in L) * (n - 2) / n
    cs = {k: summ(c) for k, c in cells.items()}
    if "created|GPU" in cs:
        cs["created|GPU"]["scope"] = ["k3-unit-tests only; the sample also has the accelerator suites", "chỉ k3-unit-tests; mẫu có thêm các bộ accelerator"]
    out = dict(window=[days[0], days[-1]], n_days=len(days), src=src, cells=cs,
               matrix=dict(workflow="Test", runs=len(runs), versions=sorted(vers, key=lambda x: int(x.split(".")[1])), leg_min=r1(legs / max(1, n_legs)),
                           legs_per_run=r1(n_legs / max(1, len(runs))), **summ(save)))
    _S30["v"] = out
    return out


def opportunities(cost, O, open_prs, files, snap_nodes):
    """Ranked list of things that save CI minutes or raise PR throughput. Every item: evidence (measured),
    saving per day (job-min, estimate method stated), and why it helps."""
    if not cost:
        return []
    k = cost["per_day"]
    ops = []

    def add(id_, area, stage, title, evidence, save, basis, why, lvl):
        ops.append(dict(id=id_, area=area, stage=stage, title=title, evidence=evidence, save=round(save) if save is not None else None,
                        basis=basis, why=why, lvl=lvl))

    # 1) runs started by dev pushes / schedules that end cancelled (superseded before they finish)
    for r in cost["rows"]:
        if r["sys"] != "GitHub Actions" or r["push"] < 3:
            continue
        push_share = r["push"] / r["runs"]
        if r["n_cancel"] >= 3 and r["cancelled"] * k >= 300 and push_share >= .5:
            add(f"sup-{r['name']}", "CPU", "dev push", [f"Stop superseded '{r['name']}' runs on dev", f"Không chạy '{r['name']}' trên dev khi push mới đè lên"],
                [f"{r['n_cancel']} of {r['runs']} runs cancelled ({r['push']} from dev push / schedule); {round(r['cancelled'])} job-min spent before the cancel.",
                 f"{r['n_cancel']} / {r['runs']} lần chạy bị huỷ ({r['push']} từ push dev / lịch); {round(r['cancelled'])} phút job đã chạy trước khi huỷ."],
                r["cancelled"] * k, ["= cancelled job-min, scaled to 24 h", "= phút job bị huỷ, quy về 24 giờ"],
                [f"Every dev push starts it and the next push cancels it after about {round(r['cancelled'] / max(1, r['n_cancel']))} job-min. Running it only on tags / nightly, or a concurrency group that cancels before the heavy jobs start, gives the same result for less.",
                 f"Mỗi push vào dev đều chạy nó và push sau huỷ nó khi đã tốn khoảng {round(r['cancelled'] / max(1, r['n_cancel']))} phút job. Chỉ chạy khi có tag / nightly, hoặc concurrency group huỷ trước khi job nặng chạy, cho cùng kết quả mà rẻ hơn."],
                "bad" if r["cancelled"] * k >= 1500 else "warn")
    # 2) wide Python matrix on PRs
    for r in cost["rows"]:
        if r["sys"] == "GitHub Actions" and len(r["versions"]) >= 4 and r["pr"] >= 5:
            per = (r["ok"] + r["failed"]) / max(1, r["runs"])
            keep = 2 / len(r["versions"])
            save = (r["ok"] + r["failed"]) * (r["pr"] / r["runs"]) * (1 - keep) * k
            add(f"matrix-{r['name']}", "CPU", "Open PR", [f"Run 2 Python versions of '{r['name']}' on PRs, all {len(r['versions'])} on release",
                                                         f"Chạy 2 phiên bản Python của '{r['name']}' cho PR, đủ {len(r['versions'])} khi release"],
                [f"{r['pr']} PR runs × {len(r['versions'])} versions ({', '.join(r['versions'])}); about {round(per)} job-min per run.",
                 f"{r['pr']} lần chạy PR × {len(r['versions'])} phiên bản ({', '.join(r['versions'])}); khoảng {round(per)} phút job mỗi lần."],
                save, [f"= PR job-min × {len(r['versions']) - 2}/{len(r['versions'])}, scaled to 24 h", f"= phút job PR × {len(r['versions']) - 2}/{len(r['versions'])}, quy về 24 giờ"],
                ["Failures here are not Python-version specific (Release Exploration · CPU tests · Findings, #cpu/findings), so the oldest + newest version catch the same bugs on a PR. The release still runs every version.",
                 "Lỗi ở đây không phụ thuộc phiên bản Python (Khám phá Release · test CPU · Phát hiện, #cpu/findings), nên bản cũ nhất + mới nhất bắt cùng bug ở PR. Khi release vẫn chạy đủ."],
                "warn")
    # 3) re-runs (same commit, spent again)
    rr = [r for r in cost["rows"] if r["rerun"] * k >= 60]
    if rr:
        tot_rr = sum(r["rerun"] for r in rr)
        top = sorted(rr, key=lambda r: -r["rerun"])[:3]
        add("rerun", "CPU+GPU", "PR + nightly" if any(r["push"] for r in top) else "Open PR", ["Cut re-runs of the same commit (PR / nightly retries)", "Giảm chạy lại cùng commit (retry ở PR / nightly)"],
            ["Re-run job-min: " + ", ".join(f"{r['name']} {round(r['rerun'])}" for r in top) + f" (total {round(tot_rr)}).",
             "Phút job chạy lại: " + ", ".join(f"{r['name']} {round(r['rerun'])}" for r in top) + f" (tổng {round(tot_rr)})."],
            tot_rr * k, ["= job-min of earlier attempts / retried jobs, scaled to 24 h", "= phút job của các lần thử trước / job retry, quy về 24 giờ"],
            ["A re-run tests the same code again; the minutes only buy a second opinion on a flaky test. Quarantining known flaky tests removes the need.",
             "Chạy lại là test lại cùng code; số phút chỉ để có ý kiến thứ hai cho test flaky. Cách ly test flaky đã biết sẽ bỏ được nhu cầu này."],
            "warn")
    # 4) GPU on commits whose DCO / lint already failed
    heads = {n["number"]: ((n.get("commits") or {}).get("nodes") or [{}])[0].get("commit", {}).get("oid") for n in snap_nodes}
    bad_cpu = [p for p in open_prs if p["cpu"] == "fail" and p["gpu"] in ("ok", "fail", "run")]
    if bad_cpu:
        shas = {heads.get(p["num"]) for p in bad_cpu} - {None}
        gm = sum(jmin(j.get("started_at"), j.get("finished_at")) for b in O.get("bk") or [] if b.get("commit") in shas
                 for j in b.get("jobs") or [] if j.get("type") == "script")
        add("pregate", "GPU", "Open PR", ["Start GPU checks only after DCO and lint pass", "Chỉ chạy check GPU sau khi DCO và lint pass"],
            [f"{len(bad_cpu)} open PRs ran GPU checks on a commit whose DCO / lint failed (#" + ", #".join(str(p['num']) for p in bad_cpu) + f"); {round(gm)} job-min on those commits in the window.",
             f"{len(bad_cpu)} PR mở chạy check GPU trên commit có DCO / lint fail (#" + ", #".join(str(p['num']) for p in bad_cpu) + f"); {round(gm)} phút job cho các commit đó trong khung."],
            gm * k if gm else None, ["= job-min on those commits (only builds inside the window)", "= phút job trên các commit đó (chỉ build trong khung)"],
            ["The PR must be pushed again anyway (DCO / lint never pass by retrying), so GPU results on that commit are thrown away.",
             "PR đằng nào cũng phải push lại (DCO / lint không tự pass), nên kết quả GPU trên commit đó bị bỏ."],
            "warn")
    # 5) docs-only PRs that still run the GPU pipelines
    docs_prs = {p["num"] for p in open_prs if p["risk"] == "docs"} | {int(n) for n, v in files.items() if v.get("files") and risk(v["files"]) == "docs"}
    dm = collections.Counter()
    for b in O.get("bk") or []:
        pr = (b.get("pull_request") or {}).get("id")
        if pr and int(pr) in docs_prs and (b.get("pipeline") or {}).get("slug", "").startswith("k3-"):
            dm[int(pr)] += sum(jmin(j.get("started_at"), j.get("finished_at")) for j in b.get("jobs") or [] if j.get("type") == "script")
    if dm and sum(dm.values()) >= 1:  # a docs PR that ran k3 for 0 min is no evidence of waste
        add("docs-gpu", "GPU", "Open PR", ["Skip GPU pipelines for docs-only PRs", "Bỏ pipeline GPU cho PR chỉ đổi docs"],
            [f"{len(dm)} docs-only PRs ran k3 GPU pipelines in the window: " + ", ".join(f"#{n} {round(v)} min" for n, v in dm.most_common(4)) + ".",
             f"{len(dm)} PR chỉ đổi docs đã chạy pipeline GPU k3 trong khung: " + ", ".join(f"#{n} {round(v)} phút" for n, v in dm.most_common(4)) + "."],
            sum(dm.values()) * k, ["= k3 job-min of those PRs, scaled to 24 h", "= phút job k3 của các PR đó, quy về 24 giờ"],
            ["Docs cannot break a kernel or the engine path; the lint check already covers them.", "Docs không thể làm hỏng kernel hay đường engine; check lint đã đủ cho chúng."],
            "warn")
    # 6) heaviest GPU pipeline per PR (input for splitting PR-smoke and heavy)
    mp = next((r for r in cost["rows"] if r["name"] == "k3-multiprocess-test"), None)
    if mp and mp["runs"]:
        per = mp["total"] / mp["runs"]
        add("mp-split", "GPU", "Open PR", ["Split k3-multiprocess-test into a PR smoke tier and a nightly heavy tier", "Tách k3-multiprocess-test thành tầng smoke cho PR và tầng nặng chạy nightly"],
            [f"{mp['runs']} builds, {round(mp['total'])} job-min ({round(100 * mp['total'] / max(1, cost['tot'].get('GPU_total', 1)))}% of k3), about {round(per)} job-min per build.",
             f"{mp['runs']} build, {round(mp['total'])} phút job ({round(100 * mp['total'] / max(1, cost['tot'].get('GPU_total', 1)))}% của k3), khoảng {round(per)} phút job mỗi build."],
            None, ["saving depends on the smoke tier; GPU tab section 6 estimates −80% of PR GPU-min", "tiết kiệm phụ thuộc tầng smoke; tab GPU mục 6 ước tính −80% GPU-phút của PR"],
            ["It is the largest GPU cost per PR and runs every workload for any code change. A small smoke tier gives the PR signal; the heavy matrix can run nightly.",
             "Đây là chi phí GPU lớn nhất mỗi PR và chạy mọi workload cho mọi thay đổi code. Tầng smoke nhỏ cho tín hiệu PR; ma trận nặng chạy nightly."],
            "info")
    ops.sort(key=lambda o: (o["save"] is None, -(o["save"] or 0)))
    return ops


# ------------------------------------------------------------------ Optimal CI: goals, directions, solution tracking
# Register an applied solution in optimal_solutions.json (list). Fields:
#   {"id": "<opportunity id shown on the page, e.g. sup-Build and Publish to PyPI>", "title": "...",
#    "applied": "YYYY-MM-DD", "ref": "PR #1234 / commit", "note": "..."}
# The page then shows before (up to 14 days before 'applied') vs after (days after) of the item's tracked metric.
SOL_FILE = os.path.join(HERE, "optimal_solutions.json")
HIST_DIR = os.path.join(HERE, "ops_hist")   # one CI-cost summary per collector day (written by main())

GOALS = {"throughput": ["Goal 1 · PR throughput", "Mục tiêu 1 · Throughput PR"], "adapt": ["Goal 2 · Adapt feature changes in the PR", "Mục tiêu 2 · Điều chỉnh thay đổi trong PR"],
         "cost": ["CI cost", "Chi phí CI"]}


def report_daily(days, key):
    """One value per report day for a tracked report metric."""
    out = []
    for d in days:
        if key == "throughput":
            v = d.get("merged") or 0
        elif key == "first_pass":
            ok, fl_ = d.get("fp_ok") or 0, d.get("fp_fail") or 0
            v = round(100 * ok / (ok + fl_), 1) if ok + fl_ else None
        else:
            src = {"ttm": "ttm_h", "k3u_runs": "pr_ci_runs", "feedback": "k3u_ttr", "queue": "k3u_wait"}[key]
            v = pct(d.get(src) or [], .5)
        if v is not None:
            out.append((d["d"], v))
    return out


def save_hist(cost, extras=None):
    if not cost or not cost.get("at"):
        return
    os.makedirs(HIST_DIR, exist_ok=True)
    k = cost["per_day"]
    rows = {r["name"]: {f: round(r[f] * k, 1) for f in ("total", "cancelled", "failed", "rerun")} for r in cost["rows"]}
    tot = {kk: round(v * k, 1) for kk, v in cost["tot"].items()}
    with open(os.path.join(HIST_DIR, cost["at"][:10] + ".json"), "w", encoding="utf-8") as f:
        json.dump(dict(date=cost["at"][:10], at=cost["at"], span_h=cost["span_h"], rows=rows, tot=tot, extras=extras or {}), f, indent=1)


def load_hist():
    out = []
    if os.path.isdir(HIST_DIR):
        for fn in sorted(os.listdir(HIST_DIR)):
            if fn.endswith(".json"):
                h = load(os.path.join(HIST_DIR, fn))
                if h:
                    out.append(h)
    return out


def track_series(track, days, hist):
    if not track:
        return []
    if track["kind"] == "report":
        return report_daily(days, track["key"])
    if track["kind"] == "workflow":
        return [(h["date"], (h["rows"].get(track["name"]) or {}).get(track["field"], 0)) for h in hist]
    if track["kind"] == "tot":
        return [(h["date"], h["tot"].get(track["key"], 0)) for h in hist]
    if track["kind"] == "extra":
        return [(h["date"], (h.get("extras") or {}).get(track["key"])) for h in hist if (h.get("extras") or {}).get(track["key"]) is not None]
    return []


def track_result(track, days, hist, applied):
    ser = track_series(track, days, hist)
    last = [v for _, v in ser[-7:]] if track and track["kind"] == "report" else [v for _, v in ser[-1:]]
    now = round(sum(last) / len(last), 1) if last else None  # report metrics: mean of the last 7 days
    res = dict(now=now, now_at=ser[-1][0] if ser else None, unit=track.get("unit", ""), metric=track.get("label"), better=track.get("better", "down"))
    if applied:
        b = [v for d_, v in ser if d_ < applied][-14:]
        a = [v for d_, v in ser if d_ > applied]
        res.update(applied=applied, before=round(sum(b) / len(b), 1) if b else None, after=round(sum(a) / len(a), 1) if a else None,
                   n_before=len(b), n_after=len(a))
        if res["before"] and res["after"] is not None:
            res["change_pct"] = round(100 * (res["after"] - res["before"]) / res["before"], 1)
    return res


# Where each public-CI / PR item sits and what it is measured by
def tag_ops(ops):
    for o in ops:
        i = o["id"]
        if i.startswith("sup-"):
            o.update(dir="public", stage="dev push", goals=["cost"], track=dict(kind="workflow", name=i[4:], field="cancelled", unit="job-min/day",
                     label=["cancelled job-min/day of this workflow", "phút job bị huỷ / ngày của workflow này"]))
        elif i.startswith("matrix-"):
            o.update(dir="public", stage="create", goals=["cost", "adapt"], track=dict(kind="workflow", name=i[7:], field="total", unit="job-min/day",
                     label=["job-min/day of this workflow", "phút job / ngày của workflow này"]))
        elif i == "rerun":
            o.update(dir="public", stage="create", goals=["cost", "adapt"], track=dict(kind="tot", key="CPU_rerun", unit="job-min/day",
                     label=["CPU re-run job-min/day", "phút job CPU chạy lại / ngày"]))
        elif i == "pregate":
            o.update(dir="pr", stage="create", goals=["adapt", "cost"], track=dict(kind="report", key="k3u_runs", unit="builds",
                     label=["k3-unit builds per merged PR (p50)", "số build k3-unit mỗi PR đã merge (p50)"]))
        elif i == "docs-gpu":
            o.update(dir="pr", stage="create", goals=["cost"], track=dict(kind="tot", key="GPU_total", unit="job-min/day",
                     label=["k3 GPU job-min/day", "phút job GPU k3 / ngày"]))
        elif i == "mp-split":
            o.update(dir="pr", stage="create", goals=["adapt", "throughput", "cost"], track=dict(kind="workflow", name="k3-multiprocess-test", field="total",
                     unit="job-min/day", label=["k3-multiprocess-test job-min/day", "phút job k3-multiprocess-test / ngày"]))
        o.setdefault("impact", [f"≈{o['save']} job-min/day", f"≈{o['save']} phút job/ngày"] if o.get("save") else None)
    return ops


def pr_opportunities(prs_a, open_prs, base):
    """PR-flow items (Direction A): what slows a PR at Create / Review / Merge."""
    B = {b["key"]: b for b in base}
    ops = []
    def add(id_, stage, goals, title, evidence, impact, why, lvl, track):
        ops.append(dict(id=id_, dir="pr", stage=stage, goals=goals, title=title, evidence=evidence, impact=impact, save=None, basis=None, why=why, lvl=lvl, track=track))
    sub = lambda k: [p for p in open_prs if p["sub"] == k]
    med = lambda ps: r1(pct([p["age_d"] for p in ps], .5))
    fb = B.get("feedback") or {}
    fails = sub("ci_fail")
    if fails or fb.get("value"):
        add("create-feedback", "create", ["adapt"], ["Faster CI feedback per push", "Phản hồi CI nhanh hơn cho mỗi lần push"],
            [f"k3-unit feedback (queue + run) p50 {fb.get('value')} min, p90 {fb.get('p90')} min; {len(fails)} open PRs have a failing required check now.",
             f"Phản hồi k3-unit (chờ + chạy) p50 {fb.get('value')} phút, p90 {fb.get('p90')} phút; {len(fails)} PR mở đang có check bắt buộc fail."],
            [f"{len(fails)} PRs now", f"{len(fails)} PR hiện tại"],
            ["Every review comment means a new push. The author waits for this feedback each round, so shorter feedback directly shortens adapting a PR. Delivered by the CPU pre-gate, the 2-version matrix and the MP split below.",
             "Mỗi góp ý review là một lần push mới. Tác giả chờ phản hồi này mỗi vòng, nên phản hồi nhanh hơn rút ngắn trực tiếp việc điều chỉnh PR. Đạt được nhờ cổng CPU chạy trước, ma trận 2 phiên bản và tách MP bên dưới."],
            "warn", dict(kind="report", key="feedback", unit="min", label=["k3-unit feedback per push, p50 (min)", "phản hồi k3-unit mỗi lần push, p50 (phút)"]))
    wf = sub("wait_full")
    if wf:
        add("review-full", "review", ["throughput"], ["Start k3-multiprocess-test on approval (add 'full' with the approval)", "Chạy k3-multiprocess-test khi duyệt (gắn 'full' cùng lúc duyệt)"],
            [f"{len(wf)} PRs have green CPU + GPU-unit checks but no 'full' label, so the required MP check has not started; median age {med(wf)} d.",
             f"{len(wf)} PR đã xanh CPU + GPU unit nhưng chưa có nhãn 'full', nên check MP bắt buộc chưa chạy; tuổi trung vị {med(wf)} ngày."],
            [f"{len(wf)} PRs", f"{len(wf)} PR"],
            ["Today approval and the MP run are two manual steps in a row: approve, then label, then wait ~3 h for MP. Doing both at once removes one waiting round before merge, without running MP on unreviewed PRs.",
             "Hiện duyệt và chạy MP là hai bước tay nối tiếp: duyệt, gắn nhãn, rồi chờ ~3 giờ cho MP. Làm cùng lúc bỏ được một vòng chờ trước merge, mà không chạy MP cho PR chưa review."],
            "warn", dict(kind="report", key="ttm", unit="h", label=["time to merge p50 (h)", "thời gian tới merge p50 (giờ)"]))
    ad = sub("adapt")
    if ad:
        add("review-adapt", "review", ["adapt"], ["Track 'changes requested' PRs until the author pushes", "Theo dõi PR 'yêu cầu sửa' tới khi tác giả push"],
            [f"{len(ad)} PRs have changes requested; median age {med(ad)} d.", f"{len(ad)} PR được yêu cầu sửa; tuổi trung vị {med(ad)} ngày."],
            [f"{len(ad)} PRs", f"{len(ad)} PR"],
            ["Adapting the feature change in the same PR is where the review loop happens. A reminder after N days without a push keeps the change moving instead of going stale.",
             "Điều chỉnh thay đổi trong cùng PR là nơi vòng review diễn ra. Nhắc sau N ngày không có push giúp thay đổi tiếp tục thay vì bị bỏ quên."],
            "info", dict(kind="report", key="first_pass", unit="%", better="up", label=["PRs green on the first push (%)", "PR xanh ngay lần push đầu (%)"]))
    sk = prs_a.get("skip") or []
    if sk:
        add("review-docs", "review", ["throughput"], ["Merge docs-only PRs without a human approval", "Merge PR chỉ đổi docs không cần người duyệt"],
            [f"{len(sk)} docs-only PRs with every required check green: " + ", ".join(f"#{p['num']}" for p in sk[:5]) + ".",
             f"{len(sk)} PR chỉ đổi docs, mọi check bắt buộc xanh: " + ", ".join(f"#{p['num']}" for p in sk[:5]) + "."],
            [f"{len(sk)} PRs", f"{len(sk)} PR"],
            ["Docs cannot break the code and lint already checks them, so the approval only adds waiting time.", "Docs không làm hỏng code và lint đã kiểm tra, nên bước duyệt chỉ thêm thời gian chờ."],
            "info", dict(kind="report", key="throughput", unit="PRs/day", better="up", label=["PRs merged per day", "PR merge mỗi ngày"]))
    rd = sub("ready")
    if rd:
        add("merge-ready", "merge", ["throughput"], ["Auto-merge approved PRs when every check is green", "Tự merge PR đã duyệt khi mọi check xanh"],
            [f"{len(rd)} approved PRs with green checks are not merged yet: " + ", ".join(f"#{p['num']}" for p in rd[:5]) + ".",
             f"{len(rd)} PR đã duyệt, check xanh nhưng chưa merge: " + ", ".join(f"#{p['num']}" for p in rd[:5]) + "."],
            [f"{len(rd)} PRs", f"{len(rd)} PR"],
            ["Nothing is left to check; the PR waits only for someone to press merge. GitHub auto-merge removes that wait.",
             "Không còn gì để kiểm; PR chỉ chờ người bấm merge. Auto-merge của GitHub bỏ được khoảng chờ đó."],
            "info", dict(kind="report", key="ttm", unit="h", label=["time to merge p50 (h)", "thời gian tới merge p50 (giờ)"]))
    stl = sub("conflict") + sub("old")
    if stl:
        add("merge-stale", "merge", ["throughput"], ["Weekly sweep of conflicting / old PRs (rebase or close)", "Dọn hằng tuần PR xung đột / cũ (rebase hoặc đóng)"],
            [f"{len(sub('conflict'))} PRs have merge conflicts and {len(sub('old'))} are older than 30 days without approval; median age {med(stl)} d.",
             f"{len(sub('conflict'))} PR xung đột merge và {len(sub('old'))} PR cũ hơn 30 ngày chưa được duyệt; tuổi trung vị {med(stl)} ngày."],
            [f"{len(stl)} stale / conflicting PRs", f"{len(stl)} PR cũ / xung đột"],
            ["Stale PRs hide the live queue and get re-run by CI on every rebase. Closing or rebasing them keeps review focused on PRs that can merge.",
             "PR cũ che hàng đợi thật và bị CI chạy lại mỗi lần rebase. Đóng hoặc rebase giúp review tập trung vào PR có thể merge."],
            "info", dict(kind="report", key="throughput", unit="PRs/day", better="up", label=["PRs merged per day", "PR merge mỗi ngày"]))
    return ops


def solution_status(ops, days, hist, base=None):
    sols = {s["id"]: s for s in (load(SOL_FILE, []) or []) if s.get("id")}
    for o in ops:
        s = sols.get(o["id"])
        o["solution"] = s
        o["result"] = r = track_result(o.get("track"), days, hist, (s or {}).get("applied"))
        if s and s.get("baseline") is not None and r.get("before") is None:
            r["before"] = s["baseline"]  # frozen by apply_solution.py on the day it was applied
            if r.get("after") is not None and s["baseline"]:
                r["change_pct"] = round(100 * (r["after"] - s["baseline"]) / s["baseline"], 1)
        tk = o.get("track") or {}
        b = (base or {}).get(tk.get("key")) if tk.get("kind") == "report" else None
        if b and b.get("value") is not None:
            r["now"] = b["value"]  # same 30-day value as the goal cards
        if r.get("now") is not None and "min/day" in (r.get("unit") or ""):
            r["now"] = round(r["now"])
    extra = [s for i, s in sols.items() if i not in {o["id"] for o in ops}]
    return extra


# ------------------------------------------------------------------ Optimal CI v3 (spec 2026-11-10, reader = team lead)
# Goal 1 = PR throughput (review is optional once CI is green). Goal 2 = CI stays optimized but still covers LMCache
# features when they change. CI cost is a means, shown as the benefit of a solution. Direction A = PR flow,
# Direction B = public CI (publish.yml + nightly_build.yml). "Better" = better than the previous 30 days.
PUBLIC_WF = ["Build and Publish to PyPI", "Build nightly container image of latest code"]


def git_window_prs(days_back, days_to):
    head = (git("log", "-1", "--format=%cI", "origin/dev") or "").strip()
    if not head:
        return None
    h = dt(head)
    out = git("log", "--format=__C__|%cI|%s", "--name-only", f"--since={(h - timedelta(days=days_back)).isoformat()}", "origin/dev") or ""
    prs, cur = [], None
    for ln in out.splitlines():
        if ln.startswith("__C__|"):
            _, at_, subj = ln.split("|", 2)
            m = re.search(r"\(#(\d+)\)\s*$", subj)
            cur = dict(num=int(m.group(1)) if m else None, at=at_, title=re.sub(r"\s*\(#\d+\)\s*$", "", subj), files=[])
            if h - timedelta(days=days_back) <= dt(at_) < h - timedelta(days=days_to):
                prs.append(cur)
        elif ln.strip() and cur:
            cur["files"].append(ln.strip())
    return prs


def has_tests(files):
    return any(f.startswith("tests/") or "/tests/" in f or re.search(r"(^|/)test_[^/]+\.py$", f) for f in files)


def verdict_row(key, en, vi, now, prev, unit, better, note=None, force=None):
    if force:
        st = force
    elif now is None or prev in (None, 0):
        st = "info"
    else:
        d = (now - prev) / prev * 100
        good = d > 0 if better == "up" else d < 0
        st = "same" if abs(d) < 3 else "better" if good else "worse"
    return dict(key=key, label=[en, vi], now=now, prev=prev, unit=unit, better=better, state=st, note=note)


def optimal_v3(base, prs_a, open_prs, ops, rm, sc, G, coming, cost):
    B = {b["key"]: b for b in base}
    st = collections.Counter(p["sub"] for p in open_prs)
    green = [p for p in open_prs if p["sub"] in ("wait_review", "wait_full", "ready")]
    g1 = [verdict_row("throughput", "PRs merged per day", "PR merge mỗi ngày", (B.get("throughput") or {}).get("value"), (B.get("throughput") or {}).get("prev"), "/day", "up"),
          verdict_row("ttm", "Time from opening a PR to merge (p50)", "Thời gian từ lúc mở PR tới merge (p50)", (B.get("ttm") or {}).get("value"), (B.get("ttm") or {}).get("prev"), "h", "down",
                      [f"p90 {(B.get('ttm') or {}).get('p90')} h (old PRs pull it up)", f"p90 {(B.get('ttm') or {}).get('p90')} giờ (PR cũ kéo số này lên)"]),
          verdict_row("ttm_p90", "Time to merge for the slowest 10% (p90)", "Thời gian tới merge của 10% chậm nhất (p90)", (B.get("ttm") or {}).get("p90"), (B.get("ttm") or {}).get("p90_prev"), "h", "down"),
          verdict_row("green_wait", "PRs with green CI still waiting to merge (now)", "PR đã xanh CI vẫn chờ merge (hiện tại)", len(green), None, "PRs", "down",
                      [f"median age {r1(pct([p['age_d'] for p in green], .5))} d; {st['wait_full']} wait for the 'full' label", f"tuổi trung vị {r1(pct([p['age_d'] for p in green], .5))} ngày; {st['wait_full']} chờ nhãn 'full'"],
                      force="watch" if len(green) >= 10 else None)]
    cur, prev = git_window_prs(30, 0), git_window_prs(60, 30)
    g2, feat_no_test = [], []
    if cur is not None:
        def share(ps, kinds=None, risks=None):
            sel = [p for p in ps if p["num"] and ((kinds and ptype(p["title"]) in kinds) or (risks and risk(p["files"]) in risks))]
            return (round(100 * sum(has_tests(p["files"]) for p in sel) / len(sel), 1) if sel else None), sel
        cs, csel = share(cur, risks=("core", "gpu"))
        ps_, _ = share(prev or [], risks=("core", "gpu"))
        fs, fsel = share(cur, kinds=("feature", "perf"))
        fp, _ = share(prev or [], kinds=("feature", "perf"))
        feat_no_test = [p for p in fsel if not has_tests(p["files"])]
        g2.append(verdict_row("code_tests", "Code PRs that change tests in the same PR (30 d)", "PR đổi code có đổi test trong cùng PR (30 ngày)", cs, ps_, "%", "up",
                              [f"{len(csel)} code PRs (core or GPU path)", f"{len(csel)} PR đổi code (core hoặc đường GPU)"]))
        g2.append(verdict_row("feat_tests", "Feature PRs that change tests in the same PR (30 d)", "PR feature có đổi test trong cùng PR (30 ngày)", fs, fp, "%", "up",
                              [f"{len(fsel)} feature / perf PRs; {len(feat_no_test)} without tests", f"{len(fsel)} PR feature / perf; {len(feat_no_test)} PR không có test"]))
    # roadmap features (external list) and whether their PRs carry tests
    feats = []
    if rm and sc:
        byf = {p["num"]: p["files"] for p in sc["prs"] if p["num"]}
        for it in rm["items"]:
            if sec_type(it["section"]) not in ("feature", "breaking", None):
                continue
            nums = [p["num"] for p in it["prs"]]
            cov = any(has_tests(byf.get(n, [])) for n in nums)
            feats.append(dict(text=it["text"], prs=nums, covered=cov))
        nf = sum(1 for f in feats if f["covered"])
        g2.append(verdict_row("roadmap_cov", f"Roadmap features ({rm['src']['rel']}) whose PRs carry tests", f"Feature trong roadmap ({rm['src']['rel']}) có test trong PR", nf, None, f"of {len(feats)}", "up",
                              ["daily-meeting feature notes: not provided yet", "ghi chú feature từ daily meeting: chưa có"]))
    red = coming.get("dev_red") or []
    gate_red = [d["pipeline"] for d in red if d["pipeline"] in GATE_PIPES]
    g2.append(verdict_row("dev_red", "dev pipelines red now (bugs that got past PR CI)", "Pipeline dev đang đỏ (lỗi lọt qua CI của PR)", len(red), None, "", "down",
                          [", ".join(d["pipeline"] for d in red) or "none", ", ".join(d["pipeline"] for d in red) or "không có"],
                          force="worse" if gate_red else "watch" if red else "same"))
    nr0 = G.get("nightly_runs") or []
    nfail0 = sum(1 for r in nr0 if r.get("conclusion") == "failure")
    if nr0:
        g2.append(verdict_row("nightly", "Nightly build: failed runs of the last 10 (the full test matrix runs there)", "Nightly build: số lần fail trong 10 lần gần nhất (nơi chạy đủ bộ test)", nfail0, None, f"of {len(nr0)}", "down",
                              None, force="worse" if nfail0 >= len(nr0) / 2 else "watch" if nfail0 else "same"))

    # ---- actions: reframe the agent-found solutions to the two goals
    acts = []
    span = (cost or {}).get("span_h")
    sample_stamp_v = sample_stamp(dict(at=(cost or {}).get("at"), since=(cost or {}).get("first") or (cost or {}).get("since"))) if (cost or {}).get("at") else None
    s30 = stage_costs_30d()
    def act(o, goal, dir_, stage, title=None, benefit=None, guard=None):
        a = dict(o)
        a.update(goal=goal, dir=dir_, stage=stage, guard=guard)
        if o.get("goals") and set(o["goals"]) <= {"cost"} and o.get("why"):
            a["why"] = ["Goal 1 link: fewer runner minutes means shorter queues, so PR checks finish sooner. " + o["why"][0],
                        "Liên quan mục tiêu 1: ít phút runner hơn thì hàng đợi ngắn hơn, check của PR xong sớm hơn. " + o["why"][1]]
        if benefit and "job-min" in benefit[0] and span:
            ss = sample_stamp_v or {}
            benefit = [benefit[0] + f" (one {span} h sample to {ss.get('date', '?')}, {(ss.get('wd') or ['?'])[0]})",
                       benefit[1] + f" (một mẫu {span} giờ tới {ss.get('date', '?')}, {(ss.get('wd') or ['?', '?'])[1]})"]
        if title:
            a["title"] = title
        a["benefit"] = benefit or (o.get("impact") if o.get("impact") else None)
        acts.append(a)
    byid = {o["id"]: o for o in ops}
    for o in ops:
        i = o["id"]
        if i.startswith("sup-"):
            wf = i[4:]
            act(o, 1, "B" if wf in PUBLIC_WF else "B*", "dev push",
                benefit=[f"frees ≈{o['save']} job-min/day", f"giải phóng ≈{o['save']} phút job/ngày"])
        elif i.startswith("matrix-"):
            act(o, 1, "A", "create", benefit=[f"frees ≈{o['save']} job-min/day", f"giải phóng ≈{o['save']} phút job/ngày"],
                guard=["Goal 2 guard: the release and nightly still run every Python version.", "Giữ mục tiêu 2: release và nightly vẫn chạy đủ mọi phiên bản Python."])
            m30 = (s30 or {}).get("matrix")
            if m30 and i == "matrix-" + m30["workflow"]:
                # round 2 G2: headline = 30-day range; the 24 h sample stays as a secondary figure
                w0, w1 = s30["window"]
                smp = acts[-1]["benefit"]
                acts[-1]["benefit"] = [f"frees ≈{m30['lo']:,}–{m30['hi']:,} job-min/day (lowest–highest 7-day mean, 30 d {w0} → {w1}; mean {m30['mean']:,}) · secondary: {smp[0]}",
                                       f"giải phóng ≈{m30['lo']:,}–{m30['hi']:,} phút job/ngày (trung bình 7 ngày thấp nhất–cao nhất, 30 ngày {w0} → {w1}; trung bình {m30['mean']:,}) · phụ: {smp[1]}"]
                acts[-1]["save"] = m30["mean"]
                ev = acts[-1].get("evidence") or ["", ""]
                acts[-1]["evidence"] = [ev[0] + f" 30 d: {m30['runs']:,} PR runs, {m30['legs_per_run']} version legs per run ({', '.join(m30['versions'])}), ≈{m30['leg_min']} job-min per leg.",
                                        ev[1] + f" 30 ngày: {m30['runs']:,} lần chạy PR, {m30['legs_per_run']} nhánh phiên bản mỗi lần ({', '.join(m30['versions'])}), ≈{m30['leg_min']} phút job mỗi nhánh."]
        elif i == "rerun":
            act(o, 1, "A+B", "create", benefit=[f"frees ≈{o['save']} job-min/day", f"giải phóng ≈{o['save']} phút job/ngày"])
        elif i in ("pregate", "docs-gpu", "create-feedback"):
            act(o, 1, "A", "create")
        elif i == "mp-split":
            act(o, 1, "A", "create", guard=["Goal 2 guard: the smoke tier must include a workload for every feature on the roadmap; the full matrix still runs nightly.",
                                             "Giữ mục tiêu 2: tầng smoke phải có workload cho mọi feature trong roadmap; ma trận đầy đủ vẫn chạy nightly."])
        elif i == "merge-stale":
            act(o, 1, "A", "merge")
    gw = [p for p in open_prs if p["sub"] in ("wait_review", "wait_full", "ready")]
    if gw:
        base_o = byid.get("review-full") or byid.get("merge-ready") or {}
        act(dict(id="merge-green", lvl="bad" if len(gw) >= 10 else "warn", track=base_o.get("track") or dict(kind="report", key="ttm", unit="h", label=["time to merge p50 (h)", "thời gian tới merge p50 (giờ)"]),
                 result=base_o.get("result") or {}, solution=base_o.get("solution"),
                 title=["Merge a PR as soon as all required CI is green (human review optional)", "Merge PR ngay khi mọi CI bắt buộc xanh (người review là tuỳ chọn)"],
                 evidence=[f"{len(gw)} PRs have green CPU + GPU-unit checks and still wait: {st['wait_full']} for the 'full' label that starts k3-multiprocess-test, {st['wait_review']} for a review, {st['ready']} approved but not merged. Median age {r1(pct([p['age_d'] for p in gw], .5))} d. Sample: {len(open_prs)} non-draft PRs among the 100 most recently updated, not all open PRs.",
                           f"{len(gw)} PR đã xanh CPU + GPU unit vẫn đang chờ: {st['wait_full']} chờ nhãn 'full' để chạy k3-multiprocess-test, {st['wait_review']} chờ review, {st['ready']} đã duyệt nhưng chưa merge. Tuổi trung vị {r1(pct([p['age_d'] for p in gw], .5))} ngày. Mẫu: {len(open_prs)} PR không nháp trong 100 PR cập nhật gần nhất, không phải mọi PR mở."],
                 why=["Agreed rule: review is optional once CI is green. Start the last required check automatically (no manual 'full' label) and turn on auto-merge, so a green PR merges the same day.",
                      "Quy tắc đã thống nhất: CI xanh thì review là tuỳ chọn. Tự chạy check bắt buộc cuối cùng (không cần gắn nhãn 'full' tay) và bật auto-merge, để PR xanh được merge trong ngày."]),
            1, "A", "review", benefit=[f"{st['ready']} could merge now; {st['wait_full']} need k3-multiprocess-test (~3 h) first; {st['wait_review']} wait for review only",
                                       f"{st['ready']} PR merge được ngay; {st['wait_full']} PR cần chạy k3-multiprocess-test (~3 giờ) trước; {st['wait_review']} PR chỉ chờ review"])
    if feat_no_test:
        act(dict(id="feat-tests", lvl="warn", track=dict(kind="report", key="throughput", unit="", label=["feature PRs with tests (%)", "PR feature có test (%)"]), result={}, solution=None,
                 title=["Require a test change in feature PRs", "Bắt buộc PR feature có thay đổi test"],
                 evidence=[f"{len(feat_no_test)} feature / perf PRs merged in 30 days had no test change: " + ", ".join(f"#{p['num']}" for p in feat_no_test[:6]) + ".",
                           f"{len(feat_no_test)} PR feature / perf merge trong 30 ngày không đổi test: " + ", ".join(f"#{p['num']}" for p in feat_no_test[:6]) + "."],
                 why=["When CI is cut down (smoke tiers, 2 Python versions), the tests that ship with a feature are what keeps that feature covered. A PR template check or a CI warning makes it visible.",
                      "Khi CI được rút gọn (tầng smoke, 2 phiên bản Python), test đi kèm feature là thứ giữ feature đó được bao phủ. Một check trong PR template hoặc cảnh báo trong CI sẽ làm việc này hiện ra."]),
            2, "A", "create", benefit=[f"{len(feat_no_test)} PR" + ("" if len(feat_no_test) == 1 else "s") + " without tests", f"{len(feat_no_test)} PR không có test"])
    unc = [f for f in feats if not f["covered"]]
    if unc:
        act(dict(id="roadmap-cov", lvl="warn", track=None, result={}, solution=None,
                 title=["Add tests for roadmap features that have none", "Thêm test cho feature trong roadmap chưa có test"],
                 evidence=[f"{len(unc)} of {len(feats)} roadmap features have no test change in their PRs: " + "; ".join(f"{f['text']} (#{', #'.join(map(str, f['prs']))})" for f in unc[:4]) + ".",
                           f"{len(unc)} / {len(feats)} feature trong roadmap không có thay đổi test trong PR: " + "; ".join(f"{f['text']} (#{', #'.join(map(str, f['prs']))})" for f in unc[:4]) + "."],
                 why=["These features ship in the next release. Without a test, an optimized CI has nothing that fails if they break.",
                      "Các feature này ship trong release tới. Không có test thì CI đã tối ưu không có gì báo lỗi nếu chúng hỏng."]),
            2, "A", "create", benefit=[f"{len(unc)} feature" + ("" if len(unc) == 1 else "s") + " without tests", f"{len(unc)} feature chưa có test"])
    nr_ = G.get("nightly_runs") or []
    nf_ = sum(1 for r in nr_ if r.get("conclusion") == "failure")
    if nr_ and nf_ >= len(nr_) / 2:
        act(dict(id="nightly-fix", lvl="bad", track=None, result={}, solution=None,
                 title=["Fix the nightly build first (it is where the full matrix runs)", "Sửa nightly build trước (đây là nơi chạy ma trận đầy đủ)"],
                 evidence=[f"nightly_build.yml: {nf_} of the last {len(nr_)} runs failed; {sum(1 for r in nr_ if r.get('conclusion') == 'success')} passed.",
                           f"nightly_build.yml: {nf_} / {len(nr_)} lần chạy gần nhất fail; {sum(1 for r in nr_ if r.get('conclusion') == 'success')} lần pass."],
                 why=["Every plan to make PR CI lighter moves the heavy checks to nightly. If nightly is red most days, features lose that safety net.",
                      "Mọi kế hoạch làm CI của PR nhẹ hơn đều dời check nặng sang nightly. Nếu nightly đỏ gần như mỗi ngày, feature mất lưới an toàn đó."]),
            2, "B", "nightly", benefit=[f"{nf_}/{len(nr_)} runs red", f"{nf_}/{len(nr_)} lần đỏ"])
    CELL = {"matrix-": ("created", "CPU"), "sup-": ("merge", "CPU"), "rerun": ("merge", "CPU"), "pregate": ("created", "GPU"), "docs-gpu": ("created", "GPU"),
            "create-feedback": ("created", "GPU"), "mp-split": ("approve", "GPU"), "merge-green": ("approve", "GPU"), "merge-stale": ("merge", "-"),
            "nightly-fix": ("merge", "CPU"), "feat-tests": ("created", "CPU"), "roadmap-cov": ("created", "CPU")}
    XTRACK = {"nightly-fix": dict(kind="extra", key="nightly_fail", unit="of 10", label=["failed nightly runs of the last 10", "số lần nightly fail trong 10 lần gần nhất"]),
              "feat-tests": dict(kind="extra", key="feat_tests_pct", unit="%", better="up", label=["feature PRs with tests (30 d, %)", "PR feature có test (30 ngày, %)"]),
              "roadmap-cov": dict(kind="extra", key="roadmap_uncovered", unit="", label=["roadmap features without tests", "feature roadmap chưa có test"]),
              "merge-green": dict(kind="extra", key="green_wait", unit="PRs", label=["PRs with green CI still waiting to merge", "PR xanh CI vẫn chờ merge"])}
    for a in acts:
        a["cell"] = next((v for k_, v in CELL.items() if a["id"].startswith(k_)), ("created", "-"))
        if a["id"] in XTRACK:
            a["track"] = XTRACK[a["id"]]
    extras = dict(nightly_fail=sum(1 for r in (G.get("nightly_runs") or []) if r.get("conclusion") == "failure"),
                  feat_tests_pct=next((r["now"] for r in g2 if r["key"] == "feat_tests"), None),
                  roadmap_uncovered=sum(1 for f in feats if not f["covered"]), green_wait=len(green))
    rank = {"bad": 0, "warn": 1, "info": 2}
    def num(a):
        m = re.search(r"([\d,]+)", (a.get("benefit") or [""])[0])
        return int(m.group(1).replace(",", "")) if m else 0
    acts.sort(key=lambda a: (a["goal"], rank.get(a["lvl"], 3), -num(a)))  # by goal, then priority; units are only compared inside a goal
    # ---- Direction B detail: publish.yml + nightly
    pub = []
    if cost:
        for r in cost["rows"]:
            if r["name"] in PUBLIC_WF:
                pub.append(dict(name=r["name"], runs=r["runs"], cancelled=r["n_cancel"], failed=r["n_fail"], minutes=round(r["total"] * cost["per_day"]),
                                cancelled_min=round(r["cancelled"] * cost["per_day"])))
    nr = G.get("nightly_runs") or []
    nightly10 = dict(n=len(nr), ok=sum(1 for r in nr if r.get("conclusion") == "success"), fail=sum(1 for r in nr if r.get("conclusion") == "failure"))
    def gv(rows):
        sts = [r["state"] for r in rows]
        if "worse" in sts:
            return "mixed" if "better" in sts else "worse"
        if "watch" in sts:
            return "mixed" if "better" in sts else "watch"
        return "better" if "better" in sts else "same"
    return dict(goals=[dict(id=1, name=["Goal 1 · More PRs merged", "Mục tiêu 1 · Merge được nhiều PR hơn"], verdict=gv(g1), rows=g1),
                       dict(id=2, name=["Goal 2 · CI keeps covering features as they change", "Mục tiêu 2 · CI vẫn bao phủ feature khi feature thay đổi"], verdict=gv(g2), rows=g2)],
                actions=acts, features=feats, extras=extras, public=dict(rows=pub, nightly10=nightly10,
                triggers=[["publish.yml: every push to dev / release-**, tags v*, published releases. A dev push cancels the previous dev run.",
                           "publish.yml: mỗi push vào dev / release-**, tag v*, release được publish. Push dev mới huỷ lần chạy dev trước."],
                          ["nightly_build.yml: every day 07:30 UTC (cron) and by hand.", "nightly_build.yml: mỗi ngày 07:30 UTC (cron) và chạy tay."]]))


# ------------------------------------------------------------------ analysis
def analyze():
    S = load(SNAP, {}) or {}
    G, B = S.get("gh") or {}, S.get("bk") or {}
    import observe_history
    H = observe_history.load_all() or {}
    REP = H.get("report") or {}
    O = load(OPS)
    P = load(PROPS, {}) or {}
    at = dt(S.get("at")) or datetime.now(timezone.utc)
    files = {str(k): v for k, v in (G.get("pr_files") or {}).items()}
    fl = lambda n: (files.get(str(n)) or {}).get("files") or []

    # ---- open PRs (dev, not draft): stage, CPU / GPU gate states
    bk_pr = collections.defaultdict(list)
    for s, bs in (B.get("recent") or {}).items():
        for b in bs or []:
            if (b.get("pull_request") or {}).get("id"):
                bk_pr[str(b["pull_request"]["id"])].append(b)
    for b in B.get("active") or []:
        if (b.get("pull_request") or {}).get("id"):
            bk_pr[str(b["pull_request"]["id"])].append(b)
    REQ_NAMES = (REP.get("required_checks") or {}).get("names") or ["DCO", "Check code quality", "buildkite/k3-unit-tests", "buildkite/k3-multiprocess-test"]
    open_prs = []
    for n in (G.get("prs_gql") or {}).get("nodes") or []:
        if n.get("isDraft") or n.get("baseRefName") != "dev":
            continue
        c = ((n.get("commits") or {}).get("nodes") or [{}])[0].get("commit") or {}
        ctx = ((c.get("statusCheckRollup") or {}).get("contexts") or {}).get("nodes") or []
        cs = [((x.get("name") or x.get("context") or ""), ctx_state(x)) for x in ctx]
        # every required check (branch protection) must be present and green; a missing one is NOT green
        req = {nm: worst([s for c_, s in cs if c_ == nm]) or "missing" for nm in REQ_NAMES}
        labs = {x["name"] for x in (n.get("labels") or {}).get("nodes") or []}
        # label-triggered required checks (observed 11-10: MP runs only on PRs labelled 'full'): missing = waiting for the label
        wait_label = [lbs[0] for nm, lbs in LABEL_TRIGGERED.items() if req.get(nm) == "missing" and not (set(lbs) & labs)]
        req_now = {nm: v for nm, v in req.items() if not (nm in LABEL_TRIGGERED and LABEL_TRIGGERED[nm][0] in wait_label)}
        cpu = worst([v for nm, v in req_now.items() if not nm.startswith("buildkite/")]) or "ok"
        gpu = worst([v for nm, v in req_now.items() if nm.startswith("buildkite/")]) or "ok"
        gate = worst([cpu, gpu]) or "ok"
        rv, mg = n.get("reviewDecision"), n.get("mergeable")
        age_d = (at - dt(n["createdAt"])).total_seconds() / 86400
        if mg == "CONFLICTING":
            stage, sub = "stale", "conflict"
        elif age_d > 30 and rv != "APPROVED":
            stage, sub = "stale", "old"
        elif gate in ("fail", "cancel"):
            stage, sub = "ci", "ci_fail"
        elif gate == "missing":
            stage, sub = "ci", "ci_missing"
        elif gate == "run":
            stage, sub = "ci", "ci_run"
        elif rv == "CHANGES_REQUESTED":
            stage, sub = "review", "adapt"
        elif wait_label:
            stage, sub = "review", "wait_full"
        elif rv == "APPROVED":
            stage, sub = "merge", "ready"
        else:
            stage, sub = "review", "wait_review"
        f = fl(n["number"])
        rk = risk(f)
        ci_at = max((b["created_at"] for b in bk_pr.get(str(n["number"]), [])), default=None)
        open_prs.append(dict(num=n["number"], title=n["title"], url=n["url"], author=(n.get("author") or {}).get("login"),
                             created=n["createdAt"], updated=n["updatedAt"], age_d=r1((at - dt(n["createdAt"])).total_seconds() / 86400),
                             type=ptype(n["title"], (n.get("labels") or {}).get("nodes")), labels=[x["name"] for x in (n.get("labels") or {}).get("nodes") or []],
                             milestone=(n.get("milestone") or {}).get("title"), stage=stage, sub=sub, cpu=cpu, gpu=gpu, review=rv,
                             risk=rk, nfiles=len(f), ci_at=ci_at, issues=(files.get(str(n["number"])) or {}).get("issues") or [],
                             req=req, wait_label=wait_label, mergeable=mg, sha=c.get("oid")))

    # ---- coming release
    stable = G.get("merged_since")
    sc = git_scope(stable)  # real scope = <stable tag commit>..origin/dev (tags can sit on an older commit)
    # one open-PR list for every tab: a PR that merged after the PR snapshot (seen in git) is not open any more
    gm0 = git_merged_window(24) if sc else None
    merged_after_snap = sorted(p["num"] for p in open_prs if gm0 and p["num"] in gm0["merged_since_snap"](S.get("at")))
    open_prs = [p for p in open_prs if p["num"] not in merged_after_snap]
    merged = []
    if sc:
        for p in sc["prs"]:
            merged.append(dict(num=p["num"], title=p["title"], url=GH_PR + str(p["num"]) if p["num"] else None, author=p["author"],
                               at=p["at"], type=ptype(p["title"]), risk=risk(p["files"]), nfiles=len(p["files"]), labels=[],
                               dirs=topdirs(p["files"]), ci_only=ci_only(p["files"])))
    else:  # no local clone: fall back to the snapshot search (by publish date, may miss PRs)
        for i in G.get("merged") or []:
            f = fl(i["number"])
            merged.append(dict(num=i["number"], title=i["title"], url=i["html_url"], author=(i.get("user") or {}).get("login"),
                               at=(i.get("pull_request") or {}).get("merged_at"), type=ptype(i["title"], i.get("labels")),
                               risk=risk(f) if f else "unknown", nfiles=len(f), labels=[x["name"] for x in i.get("labels") or []]))
    merged.sort(key=lambda x: x["at"] or "", reverse=True)
    rmp = find_roadmap(stable)
    rm = None
    shipped_tag = None
    if rmp and rmp.exists():
        prm = parse_roadmap(rmp)
        vt = "v" + prm["version"] if prm.get("version") else None
        if sc and vt and vt != stable and git("rev-parse", "--verify", "-q", vt + "^{commit}") is not None:
            # A1: the target release is tagged: what it ships is <stable>..<tag>; later merges go to the next line
            shipped_tag = vt
            after = {p["num"] for p in sc["prs"]} - {p["num"] for p in (git_scope(stable, vt) or {}).get("prs") or []}
            sc = git_scope(stable, vt)
            merged = [m for m in merged if m["num"] not in after]
        rm = roadmap_check(prm, sc, {p["num"] for p in open_prs})
    cand = [p for p in open_prs if p["sub"] in ("ready", "wait_review", "adapt") or (p["milestone"] or "")]
    cand.sort(key=lambda p: ({"ready": 0, "adapt": 1, "wait_review": 2}.get(p["sub"], 3), p["age_d"] or 0))
    # dev health: last finished build per merge-gate / key pipeline on dev
    dev = collections.defaultdict(list)
    for b in B.get("dev_builds") or []:
        dev[(b.get("pipeline") or {}).get("slug")].append(b)
    dev_red = []
    for slug, bs in dev.items():
        fin = sorted((b for b in bs if b["state"] in ("passed", "failed")), key=lambda b: b["created_at"], reverse=True)
        if fin and fin[0]["state"] == "failed":
            dev_red.append(dict(pipeline=slug, build=fin[0]["number"], url=fin[0].get("web_url"), at=fin[0]["created_at"]))
    coming = dict(stable=stable, merged=merged, by_type=collections.Counter(m["type"] for m in merged),
                  candidates=cand[:40], n_cand=len(cand), open_ci_fail=sum(1 for p in open_prs if p["sub"] == "ci_fail"),
                  n_open=len(open_prs), dev_red=dev_red, roadmap=rm,
                  scope=dict(src="git" if sc else "snapshot", tag_sha=(sc or {}).get("tag_sha"), head=(sc or {}).get("head"),
                             end=(sc or {}).get("end"), shipped_tag=shipped_tag,
                             head_at=(sc or {}).get("head_at"), repo=(sc or {}).get("repo")))

    # ---- 30-day baselines (report days: 60 days -> last 30 vs previous 30)
    days = REP.get("days") or []
    if days and str(REP.get("made") or "").startswith(days[-1]["d"]):
        days = days[:-1]  # the report's own day is partial
    cur, prev = days[-30:], days[-60:-30]
    def flat(ds, k):
        return [v for d in ds for v in (d.get(k) or [])]
    def series(ds, k):
        return [d.get(k) or 0 for d in ds]
    def failed_share(ds):
        r, ok = sum(flat(ds, "pr_ci_runs")), sum(flat(ds, "pr_ci_ok_runs"))
        return r1(100 * (r - ok) / r) if r else None
    def m(key, en, vi, unit, ds_val, prev_val, ser=None, p90=None, better="down", d_en="", d_vi="", src=""):
        return dict(key=key, name=[en, vi], unit=unit, value=ds_val, prev=prev_val, series=ser, p90=p90, better=better, defn=[d_en, d_vi], src=src)
    ff = (H.get("measured") or {}).get("fastfail") or {}
    gpu_per_build = (ff.get("mp_pr_gpu_hours") or 0) / (ff.get("mp_pr_builds") or 1)
    base = [
        m("throughput", "PRs merged per day", "PR merge mỗi ngày", "/day", r1(sum(series(cur, "merged")) / max(1, len(cur))), r1(sum(series(prev, "merged")) / max(1, len(prev))),
          series(cur, "merged"), None, "up", "PRs merged into dev, mean per day over 30 days.", "Số PR merge vào dev, trung bình mỗi ngày trong 30 ngày.", "report days.merged"),
        m("ttm", "Time to merge (p50)", "Thời gian tới merge (p50)", "h", r1(pct(flat(cur, "ttm_h"), .5)), r1(pct(flat(prev, "ttm_h"), .5)),
          [r1(pct(d.get("ttm_h") or [], .5)) or 0 for d in cur], r1(pct(flat(cur, "ttm_h"), .9)), "down",
          "Hours from PR opened to merged, for PRs merged in the window.", "Số giờ từ lúc mở PR tới lúc merge, cho các PR merge trong kỳ.", "report days.ttm_h"),
        m("k3u_runs", "k3-unit builds per merged PR (p50)", "Số build k3-unit mỗi PR đã merge (p50)", "", pct(flat(cur, "pr_ci_runs"), .5), pct(flat(prev, "pr_ci_runs"), .5),
          None, pct(flat(cur, "pr_ci_runs"), .9), "down", "Required GPU unit builds (passed or failed) a PR needed before merge. 1 = merged on the first run.",
          "Số build GPU unit bắt buộc (pass hoặc fail) một PR cần trước khi merge. 1 = merge ngay lần chạy đầu.", "report days.pr_ci_runs"),
        m("retry_waste", "k3-unit fail share", "Tỉ lệ build k3-unit fail", "%", failed_share(cur), failed_share(prev), None, None, "down",
          "Failed builds / all k3-unit builds of merged PRs. Includes real bugs caught, so it is an upper bound of retry waste.",
          "Build fail / tổng build k3-unit của các PR đã merge. Có cả lần bắt bug thật, nên là cận trên của lãng phí do retry.", "report days.pr_ci_runs / pr_ci_ok_runs"),
        m("queue", "k3-unit queue wait (p50)", "Thời gian chờ queue k3-unit (p50)", "min", r1(pct(flat(cur, "k3u_wait"), .5)), r1(pct(flat(prev, "k3u_wait"), .5)),
          [r1(pct(d.get("k3u_wait") or [], .9)) or 0 for d in cur], r1(pct(flat(cur, "k3u_wait"), .9)), "down",
          "Minutes a k3-unit job waits for a GPU pod. The median hides the spikes, so read p90 (chart = daily p90).",
          "Số phút job k3-unit chờ GPU pod. Trung vị che các đợt tăng, nên đọc p90 (biểu đồ = p90 mỗi ngày).", "report days.k3u_wait"),
        m("k3u_run", "k3-unit run time (p50)", "Thời gian chạy k3-unit (p50)", "min", r1(pct(flat(cur, "k3u_run"), .5)), r1(pct(flat(prev, "k3u_run"), .5)),
          None, r1(pct(flat(cur, "k3u_run"), .9)), "down", "Minutes from job start to finish.", "Số phút từ lúc job bắt đầu tới lúc xong.", "report days.k3u_run"),
        m("feedback", "CI feedback per push (p50)", "Phản hồi CI mỗi lần push (p50)", "min", r1(pct(flat(cur, "k3u_ttr"), .5)), r1(pct(flat(prev, "k3u_ttr"), .5)),
          [r1(pct(d.get("k3u_ttr") or [], .5)) or 0 for d in cur], r1(pct(flat(cur, "k3u_ttr"), .9)), "down",
          "Minutes from a push to the k3-unit result (queue wait + run). The author waits this long after each review fix.",
          "Số phút từ lúc push tới khi có kết quả k3-unit (chờ + chạy). Tác giả chờ chừng này sau mỗi lần sửa theo review.", "report days.k3u_ttr"),
        m("first_pass", "PRs green on the first push", "PR xanh ngay lần push đầu", "%",
          r1(100 * sum(d.get("fp_ok") or 0 for d in cur) / max(1, sum((d.get("fp_ok") or 0) + (d.get("fp_fail") or 0) for d in cur))),
          r1(100 * sum(d.get("fp_ok") or 0 for d in prev) / max(1, sum((d.get("fp_ok") or 0) + (d.get("fp_fail") or 0) for d in prev))),
          [v for _, v in report_daily(cur, "first_pass")], None, "up",
          "Share of PRs whose first k3-unit build passed. Low = more fix-and-push rounds.", "Tỉ lệ PR có build k3-unit đầu tiên pass. Thấp = nhiều vòng sửa và push hơn.", "report days.fp_ok / fp_fail"),
    ]
    for b_ in base:
        if b_["key"] == "ttm":
            b_["p90_prev"] = r1(pct(flat(prev, "ttm_h"), .9))
    window = [cur[0]["d"], cur[-1]["d"]] if cur else None

    # ---- A. PRs funnel + skip-approval candidates + CPU vs GPU
    st = collections.Counter(p["sub"] for p in open_prs)
    age = lambda ps: r1(pct([p["age_d"] for p in ps], .5))
    stages = [dict(id=s, n=sum(1 for p in open_prs if p["stage"] == s), age=age([p for p in open_prs if p["stage"] == s]),
                   subs={k: st[k] for k in subs}) for s, subs in (("ci", ("ci_run", "ci_missing", "ci_fail")), ("review", ("wait_review", "wait_full", "adapt")), ("merge", ("ready",)), ("stale", ("conflict", "old")))]
    # skip human approval: docs-only AND every required check present and green (tests-only PRs can delete tests)
    skip = [p for p in open_prs if p["risk"] == "docs" and p["sub"] in ("wait_review", "wait_full", "ready")]
    gpu_after_cpu_fail = [p for p in open_prs if p["cpu"] == "fail" and p["gpu"] in ("ok", "fail", "run")]
    # merged in the 7-day window: change class -> could MP GPU have been skipped?
    m7 = []
    for i in G.get("merged_recent") or []:
        f = fl(i["number"])
        if f:
            m7.append(dict(num=i["number"], risk=risk(f), skip_label="skip expensive ci" in [x["name"] for x in i.get("labels") or []]))
    low = [x for x in m7 if x["risk"] in ("docs", "tests")]
    low_no_label = [x for x in low if not x["skip_label"]]
    prs_a = dict(stages=stages, n_open=len(open_prs), skip=skip[:30], n_skip=len(skip), gpu_after_cpu_fail=[p["num"] for p in gpu_after_cpu_fail],
                 risk_open=collections.Counter(p["risk"] for p in open_prs), m7=dict(n=len(m7), low=len(low), low_no_label=len(low_no_label),
                 by_risk=collections.Counter(x["risk"] for x in m7), skip_label=sum(1 for x in m7 if x["skip_label"])),
                 gpu_h_per_mp_build=r1(gpu_per_build), est_gpu_h_week=r1(len(low_no_label) * gpu_per_build))
    cost = ci_costs(O)
    cn = G.get("counts") or {}
    all_ops = tag_ops(opportunities(cost, O or {}, open_prs, files, (G.get("prs_gql") or {}).get("nodes") or [])) + pr_opportunities(prs_a, open_prs, base)
    hist = load_hist()
    if cost and not any(h["date"] == (cost.get("at") or "")[:10] for h in hist):
        save_hist(cost)
        hist = load_hist()
    extra_sol = solution_status(all_ops, days, hist, {b["key"]: b for b in base})
    v3 = optimal_v3(base, prs_a, open_prs, all_ops, rm, sc, G, coming, cost)
    if cost and not any(h["date"] == (cost.get("at") or "")[:10] and h.get("extras") for h in hist):
        save_hist(cost, v3.get("extras"))
        hist = load_hist()
    solution_status(v3["actions"], days, hist, {b["key"]: b for b in base})
    v3["stage_costs"] = stage_costs(O)
    v3["stage_costs_30d"] = stage_costs_30d()
    opt = dict(cost=cost, ops=all_ops, v3=v3, extra_sol=extra_sol, hist_days=[h["date"] for h in hist], sol_file=os.path.relpath(SOL_FILE, WS).replace("\\", "/"),
               sample=dict(n=len(open_prs), total=max(0, (cn.get("open") or 0) - (cn.get("draft") or 0))))

    # ---- B. Public CI (24 h): CPU vs GPU runner-minutes
    pub = None
    if O:
        rows = collections.defaultdict(lambda: dict(runs=0, pr=0, push=0, other=0, ok=0, fail=0, cancel=0, skip=0, min=0.0, waste=0.0, retried=0))
        for r in O.get("gha") or []:
            jobs = r.get("jobs") or []
            jm = [(mins(j.get("started_at"), j.get("completed_at")) or 0, j) for j in jobs]
            gpu = any(any(re.search(r"gpu|cuda|a100|h100|l4\b", (lb or "").lower()) for lb in j.get("labels") or []) for j in jobs)
            k = ("GPU" if gpu else "CPU", "GitHub Actions", r["name"])
            x = rows[k]
            x["runs"] += 1
            ev = r.get("event")
            x["pr" if ev in ("pull_request", "pull_request_target") else "push" if ev == "push" else "other"] += 1
            c = r.get("conclusion")
            x["ok" if c == "success" else "cancel" if c == "cancelled" else "fail" if c in ("failure", "timed_out", "startup_failure") else "skip"] += 1
            tot = sum(v for v, _ in jm)
            x["min"] += tot
            x["waste"] += sum(v for v, j in jm if j.get("conclusion") in ("cancelled", "failure", "timed_out"))
            x["retried"] += 1 if (r.get("run_attempt") or 1) > 1 else 0
        for b in O.get("bk") or []:
            slug = (b.get("pipeline") or {}).get("slug") or "?"
            hw = "GPU" if slug.startswith("k3-") or "gpu" in slug else "Accel" if re.match(r"(amd|xpu|musa|rbln|metax|unit-tests-(amd|xpu|musa))", slug) else "Other"
            x = rows[(hw, "Buildkite", slug)]
            x["runs"] += 1
            x["pr" if b.get("pull_request") else "push" if b.get("branch") == "dev" else "other"] += 1
            s = b.get("state")
            x["ok" if s == "passed" else "cancel" if s in ("canceled", "canceling") else "fail" if s in ("failed", "failing") else "skip"] += 1
            for j in b.get("jobs") or []:
                if j.get("type") != "script":
                    continue
                v = mins(j.get("started_at"), j.get("finished_at")) or 0
                x["min"] += v
                if j.get("state") in ("failed", "canceled", "timed_out") or j.get("retried"):
                    x["waste"] += v
                x["retried"] += 1 if j.get("retried") else 0
        out = [dict(hw=k[0], sys=k[1], name=k[2], **{kk: (r1(vv) if isinstance(vv, float) else vv) for kk, vv in v.items()}) for k, v in rows.items()]
        out.sort(key=lambda x: -x["min"])
        tot = collections.defaultdict(float)
        for x in out:
            tot[x["hw"]] += x["min"]
            tot[x["hw"] + "_waste"] += x["waste"]
            tot[x["hw"] + "_pr"] += x["min"] * (x["pr"] / x["runs"] if x["runs"] else 0)
        ng = len(O.get("gha") or [])
        pub = dict(at=O.get("at"), since=O.get("since"), hours=O.get("hours"), rows=out, tot={k: r1(v) for k, v in tot.items()},
                   errors=O.get("errors") or [], n_gha=ng, n_bk=len(O.get("bk") or []), gha_capped=ng >= 1000)

    # ---- 24 h overlap: PRs merged in the last 24 h (git, latest origin/dev) vs every PR that is NOT merged (any open state)
    gm = git_merged_window(24) if sc else None
    if gm:
        w0, w1 = dt(gm["w0"]), dt(gm["w1"])
        m24 = [dict(number=x["num"], sha=x["sha"], title=x["title"], html_url=GH_PR + str(x["num"]), merged_at=x["at"], files=x["files"]) for x in gm["prs"]]
        merged_since = gm["merged_since_snap"](S.get("at"))
    else:
        w1 = at
        w0 = at - timedelta(hours=24)
        m24 = [dict(number=i["number"], title=i["title"], html_url=i["html_url"], merged_at=i["pull_request"]["merged_at"], files=fl(i["number"]))
               for i in G.get("merged_recent") or [] if dt((i.get("pull_request") or {}).get("merged_at")) and dt(i["pull_request"]["merged_at"]) >= w0]
        merged_since = set()
    by_open = {p["num"]: p for p in open_prs}
    infl, dropped = [], []
    for n in (G.get("prs_gql") or {}).get("nodes") or []:
        if n.get("baseRefName") != "dev":
            continue
        if n["number"] in merged_since:
            dropped.append(n["number"])  # merged after the PR snapshot: not "another state" any more
            continue
        p = by_open.get(n["number"])
        if p:
            infl.append(p)
        else:  # draft
            infl.append(dict(num=n["number"], title=n["title"], url=n["url"], sub="draft", ci_at=None, updated=n["updatedAt"],
                             issues=(files.get(str(n["number"])) or {}).get("issues") or []))
    states = collections.Counter(p["sub"] for p in infl)
    PP = (load(OV_PATCH, {}) or {}).get("prs") or {}
    ppatch = {n: {x["f"]: x["p"] for x in fs} for n, fs in PP.items()}
    SUBL = {"draft": ["Draft", "nháp"], "old": ["Old (30+ days)", "cũ (30+ ngày)"], "conflict": ["In merge conflict", "đang xung đột merge"]}
    pairs = []
    for i in m24:
        mf, mat = set(i["files"]), dt(i["merged_at"])
        mi = set((files.get(str(i["number"])) or {}).get("issues") or [])
        for p in infl:
            pf = set(ppatch.get(str(p["num"])) or fl(p["num"]))
            sh = sorted(mf & pf)
            jw = words(i["title"]), words(p["title"])
            sim = len(jw[0] & jw[1]) / max(1, len(jw[0] | jw[1]))
            dup = sim >= .5 or bool(mi & set(p["issues"]))
            if not sh and not dup:
                continue
            src = [f for f in sh if pclass(f) in ("core", "kernel", "adapter", "rust", "other") and f.endswith((".py", ".cu", ".cpp", ".h", ".rs"))]
            ci_at = dt(p["ci_at"]) if p.get("ci_at") else None
            basis = "buildkite" if ci_at else "pr-updated"
            stale = (ci_at or dt(p["updated"])) < mat
            kinds = []
            # race only matters for PRs whose checks are green: that green result predates the merge
            if sh and stale and p["sub"] in ("wait_review", "wait_full", "ready"):
                kinds.append("race")
            if src and p["sub"] != "conflict":
                kinds.append("semantic")
            if dup:
                kinds.append("duplicate")
            if not kinds:
                kinds.append("touch")
            pairs.append(dict(m=i["number"], m_title=i["title"], m_url=i["html_url"], m_at=i["merged_at"],
                              p=p["num"], p_title=p["title"], p_url=p["url"], p_sub=p["sub"], shared=sh[:8], n_shared=len(sh), src=len(src),
                              sim=round(sim, 2), kinds=kinds, basis=basis))
            if sh and i.get("sha") and ppatch.get(str(p["num"])):
                rv = review_pair(i["sha"], ppatch[str(p["num"])], sh, p["sub"])
            else:
                rv = dict(level="p4" if not sh else "p3", same_func=[], same_cls=[], near=[], broken=[], imports=[], dup_lines=0, src=[f for f in sh if f.endswith(SRC_EXT)],
                          inactive="inactive" if p["sub"] in ("draft", "old", "conflict") else None)
                if sh and rv["src"] and not ppatch.get(str(p["num"])):
                    rv["nodiff"] = True
            same, rerun, dec = pair_text(rv, i["number"], p["num"], SUBL.get(p["sub"], ["", ""]))
            pairs[-1].update(level=rv["level"], inactive=bool(rv.get("inactive")), same=same, rerun=rerun, decision=dec,
                             same_func=rv["same_func"], same_cls=rv.get("same_cls") or [], near=rv["near"], broken=rv["broken"])
    LV = {"stop": 0, "rerun": 1, "go": 2}
    pairs.sort(key=lambda x: (x.get("inactive", False), LV.get(x.get("level"), 3), -x["n_shared"]))
    # flaky: same pipeline + same commit has both a failed and a passed build
    allb = [b for bs in (B.get("recent") or {}).values() for b in bs or []] + list(B.get("dev_builds") or []) + list((O or {}).get("bk") or [])
    seen, by = set(), collections.defaultdict(list)
    for b in allb:
        k = ((b.get("pipeline") or {}).get("slug"), b.get("number"))
        if k in seen:
            continue
        seen.add(k)
        by[(k[0], b.get("commit"))].append(b)
    flaky = []
    for (slug, sha), bs in by.items():
        sts = {b["state"] for b in bs}
        if "failed" in sts and "passed" in sts:
            pr = next(((b.get("pull_request") or {}).get("id") for b in bs if b.get("pull_request")), None)
            flaky.append(dict(pipeline=slug, sha=(sha or "")[:8], pr=pr, branch=bs[0].get("branch"), n=len(bs),
                              fails=sum(1 for b in bs if b["state"] == "failed"), at=max(b["created_at"] for b in bs)))
    flaky.sort(key=lambda x: x["at"], reverse=True)
    retried_jobs = sum(1 for b in (O or {}).get("bk") or [] for j in b.get("jobs") or [] if j.get("retried"))
    known = [dict(name=x["name"], rate=x["rate"], runs=x["runs"], gpu_h=x.get("gpu_h")) for x in (REP.get("failed_order") or [])[:6]]

    # cancel question: dev builds overtaken by a newer dev commit while still running
    def overtaken(builds, now):
        """Per pipeline: dev builds still running when a newer dev commit's build was created.
        over_done = overtaken builds that ran to the end (passed / failed): the time a cancel rule would save.
        over_cancel = overtaken builds that were already cancelled (a cancel rule seems active there)."""
        res = collections.defaultdict(lambda: dict(n=0, over=0, over_done=0, over_min=0.0, over_cancel=0, canceled=0, failed_over=0, gate=False))
        bys = collections.defaultdict(list)
        for b in builds:
            if b.get("branch") == "dev" and b.get("source") != "schedule":
                bys[(b.get("pipeline") or {}).get("slug")].append(b)
        for slug, bs in bys.items():
            bs.sort(key=lambda b: b["created_at"])
            r = res[slug]
            r["gate"] = slug in ("k3-unit-tests", "k3-multiprocess-test")
            for i, b in enumerate(bs):
                r["n"] += 1
                cancelled = b["state"] in ("canceled", "canceling")
                r["canceled"] += cancelled
                if not b.get("started_at"):
                    continue  # skipped / blocked / never ran
                end = dt(b.get("finished_at")) or (now if b["state"] in ("running", "failing") else None)
                nxt = next((x for x in bs[i + 1:] if x.get("commit") != b.get("commit")), None)
                if not (end and nxt and dt(nxt["created_at"]) < end):
                    continue
                r["over"] += 1
                if cancelled:
                    r["over_cancel"] += 1
                    continue
                r["over_done"] += 1
                r["over_min"] += (end - max(dt(nxt["created_at"]), dt(b["started_at"]))).total_seconds() / 60
                r["failed_over"] += b["state"] == "failed"
        return [dict(pipeline=k, **{kk: (r1(vv) if isinstance(vv, float) else vv) for kk, vv in v.items()}) for k, v in sorted(res.items(), key=lambda kv: -kv[1]["over_min"])]
    src_builds = (O or {}).get("bk") or B.get("dev_builds") or []
    cancel = overtaken(src_builds, dt((O or {}).get("at")) or at)
    cancel_src = "ops_ci_24h.json (24 h, all pipelines)" if O and O.get("bk") else "observe_snapshot.json (last 100 dev builds)"
    # one row per open PR: its worst level over all merged PRs, and a decision that depends on its CI state
    LVN = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "p4": 4}
    # merged side: has dev CI (Buildkite, branch dev) started for the merge commit?
    devb = [b for b in ((O or {}).get("bk") or []) + list(B.get("dev_builds") or []) if b.get("branch") == "dev"]
    dev_by_pipe = collections.defaultdict(list)
    for b in devb:
        dev_by_pipe[(b.get("pipeline") or {}).get("slug")].append(b)
    for v_ in dev_by_pipe.values():
        v_.sort(key=lambda b: b.get("created_at") or "")

    def red_before(b):
        """The pipeline's previous finished dev build (another commit) was already red."""
        slug = (b.get("pipeline") or {}).get("slug")
        prev = [x for x in dev_by_pipe.get(slug, []) if (x.get("created_at") or "") < (b.get("created_at") or "")
                and x.get("commit") != b.get("commit") and x.get("state") in ("passed", "failed")]
        return bool(prev) and prev[-1]["state"] == "failed"

    def dev_ci(sha):
        """queued / running / failed (new red) / red_before (only pipelines already red) / skipped (superseded) / passed."""
        bs = [b for b in devb if sha and (b.get("commit") or "").startswith(sha[:7])]
        if not bs:
            return "queued"
        sts = {b.get("state") for b in bs}
        if sts & {"running", "scheduled", "creating"}:
            return "running"
        red = [b for b in bs if b.get("state") in ("failed", "failing")]
        if red:
            return "red_before" if all(red_before(b) for b in red) else "failed"
        if "passed" in sts:
            return "passed"
        return "skipped" if sts <= {"skipped", "canceled", "canceling", "not_run"} else "queued"
    m_ci = {i["number"]: dev_ci(i.get("sha")) for i in m24}
    groups = {}
    for x in pairs:
        g = groups.setdefault(x["p"], dict(p=x["p"], p_title=x["p_title"], p_url=x["p_url"], p_sub=x["p_sub"], inactive=bool(x.get("inactive")), level="p4", items=[]))
        g["items"].append(dict(m=x["m"], m_title=x["m_title"], m_url=x["m_url"], m_at=x["m_at"], m_ci=m_ci.get(x["m"]), level=x.get("level", "p4"), same=x.get("same"), shared=x["shared"], n_shared=x["n_shared"]))
        if LVN[x.get("level", "p4")] < LVN[g["level"]]:
            g["level"] = x.get("level", "p4")
    # verb keys: stop / block / hold / rebase / keep / later / go / idle (labels + colours live in the JS VB table)
    # the rules live in decisions.py (one place for every verb on the page)
    import decisions as DEC
    SHORT = DEC.CLASH_TEXT

    def decide(lv, sub):
        return DEC.clash_action(lv, sub)
    for g in groups.values():
        g["verb"], g["decision"] = DEC.clash_action(g["level"], g["p_sub"], g["inactive"])
        g["stop_now"] = g["level"] in ("p0", "p1") and g["p_sub"] == "ci_run" and not g["inactive"]
        g["items"].sort(key=lambda i: LVN[i["level"]])
    glist = sorted(groups.values(), key=lambda g: (g["inactive"], LVN[g["level"]], not g["stop_now"], -len(g["items"])))
    act_g = [g for g in glist if not g["inactive"]]
    gcount = dict(stop_now=sum(g["stop_now"] for g in act_g), inactive=sum(1 for g in glist if g["inactive"]),
                  **{lv: sum(1 for g in act_g if g["level"] == lv) for lv in LVN},
                  hold=sum(1 for g in act_g if g["level"] in ("p0", "p1") and g["p_sub"] in ("wait_review", "wait_full", "ready", "adapt")),
                  red=sum(1 for g in act_g if g["level"] in ("p0", "p1") and g["p_sub"] == "ci_fail"),
                  verbs=dict(collections.Counter(g["verb"] for g in glist)),
                  mp_gpu_p50=((load(os.path.join(HERE, "report1130.json"), {}) or {}).get("base") or {}).get("gpu_build_p50"))
    # what to do: level x status (the same rules the per-PR decision uses), with how many PRs sit in each cell
    COLS = [("ci_run", ["CI running", "CI đang chạy"]), ("green", ["Waiting ('full' / review)", "Đang chờ ('full' / review)"]),
            ("ready", ["Approved", "Đã duyệt"]), ("ci_fail", ["Required check red", "Check bắt buộc đỏ"]),
            ("inactive", ["No CI (draft / stale / conflict)", "Không CI (nháp / cũ / xung đột)"])]
    REP_SUB = {"ci_run": "ci_run", "green": "wait_full", "ready": "ready", "ci_fail": "ci_fail"}
    def col_of(g):
        if g["inactive"]:
            return "inactive"
        return "green" if g["p_sub"] in ("wait_review", "wait_full", "adapt", "ci_missing") else g["p_sub"] if g["p_sub"] in ("ci_run", "ready", "ci_fail") else "green"
    RISK = {"p0": ["Won't import after rebase.", "Không import được sau rebase."],
            "p1": ["Same function edited on dev.", "Cùng hàm đã bị sửa trên dev."],
            "p2": ["Edits a few lines apart.", "Hai chỗ sửa cách vài dòng."],
            "p3": ["Same file, other code.", "Cùng file, khác đoạn."],
            "p4": ["No shared code.", "Không chung code."]}
    amatrix = []
    for lv in ("p0", "p1", "p2", "p3", "p4"):
        cells = {}
        for ck, _ in COLS:
            vb, txt = DEC.clash_action(lv, REP_SUB.get(ck), ck == "inactive")
            cells[ck] = dict(v=vb, t=txt, n=sum(1 for g in glist if g["level"] == lv and col_of(g) == ck))
        amatrix.append(dict(level=lv, risk=RISK[lv], cells=cells))
    # PR status overview (naming: family · detail)
    fam = {"draft": "draft", "wait_review": "open", "wait_full": "open", "adapt": "open", "ci_missing": "open", "ci_run": "progress", "ready": "queue",
           "ci_fail": "blocked", "conflict": "blocked", "old": "blocked"}
    pstat = collections.Counter(p["sub"] for p in infl)
    status = dict(open_prs={k: v for k, v in pstat.items()}, families=dict(collections.Counter(fam.get(k, "open") for k in pstat.elements())),
                  merged=dict(collections.Counter(m_ci.values())))
    # ---- reviewer view: what each merge of the last 24 h means for PRs waiting for review and PRs with CI running
    R11 = load(os.path.join(HERE, "report1130.json"), {}) or {}
    gb = (R11.get("base") or {})
    GPU_BUILD = {"k3-multiprocess-test": gb.get("mp_build_gpu_p50"), "k3-unit-tests": gb.get("unit_build_gpu_p50")}
    GATES = [("DCO", "dco"), ("Check code quality", "quality"), ("buildkite/k3-unit-tests", "unit"), ("buildkite/k3-multiprocess-test", "mp")]
    def gates_of(p):
        out = {}
        for nm, k in GATES:
            v = (p.get("req") or {}).get(nm) or "missing"
            out[k] = "label" if (v == "missing" and nm in LABEL_TRIGGERED and LABEL_TRIGGERED[nm][0] in (p.get("wait_label") or [])) else v
        return out
    def clashes(num):
        g = groups.get(num)
        if not g:
            return "p4", []
        def files(i):
            sh = sorted(i.get("shared") or [], key=lambda f: (f.rsplit("/", 1)[-1] not in (i.get("same") or [""])[0], f.endswith((".md", ".rst")), f))
            return [[f, hashlib.sha256(f.encode()).hexdigest()] for f in sh[:3]]
        return g["level"], [dict(m=i["m"], level=i["level"], same=i["same"], files=files(i)) for i in g["items"] if i["level"] != "p4"][:4]
    def running_builds(num):
        out = []
        for b in bk_pr.get(str(num), []):
            if b.get("state") in ("running", "scheduled", "creating", "failing") and not b.get("finished_at"):
                slug = (b.get("pipeline") or {}).get("slug") or ""
                out.append(dict(pipe=slug, url=b.get("web_url"), started=b.get("started_at") or b.get("created_at"), gpu=GPU_BUILD.get(slug)))
        return {x["url"]: x for x in out}.values()
    rq, rr = [], []
    for p_ in open_prs:
        if p_["sub"] in ("conflict", "old"):
            continue
        lv, cl = clashes(p_["num"])
        gt = gates_of(p_)
        runs = list(running_builds(p_["num"]))
        rb_ = dict(num=p_["num"], title=p_["title"], url=p_["url"], author=p_["author"], sub=p_["sub"], level=lv, clash=cl, gates=gt,
                    review=p_["review"], age_d=p_["age_d"])
        if p_["sub"] == "ci_run" or runs:
            d = DEC.pr_running(gt, lv, cl)   # cancel-in-progress rule: decisions.cancel_ci
            rr.append(dict(rb_, runs=list(runs), verb=d["verb"], why=d["why"], short=d["short"],
                           save=round(sum(x["gpu"] or 0 for x in runs)) if d["verb"] == "cancel" else 0))
        else:
            d = DEC.pr_waiting(gt, lv, p_["review"], cl)
            rq.append(dict(rb_, verb=d["verb"], why=d["why"], short=d["short"]))
    ORDER = {"merge": 0, "full": 1, "review": 2, "rebase": 3, "red": 4, "dco": 5, "author": 6}
    rq.sort(key=lambda x: (ORDER.get(x["verb"], 9), LVN[x["level"]], -x["age_d"]))
    rr.sort(key=lambda x: (x["verb"] != "cancel", LVN[x["level"]]))
    by_m = []
    for i in m24:
        hit_q = [dict(num=x["num"], level=c["level"], verb=x["verb"]) for x in rq for c in x["clash"] if c["m"] == i["number"]]
        hit_r = [dict(num=x["num"], level=c["level"], verb=x["verb"]) for x in rr for c in x["clash"] if c["m"] == i["number"]]
        by_m.append(dict(num=i["number"], title=i["title"], url=i["html_url"], at=i["merged_at"], ci=m_ci.get(i["number"]), ready=hit_q, running=hit_r))
    by_m.sort(key=lambda x: (-(len(x["ready"]) + len(x["running"])), x["at"]), reverse=False)
    TA = load(os.path.join(HERE, "..", "trace_agent", "directions", "rebase.json"), None)
    ta = None
    if TA:
        cur = {(m["num"], r["num"]) for m in by_m for r in m["ready"] + m["running"]}
        its = {f'{x.get("merged")}-{x.get("open")}': dict(d=x.get("decision"), r=x.get("reason"), c=x.get("confidence"), clash=x.get("clash"), ev=(x.get("evidence") or [])[:2])
               for x in TA.get("items") or []}
        ta = dict(status=TA.get("status"), run_at=TA.get("run_at"), model=TA.get("model"), cost=TA.get("cost_usd"), snap_at=TA.get("snap_at"), report=TA.get("report"),
                  error=TA.get("error"), summary=TA.get("summary"), items=its,
                  merged={str(x.get("merged")): dict(d=x.get("final"), r=x.get("reason")) for x in TA.get("merged") or []},
                  covered=sum(1 for k in cur if f"{k[0]}-{k[1]}" in its), pairs=len(cur))
    review = dict(agent=ta, queue=rq, running=rr, by_merged=by_m, verbs=dict(collections.Counter([x["verb"] for x in rq] + [x["verb"] for x in rr])),
                  save=sum(x["save"] for x in rr), gpu_build=GPU_BUILD, n_inactive=sum(1 for p_ in open_prs if p_["sub"] in ("conflict", "old")))
    overlap = dict(review=review, groups=[g for g in glist if g["level"] != "p4" or g["inactive"]], gcount=gcount, status=status, amatrix=amatrix, acols=[dict(id=k, name=n) for k, n in COLS],
                   merged_ci=[dict(num=i["number"], title=i["title"], url=i["html_url"], at=i["merged_at"], ci=m_ci.get(i["number"])) for i in m24], at=w1.strftime("%Y-%m-%dT%H:%M:%SZ"), w0=w0.strftime("%Y-%m-%dT%H:%M:%SZ"), merged_src="git" if gm else "snapshot", snap_at=S.get("at"),
                   merged=[dict(num=i["number"], title=i["title"], url=i["html_url"], at=i["merged_at"], nfiles=len(i["files"])) for i in m24],
                   states=dict(states), dropped=sorted(dropped), n_inflight=len(infl), pairs=[], n_go=sum(1 for x in pairs if x.get("level") == "go"), patches_at=(load(OV_PATCH, {}) or {}).get("at"), n_pairs=len(pairs), kinds=collections.Counter(k for x in pairs for k in x["kinds"]),
                   flaky=flaky[:30], n_flaky=len(flaky), retried_jobs=retried_jobs, known_flaky=known, cancel=cancel, cancel_src=cancel_src)

    # ---- Trace Agent proposals -> tabs
    scope_nums = {m["num"] for m in merged}
    ta = collections.defaultdict(list)
    for k, v in (P.get("prs") or {}).items():
        pr = v.get("proposal") or {}
        if pr.get("status") != "ok":
            continue
        tabs = [pr["tab"]] if pr.get("tab") else ["trace"]
        if not pr.get("tab"):
            cls, imp = pr.get("cls"), pr.get("impact")
            if imp == "blocks-release":
                tabs.append("release")
            if imp == "shipped-bug" or cls == "pr-bug":
                tabs.append("coming")
            if cls in ("dev-red", "flaky"):
                tabs.append("overlap")
            if cls in ("infra", "env-dependent"):
                tabs.append("optimal")
            if v.get("num") in scope_nums and "coming" not in tabs:
                tabs.append("coming")  # the traced PR ships in the coming release
        it = dict(key=k, tag=v.get("tag"), num=v.get("num"), title=v.get("title"), cls=pr.get("cls"), impact=pr.get("impact"),
                  conf=pr.get("confidence"), root=pr.get("root_cause"), fix=pr.get("fix"), fix_pr=pr.get("fix_pr"),
                  fix_status=pr.get("fix_status"), report=pr.get("report"), run_at=pr.get("run_at"))
        for t in tabs:
            ta[t].append(it)
    for t in ta:
        ta[t].sort(key=lambda x: x["run_at"] or "", reverse=True)
    files_of = {p_["num"]: p_["files"] for p_ in (sc or {}).get("prs") or [] if p_["num"]}
    for n_, v_ in files.items():
        files_of.setdefault(int(n_), v_.get("files") or [])
    coming["cands"] = candidate_list(rm, merged, open_prs, ta, stable, coming["scope"].get("tag_sha"), files_of)
    # release feature matrix: user-facing PRs in scope grouped by the feature they change
    from area_meta import AREAS as _AREAS
    lst_ = set((rm or {}).get("listed_all") or [])
    rows_ = {}
    LV_ = {"none": 0, "unit": 1, "conditional": 2, "required": 3}
    for m_ in merged:
        if not m_["num"] or not (m_["num"] in lst_ or not (m_["type"] in INTERNAL_TYPES or m_["risk"] in ("docs", "tests") or m_.get("ci_only"))):
            continue
        ft = pr_feature(files_of.get(m_["num"], []))
        if not ft["prim"]:
            continue
        r_ = rows_.setdefault(ft["prim"], dict(area=ft["prim"], prs=[], stage=STAGE_OF.get(ft["prim"]), cpu="none", gpu="none", rel=collections.Counter(), listed=0))
        r_["prs"].append(m_["num"])
        r_["listed"] += m_["num"] in lst_
        r_["rel"].update(ft["rel"])
        if LV_[ft["cpu"]["level"]] > LV_[r_["cpu"]]:
            r_["cpu"] = ft["cpu"]["level"]
        if LV_[ft["gpu"]["level"]] > LV_[r_["gpu"]]:
            r_["gpu"] = ft["gpu"]["level"]
    coming["features"] = sorted([dict(r_, rel=[a for a, _ in r_["rel"].most_common(3)]) for r_ in rows_.values()],
                                key=lambda r_: (r_["stage"] is None, r_["stage"] if r_["stage"] is not None else 9, -len(r_["prs"])))
    coming["area_names"] = {k: v["name"] for k, v in _AREAS.items()}
    coming["flow"] = [dict(id=i, name=n) for i, n, _ in FLOW]
    coming["summary"] = target_summary(coming, rm, ta, stable, parse_prep(rmp.parent / "RELEASE_PREP.md" if rmp else None))
    try:  # Next release cockpit (sections 3A–3E): scope -> critical path -> tests per feature -> rc cut
        import next_release
        coming["nr"] = next_release.build(coming, sc, src_area, pr_feature, ptype, risk, G, WS,
                                          str(rmp.parent / "RELEASE_PREP.md") if rmp else None)
    except Exception as e:  # never break the page; the cockpit shows the error instead
        coming["nr"] = {"error": f"{type(e).__name__}: {e}"}
    stbl = G.get("merged_since")
    pruns = sorted((G.get("publish_tags") or {}).get(stbl) or [], key=lambda r: r.get("created_at") or "", reverse=True)
    pjobs = (G.get("publish_jobs") or {}).get(str(pruns[0]["id"])) if pruns else None
    nr1 = G.get("nightly_runs") or []
    rel_ta = collections.defaultdict(lambda: dict(blocks=0, fixed=0, nums=[]))
    for v in (P.get("prs") or {}).values():
        pr_ = v.get("proposal") or {}
        if pr_.get("status") == "ok" and pr_.get("impact") == "blocks-release":
            r_ = rel_ta[v.get("tag")]
            r_["blocks"] += 1
            if pr_.get("fix_pr") or pr_.get("fix_status") == "merged":
                r_["fixed"] += 1
                r_["nums"].append(f"#{v.get('num')} (fixed by #{pr_.get('fix_pr')})" if pr_.get("fix_pr") else f"#{v.get('num')} (fixed)")
            else:
                r_["nums"].append(f"#{v.get('num')} (open)")
    health = dict(stable=stbl, publish=dict(status=pruns[0].get("status"), conclusion=pruns[0].get("conclusion"), attempt=pruns[0].get("run_attempt"), url=pruns[0].get("html_url"),
                                            failed_jobs=sum(1 for j in (pjobs or []) if j.get("conclusion") == "failure")) if pruns else None,
                  nightly=dict(n=len(nr1), fail=sum(1 for r in nr1 if r.get("conclusion") == "failure")), releases=dict(rel_ta))
    not_expl = [dict(tag=v.get("tag"), num=v.get("num"), title=v.get("title"), status=(v.get("proposal") or {}).get("status") or "pending")
                for v in (P.get("prs") or {}).values() if (v.get("checks") or {}).get("failed") and (v.get("proposal") or {}).get("status") != "ok"]
    ta_meta = dict(health=health, not_explained=not_expl, updated=P.get("updated_at"), total=len(P.get("prs") or {}), ok=sum(1 for v in (P.get("prs") or {}).values() if (v.get("proposal") or {}).get("status") == "ok"))

    # ---- rule checks (computed here, shown in the Trace Agent card next to the proposals)
    R = collections.defaultdict(list)
    def rule(tab, lvl, en, vi):
        R[tab].append(dict(lvl=lvl, t=[en, vi]))
    bt = coming["by_type"]
    rule("coming", "info", f"{len(merged)} PRs merged since {stable}: {bt.get('feature', 0)} feature, {bt.get('bug', 0)} bug fix, {bt.get('perf', 0)} perf, {bt.get('refactor', 0)} refactor.",
         f"{len(merged)} PR đã merge từ {stable}: {bt.get('feature', 0)} feature, {bt.get('bug', 0)} sửa bug, {bt.get('perf', 0)} perf, {bt.get('refactor', 0)} refactor.")
    if dev_red:
        rule("coming", "bad", "dev is red on " + ", ".join(d["pipeline"] for d in dev_red) + ": fix before the next RC.",
             "dev đang đỏ ở " + ", ".join(d["pipeline"] for d in dev_red) + ": cần sửa trước RC tiếp theo.")
    rule("coming", "warn" if coming["open_ci_fail"] else "info", f"{coming['open_ci_fail']} of {len(open_prs)} open PRs fail a required check.",
         f"{coming['open_ci_fail']} / {len(open_prs)} PR đang mở fail check bắt buộc.")
    scd = coming["scope"]
    if scd["src"] != "git":
        rule("coming", "warn", f"No local clone at third_party/LMCache: scope uses the GitHub search since the {stable} publish date, which misses PRs merged between the tag commit and the publish.",
             f"Không có clone local ở third_party/LMCache: phạm vi dùng tìm kiếm GitHub từ ngày publish {stable}, sẽ sót các PR merge giữa commit tag và ngày publish.")
    elif S.get("at") and scd["head_at"] and (dt(S["at"]) - dt(scd["head_at"])).total_seconds() > 86400:
        rule("coming", "warn", f"The local clone's origin/dev ({scd['head']}) is more than a day older than the snapshot: run git fetch in {scd['repo']}.",
             f"origin/dev trong clone local ({scd['head']}) cũ hơn snapshot quá một ngày: chạy git fetch trong {scd['repo']}.")
    if rm:
        s_ = rm["status"]
        rule("coming", "info", f"External list {rm['src']['rel']}: {rm['n_items']} items, {rm['n_listed']} PRs. {s_.get('in_scope', 0)} are in {stable}..dev, {s_.get('in_tag', 0)} already shipped in {stable}, {s_.get('open', 0)} still open, {s_.get('not_found', 0)} not found.",
             f"Danh sách ngoài {rm['src']['rel']}: {rm['n_items']} mục, {rm['n_listed']} PR. {s_.get('in_scope', 0)} nằm trong {stable}..dev, {s_.get('in_tag', 0)} đã có trong {stable}, {s_.get('open', 0)} còn mở, {s_.get('not_found', 0)} không tìm thấy.")
        if s_.get("in_tag") or s_.get("open") or s_.get("not_found"):
            rule("coming", "bad", "Some listed PRs will not ship in the next release as written: see the status chips in 3B.",
                 "Một số PR trong danh sách sẽ không vào release tới như đã ghi: xem trạng thái ở 3B.")
        rule("coming", "warn" if rm["n_missing_user"] else "good", f"The list covers {rm['n_user_listed']} of {rm['n_user']} user-facing PRs in scope; {rm['n_missing_user']} user-facing PRs are not in it ({sum(1 for x in rm['missing'] if not x['internal'] and not x['mentioned'])} not even in the review notes).",
             f"Danh sách có {rm['n_user_listed']} / {rm['n_user']} PR người dùng thấy được trong phạm vi; {rm['n_missing_user']} PR người dùng thấy được chưa có ({sum(1 for x in rm['missing'] if not x['internal'] and not x['mentioned'])} PR chưa có cả trong phần review).")
        if rm["breaking"]:
            rule("coming", "bad", "Possibly breaking, not under 'Breaking changes': " + ", ".join(f"#{x['num']}" for x in rm["breaking"]) + ". Check and move them first.",
                 "Có thể là thay đổi phá vỡ, chưa nằm trong 'Breaking changes': " + ", ".join(f"#{x['num']}" for x in rm["breaking"]) + ". Kiểm tra và đưa lên đầu.")
        late = sum(1 for m in merged if m["at"] and m["at"] > rm["src"]["mtime"])
        if late:
            rule("coming", "info", f"{late} PRs merged after the list was last saved ({rm['src']['mtime'][:10]}).",
                 f"{late} PR merge sau lần lưu danh sách gần nhất ({rm['src']['mtime'][:10]}).")
    else:
        rule("coming", "info", "No external candidate list found (release-<next>/ROADMAP.md or COMING_RELEASE_SRC).",
             "Không thấy danh sách ứng viên bên ngoài (release-<next>/ROADMAP.md hoặc COMING_RELEASE_SRC).")
    rule("optimal", "info", f"{st['wait_review'] + st['wait_full']} PRs have green CPU and GPU-unit checks and wait for a maintainer; {st['wait_full']} of them still need the 'full' label before k3-multiprocess-test (a required check) runs.",
         f"{st['wait_review'] + st['wait_full']} PR đã xanh check CPU và GPU unit, chờ maintainer; {st['wait_full']} PR trong đó còn cần nhãn 'full' trước khi k3-multiprocess-test (check bắt buộc) chạy.")
    if skip:
        rule("optimal", "good", f"{len(skip)} green PRs change only docs: candidates to merge without human approval.",
             f"{len(skip)} PR xanh chỉ đổi docs: ứng viên merge không cần người duyệt.")
    if gpu_after_cpu_fail:
        rule("optimal", "warn", f"{len(gpu_after_cpu_fail)} open PRs ran GPU checks on a commit whose DCO / lint failed: a CPU pre-gate would stop them.",
             f"{len(gpu_after_cpu_fail)} PR đang mở chạy check GPU trên commit có DCO / lint fail: một cổng CPU chạy trước sẽ chặn được.")
    if opt["ops"]:
        o = opt["ops"][0]
        ss = (opt["v3"].get("stage_costs") or {}).get("stamp") or {}
        m30 = (opt["v3"].get("stage_costs_30d") or {}).get("matrix")
        if m30 and o["id"] == "matrix-" + m30["workflow"]:
            w0, w1 = opt["v3"]["stage_costs_30d"]["window"]
            rule("optimal", "bad" if m30["lo"] > 1500 else "warn", f"Largest saving: {o['title'][0]} (≈{m30['lo']:,}–{m30['hi']:,} job-min/day, 7-day means over 30 d {w0} → {w1}).",
                 f"Tiết kiệm lớn nhất: {o['title'][1]} (≈{m30['lo']:,}–{m30['hi']:,} phút job/ngày, trung bình 7 ngày trong 30 ngày {w0} → {w1}).")
        else:
            rule("optimal", "bad" if (o["save"] or 0) > 1500 else "warn", f"Largest saving: {o['title'][0]} (≈{o['save']} job-min/day, one 24 h sample to {ss.get('date', '?')}).",
                 f"Tiết kiệm lớn nhất: {o['title'][1]} (≈{o['save']} phút job/ngày, một mẫu 24 giờ tới {ss.get('date', '?')}).")
    kc = overlap["kinds"]
    gc_ = overlap["gcount"]
    rule("overlap", "warn" if gc_.get("p0") or gc_.get("p1") else "info",
         f"{len(m24)} PRs merged in 24 h vs {len(infl)} open PRs. Open PRs with CI: P0 {gc_.get('p0', 0)} · P1 {gc_.get('p1', 0)} · P2 {gc_.get('p2', 0)} · P3 {gc_.get('p3', 0)}; {gc_.get('inactive', 0)} more without CI (draft / stale / conflict). {kc.get('duplicate', 0)} possible duplicate pairs.",
         f"{len(m24)} PR merge trong 24 giờ so với {len(infl)} PR đang mở. PR đang có CI: P0 {gc_.get('p0', 0)} · P1 {gc_.get('p1', 0)} · P2 {gc_.get('p2', 0)} · P3 {gc_.get('p3', 0)}; thêm {gc_.get('inactive', 0)} PR không chạy CI (nháp / cũ / xung đột). {kc.get('duplicate', 0)} cặp có thể trùng.")
    if flaky:
        rule("overlap", "warn", f"{len(flaky)} pipeline+commit pairs failed and then passed on the same commit (flaky).",
             f"{len(flaky)} cặp pipeline+commit fail rồi pass trên cùng commit (flaky).")
    ov, od = sum(c["over"] for c in cancel), sum(c["over_done"] for c in cancel)
    if ov:
        rule("overlap", "info", f"{ov} dev builds were still running when a newer dev commit arrived; {ov - od} were cancelled, {od} ran to the end ({r1(sum(c['over_min'] for c in cancel))} wall-min after the newer commit).",
             f"{ov} build dev vẫn đang chạy khi commit dev mới hơn tới; {ov - od} đã bị huỷ, {od} chạy tới cuối ({r1(sum(c['over_min'] for c in cancel))} phút sau commit mới hơn).")

    # ---- metric catalog per tab (baseline 30 d; target / after / task filled when tasks are classified)
    bmap = {b["key"]: b for b in base}
    def mrow(key, en, vi, d_en, d_vi, val, unit):
        return dict(key=key, name=[en, vi], defn=[d_en, d_vi], base=val, unit=unit)
    tot = (pub or {}).get("tot") or {}
    metrics = dict(
        coming=[mrow("merged_scope", "PRs in release scope", "PR trong phạm vi release", "Merged into dev after the last stable tag commit (git).", "Đã merge vào dev sau commit của tag stable gần nhất (git).", len(merged), ""),
                mrow("list_coverage", "User-facing PRs in the release list", "PR người dùng thấy được có trong danh sách release", "Listed / user-facing PRs in scope (not refactor, test, CI, docs).", "Có trong danh sách / PR người dùng thấy được trong phạm vi (không phải refactor, test, CI, docs).",
                     f"{rm['n_user_listed']}/{rm['n_user']}" if rm else None, ""),
                mrow("open_fail", "Open PRs failing a required check", "PR mở fail check bắt buộc", "Required checks red on the head commit.", "Check bắt buộc đỏ trên commit mới nhất.", coming["open_ci_fail"], "")],
        optimal=[mrow(b["key"], b["name"][0], b["name"][1], b["defn"][0], b["defn"][1], b["value"], b["unit"]) for b in base] + [
                 mrow("skip_cand", "PRs that could skip human approval", "PR có thể bỏ qua người duyệt", "Green gates, docs / tests only (now).", "Cổng xanh, chỉ docs / test (hiện tại).", len(skip), ""),
                 mrow("cpu_min", "CPU runner-min / 24 h", "Phút CPU runner / 24 giờ", "GitHub Actions job-minutes, all events.", "Phút job GitHub Actions, mọi event.", tot.get("CPU"), "min"),
                 mrow("gpu_min", "GPU job-min / 24 h", "Phút GPU agent / 24 giờ", "Buildkite k3 job-minutes, all branches.", "Phút job Buildkite k3, mọi nhánh.", tot.get("GPU"), "min")],
        overlap=[mrow("pairs", "Merged × in-flight pairs with risk", "Cặp merge × đang chạy có rủi ro", "Shared files or same topic, 24 h.", "Chung file hoặc cùng chủ đề, 24 giờ.", len(pairs), ""),
                 mrow("flaky", "Flaky pipeline+commit pairs", "Cặp pipeline+commit flaky", "Failed and passed on the same commit.", "Fail và pass trên cùng commit.", len(flaky), ""),
                 mrow("overtaken_min", "Dev build-min after a newer commit", "Phút build dev sau commit mới hơn", "Time older dev builds kept running.", "Thời gian build dev cũ vẫn chạy.", r1(sum(c["over_min"] for c in cancel)), "min")])

    return dict(made=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), snap_at=S.get("at"), window=window,
                coming=coming, base=base, prs=prs_a, pub=pub, opt=opt, overlap=overlap, ta=dict(ta), ta_meta=ta_meta, rules=dict(R),
                metrics=metrics, tasks=TASKS)


# ------------------------------------------------------------------ page blocks
HTML = r"""
<!-- OPS:HTML:START -->
<section class="card ops" data-view="obs" data-tab="release" data-ops="ta-release"></section>
<section class="card ops" data-view="obs" data-tab="trace" data-ops="ta-trace"></section>
<section class="card ops" data-view="obs" data-tab="coming" data-ops="nr-ck"></section>
<section class="card ops" data-view="obs" data-tab="coming" data-ops="nr-scope"></section>
<section class="card ops" data-view="obs" data-tab="coming" data-ops="nr-cp"></section>
<section class="card ops" data-view="obs" data-tab="coming" data-ops="nr-fm"></section>
<section class="card ops" data-view="obs" data-tab="coming" data-ops="nr-cut"></section>
<section class="card ops" data-view="obs" data-tab="coming" data-ops="summary"></section>
<section class="card ops" data-view="obs" data-tab="coming" data-ops="coming"></section>
<section class="card ops" data-view="obs" data-tab="opt_cpu" data-ops="oc-sum"></section>
<section class="card ops" data-view="obs" data-tab="opt_cpu" data-ops="oc-stages"></section>
<section class="card ops" data-view="obs" data-tab="opt_cpu" data-ops="oc-res"></section>
<section class="card ops" data-view="obs" data-tab="opt_cpu" data-ops="oc-more"></section>
<section class="card ops" data-view="obs" data-tab="opt_gpu" data-ops="og-sum"></section>
<section class="card ops" data-view="obs" data-tab="opt_gpu" data-ops="og-stages"></section>
<section class="card ops" data-view="obs" data-tab="opt_gpu" data-ops="og-res"></section>
<section class="card ops" data-view="obs" data-tab="opt_gpu" data-ops="og-more"></section>
<section class="card ops" data-view="obs" data-tab="overlap" data-ops="overlap"></section>
<!-- OPS:HTML:END -->
"""

CSS = r"""
/* OPS:CSS:START */
.ops h2{margin:0}
.ops .head{margin-bottom:12px}
.ops-kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;margin:4px 0 14px}
.ops-kpi{border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--surface-1)}
.ops-kpi .v{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--text-primary)}
.ops-kpi .l{font-size:12px;color:var(--text-secondary);margin-top:2px}
.ops-kpi.bad{border-color:var(--critical)}.ops-kpi.warn{border-color:var(--warning)}.ops-kpi.good{border-color:color-mix(in oklab,var(--good) 70%,var(--border))}
.ops-mc{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.ops-card{border:1px solid var(--border);border-radius:12px;padding:12px 14px;background:var(--surface-1);display:flex;flex-direction:column;gap:4px;min-width:0}
.ops-card .n{font-size:12.5px;font-weight:650;color:var(--text-secondary)}
.ops-card .v{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--text-primary)}
.ops-card .v small{font-size:12px;color:var(--text-muted);font-weight:600;margin-left:4px}
.ops-card .d{font-size:11.5px;color:var(--text-muted);line-height:1.35}
.ops-card .dl{font-size:12px;font-weight:600}
.ops-card .dl.better{color:var(--good)}.ops-card .dl.worse{color:var(--crit-text,var(--critical))}.ops-card .dl.same{color:var(--text-muted)}
.ops-spark{width:100%;height:36px;display:block}
.ops-spark rect{fill:var(--series-1)}
.ops-spark rect:hover{fill:var(--series-2)}
.ops-funnel{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:6px 0 14px}
.ops-stage{border:1px solid var(--border);border-radius:12px;padding:12px;background:var(--surface-1);position:relative}
.ops-stage:not(:last-child)::after{content:"→";position:absolute;right:-12px;top:40%;color:var(--text-muted);font-weight:700}
.ops-stage .k{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted)}
.ops-stage .t{font-weight:650;margin:2px 0 6px}
.ops-stage .v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums}
.ops-stage .s{font-size:12px;color:var(--text-secondary);display:flex;flex-direction:column;gap:2px;margin-top:4px}
.ops-stack{display:flex;height:14px;border-radius:4px;overflow:hidden;gap:2px;margin:6px 0 4px;background:var(--surface-1)}
.ops-stack i{display:block;height:100%}
.ops-leg{display:flex;flex-wrap:wrap;gap:10px;font-size:11.5px;color:var(--text-secondary);margin-bottom:10px}
.ops-leg span{display:inline-flex;align-items:center;gap:5px}
.ops-leg i{width:10px;height:10px;border-radius:3px;display:inline-block}
.ops-split{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.ops-hb{display:flex;align-items:center;gap:8px}
.ops-hb i{display:block;height:10px;border-radius:0 4px 4px 0;min-width:2px}
.ops-kind{display:inline-block;font-size:10.5px;font-weight:650;padding:1px 6px;border-radius:5px;margin:1px 3px 1px 0;border:1px solid var(--border);white-space:nowrap}
.ops-kind.semantic{border-color:var(--critical);color:var(--crit-text,var(--critical))}
.ops-kind.shared{border-color:var(--warning)}
.ops-kind.race{border-color:var(--warning)}
.ops-kind.duplicate{border-color:var(--series-2)}
.ops-kind.flaky{border-color:var(--series-3)}
.ops-files{font:11px ui-monospace,Consolas,monospace;color:var(--text-secondary);word-break:break-all}
.ops-rules{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
.ops-rule{font-size:12.5px;padding:7px 10px;border-radius:8px;border-left:3px solid var(--border);background:var(--surface-2)}
.ops-rule.lv-bad{border-left-color:var(--critical)}.ops-rule.lv-warn{border-left-color:var(--warning)}.ops-rule.lv-good{border-left-color:var(--good)}
.ops-rule b{margin-right:6px}
.ops-ta{border:1px solid var(--border);border-radius:10px;padding:10px 12px;margin-bottom:8px;background:var(--surface-1)}
.ops-ta summary{cursor:pointer;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;font-size:12.5px}
.ops-ta .why{font-size:12.5px;margin:8px 0 4px;color:var(--text-primary)}
.ops-ta .fix{font-size:12.5px;color:var(--good)}
.ops-ta .meta{font-size:11.5px;color:var(--text-muted)}
.ops-empty{padding:12px 14px;border:1px dashed var(--border);border-radius:9px;color:var(--text-secondary);font-size:12.5px}
.ops-verdict{border:1px solid var(--border);border-left:4px solid var(--series-1);border-radius:10px;padding:12px 14px;background:var(--surface-1);font-size:13px;line-height:1.5;margin-bottom:12px}
.ops-verdict ul{margin:6px 0 0;padding-left:18px}
.ops-why{font-size:12px;color:var(--text-secondary);line-height:1.45;margin-top:4px;max-width:70ch}
.ops-src{font-size:11.5px;color:var(--text-muted);margin-top:8px}
@media (max-width:760px){.ops-funnel,.ops-split{grid-template-columns:1fr}.ops-stage::after{display:none}}
.ops-feat{all:unset;cursor:pointer;display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:999px;border:1px solid var(--border);margin:1px 4px 1px 0;color:var(--text-secondary)}
.ops-feat.main{border-color:var(--series-1);color:var(--text-primary);font-weight:650}
.ops-feat:hover{background:var(--surface-2)}
.ops-featline{margin-top:4px;display:flex;flex-wrap:wrap;align-items:center;gap:2px;font-size:12px}
.ops-flow{display:flex;align-items:stretch;gap:6px;flex-wrap:wrap;margin:6px 0 12px}
.ops-fstep{flex:1 1 120px;border:1px solid var(--border);border-radius:10px;padding:8px 10px;background:var(--surface-1);min-width:110px}
.ops-fstep.hit{border-color:var(--warning)}
.ops-fstep .t{font-size:12px;font-weight:650}.ops-fstep .v{font-size:18px;font-weight:700;margin:2px 0}
.ops-farr{align-self:center;color:var(--text-muted);font-weight:700}
tr.ops-flash td{background:color-mix(in oklab,var(--warning) 25%,transparent)!important;transition:background .4s}
.ops-cells td{vertical-align:top;min-width:200px}
.ops-sol{display:block;font-size:12px;margin:2px 0;padding-left:6px;border-left:3px solid var(--border);color:var(--text-primary);text-decoration:none}
.ops-sol.bad{border-left-color:var(--critical)}.ops-sol.warn{border-left-color:var(--warning)}.ops-sol:hover{text-decoration:underline}
.ops-apply{margin-top:4px;padding:6px 8px;border:1px dashed var(--warning);border-radius:8px;font-size:12px}
.ops-apply code{font-size:11px;word-break:break-all}
.ops-amx td{font-size:12px;vertical-align:top;min-width:150px}
.ops-amx td.hit{background:color-mix(in oklab,var(--warning) 10%,transparent)}
.ops-amx tr.lv-p0 td:first-child,.ops-amx tr.lv-p1 td:first-child{border-left:3px solid var(--critical)}
.ops-amx tr.lv-p2 td:first-child,.ops-amx tr.lv-p3 td:first-child{border-left:3px solid var(--warning)}
.ops-amx tr.lv-p4 td:first-child{border-left:3px solid var(--good)}
.ops-cnt{display:inline-block;font-weight:700;font-size:11px;padding:0 6px;border-radius:999px;background:var(--surface-2);margin-bottom:3px}
.ops-grp td{background:var(--surface-2);padding-top:8px!important}
.ops-picker>summary,.ops-fold>summary{cursor:pointer;padding:6px 0;font-size:14px}.ops-picker .ops-open{color:var(--series-1)}.ops-fold>summary{font-weight:600;margin-top:10px}
.ops-picker>summary:focus-visible,.ops-fold>summary:focus-visible{outline:2px solid var(--series-1);outline-offset:2px}
.ops-pick{width:22px}
.ops-md{width:100%;box-sizing:border-box;font:12px ui-monospace,Consolas,monospace;background:var(--surface-1);color:var(--text-primary);border:1px solid var(--border);border-radius:8px;padding:8px;margin:6px 0}
.ops-filter{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:6px 0 8px}
.ops-filter button{all:unset;cursor:pointer;font-size:12.5px;padding:4px 10px;border-radius:8px;border:1px solid var(--border);color:var(--text-secondary)}
.ops-filter button[aria-pressed="true"]{background:var(--surface-2);color:var(--text-primary);font-weight:650}
.obs-scroll{overflow-x:auto;max-width:100%}
@media (max-width:700px){
  .ops-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  .ops-rule,.ops-verdict,.ops-why,.ops-files{overflow-wrap:anywhere}
  .ops .obs-t{min-width:560px}
  .card.ops{overflow-x:hidden}
}
.ops-narrow{display:none;margin:4px 0}@media (max-width:760px){.ops-narrow{display:block}}
.rv-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin:8px 0 14px}
.rv-box{border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--surface-1)}
.rv-box.warn{border-left:3px solid var(--critical)}
.rv-box .l{font-size:12.5px;color:var(--text-secondary);margin-bottom:6px}
.rv-chips{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
.rv-gates{display:inline-flex;flex-wrap:wrap;gap:4px}
.rv-ref{display:inline-flex;align-items:center;gap:4px;margin:0 10px 6px 0;white-space:nowrap}
.rv-cl{margin-bottom:4px;font-size:12.5px}
.rv-files{display:flex;flex-wrap:wrap;gap:2px 12px;margin:2px 0 0 2px;font-size:11.5px}.rv-file{white-space:nowrap}.rv-file code{font-size:11px}
.rv-lv{cursor:default}
.rv-tip{position:fixed;z-index:60;font-family:inherit;white-space:normal;text-align:left;display:none;pointer-events:none;max-width:320px;background:var(--surface-1);color:var(--text-primary);border:1px solid var(--border);border-radius:8px;padding:6px 9px;font-size:12px;line-height:1.4;box-shadow:0 4px 14px rgba(0,0,0,.18)}
.rv-leg{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:12.5px;color:var(--text-secondary);margin:4px 0 6px}
.rv-ta{border-style:dashed}
.rv-tanote{font-size:12.5px;color:var(--text-secondary);border-left:3px solid var(--series-2);padding:4px 8px;margin:4px 0 8px}
.rv-tanote.warn{border-left-color:var(--warning)}
/* Next release cockpit (3A–3E, next_release.js) — same tokens as the ops cards */
section[data-ops="nr-ck"]{border:2px solid var(--series-1)}
.nr-phases{list-style:none;margin:4px 0 14px;padding:0;display:grid;grid-template-columns:repeat(7,minmax(120px,1fr));gap:6px;overflow-x:auto}
.nr-ph{all:unset;box-sizing:border-box;cursor:pointer;width:100%;height:100%;display:flex;flex-direction:column;gap:2px;border:1px solid var(--border);border-radius:10px;padding:8px 10px;background:var(--surface-1)}
.nr-ph b{font-size:13px;color:var(--text-primary)}.nr-pn,.nr-ps{font-size:11px;color:var(--text-muted)}.nr-ph .gch{align-self:flex-start;margin-top:4px}
.nr-ph.cur{border:2px solid var(--series-1);background:var(--surface-2)}.nr-ph.done{border-color:var(--good)}.nr-ph.lock{opacity:.6}.nr-ph.unk{border-style:dashed}.nr-ph.warn{border-color:var(--warning)}.nr-ph.carry{border-color:var(--text-muted);border-style:dashed}
.nr-ph.sel{box-shadow:0 0 0 2px var(--series-1)}.nr-ph:focus-visible{outline:2px solid var(--series-1);outline-offset:2px}
.nr-grp{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}
.nr-grp h3{margin:0;font-size:14px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.nr-gi{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;background:var(--series-1);color:var(--surface-1);font-size:12px;font-weight:700}
.nr-card{border:1px solid var(--border);border-left:4px solid var(--border);border-radius:8px;padding:8px 10px;background:var(--surface-1);display:flex;flex-direction:column;gap:4px;min-width:0;font-size:12.5px}
.nr-card.lv-bad{border-left-color:var(--critical)}.nr-card.lv-warn{border-left-color:var(--warning)}.nr-card.lv-ok{border-left-color:var(--good);opacity:.7}
.nr-ct{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}.nr-ct b{overflow-wrap:anywhere;color:var(--text-primary)}
.nr-id{font:600 12px ui-monospace,Consolas,monospace;color:var(--series-1)}
.nr-cb{overflow-wrap:anywhere;color:var(--text-primary)}
.nr-cf{display:flex;flex-wrap:wrap;gap:4px 14px;justify-content:space-between;align-items:center;font-size:11.5px;color:var(--text-muted)}
.nr-evs{display:inline-flex;flex-wrap:wrap;gap:4px;align-items:center}
.nr-ev{all:unset;cursor:pointer;font-size:11.5px;padding:1px 8px;border-radius:999px;border:1px solid var(--series-1);color:var(--text-primary)}
.nr-ev:hover{background:var(--surface-2)}.nr-ev:focus-visible{outline:2px solid var(--series-1)}
.nr-next{border:1px dashed var(--series-1);border-radius:8px;padding:10px 12px;font-size:12.5px;display:flex;flex-direction:column;gap:6px}
.nr-cmd{margin:0;font:12px ui-monospace,Consolas,monospace;background:var(--surface-2);border-radius:6px;padding:8px;overflow-x:auto;white-space:pre}
.nr-mute{color:var(--text-muted);font-size:11.5px}.nr-warn{color:var(--warning);font-weight:650}
.nr-t td{font-size:12px;vertical-align:top}.nr-t td .ops-rule{padding:3px 7px;margin:2px 0;font-size:11.5px}
.nr-t td[data-col],.ops-kpi[data-kpi],[data-tier],[data-fid],[data-stg],.nr-mkm{cursor:help}
tr.nr-arow{cursor:pointer}tr.nr-arow:hover td,tr.nr-arow.sel td{background:var(--surface-2)}
.nr-tier{display:inline-block;font:11px ui-monospace,Consolas,monospace;border:1px solid var(--text-secondary);border-radius:4px;padding:0 4px;margin:1px}
.nr-tier.cond{border-style:dashed}.nr-tier.prop{opacity:.55;font-style:italic}.nr-tier.prop::after{content:"*"}
.nr-stg{font:11px ui-monospace,Consolas,monospace;border-radius:4px;padding:0 5px;border:1px solid var(--border)}
.nr-stg.w3{border-color:var(--critical)}.nr-stg.w2{border-color:var(--warning)}
.nr-mk{display:inline-block;white-space:nowrap;margin:1px 6px 1px 0;font-size:12px}.nr-mkm{margin-right:1px}
.nr-seq{display:flex;align-items:stretch;gap:6px;min-width:max-content;margin:6px 0}
.nr-node{all:unset;box-sizing:border-box;cursor:pointer;display:flex;flex-direction:column;gap:4px;min-width:118px;max-width:170px;border:1px solid var(--border);border-radius:10px;padding:8px 10px;background:var(--surface-1)}
.nr-node .t{font-weight:650;font-size:12.5px;color:var(--text-primary)}
.nr-node.ch{border-color:var(--warning)}.nr-node.warn{border:2px solid var(--warning);background:color-mix(in oklab,var(--warning) 12%,var(--surface-1))}
.nr-node.bad{border:2px solid var(--critical);background:color-mix(in oklab,var(--critical) 10%,var(--surface-1))}
.nr-node.bug{border:2px solid var(--series-1);background:var(--surface-2)}.nr-node.sel{box-shadow:0 0 0 2px var(--series-1)}.nr-node:focus-visible{outline:2px solid var(--series-1)}
.nr-fs{display:flex;flex-wrap:wrap;gap:3px}.nr-f{font:10px ui-monospace,Consolas,monospace;border:1px solid var(--border);border-radius:3px;padding:0 3px;color:var(--text-secondary)}
.nr-crit{font-size:11px;font-weight:650;color:var(--warning)}
.nr-dbg{margin:10px 0 0;padding-left:20px;display:flex;flex-direction:column;gap:5px;font-size:12.5px}.nr-dbg li::marker{font-weight:700;color:var(--series-1)}
.nr-sel{font:inherit;font-size:12.5px;max-width:100%;padding:3px 6px;border:1px solid var(--border);border-radius:8px;background:var(--surface-1);color:var(--text-primary)}
.nr-link{all:unset;cursor:pointer;color:var(--series-1);text-decoration:underline;font-size:12px}
.nr-strip{display:flex;align-items:flex-end;gap:2px;height:60px;min-width:760px}
.nr-coll > :not(.head){display:none!important}.nr-tog{margin-left:8px;font-size:12px}
.nr-tick{all:unset;flex:1 1 0;min-width:4px;min-height:24px;height:34%;border-radius:2px 2px 0 0;cursor:pointer;background:var(--border)}
.nr-tick.scope{background:var(--series-1);height:100%}.nr-tick.hi{background:var(--warning);height:62%}.nr-tick.bk{background:var(--critical);height:80%}
.nr-tick.after{opacity:.35}.nr-tick.cut{outline:2px solid var(--text-primary);outline-offset:1px}.nr-tick:hover{opacity:1;filter:brightness(1.15)}
.nr-axis{display:flex;justify-content:space-between;font:11px ui-monospace,Consolas,monospace;color:var(--text-muted);min-width:760px}
.nr-pop{position:fixed;z-index:70;max-width:min(440px,calc(100vw - 24px));background:var(--surface-1);color:var(--text-primary);border:1px solid var(--series-1);border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,.2);font-size:12.5px;line-height:1.45}
.nr-ph2{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid var(--border);background:var(--surface-2);border-radius:8px 8px 0 0}
.nr-x{all:unset;cursor:pointer;font-size:18px;line-height:1;color:var(--text-muted);padding:0 4px}
.nr-pb{padding:8px 10px;max-height:50vh;overflow:auto;overflow-wrap:anywhere}.nr-pb hr{border:0;border-top:1px solid var(--border);margin:8px 0}
@media (max-width:760px){.nr-phases{grid-template-columns:repeat(7,minmax(120px,1fr))}}
/* OPS:CSS:END */
"""

JS = r"""
<!-- OPS:JS:START -->
<script id="opsData" type="application/json">__DATA__</script>
<script>
(function(){
  let D=null;try{D=JSON.parse(document.getElementById('opsData').textContent);}catch(e){return;}
  const V=()=>(window.I18N&&I18N.lang==='vi')?1:0, T=(en,vi)=>V()?vi:en, L=a=>Array.isArray(a)?(a[V()]||a[0]):(a||'');
  const el=(t,a={},...kids)=>{const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(v==null)continue;if(k==='class')e.className=v;else if(k==='style')e.style.cssText=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else e.setAttribute(k,v);}
    kids.flat().forEach(c=>{if(c==null||c===false)return;e.append(c.nodeType?c:document.createTextNode(String(c)));});return e;};
  const fmt=n=>n==null?'—':Number(n).toLocaleString('en-US');
  const day=s=>{if(!s)return '—';const d=new Date(s);if(isNaN(d))return String(s);const q=n=>String(n).padStart(2,'0');return `${d.getFullYear()}-${q(d.getMonth()+1)}-${q(d.getDate())} ${q(d.getHours())}:${q(d.getMinutes())}`;};
  const U=u=>!V()?(u||''):({'/day':'/ngày','PRs':'PR','h':'giờ','min':'phút','PRs/day':'PR/ngày','job-min/day':'phút job/ngày','job-min/day':'phút job/ngày','builds':'build'}[u]||(u||'').replace(/^of /,'trên '));
  const CONF={high:['high','cao'],medium:['medium','trung bình'],low:['low','thấp']};
  const a=(href,txt)=>el('a',{href,target:'_blank',rel:'noopener'},txt);
  const head=(n,en,vi,sen,svi)=>el('div',{class:'head'},el('h2',{},`${n?n+' · ':''}${T(en,vi)}`),sen?el('p',{class:'sub'},T(sen,svi)):null);
  const kpi=(v,l,cls)=>el('div',{class:'ops-kpi'+(cls?' '+cls:'')},el('div',{class:'v'},v),el('div',{class:'l'},l));
  const table=(cols,rows)=>{const t=el('table',{class:'obs-t'});t.append(el('thead',{},el('tr',{},cols.map(c=>el('th',{class:c[1]||''},c[0])))));const b=el('tbody');rows.forEach(r=>b.append(r));t.append(b);return el('div',{class:'obs-scroll'},t);};
  const TYPE={feature:['Feature','Feature','var(--series-1)'],bug:['Bug fix','Sửa bug','var(--series-2)'],perf:['Perf','Perf','var(--series-3)'],refactor:['Refactor','Refactor','var(--series-4,#8a5cd0)'],ci:['CI / build','CI / build','var(--series-5,#b0753a)'],docs:['Docs','Docs','var(--text-muted)'],test:['Tests','Test','var(--border)'],other:['Other','Khác','var(--surface-2)']};
  const RISK={docs:['docs only','chỉ docs'],tests:['docs / tests','docs / test'],core:['core','core'],ci:['CI / deps','CI / deps'],gpu:['GPU path','đường GPU'],unknown:['no file data','chưa có file']};
  const SUB={draft:['Draft','Nháp'],wait_full:["Waiting for a 'full' / 'force-ci' / 'mp' label (starts MP GPU)","Chờ nhãn 'full' / 'force-ci' / 'mp' (bắt đầu MP GPU)"],ci_missing:['Required check not run','Check bắt buộc chưa chạy'],old:['Older than 30 days','Cũ hơn 30 ngày'],ci_run:['CI running','CI đang chạy'],ci_fail:['Required check failing','Check bắt buộc đang đỏ'],wait_review:['Waiting review','Chờ review'],adapt:['Changes requested (adapt)','Yêu cầu sửa (adapt)'],ready:['Approved, ready','Đã duyệt, sẵn sàng'],conflict:['Merge conflict','Xung đột merge']};
  const KIND={semantic:['Shared source file','Chung file nguồn'],race:['Stale CI (race)','CI cũ (race)'],duplicate:['Duplicate?','Trùng?'],touch:['Shared files','Chung file'],flaky:['Flaky','Flaky']};
  const st=s=>el('span',{class:'gch s-'+(s==='none'?'none':s)},s);
  const typeTag=t=>el('span',{class:'obs-lab'},L(TYPE[t]||TYPE.other));
  const sec=k=>document.querySelector(`section[data-ops="${k}"]`);
  const GH='https://github.com/LMCache/LMCache/pull/';
  const delta=(b)=>{if(b.value==null||b.prev==null||!b.prev)return el('span',{class:'dl same'},T('no previous period','chưa có kỳ trước'));const d=(b.value-b.prev)/b.prev*100;
    const good=b.better==='up'?d>0:d<0;const cls=Math.abs(d)<2?'same':good?'better':'worse';return el('span',{class:'dl '+cls},`${d>0?'▲':'▼'} ${Math.abs(d).toFixed(0)}% ${T('vs previous 30 d','so với 30 ngày trước')} (${fmt(b.prev)}${b.unit&&b.unit!=='%'&&b.unit!=='/day'?' '+b.unit:b.unit==='%'?'%':''})`);};
  function spark(vals,lab){if(!vals||!vals.length)return null;const NS='http://www.w3.org/2000/svg',w=240,h=36,mx=Math.max(...vals,1),bw=w/vals.length;const s=document.createElementNS(NS,'svg');s.setAttribute('viewBox',`0 0 ${w} ${h}`);s.setAttribute('class','ops-spark');s.setAttribute('preserveAspectRatio','none');s.setAttribute('role','img');s.setAttribute('aria-label',lab);
    vals.forEach((v,i)=>{const r=document.createElementNS(NS,'rect'),bh=Math.max(1,(h-2)*v/mx);r.setAttribute('x',i*bw+1);r.setAttribute('width',Math.max(1,bw-2));r.setAttribute('y',h-bh);r.setAttribute('height',bh);r.setAttribute('rx',Math.min(2,bw/3));
      const t=document.createElementNS(NS,'title');t.textContent=`${T('day','ngày')} ${i+1}/${vals.length}: ${v}`;r.append(t);s.append(r);});return s;}
  function mcard(b){return el('div',{class:'ops-card'},el('div',{class:'n'},L(b.name)),el('div',{class:'v'},fmt(b.value),el('small',{},U(b.unit))),
      b.p90!=null?el('div',{class:'d'},`p90: ${fmt(b.p90)} ${b.unit}`):null,delta(b),spark(b.series,L(b.name)),el('div',{class:'d'},L(b.defn)),el('div',{class:'d'},T('Source: ','Nguồn: '),el('span',{class:'obsraw'},b.src)));}

  const VERD={ready:['Ready for an RC','Sẵn sàng cắt RC','good'],almost:['Almost ready: warnings only','Gần sẵn sàng: chỉ còn cảnh báo','warn'],not_ready:['Not ready for an RC','Chưa sẵn sàng cắt RC','bad']};
  function rSummary(){const s=sec('summary');if(!s)return;const C=D.coming,S=C.summary;if(!S){s.remove();return;}
    const v=VERD[S.verdict],bt=S.by_type;
    s.replaceChildren(head('3F',`${S.ver} · Automatic RC checklist`,`${S.ver} · Checklist cắt RC tự động`));
    s.append(el('div',{class:'ops-verdict',style:`border-left-color:var(--${v[2]==='good'?'good':v[2]==='warn'?'warning':'critical'})`},
      el('div',{},el('b',{},L(v)),S.n_bad?T(` · ${S.n_bad} blocking item(s)`,` · ${S.n_bad} mục chặn`):''),
      el('div',{style:'margin-top:4px'},T(`${S.ver} = everything merged into dev after ${S.stable} (${C.scope.tag_sha||'?'}) up to origin/dev ${C.scope.head||'?'} (${day(C.scope.head_at)}): ${S.n_scope} PRs. ${S.n_user} are user-facing (${bt.feature||0} features, ${bt.bug||0} bug fixes, ${bt.perf||0} perf, ${bt.other||0} without a type prefix${(r=>r>0?`, ${r} other types (refactor / docs / CI) already in the notes`:'')(S.n_user-(bt.feature||0)-(bt.bug||0)-(bt.perf||0)-(bt.other||0))}); ${S.n_internal} are internal (refactor, tests, CI, docs).${S.breaking.length?' Possibly breaking: '+S.breaking.map(n=>'#'+n).join(', ')+'.':''}`,
        `${S.ver} = mọi thứ merge vào dev sau ${S.stable} (${C.scope.tag_sha||'?'}) tới origin/dev ${C.scope.head||'?'} (${day(C.scope.head_at)}): ${S.n_scope} PR. ${S.n_user} PR người dùng thấy được (${bt.feature||0} feature, ${bt.bug||0} sửa bug, ${bt.perf||0} perf, ${bt.other||0} không có tiền tố loại${(r=>r>0?`, ${r} loại khác (refactor / docs / CI) đã có trong note`:'')(S.n_user-(bt.feature||0)-(bt.bug||0)-(bt.perf||0)-(bt.other||0))}); ${S.n_internal} PR nội bộ (refactor, test, CI, docs).${S.breaking.length?' Có thể không tương thích (breaking): '+S.breaking.map(n=>'#'+n).join(', ')+'.':''}`))));
    const ICON={ok:'✓',warn:'•',bad:'!'},CL={ok:'s-ok',warn:'s-run',bad:'s-fail'};
    s.append(el('h3',{},T('RC checklist','Checklist cắt RC')),el('div',{class:'ops-rules'},S.checks.map(c=>el('div',{class:'ops-rule lv-'+(c.lvl==='ok'?'good':c.lvl)},el('span',{class:'gch '+CL[c.lvl]},ICON[c.lvl]),' ',L(c.t)))));
    const P=S.prep;
    if(P){const od=P.decisions.filter(d=>d.open),ob=P.blockers.filter(b=>b.open);
      // the decisions and carry-over blockers are decided in Now · Release Desk (dkDecide / dkBlock); here only their ids + a link (merged 2026-11-24)
      if(od.length||ob.length){const go=el('button',{type:'button','data-goto':'obs/today'},T('Now · Release Desk','Bây giờ · Release Desk')+' →');
        s.append(el('div',{class:'ops-src'},T(`Open decisions and carry-over blockers (${od.length+ob.length}) from `,`Quyết định còn mở và blocker tồn (${od.length+ob.length}) từ `),el('code',{},P.rel),': ',el('span',{class:'obsraw'},[...od,...ob].map(x=>x.id).join(', ')),T(' · decided in ',' · quyết tại '),go));}}
    s.append(el('p',{class:'ops-src'},T('Verdict = "not ready" if any checklist item is red, "almost" if only warnings. Inputs: git range (local clone), PR snapshot, Trace Agent proposals, the release list and RELEASE_PREP.md of the target release folder.','Kết luận = "chưa sẵn sàng" nếu có mục đỏ, "gần sẵn sàng" nếu chỉ còn cảnh báo. Đầu vào: khoảng git (clone local), snapshot PR, đề xuất Trace Agent, danh sách release và RELEASE_PREP.md trong thư mục release mục tiêu.')));}

  const ORIG={listed:['In notes','Đã có trong note'],suggested:['Suggested','Đề xuất thêm'],open:['Open PR','PR đang mở']};
  const NOTE={ok:'s-ok',bad:'s-fail',warn:'s-run',info:'s-none'};
  const SCOPE={required:['Required','Bắt buộc','s-fail'],conditional:['Conditional','Có điều kiện','s-run'],unit:['Unit only','Chỉ unit','s-none'],none:['None','Không','s-ok']};
  const AN=id=>((D.coming||{}).area_names||{})[id]||id;
  window.opsOpenFeature=id=>{if(!window.vizNav)return;vizNav.show('cpu','tiers');setTimeout(()=>{const r=document.querySelector(`#fm tr.ar[data-area="${id}"]`);
    if(r){if(r.getAttribute('aria-expanded')!=='true')r.click();r.scrollIntoView({behavior:'smooth',block:'center'});r.classList.add('ops-flash');setTimeout(()=>r.classList.remove('ops-flash'),1600);}},150);};
  const fchip=(id,main)=>el('button',{type:'button',class:'ops-feat'+(main?' main':''),title:T('Open the feature definition in Release Exploration','Mở định nghĩa feature ở Khám phá Release'),onclick:()=>opsOpenFeature(id)},AN(id));
  const scopeChip=(lv,tag)=>el('span',{class:'gch '+SCOPE[lv][2]},`${tag} ${L(SCOPE[lv])}`);
  const stageName=i=>i==null?T('off the KV path','ngoài đường KV'):L(((D.coming||{}).flow||[])[i]?.name);
  function featLine(f){if(!f||!f.prim)return null;return el('div',{class:'ops-featline'},fchip(f.prim,true),(f.rel||[]).slice(0,3).map(r=>fchip(r,false)),
    el('span',{class:'meta'},` · ${T('critical stage','stage quan trọng')}: `),el('b',{},stageName(f.stage)),' ',scopeChip(f.cpu.level,'CPU'),' ',scopeChip(f.gpu.level,'GPU'));}
  const PICK_KEY='opsPicked';
  const picked=()=>{try{return JSON.parse(localStorage.getItem(PICK_KEY)||'null');}catch(e){return null;}};
  const savePick=m=>{try{localStorage.setItem(PICK_KEY,JSON.stringify(m));}catch(e){}};
  const LVO={none:0,unit:1,conditional:2,required:3};
  function rComing(){const s=sec('coming');if(!s)return;const C=D.coming,R=C.roadmap,CA=C.cands||[],FL=C.flow||[],ver=R&&R.src.version?'v'+R.src.version:T('next release','release tới');
    s.replaceChildren(head('3G',`Release-note PRs by feature · ${ver}`,`PR cho release note theo feature · ${ver}`,
      `Pick the PRs for the release notes. Scope = git ${C.stable} (${C.scope.tag_sha||'?'})..origin/dev (${C.scope.head||'?'}, ${day(C.scope.head_at)}).`,
      `Chọn PR cho release note. Phạm vi = git ${C.stable} (${C.scope.tag_sha||'?'})..origin/dev (${C.scope.head||'?'}, ${day(C.scope.head_at)}).`));
    if(R)s.append(el('p',{class:'obs-note'},T('List source: ','Nguồn danh sách: '),el('code',{},R.src.rel),T(` (saved ${day(R.src.mtime)}). Another source: COMING_RELEASE_SRC=<file>.`,` (lưu ${day(R.src.mtime)}). Nguồn khác: COMING_RELEASE_SRC=<file>.`)));
    // selection: default = PRs already in the list
    let P=picked();if(!P){P={};CA.filter(c=>c.origin==='listed').forEach(c=>P[c.num]=1);}
    const lis=CA.filter(c=>c.origin==='listed'),sug=CA.filter(c=>c.origin==='suggested'),act=CA.filter(c=>c.rank===0).length;
    const kp=el('div',{class:'ops-kpis'});
    const drawKpi=()=>kp.replaceChildren(kpi(fmt(Object.keys(P).length),T('PRs picked for the notes','PR đã chọn cho release note'),'good'),kpi(fmt(act),T('need action now','cần xử lý ngay'),act?'bad':''),
      kpi(`${lis.filter(c=>c.notes.some(n=>n[0]==='ok')).length}/${lis.length}`,T('PRs in notes that ship','PR đã có trong note sẽ ship')),kpi(fmt(sug.length),T('user-facing PRs missing from notes','PR người dùng thấy được chưa có trong note'),sug.length?'warn':''));
    drawKpi();s.append(kp);
    // KV path strip
    const per=FL.map((_,i)=>CA.filter(c=>c.feat&&c.feat.stage===i).length);
    s.append(el('div',{class:'ops-flow'},FL.map((st_,i)=>el('div',{class:'ops-fstep'+(per[i]?' hit':'')},el('div',{class:'t'},L(st_.name)),el('div',{class:'v'},per[i]?T(`${per[i]} PRs`,`${per[i]} PR`):'—'))).flatMap((n,i)=>i?[el('span',{class:'ops-farr'},'→'),n]:[n])));
    const row=c=>el('tr',{},
      el('td',{class:'ops-pick'},el('input',{type:'checkbox','aria-label':T(`pick #${c.num}`,`chọn #${c.num}`),...(P[c.num]?{checked:''}:{}),onchange:e=>{if(e.target.checked)P[c.num]=1;else delete P[c.num];savePick(P);drawKpi();}})),
      el('td',{},el('div',{class:'ttl'},a(GH+c.num,'#'+c.num),' ',el('span',{class:'obsraw'},c.title)),
        el('div',{class:'meta'},L(ORIG[c.origin]),' · ',c.origin==='suggested'?T('suggested section: ','mục đề xuất: '):'',c.section==='section to pick'?T('section to pick','cần chọn mục'):el('span',{class:'obsraw'},c.section),c.at?` · ${day(c.at)}`:''),
        c.feat&&c.feat.rel&&c.feat.rel.length?el('div',{class:'ops-featline'},el('span',{class:'meta'},T('related: ','liên quan: ')),c.feat.rel.slice(0,3).map(r=>fchip(r,false))):null),
      el('td',{},c.notes.map(n=>el('div',{},el('span',{class:'gch '+NOTE[n[0]]},n[0]==='ok'?'✓':n[0]==='bad'?'!':n[0]==='warn'?'•':'i'),L([n[1],n[2]]))),c.why?el('div',{class:'ops-why'},el('b',{},T('Rationale: ','Lý do: ')),L(c.why)):null,
        (c.ta||[]).map(t=>el('div',{class:'ops-why',style:'border-left:2px solid var(--warning);padding-left:6px;margin-top:4px'},el('b',{},`Trace Agent (${t.tag}): `),'🔎 ',L(t.root),t.fix?el('div',{},'🛠️ ',L(t.fix)):null))));
    let GB='feature';
    const keyOf=c=>GB==='feature'?((c.feat&&c.feat.prim)||'_none'):GB==='stage'?(c.feat&&c.feat.stage!=null?'st'+c.feat.stage:'_off'):(c.section&&c.section!=='—'&&c.section!=='section to pick'?c.section:'_pick');
    const groupsOf=list=>{const g={};list.forEach(c=>{const k=keyOf(c);(g[k]=g[k]||[]).push(c);});
      return Object.entries(g).map(([k,v])=>{const st_=GB==='stage'?(k.startsWith('st')?+k.slice(2):null):GB==='feature'&&k!=='_none'?((v.find(c=>c.feat)||{}).feat||{}).stage:null;const mx=lvk=>v.reduce((m,c)=>c.feat&&LVO[c.feat[lvk].level]>LVO[m]?c.feat[lvk].level:m,'none');
        return {k,v,stage:st_==null?null:st_,cpu:mx('cpu'),gpu:mx('gpu'),act:v.filter(c=>c.rank===0).length};})
        .sort((x,y)=>(y.act-x.act)||((x.stage==null)-(y.stage==null))||((x.stage??9)-(y.stage??9))||(y.v.length-x.v.length));};
    const FLT=[['add',T(`Missing from notes (${sug.length})`,`Chưa có trong note (${sug.length})`),CA.filter(c=>c.origin==='suggested'||c.rank===0)],['list',T(`In notes (${lis.length})`,`Đã có trong note (${lis.length})`),lis],['all',T(`All (${CA.length})`,`Tất cả (${CA.length})`),CA]];
    const bar=el('div',{class:'ops-filter'}),box=el('div');
    const draw=k_=>{bar.querySelectorAll('button[data-k]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.k===k_)));const G=groupsOf(FLT.find(f=>f[0]===k_)[2]);
      const t=el('table',{class:'obs-t'});t.append(el('thead',{},el('tr',{},el('th',{},''),el('th',{},'PR'),el('th',{},T('Checks · rationale','Kiểm tra · lý do')))));const tb=el('tbody');
      const gTitle=g=>GB==='feature'?(g.k==='_none'?el('b',{},T('No LMCache feature (docs, tests, examples)','Không thuộc feature LMCache (docs, test, ví dụ)')):fchip(g.k,true))
        :GB==='stage'?el('b',{},g.k==='_off'?T('Off the KV path (CLI, control plane, build, docs)','Ngoài đường KV (CLI, điều khiển, build, docs)'):stageName(g.stage))
        :el('b',{},g.k==='_pick'?T('Section to pick','Cần chọn mục'):el('span',{class:'obsraw'},g.k));
      G.forEach(g=>{tb.append(el('tr',{class:'ops-grp'},el('td',{colspan:'3'},gTitle(g),' ',
          el('span',{class:'meta'},`${g.v.length} PR · `),GB!=='feature'||g.k==='_none'?(GB==='feature'?null:el('span',{},scopeChip(g.cpu,'CPU'),' ',scopeChip(g.gpu,'GPU'))):el('span',{},g.stage==null?el('span',{class:'meta'},stageName(null)):el('b',{style:'color:var(--text-primary)'},'→ '+stageName(g.stage)),' ',scopeChip(g.cpu,'CPU'),' ',scopeChip(g.gpu,'GPU')))));
        g.v.forEach(c=>tb.append(row(c)));});
      t.append(tb);box.replaceChildren(el('p',{class:'meta ops-narrow'},T('Scroll the table sideways →','Kéo bảng sang ngang →')),el('div',{class:'obs-scroll'},t));};
    FLT.forEach(([k_,lab])=>bar.append(el('button',{type:'button','data-k':k_,onclick:()=>draw(k_)},lab)));
    const cur=()=>(bar.querySelector('button[data-k][aria-pressed="true"]')||{dataset:{k:'add'}}).dataset.k;
    bar.append(el('span',{class:'meta',style:'margin-left:10px'},T('Group by:','Nhóm theo:')),...[['feature',T('Feature','Feature')],['stage',T('KV-path stage','Stage trên đường KV')],['section',T('Notes section','Mục release note')]].map(([g_,lab])=>
      el('button',{type:'button','data-g':g_,'aria-pressed':String(g_===GB),onclick:e=>{GB=g_;bar.querySelectorAll('button[data-g]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.g===GB)));draw(cur());}},lab)));
    // export the picked PRs as a "Coming in vX" list
    const out=el('div');
    bar.append(el('span',{style:'flex:1'}),el('button',{type:'button',class:'tr-btn sm',onclick:()=>{const pick=CA.filter(c=>P[c.num]);const by={};
      pick.forEach(c=>{const brk=/possibly breaking|có thể không tương thích/i.test(c.notes.map(n=>n[1]).join(' '));const sec_=brk?'Breaking changes':(c.section==='section to pick'||!c.section||c.section==='—')?'Other changes':c.section;(by[sec_]=by[sec_]||[]).push(c);});
      const order=['Breaking changes',...Object.keys(by).filter(x=>x!=='Breaking changes')];
      // release-note line: the curated ROADMAP wording when the PR is already in the notes, else the PR title without
      // [tags] and conventional-commit prefixes; PRs of one notes item share one line
      const clean=t=>{const s=(t||'').replace(/^(\s*\[[^\]]*\])+\s*/,'').replace(/^(feat|feature|fix|bugfix|hotfix|docs?|perf|refactor|chore|ci|build|test|misc)(\([^)]*\))?!?:\s*/i,'').trim();return s.charAt(0).toUpperCase()+s.slice(1);};
      const lines=cs=>{const g=new Map();cs.forEach(c=>{const k=c.note_text||clean(c.title);if(!g.has(k))g.set(k,[]);g.get(k).push(c.num);});return [...g].map(([k,ns])=>`- ${k} (${ns.map(n=>'#'+n).join(', ')})`).join('\n');};
      const md=`**Coming in ${ver}.** The following changes were merged to \`dev\` after ${C.stable} was cut (tag commit \`${C.scope.tag_sha||'?'}\`).\n\n`+order.filter(x=>by[x]).map(x=>`**${x}**\n`+lines(by[x])).join('\n\n');
      const ta=el('textarea',{class:'ops-md',rows:'12',readonly:''});ta.value=md;
      out.replaceChildren(el('div',{class:'meta'},T(`${pick.length} picked PRs as a "Coming in ${ver}" list (paste into the release folder's ROADMAP.md):`,`${pick.length} PR đã chọn dưới dạng danh sách "Coming in ${ver}" (dán vào ROADMAP.md của thư mục release):`)),ta,
        el('button',{type:'button',class:'tr-btn sm',onclick:e=>{try{navigator.clipboard.writeText(md);e.target.textContent='✓';}catch(x){}}},T('Copy','Chép')));}},T('Export picked list','Xuất danh sách đã chọn')),
      el('button',{type:'button',class:'tr-btn sm',onclick:()=>{P={};CA.filter(c=>c.origin==='listed').forEach(c=>P[c.num]=1);savePick(P);drawKpi();draw(cur());}},T('Reset to the list','Đặt lại theo danh sách')));
    s.append(bar,out,box);draw('add');
    if(!R)s.append(el('div',{class:'ops-empty'},T('No external list yet: put a "Coming in vX" list in release-<next>/ROADMAP.md or set COMING_RELEASE_SRC, then rebuild. Showing suggestions only.','Chưa có danh sách ngoài: đặt danh sách "Coming in vX" vào release-<next>/ROADMAP.md hoặc đặt COMING_RELEASE_SRC, rồi build lại. Chỉ hiện đề xuất.')));
    s.append(el('p',{class:'ops-src'},T('Feature = the area most of the PR\'s source files belong to (the 29 areas of Release Exploration; click one to open its definition). Critical stage = where that feature sits on the KV path. CPU / GPU test level comes from the change class in Quality Gate. Picks are kept in this browser.',
      'Feature = nhóm mà phần lớn file source của PR thuộc về (29 nhóm của Khám phá Release; bấm để mở định nghĩa). Stage quan trọng = vị trí của feature đó trên đường KV. Mức test CPU / GPU lấy từ loại thay đổi ở Cổng chất lượng. Lựa chọn được lưu trong trình duyệt này.')));
    // round 3 (C_ia 3G, A_visual 5.5): a work tool, not status: one summary line, the picker opens on demand; the shared reason is said here once
    {const kids=[...s.children].slice(1),np=Object.keys(P).length;const det=el('details',{class:'ops-picker','data-ux':'notes-picker'});
      det.append(el('summary',{},el('b',{},T('Release-note picker','Bộ chọn release note')),' · ',T(`${np} picked`,`${np} đã chọn`),' · ',
        sug.length?T(`${sug.length} PRs merged after ${C.stable} ship in ${ver} but are not in the notes`,`${sug.length} PR merge sau ${C.stable} sẽ ship trong ${ver} nhưng chưa có trong release note`):T('every user-facing PR is in the notes','mọi PR người dùng thấy được đã có trong note'),
        ' · ',el('span',{class:'ops-open'},T('open picker ▸','mở bộ chọn ▸'))));det.append(...kids);s.append(det);}}

  function rBase(){const s=document.getElementById('optBase');if(!s)return;s.replaceChildren(head('','30-day baseline','Baseline 30 ngày',`Shared baseline for every CI task: ${D.window?D.window.join(' → '):''}, compared with the 30 days before.`,`Baseline chung cho mọi task CI: ${D.window?D.window.join(' → '):''}, so với 30 ngày trước đó.`),
    el('div',{class:'ops-mc'},D.base.map(mcard)));}

  const V3ST={better:['better','tốt hơn','s-ok','✓'],worse:['worse','xấu hơn','s-fail','!'],same:['about the same','gần như không đổi','s-none','='],info:['now','hiện tại','s-none','i'],
    watch:['needs attention','cần chú ý','s-run','!'],mixed:['mixed: some rows better, some worse or to watch (open to see which)','lẫn lộn: có dòng tốt hơn, có dòng tệ hơn hoặc cần theo dõi (mở để xem)','s-run','!']};
  const GCOL={1:'var(--series-1)',2:'var(--series-2)'};
  const DIRN={A:['A · PR flow','A · Luồng PR'],B:['B · Public CI (publish / nightly)','B · CI public (publish / nightly)'],'B*':['B · other dev-push CI','B · CI khác chạy khi push dev'],'A+B':['A + B','A + B']};
  const STG={create:['Create PR','Tạo PR'],review:['Human review','Người review'],merge:['Merge PR','Merge PR'],'dev push':['push to dev','push vào dev'],nightly:['nightly','nightly']};
  function rOptSum3(){const s=sec('opt-sum3');if(!s)return;const V=((D.opt||{}).v3)||{goals:[]};
    s.replaceChildren(head('4A','Is CI helping PRs merge faster?','CI có giúp PR merge nhanh hơn không?','Two goals, each compared with the previous 30 days. CI cost is not a goal: it shows up as the expected gain of a proposed change below.','Hai mục tiêu, mỗi mục tiêu so với 30 ngày trước. Chi phí CI không phải mục tiêu: nó hiện như lợi ích dự kiến của từng thay đổi đề xuất bên dưới.'));
    const vb=V.goals.map(g=>el('div',{},el('b',{},L(g.name)),': ',el('span',{class:'gch '+V3ST[g.verdict][2]},V3ST[g.verdict][3]),' ',L(V3ST[g.verdict])));
    const worst=V.goals.some(g=>g.verdict==='worse')?'critical':V.goals.every(g=>g.verdict==='better')?'good':'warning';
    const endAgo=D.window?Math.round((Date.now()-Date.parse(D.window[1]))/864e5):null;
    s.append(el('div',{class:'ops-verdict',style:`border-left-color:var(--${worst})`},vb,
      endAgo>2?el('div',{class:'meta',style:'margin-top:6px;color:var(--text-primary);border-left:3px solid var(--warning);padding-left:6px'},T(`30-day PR numbers end on ${D.window[1]} (${endAgo} days ago): re-run the daily report for current numbers.`,`Số liệu PR 30 ngày kết thúc ngày ${D.window[1]} (${endAgo} ngày trước): chạy lại báo cáo ngày để có số mới.`)):null));
    V.goals.forEach(g=>{s.append(el('h3',{style:`margin-top:12px;border-left:3px solid ${GCOL[g.id]};padding-left:8px`},L(g.name)));
      s.append(el('div',{class:'ops-rules'},g.rows.map(r=>{const v=V3ST[r.state],u=U(r.unit);
        return el('div',{class:'ops-rule lv-'+(r.state==='better'?'good':r.state==='worse'?'bad':r.state==='watch'?'warn':'info')},el('span',{class:'gch '+v[2]},v[3]),' ',L(r.label),': ',el('b',{},`${fmt(r.now)} ${u}`),
          r.prev!=null?T(` (previous 30 d: ${fmt(r.prev)} ${u})`,` (30 ngày trước: ${fmt(r.prev)} ${u})`):'',r.note?el('span',{class:'meta'},' · '+L(r.note)):null);})));});
    s.append(el('p',{class:'ops-src'},T(`Goal 2 reads the feature list from the roadmap file; daily-meeting feature notes can be added later as a text file. 30-day PR numbers: daily report up to ${D.window?D.window[1]:'—'}; test numbers: git origin/dev.`,`Mục tiêu 2 đọc danh sách feature từ file roadmap; ghi chú feature từ daily meeting có thể thêm sau dưới dạng file text. Số PR 30 ngày: báo cáo ngày tới ${D.window?D.window[1]:'—'}; số liệu test: git origin/dev.`)));}

  const CELLN={created:['PR created → CI','Tạo PR → CI'],approve:['Review → approve','Review → duyệt'],merge:['After merge','Sau merge']};
  const actAnchor=id=>'opt-a-'+id.replace(/[^a-z0-9]+/gi,'-');
  function rOptCells(){const s=sec('opt-cells');if(!s)return;const V=((D.opt||{}).v3)||{},SC=V.stage_costs,A=V.actions||[];
    s.replaceChildren(head('4B','Where CI time goes: PR stage × CPU / GPU','Thời gian CI đi đâu: giai đoạn PR × CPU / GPU',
      'Each cell: job-minutes per day in that PR stage, how much ended cancelled or failed, the biggest workflows, and the proposed changes for that cell (click one to jump to it).',
      'Mỗi ô: số phút job mỗi ngày ở giai đoạn PR đó, bao nhiêu kết thúc bị huỷ hoặc fail, các workflow lớn nhất, và thay đổi đề xuất cho ô đó (bấm để nhảy tới).'));
    if(!SC){s.append(el('div',{class:'ops-empty'},T('No CI cost data yet: run observe_ops_collect.py.','Chưa có dữ liệu chi phí CI: chạy observe_ops_collect.py.')));return;}
    const t=el('table',{class:'obs-t ops-cells'});
    t.append(el('thead',{},el('tr',{},el('th',{},''),SC.stages.map(st_=>el('th',{},L(st_.name))))));
    const b=el('tbody');
    [['CPU',T('CPU · GitHub Actions','CPU · GitHub Actions')],['GPU',T('GPU · Buildkite (k3 + other accelerators)','GPU · Buildkite (k3 + accelerator khác)')]].forEach(([hw,lab])=>{
      b.append(el('tr',{},el('th',{style:'text-align:left;white-space:nowrap'},lab),SC.stages.map(st_=>{const c=SC.cells[`${st_.id}|${hw}`]||{},sol=A.filter(a=>a.cell&&a.cell[0]===st_.id&&a.cell[1]===hw);
        const pc=x=>c.total?Math.round(100*x/c.total):0;
        const c30=(S30()||{cells:{}}).cells[`${st_.id}|${hw}`];
        return el('td',{},c30?el('div',{},el('b',{style:'font-size:18px'},range30(c30)),' ',el('span',{class:'meta'},T('job-min/day (7-day means, 30 d)','phút job/ngày (trung bình 7 ngày, 30 ngày)')),c.total?el('div',{class:'meta'},T(`sample: ${fmt(c.total)}`,`mẫu: ${fmt(c.total)}`)):null):c.total?el('div',{},el('b',{style:'font-size:18px'},fmt(c.total)),' ',el('span',{class:'meta'},T('job-min/day (sample)','phút job/ngày (mẫu)'))):el('div',{class:'meta'},hw==='CPU'&&st_.id==='approve'?T('no separate CPU run: review fixes are new pushes, counted in "PR created"','không có lần chạy CPU riêng: sửa theo review là push mới, tính ở "Tạo PR"'):'—'),
          c.total?el('div',{class:'meta'},T(`${pc(c.cancelled)}% cancelled · ${pc(c.failed)}% failed`,`${pc(c.cancelled)}% bị huỷ · ${pc(c.failed)}% fail`)):null,
          (c.top||[]).length?el('div',{class:'meta obsraw'},c.top.map(x=>`${x[0]} ${fmt(x[1])}`).join(' · ')):null,
          el('div',{style:'margin-top:6px'},sol.length?sol.map(a_=>el('a',{href:'#',class:'ops-sol '+a_.lvl,onclick:e=>{e.preventDefault();const r=document.getElementById(actAnchor(a_.id));if(r){r.scrollIntoView({behavior:'smooth',block:'center'});r.classList.add('ops-flash');setTimeout(()=>r.classList.remove('ops-flash'),1600);}}},L(a_.title))):el('span',{class:'meta'},T('no proposed change','chưa có thay đổi đề xuất'))));})));});
    t.append(b);s.append(el('div',{class:'obs-scroll'},t));
    s.append(el('p',{class:'ops-src'},T(`PR created = PR-triggered runs (GitHub Actions, k3-unit and accelerator suites). Review → approve = k3-multiprocess-test on PRs, which starts after the 'full' label. After merge = runs on dev pushes, schedules and tags. Large number: 30-day baseline ${(S30()||{window:['?','?']}).window.join(' → ')}, lowest–highest 7-day mean. Sample: ${smpTxt(SC)}, window ${SC.span_h} h, scaled to 24 h.`,
      `Tạo PR = các lần chạy do PR kích hoạt (GitHub Actions, k3-unit và bộ accelerator). Review → duyệt = k3-multiprocess-test trên PR, chạy sau khi gắn nhãn 'full'. Sau merge = các lần chạy khi push dev, theo lịch và tag. Số lớn: baseline 30 ngày ${(S30()||{window:['?','?']}).window.join(' → ')}, trung bình 7 ngày thấp nhất–cao nhất. Mẫu: ${smpTxt(SC)}, khung ${SC.span_h} giờ, quy về 24 giờ.`)));}

  const applied=()=>{try{return JSON.parse(localStorage.getItem('opsApplied')||'{}');}catch(e){return {};}};
  function applyBox(a_){const S=a_.solution,R=a_.result||{},u=U(R.unit),loc=applied()[a_.id];
    if(S&&S.applied){const ch=R.change_pct,good=ch==null?null:(R.better==='up'?ch>0:ch<0);
      return el('div',{},el('span',{class:'gch s-ok'},T('Applied','Đã áp dụng')),` ${S.applied}`,el('div',{},T('before ','trước '),el('b',{},`${fmt(R.before)} ${u}`),' → ',R.after!=null?el('b',{},`${fmt(R.after)} ${u}`):T('waiting for data','chờ dữ liệu'),
        ch!=null?el('b',{style:`color:var(--${good?'good':'critical'})`},` (${ch>0?'+':''}${ch}%)`):null),el('div',{class:'meta'},L(R.metric)));}
    const cmd=`python -I -X utf8 apply_solution.py "${a_.id}" --date ${new Date().toISOString().slice(0,10)}`;
    const box=el('div');
    const draw=()=>{const lc=applied()[a_.id];box.replaceChildren(
      el('div',{class:'meta'},T('now ','hiện tại '),el('b',{},`${fmt(R.now)} ${u}`),' · ',L(R.metric)||'—'),
      lc?el('div',{class:'ops-apply'},el('div',{},el('span',{class:'gch s-run'},T('Marked applied','Đã đánh dấu áp dụng')),` ${lc}`),
          el('div',{class:'meta'},T('To start measuring, run once in outputs/cpu_tests (freezes the current value as the baseline):','Để bắt đầu đo, chạy một lần trong outputs/cpu_tests (chốt giá trị hôm nay làm baseline):')),
          el('code',{class:'obsraw'},cmd),' ',el('button',{type:'button',class:'tr-btn sm',onclick:e=>{try{navigator.clipboard.writeText(cmd);e.target.textContent='✓';}catch(x){}}},T('Copy','Chép')),
          ' ',el('button',{type:'button',class:'tr-btn sm',onclick:()=>{const m=applied();delete m[a_.id];try{localStorage.setItem('opsApplied',JSON.stringify(m));}catch(x){}draw();}},T('Undo','Bỏ')))
        :el('button',{type:'button',class:'tr-btn sm ops-applybtn',onclick:()=>{const m=applied();m[a_.id]=new Date().toISOString().slice(0,10);try{localStorage.setItem('opsApplied',JSON.stringify(m));}catch(x){}draw();}},T('Mark as applied','Đánh dấu đã áp dụng')));};
    draw();return box;}

  // ---------- Optimal CI split by hardware: one sub-tab for CPU (GitHub Actions), one for GPU (Buildkite)
  const HWI={CPU:{p:'oc',n:4,name:['CI cost · GitHub Actions (CPU runners)','Chi phí CI · GitHub Actions (runner CPU)'],unit:['job-min/day','phút job/ngày']},
             GPU:{p:'og',n:5,name:['CI cost · Buildkite (GPU and accelerator agents)','Chi phí CI · Buildkite (agent GPU và accelerator)'],unit:['job-min/day','phút job/ngày']}};
  const STG3=[['created',['1 · Pre-merge CI (every push)','1 · CI trước merge (mỗi lần push)']],['approve',['2 · Approval gate (full label → MP suite)','2 · Cổng duyệt (nhãn full → bộ MP)']],['merge',['3 · Post-merge (dev, nightly, publish)','3 · Sau merge (dev, nightly, publish)']]];
  const STGWHAT={CPU:{created:['GitHub Actions runs started by a PR push (lint, Test matrix, CPU device, PR build).','Các lần chạy GitHub Actions do push PR (lint, ma trận Test, CPU device, PR build).'],
      approve:['No separate CPU run: each review fix is a new push, counted in stage 1. What slows this stage is the wait for a reviewer.','Không có lần chạy CPU riêng: mỗi lần sửa theo review là push mới, tính ở bước 1. Thứ làm chậm bước này là chờ người review.'],
      merge:['Runs on dev pushes, schedules and tags: publish.yml, docs, nightly, scorecard.','Các lần chạy khi push dev, theo lịch và tag: publish.yml, docs, nightly, scorecard.']},
    GPU:{created:['Buildkite PR builds that start on every push: k3-unit-tests and the accelerator suites.','Build Buildkite của PR chạy mỗi lần push: k3-unit-tests và các bộ accelerator.'],
      approve:["k3-multiprocess-test (MP GPU, required) starts only after a maintainer adds the 'full' label, usually at approval.","k3-multiprocess-test (MP GPU, bắt buộc) chỉ chạy sau khi maintainer gắn nhãn 'full', thường lúc duyệt."],
      merge:['Buildkite builds on dev after the merge (k3 and accelerator pipelines).','Build Buildkite trên dev sau khi merge (pipeline k3 và accelerator).']}};
  function goalBox(){const V=((D.opt||{}).v3)||{goals:[]},endAgo=D.window?Math.floor((Date.now()-Date.parse(D.window[1])-864e5)/864e5):null;  // age from the exclusive end (G8)
    const worst=V.goals.some(g=>g.verdict==='worse')?'critical':V.goals.every(g=>g.verdict==='better')?'good':'warning';
    return el('div',{class:'ops-verdict',style:`border-left-color:var(--${worst})`},
      V.goals.map(g=>el('details',{},el('summary',{},el('b',{},L(g.name)),': ',el('span',{class:'gch '+V3ST[g.verdict][2]},V3ST[g.verdict][3]),' ',L(V3ST[g.verdict])),
        el('div',{class:'ops-rules',style:'margin-top:6px'},g.rows.map(r=>{const v=V3ST[r.state],u=U(r.unit);return el('div',{class:'ops-rule lv-'+(r.state==='better'?'good':r.state==='worse'?'bad':r.state==='watch'?'warn':'info')},
          el('span',{class:'gch '+v[2]},v[3]),' ',L(r.label),': ',el('b',{},`${fmt(r.now)} ${u}`),r.prev!=null?T(` (previous 30 d: ${fmt(r.prev)} ${u})`,` (30 ngày trước: ${fmt(r.prev)} ${u})`):'',r.note?el('span',{class:'meta'},' · '+L(r.note)):null);})))),
      endAgo>2?el('div',{class:'meta',style:'margin-top:6px;color:var(--text-primary);border-left:3px solid var(--warning);padding-left:6px'},T(`Goal rows come from the daily PR report, which ends on ${D.window[1]} (${endAgo} d old): re-run the daily report. The cost cards below have their own dates.`,`Các dòng mục tiêu lấy từ báo cáo PR hằng ngày, kết thúc ${D.window[1]} (cũ ${endAgo} ngày): chạy lại báo cáo ngày. Các thẻ chi phí bên dưới có ngày riêng.`)):null);}
  // round 2 G2: headline = 30-day baseline (range of 7-day means), the 24 h sample is secondary with its date and weekday
  const S30=()=>(((D.opt||{}).v3)||{}).stage_costs_30d||null;
  const smpAge=SC=>{const a=SC&&SC.stamp&&SC.stamp.at;return a?Math.round((Date.now()-Date.parse(a))/864e5):null;};
  const smpTxt=SC=>{const s=(SC&&SC.stamp)||{},g=smpAge(SC);return T(`one 24 h sample to ${s.date||'?'} (${(s.wd||['?'])[0]}${g!=null?`, ${g} d old`:''})`,`một mẫu 24 giờ tới ${s.date||'?'} (${(s.wd||['?','?'])[1]}${g!=null?`, cũ ${g} ngày`:''})`);};
  const range30=c=>c?`${fmt(c.lo)}–${fmt(c.hi)}`:'';
  function hwActs(hw,st){return (((D.opt||{}).v3)||{}).actions.filter(a=>a.cell&&a.cell[0]===st&&(a.cell[1]===hw||a.cell[1]==='-'));}
  function rOptHW(hw){const I=HWI[hw],V=((D.opt||{}).v3)||{},SC=V.stage_costs,n=I.n;
    // A: goals + cost per stage
    const sA=sec(I.p+'-sum');if(sA){sA.replaceChildren(head(n+'A',L(I.name),L(I.name),
        hw==='CPU'?'CPU runner job-min per PR stage, the proposed changes for each stage, and what each applied change saved.':'Buildkite job-min (GPU and accelerator agents) per PR stage, the proposed changes for each stage, and what each applied change saved.',
        hw==='CPU'?'Phút job runner CPU theo từng giai đoạn PR, thay đổi đề xuất cho mỗi giai đoạn, và mỗi thay đổi đã áp dụng tiết kiệm được bao nhiêu.':'Phút job Buildkite (agent GPU và accelerator) theo từng giai đoạn PR, thay đổi đề xuất cho mỗi giai đoạn, và mỗi thay đổi đã áp dụng tiết kiệm được bao nhiêu.'),goalBox());
      if(SC){const tot=STG3.reduce((x,[st])=>x+((SC.cells[`${st}|${hw}`]||{}).total||0),0),M=S30();
        sA.append(el('div',{class:'ops-flow'},STG3.map(([st,nm])=>{const c=SC.cells[`${st}|${hw}`]||{},c30=M&&M.cells[`${st}|${hw}`],k=hwActs(hw,st).length,pc=x=>c.total?Math.round(100*x/c.total):0;
          return el('div',{class:'ops-fstep'+(c.total||c30?' hit':'')},el('div',{class:'t'},L(nm)),el('div',{class:'v'},c30?range30(c30):c.total?fmt(c.total):'—'),
            c30&&c30.scope?el('div',{class:'meta'},L(c30.scope)):null,
            el('div',{class:'meta'},c30?T(`job-min/day · lowest–highest 7-day mean, 30 d · mean ${fmt(c30.mean)}`,`phút job/ngày · trung bình 7 ngày thấp nhất–cao nhất, 30 ngày · trung bình ${fmt(c30.mean)}`):c.total?L(I.unit)+' · '+T('no 30-day data: sample only','không có dữ liệu 30 ngày: chỉ có mẫu'):T('no separate run','không có lần chạy riêng')),
            c.total?el('div',{class:'meta'},T('Secondary: ','Phụ: ')+smpTxt(SC)+`: ${fmt(c.total)} · `+(tot?T(`${Math.round(100*c.total/tot)}% of the ${hw} sample`,`${Math.round(100*c.total/tot)}% mẫu ${hw}`):'')+' · '+T(`${pc(c.cancelled)}% cancelled · ${pc(c.failed)}% failed`,`${pc(c.cancelled)}% bị huỷ · ${pc(c.failed)}% fail`)):null,
            el('div',{class:'meta'},el('b',{},String(k)),T(k===1?' proposal':' proposals',' đề xuất')));}).flatMap((x,i)=>i?[el('span',{class:'ops-farr'},'→'),x]:[x])));
        const w=M?M.window:['?','?'];
        sA.append(el('p',{class:'ops-src'},T(`Headline: job-min per day from the 30-day baseline ${w[0]} → ${w[1]} (${(S30()||{}).src||'P1'} CSVs), shown as the lowest–highest 7-day mean. Secondary: ${smpTxt(SC)}, window ${SC.span_h} h, scaled to 24 h. ${hw==='GPU'?'30-day GPU cells cover the k3 pipelines only (accelerator suites are in the sample only). GPUs per job are not applied: job-min, not GPU-min.':'Post-merge GitHub Actions runs are not in the 30-day files: that cell is the sample only.'}`,
          `Số chính: phút job mỗi ngày từ baseline 30 ngày ${w[0]} → ${w[1]} (CSV ${(S30()||{}).src||'P1'}), ghi dạng trung bình 7 ngày thấp nhất–cao nhất. Số phụ: ${smpTxt(SC)}, khung ${SC.span_h} giờ, quy về 24 giờ. ${hw==='GPU'?'Ô GPU 30 ngày chỉ gồm pipeline k3 (bộ accelerator chỉ có trong mẫu). Chưa nhân số GPU mỗi job: đây là phút job, không phải GPU-phút.':'File 30 ngày không có lần chạy GitHub Actions sau merge: ô đó chỉ có mẫu.'}`)));}}
    // B: per stage: what runs, where the time goes, the agent's solutions with Apply
    const sB=sec(I.p+'-stages');if(sB){sB.replaceChildren(head(n+'B','Proposed changes by PR stage','Thay đổi đề xuất theo giai đoạn PR','For each stage: what runs, where the job-min go, and the proposed CI changes with evidence and rationale. Mark a change as applied to start tracking it.','Mỗi giai đoạn: chạy gì, phút job đi đâu, và thay đổi CI đề xuất kèm bằng chứng và lý do. Đánh dấu đã áp dụng để bắt đầu theo dõi.'));
      const M=S30();
      sB.append(el('p',{class:'ops-src'},T(`Data age: open-PR counts ("now") from the snapshot of ${String(D.snap_at||'?').slice(0,16).replace('T',' ')} UTC; 30-day figures ${M?M.window.join(' → '):'—'}; per-workflow minutes and "frees" figures without a 30-day range: ${smpTxt(SC)}.`,
        `Tuổi dữ liệu: số PR đang mở ("hiện tại") từ snapshot lúc ${String(D.snap_at||'?').slice(0,16).replace('T',' ')} UTC; số 30 ngày ${M?M.window.join(' → '):'—'}; số phút theo workflow và số "giải phóng" không có khoảng 30 ngày: ${smpTxt(SC)}.`)));
      STG3.forEach(([st,nm])=>{const c=(SC&&SC.cells[`${st}|${hw}`])||{},c30=M&&M.cells[`${st}|${hw}`],A=hwActs(hw,st);
        sB.append(el('h3',{style:'margin-top:14px;border-left:3px solid var(--series-1);padding-left:8px'},L(nm),c30?el('span',{class:'meta'},` · ${range30(c30)} ${L(I.unit)} (30 d)`+(c.total?T(` · sample ${fmt(c.total)}`,` · mẫu ${fmt(c.total)}`):'')):c.total?el('span',{class:'meta'},` · ${fmt(c.total)} ${L(I.unit)} `+T('(sample)','(mẫu)')):null),
          el('p',{class:'obs-note'},L(STGWHAT[hw][st]),(c.top||[]).length?el('span',{},T(' · largest in the sample: ',' · lớn nhất trong mẫu: '),el('span',{class:'obsraw'},c.top.map(x=>`${x[0]} ${fmt(x[1])}`).join(' · '))):''));
        if(!A.length){sB.append(el('div',{class:'ops-empty'},T('No proposed change for this stage yet.','Chưa có thay đổi đề xuất cho giai đoạn này.')));return;}
        sB.append(table([[T('Proposed change','Thay đổi đề xuất')],[T('Evidence · rationale','Bằng chứng · lý do')],[T('Expected gain · tracking','Lợi ích dự kiến · theo dõi')]],A.map(a_=>el('tr',{id:actAnchor(hw+'-'+a_.id)},
          el('td',{},el('div',{class:'ttl'},L(a_.title)),el('div',{},el('span',{class:'ops-kind',style:`border-color:${GCOL[a_.goal]}`},T(`Goal ${a_.goal}`,`Mục tiêu ${a_.goal}`)),a_.cell[1]==='-'?el('span',{class:'meta'},T(' · PR flow (CPU and GPU)',' · luồng PR (CPU và GPU)')):null),
            el('div',{style:'margin-top:4px'},el('span',{class:'gch '+(a_.lvl==='bad'?'s-fail':a_.lvl==='warn'?'s-run':'s-none')},a_.lvl==='bad'?T('priority: high','ưu tiên: cao'):a_.lvl==='warn'?T('priority: medium','ưu tiên: vừa'):T('priority: low','ưu tiên: thấp')))),
          el('td',{},el('div',{class:'meta'},L(a_.evidence)),el('div',{class:'ops-why'},el('b',{},T('Rationale: ','Lý do: ')),L(a_.why)),a_.guard?el('div',{class:'ops-why',style:'color:var(--text-secondary);border-left:2px solid var(--series-2);padding-left:6px'},L(a_.guard)):null),
          el('td',{},a_.benefit?el('b',{},L(a_.benefit)):'—',el('div',{style:'margin-top:6px'},applyBox(a_)))))));});}
    // C: did it work (this hardware only)
    const sC=sec(I.p+'-res');if(sC){const A=(V.actions||[]).filter(a_=>a_.solution&&a_.solution.applied&&a_.cell&&(a_.cell[1]===hw||a_.cell[1]==='-'));
      sC.replaceChildren(head(n+'C','Before / after','Trước / sau','Each applied change: its tracked metric before → after.','Mỗi thay đổi đã áp dụng: metric theo dõi trước → sau.'));
      sC.classList.toggle('ux-gone',!A.length);   // round 3 (C_ia P6): an empty "before / after" has no own section
      if(!A.length)sC.append(el('div',{class:'ops-empty'},T('No change applied yet on this side. Use "Mark as applied" above, then run the command it shows.','Chưa áp dụng thay đổi nào ở phần này. Bấm "Đánh dấu đã áp dụng" ở trên, rồi chạy lệnh nó hiện ra.')));
      else sC.append(table([[T('Solution','Giải pháp')],[T('Stage','Giai đoạn')],[T('Applied','Áp dụng')],[T('Metric','Metric')],[T('Before','Trước'),'r'],[T('After','Sau'),'r'],[T('Change','Thay đổi'),'r']],A.map(a_=>{const r=a_.result||{};
        return el('tr',{},el('td',{},L(a_.title)),el('td',{},L((STG3.find(x=>x[0]===a_.cell[0])||[0,['','']])[1])),el('td',{},a_.solution.applied),el('td',{},L(r.metric)),el('td',{class:'r'},`${fmt(r.before)} ${U(r.unit)}`),
          el('td',{class:'r'},r.after!=null?`${fmt(r.after)} ${U(r.unit)}`:T('waiting for data','chờ dữ liệu')),el('td',{class:'r'},r.change_pct!=null?`${r.change_pct>0?'+':''}${r.change_pct}%`:'—'));})));}
    // D: details (folded)
    const sD=sec(I.p+'-more');if(sD){const P=V.public||{rows:[]},n10=P.nightly10||{},O=D.opt||{};
      sD.replaceChildren(head(n+'D','Details','Chi tiết'));
      if(hw==='CPU')sD.append(el('details',{},el('summary',{},T('Public CI: publish.yml and nightly','CI public: publish.yml và nightly')),
          el('ul',{class:'ops-why'},(P.triggers||[]).map(t=>el('li',{},L(t))),el('li',{},T(`nightly: ${n10.ok||0} passed, ${n10.fail||0} failed of the last ${n10.n||0} runs.`,`nightly: ${n10.ok||0} pass, ${n10.fail||0} fail trong ${n10.n||0} lần chạy gần nhất.`))),
          table([['Workflow'],[T('Runs / 24 h','Lần chạy / 24 giờ'),'r'],[T('cancelled','bị huỷ'),'r'],[T('failed','fail'),'r'],[T('job-min / day','phút job / ngày'),'r'],[T('of which cancelled','trong đó bị huỷ'),'r']],
            P.rows.map(r=>el('tr',{},el('td',{},el('span',{class:'obsraw'},r.name)),el('td',{class:'r'},r.runs),el('td',{class:'r'},r.cancelled),el('td',{class:'r'},r.failed),el('td',{class:'r'},fmt(r.minutes)),el('td',{class:'r'},fmt(r.cancelled_min)))))),
        el('details',{},el('summary',{},T('Every workflow and pipeline (job-min)','Mọi workflow và pipeline (phút job)')),el('div',{id:'optPub'})));
      else{const sg=Object.fromEntries(((D.prs||{}).stages||[]).map(g=>[g.id,g])),SM=O.sample||{};
        sD.append(el('details',{},el('summary',{},T('All 30-day baseline cards','Mọi thẻ baseline 30 ngày')),el('div',{id:'optBase'})),
          el('details',{},el('summary',{},T('Where open PRs are now','PR đang mở nằm ở đâu')),el('p',{class:'obs-note'},T(`Sample: ${SM.n} non-draft dev PRs among the 100 most recently updated (of about ${fmt(SM.total)} open).`,`Mẫu: ${SM.n} PR dev không nháp trong 100 PR cập nhật gần nhất (trên khoảng ${fmt(SM.total)} PR mở).`)),
            el('div',{class:'ops-funnel',id:'optFlow3'},[['ci','1 · Create PR + CI','1 · Tạo PR + CI'],['review','2 · Human review','2 · Người review'],['merge','3 · Merge PR','3 · Merge PR'],['stale','Blocked / stale','Bị chặn / cũ']].map(([id,en,vi])=>{const g=sg[id]||{subs:{}};
              return el('div',{class:'ops-stage'},el('div',{class:'t'},T(en,vi)),el('div',{class:'v'},fmt(g.n)),el('div',{class:'s'},Object.entries(g.subs).filter(([,v])=>v).map(([k_,v])=>el('span',{},`${L(SUB[k_])}: ${v}`))));}))),
          el('details',{},el('summary',{},T('Goal 2 · roadmap features and their tests','Mục tiêu 2 · feature trong roadmap và test của chúng')),
            (V.features||[]).length?table([[T('Feature (roadmap)','Feature (roadmap)')],['PR'],[T('Test in PR?','Có test trong PR?')]],V.features.map(f=>el('tr',{},el('td',{},el('span',{class:'obsraw'},f.text)),el('td',{},f.prs.map(n_=>a(GH+n_,'#'+n_+' '))),el('td',{},el('span',{class:'gch '+(f.covered?'s-ok':'s-fail')},f.covered?T('yes','có'):T('no','không')))))):el('div',{class:'ops-empty'},T('No roadmap file found.','Không thấy file roadmap.'))));}
      sD.append(el('details',{},el('summary',{},T('Words used on this tab','Thuật ngữ trên tab này')),el('ul',{class:'ops-why'},
        [['k3','the Buildkite GPU cluster that runs the required GPU checks','cụm GPU Buildkite chạy các check GPU bắt buộc'],['k3-multiprocess-test (MP)','required end-to-end GPU tests; on PRs it starts only after a maintainer adds the label "full"','test GPU end-to-end bắt buộc; ở PR chỉ chạy sau khi maintainer gắn nhãn "full"'],
         ['job-min','wall-clock minutes one CI job runs, on a GitHub runner or a Buildkite agent (one job = one machine). Not GPU-min: GPUs per job are not in the 24 h data','số phút một job CI chạy, trên runner GitHub hoặc agent Buildkite (một job = một máy). Không phải GPU-phút: dữ liệu 24 giờ không có số GPU mỗi job'],['p50 / p90','half / 9 in 10 of the values are at or below this number','một nửa / 9 trên 10 giá trị bằng hoặc dưới số này'],
         ['superseded run','a run cancelled because a newer push started the same workflow','lần chạy bị huỷ vì một push mới hơn chạy lại cùng workflow']].map(([k_,en,vi])=>el('li',{},el('b',{},k_),': ',T(en,vi))))),
        el('details',{},el('summary',{},T('How marking and tracking work','Đánh dấu và theo dõi hoạt động thế nào')),el('p',{class:'ops-why'},T('"Mark as applied" marks the date in this browser and shows one command. Running it writes the change to ','"Đánh dấu đã áp dụng" ghi ngày trong trình duyệt này và hiện một lệnh. Chạy lệnh đó sẽ ghi thay đổi vào '),el('code',{},O.sol_file||'optimal_solutions.json'),
          T(' with today’s value as the baseline. Keep the collectors running daily; each build then shows before → after.',' với giá trị hôm nay làm baseline. Tiếp tục chạy collector mỗi ngày; mỗi lần build sẽ hiện trước → sau.'))));}}

  function rOptAct3(){const s=sec('opt-act3');if(!s)return;const A=(((D.opt||{}).v3)||{}).actions||[];
    s.replaceChildren(head('4C','What to do next','Việc cần làm tiếp','Proposed changes, most important first. Each says which goal it serves, where it acts, the evidence and why it fits.','Giải pháp do agent tìm, quan trọng nhất trước. Mỗi giải pháp ghi rõ phục vụ mục tiêu nào, tác động ở đâu, bằng chứng và vì sao phù hợp.'));
    const row=a=>el('tr',{id:actAnchor(a.id)},
      el('td',{},el('div',{class:'ttl'},L(a.title)),el('div',{},el('span',{class:'ops-kind',style:`border-color:${GCOL[a.goal]}`},T(`Goal ${a.goal}`,`Mục tiêu ${a.goal}`)),
        el('span',{class:'meta'},` ${a.cell?L(CELLN[a.cell[0]])+' · '+(a.cell[1]==='-'?T('PR flow','luồng PR'):a.cell[1]):''}`))),
      el('td',{},el('div',{class:'meta'},L(a.evidence)),el('div',{class:'ops-why'},el('b',{},T('Rationale: ','Lý do: ')),L(a.why)),a.guard?el('div',{class:'ops-why',style:'color:var(--text-secondary);border-left:2px solid var(--series-2);padding-left:6px'},L(a.guard)):null),
      el('td',{},a.benefit?el('b',{},L(a.benefit)):'—',el('div',{style:'margin-top:4px'},el('span',{class:'gch '+(a.lvl==='bad'?'s-fail':a.lvl==='warn'?'s-run':'s-none')},a.lvl==='bad'?T('do first','làm trước'):a.lvl==='warn'?T('worth doing','nên làm'):T('later','để sau'))),
        el('div',{style:'margin-top:6px'},applyBox(a))));
    const cols=[[T('Solution','Giải pháp')],[T('Evidence · rationale','Bằng chứng · lý do')],[T('Expected gain · status','Lợi ích dự kiến · trạng thái')]];
    const GN={1:['Goal 1 · More PRs merged','Mục tiêu 1 · Merge được nhiều PR hơn'],2:['Goal 2 · CI keeps covering features','Mục tiêu 2 · CI vẫn bao phủ feature']};
    [1,2].forEach(g=>{const G_=A.filter(x=>x.goal===g);if(!G_.length)return;
      s.append(el('h3',{style:`margin-top:12px;border-left:3px solid ${GCOL[g]};padding-left:8px`},L(GN[g]),` (${G_.length})`),table(cols,G_.slice(0,5).map(row)));
      if(G_.length>5)s.append(el('details',{style:'margin-top:6px'},el('summary',{},T(`${G_.length-5} more for this goal`,`Thêm ${G_.length-5} giải pháp cho mục tiêu này`)),table(cols,G_.slice(5).map(row))));});
    s.append(el('p',{class:'ops-src'},T('Ranked inside each goal: "do first" before "worth doing", then by benefit. Benefits in different units are not compared.','Xếp hạng trong từng mục tiêu: "làm trước" rồi "nên làm", sau đó theo lợi ích. Lợi ích khác đơn vị không so với nhau.')));}

  function rOptRes3(){const s=sec('opt-res3');if(!s)return;const O=D.opt||{},A=((O.v3||{}).actions||[]).filter(a=>a.solution&&a.solution.applied);
    s.replaceChildren(head('4D','Did it work?','Đã cải thiện chưa?','Each applied solution: its metric before → after.','Mỗi giải pháp đã áp dụng: metric trước → sau.'));
    s.classList.toggle('ux-gone',!A.length);   // round 3 (C_ia P6)
    if(!A.length){s.append(el('div',{class:'ops-empty'},T('No solution applied yet. When one is applied, add it to ','Chưa áp dụng giải pháp nào. Khi áp dụng, thêm vào '),el('code',{},O.sol_file||'optimal_solutions.json'),T(' and its before → after appears here.',' và kết quả trước → sau sẽ hiện ở đây.')));return;}
    s.append(table([[T('Solution','Giải pháp')],[T('Applied','Áp dụng')],[T('Metric','Metric')],[T('Before','Trước'),'r'],[T('After','Sau'),'r'],[T('Change','Thay đổi'),'r']],A.map(a=>{const r=a.result||{};
      return el('tr',{},el('td',{},L(a.title)),el('td',{},a.solution.applied,a.solution.ref?el('div',{class:'meta obsraw'},a.solution.ref):null),el('td',{},L(r.metric)),el('td',{class:'r'},`${fmt(r.before)} ${r.unit||''}`),
        el('td',{class:'r'},r.after!=null?`${fmt(r.after)} ${r.unit||''}`:T('waiting for data','chờ dữ liệu')),el('td',{class:'r'},r.change_pct!=null?`${r.change_pct>0?'+':''}${r.change_pct}%`:'—'));})));}

  function rOptMore3(){const s=sec('opt-more3');if(!s)return;const O=D.opt||{},V=O.v3||{},P=V.public||{rows:[]},ids=(V.actions||[]).map(a=>a.id);
    s.replaceChildren(head('4E','Details','Chi tiết'));
    const n10=P.nightly10||{};
    s.append(el('details',{},el('summary',{},T('B · Public CI: publish.yml and nightly','B · CI public: publish.yml và nightly')),
        el('ul',{class:'ops-why'},(P.triggers||[]).map(t=>el('li',{},L(t))),el('li',{},T(`nightly: ${n10.ok||0} passed, ${n10.fail||0} failed of the last ${n10.n||0} runs.`,`nightly: ${n10.ok||0} pass, ${n10.fail||0} fail trong ${n10.n||0} lần chạy gần nhất.`))),
        table([['Workflow'],[T('Runs / 24 h','Lần chạy / 24 giờ'),'r'],[T('cancelled','bị huỷ'),'r'],[T('failed','fail'),'r'],[T('job-min / day','phút job / ngày'),'r'],[T('of which cancelled','trong đó bị huỷ'),'r']],
          P.rows.map(r=>el('tr',{},el('td',{},el('span',{class:'obsraw'},r.name)),el('td',{class:'r'},r.runs),el('td',{class:'r'},r.cancelled),el('td',{class:'r'},r.failed),el('td',{class:'r'},fmt(r.minutes)),el('td',{class:'r'},fmt(r.cancelled_min)))))),
      el('details',{},el('summary',{},T('A · PR flow: where open PRs are now','A · Luồng PR: PR đang mở nằm ở đâu')),el('div',{id:'optFlow3'}),el('div',{id:'optPRs'})),
      el('details',{},el('summary',{},T('Goal 2 · roadmap features and their tests','Mục tiêu 2 · feature trong roadmap và test của chúng')),
        (V.features||[]).length?table([[T('Feature (roadmap)','Feature (roadmap)')],['PR'],[T('Test in PR?','Có test trong PR?')]],V.features.map(f=>el('tr',{},el('td',{},el('span',{class:'obsraw'},f.text)),el('td',{},f.prs.map(n=>a(GH+n,'#'+n+' '))),el('td',{},el('span',{class:'gch '+(f.covered?'s-ok':'s-fail')},f.covered?T('yes','có'):T('no','không')))))):el('div',{class:'ops-empty'},T('No roadmap file found.','Không thấy file roadmap.'))),
      el('details',{},el('summary',{},T('All 30-day baseline cards','Mọi thẻ baseline 30 ngày')),el('div',{id:'optBase'})),
      el('details',{},el('summary',{},T('Every workflow and pipeline (job-min)','Mọi workflow và pipeline (phút job)')),el('div',{id:'optPub'})),
      el('details',{},el('summary',{},T('Words used on this tab','Thuật ngữ trên tab này')),el('ul',{class:'ops-why'},
        [['k3','the Buildkite GPU cluster that runs the required GPU checks','cụm GPU Buildkite chạy các check GPU bắt buộc'],['k3-unit-tests','required GPU unit tests on 1 GPU pod','unit test GPU bắt buộc trên 1 GPU pod'],
         ['k3-multiprocess-test (MP)','required end-to-end GPU tests; on PRs it starts only after a maintainer adds the label "full"','test GPU end-to-end bắt buộc; ở PR chỉ chạy sau khi maintainer gắn nhãn "full"'],
         ['job-min','minutes one CI job runs (GitHub runner or Buildkite agent)','số phút một job CI chạy (runner GitHub hoặc agent Buildkite)'],['p50 / p90','half / 9 in 10 of the values are at or below this number','một nửa / 9 trên 10 giá trị bằng hoặc dưới số này'],
         ['superseded run','a run cancelled because a newer push started the same workflow','lần chạy bị huỷ vì một push mới hơn chạy lại cùng workflow'],['DCO','the sign-off check every commit needs','check chữ ký (sign-off) mà mọi commit cần']].map(([k_,en,vi])=>el('li',{},el('b',{},k_),': ',T(en,vi))))),
      el('details',{},el('summary',{},T('How to register an applied solution','Cách đăng ký giải pháp đã áp dụng')),el('p',{class:'ops-why'},T('Add an entry to ','Thêm một mục vào '),el('code',{},O.sol_file||'optimal_solutions.json'),T(', then keep running the daily collectors. Before = mean of up to 14 days before "applied"; after = mean of the days after.',', rồi tiếp tục chạy collector mỗi ngày. Trước = trung bình tối đa 14 ngày trước "applied"; sau = trung bình các ngày sau.')),
        el('pre',{},'[{"id": "sup-Build and Publish to PyPI", "applied": "2026-11-12", "ref": "PR #6520"}]'),el('p',{class:'meta'},T('Ids: ','Id: '),el('span',{class:'obsraw'},ids.join(' · ')))));
    // PR flow boxes inside the fold
    const fl=document.getElementById('optFlow3'),sg=Object.fromEntries(((D.prs||{}).stages||[]).map(g=>[g.id,g])),SM=O.sample||{};
    if(fl){fl.append(el('p',{class:'obs-note'},T(`Sample: ${SM.n} non-draft dev PRs among the 100 most recently updated (of about ${fmt(SM.total)} open).`,`Mẫu: ${SM.n} PR dev không nháp trong 100 PR cập nhật gần nhất (trên khoảng ${fmt(SM.total)} PR mở).`)),
      el('div',{class:'ops-funnel'},[['ci','1 · Create PR + CI','1 · Tạo PR + CI'],['review','2 · Human review','2 · Người review'],['merge','3 · Merge PR','3 · Merge PR'],['stale','Blocked / stale','Bị chặn / cũ']].map(([id,en,vi])=>{const g=sg[id]||{subs:{}};
        return el('div',{class:'ops-stage'},el('div',{class:'t'},T(en,vi)),el('div',{class:'v'},fmt(g.n)),el('div',{class:'s'},Object.entries(g.subs).filter(([,v])=>v).map(([k_,v])=>el('span',{},`${L(SUB[k_])}: ${v}`))));})));}}

  function rPub(){const s=document.getElementById('optPub');if(!s)return;const C=(D.opt||{}).cost;s.replaceChildren();if(!C)return;
    const mx=Math.max(1,...C.rows.map(r=>r.total)),HW={CPU:'var(--series-3)',GPU:'var(--series-1)',Accel:'var(--series-2)',Other:'var(--text-muted)'};
    s.append(el('p',{class:'obs-note'},T(`Raw job-min in the window (${C.span_h} h), not scaled. GitHub CPU by runner: `,`Phút job thô trong khung (${C.span_h} giờ), chưa quy đổi. CPU GitHub theo runner: `),el('span',{class:'obsraw'},Object.entries(C.os).map(([a,b])=>`${a} ${fmt(b)}`).join(' · '))));
    s.append(table([[T('Workflow / pipeline','Workflow / pipeline')],['HW'],[T('Runs','Lần chạy'),'r'],['PR','r'],['push','r'],[T('job-min','phút job')],[T('cancelled','bị huỷ'),'r'],[T('failed','fail'),'r'],[T('re-run','chạy lại'),'r']],
      C.rows.slice(0,40).map(r=>el('tr',{},el('td',{},el('span',{class:'obsraw'},r.name),el('div',{class:'meta'},r.sys)),el('td',{},r.hw),el('td',{class:'r'},r.runs),el('td',{class:'r'},r.pr),el('td',{class:'r'},r.push),
        el('td',{},el('div',{class:'ops-hb'},el('i',{style:`width:${Math.max(2,120*r.total/mx)}px;background:${HW[r.hw]}`}),el('span',{},fmt(Math.round(r.total))))),el('td',{class:'r'},fmt(Math.round(r.cancelled))),el('td',{class:'r'},fmt(Math.round(r.failed))),el('td',{class:'r'},fmt(Math.round(r.rerun)))))));}

  function rPRs(){const s=document.getElementById('optPRs');if(!s)return;const P=D.prs,SM=(D.opt||{}).sample||{};s.replaceChildren();
    const ST={ci:['1 · Open PR + CI','1 · Mở PR + CI'],review:['2 · Human review (optional)','2 · Người review (tuỳ chọn)'],merge:['3 · Merge PR','3 · Merge PR'],stale:['Blocked / stale','Bị chặn / cũ']};
    s.append(el('p',{class:'obs-note'},T(`Sample: the ${SM.n} non-draft dev PRs among the 100 most recently updated (of about ${fmt(SM.total)} open non-draft PRs). Every required check must be present and green; a missing one counts as "not run".`,`Mẫu: ${SM.n} PR dev không nháp trong 100 PR cập nhật gần nhất (trên khoảng ${fmt(SM.total)} PR mở không nháp). Mọi check bắt buộc phải có và xanh; thiếu check tính là "chưa chạy".`)));
    s.append(el('h3',{},T('Could merge without human approval','Có thể merge không cần người duyệt')),
      P.skip.length?table([['PR'],['CPU'],['GPU']],P.skip.map(p=>el('tr',{},el('td',{},el('div',{class:'ttl'},a(p.url,'#'+p.num),' ',el('span',{class:'obsraw'},p.title))),el('td',{},st(p.cpu)),el('td',{},st(p.gpu))))):el('div',{class:'ops-empty'},T('None right now.','Hiện không có.')),
      el('p',{class:'ops-src'},T('Rule (proposal): docs-only PRs with every required check green may merge without a human approval. Tests-only PRs keep review: they can delete tests or change thresholds.','Luật (đề xuất): PR chỉ đổi docs, mọi check bắt buộc xanh, có thể merge không cần người duyệt. PR chỉ đổi test vẫn cần review: có thể xoá test hoặc đổi ngưỡng.')));}

  // risk level = what the diff shows (short); the action is the verb chip (VB), decided per PR from level + CI status
  const OVL={p0:['P0 · Breaks on rebase','P0 · Vỡ khi rebase','s-fail','var(--critical)'],p1:['P1 · Same function','P1 · Cùng hàm','s-fail','var(--critical)'],
    p2:['P2 · Nearby lines','P2 · Dòng gần nhau','s-run','var(--warning)'],p3:['P3 · Same file','P3 · Cùng file','s-run','var(--warning)'],p4:['P4 · No shared code','P4 · Không chung code','s-ok','var(--good)']};
  const OWN={p0:['PR author','tác giả PR'],p1:['PR author','tác giả PR'],p2:['PR author + reviewer','tác giả PR + reviewer'],p3:['PR author','tác giả PR'],p4:['—','—']};
  const VB={stop:['STOP CI','DỪNG CI','s-fail'],block:['BLOCK MERGE','CHẶN MERGE','s-fail'],hold:['HOLD','GIỮ LẠI','s-run'],rebase:['REBASE FIRST','REBASE TRƯỚC','s-run'],
    keep:['KEEP RUNNING','ĐỂ CHẠY',''],later:['REBASE BEFORE MERGE','REBASE TRƯỚC MERGE',''],go:['PROCEED','TIẾP TỤC','s-ok'],idle:['NO CI','KHÔNG CI','s-none']};
  const vchip=v=>el('span',{class:'gch '+(VB[v]||VB.go)[2]},V()?(VB[v]||VB.go)[1]:(VB[v]||VB.go)[0]);
  const FAM={draft:['Draft','Nháp'],open:['Open','Mở'],progress:['In progress','Đang chạy'],queue:['Queue','Hàng đợi'],blocked:['Blocked','Bị chặn']};
  const PST={draft:['draft','draft','nháp'],wait_review:['open','waiting review','chờ review'],wait_full:['open',"waiting 'full'",'chờ nhãn full'],adapt:['open','changes requested','yêu cầu sửa'],
    ci_missing:['open','required check not run','check bắt buộc chưa chạy'],ci_run:['progress','CI running','CI đang chạy'],ready:['queue','approved','đã duyệt'],
    ci_fail:['blocked','required check red','check bắt buộc đỏ'],conflict:['blocked','merge conflict','xung đột merge'],old:['blocked','stale (30+ d)','cũ (30+ ngày)']};
  const MCI={queued:['queue','Post-merge CI not started','CI sau merge chưa chạy','s-run'],running:['progress','Post-merge CI running','CI sau merge đang chạy','s-run'],
    passed:['done','Post-merge CI passed','CI sau merge pass','s-ok'],failed:['blocked','Post-merge CI failed (new red)','CI sau merge fail (mới đỏ)','s-fail'],
    red_before:['done','Post-merge CI red (already red before)','CI sau merge đỏ (đã đỏ từ trước)','s-run'],
    skipped:['done','Post-merge CI skipped (superseded)','CI sau merge bị bỏ qua (bị thay thế)','s-run']};
  const pst=sub=>{const x=PST[sub]||['open',sub,sub];return `${L(FAM[x[0]])} · ${V()?x[2]:x[1]}`;};
  function rOverlap(){const s=sec('overlap');if(!s)return;const O=D.overlap,G_=O.groups||[],C=O.gcount||{},ST=O.status||{},VC=C.verbs||{};
    s.replaceChildren(head('6A','Rebase risk: open PRs vs merges of the last 24 h','Rủi ro rebase: PR đang mở so với các merge trong 24 giờ qua',
      'Last 24 h of merges vs open PRs. Click a PR for its map.',
      'Merge 24 giờ qua so với PR đang mở. Bấm PR để xem map.'));
    // ===== reviewer view (top): decide merge / review / rebase, and cancel CI that tests stale code
    const RV=O.review||{queue:[],running:[],by_merged:[],verbs:{}},RVB={merge:['MERGE','MERGE','s-ok'],full:["ADD 'full'","GẮN 'full'",'s-ok'],review:['REVIEW','REVIEW',''],
      rebase:['REBASE FIRST','REBASE TRƯỚC','s-run'],red:['WAIT FIX','CHỜ SỬA','s-run'],dco:['FIX DCO','SỬA DCO','s-fail'],author:['WAIT AUTHOR','CHỜ TÁC GIẢ','s-none'],
      cancel:['CANCEL CI','HUỶ CI','s-fail'],keep:['KEEP RUNNING','ĐỂ CHẠY','']};
    const DV=(D.dec||{}).verbs||{},DR=(D.dec||{}).rules||{};
    const rchip=v=>DV[v]?el('span',{class:'tdy-v t-'+DV[v][2],tabindex:'0','data-rule':T('Rule · ','Luật · ')+L(DR[v]||['',''])},V()?DV[v][1]:DV[v][0]):el('span',{class:'gch '+(RVB[v]||RVB.review)[2]},V()?(RVB[v]||RVB.review)[1]:(RVB[v]||RVB.review)[0]);
    const LVDEF={p0:['P0 · Breaks on rebase: the merge removed or renamed a symbol this PR still uses. It will not import or run after rebase.','P0 · Vỡ khi rebase: merge đã xoá hoặc đổi tên symbol mà PR này vẫn dùng. Sau rebase sẽ không import / chạy được.'],
      p1:['P1 · Same function: both PRs edit the same function or class. This PR\'s green CI says nothing about the code on dev now.','P1 · Cùng hàm: hai PR sửa cùng hàm hoặc class. CI xanh của PR này không còn nói gì về code đang có trên dev.'],
      p2:['P2 · Nearby lines: edits a few lines apart in the same file. Git may merge them, but the logic can clash.','P2 · Dòng gần nhau: hai chỗ sửa cách vài dòng trong cùng file. Git có thể tự merge, nhưng logic có thể đụng nhau.'],
      p3:['P3 · Same file, different code: low risk; this PR was tested without the merge.','P3 · Cùng file, khác đoạn: rủi ro thấp; PR này được test khi chưa có merge.'],
      p4:['P4 · No shared code.','P4 · Không chung code.']};
    const lvchip=lv=>el('span',{class:'gch rv-lv '+OVL[lv][2],'data-tip':L(LVDEF[lv]),tabindex:'0'},lv.toUpperCase());
    {const tp0=document.createElement('div');tp0.className='rv-tip';tp0.setAttribute('role','tooltip');s.append(tp0);}
    if(!window.__rvTip){window.__rvTip=1;const tpq=()=>document.querySelector('section[data-ops="overlap"] .rv-tip');
      const show=e=>{const tp=tpq();if(!tp)return;const t=e.target.closest&&e.target.closest('[data-tip]');if(!t){tp.style.display='none';return;}tp.textContent=t.getAttribute('data-tip');tp.style.display='block';
        const r=t.getBoundingClientRect();let x=r.left,y=r.bottom+6;if(x+tp.offsetWidth>innerWidth-8)x=innerWidth-8-tp.offsetWidth;if(y+tp.offsetHeight>innerHeight-8)y=r.top-6-tp.offsetHeight;tp.style.left=Math.max(8,x)+'px';tp.style.top=y+'px';};
      document.addEventListener('pointerover',show);document.addEventListener('focusin',show);document.addEventListener('scroll',()=>{const tp=tpq();if(tp)tp.style.display='none';},true);}
    const TAC={'MERGE OK':'s-ok','REBASE BEFORE MERGE':'','REBASE + RE-RUN':'s-run','BLOCK':'s-fail','CANCEL CI':'s-fail','KEEP RUNNING':''};
    const TAV={'MERGE OK':'MERGE ĐƯỢC','REBASE BEFORE MERGE':'REBASE TRƯỚC MERGE','REBASE + RE-RUN':'REBASE + CHẠY LẠI','BLOCK':'CHẶN','CANCEL CI':'HUỶ CI','KEEP RUNNING':'ĐỂ CHẠY'};
    const tachip=d=>d?el('span',{class:'gch rv-ta '+(TAC[d]??'')},'✦ ',V()?(TAV[d]||d):d):null;
    const TA=RV.agent;
    const GL={dco:'DCO',quality:T('Quality','Quality'),unit:'Unit',mp:'MP'},GS={ok:['✓','s-ok',T('passed','pass')],run:['…','s-run',T('running','đang chạy')],fail:['✗','s-fail',T('failed','fail')],
      cancel:['✗','s-fail',T('cancelled','bị huỷ')],missing:['–','s-none',T('not run','chưa chạy')],label:["'full'",'s-none',T("waiting for 'full'","chờ nhãn 'full'")]};
    const gates=g=>el('span',{class:'rv-gates'},['dco','quality','unit','mp'].map(k=>{const x=GS[g[k]]||GS.missing;return el('span',{class:'gch '+x[1],title:`${GL[k]}: ${x[2]}`},`${GL[k]} ${x[0]}`);}));
    const prRef=(x,m)=>{const t=TA&&TA.items?TA.items[`${m}-${x.num}`]:null;return el('span',{class:'rv-ref','data-tip':t?`${T('Trace Agent','Trace Agent')}: ${t.d} (${t.c||'?'}) — ${L(t.r)}`:null},a(`${GH_}/pull/${x.num}`,'#'+x.num),' ',lvchip(x.level),' ',rchip(x.verb),t?tachip(t.d):null);};
    const GH_='https://github.com/LMCache/LMCache';
    const ago=t=>{if(!t)return '';const m=Math.round((Date.parse(O.snap_at||O.at)-Date.parse(t))/60000);return m<60?`${m} min`:`${Math.round(m/6)/10} h`;};
    // decision strip
    const VV=RV.verbs||{},nq=RV.queue.length,nr=RV.running.length;
    s.append(el('div',{class:'rv-strip'},
      el('div',{class:'rv-box'},el('div',{class:'l'},T(`Ready for review · ${nq} PRs`,`Chờ review · ${nq} PR`)),el('div',{class:'rv-chips'},['merge','full','review','rebase','red','dco','author'].filter(v=>VV[v]).map(v=>el('span',{},rchip(v),' ',el('b',{},String(VV[v])))))),
      el('div',{class:'rv-box'+(VV.cancel?' warn':'')},el('div',{class:'l'},T(`CI running now · ${nr} PRs`,`CI đang chạy · ${nr} PR`)),el('div',{class:'rv-chips'},['cancel','keep'].filter(v=>VV[v]).map(v=>el('span',{},rchip(v),' ',el('b',{},String(VV[v]))))),
        RV.save?el('div',{class:'meta'},T(`Cancelling saves ≈${fmt(RV.save)} GPU-min (median GPU-min of one build, 30-day baseline).`,`Huỷ tiết kiệm ≈${fmt(RV.save)} GPU-phút (trung vị GPU-phút một build, baseline 30 ngày).`)):null),
      el('div',{class:'rv-box'},el('div',{class:'l'},T(`Merged in 24 h · ${O.merged.length}`,`Merge trong 24 giờ · ${O.merged.length}`)),el('div',{class:'meta'},T(`${RV.by_merged.filter(m=>m.ready.length+m.running.length).length} touch code of an open PR. ${RV.n_inactive} open PRs have a conflict or are stale (not listed).`,`${RV.by_merged.filter(m=>m.ready.length+m.running.length).length} đụng code của PR đang mở. ${RV.n_inactive} PR đang xung đột hoặc cũ (không liệt kê).`)))));
    // A · merged PRs -> open PRs
    const BM=RV.by_merged.filter(m=>m.ready.length+m.running.length);
    const lvLegend=el('div',{class:'rv-leg'},T('Level (hover for the meaning): ','Mức (rê chuột để xem nghĩa): '),['p0','p1','p2','p3'].map(lv=>el('span',{},lvchip(lv),' ',L(LVDEF[lv]).split(':')[0].replace(/^P\d · /,''))),
      el('span',{class:'meta'},T('Rule chip = diff rule; ✦ chip = Trace Agent (read both diffs).','Chip luật = luật diff; chip ✦ = Trace Agent (đã đọc cả hai diff).')));
    const taNote=!TA?el('div',{class:'rv-tanote'},T('Trace Agent has not reviewed these merges yet. Run (paid, read-only, ~10–20 min): ','Trace Agent chưa xem các merge này. Chạy (tốn phí, chỉ đọc, ~10–20 phút): '),el('code',{class:'obsraw'},'python -I -X utf8 LM-762-ci-resource/plan-2026-11/outputs/cpu_tests/trace_agent_dirs.py --dir rebase')):
      el('div',{class:'rv-tanote'+(TA.status!=='ok'?' warn':'')},TA.status==='ok'?T(`✦ Trace Agent ${day(TA.run_at)} · ${TA.covered}/${TA.pairs} pairs reviewed${TA.snap_at!==O.snap_at?' · from an older snapshot: re-run for the current merges':''}. `,`✦ Trace Agent ${day(TA.run_at)} · đã xem ${TA.covered}/${TA.pairs} cặp${TA.snap_at!==O.snap_at?' · từ snapshot cũ hơn: chạy lại cho các merge hiện tại':''}. `):T('Trace Agent run failed: ','Trace Agent chạy lỗi: ')+(TA.error||'').slice(0,160),TA.summary?el('span',{class:'meta'},L(TA.summary)):null);
    s.append(el('h3',{},T('A · Each merge vs open PRs','A · Từng merge so với PR đang mở')),lvLegend,taNote,el('p',{class:'meta'},T('Which open PRs a merge of the last 24 h touched: ready for review (left) and CI running (right). Level = how close the code is (P1 same function … P3 same file).','Merge nào trong 24 giờ đụng PR đang mở nào: chờ review (trái) và CI đang chạy (phải). Mức = code gần nhau tới đâu (P1 cùng hàm … P3 cùng file).')));
    s.append(BM.length?table([[T('Merged PR · post-merge CI','PR đã merge · CI sau merge')],[T('vs ready for review','so với PR chờ review')],[T('vs CI running','so với CI đang chạy')],[T('✦ Trace Agent final decision','✦ Quyết định cuối của Trace Agent')]],BM.map(m=>el('tr',{},
      el('td',{},el('div',{class:'ttl'},a(m.url,'#'+m.num),' ',el('span',{class:'obsraw'},m.title)),el('div',{class:'meta'},day(m.at),' ',m.ci&&MCI[m.ci]?el('span',{class:'gch '+MCI[m.ci][3]},V()?MCI[m.ci][2]:MCI[m.ci][1]):null)),
      el('td',{},m.ready.length?m.ready.map(x=>prRef(x,m.num)):el('span',{class:'meta'},'—')),el('td',{},m.running.length?m.running.map(x=>prRef(x,m.num)):el('span',{class:'meta'},'—')),
      el('td',{},(()=>{const f=TA&&TA.merged?TA.merged[String(m.num)]:null;return f?[tachip(f.d),el('div',{class:'ops-why'},L(f.r))]:el('span',{class:'meta'},TA?T('not reviewed','chưa xem'):T('pending: run Trace Agent','chờ: chạy Trace Agent'));})())))):el('div',{class:'ops-empty'},T('No merge of the last 24 h touches an open PR.','Không merge nào trong 24 giờ đụng PR đang mở.')));
    // B · review queue
    s.append(el('h3',{style:'margin-top:14px'},T(`B · Ready for review: merge or not (${nq})`,`B · Chờ review: merge hay chưa (${nq})`)),el('p',{class:'meta'},T("Gates = the 4 required checks on the PR's last commit: DCO, Check code quality, k3-unit-tests, k3-multiprocess-test (runs after 'full'). Sorted: can merge first.","Gate = 4 check bắt buộc trên commit cuối của PR: DCO, Check code quality, k3-unit-tests, k3-multiprocess-test (chạy sau khi gắn 'full'). Sắp xếp: merge được lên đầu.")));
    // evidence in 1 click: each shared file opens at its diff in this PR and in the merged PR
    // per-PR detail (shared files with diff links) lives in the PR Inspector, view 5 (merged 2026-11-24): here a count + button
    const clashFiles=(x,c)=>(c.files||[]).length?el('div',{class:'rv-files'},el('button',{type:'button',class:'pi-btn','data-pi':'pr:'+x.num,'data-pi-view':'5'},`${c.files.length} ${T('shared files','file chung')} · ${T('Inspect','Xem chi tiết')} →`)):null;
    const clashCell=x=>x.clash.length?x.clash.map(c=>el('div',{class:'rv-cl'},lvchip(c.level),' ',a(`${GH_}/pull/${c.m}`,'#'+c.m),' ',el('span',{class:'meta'},L(c.same)),clashFiles(x,c))):el('span',{class:'meta'},T('no clash','không đụng'));
    const QC=[[T('PR','PR')],[T('Gates','Gate')],[T('Clashes with merged','Đụng PR đã merge')],[T('Decision','Quyết định')]],qMain=RV.queue.filter(x=>x.verb!=='review'||x.clash.length),qRest=RV.queue.filter(x=>x.verb==='review'&&!x.clash.length);
    const qrow=x=>el('tr',{},
      el('td',{},el('div',{class:'ttl'},a(x.url,'#'+x.num),' ',el('span',{class:'obsraw'},x.title)),el('div',{class:'meta'},`${x.author||''} · ${pst(x.sub)} · ${fmt(x.age_d)} ${T('d old','ngày')}`)),
      el('td',{},gates(x.gates)),el('td',{},clashCell(x)),el('td',{},rchip(x.verb),el('div',{class:'ops-why'},L(x.why))));
    s.append(qMain.length?table(QC,qMain.map(qrow)):el('div',{class:'ops-empty'},T('No PR needs a decision now.','Không PR nào cần quyết định ngay.')));
    if(qRest.length)s.append(el('details',{style:'margin-top:8px'},el('summary',{},T(`+ ${qRest.length} more PRs waiting for review, no clash with the merges`,`+ ${qRest.length} PR khác chờ review, không đụng các merge`)),table(QC,qRest.map(qrow))));
    // C · running CI
    s.append(el('h3',{style:'margin-top:14px'},T(`C · CI running now: cancel or keep (${nr})`,`C · CI đang chạy: huỷ hay để (${nr})`)),el('p',{class:'meta'},T('Cancel when the result will be thrown away: the PR must be rebased (a merge changed the same function) or DCO already failed. Cancel in Buildkite (build page → Cancel) or with gh run cancel for GitHub Actions.','Huỷ khi kết quả sẽ bị bỏ: PR phải rebase (một merge đã đổi cùng hàm) hoặc DCO đã fail. Huỷ trên Buildkite (trang build → Cancel) hoặc gh run cancel cho GitHub Actions.')));
    s.append(RV.running.length?table([[T('PR','PR')],[T('Running','Đang chạy')],[T('Gates','Gate')],[T('Clashes with merged','Đụng PR đã merge')],[T('Decision','Quyết định')]],RV.running.map(x=>el('tr',{},
      el('td',{},el('div',{class:'ttl'},a(x.url,'#'+x.num),' ',el('span',{class:'obsraw'},x.title)),el('div',{class:'meta'},x.author||'')),
      el('td',{},x.runs.length?x.runs.map(r=>el('div',{},a(r.url,r.pipe),' ',el('span',{class:'meta'},T(`for ${ago(r.started)}`,`đã ${ago(r.started)}`)))):el('span',{class:'meta'},T('GitHub Actions','GitHub Actions'))),
      el('td',{},gates(x.gates)),el('td',{},clashCell(x)),
      el('td',{},rchip(x.verb),el('div',{class:'ops-why'},L(x.why)),x.save?el('div',{class:'meta'},T(`saves ≈${fmt(x.save)} GPU-min`,`tiết kiệm ≈${fmt(x.save)} GPU-phút`)):null)))):el('div',{class:'ops-empty'},T('No PR CI running at snapshot time.','Không có CI của PR đang chạy lúc chụp dữ liệu.')));
    s.append(el('p',{class:'ops-src'},T(`Sources: git origin/dev ${day(O.w0)} → ${day(O.at)} · PR snapshot ${day(O.snap_at)} · open-PR diffs ${day(O.patches_at)}. Rule-based (diff hunks, ≈ line numbers): check P0 / P1 by hand before stopping CI.`,
      `Nguồn: git origin/dev ${day(O.w0)} → ${day(O.at)} · snapshot PR ${day(O.snap_at)} · diff PR mở ${day(O.patches_at)}. Theo luật (hunk diff, số dòng ≈): kiểm tra tay P0 / P1 trước khi dừng CI.`)));
    // round 3 (C_ia 5A / P3): the decision strip stays open; each group A / B / C is a closed <details> whose summary is its heading
    {let det=null;[...s.children].forEach(ch=>{if(ch.tagName==='H3'){det=el('details',{class:'ops-fold','data-ux':'overlap-group'});ch.before(det);const sm=el('summary',{});sm.append(...ch.childNodes);ch.remove();det.append(sm);return;}
      if(det&&!ch.classList.contains('ops-src')&&!ch.classList.contains('rv-tip'))det.append(ch);else det=null;});}}

  function rCancel(){const s=sec('cancel');if(!s)return;const C=D.overlap.cancel;s.replaceChildren(head('6B','Cancel CI of older dev commits?','Huỷ CI của commit dev cũ?','Dev builds still running when a newer commit lands: cost and risk of cancelling.','Build dev vẫn chạy khi có commit mới hơn: chi phí và rủi ro khi huỷ.'));
    const sum=k=>C.reduce((x,c)=>x+(c[k]||0),0),over=sum('over'),done=sum('over_done'),om=sum('over_min'),fo=sum('failed_over'),oc=sum('over_cancel'),n=sum('n');
    const gate=C.filter(c=>c.gate),nong=C.filter(c=>!c.gate&&c.over_done),act=C.filter(c=>c.over_cancel).map(c=>c.pipeline),ga=gate.filter(c=>c.over_cancel).map(c=>c.pipeline);
    s.append(el('div',{class:'ops-kpis'},kpi(`${over}/${n}`,T('overtaken dev builds','build dev bị vượt')),kpi(fmt(oc),T('already cancelled','đã huỷ')),
      kpi(`${fmt(done)}`,T('ran to the end','chạy tới cuối'),done?'warn':''),kpi(`${fmt(Math.round(om))} min`,T('wall-min after the newer commit','phút chạy sau commit mới'),om?'warn':''),
      kpi(fmt(fo),T('ran to the end and failed','chạy tới cuối và fail'),fo?'bad':'')));
    s.append(el('div',{class:'ops-verdict'},el('ul',{style:'margin:0'},
      el('li',{},T(`Already cancelling: ${act.join(', ')||'none seen'}.`,`Đã tự huỷ: ${act.join(', ')||'chưa thấy'}.`)),
      nong.length?el('li',{},T(`Still run to the end: ${nong.map(c=>c.pipeline).join(', ')} → enable cancel_intermediate_builds on dev (≈${fmt(Math.round(om))} wall-min / 24 h).`,`Vẫn chạy tới cuối: ${nong.map(c=>c.pipeline).join(', ')} → bật cancel_intermediate_builds cho dev (≈${fmt(Math.round(om))} phút / 24 giờ).`)):null,
      el('li',{},ga.length?T(`Required-check pipelines already cancel (${ga.join(', ')}). Cost: to find the merge that broke dev, re-run the cancelled commits.`,`Pipeline check bắt buộc đã tự huỷ (${ga.join(', ')}). Đánh đổi: muốn tìm merge làm hỏng dev phải chạy lại các commit đã huỷ.`)
        :T(`Required-check pipelines: keep one result per merged commit.`,`Pipeline check bắt buộc: giữ một kết quả cho mỗi commit đã merge.`)),
      fo?el('li',{},T(`${fo} overtaken builds failed: cancelling them would hide which commit broke dev.`,`${fo} build bị vượt đã fail: huỷ sẽ che mất commit làm hỏng dev.`)):null)));
    s.append(table([['Pipeline'],[T('Required check?','Check bắt buộc?')],[T('dev builds','build dev'),'r'],[T('overtaken','bị vượt'),'r'],[T('cancelled','đã huỷ'),'r'],[T('ran to end','chạy tới cuối'),'r'],[T('min after newer','phút sau commit mới'),'r'],[T('failed','fail'),'r']],
      C.map(c=>el('tr',{},el('td',{},el('span',{class:'obsraw'},c.pipeline)),el('td',{},c.gate?T('yes','có'):'—'),el('td',{class:'r'},c.n),el('td',{class:'r'},c.over),el('td',{class:'r'},c.over_cancel),el('td',{class:'r'},c.over_done),el('td',{class:'r'},fmt(Math.round(c.over_min))),el('td',{class:'r'},c.failed_over)))));
    s.append(el('p',{class:'ops-src'},T('Source: ','Nguồn: '),el('span',{class:'obsraw'},D.overlap.cancel_src),T('. Schedules excluded. Overtaken = a newer dev commit arrived before the build finished.','. Bỏ build theo lịch. Bị vượt = commit dev mới hơn tới trước khi build xong.')));}

  function tasksBox(tab){const M=D.metrics[tab]||[],TK=(D.tasks||{})[tab]||[];
    return [table([[T('Metric','Metric')],[T('Definition','Định nghĩa')],[T('Baseline','Baseline'),'r'],[T('Target','Mục tiêu'),'r'],[T('After','Sau'),'r'],[T('Task','Task')]],M.map(m=>{const t=TK.find(x=>x.metric===m.key);
      return el('tr',{},el('td',{},L(m.name)),el('td',{},el('span',{class:'meta'},L(m.defn))),el('td',{class:'r'},`${fmt(m.base)} ${m.unit||''}`),el('td',{class:'r'},t&&t.target||'—'),el('td',{class:'r'},t&&t.after!=null?t.after:'—'),el('td',{},t?el('span',{class:'obsraw'},`${t.key} · ${t.status||''}`):'—'));})),
      TK.length?null:el('div',{class:'ops-empty',style:'margin-top:8px'},T('No task assigned to this tab yet (TASKS in build_ops_tabs.py).','Chưa có task nào gán cho tab này (TASKS trong build_ops_tabs.py).'))];}
  function rTasks(tab,n){const s=sec('tasks-'+tab);if(!s)return;
    s.replaceChildren(head(n,'Tasks & metrics','Task & metric','How this tab measures a task: baseline (30 d or now) → target → after. Tasks are classified into tabs after analysis.','Cách tab này đo một task: baseline (30 ngày hoặc hiện tại) → mục tiêu → sau khi làm. Task được phân vào tab sau khi phân tích.'),...tasksBox(tab).filter(Boolean));}

  const CLS={'dev-red':['dev turned red','dev bị đỏ'],infra:['infra','hạ tầng'],flaky:['flaky','flaky'],'env-dependent':['environment','môi trường'],'pr-bug':['PR bug','bug của PR']};
  function rTA(tab,n){const s=sec('ta-'+tab);if(!s)return;const it=(D.ta||{})[tab]||[],M=D.ta_meta||{},H=M.health||{};
    const prop=x=>el('details',{class:'ops-ta'},el('summary',{},el('span',{class:'obsraw'},`${x.tag} · #${x.num}`),el('b',{class:'obsraw'},x.title),el('span',{class:'ops-kind'},L(CLS[x.cls])||x.cls),x.impact&&x.impact!=='none'?el('span',{class:'ops-kind semantic'},x.impact):null,x.conf?el('span',{class:'meta'},`${T('confidence','độ tin cậy')} ${L(CONF[x.conf])||x.conf}`):null),
      el('div',{class:'why'},'🔎 ',L(x.root)),x.fix?el('div',{class:'fix'},'🛠️ ',L(x.fix)):null,el('div',{class:'meta'},`${day(x.run_at)}${x.fix_pr?' · fix PR #'+x.fix_pr:''}`,x.report?el('span',{class:'obsraw'},' · '+x.report):''));
    if(tab==='release'){
      const P=H.publish||{},bad=(P.conclusion&&P.conclusion!=='success')||P.failed_jobs||(H.nightly&&H.nightly.fail>=H.nightly.n/2);
      s.replaceChildren(head(n,`Release health · ${H.stable||''}`,`Sức khoẻ release · ${H.stable||''}`));
      s.append(el('div',{class:'ops-verdict',style:`border-left-color:var(--${bad?'warning':'good'})`},
        el('div',{},el('b',{},'publish.yml '+(H.stable||'')+': '),P.status?T(`${P.status}${P.conclusion?' / '+P.conclusion:''}, attempt ${P.attempt||1}, ${P.failed_jobs||0} failed jobs`,`${P.status==='queued'?'đang xếp hàng':P.status==='completed'?'đã chạy xong':P.status}${P.conclusion?' / '+P.conclusion:''}, lần chạy thứ ${P.attempt||1}, ${P.failed_jobs||0} job fail`):'—',P.url?el('span',{},' · ',a(P.url,T('run','lần chạy'))):null),
        el('div',{},el('b',{},T('Nightly: ','Nightly: ')),T(`${(H.nightly||{}).fail||0} of the last ${(H.nightly||{}).n||0} runs failed`,`${(H.nightly||{}).fail||0} / ${(H.nightly||{}).n||0} lần chạy gần nhất fail`)),
        Object.entries(H.releases||{}).map(([t,r])=>el('div',{},el('b',{},`Trace Agent ${t}: `),T(`${r.blocks} blocks-release, ${r.fixed} fixed`,`${r.blocks} blocks-release, ${r.fixed} đã sửa`),el('span',{class:'meta'},' · '+r.nums.join(', '))))));
      if(it.length)s.append(el('details',{},el('summary',{},T(`Trace Agent proposals for this release (${it.length})`,`Đề xuất Trace Agent cho release này (${it.length})`)),it.map(prop)));return;}
    if(tab==='trace'){const NE=M.not_explained||[];
      s.replaceChildren(head(n,'Failing PRs the Trace Agent has not explained yet','PR fail mà Trace Agent chưa giải thích',`Proposals already show in the trace above. This list is what is left (Trace Agent updated ${day(M.updated)}).`,`Các đề xuất đã có ở phần truy vết bên trên. Danh sách này là phần còn lại (Trace Agent cập nhật ${day(M.updated)}).`));
      s.append(NE.length?table([[T('Release','Release')],['PR'],[T('Status','Trạng thái')]],NE.map(x=>el('tr',{},el('td',{},el('span',{class:'obsraw'},x.tag)),el('td',{},a(GH+x.num,'#'+x.num),' ',el('span',{class:'obsraw'},x.title||'')),el('td',{},x.status==='error'?T('agent run failed','agent chạy lỗi'):T('not run yet','chưa chạy'))))):el('div',{class:'ops-empty'},T('Every failing PR has a proposal.','Mọi PR fail đều đã có đề xuất.')));return;}
  }

  function render(){rSummary();rComing();rOptHW('CPU');rOptHW('GPU');rBase();rPub();rOverlap();
    rTA('release','1B');rTA('trace','2B');}
  render();addEventListener('langchange',render);
})();
</script>
<!-- OPS:JS:END -->
"""


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor) if before else page.index(anchor) + len(anchor)
    return page[:i] + ("" if before else "\n") + block.strip() + ("\n" if before else "") + page[i:]


def main():
    data = analyze()
    import decisions as DEC
    data["dec"] = dict(verbs=DEC.VERBS, rules=DEC.RULE)
    save_hist((data.get("opt") or {}).get("cost"), ((data.get("opt") or {}).get("v3") or {}).get("extras"))  # one summary per day for before/after
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    page = open(PAGE, encoding="utf-8").read()
    js = JS.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    nr_js = os.path.join(HERE, "next_release.js")  # Next release cockpit 3A–3E (reads opsData.coming.nr)
    if os.path.exists(nr_js):
        js = js.replace("<!-- OPS:JS:END -->", open(nr_js, encoding="utf-8").read().strip() + "\n<!-- OPS:JS:END -->")
    page = put(page, "/* OPS:CSS:START */", "/* OPS:CSS:END */", CSS, "@media (max-width:980px)")
    page = put(page, "<!-- OPS:HTML:START -->", "<!-- OPS:HTML:END -->", HTML, "<!-- OBS:HTML:END -->", before=False)
    page = put(page, "<!-- OPS:JS:START -->", "<!-- OPS:JS:END -->", js, "</body>")
    open(PAGE, "w", encoding="utf-8").write(page)
    o, p = data["overlap"], data["prs"]
    print(f"ops: merged scope {len(data['coming']['merged'])} · open {p['n_open']} · skip-approval {p['n_skip']} · "
          f"pairs {o['n_pairs']} {dict(o['kinds'])} · flaky {o['n_flaky']} · public CI {'yes' if data['pub'] else 'no'} · "
          f"TA {({k: len(v) for k, v in data['ta'].items()})}")


if __name__ == "__main__":
    main()
