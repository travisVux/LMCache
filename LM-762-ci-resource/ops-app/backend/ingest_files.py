"""Backfill the database from the JSON files the old page already collects.

Safe to run again: every table is keyed by its natural id, so rows are updated, not duplicated.
Run:  python -X utf8 ingest_files.py
"""
import json
import re
import sys
from pathlib import Path

from config import OLD, RELEASE_DIR, WF_NIGHTLY, WF_PUBLISH, parse_tag
from db import connect, ensure_release, new_snapshot, prune_untagged, upsert


def load(p):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def iso(s):
    """'2026-11-15 06:05' or '...Z' -> UTC ISO with Z (seconds)."""
    if not s:
        return None
    s = str(s).replace(" ", "T")
    s = re.sub(r"\.\d+", "", s)
    if len(s) == 16:
        s += ":00"
    return s if s.endswith("Z") or "+" in s else s + "Z"


# ───────────── GitHub runs / jobs ─────────────
def put_run(con, r, snap, workflow_id=None):
    tag = r.get("head_branch")
    p = parse_tag(tag)
    rel = tag if p and not p["plat"] else None
    if rel:
        ensure_release(con, rel, snap)
    wid = workflow_id or r.get("workflow_id")
    if wid:
        role = {WF_PUBLISH: "publish", WF_NIGHTLY: "nightly"}.get(wid)
        upsert(con, "workflow", dict(id=wid, name=r.get("name") or "?", role=role), ["id"], keep=("role",))
    upsert(con, "wf_run", dict(
        run_id=r["id"], workflow_id=wid, workflow=r.get("name"), event=r.get("event"), head_branch=tag,
        head_sha=r.get("head_sha"), release_tag=rel, status=r.get("status"), conclusion=r.get("conclusion"),
        attempt=r.get("run_attempt"), title=r.get("display_title"), created_at=iso(r.get("created_at")),
        updated_at=iso(r.get("updated_at")), url=r.get("html_url"), snapshot_id=snap),
        ["run_id"], keep=("workflow_id", "workflow", "head_sha", "title", "updated_at"))


def put_job(con, run_id, j, snap):
    jid = j.get("id") or int(str(j["html_url"]).rstrip("/").split("/")[-1])
    upsert(con, "wf_job", dict(
        job_id=jid, run_id=int(run_id), name=j["name"], status=j.get("status"), conclusion=j.get("conclusion"),
        started_at=iso(j.get("started_at")), completed_at=iso(j.get("completed_at")), url=j.get("html_url"),
        snapshot_id=snap), ["job_id"])


# ───────────── Buildkite ─────────────
def slug_of(b):
    pl = b.get("pipeline")
    if isinstance(pl, dict) and pl.get("slug"):
        return pl["slug"]
    m = re.search(r"buildkite\.com/[^/]+/([^/]+)/builds", b.get("web_url") or "")
    return m.group(1) if m else None


def put_build(con, slug, b, snap):
    upsert(con, "bk_pipeline", dict(slug=slug, name=slug, hw="GPU" if slug.startswith("k3") else None), ["slug"],
           keep=("name", "hw"))
    pr = b.get("pr")
    if pr is None and isinstance(b.get("pull_request"), dict):
        pr = b["pull_request"].get("id")
    upsert(con, "bk_build", dict(
        pipeline=slug, number=int(b["number"]), state=b.get("state"), branch=b.get("branch"),
        commit_sha=b.get("commit"), source=b.get("source"), pr=int(pr) if pr and str(pr).isdigit() else None,
        created_at=iso(b.get("created_at")), started_at=iso(b.get("started_at")),
        finished_at=iso(b.get("finished_at")), wait_min=b.get("wait_min"),
        url=b.get("web_url") or f"https://buildkite.com/lmcache/{slug}/builds/{b['number']}", snapshot_id=snap),
        ["pipeline", "number"], keep=("commit_sha", "source", "pr", "wait_min", "started_at", "finished_at"))


