"""Entity index of the Release & CI page (v2, phase P1).

One graph for every object the page shows, linked up and down the level chain:

    Sprint item ⇄ Release ⇄ PR ⇄ Feature ⇄ CI (pipeline · build) ⇄ Test (CPU file / GPU workload) ⇄ Bug

Reads ONLY local files (collector JSON, P1 CSVs, the local git clone, the roadmap). No network, no tokens.
Writes entities.json and embeds it in the page as <script id="entData" type="application/json">.
Run it BEFORE the tab generators (they will read entities.json from P2 on):

    python -I -X utf8 build_entities.py            # write entities.json + embed
    python -I -X utf8 build_entities.py --no-page  # write entities.json only

Rules: an edge that cannot be proven from a local file is not drawn; it is counted in health.missing.
Times are UTC, 'YYYY-MM-DD HH:MM'. `decision` stays null here; verbs come from decisions.py (phase P3).
"""
import collections
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "P1"))

import area_meta  # noqa: E402
import build_ops_tabs as ops  # noqa: E402  (reuse: SRC_AREA rules, git helpers, roadmap parser, check-state rules)
import gates  # noqa: E402
from areas import area_of  # noqa: E402
from build_jobs_table import parse_label  # noqa: E402

PAGE = str(Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
OUT = os.path.join(HERE, "entities.json")
P1 = os.path.join(HERE, "..", "P1")
GH = "https://github.com/LMCache/LMCache"
BK = "https://buildkite.com/lmcache"
FIRST_TAG = (0, 5, 7)          # releases older than v0.5.7 are not on the page
TAG_RX = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?(?:\.post(\d+))?$")
PR_RX = re.compile(r"\(#(\d+)\)\s*$")

# relation -> (from kind, to kind, where the proof comes from)
RELS = {
    "plans":       ("sprint", "pr",      "release-<ver>/ROADMAP.md item lines with (#n)"),
    "targets":     ("sprint", "release", "ROADMAP.md 'Coming in vX'"),
    "contains":    ("release", "pr",     "git first-parent log <prev tag>..<tag> (next release: <last tag>..origin/dev)"),
    "shipped_in":  ("pr", "release",     "squash commit is in <prev stable>..<stable tag>"),
    "edits":       ("pr", "test",        "changed files of the PR that are test files in cpu_tests.json"),
    "changes":     ("pr", "feature",     "changed files × SRC_AREA / area_of (strong: source file, weak: tests only)"),
    "ran":         ("pr", "build",       "Buildkite pull_request.id (snapshot, ops_ci_24h, P1/jobs_all_30d.csv)"),
    "of":          ("build", "ci",       "Buildkite pipeline slug of the build"),
    "runs":        ("build", "test",     "MP job label -> workload (parse_label)"),
    "runs_suite":  ("ci", "test",        "GPU: workloads seen in the pipeline's jobs (strong) · CPU: files of the unit-test run in cpu_tests.json (likely)"),
    "covered_by":  ("feature", "test",   "CPU: area_of(test file) · GPU: AREA_CLASS -> CLASSES tiers -> TIER_WORKLOADS (2 = conditional -> likely)"),
    "fails_with":  ("test", "bug",       "P1/raw/fail_signatures.json job -> workload of that job"),
    "failed_with": ("build", "bug",      "P1/raw/fail_signatures.json job -> its build"),
    "fixed_by":    ("bug", "pr",         "closingIssuesReferences of the PR (snapshot pr_files.issues)"),
}


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def rows(name):
    p = os.path.join(P1, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def at(s):
    """Any ISO time -> 'YYYY-MM-DD HH:MM' in UTC (None when missing)."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(s)[:16].replace("T", " ")


def tag_key(t):
    m = TAG_RX.match(t)
    if not m:
        return None
    a, b, c, rc, post = m.groups()
    # rc < final < .postN; index 3 stays 10**6 for every non-rc tag (stable and post)
    return (int(a), int(b), int(c), int(rc) if rc else 10 ** 6, int(post) if post else 0)


BK_STATUS = {"passed": "green", "failed": "red", "failing": "red", "running": "running", "scheduled": "running", "creating": "running",
             "blocked": "waiting", "canceled": "unknown", "canceling": "unknown", "skipped": "unknown", "not_run": "unknown"}
ROLLUP = {"SUCCESS": "green", "FAILURE": "red", "ERROR": "red", "PENDING": "running", "EXPECTED": "running"}
CHECK_KEY = {"DCO": "dco", "Check code quality": "quality", "buildkite/k3-unit-tests": "unit", "buildkite/k3-multiprocess-test": "mp"}


def req_status(checks, rollup):
    """Status of an open PR from its 4 required checks: red if one failed, running if one runs,
    green only when all 4 passed, waiting when one has not started (for example MP without the 'full' label)."""
    if not checks:
        return ROLLUP.get(rollup, "unknown")
    vals = list(checks.values())
    if "fail" in vals:
        return "red"
    if "run" in vals:
        return "running"
    return "green" if len(checks) == len(CHECK_KEY) and all(v == "ok" for v in vals) else "waiting"


class Graph:
    def __init__(self):
        self.nodes, self.edges, self._seen = {}, [], set()

    def node(self, kind, id_, **kw):
        key = f"{kind}:{id_}"
        n = self.nodes.get(key)
        if n is None:
            n = self.nodes[key] = dict(kind=kind, id=str(id_), title=None, status="unknown", decision=None, url=None, at=None, tabs=[])
        for k, v in kw.items():
            if k == "tabs":
                for t in v:
                    if t not in n["tabs"]:
                        n["tabs"].append(t)
            elif v is not None and (n.get(k) in (None, "unknown", "") or k in ("status", "state", "checks")):
                n[k] = v
        return key

    def edge(self, a, b, rel, strength="strong"):
        k = (a, b, rel)
        if k in self._seen or a not in self.nodes or b not in self.nodes:
            return
        self._seen.add(k)
        self.edges.append({"from": a, "to": b, "rel": rel, "strength": strength})


def git_range(rng):
    """First-parent squash commits of a git range -> [{num, sha, at, title, files}] (PR number from '(#n)')."""
    out = ops.git("log", "--first-parent", "--format=__C__|%h|%cI|%s", "--name-only", rng)
    res, cur = [], None
    for ln in (out or "").splitlines():
        if ln.startswith("__C__|"):
            _, sha, when, subj = ln.split("|", 3)
            m = PR_RX.search(subj)
            cur = dict(num=int(m.group(1)), sha=sha, at=when, title=PR_RX.sub("", subj).strip(), files=[]) if m else None
            if cur:
                res.append(cur)
        elif ln.strip() and cur:
            cur["files"].append(ln.strip())
    return res


def build():
    G = Graph()
    miss = collections.Counter()
    inputs = {}

    def src(path):
        if os.path.exists(path):
            inputs[os.path.relpath(path, HERE).replace("\\", "/")] = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).strftime("%Y-%m-%d %H:%M")
        return path

    snap = load(src(os.path.join(HERE, "observe_snapshot.json")), {}) or {}
    gh, bk = snap.get("gh") or {}, snap.get("bk") or {}
    ci24 = load(src(os.path.join(HERE, "ops_ci_24h.json")), {}) or {}
    patches = (load(src(os.path.join(HERE, "overlap_patches.json")), {}) or {}).get("prs") or {}
    cpu = load(src(os.path.join(HERE, "cpu_tests.json")), {}) or {}
    sigs = load(src(os.path.join(P1, "raw", "fail_signatures.json")), {}) or {}
    props = load(src(os.path.join(HERE, "..", "trace_agent", "proposals.json")), {}) or {}
    jobs = rows("jobs_all_30d.csv"); src(os.path.join(P1, "jobs_all_30d.csv"))
    pr30 = rows("pr_30d.csv"); src(os.path.join(P1, "pr_30d.csv"))
    ttg = rows("ttg_30d.csv"); src(os.path.join(P1, "ttg_30d.csv"))
    ghj = rows("gh_jobs_30d.csv"); src(os.path.join(P1, "gh_jobs_30d.csv"))
    wcost = {r["workload"]: r for r in rows("cost_by_workload.csv")}

    # ------------------------------------------------------------ features (29 areas)
    for aid, a in area_meta.AREAS.items():
        st = ops.STAGE_OF.get(aid)
        G.node("feature", aid, title=a.get("name") or aid, stage=ops.FLOW[st][0] if st is not None else None,
               klass=gates.AREA_CLASS.get(aid, "core"), tabs=["#cpu/tiers", "#cpu/explore", "#gates/tiers"])

    # ------------------------------------------------------------ releases + their PRs (local clone)
    files_of = {}      # PR number -> changed files
    merged = {}        # PR number -> squash commit info
    tags = sorted((t for t in (ops.git("tag") or "").split() if tag_key(t)), key=tag_key)
    stable = [t for t in tags if tag_key(t)[3] == 10 ** 6]
    rel_tags = [t for t in tags if tag_key(t)[:3] >= FIRST_TAG]
    pub = gh.get("publish_tags") or {}
    rel_at = {r["tag_name"]: r.get("published_at") or r.get("created_at") for r in gh.get("releases") or []}
    for t in rel_tags:
        prev = tags[tags.index(t) - 1] if tags.index(t) else None
        runs = pub.get(t) or []
        concl = [r.get("conclusion") for r in runs if r.get("status") == "completed"]
        status = "green" if concl[:1] == ["success"] else "red" if concl[:1] == ["failure"] else "unknown"   # newest publish run; cancelled = unknown
        rk = G.node("release", t, title=t, status=status, state="rc" if "rc" in t else "stable", url=f"{GH}/releases/tag/{t}",
                    at=at(rel_at.get(t) or (ops.git("log", "-1", "--format=%cI", t) or "").strip()), prev=prev,
                    tabs=["#obs/release", "#obs/trace"])
        for c in git_range(f"{prev}..{t}") if prev else []:
            merged.setdefault(c["num"], c); files_of.setdefault(c["num"], c["files"])
            G.edge(rk, G.node("pr", c["num"], title=c["title"], state="merged", at=at(c["at"]), sha=c["sha"], url=f"{GH}/pull/{c['num']}",
                              tabs=["#obs/trace"]), "contains")
    # the next release: everything on origin/dev after the last tag
    last = rel_tags[-1] if rel_tags else (stable[-1] if stable else None)
    rm_path = ops.find_roadmap(stable[-1] if stable else None)
    rm = ops.parse_roadmap(rm_path) if rm_path and os.path.exists(rm_path) else None
    if rm_path:
        src(str(rm_path))
    k = tag_key(last) if last else None
    next_ver = "v" + (rm["version"] if rm and rm.get("version") else f"{k[0]}.{k[1]}.{k[2] + (0 if k[3] != 10 ** 6 else 1)}" if k else "next")
    if next_ver in G.nodes.get(f"release:{next_ver}", {}).get("id", ""):
        next_key = f"release:{next_ver}"      # the stable tag already exists
    else:
        next_key = G.node("release", next_ver, title=f"{next_ver} (next, not tagged)", status="waiting", state="next", prev=last,
                          tabs=["#obs/coming"])
    for c in git_range(f"{last}..origin/dev") if last else []:
        merged.setdefault(c["num"], c); files_of.setdefault(c["num"], c["files"])
        G.edge(next_key, G.node("pr", c["num"], title=c["title"], state="merged", at=at(c["at"]), sha=c["sha"], url=f"{GH}/pull/{c['num']}",
                                tabs=["#obs/coming"]), "contains")
    # PR -> stable release it shipped in
    for i, t in enumerate(stable):
        if tag_key(t)[:3] < FIRST_TAG or not i:
            continue
        for c in git_range(f"{stable[i - 1]}..{t}"):
            G.edge(f"pr:{c['num']}", f"release:{t}", "shipped_in")

    # ------------------------------------------------------------ PRs: open (snapshot), 30-day window (P1), merged list
    for n in (gh.get("prs_gql") or {}).get("nodes") or []:
        commit = (((n.get("commits") or {}).get("nodes") or [{}])[0].get("commit")) or {}
        roll = commit.get("statusCheckRollup") or {}
        checks = {}
        for c in (roll.get("contexts") or {}).get("nodes") or []:
            key = CHECK_KEY.get(c.get("context") or c.get("name"))
            if key:
                checks[key] = ops.ctx_state(c)
        G.node("pr", n["number"], title=n.get("title"), state="draft" if n.get("isDraft") else "open", url=n.get("url"),
               status=req_status(checks, roll.get("state")), rollup=roll.get("state"), at=at(n.get("updatedAt")), author=(n.get("author") or {}).get("login"),
               review=n.get("reviewDecision"), mergeable=n.get("mergeable"), checks=checks or None, sha=(commit.get("oid") or "")[:8] or None,
               labels=[x["name"] for x in (n.get("labels") or {}).get("nodes") or []] or None, tabs=["#obs/overlap"])
    for m in (gh.get("merged") or []) + (gh.get("merged_recent") or []):
        G.node("pr", m["number"], title=m.get("title"), state="merged", url=m.get("html_url"), at=at((m.get("pull_request") or {}).get("merged_at")),
               author=(m.get("user") or {}).get("login"), labels=[x["name"] for x in m.get("labels") or []] or None)
    green = {r["pr"] for r in ttg if not r.get("not_green")}
    for r in pr30:
        G.node("pr", r["pr"], state="merged" if r.get("merged") else None, url=r.get("pr_url"), author=r.get("author"),
               at=at(r.get("merged") or r.get("created")), status="green" if r["pr"] in green else None, tabs=["#r1130/prs"])
    for num, v in (gh.get("pr_files") or {}).items():
        files_of.setdefault(int(num), v.get("files") or [])
    for num, hunks in patches.items():
        files_of.setdefault(int(num), sorted({h["f"] for h in hunks if h.get("f")}))
    # Trace Agent finding on a PR (shown on the card as the dashed chip later; never mixed with rule decisions)
    for key, p in (props.get("prs") or {}).items() if isinstance(props.get("prs"), dict) else []:
        num = p.get("pr") or p.get("num") or (key.split("::")[-1] if "::" in key else None)
        if num and f"pr:{num}" in G.nodes and (p.get("classification") or p.get("cls")):
            G.nodes[f"pr:{num}"]["ta"] = dict(cls=p.get("classification") or p.get("cls"), impact=p.get("release_impact") or p.get("impact"),
                                             fix_pr=p.get("fix_pr"), tag=p.get("tag") or key.split("::")[0])

    # ------------------------------------------------------------ PR -> feature
    for key, n in G.nodes.items():
        if n["kind"] != "pr":
            continue
        files = files_of.get(int(n["id"]))
        if not files:
            miss["pr_without_files"] += 1
            continue
        n["nfiles"] = len(files)
        is_src = lambda f: not (f.startswith(("tests/", "docs/", "examples/")) or "/tests/" in f or f.endswith((".md", ".rst")))
        strong = collections.Counter(a for a in (ops.src_area(f) for f in files if is_src(f)) if a)
        weak = collections.Counter(a for a in (ops.src_area(f) for f in files if not is_src(f)) if a)
        for a, _ in strong.most_common():
            G.edge(key, f"feature:{a}", "changes", "strong")
        for a, _ in weak.most_common():
            G.edge(key, f"feature:{a}", "changes", "weak")
        if not strong and not weak:
            miss["pr_without_feature"] += 1
        tests = [f for f in files if f.startswith("tests/") and f.endswith(".py")]
        if tests:
            n["tests_changed"] = tests[:12]

    # ------------------------------------------------------------ CI pipelines / workflows
    last_dev = {}
    for b in bk.get("dev_builds") or []:
        last_dev.setdefault(b["pipeline"]["slug"], b)
    for p in bk.get("pipelines") or []:
        b = last_dev.get(p["slug"])
        G.node("ci", p["slug"], title=p.get("name") or p["slug"], system="Buildkite", url=p.get("web_url") or f"{BK}/{p['slug']}",
               status=BK_STATUS.get(b["state"], "unknown") if b else "unknown", at=at(b["created_at"]) if b else None,
               required=("buildkite/" + p["slug"]) in CHECK_KEY, tabs=["#obs/opt_gpu", "#r1130/baseline"])
    wf_req = collections.defaultdict(bool)
    for r in ghj:
        wf_req[r["workflow"]] |= r.get("required") == "1"
    last_run = {}
    for r in gh.get("runs_dev") or []:
        last_run.setdefault(r["name"], r)
    for wf, req in wf_req.items():
        r = last_run.get(wf)
        st = "unknown" if not r else "running" if r.get("status") != "completed" else "green" if r.get("conclusion") == "success" else "red" if r.get("conclusion") == "failure" else "unknown"
        G.node("ci", "gha/" + wf, title=wf, system="GitHub Actions", required=req, status=st, at=at(r.get("created_at")) if r else None,
               url=r.get("html_url") if r else f"{GH}/actions", tabs=["#obs/opt_cpu", "#r1130/cpu"])

    # ------------------------------------------------------------ tests: CPU files + GPU workloads
    for f in cpu.get("files") or []:
        a = area_of(f["path"])
        tk = G.node("test", f["path"], title=f["path"].rsplit("/", 1)[-1], hw="cpu", status="red" if f.get("fail") else "green",
                    passed=f.get("pass"), failed=f.get("fail"), skipped=f.get("skip"), secs=f.get("secs"),
                    url=f"{GH}/blob/dev/{f['path']}", tabs=["#cpu/explore", "#cpu/tiers"])
        if a != "other" and f"feature:{a}" in G.nodes:
            G.edge(f"feature:{a}", tk, "covered_by", "strong")
        else:
            miss["cpu_test_without_feature"] += 1
        for ci_id in ("k3-unit-tests", "gha/Test"):
            G.edge(f"ci:{ci_id}", tk, "runs_suite", "likely")
    for f in cpu.get("notrun") or []:
        a = area_of(f["path"])
        tk = G.node("test", f["path"], title=f["path"].rsplit("/", 1)[-1], hw="cpu", status="unknown", why_not_run=f.get("why"),
                    url=f"{GH}/blob/dev/{f['path']}", tabs=["#cpu/tiers"])
        if a != "other" and f"feature:{a}" in G.nodes:
            G.edge(f"feature:{a}", tk, "covered_by", "strong")
    wl_last = {}
    for r in jobs:     # the file is ordered by build; keep the newest finished job per workload
        w = r.get("workload")
        if w and r.get("state") in ("passed", "failed") and (w not in wl_last or r["build_created"] > wl_last[w]["build_created"]):
            wl_last[w] = r
    known_wl = {w["name"] for w in gates.WORKLOADS} | set(wcost) | set(wl_last)
    for w in sorted(known_wl):
        if w in ("unit_tests", ""):
            continue
        c, lj = wcost.get(w) or {}, wl_last.get(w)
        G.node("test", "gpu/" + w, title=w, hw="gpu", status=BK_STATUS.get(lj["state"], "unknown") if lj else "unknown",
               at=at(lj["finished_at"] or lj["build_created"]) if lj else None, gpus=c.get("gpus") or None,
               runs_30d=int(c["runs_30d"]) if c.get("runs_30d") else None,
               fail_pct=float(c["first_try_fail_pct"]) if c.get("first_try_fail_pct") else None,
               pass_after_retry_pct=float(c["pass_after_retry_pct"]) if c.get("pass_after_retry_pct") else None,
               gpu_min_p50=float(c["gpu_min_p50"]) if c.get("gpu_min_p50") else None, tabs=["#gpu/tiers", "#gpu/cost"])
    # feature -> GPU workload through the change class of the feature
    tiers_of = {c["id"]: c["tiers"] for c in gates.CLASSES}
    for aid in area_meta.AREAS:
        tiers = tiers_of.get(gates.AREA_CLASS.get(aid, "core"), {})
        for tier, need in tiers.items():
            for w in gates.TIER_WORKLOADS.get(tier, []):
                names = [x for x in known_wl if x not in ("unit_tests", "")] if w.startswith("all ") else [re.sub(r"\s*\(.*\)$", "", w)]
                if w.startswith("all ") and need != 1:
                    continue
                for name in names:
                    G.edge(f"feature:{aid}", f"test:gpu/{name}", "covered_by", "strong" if need == 1 else "likely")
    # PR -> the test files it edits (the test card lists the PRs that changed it)
    for key, n in list(G.nodes.items()):
        if n["kind"] == "pr":
            for f in files_of.get(int(n["id"])) or []:
                if f"test:{f}" in G.nodes:
                    G.edge(key, f"test:{f}", "edits")
    for aid in area_meta.AREAS:
        if not any(e["from"] == f"feature:{aid}" and e["rel"] == "covered_by" for e in G.edges):
            miss["feature_without_test"] += 1

    # ------------------------------------------------------------ builds
    def add_build(slug, number, state=None, url=None, when=None, pr=None, branch=None, commit=None, tab=None):
        if slug and f"ci:{slug}" not in G.nodes:
            G.node("ci", slug, title=slug, system="Buildkite", url=f"{BK}/{slug}")
        bkey = G.node("build", f"{slug}/{number}", title=f"{slug} #{number}", status=BK_STATUS.get(state, "unknown") if state else None,
                      state=state, url=url or f"{BK}/{slug}/builds/{number}", at=at(when), branch=branch, sha=(commit or "")[:8] or None,
                      tabs=[tab] if tab else [])
        G.edge(bkey, f"ci:{slug}", "of")
        if pr and f"pr:{pr}" in G.nodes:
            G.edge(f"pr:{pr}", bkey, "ran")
        elif pr:
            miss["build_with_unknown_pr"] += 1
        return bkey

    for b in (bk.get("active") or []) + (bk.get("dev_builds") or []) + [x for v in (bk.get("recent") or {}).values() for x in v]:
        add_build(b["pipeline"]["slug"] if b.get("pipeline") else None, b["number"], b.get("state"), b.get("web_url"), b.get("created_at"),
                  (b.get("pull_request") or {}).get("id"), b.get("branch"), b.get("commit"), "#obs/overlap")
    for b in ci24.get("bk") or []:
        bkey = add_build(b["pipeline"]["slug"], b["number"], b.get("state"), b.get("web_url"), b.get("created_at"),
                         (b.get("pull_request") or {}).get("id"), b.get("branch"), b.get("commit"), "#obs/opt_gpu")
        for j in b.get("jobs") or []:
            if j.get("type", "script") != "script" or not j.get("name"):
                continue
            w = parse_label(j["name"])[0]
            if f"test:gpu/{w}" in G.nodes:
                G.edge(bkey, f"test:gpu/{w}", "runs"); G.edge(f"ci:{b['pipeline']['slug']}", f"test:gpu/{w}", "runs_suite")
            elif w not in ("unit_tests",):
                miss["gpu_job_without_workload"] += 1
    # k3-multiprocess-test builds since the end of the 30-day window (mp_pr_collect.py): the PR's own MP evidence
    mpb = load(src(os.path.join(HERE, "mp_pr_builds.json")), {}) or {}
    for b in mpb.get("builds") or []:
        add_build(mpb.get("pipeline") or "k3-multiprocess-test", b["number"], b.get("state"), b.get("web_url"), b.get("created_at"),
                  (b.get("pull_request") or {}).get("id"), b.get("branch"), b.get("commit"), "#obs/coming")
    # 30-day table: keep the last build per (PR, pipeline) for PRs that are open or in the next release, and every build with a read failure log
    keep_pr = {n["id"] for n in G.nodes.values() if n["kind"] == "pr" and n.get("state") in ("open", "draft")}
    keep_pr |= {e["to"][3:] for e in G.edges if e["rel"] == "contains" and e["from"] == next_key}
    last_b, by_build, job_build = {}, collections.defaultdict(list), {}
    for r in jobs:
        bid = (r["pipeline"], r["build_number"])
        by_build[bid].append(r); job_build[r["job_id"]] = bid
        if r.get("pr") and (r["pr"], r["pipeline"]) not in last_b or r.get("pr") and int(r["build_number"]) > int(last_b[(r["pr"], r["pipeline"])][1]):
            last_b[(r["pr"], r["pipeline"])] = bid
    wanted = {bid for (pr, _), bid in last_b.items() if pr in keep_pr} | {job_build[j] for j in sigs if j in job_build}
    for bid in sorted(wanted):
        rs = by_build[bid]; r0 = rs[0]
        bkey = add_build(bid[0], bid[1], r0.get("build_state"), r0.get("build_url"), r0.get("build_created"), r0.get("pr") or None,
                         r0.get("branch"), r0.get("commit"), "#r1130/prs")
        for r in rs:
            if r.get("workload") and f"test:gpu/{r['workload']}" in G.nodes:
                G.edge(bkey, f"test:gpu/{r['workload']}", "runs")
    for r in jobs:
        if r.get("workload") and f"test:gpu/{r['workload']}" in G.nodes:
            G.edge(f"ci:{r['pipeline']}", f"test:gpu/{r['workload']}", "runs_suite")
        elif not r.get("workload"):
            miss["bk_job_30d_without_workload"] += 1
    miss["builds_30d_not_indexed"] = len(by_build) - len(wanted)

    # ------------------------------------------------------------ bugs: failure signatures + GitHub issues
    by_job = {r["job_id"]: r for r in jobs}
    sig_n, sig_line, sig_cls, sig_wl = collections.Counter(), {}, {}, collections.defaultdict(collections.Counter)
    for jid, s in sigs.items():
        sid = s.get("sig") or "unknown"
        sig_n[sid] += 1; sig_line.setdefault(sid, s.get("line")); sig_cls.setdefault(sid, s.get("cls"))
        r = by_job.get(jid)
        if r:
            sig_wl[sid][r.get("workload") or ""] += 1
    for sid, n in sig_n.items():
        G.node("bug", "sig/" + sid, title=sid.replace("_", " "), status="red", cls=sig_cls.get(sid), n_30d=n, line=(sig_line.get(sid) or "")[:200] or None,
               tabs=["#r1130/retry"])
        tested = False
        for w, c in sig_wl[sid].items():
            if f"test:gpu/{w}" in G.nodes:
                G.edge(f"test:gpu/{w}", f"bug:sig/{sid}", "fails_with", "likely"); tested = True
        if not tested:
            miss["bug_sig_without_test"] += 1
        miss["bug_sig_without_fix_pr"] += 1      # no local proof links a signature to a fixing PR yet
    for jid, s in sigs.items():
        bid = job_build.get(jid)
        if bid:
            G.edge(f"build:{bid[0]}/{bid[1]}", f"bug:sig/{s.get('sig') or 'unknown'}", "failed_with")
    for num, v in (gh.get("pr_files") or {}).items():
        for iss in v.get("issues") or []:
            pk = f"pr:{num}"
            fixed = G.nodes.get(pk, {}).get("state") == "merged"
            ik = G.node("bug", f"issue/{iss}", title=f"issue #{iss}", status="green" if fixed else "waiting", url=f"{GH}/issues/{iss}")
            G.edge(ik, pk, "fixed_by")
    miss["bug_issue_without_test"] = sum(1 for n in G.nodes.values() if n["kind"] == "bug" and n["id"].startswith("issue/"))

    # ------------------------------------------------------------ sprint / roadmap items
    if rm:
        ver = "v" + (rm.get("version") or next_ver.lstrip("v"))
        for i, it in enumerate(rm["items"], 1):
            nums = [n for n in it["prs"] if f"pr:{n}" in G.nodes]
            done = bool(nums) and all(G.nodes[f"pr:{n}"].get("state") == "merged" for n in nums)
            sk = G.node("sprint", f"{ver}/{i}", title=it["text"][:120], section=it.get("section"), status="green" if done else "waiting",
                        src=rm["rel"], at=at(rm.get("mtime")), tabs=["#obs/coming"])
            if f"release:{ver}" in G.nodes:
                G.edge(sk, f"release:{ver}", "targets")
            for n in nums:
                G.edge(sk, f"pr:{n}", "plans")
            if not nums:
                miss["sprint_item_without_pr"] += 1

    # ------------------------------------------------------------ feature status from its CPU test files
    cov = collections.defaultdict(list)
    for e in G.edges:
        if e["rel"] == "covered_by" and G.nodes[e["to"]].get("hw") == "cpu":
            cov[e["from"]].append(G.nodes[e["to"]]["status"])
    for fk, sts in cov.items():
        G.nodes[fk]["status"] = "red" if "red" in sts else "green" if "green" in sts else "unknown"

    # ------------------------------------------------------------ missing links per relation
    has_out = collections.defaultdict(set)
    for e in G.edges:
        has_out[e["rel"]].add(e["from"]); has_out["<-" + e["rel"]].add(e["to"])
    prs = [k for k, n in G.nodes.items() if n["kind"] == "pr"]
    miss["pr_without_feature"] = sum(1 for k in prs if k not in has_out["changes"])
    miss["pr_without_build"] = sum(1 for k in prs if k not in has_out["ran"])
    miss["pr_open_without_build"] = sum(1 for k in prs if G.nodes[k].get("state") in ("open", "draft") and k not in has_out["ran"])
    miss["pr_merged_without_release"] = sum(1 for k in prs if G.nodes[k].get("state") == "merged" and k not in has_out["<-contains"])
    miss["build_without_pr"] = sum(1 for k, n in G.nodes.items() if n["kind"] == "build" and k not in has_out["<-ran"] and n.get("branch") not in ("dev", None))
    miss["gpu_test_without_feature"] = sum(1 for k, n in G.nodes.items() if n["kind"] == "test" and n.get("hw") == "gpu" and k not in has_out["<-covered_by"])
    miss["gpu_test_without_ci"] = sum(1 for k, n in G.nodes.items() if n["kind"] == "test" and n.get("hw") == "gpu" and k not in has_out["<-runs_suite"])

    for n in G.nodes.values():      # drop empty optional fields: the index is embedded in the page
        for k in [k for k, v in n.items() if v is None and k not in ("title", "status", "decision", "url", "at")]:
            del n[k]
    kinds = collections.Counter(n["kind"] for n in G.nodes.values())
    rels = collections.Counter(e["rel"] for e in G.edges)
    strength = collections.Counter(e["strength"] for e in G.edges)
    oldest = min(inputs.items(), key=lambda kv: kv[1]) if inputs else (None, None)
    return dict(made=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), tz="UTC", snap_at=at(snap.get("at")),
                rels={k: dict(frm=v[0], to=v[1], src=v[2]) for k, v in RELS.items()},
                health=dict(nodes=dict(kinds), edges=dict(rels), strength=dict(strength), missing={k: v for k, v in sorted(miss.items()) if v},
                            inputs=inputs, oldest_input=dict(path=oldest[0], made=oldest[1])),
                nodes=G.nodes, edges=G.edges)


BLOCK = """<!-- ENT:JS:START -->
<script id="entData" type="application/json">__DATA__</script>
<!-- ENT:JS:END -->"""


def compact(data):
    """Page form of the index: same nodes, edges as [from index, to index, relation index, strength index].
    entities.json on disk keeps the readable {from, to, rel, strength} objects."""
    keys = list(data["nodes"])
    idx = {k: i for i, k in enumerate(keys)}
    rel_names, st_names = list(data["rels"]), ["strong", "likely", "weak"]
    d = {k: v for k, v in data.items() if k != "edges"}
    d.update(K=keys, R=rel_names, S=st_names,
             E=[[idx[e["from"]], idx[e["to"]], rel_names.index(e["rel"]), st_names.index(e["strength"])] for e in data["edges"]])
    return d


def embed(data):
    page = open(PAGE, encoding="utf-8").read()
    block = BLOCK.replace("__DATA__", json.dumps(compact(data), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    if "<!-- ENT:JS:START -->" in page:
        page = re.sub(r"<!-- ENT:JS:START -->.*?<!-- ENT:JS:END -->", lambda _: block, page, flags=re.S)
    else:   # before the first tab script, so every later generator script can read it
        anchor = "<!-- OBS:JS:START -->" if "<!-- OBS:JS:START -->" in page else "</body>"
        i = page.index(anchor)
        page = page[:i] + block + "\n" + page[i:]
    open(PAGE, "w", encoding="utf-8").write(page)


def main():
    data = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    h = data["health"]
    print(f"entities: {len(data['nodes'])} nodes {h['nodes']}")
    print(f"          {len(data['edges'])} edges {h['edges']} · strength {h['strength']}")
    print(f"          missing {h['missing']}")
    print(f"          oldest input {h['oldest_input']['path']} ({h['oldest_input']['made']}) · {os.path.getsize(OUT) // 1024} KB")
    if "--no-page" not in sys.argv:
        embed(data)
        print("          embedded in", os.path.basename(PAGE))


if __name__ == "__main__":
    main()
