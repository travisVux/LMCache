"""Data for the Next release cockpit (tab "Next release", sections 3A–3E of 06_PR_TO_CI_VISUAL.html).

Scope-first model:
  scope      = items of release-<ver>/ROADMAP.md ("Coming in vX")
  cut        = release is an rc cut from dev + cherry-picks, so every PR merged before the rc commit ships
  evidence   = per PR: code areas touched (Feature matrix ids), MP CI at PR (labels), breaking
  flow trace = journeys A–D and features F01–F17 of knowledge/inputs/LMCache_CPU_GPU_Feature_Matrix.xlsx
  decisions  = D / C rows of release-<ver>/RELEASE_PREP.md

Local run only. PR labels missing from the snapshot are fetched once with `gh pr view` and cached in
pr_labels_cache.json next to this file (set NR_NO_GH=1 to skip the fetch).
"""
import html
import json
import os
import re
import subprocess
import zipfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
LABEL_CACHE = os.path.join(HERE, "pr_labels_cache.json")

# Journey node -> F-ids (order = steps of sheet "00 Critical Path"). DRAFT, review with the release lead.
NODE_F = {
    "A": [["F01"], ["F01", "F04"], ["F02"], ["F03", "F13"], ["F05", "F07", "F11"], ["F04", "F12"], ["F12"]],
    "B": [["F01"], ["F03"], ["F06"], ["F12", "F06", "F05", "F07"]],
    "C": [["F08", "F09"], ["F03"], ["F08", "F10", "F11"], ["F05", "F04"], ["F12", "F01"]],
    "D": [["F17"], ["F17"], ["F15"], ["F15", "F16"], ["F17"]],
}
# Feature matrix area (28 code areas, ids of cpuData) -> F-ids. DRAFT, review with the release lead.
AREA_F = {
    "vllm": ["F01"], "engines": ["F01"], "lazy": ["F05", "F06"], "blend": ["F13"],
    "lifecycle": ["F01", "F11"], "transport": ["F04"], "modules": ["F01"], "datapath": ["F04", "F05"],
    "lookup": ["F02", "F03"], "http": ["F01", "F14"], "l1": ["F05", "F11"], "smcore": ["F05", "F06", "F11"],
    "l2": ["F07"], "serde": ["F07"], "p2p": ["F08", "F10"], "gds": ["F07"], "orch": ["F05"],
    "layout": ["F12"], "platform": ["F12", "F15"], "native": ["F04", "F12"], "coord": ["F09"], "obs": ["F14"],
    "ip_engine": ["F01"], "ip_store": ["F07"], "ip_ctrl": ["F01"], "cli": ["F14"], "frontend": ["F01"],
    "build": ["F15", "F16", "F17"],
}


def xlsx_rows(path):
    """Rows of every sheet as {column letter: text}. The file uses x:-prefixed XML with inline <x:v> strings."""
    z = zipfile.ZipFile(path)
    rels, wbx = z.read("xl/_rels/workbook.xml.rels").decode(), z.read("xl/workbook.xml").decode()
    out = {}
    for name, rid in re.findall(r'name="([^"]+)" sheetId="\d+" r:id="([^"]+)"', wbx):
        tgt = re.search(r'Target="([^"]+)" Id="%s"|Id="%s"[^>]*Target="([^"]+)"' % (rid, rid), rels)
        p = [x for x in tgt.groups() if x][0].lstrip("/")
        x = z.read(p if p.startswith("xl/") else "xl/" + p).decode("utf-8")
        rows = []
        for row in re.findall(r"<x:row[^>]*>(.*?)</x:row>", x, re.S):
            cells = {c: html.unescape(v) for c, v in re.findall(r'<x:c r="([A-Z]+)\d+"[^>]*><x:v>(.*?)</x:v>', row, re.S)}
            if cells:
                rows.append(cells)
        out[name] = rows
    return out


def critical_path_model(ws):
    path = os.path.join(str(ws), "knowledge", "inputs", "LMCache_CPU_GPU_Feature_Matrix.xlsx")
    if not os.path.exists(path):
        return None
    xr = xlsx_rows(path)
    journeys = [{"id": r["A"], "name": r["B"], "steps": [s.strip() for s in r["C"].split("→")], "test": r.get("D", ""), "impact": r.get("E", "")}
                for r in xr.get("00 Critical Path", []) if re.fullmatch(r"[A-D]", r.get("A", ""))]
    feats = [{"id": r["A"], "step": r.get("B", ""), "name": r.get("C", ""), "cpu": r.get("D", ""), "gpu": r.get("E", ""), "dep": r.get("F", ""),
              "crit": r.get("G", ""), "risk": r.get("H", ""), "gate": r.get("I", ""), "conf": r.get("L", "")}
             for r in xr.get("01 Feature Test Matrix", []) if re.fullmatch(r"F\d\d", r.get("A", ""))]
    return {"src": os.path.relpath(path, str(ws)).replace("\\", "/"), "journeys": journeys, "features": feats, "node_f": NODE_F, "area_f": AREA_F}