# ───────────── sources ─────────────
def from_observe_snapshot(con):
    S = load(OLD / "observe_snapshot.json")
    if not S:
        return 0
    snap = new_snapshot(con, "file:observe_snapshot.json", iso(S.get("at")))
    G, B = S.get("gh") or {}, S.get("bk") or {}
    n = 0
    for r in G.get("releases") or []:
        if r.get("draft"):
            continue
        p = parse_tag(r["tag_name"])
        if not p:
            continue
        if not p["plat"]:
            ensure_release(con, r["tag_name"], snap, tagged_at=iso(r.get("created_at")),
                           published_at=iso(r.get("published_at")), prerelease=int(bool(r.get("prerelease"))),
                           url=r.get("html_url"))
        n += 1
    for r in (G.get("runs_dev") or []) + (G.get("publish_dev") or []):
        put_run(con, r, snap, WF_PUBLISH if r in (G.get("publish_dev") or []) else None)
    for r in G.get("nightly_runs") or []:
        put_run(con, r, snap, WF_NIGHTLY)
    for runs in (G.get("publish_tags") or {}).values():
        for r in runs or []:
            put_run(con, r, snap, WF_PUBLISH)
    for rid, jobs in (G.get("publish_jobs") or {}).items():
        if con.execute("SELECT 1 FROM wf_run WHERE run_id=?", (int(rid),)).fetchone():
            for j in jobs or []:
                put_job(con, rid, j, snap)
    for m in G.get("merged") or []:
        upsert(con, "pr", dict(number=m["number"], title=m.get("title"), author=(m.get("user") or {}).get("login"),
                               merged_at=iso((m.get("pull_request") or {}).get("merged_at")), state="merged",
                               url=m.get("html_url"), snapshot_id=snap), ["number"],
               keep=("title", "author", "created_at", "url"))
        for lb in m.get("labels") or []:
            upsert(con, "pr_label", dict(pr=m["number"], label=lb["name"]), ["pr", "label"])
    for p in ((G.get("prs_gql") or {}).get("nodes") or []):
        upsert(con, "pr", dict(number=p["number"], title=p.get("title"), author=(p.get("author") or {}).get("login"),
                               created_at=iso(p.get("createdAt")), state="open", draft=int(bool(p.get("isDraft"))),
                               url=p.get("url"), snapshot_id=snap), ["number"])
        ci = None
        cm = ((p.get("commits") or {}).get("nodes") or [{}])
        if cm and cm[0]:
            ci = ((cm[0].get("commit") or {}).get("statusCheckRollup") or {}).get("state")
        upsert(con, "pr_state", dict(snapshot_id=snap, pr=p["number"], review=p.get("reviewDecision"),
                                     mergeable=p.get("mergeable"), ci_state=ci), ["snapshot_id", "pr"])
        for lb in ((p.get("labels") or {}).get("nodes") or []):
            upsert(con, "pr_label", dict(pr=p["number"], label=lb["name"]), ["pr", "label"])
        if "assignees" in p:   # field exists since 2026-11-15; replace, so an unassigned PR loses its old owner
            con.execute("DELETE FROM pr_assignee WHERE pr=?", (p["number"],))
            for a_ in ((p.get("assignees") or {}).get("nodes") or []):
                upsert(con, "pr_assignee", dict(pr=p["number"], login=a_["login"]), ["pr", "login"])
    for pl in B.get("pipelines") or []:
        upsert(con, "bk_pipeline", dict(slug=pl["slug"], name=pl.get("name")), ["slug"], keep=("hw",))
    for b in B.get("dev_builds") or []:
        s = slug_of(b)
        if s:
            put_build(con, s, b, snap)
    for s, bs in (B.get("recent") or {}).items():
        for b in bs or []:
            put_build(con, s, b, snap)
    return n


def iso_mtime(t):
    import datetime as _dt
    return _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_report_cache(con):
    rc = OLD / "report_cache"
    # review 2.4: the newest file time is the collection time, so re-reading unchanged files reuses the snapshot
    mt = max((p.stat().st_mtime for p in rc.glob("*.json")), default=None)
    snap = new_snapshot(con, "file:report_cache/", iso_mtime(mt) if mt else None)
    n = 0
    for f, wid in (("publish.json", WF_PUBLISH), ("nightly.json", WF_NIGHTLY)):
        for r in load(rc / f) or []:
            r.setdefault("name", "Build and Publish to PyPI" if wid == WF_PUBLISH else "nightly")
            put_run(con, r, snap, wid)
            n += 1
    for f in rc.glob("dev_*.json"):
        slug = f.stem[4:]
        for b in load(f) or []:
            put_build(con, slug, b, snap)
            n += 1
    for b in load(rc / "k3u_pr.json") or []:
        put_build(con, "k3-unit-tests", b, snap)
        n += 1
    for p in load(rc / "merged.json") or []:
        upsert(con, "pr", dict(number=p["n"], created_at=iso(p.get("c")), merged_at=iso(p.get("m")), state="merged",
                               author=p.get("u"), snapshot_id=snap), ["number"],
               keep=("title", "author", "url", "created_at"))
    for p in load(rc / "opened.json") or []:
        upsert(con, "pr", dict(number=p["n"], created_at=iso(p.get("c")), author=p.get("u"),
                               state={"closed": "closed", "open": "open"}.get(p.get("s"), p.get("s")),
                               snapshot_id=snap), ["number"],
               keep=("title", "author", "url", "created_at", "merged_at"))
        # a 'closed' in opened.json may be a merge: never downgrade a merged PR
        con.execute("UPDATE pr SET state='merged' WHERE number=? AND merged_at IS NOT NULL", (p["n"],))
    return n


