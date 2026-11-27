"""Turn database facts into the release-manager view. Pure reads, except record_verdicts().

Verdicts (one word per release, from facts only):
  shipped        every expected artifact is present and correct
  partial        some expected artifacts are missing or wrong
  publish_failed nothing expected was shipped
  in_progress    a publish run for the tag is still running
  no_data        we never checked the registries for this tag
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from config import ARTIFACT_DECISION, DEV_GATE_PIPELINES, GATING_ARTIFACTS, OLD, PLATFORM_JOB, RELEASE_DIR, REPO, WATCH_DAYS, parse_tag

VERDICT_TEXT = {
    "shipped": ("Shipped", "Đã phát hành đủ"),
    "partial": ("Missing artifacts", "Thiếu artifact"),
    "publish_failed": ("Not shipped", "Chưa phát hành"),
    "in_progress": ("Publishing", "Đang publish"),
    "no_data": ("Not checked", "Chưa kiểm tra"),
}


def rows(con, sql, *a):
    return [dict(r) for r in con.execute(sql, a).fetchall()]


def one(con, sql, *a):
    r = con.execute(sql, a).fetchone()
    return dict(r) if r else None


# ───────────── per release ─────────────
def matrix(con, tag):
    return rows(con, "SELECT * FROM v_artifact_matrix WHERE tag=? ORDER BY ord", tag)


def publish_runs(con, tag):
    runs = rows(con, """SELECT run_id, event, status, conclusion, attempt, created_at, updated_at, url
                        FROM wf_run WHERE release_tag=? AND workflow_id=157910139 ORDER BY created_at DESC""", tag)
    latest = {}
    for r in runs:                        # newest run per event
        latest.setdefault(r["event"], r)
    out = []
    for r in latest.values():
        r["failed_jobs"] = rows(con, """SELECT job_id, name, url, error_line FROM wf_job
                                        WHERE run_id=? AND conclusion='failure' ORDER BY started_at""", r["run_id"])
        r["skipped"] = one(con, "SELECT COUNT(*) n FROM wf_job WHERE run_id=? AND conclusion='skipped'", r["run_id"])["n"]
        r["jobs"] = one(con, "SELECT COUNT(*) n FROM wf_job WHERE run_id=?", r["run_id"])["n"]
        out.append(r)
    return out


def verdict(con, tag):
    m = [x for x in matrix(con, tag) if x["expected"]]
    runs = publish_runs(con, tag)
    checked = [x for x in m if x["present"] is not None]
    missing = [x for x in checked if not x["ok"]]
    if any(r["status"] in ("in_progress", "queued", "waiting") for r in runs):
        v = "in_progress"
    elif not checked:
        v = "no_data"
    elif not missing:
        v = "shipped"
    elif len(missing) == len(checked):
        v = "publish_failed"
    else:
        v = "partial"
    reason = ", ".join(x["label"] for x in missing)
    return dict(verdict=v, missing=[dict(code=x["code"], label=x["label"], detail=x["detail"]) for x in missing],
                n_expected=len(m), n_ok=len(checked) - len(missing), reason=reason,
                publish_red=any(r["conclusion"] == "failure" for r in runs), runs=runs)


def record_verdicts(con, snap):
    for (tag,) in con.execute("SELECT tag FROM release").fetchall():
        v = verdict(con, tag)
        if v["verdict"] != "no_data":
            con.execute("INSERT OR REPLACE INTO release_verdict(snapshot_id, release_tag, verdict, reason) VALUES (?,?,?,?)",
                        (snap, tag, v["verdict"], v["reason"]))


# ───────────── release line state ─────────────
def releases(con, limit=12):
    rs = rows(con, """SELECT r.*, (SELECT COUNT(*) FROM pr_release p WHERE p.release_tag=r.tag) n_prs
                      FROM release r ORDER BY COALESCE(published_at, tagged_at) DESC, sort_key DESC LIMIT ?""", limit)
    for r in rs:
        v = verdict(con, r["tag"])
        r.update({k: v[k] for k in ("verdict", "missing", "n_expected", "n_ok", "publish_red")})
        r["publish"] = [dict(event=x["event"], conclusion=x["conclusion"], status=x["status"], url=x["url"])
                        for x in v["runs"]]
        r["bugs"] = rows(con, "SELECT code, status, fix_ref, evidence FROM blocker WHERE kind='pr' AND title LIKE ?",
                         f"%found in {r['tag']} (%")   # ' (' stops v0.5.7 matching v0.5.7rc3
    return rs


def dev_gates(con):
    out = []
    for slug in DEV_GATE_PIPELINES:
        bs = rows(con, """SELECT number, state, created_at, url FROM bk_build
                          WHERE pipeline=? AND branch='dev' AND state IN ('passed','failed')
                          ORDER BY created_at DESC LIMIT 10""", slug)
        if not bs:
            continue
        last_pass = one(con, """SELECT created_at FROM bk_build WHERE pipeline=? AND branch='dev' AND state='passed'
                                ORDER BY created_at DESC LIMIT 1""", slug)
        out.append(dict(slug=slug, last=bs[0], last_pass=(last_pass or {}).get("created_at"),
                        recent=[b["state"] for b in reversed(bs)]))
    return out


def decision_hints(con, line, latest):
    """Facts that suggest a decision was already made in practice. Shown next to the doc status, never replace it."""
    hints = {}
    a, b, c = (int(x) for x in line.split("."))
    prev = f"{a}.{b}.{c - 1}" if c else None
    post = one(con, "SELECT tag, published_at FROM release WHERE line=? AND kind='post' ORDER BY seq DESC LIMIT 1", prev)
    if post:
        hints["D1"] = dict(en=f"{post['tag']} was published {post['published_at'][:10]}: the fix shipped as a .post release.",
                           vi=f"{post['tag']} đã phát hành {post['published_at'][:10]}: bản sửa đã ra dưới dạng .post.")
    err = one(con, """SELECT j.error_line, j.url FROM wf_job j JOIN wf_run r ON r.run_id=j.run_id
                      WHERE r.release_tag=? AND j.error_line LIKE '%torch 2.1%' LIMIT 1""", latest) if latest else None
    if err:
        m = re.search(r"torch \d+\.\d+(\.\d+)?", err["error_line"])
        hints["D2"] = dict(en=f"{latest} already builds with {m.group(0)} (publish job error).",
                           vi=f"{latest} đã build với {m.group(0)} (lỗi job publish).", url=err["url"])
    if latest and one(con, "SELECT 1 FROM pr_release WHERE pr=6254 AND release_tag=?", latest):
        hints["D3"] = dict(en=f"#6254 is already in {latest}.", vi=f"#6254 đã nằm trong {latest}.",
                           url="https://github.com/LMCache/LMCache/pull/6254")
    return hints


def blockers(con, line, latest):
    out = rows(con, """SELECT id, code, kind, title, status, fix_ref, evidence, opened_at, source FROM blocker
                       WHERE line=? AND status='open' AND title NOT LIKE '%found in%' ORDER BY kind, code""", line)
    if latest:
        v = verdict(con, latest)
        for x in v["missing"]:
            out.append(dict(id=f"{line}:artifact:{x['code']}", code=x["label"], kind="artifact",
                            title=f"{latest}: {x['label']} — {x['detail'] or 'missing'}", status="open",
                            evidence=next((m["url"] for m in matrix(con, latest) if m["code"] == x["code"]), None),
                            source="registries"))
        for r in v["runs"]:
            for j in r["failed_jobs"]:
                out.append(dict(id=f"{line}:publish:{j['job_id']}", code=j["name"], kind="publish",
                                title=f"{latest} publish ({r['event']}): {j['name']}", detail=j["error_line"],
                                status="open", evidence=j["url"], source="publish.yml"))
        cli = next((m for m in matrix(con, latest) if m["code"] == "pypi:lmcache-cli"), None)
        for b in out:
            if b["code"] == "C2" and cli and not cli["ok"]:
                b["fact"] = f"PyPI lmcache-cli for {latest}: {cli['detail']}"
    for g in dev_gates(con):
        if g["last"]["state"] == "failed":
            key = f"{line}:ci:{g['slug']}"
            if not any(b["id"] == key for b in out):
                out.append(dict(id=key, code=g["slug"], kind="ci", title=f"dev red on {g['slug']}", status="open",
                                evidence=g["last"]["url"], source="Buildkite"))
            for b in out:
                if b["id"] == key:
                    b["fact"] = f"last dev build #{g['last']['number']} failed; last pass {(g['last_pass'] or '—')[:10]}"
    # ci blockers from older snapshots that are green again are no longer blockers
    green = {g["slug"] for g in dev_gates(con) if g["last"]["state"] == "passed"}
    out = [b for b in out if not (b["kind"] == "ci" and b["code"] in green)]
    order = {"publish": 0, "artifact": 1, "ci": 2, "pr": 3, "carryover": 4}
    return sorted(out, key=lambda b: order.get(b["kind"], 9))


def overview(con):
    rel = rows(con, "SELECT * FROM release ORDER BY sort_key DESC")
    latest = rel[0] if rel else None
    stable = next((r for r in sorted(rel, key=lambda r: r["published_at"] or "", reverse=True)
                   if r["kind"] in ("final", "post")), None)
    line = latest["line"] if latest else None
    if latest and latest["kind"] == "rc":
        phase = dict(en=f"{latest['tag']} is out → next: rc{latest['seq'] + 1} or v{line}",
                     vi=f"Đã ra {latest['tag']} → tiếp theo: rc{latest['seq'] + 1} hoặc v{line}")
    else:
        phase = dict(en="Stable out → plan the next line", vi="Đã ra stable → lên kế hoạch bản tiếp theo")
    hints = decision_hints(con, line, latest["tag"]) if latest else {}
    decs = rows(con, "SELECT * FROM decision WHERE line=? ORDER BY code", line)
    for d in decs:
        d["hint"] = hints.get(d["code"])
    bl = blockers(con, line, latest["tag"] if latest else None)
    snaps = rows(con, "SELECT source, MAX(taken_at) taken_at FROM snapshot GROUP BY source ORDER BY taken_at DESC")
    enrich_blockers(con, bl)
    bl = merge_publish_blockers(bl)
    ages = source_ages(con, line)
    stale_src = {a["key"] for a in ages if a["stale"]}
    open_dec = {d["code"] for d in decs if (d.get("status") or "open") == "open" and not d.get("hint")}
    rel_tags = {r["tag"]: r for r in rel}
    rec = recorded_decisions(con)
    for b in bl:
        tv = title_vi(b.get("title"))
        if tv:
            b["title_vi"] = tv   # expert review R2: evidence older than 48 h cannot decide the verdict on its own
        b["stale"] = b.get("src") in stale_src
        apply_policy(b, open_dec, line, rel_tags)
        r = rec.get(b["id"])
        if r:   # round 2 A4 / B5 / D-1: a recorded decision; known issue / accepted gap no longer gates this line
            b["decided"] = dict(action=r["action"], by=r["decided_by"], at=r["decided_at"], reason=r["reason"])
            if r["action"] in ("known_issue", "accept"):
                b.update(gating=False, policy="decided")
    deciding = [b for b in bl if not b["stale"] and b.get("gating", True)]
    status = "red" if any(b["kind"] in ("publish", "ci", "pr") for b in deciding) else ("amber" if deciding else "green")
    if status == "green" and any(b["stale"] and b["kind"] in ("ci", "pr") for b in bl):
        status = "unverified"
    # what decides first: gating and fresh, then gating but old, then known issues / waiting on a decision
    bl.sort(key=lambda b: (not b.get("gating", True), b["stale"]))
    shipped = bool(latest and stable and latest["tag"] == stable["tag"] and latest["kind"] in ("final", "post"))
    watch = None
    if shipped and stable["published_at"]:
        t0 = datetime.fromisoformat(stable["published_at"].replace("Z", "+00:00"))
        until = t0.timestamp() + WATCH_DAYS * 86400
        nxt = ".".join(line.split(".")[:-1] + [str(int(line.split(".")[-1]) + 1)]) if line and line.split(".")[-1].isdigit() else None
        watch = dict(until=datetime.fromtimestamp(until, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     over=datetime.now(timezone.utc).timestamp() > until, next_line=nxt,
                     next_prep=bool(nxt and (RELEASE_DIR(nxt) / "RELEASE_PREP.md").is_file()))
    return dict(ages=ages, good=good_target(con, stable and stable["tag"]), ready=ready_queue(con), shipped=shipped, watch=watch,
        policy=dict(gating=sorted(GATING_ARTIFACTS), decision=ARTIFACT_DECISION, platform=PLATFORM_JOB, watch_days=WATCH_DAYS),
        stable=stable and dict(tag=stable["tag"], at=stable["published_at"], url=stable["url"]),
        latest=latest and dict(tag=latest["tag"], at=latest["published_at"], kind=latest["kind"], url=latest["url"]),
        line=line, phase=phase, status=status, decisions=decs, blockers=bl,
        releases=releases(con), focus=list(dict.fromkeys(t for t in (latest and latest["tag"], stable and stable["tag"]) if t)),
        matrix={t: matrix(con, t) for t in {latest and latest["tag"], stable and stable["tag"]} if t},
        dev_gates=dev_gates(con), weekly=weekly_badge(con), sources=snaps, verdict_text=VERDICT_TEXT)


# ───────────── weekly full build (GitHub Actions weekly_full_build.yml; collect_weekly.py) ─────────────
WEEKLY_DEVICES = ["cuda", "xpu", "amd", "rbln"]
WEEKLY_WF_URL = f"https://github.com/{REPO}/actions/workflows/weekly_full_build.yml"


def weekly(con, weeks=12, limit=30):
    """Runs of the last `weeks` weeks (newest first), each with device lanes -> Buildkite pipelines -> problems."""
    meta = {r["key"]: r["value"] for r in rows(con, "SELECT key, value FROM weekly_gha_meta")}
    runs = rows(con, """SELECT * FROM weekly_gha_run WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%SZ','now',?)
                        ORDER BY created_at DESC LIMIT ?""", f"-{weeks * 7} day", limit)
    ids = [r["run_id"] for r in runs]
    q = ",".join("?" * len(ids)) or "NULL"
    lanes, pipes, probs = {}, {}, {}
    for x in rows(con, f"SELECT * FROM weekly_gha_problem WHERE run_id IN ({q}) ORDER BY run_id, device, slug, idx", *ids):
        probs.setdefault((x["run_id"], x["device"], x["slug"]), []).append(
            {k: x[k] for k in ("kind", "label", "state", "exit_status", "url", "job_id", "detail")})
    for x in rows(con, f"SELECT * FROM weekly_gha_pipeline WHERE run_id IN ({q}) ORDER BY run_id, device, ord", *ids):
        pipes.setdefault((x["run_id"], x["device"]), []).append(dict(
            slug=x["slug"], name=x["name"], number=x["number"], url=x["url"], state=x["state"],
            retried=json.loads(x["retried"] or "[]"), problems=probs.get((x["run_id"], x["device"], x["slug"]), [])))
    for x in rows(con, f"SELECT * FROM weekly_gha_lane WHERE run_id IN ({q})", *ids):
        lanes.setdefault(x["run_id"], {})[x["device"]] = dict(
            state=x["state"], conclusion=x["conclusion"], job_url=x["url"], job_id=x["job_id"], started=x["started_at"],
            completed=x["completed_at"], artifact=x["artifact_name"], report=bool(x["report"]), timed_out=bool(x["timed_out"]),
            commit=x["commit_sha"], branch=x["branch"], earlier_reports=x["earlier_reports"] or 0, earlier_failed=x["earlier_failed"] or 0,
            log_notes=json.loads(x["log_notes"] or "[]"), pipelines=pipes.get((x["run_id"], x["device"]), []))
    out = []
    for r in runs:
        out.append(dict(run_id=r["run_id"], number=r["run_number"], attempt=r["attempt"], event=r["event"], verdict=r["verdict"],
                        url=r["url"], created_at=r["created_at"], first_job_at=r["first_job_at"], last_job_at=r["last_job_at"],
                        head_sha=r["head_sha"], head_branch=r["head_branch"], prepare=r["prepare_conclusion"],
                        lanes=lanes.get(r["run_id"], {})))
    cron = meta.get("cron") or "0 8 * * 0"
    return dict(runs=out, devices=WEEKLY_DEVICES, weeks=weeks, collected_at=meta.get("collected_at"), workflow_url=WEEKLY_WF_URL,
                repo=REPO, schedule=dict(text=f"Sun 08:00 UTC (cron {cron})" if cron == "0 8 * * 0" else f"cron {cron}", cron=cron,
                                         enabled=None if "schedule_enabled" not in meta else meta["schedule_enabled"] == "1"))


def ci_impact(con):
    """CI impact by improvement version (collect_ci_impact.py, ci_versions.json): versions v0 (baseline) .. vN,
    metric definitions and one value per metric x version (value, N, state, change vs v0 and vs the previous version).
    None before the first collect."""
    try:
        vs = rows(con, "SELECT * FROM ci_impact_version ORDER BY ord")
        ds = rows(con, "SELECT * FROM ci_impact_def ORDER BY ord")
        vals = rows(con, "SELECT * FROM ci_impact_value")
        meta = {r["key"]: json.loads(r["value"]) for r in rows(con, "SELECT key, value FROM ci_impact_meta")}
    except Exception:  # noqa: BLE001  (tables not created yet: old database)
        return None
    if not vs or not ds:
        return None
    for v in vs:
        v["title"] = [v.pop("title_en"), v.pop("title_vi")]
        v["prs"] = json.loads(v["prs"] or "[]")
    by = {}
    for x in vals:
        try:
            x["note"] = json.loads(x["note"]) if x["note"] else None   # [en, vi]
        except ValueError:
            x["note"] = [x["note"], x["note"]]
        by.setdefault(x.pop("key"), {})[x.pop("version")] = x
    for d in ds:
        d["label"] = [d.pop("label_en"), d.pop("label_vi")]
        d["after_only"] = bool(d["after_only"])
        d["values"] = by.get(d["key"], {})
    return dict(meta, versions=vs, metrics=ds)


def weekly_badge(con):
    """One line for the Today banner: the newest weekly run that has a verdict (or is running)."""
    r = one(con, """SELECT run_id, run_number, verdict, created_at, url FROM weekly_gha_run
                    WHERE verdict != 'cancelled' ORDER BY created_at DESC LIMIT 1""")
    last = one(con, "SELECT MAX(created_at) at FROM weekly_gha_run") or {}
    return dict(latest=r, last_run_at=last.get("at"))


# ───────────── history (analysis) ─────────────
def history(con):
    cyc = rows(con, "SELECT * FROM v_release_cycle ORDER BY line DESC LIMIT 8")
    nightly = rows(con, """SELECT substr(created_at,1,10) day, conclusion, url FROM wf_run
                           WHERE workflow_id=164357863 AND event IN ('schedule','workflow_dispatch')
                           ORDER BY created_at DESC LIMIT 30""")
    pub = rows(con, "SELECT * FROM v_publish_weekly ORDER BY week DESC LIMIT 24")
    gates = rows(con, f"""SELECT * FROM v_dev_pipeline_daily WHERE pipeline IN ({','.join('?' * len(DEV_GATE_PIPELINES))})
                          AND day >= date('now','-30 day') ORDER BY day""", *DEV_GATE_PIPELINES)
    jobs = rows(con, "SELECT * FROM v_failing_jobs ORDER BY failures DESC LIMIT 10")
    kpi = rows(con, """SELECT day, key, value FROM kpi_daily WHERE key IN
                       ('observe_history.prs.open','observe_history.prs.merged_unreleased',
                        'observe_history.queue.k3-unit-tests.w90','observe_history.queue.k3-multiprocess-test.w90',
                        'ops_hist.tot.GPU_failed','ops_hist.tot.GPU_cancelled','ops_hist.tot.GPU_total')
                       ORDER BY day""")
    return dict(cycle=cyc, nightly=list(reversed(nightly)), publish_weekly=list(reversed(pub)), gates=gates,
                failing_jobs=jobs, kpi=kpi)   # weekly full build: its own tab (#obs/weekly), model.weekly()


def release_detail(con, tag):
    r = one(con, "SELECT * FROM release WHERE tag=?", tag)
    if not r or not parse_tag(tag):
        return None
    v = verdict(con, tag)
    r.update(v)
    r["matrix"] = matrix(con, tag)
    r["prs"] = rows(con, """SELECT p.number, p.title, p.author, p.merged_at, p.url,
                                   (SELECT group_concat(feature) FROM pr_feature f WHERE f.pr=p.number AND f.strength='strong') features
                            FROM pr_release x JOIN pr p ON p.number=x.pr WHERE x.release_tag=? ORDER BY p.number""", tag)
    r["verdict_history"] = rows(con, """SELECT s.taken_at, v.verdict, v.reason FROM release_verdict v
                                        JOIN snapshot s ON s.id=v.snapshot_id WHERE v.release_tag=? ORDER BY s.taken_at""", tag)
    return r


# ───────────── data age per source ─────────────
STALE_H = 48


def _jget(name, *path):
    try:
        d = json.loads((OLD / name).read_text(encoding="utf-8"))
        for k in path:
            d = d[k]
        return d
    except Exception:  # noqa: BLE001 - a missing input shows as unknown age
        return None


def _mtime(p):
    try:
        return datetime.fromtimestamp(os.path.getmtime(p), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        return None


def _age_h(s):
    if not s:
        return None
    s = str(s)
    if len(s) == 10:
        s += "T23:59:59Z"   # a date = end of that day
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - t).total_seconds() / 3600, 1)


def source_ages(con, line=None):
    """Every input the Release Desk mixes, with its age. stale = older than 48 h."""
    collect = one(con, "SELECT MAX(taken_at) t FROM snapshot WHERE source LIKE 'collect:%'") or {}
    line = line or (one(con, "SELECT line FROM release ORDER BY sort_key DESC LIMIT 1") or {}).get("line")
    out = [
        dict(key="ops_db", label="ops.db (registries, publish runs)", at=collect.get("t")),
        dict(key="observe_snapshot", label="observe_snapshot.json (PRs, dev builds)", at=_jget("observe_snapshot.json", "at")),
        dict(key="ops_ci_24h", label="ops_ci_24h.json (CI last 24 h)", at=_jget("ops_ci_24h.json", "at")),
        dict(key="trace_agent", label="Trace Agent", at=(_jget("ops_tabs.json", "ta_meta") or {}).get("updated")),
        dict(key="report1130", label="report1130.json (window end)", at=_jget("report1130.json", "until")),
        dict(key="release_prep", label=f"release-{line}/RELEASE_PREP.md", at=_prep_date(RELEASE_DIR(line) / "RELEASE_PREP.md") if line else None),
    ]
    for x in out:
        x["age_h"] = _age_h(x["at"])
        x["stale"] = x["age_h"] is not None and x["age_h"] > STALE_H
    return out


def _prep_date(p):
    """'Prepared YYYY-MM-DD' (or 'Updated …') inside the doc; the file time only when the doc names no date (R6)."""
    try:
        m = re.findall(r"^(?:Prepared|Updated|Last updated)[: ]+(\d{4}-\d{2}-\d{2})", p.read_text(encoding="utf-8"), re.M)
    except OSError:
        return None
    return (max(m) + "T00:00:00Z") if m else _mtime(p)


# ───────────── rollback target ─────────────
CORE = ("pypi:lmcache", "gh:main", "docker:vllm-openai")


def good_target(con, current=None):
    """$GOOD = newest final/post tag OLDER than the current stable whose core artifacts (wheel, GitHub release, main
    image) are present and correct: you roll back FROM the current stable, never to it (R4)."""
    for r in rows(con, "SELECT * FROM release WHERE kind IN ('final','post') ORDER BY COALESCE(published_at, tagged_at) DESC"):
        if current and r["tag"] == current:
            continue
        m = {x["code"]: x for x in matrix(con, r["tag"])}
        if all(m.get(c) and m[c]["ok"] for c in CORE):
            gaps = [x["label"] for x in m.values() if x["expected"] and x["present"] is not None and not x["ok"]]
            return dict(tag=r["tag"], at=r["published_at"], url=r["url"], gaps=gaps, core=list(CORE))
    return None


# ───────────── owners + one-click commands ─────────────
def owner(con, pr):
    a = [r["login"] for r in rows(con, "SELECT login FROM pr_assignee WHERE pr=?", pr)]
    if a:
        return dict(who=", ".join(a), how="assignee")
    au = (one(con, "SELECT author FROM pr WHERE number=?", pr) or {}).get("author")
    return dict(who=au, how="author") if au else None


CLONE = Path(__file__).resolve().parents[3] / "third_party" / "LMCache"   # local clone (CODEOWNERS)


def codeowners_of(path):
    """Owners of one repo path from .github/CODEOWNERS of the local clone (last matching rule wins). Round 2 A4 / B5."""
    f = CLONE / ".github" / "CODEOWNERS"
    hit = None
    if not f.is_file():
        return []
    for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        pat, *own = ln.split()
        rx = re.escape(pat.lstrip("/")).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        rx = ("^" if pat.startswith("/") else "(^|/)") + rx + ("" if pat.endswith("/") else "($|/)")
        if re.search(rx, path):
            hit = own
    return [o.lstrip("@") for o in hit or []]


def recorded_decisions(con):
    """Latest recorded decision per blocker (decide.py, append-only table release_decision)."""
    try:
        return {r["blocker_id"]: r for r in rows(con, "SELECT * FROM release_decision ORDER BY decided_at, id")}
    except Exception:  # noqa: BLE001 - table not created yet (no decision recorded so far)
        return {}


VI_PHRASES = [   # round 2 E4: blocker titles in Vietnamese (the English title stays the source of truth)
    (r"uploaded (\S+) instead \(a pre-release: pip install of this package gets a dev build\)", r"đã upload \1 thay vì bản đúng (bản pre-release: pip install gói này sẽ ra bản dev)"),
    (r"uploaded (\S+) instead", r"đã upload \1 thay vì bản đúng"),
    (r"^dev red on (.+)$", r"dev đỏ ở \1"),
    (r" — missing$", " — thiếu"),
]


def title_vi(t):
    v = t or ""
    for rx, rp in VI_PHRASES:
        v = re.sub(rx, rp, v)
    return v if v != t else None


def decide_cmd(bid):
    return f'python -X utf8 ops-app/backend/decide.py record {bid} --action post1|upload|known_issue|accept --reason "..." --by <name>'


SRC_OF_KIND = {"publish": "ops_db", "artifact": "ops_db", "ci": "observe_snapshot", "pr": "trace_agent", "carryover": "release_prep"}


def apply_policy(b, open_dec, line, rel_tags):
    """Gating policy (config.GATING_ARTIFACTS): platform wheels and optional images are known issues, an artifact whose need is
    an open decision waits on it, a blocker that belongs to another (older) line does not decide this line."""
    aid = (b.get("id") or "").split(":artifact:")[-1] if ":artifact:" in (b.get("id") or "") else None
    if b["kind"] == "artifact" and aid:
        dec = ARTIFACT_DECISION.get(aid)
        if dec and dec in open_dec:
            b.update(gating=False, policy="decision", policy_ref=dec)
        elif aid not in GATING_ARTIFACTS:
            b.update(gating=False, policy="known_issue")
    elif b["kind"] == "publish" and re.search(PLATFORM_JOB, b.get("code") or ""):
        b.update(gating=False, policy="known_issue")
    elif b["kind"] == "pr":
        m = re.search(r"\b(v\d+\.\d+\.\d+\S*)", (b.get("fact") or "") + " " + (b.get("title") or ""))
        if m and m.group(1) in rel_tags and rel_tags[m.group(1)]["line"] != line:
            b.update(gating=False, policy="other_line", policy_ref=m.group(1))
    b.setdefault("gating", True)
    return b


def merge_publish_blockers(bl):
    """The push run and the release run of one tag fail the same job: one blocker, both runs as evidence (R9).
    A failed publish job of a FINAL tag cannot be fixed by rerunning the same commit (R3): no rerun command."""
    out, seen = [], {}
    for b in bl:
        if b["kind"] != "publish":
            out.append(b); continue
        tag = (b.get("title") or "").split(" ")[0]
        k = (tag, b.get("code"))
        if k in seen:
            first = seen[k]
            first["runs"] = first.get("runs", [first.get("evidence")]) + [b.get("evidence")]
            first["title"] = re.sub(r" publish \((release|push)\):", " publish (push + release):", first["title"])
            continue
        seen[k] = b
        if re.fullmatch(r"v\d+\.\d+\.\d+(\.post\d+)?", tag):
            b.pop("cmd", None)
            b["next"] = dict(en=f"{tag} is a final tag: a rerun builds the same commit and fails again. Options: {tag}.post1 with the fix, "
                                 "an out-of-band upload of this artifact, or a known issue in the release notes.",
                             vi=f"{tag} là tag final: chạy lại sẽ build cùng commit và lỗi lại. Lựa chọn: ra {tag}.post1 có bản sửa, "
                                "upload riêng artifact này, hoặc ghi known issue trong release note.")
        out.append(b)
    return out


def enrich_blockers(con, bl):
    for b in bl:
        b["src"] = SRC_OF_KIND.get(b["kind"])
        m = re.search(r"/actions/runs/(\d+)", b.get("evidence") or "")
        if b["kind"] == "publish" and m:
            b["cmd"] = f"gh run rerun {m.group(1)} --failed --repo {REPO}"
        n = re.match(r"#(\d+)$", b.get("code") or "")
        if b["kind"] == "pr" and n:
            b["owner"] = owner(con, int(n.group(1)))
            b["cmd"] = f"gh pr view {n.group(1)} --repo {REPO} --web"
        if b["kind"] in ("artifact", "publish") and not b.get("owner"):   # round 2 A4 / B5: who acts on a publish gap
            own = codeowners_of(".github/workflows/publish.yml")
            if own:
                b["owner"] = dict(who=", ".join(own[:4]) + (f" +{len(own) - 4}" if len(own) > 4 else ""), how="codeowners")
        tag = (b.get("title") or "").split(":")[0].split(" ")[0]
        if b["kind"] == "artifact" and re.fullmatch(r"v\d+\.\d+\.\d+(\.post\d+)?", tag) and not b.get("next"):
            b["next"] = dict(en=f"{tag} is a final tag: decide between {tag}.post1 with the fix, an out-of-band upload of this artifact, "
                                "or a known issue in the release notes, and record it.",
                             vi=f"{tag} là tag final: chọn giữa {tag}.post1 có bản sửa, upload riêng artifact này, "
                                "hoặc known issue trong release note, rồi ghi lại quyết định.")
        if b["kind"] in ("artifact", "publish"):
            b["decide_cmd"] = decide_cmd(b["id"])
    return bl


def ready_queue(con):
    """PRs green on DCO + quality + GPU unit whose MP suite has not run: approved first, then oldest."""
    q = []
    for x in _jget("today.json", "ready") or []:
        x = dict(x)
        x["owner"] = owner(con, x["num"]) or dict(who=x.get("author"), how="author")
        x["cmd"] = f"gh pr edit {x['num']} --repo {REPO} --add-label full"
        q.append(x)
    q.sort(key=lambda r: (r.get("review") != "APPROVED", -(r.get("age_d") or 0)))
    return q