def prep_rows(path):
    """D (decision) and C (carry-over blocker) rows of RELEASE_PREP.md: id + the remaining columns, markdown stripped."""
    if not path or not os.path.exists(path):
        return []
    rows = []
    for ln in open(path, encoding="utf-8").read().splitlines():
        m = re.match(r"^\|\s*([DC]\d+)\s*\|(.*)\|\s*$", ln)
        if m:
            rows.append({"id": m.group(1), "cols": [re.sub(r"\*\*|`", "", c).strip() for c in m.group(2).split("|")]})
    return rows


def pr_labels(nums, snap_gh):
    """Labels per PR: snapshot first, then the local cache, then `gh pr view` for what is still missing."""
    lab = {}
    for m in (snap_gh.get("merged") or []) + (snap_gh.get("merged_recent") or []):
        lab[m["number"]] = [x["name"] if isinstance(x, dict) else x for x in m.get("labels") or []]
    try:
        cache = {int(k): v for k, v in json.load(open(LABEL_CACHE, encoding="utf-8")).items()}
    except (OSError, ValueError):
        cache = {}
    for n, v in cache.items():
        lab.setdefault(n, v)
    miss = [n for n in nums if n not in lab]
    if miss and not os.environ.get("NR_NO_GH"):
        for n in miss:
            try:
                r = subprocess.run(["gh", "pr", "view", str(n), "-R", "LMCache/LMCache", "--json", "labels"],
                                   capture_output=True, text=True, encoding="utf-8", timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                break
            if r.returncode:
                break
            lab[n] = cache[n] = [x["name"] for x in json.loads(r.stdout)["labels"]]
        with open(LABEL_CACHE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in sorted(cache.items())}, f, indent=0)
    return lab


def mp_evidence():
    """PR number -> newest k3-multiprocess-test build of that PR in entities.json (passed one first): {key, state, url, at}."""
    ent = {}
    try:
        ent = json.load(open(os.path.join(HERE, "entities.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    N, out = ent.get("nodes") or {}, {}
    for e in ent.get("edges") or []:
        if e["rel"] != "ran" or not e["to"].startswith("build:k3-multiprocess-test/"):
            continue
        b = N.get(e["to"]) or {}
        num = int(e["from"].split(":", 1)[1])
        cur = out.get(num)
        rank = (b.get("status") == "green", b.get("at") or "")
        if not cur or rank > cur[0]:
            out[num] = (rank, dict(key=e["to"], state=b.get("state"), url=b.get("url"), at=b.get("at")))
    return {k: v[1] for k, v in out.items()}


def build(coming, sc, src_area, pr_feature, ptype, risk, snap_gh, ws, prep_path):
    if not sc or not sc.get("prs"):
        return None
    rm = coming.get("roadmap") or {}
    items = [{"section": it["section"], "text": it["text"], "prs": [q["num"] for q in it["prs"]]} for it in rm.get("items") or []]
    cands = {x["num"]: x for x in coming.get("cands") or []}
    breaking = {b["num"] for b in rm.get("breaking") or []}
    devp = [p for p in sc["prs"] if p["num"] and p["num"] not in sc["in_tag"]][::-1]   # oldest first
    lab = pr_labels([p["num"] for p in devp], snap_gh)
    is_test = lambda f: f.startswith(("tests/", "examples/")) or "/tests/" in f
    prs = []
    for i, p in enumerate(devp):
        files = p["files"]
        src = [f for f in files if not is_test(f) and not f.startswith("docs/") and not f.endswith((".md", ".rst"))]
        ft = pr_feature(files)
        x = cands.get(p["num"], {})
        lb = lab.get(p["num"])
        prs.append({
            "i": i, "num": p["num"], "sha": p["sha"], "at": p["at"][:16].replace("T", " "), "author": p["author"], "title": p["title"],
            "type": ptype(p["title"]), "risk": risk(files),
            "area": ft["prim"], "stage": ft["stage"], "klass": ft["klass"], "cpu_tiers": ft["cpu"]["tiers"], "gpu_tiers": ft["gpu"]["tiers"],
            "a_src": dict(Counter(a for a in map(src_area, src) if a)),
            "a_test": dict(Counter(a for a in map(src_area, [f for f in files if is_test(f)]) if a)),
            "breaking": p["num"] in breaking,
            "notes": x.get("notes") or [], "why": x.get("why"),
            "mp_ci": None if lb is None else ("skip" if "skip expensive ci" in lb and "force-ci" not in lb else "ran"),
        })
    # evidence for each PR: its newest k3-multiprocess-test build in the entity index (PR CI, not dev); decision per item from decisions.py
    import decisions as DEC
    ev = mp_evidence()
    for p in prs:
        p["mp_ev"] = ev.get(p["num"])
    by_num = {p["num"]: p for p in prs}
    for it in items:
        missing = [n for n in it["prs"] if n not in by_num]
        d = DEC.scope_item([by_num[n] for n in it["prs"] if n in by_num], missing)
        it["dec"] = dict(verb=d["verb"], short=d["short"])
    return {"items": items, "prs": prs, "stable": coming.get("stable"), "tag_sha": sc.get("tag_sha"), "head": sc.get("head"), "head_at": sc.get("head_at"),
            "roadmap": {"rel": (rm.get("src") or {}).get("rel"), "mtime": (rm.get("src") or {}).get("mtime")},
            "prep_rel": os.path.relpath(prep_path, str(ws)).replace("\\", "/") if prep_path and os.path.exists(prep_path) else None,
            "prep": prep_rows(prep_path), "cp": critical_path_model(ws)}