def flatten(prefix, v, out):
    if isinstance(v, dict):
        for k, x in v.items():
            flatten(f"{prefix}.{k}" if prefix else k, x, out)
    elif isinstance(v, bool):
        out[prefix] = float(v)
    elif isinstance(v, (int, float)):
        out[prefix] = float(v)
    elif isinstance(v, str) and prefix.endswith((".last", "nightly", ".publish")):
        out[prefix + ".ok"] = 1.0 if v in ("passed", "success") else 0.0


def from_daily(con):
    n = 0
    for d, src in ((OLD / "observe_history", "observe_history"), (OLD / "ops_hist", "ops_hist")):
        for f in sorted(d.glob("20*.json")):
            j = load(f)
            day = j.get("day") or j.get("date") or f.stem
            out = {}
            for k, v in j.items():
                if k in ("at", "day", "date"):
                    continue
                flatten(k, v, out)
            for k, v in out.items():
                upsert(con, "kpi_daily", dict(day=day, key=f"{src}.{k}", value=v, source=src), ["day", "key"])
                n += 1
    return n


def from_entities(con):
    E = load(OLD / "entities.json")
    if not E:
        return 0
    snap = new_snapshot(con, "file:entities.json", iso(E.get("snap_at")))
    N = E["nodes"]
    for k, v in N.items():
        if v["kind"] == "release":
            if v.get("state") != "next":          # 'next' is a plan, not a tag
                ensure_release(con, v["id"], snap, url=v.get("url"), tagged_at=iso(v.get("at")))
        elif v["kind"] == "feature":
            upsert(con, "feature", dict(id=v["id"], title=v.get("title"), stage=v.get("stage"), klass=v.get("klass")),
                   ["id"])
        elif v["kind"] == "pr":
            upsert(con, "pr", dict(number=int(v["id"]), title=v.get("title"), author=v.get("author"), url=v.get("url"),
                                   state=v.get("state"), snapshot_id=snap), ["number"],
                   keep=("title", "author", "url", "state"))
    n = 0
    for e in E["edges"]:
        fk, fid = e["from"].split(":", 1)
        tk, tid = e["to"].split(":", 1)
        if e["rel"] == "contains" and fk == "release" and parse_tag(fid) and N.get(e["from"], {}).get("state") != "next":
            ensure_release(con, fid, snap)
            con.execute("INSERT OR IGNORE INTO pr(number) VALUES (?)", (int(tid),))
            upsert(con, "pr_release", dict(pr=int(tid), release_tag=fid), ["pr", "release_tag"])
            n += 1
        elif e["rel"] == "changes" and fk == "pr" and tk == "feature" and e["to"] in N:
            con.execute("INSERT OR IGNORE INTO pr(number) VALUES (?)", (int(fid),))
            upsert(con, "pr_feature", dict(pr=int(fid), feature=tid, strength=e.get("strength")), ["pr", "feature"])
            n += 1
    return n


ROW_RE = re.compile(r"^\|\s*(D\d|C\d)\s*\|(.+)\|\s*$")


def from_release_prep(con, line):
    f = RELEASE_DIR(line) / "RELEASE_PREP.md"
    if not f.exists():
        return 0
    snap = new_snapshot(con, f"file:release-{line}/RELEASE_PREP.md", iso_mtime(f.stat().st_mtime))
    a, b, c = (int(x) for x in line.split("."))
    upsert(con, "release_line", dict(line=line, major=a, minor=b, patch=c), ["line"])
    n = 0
    for raw in f.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(raw)
        if not m:
            continue
        code, cells = m.group(1), [x.strip() for x in m.group(2).split("|")]
        if code.startswith("D"):
            q, opts, inp = (cells + ["", "", ""])[:3]
            # A doc row is 'decided' only when it says so; the model adds evidence-based hints on top.
            status = "decided" if re.search(r"\bdecided\b|✅", inp, re.I) else "open"
            upsert(con, "decision", dict(id=f"{line}:{code}", line=line, code=code, question=q, options=opts,
                                         status=status, source=f.name, snapshot_id=snap), ["id"],
                   keep=("choice", "decided_at"))
        else:
            prob, fix, state = (cells + ["", "", ""])[:3]
            status = "fixed" if re.search(r"\b(merged|done|fixed)\b", state, re.I) and "not" not in state.lower() else "open"
            upsert(con, "blocker", dict(id=f"{line}:{code}", line=line, code=code, kind="carryover", title=prob,
                                        status=status, fix_ref=fix, source=f.name, snapshot_id=snap), ["id"],
                   keep=("opened_at", "closed_at", "evidence"))
        n += 1
    return n


VERDICT = {"shipped_fail": "partial", "blocked": "bug_after", "no_data": "no_data", "shipped": "shipped"}


def from_today(con):
    T = load(OLD / "today.json")
    if not T:
        return 0
    snap = new_snapshot(con, "file:today.json", iso(T.get("snap_at")), note="old page verdicts (rule/agent)")
    nxt = (T.get("next") or "").lstrip("v")
    n = 0
    for r in T.get("releases") or []:
        if ensure_release(con, r["tag"], snap):
            upsert(con, "release_verdict", dict(snapshot_id=snap, release_tag=r["tag"],
                                                verdict="old:" + r["verb"], reason=(r.get("short") or [""])[0]),
                   ["snapshot_id", "release_tag"])
            n += 1
            # bugs the Trace Agent found in this release (kept per release, not per line)
            ln = parse_tag(r["tag"])["line"]
            for bl in r.get("blockers") or []:
                fixed = bl.get("fix_status") == "merged"
                upsert(con, "blocker", dict(
                    id=f"{ln}:bug#{bl['num']}@{r['tag']}", line=ln, code=f"#{bl['num']}", kind="pr",
                    title=f"bug found in {r['tag']} ({bl.get('cls')})", status="fixed" if fixed else "open",
                    fix_ref=f"#{bl['fix_pr']}" if bl.get("fix_pr") else None,
                    evidence=f"https://github.com/LMCache/LMCache/pull/{bl['num']}",
                    source="today.json (Trace Agent)", snapshot_id=snap), ["id"])
    if nxt:
        a, b, c = (int(x) for x in nxt.split("."))
        upsert(con, "release_line", dict(line=nxt, major=a, minor=b, patch=c), ["line"])
        for k in T.get("known_red") or []:
            upsert(con, "blocker", dict(id=f"{nxt}:ci:{k['slug']}", line=nxt, code=k["slug"], kind="ci",
                                        title=f"dev red on {k['slug']} (#{k['number']})", status="open",
                                        evidence=k.get("url"), opened_at=iso(k.get("at")), source="today.json",
                                        snapshot_id=snap), ["id"], keep=("opened_at",))
        for r in T.get("rows") or []:
            if r.get("verb") == "block" and r.get("label", "").startswith("#"):
                num = r["label"][1:]
                upsert(con, "blocker", dict(id=f"{nxt}:pr#{num}", line=nxt, code=f"#{num}", kind="pr",
                                            title=r.get("title") or "", status="open",
                                            evidence=f"https://github.com/LMCache/LMCache/pull/{num}",
                                            source="today.json (Trace Agent)", snapshot_id=snap), ["id"])
    return n


def main():
    con = connect()
    steps = [("observe_snapshot", from_observe_snapshot), ("report_cache", from_report_cache),
             ("daily kpis", from_daily), ("entities", from_entities), ("today", from_today)]
    for name, fn in steps:
        print(f"{name:18s} {fn(con)}")
        con.commit()
    for line in sorted({r["line"] for r in con.execute("SELECT line FROM release_line")}):
        k = from_release_prep(con, line)
        if k:
            print(f"release-{line} prep   {k}")
    con.commit()
    print(f"pruned untagged   {prune_untagged(con)}")
    for t in ("release", "wf_run", "wf_job", "bk_build", "pr", "pr_release", "pr_feature", "kpi_daily",
              "decision", "blocker", "release_verdict"):
        print(f"  {t:16s} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")


if __name__ == "__main__":
    sys.exit(main())
