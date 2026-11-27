"""Today tab (#obs/today): the reviewer's decision inbox (v2, phase P3). Idempotent.

One row per item that needs a person today, most urgent first. Every verb comes from decisions.py;
the rule sentence is the chip tooltip. Reads only local files (no network):
  ops_tabs.json (Rebase risk review queue, post-merge CI, Trace Agent findings, RELEASE_PREP rows),
  observe_snapshot.json (dev builds, publish runs), ops_ci_24h.json (last 24 h of builds and jobs), entities.json.
Writes today.json and embeds it as <script id="todayData">. Run after build_ops_tabs.py, before build_entity_ui.py.
"""
import collections
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "P1"))
import decisions as DEC  # noqa: E402
from build_jobs_table import parse_label  # noqa: E402

PAGE = str(Path(__file__).resolve().parents[2] / "06_PR_TO_CI_VISUAL.html")
OUT = os.path.join(HERE, "today.json")
TA_DIR = os.path.join(HERE, "..", "trace_agent")
GH = "https://github.com/LMCache/LMCache"
VISIBLE = 15


def load(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def at(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(s)[:16].replace("T", " ")


def words(s):
    return len(s.split())


DESK = os.path.join(HERE, "release_desk.json")
DESK_EXPORT = Path(HERE).resolve().parents[2] / "ops-app" / "backend" / "export_page_data.py"


def load_desk():
    """Registry facts from ops-app (ops.db). Refresh the export when the db exists; never needs network."""
    db = DESK_EXPORT.parents[1] / "data" / "ops.db"
    if DESK_EXPORT.exists() and db.exists():
        import subprocess
        r = subprocess.run([sys.executable, "-X", "utf8", str(DESK_EXPORT)], cwd=str(DESK_EXPORT.parent),
                           capture_output=True, text=True, encoding="utf-8")
        print("today:", (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else "export: no output")
    return load(DESK, {}) or {}


def vcount_pre(rows, verb):
    return sum(1 for r in rows if r["verb"] == verb)


def age_h(s):
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def build():
    ops = load(os.path.join(HERE, "ops_tabs.json"), {}) or {}
    snap = load(os.path.join(HERE, "observe_snapshot.json"), {}) or {}
    ci24 = load(os.path.join(HERE, "ops_ci_24h.json"), {}) or {}
    ent = load(os.path.join(HERE, "entities.json"), {}) or {}
    nodes = ent.get("nodes") or {}
    desk = load_desk()
    src_at = {s["key"]: s.get("at") for s in desk.get("sources") or []}
    ov, rv = ops.get("overlap") or {}, (ops.get("overlap") or {}).get("review") or {}
    rows, dec = [], {}

    def node_title(k, fallback=None):
        return (nodes.get(k) or {}).get("title") or fallback

    # Trace Agent findings per PR (all tabs): shown as a dashed chip next to the rule chip, never merged into it
    ta_by_pr = {}
    for lst in (ops.get("ta") or {}).values():
        for x in lst:
            ta_by_pr.setdefault(x["num"], x)

    def ta_of(num):
        x = ta_by_pr.get(num)
        return dict(cls=x.get("cls"), impact=x.get("impact"), tag=x.get("tag"), fix_pr=x.get("fix_pr"),
                    report=x.get("report")) if x else None

    def add(verb, key, label, title, short, ev, evl, by="rule", when=None, lvl=9, raw=True, **kw):
        assert verb in DEC.VERBS and words(short[0]) <= 8, (verb, short)
        r = dict(verb=verb, by=by, key=key if key in nodes else None, label=label, title=title, short=short, ev=ev, evl=evl,
                 at=at(when), lvl=lvl, raw=raw, **kw)
        rows.append(r)
        return r

    # ---------------------------------------------------------- PR decisions (Rebase risk review queue + running CI)
    for x in rv.get("queue") or []:
        k = f"pr:{x['num']}"
        dec[k] = dict(verb=x["verb"], short=x.get("short"), by="rule", ta=ta_of(x["num"]), clash=x.get("clash") or None)
        if x["verb"] not in DEC.TODAY:
            continue
        if x["verb"] == "rebase" and x.get("clash"):
            ev, evl = f"{GH}/pull/{x['clash'][0]['m']}/files", [f"Diff of #{x['clash'][0]['m']}", f"Diff của #{x['clash'][0]['m']}"]
        else:
            ev, evl = (x.get("url") or f"{GH}/pull/{x['num']}") + "/checks", ["Checks", "Checks"]
        add(x["verb"], k, f"#{x['num']}", x["title"], x["short"], ev, evl, lvl=DEC.LVN.get(x.get("level"), 9),
            age_d=x.get("age_d"), ta=ta_of(x["num"]))
    for x in rv.get("running") or []:
        k = f"pr:{x['num']}"
        dec[k] = dict(verb=x["verb"], short=x.get("short"), by="rule", ta=ta_of(x["num"]), clash=x.get("clash") or None)
        if x["verb"] == "cancel":
            run = (x.get("runs") or [{}])[0]
            add("cancel", k, f"#{x['num']}", x["title"], x["short"], run.get("url") or x.get("url"),
                ["Running build", "Build đang chạy"], lvl=DEC.LVN.get(x.get("level"), 9), ta=ta_of(x["num"]), save=x.get("save"))

    # ---------------------------------------------------------- dev: new red (TRIAGE) / known red (watch)
    devb = {}
    for b in (snap.get("bk") or {}).get("dev_builds") or []:
        devb[((b.get("pipeline") or {}).get("slug"), b["number"])] = b
    for b in ci24.get("bk") or []:
        if b.get("branch") == "dev":
            devb[((b.get("pipeline") or {}).get("slug"), b["number"])] = b
    by_pipe = collections.defaultdict(list)
    for (slug, _), b in devb.items():
        by_pipe[slug].append(b)
    known_red = []
    for slug, bs in sorted(by_pipe.items()):
        d = DEC.dev_pipeline(bs)
        if not d:
            continue
        b = d["build"]
        bk = f"build:{slug}/{b['number']}"
        dec[bk] = dict(verb=d["verb"], short=d["short"], by="rule")
        dec[f"ci:{slug}"] = dec[bk]
        if d["verb"] == "triage":
            add("triage", bk, f"{slug} #{b['number']}", (b.get("message") or "").splitlines()[0] if b.get("message") else slug,
                d["short"], b.get("web_url"), ["Failed build", "Build fail"], when=b.get("created_at"), pr=d.get("pr"))
        else:
            known_red.append(dict(key=bk, slug=slug, number=b["number"], url=b.get("web_url"), at=at(b.get("created_at"))))

    # ---------------------------------------------------------- flaky: fail then pass on one commit, last 24 h (QUARANTINE?)
    known = {re.sub(r"\s*\(.*$", "", x["name"]) for x in ov.get("known_flaky") or []}
    same = collections.defaultdict(list)
    for b in ci24.get("bk") or []:
        same[((b.get("pipeline") or {}).get("slug"), b.get("commit"))].append(b)
    seen = set()
    for (slug, sha), bs in same.items():
        states = {b.get("state") for b in bs}
        failed_w = {parse_label(j["name"])[0] for b in bs if b.get("state") == "failed" for j in b.get("jobs") or []
                    if j.get("name") and j.get("state") == "failed"}
        is_known = bool(failed_w) and failed_w <= known
        if DEC.quarantine(states, is_known):
            w = next(iter(failed_w)) if len(failed_w) == 1 else None
            k = f"test:gpu/{w}" if w else f"ci:{slug}"
            fb = next(b for b in bs if b.get("state") == "failed")
            if (k, sha) in seen:
                continue
            seen.add((k, sha))
            add("quarantine", k, w or slug, f"{slug} · {(sha or '')[:8]}", ["Failed, then passed on same commit", "Fail rồi pass trên cùng commit"],
                fb.get("web_url"), ["Failed build", "Build fail"], when=fb.get("created_at"))
    for b in ci24.get("bk") or []:   # job retried inside one build and the build passed
        if b.get("state") != "passed":
            continue
        for j in b.get("jobs") or []:
            if j.get("retried") and j.get("name"):
                w = parse_label(j["name"])[0]
                k = f"test:gpu/{w}"
                if DEC.quarantine({"failed", "passed"}, w in known) and (k, b.get("commit")) not in seen:
                    seen.add((k, b.get("commit")))
                    add("quarantine", k, w, f"{(b.get('pipeline') or {}).get('slug')} #{b['number']}", ["Job retried, then passed", "Job chạy lại rồi pass"],
                        b.get("web_url"), ["Build", "Build"], when=b.get("created_at"))

    # ---------------------------------------------------------- release blockers (BLOCK by Trace Agent, FIX by rule)
    health = (ops.get("ta_meta") or {}).get("health") or {}
    # stable = newest final/post tag seen in the registries (the Trace Agent's 'stable' can be days old)
    current = desk.get("stable") or health.get("stable") or (snap.get("gh") or {}).get("merged_since")
    rm = ((ops.get("coming") or {}).get("roadmap") or {}).get("src") or {}
    nxt = "v" + rm["version"] if rm.get("version") else None
    for x in sorted({x["key"]: x for lst in (ops.get("ta") or {}).values() for x in lst}.values(), key=lambda x: x["key"]):
        if DEC.block_release(x, current, nxt):
            rep = os.path.join(TA_DIR, x["report"]) if x.get("report") else None
            ev = ("outputs/trace_agent/" + x["report"]) if rep and os.path.exists(rep) else f"{GH}/pull/{x['num']}"
            k = f"pr:{x['num']}"
            r = add("block", k, f"#{x['num']}", x.get("title") or node_title(k, ""), [f"Trace Agent: blocks {x['tag']}; no fix", f"Trace Agent: chặn {x['tag']}; chưa sửa"],
                    ev, ["Trace Agent report", "Báo cáo Trace Agent"], by="agent", when=x.get("run_at"), ta=ta_of(x["num"]), src=x.get("run_at") or src_at.get("trace_agent"))
            dec.setdefault(k, {}).update(block=dict(verb="block", short=r["short"], by="agent"))
    pubs = (snap.get("gh") or {}).get("publish_tags") or {}
    # the latest tag (an RC counts: v0.5.8rc1, not only 'v0.5.8') and the stable tag users have
    pub_tags = [t for t in dict.fromkeys([desk.get("latest"), desk.get("stable")] if desk else [current, nxt]) if t]
    for tag in pub_tags:
        drun = sorted((desk.get("releases") or {}).get(tag, {}).get("runs") or [], key=lambda r: r.get("created_at") or "", reverse=True)
        runs = drun or sorted(pubs.get(tag) or [], key=lambda r: (r.get("created_at") or "", r.get("run_attempt") or 0), reverse=True)
        fin = next((r for r in runs if r.get("status") == "completed"), None)
        if DEC.fix_publish(fin):
            jobs = {}
            for r in runs:   # same job failing in the push and the release run -> one line
                for j in r.get("failed_jobs") or []:
                    jobs.setdefault((j["name"], j.get("error_line")), []).append(r.get("event"))
            c = fin.get("conclusion")
            title = "; ".join(f"{n.split(' / ')[-1]} ({'+'.join(e)})" for (n, _), e in jobs.items()) or f"publish.yml {tag}"
            note = "\n".join(f"{n} [{'+'.join(e)}]: {err or '—'}" for (n, err), e in jobs.items())
            add("fix", f"release:{tag}", tag, title, [f"publish.yml {c} for {tag}", f"publish.yml {c} cho {tag}"],
                fin.get("url") or fin.get("html_url"), ["publish run", "run publish"], when=fin.get("created_at"),
                note=note or None, errors=[dict(job=n, events=e, line=err) for (n, err), e in jobs.items()],
                src=src_at.get("registries") if drun else snap.get("at"))
            dec[f"release:{tag}"] = dict(verb="fix", short=rows[-1]["short"], by="rule")
    prep = ((ops.get("coming") or {}).get("nr") or {}).get("prep") or []
    carry = [r for r in prep if DEC.fix_carry_over(r)]
    if carry:   # one row for all open carry-over blockers: same rule, same place to act (the cockpit lists each one)
        ids = [r["id"] for r in carry]
        add("fix", None, ids[0] + ("–" + ids[-1] if len(ids) > 1 else ""), carry[0]["cols"][0] + (f" (+{len(carry) - 1})" if len(carry) > 1 else ""),
            [f"{len(carry)} carry-over blockers from last release open", f"{len(carry)} blocker mang từ bản trước còn mở"],
            "#obs/coming", ["Release cockpit", "Release cockpit"], note="\n".join(f"{r['id']} · {r['cols'][0]} — {(r['cols'] + ['', ''])[2]}" for r in carry),
            src=src_at.get("release_prep"))   # age of the prep doc: shown as a stale chip when > 48 h
    decide_open = [r["id"] for r in prep if r.get("id", "").startswith("D")
                   and not re.match(r"^(decided|done|xong|đã)", (r.get("cols") + ["", "", "", ""])[3] or "", re.I)]

    # ---------------------------------------------------------- releases: verdict per tag + PRs -> features -> blockers (Releases tab)
    out_e = collections.defaultdict(list)
    for e in ent.get("edges") or []:
        out_e[e["from"]].append(e)
    ta_all = {x["key"]: x for lst in (ops.get("ta") or {}).values() for x in lst}
    published = {r["tag_name"]: r for r in (snap.get("gh") or {}).get("releases") or []}
    releases = []
    drel = desk.get("releases") or {}   # ops.db (fresh): publish runs + publish time per tag (expert review R7)
    def pub_at(n):
        return (drel.get(n["id"]) or {}).get("at") or n.get("at") or ""
    for n in sorted((n for n in nodes.values() if n["kind"] == "release" and n.get("state") != "next"), key=pub_at, reverse=True):
        tag, rk = n["id"], f"release:{n['id']}"
        prs = [e["to"] for e in out_e[rk] if e["rel"] == "contains"]
        feats = collections.Counter(e["to"] for p_ in prs for e in out_e[p_] if e["rel"] == "changes" and e["strength"] == "strong")
        runs = pubs.get(tag) or [dict(status=r.get("status"), conclusion=r.get("conclusion"), created_at=r.get("created_at"), html_url=r.get("url"), event=r.get("event"))
                                  for r in (drel.get(tag) or {}).get("runs") or []]
        runs = sorted(runs, key=lambda r: (r.get("created_at") or "", r.get("run_attempt") or 0), reverse=True)
        fin = next((r for r in runs if r.get("status") == "completed"), None)
        blockers = [dict(num=x["num"], fix_status=x.get("fix_status"), fix_pr=x.get("fix_pr"), cls=x.get("cls"))
                    for x in ta_all.values() if x.get("tag") == tag and x.get("impact") == "blocks-release"]
        d = DEC.release_verdict(fin, blockers, [r for r in runs if r.get("status") != "completed"])
        dec[rk] = dict(verb=d["verb"], short=d["short"], by=d.get("by", "rule"))
        releases.append(dict(key=rk, tag=tag, at=pub_at(n) or n.get("at"), state=n.get("state"), verb=d["verb"], by=d.get("by", "rule"), short=d["short"],
                             n_prs=len(prs), feats=[[k, c, (nodes.get(k) or {}).get("status")] for k, c in feats.most_common(5)],
                             n_feats=len(feats), blockers=blockers, published=tag in published,
                             ev=(fin or (runs[0] if runs else {})).get("html_url") or n.get("url"), evl=["publish run", "run publish"] if runs else ["GitHub release", "GitHub release"]))
    nxt_row = dict(key=f"release:{nxt}" if f"release:{nxt}" in nodes else None, tag=nxt)

    # ---------------------------------------------------------- known red: add last-known-good (ops.db keeps ~60 days of dev builds)
    for k in known_red:
        g = (desk.get("lkg") or {}).get(k["slug"]) or {}
        k.update(green_at=at((g.get("green") or {}).get("created_at")), green_num=(g.get("green") or {}).get("number"),
                 green_url=(g.get("green") or {}).get("url"), red_since=at(g.get("red_since")), red_builds=g.get("red_builds"),
                 history_from=at(g.get("history_from")))

    # ---------------------------------------------------------- Go / No-Go for the next RC + rollback target ($GOOD)
    gate = None
    if desk:
        lt = (desk.get("releases") or {}).get(desk.get("latest")) or {}
        pub_err = sorted({j["name"] for r in lt.get("runs") or [] for j in r.get("failed_jobs") or []})
        reasons = [
            dict(kind="publish", n=len(pub_err), en=f"publish.yml errors on {desk.get('latest')}", vi=f"lỗi publish.yml trên {desk.get('latest')}",
                 items=pub_err, goto="obs/release"),
            dict(kind="artifact", n=len(lt.get("missing") or []), en=f"artifacts missing or wrong on {desk.get('latest')}",
                 vi=f"artifact thiếu hoặc sai trên {desk.get('latest')}", items=[m["label"] for m in lt.get("missing") or []], goto="obs/release"),
            dict(kind="dev_red", n=len(known_red) + vcount_pre(rows, "triage"), en="dev gate pipelines red", vi="pipeline gate trên dev đang đỏ",
                 items=[k["slug"] for k in known_red], goto="obs/today"),
            dict(kind="block", n=vcount_pre(rows, "block"), en="release-blocking bugs without a merged fix", vi="bug chặn release chưa có bản sửa",
                 items=[r["label"] for r in rows if r["verb"] == "block"], goto="obs/today"),
            dict(kind="carry", n=len(carry), en="carry-over blockers open", vi="blocker mang từ bản trước còn mở", items=[r["id"] for r in carry], goto="obs/coming"),
            dict(kind="decide", n=len(decide_open), en="release decisions open", vi="quyết định release còn mở", items=decide_open,
                 hinted=[d for d in decide_open if d in (desk.get("hints") or {})], goto="obs/coming"),
        ]
        hard = sum(r["n"] for r in reasons if r["kind"] in ("publish", "artifact", "dev_red", "block"))
        soft = sum(r["n"] for r in reasons if r["kind"] in ("carry", "decide"))
        st = (desk.get("releases") or {}).get(desk.get("stable")) or {}
        gate = dict(next_rc=desk.get("next_rc") or nxt, latest=desk.get("latest"), stable=desk.get("stable"),
                    verdict="no_go" if hard else ("go_with_items" if soft else "go"), reasons=reasons,
                    latest_art=[lt.get("n_ok"), lt.get("n_expected")], stable_art=[st.get("n_ok"), st.get("n_expected")],
                    stable_missing=[m["label"] for m in st.get("missing") or []], good=desk.get("good"), core=desk.get("core"),
                    hints=desk.get("hints") or {}, sources=desk.get("sources") or [], checked=src_at.get("registries"))

    # ---------------------------------------------------------- waiting for a maintainer: green on CPU + GPU unit, MP not run ('full' missing)
    gql = {p["number"]: p for p in ((snap.get("gh") or {}).get("prs_gql") or {}).get("nodes") or []}
    ready = []
    for x in rv.get("queue") or []:
        g = x.get("gates") or {}
        # green on DCO + quality + GPU unit and the MP suite never ran; approved PRs too (they may also need a rebase)
        if x["verb"] in ("review", "full", "rebase", "merge") and all(g.get(k) == "ok" for k in ("dco", "quality", "unit"))                 and g.get("mp") in ("label", "missing"):
            p = gql.get(x["num"]) or {}
            ready.append(dict(num=x["num"], key=f"pr:{x['num']}" if f"pr:{x['num']}" in nodes else None, title=x["title"], author=x.get("author"),
                              age_d=x.get("age_d"), review=x.get("review"), mergeable=p.get("mergeable"), verb=x["verb"],
                              assignees=[a["login"] for a in ((p.get("assignees") or {}).get("nodes") or [])]))
    ready.sort(key=lambda r: (r.get("review") != "APPROVED", -(r.get("age_d") or 0)))   # approved first, then oldest

    # ---------------------------------------------------------- order, counts
    order = {v: i for i, v in enumerate(DEC.TODAY)}
    rows.sort(key=lambda r: (order[r["verb"]], r["lvl"], -(datetime.fromisoformat(r["at"]).timestamp() if r.get("at") else 0)))
    mci = collections.Counter(m.get("ci") for m in ov.get("merged_ci") or [])
    keep = [x for x in rv.get("running") or [] if x["verb"] == "keep"]
    watch = dict(ci_running=len(keep), post_merge=mci.get("queued", 0) + mci.get("running", 0), known_red=len(known_red))
    git_head = ((ops.get("coming") or {}).get("scope") or {}).get("head_at")
    vcount = collections.Counter(r["verb"] for r in rows)
    return dict(made=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), snap_at=snap.get("at"), ci_at=ci24.get("at"), git_at=git_head,
                current=current, next=nxt, visible=VISIBLE, rows=rows, dec=dec,
                counts=dict(decide=len(rows), by_verb=dict(vcount), watch=sum(watch.values()), watch_parts=watch,
                            done=mci.get("passed", 0), merged_24h=len(ov.get("merged_ci") or []),
                            review_queue=sum(1 for x in rv.get("queue") or [] if x["verb"] == "review"),
                            author=sum(1 for x in rv.get("queue") or [] if x["verb"] in ("red", "dco", "author")),
                            release_decisions=decide_open),
                known_red=known_red, releases=releases, next_release=nxt_row, gate=gate, ready=ready,
                desk=dict(releases=desk.get("releases") or {}, matrix=desk.get("matrix") or {}, focus=desk.get("focus") or [],
                          good=desk.get("good"), core=desk.get("core")) if desk else None,
                verbs={k: list(v) for k, v in DEC.VERBS.items()}, rules=DEC.RULE, order=DEC.TODAY)


HTML = r"""
<!-- TODAY:HTML:START -->
<section class="card" data-view="obs" data-tab="today" id="todaySec">
  <div class="head"><h2 id="tdyH">0 · Today</h2><p class="sub" id="tdySub"></p></div>
  <div id="tdyBody"></div>
</section>
<section class="card" data-view="obs" data-tab="release" id="relVerdict">
  <div class="head"><h2 id="relH">1 · Verdict per release</h2><p class="sub" id="relSub"></p></div>
  <div id="relBody"></div>
</section>
<section class="card" data-view="obs" data-tab="overlap" id="ovReady">
  <div class="head"><h2 id="ovReadyH">PR queue · ready for 'full'</h2><p class="sub" id="ovReadySub"></p></div>
  <div id="ovReadyBody"></div>
</section>
<!-- TODAY:HTML:END -->
"""

CSS = r"""
/* TODAY:CSS:START */
.tdy-kpi{margin:2px 0 12px;font-size:14px}
.tdy-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:4px 0 16px}
.tdy-tile{border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--surface-1)}
.tdy-tile .l{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted)}
.tdy-tile .v{font-size:26px;font-weight:700;line-height:1.15;margin:2px 0;color:var(--text-primary);font-variant-numeric:tabular-nums}
.tdy-tile .s{font-size:12px;color:var(--text-secondary);line-height:1.35;overflow-wrap:anywhere}
.tdy-tile.warn{border-color:var(--warning)}
.tdy-st{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:650;color:var(--text-primary)}
.tdy-st i{width:8px;height:8px;border-radius:50%;background:var(--good)}
.tdy-tile.warn .tdy-st i{background:var(--warning)}
.tdy-list{border-top:1px solid var(--border)}
.tdy-row{display:grid;grid-template-columns:170px minmax(0,1.6fr) minmax(0,1.3fr) max-content;gap:4px 14px;align-items:baseline;padding:8px 4px;border-bottom:1px solid var(--border)}
.tdy-row.hd{font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted);padding-top:6px;padding-bottom:6px}
.tdy-obj{min-width:0;display:flex;gap:8px;align-items:baseline}
#todaySec .tdy-row.hd,#todaySec .tdy-row.pr .tdy-obj .t{display:none}
.tdy-obj .t{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-secondary)}
.tdy-obj .id{font-weight:650;white-space:nowrap}
.tdy-why{color:var(--text-primary)}
.tdy-ev{font-weight:600;color:var(--series-1);white-space:nowrap}
.tdy-v{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:750;letter-spacing:.03em;padding:2px 8px;border-radius:6px;border:1.5px solid var(--border);color:var(--text-primary);white-space:nowrap;cursor:help;margin:0 4px 2px 0;background:var(--surface-1)}
.tdy-v::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--text-muted);flex:none}
.tdy-v.t-act{border-color:var(--critical)}.tdy-v.t-act::before{background:var(--critical)}
.tdy-v.t-do{border-color:var(--warning)}.tdy-v.t-do::before{background:var(--warning)}
.tdy-v.t-ok{border-color:var(--good)}.tdy-v.t-ok::before{background:var(--good)}
.tdy-v.agent{border-style:dashed}
.tdy-v:focus-visible{outline:2px solid var(--series-1);outline-offset:1px}
.tdy-more{all:unset;cursor:pointer;margin:10px 4px 0;font-size:12.5px;font-weight:600;color:var(--series-1)}
.tdy-more:hover{text-decoration:underline}
.tdy-more:focus-visible{outline:2px solid var(--series-1)}
.tdy-empty{padding:18px 4px;color:var(--text-secondary)}
.tdy-foot{margin-top:16px;display:flex;flex-direction:column;gap:6px;font-size:12.5px;color:var(--text-secondary)}
.tdy-foot button{all:unset;cursor:pointer;color:var(--series-1);font-weight:600}
.tdy-foot button:hover{text-decoration:underline}
.tdy-foot button:focus-visible{outline:2px solid var(--series-1)}
.tdy-rules{margin-top:14px;border:1px solid var(--border);border-radius:8px;padding:0 12px}
.tdy-rules>summary{cursor:pointer;padding:8px 0;font-weight:650;font-size:12.5px;color:var(--text-secondary)}
.tdy-rules dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 12px;margin:4px 0 12px;font-size:12.5px}
.tdy-rules dd{margin:0;color:var(--text-secondary)}
.tdy-tip{position:fixed;z-index:90;max-width:340px;padding:7px 10px;border-radius:8px;background:var(--surface-2);color:var(--text-primary);border:1px solid var(--border);box-shadow:0 6px 18px rgba(0,0,0,.18);font-size:12px;line-height:1.4;pointer-events:none;display:none}
.rel-row{display:grid;grid-template-columns:110px 210px minmax(0,1.6fr) minmax(0,1fr) max-content;gap:4px 14px;align-items:baseline;padding:8px 4px;border-bottom:1px solid var(--border)}
.rel-row.hd{font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted);padding:6px 4px}
.rel-feat{display:inline-flex;align-items:center;gap:4px;margin:0 10px 2px 0;white-space:nowrap}
.rel-feat i{width:7px;height:7px;border-radius:50%;background:var(--text-muted)}.rel-feat i.green{background:var(--good)}.rel-feat i.red{background:var(--critical)}
.rel-feat small,.rel-meta{color:var(--text-muted);font-size:11.5px}
.gng{display:grid;grid-template-columns:minmax(0,2fr) repeat(3,minmax(0,1fr));gap:10px;margin:4px 0 12px;border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--surface-1)}
.gng .l{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted);margin-bottom:4px}
.gng .v{font-size:17px;font-weight:700;color:var(--text-primary)}
.gng .s{font-size:12px;color:var(--text-secondary);line-height:1.4}
.gng ul{margin:6px 0 0;padding-left:18px;font-size:12.5px;line-height:1.55;color:var(--text-primary)}
.gng-cell{border-left:1px solid var(--border);padding-left:10px;min-width:0}
.gng-foot{grid-column:1/-1;font-size:11.5px;color:var(--text-muted)}
.gng-go{all:unset;cursor:pointer;color:var(--series-1);font-weight:700;padding:0 4px}
.gng-go:focus-visible,.tdy-copy:focus-visible{outline:2px solid var(--series-1)}
.tdy-hint{font-size:11.5px;color:var(--warning);font-weight:600}
.tdy-stale{display:inline-block;font-size:10.5px;font-weight:700;padding:0 6px;border-radius:5px;border:1px dashed var(--warning);color:var(--warning);white-space:nowrap;margin-left:4px}
.tdy-err{display:block;margin-top:3px;font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:var(--critical);overflow-wrap:anywhere}
.tdy-old{color:var(--warning);font-weight:600}
.tdy-src{margin-top:4px;font-size:11.5px}.tdy-src>summary{cursor:pointer;color:var(--series-1)}
.tdy-ready{margin-top:12px;border:1px solid var(--border);border-radius:8px;padding:0 12px}
.tdy-ready>summary{cursor:pointer;padding:8px 0;font-size:12.5px;color:var(--text-primary)}
.tdy-rtab{width:100%;border-collapse:collapse;font-size:12.5px}
.tdy-rtab th{text-align:left;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--text-muted);padding:4px 6px;border-bottom:1px solid var(--border)}
.tdy-rtab td{padding:5px 6px;border-bottom:1px solid var(--border);vertical-align:top}
.tdy-rt{max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tdy-rtab.mx td:not(:first-child),.tdy-rtab.mx th:not(:first-child){text-align:center}
.tdy-copy{all:unset;cursor:pointer;font-size:11.5px;font-weight:600;color:var(--series-1);white-space:nowrap}
.mx-h{margin:18px 0 2px;font-size:14px}
.tdy-scroll{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
@media (max-width:900px){.gng{grid-template-columns:repeat(2,minmax(0,1fr))}.gng-main{grid-column:1/-1}.gng-cell{border-left:0;padding-left:0;border-top:1px solid var(--border);padding-top:6px}}
@media (max-width:520px){.gng{grid-template-columns:1fr}.tdy-rt{max-width:180px}}
@media (max-width:900px){.rel-row{grid-template-columns:auto minmax(0,1fr)}.rel-row.hd{display:none}.rel-row>:nth-child(n+3){grid-column:1/-1}}
@media (max-width:900px){.tdy-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:700px){.tdy-row{grid-template-columns:auto minmax(0,1fr)}.tdy-row.hd{display:none}.tdy-why,.tdy-ev{grid-column:1/-1}.tdy-why{padding-left:2px}}
/* TODAY:CSS:END */
"""

JS = r"""
<!-- TODAY:JS:START -->
<script id="todayData" type="application/json">__DATA__</script>
<script>
(function(){
  let D;try{D=JSON.parse(document.getElementById('todayData').textContent);}catch(e){return;}
  window.TODAY=D;
  const T=(en,vi)=>(window.I18N&&I18N.lang==='vi')?vi:en, L=a=>a?T(a[0],a[1]):'';
  const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const body=document.getElementById('tdyBody'),H=document.getElementById('tdyH'),SUB=document.getElementById('tdySub');
  let more=false;
  // one verb chip for the page: rule = solid, Trace Agent = dashed; the rule sentence is the tooltip (decisions.py)
  const chip=(verb,by)=>{const v=D.verbs[verb]||[verb,verb,'info'],rule=D.rules[verb];
    const tip=(by==='agent'?'✦ Trace Agent · ':T('Rule · ','Luật · '))+(rule?L(rule):'');
    return `<span class="tdy-v t-${v[2]}${by==='agent'?' agent':''}" data-verb="${esc(verb)}" tabindex="0" data-rule="${esc(tip)}">${by==='agent'?'✦ ':''}${esc((s=>s.charAt(0)+s.slice(1).toLowerCase())(String(T(v[0],v[1]))))}</span>`;};   // round 3: sentence case
  window.TODAY.chip=chip;
  const taChip=t=>t?`<span class="tdy-v agent" tabindex="0" data-rule="${esc('✦ Trace Agent · '+(t.tag||'')+' · '+(t.impact||''))}">✦ ${esc(t.cls||'')}</span>`:'';
  const ent=(k,lab)=>k&&window.ENT?ENT.a(k,lab):`<b>${esc(lab)}</b>`;
  const ageH=()=>D.snap_at?(Date.now()-Date.parse(D.snap_at))/36e5:null;
  const fmtAge=h=>h==null?'–':h<1?'< 1 h':h<48?Math.round(h)+' h':Math.round(h/24)+' d';
  const ut=s=>s?String(s).replace('T',' ').slice(0,16)+' UTC':'–';
  const hOf=s=>s?(Date.now()-Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(s)?s:String(s).replace(' ','T')+'Z'))/36e5:null;
  const staleChip=s=>{const h=hOf(s);return h!=null&&h>48?`<span class="tdy-stale" title="${esc(T('Source data is older than 48 h','Dữ liệu nguồn cũ hơn 48 giờ'))}">${T('data','dữ liệu')} ${fmtAge(h)}</span>`:'';};
  // Go / No-Go for the next RC + rollback target: facts from the registries (ops-app/ops.db), read from today.json
  function strip(){const g=D.gate;if(!g)return '';
    const V={no_go:['t-act',T('NO-GO for '+g.next_rc,'CHƯA ĐƯỢC cắt '+g.next_rc)],go_with_items:['t-do',T('GO with open items','ĐƯỢC, còn việc mở')],go:['t-ok','GO']}[g.verdict];
    const rs=g.reasons.filter(r=>r.n).map(r=>`<li><b>${r.n}</b> ${esc(T(r.en,r.vi))}${r.items&&r.items.length?` <span class="rel-meta obsraw">· ${esc(r.items.slice(0,4).join(', '))}${r.items.length>4?' …':''}</span>`:''}`+
      `${r.hinted&&r.hinted.length?` <span class="tdy-hint">⚑ ${esc(T(r.hinted.join(', ')+' look decided in practice',r.hinted.join(', ')+' có vẻ đã quyết trên thực tế'))}</span>`:''} <button type="button" class="gng-go" data-goto="${esc(r.goto)}">→</button></li>`).join('');
    const art=a=>a&&a[1]?`${a[0]}/${a[1]}`:'–';
    const gd=g.good;
    return `<div class="gng"><div class="gng-main"><div class="l">${T('Next RC','RC tiếp theo')}</div><span class="tdy-v ${V[0]}" style="font-size:13px">${esc(V[1])}</span><ul>${rs||'<li>'+T('Nothing blocks.','Không có gì chặn.')+'</li>'}</ul></div>`+
      `<div class="gng-cell"><div class="l">${T('Latest tag','Tag mới nhất')}</div><div class="v">${ent('release:'+g.latest,g.latest)}</div><div class="s">${T('artifacts OK','artifact đạt')} <b>${art(g.latest_art)}</b></div></div>`+
      `<div class="gng-cell"><div class="l">${T('Stable (users have)','Stable (người dùng đang dùng)')}</div><div class="v">${ent('release:'+g.stable,g.stable)}</div><div class="s">${T('artifacts OK','artifact đạt')} <b>${art(g.stable_art)}</b>${g.stable_missing.length?'<br>'+T('missing','thiếu')+': <span class="obsraw">'+esc(g.stable_missing.join(', '))+'</span>':''}</div></div>`+
      `<div class="gng-cell"><div class="l">${T('Rollback target ($GOOD)','Bản rollback ($GOOD)')}</div><div class="v">${gd?`<a href="${esc(gd.url)}" target="_blank" rel="noopener">${esc(gd.tag)}</a>`:'–'}</div>`+
      `<div class="s" title="${esc(T('Rule: newest final/post tag whose core artifacts are present and correct: ','Luật: tag final/post mới nhất có đủ artifact lõi: ')+(g.core||[]).join(', '))}">${T('newest final/post with core artifacts OK','final/post mới nhất có đủ artifact lõi')} ⓘ${gd&&gd.gaps.length?'<br>'+T('not core, missing','ngoài lõi, thiếu')+': <span class="obsraw">'+esc(gd.gaps.join(', '))+'</span>':''}</div></div>`+
      `<div class="gng-foot">${T('Registries checked','Kiểm tra registry lúc')} ${esc(ut(g.checked))} ${staleChip(g.checked)}</div></div>`;}
  function tiles(){const c=D.counts,h=ageH(),old=h!=null&&h>6;
    const src=(D.gate&&D.gate.sources)||[];
    const oldest=src.filter(s=>['snapshot','registries','trace_agent','release_prep'].includes(s.key)&&s.at).map(s=>({...s,h:hOf(s.at)})).sort((a,b)=>b.h-a.h)[0];
    const srcList=src.map(s=>{const sh=hOf(s.at);return `<div class="${sh!=null&&sh>48?'tdy-old':''}">${esc(T(s.en,s.vi))}: ${fmtAge(sh)}</div>`;}).join('');
    const kinds=D.order.filter(v=>c.by_verb[v]).map(v=>`${c.by_verb[v]} ${T(D.verbs[v][0],D.verbs[v][1]).toLowerCase()}`).join(' · ');
    const t=(l,v,s,cls)=>`<div class="tdy-tile${cls?' '+cls:''}"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
    // round 3 (A_visual 4.5): one line of counts instead of 4 cards; the data-age card moved to the header "Data" item
    return `<p class="tdy-kpi">`+[`<span title="${esc(kinds)}"><b>${c.decide}</b> ${T('to decide','cần quyết')}</span>`,
      `<span title="${esc(T(`CI running ${c.watch_parts.ci_running} · post-merge CI ${c.watch_parts.post_merge} · dev known red ${c.watch_parts.known_red}`,`CI đang chạy ${c.watch_parts.ci_running} · CI sau merge ${c.watch_parts.post_merge} · dev đỏ đã biết ${c.watch_parts.known_red}`))}"><b>${c.watch}</b> ${T('to watch','theo dõi')}</span>`,
      `<span title="${esc(T(`of ${c.merged_24h} merged in 24 h: post-merge CI green`,`trên ${c.merged_24h} PR merge trong 24 giờ: CI sau merge xanh`))}"><b>${c.done}</b> ${T('done today','xong hôm nay')}</span>`].join(' · ')+`</p>`;}
  function row(r){
    const obj=r.key?ent(r.key,r.label):`<b>${esc(r.label)}</b>`;
    const ev=r.ev?`<a class="tdy-ev" data-ev href="${esc(r.ev)}"${/^#/.test(r.ev)?'':' target="_blank" rel="noopener"'}>${esc(L(r.evl))}${/^#/.test(r.ev)?' →':' ↗'}</a>`:'';
    return `<div class="tdy-row${/^pr:/.test(r.key||'')?' pr':''}"><div>${chip(r.verb,r.by)}${r.by!=='agent'?taChip(r.ta):''}</div>`+
      `<div class="tdy-obj"${/^pr:/.test(r.key||'')?` title="${esc(r.title||'')}"`:''}><span class="id">${obj}</span><span class="t${r.raw?' obsraw':''}" title="${esc(r.note||r.title||'')}">${esc(r.title||'')}</span></div>`+
      `<div class="tdy-why">${esc(L(r.short))} ${staleChip(r.src)}${(r.errors||[]).filter(e=>e.line).map(e=>`<span class="tdy-err obsraw" title="${esc(e.job)}">${esc(e.line)}</span>`).join('')}</div><div>${ev}</div></div>`;}
  function copyCmd(b){const c=b.dataset.cmd,done=()=>{b.textContent=T('copied','đã copy');setTimeout(()=>{b.textContent=T('copy cmd','copy lệnh');},1500);};
    if(navigator.clipboard)navigator.clipboard.writeText(c).then(done,()=>prompt('',c));else prompt('',c);}
  // PRs green on CPU + GPU unit whose MP suite has not run: a maintainer reviews, then adds 'full'. Not a rule verb (they are not approved).
  function readyBox(){const R=D.ready||[];if(!R.length)return '';
    const cmd=n=>`gh pr edit ${n} --repo LMCache/LMCache --add-label full`;
    const rowsH=R.map(p=>`<tr><td>${p.key?ent(p.key,'#'+p.num):'<b>#'+p.num+'</b>'}</td><td class="tdy-rt obsraw">${esc(p.title)}</td><td class="rel-meta">${p.assignees&&p.assignees.length?'<b>'+esc(p.assignees.join(', '))+'</b>':esc(p.author||'')+' <small>('+T('author','tác giả')+')</small>'}${p.review==='APPROVED'?' <span class="tdy-v t-ok">APPROVED</span>':''}${p.verb==='rebase'?' <span class="tdy-v t-do">'+T('rebase first','rebase trước')+'</span>':''}</td>`+
      `<td class="rel-meta">${p.age_d!=null?Math.round(p.age_d)+' d':''}</td><td class="rel-meta">${esc(p.mergeable||'')}</td>`+
      `<td><button type="button" class="tdy-copy" data-cmd="${esc(cmd(p.num))}" title="${esc(cmd(p.num))}">${T('copy cmd','copy lệnh')}</button></td></tr>`).join('');
    return `<details class="tdy-ready"><summary><b>${R.length}</b> ${T("PRs are green on CPU + GPU unit and wait for a maintainer: review, then add 'full' so k3-multiprocess-test (required) runs","PR đã xanh CPU + GPU unit, chờ maintainer: review rồi gắn 'full' để k3-multiprocess-test (bắt buộc) chạy")}</summary>`+
      `<div class="tdy-scroll"><table class="tdy-rtab"><thead><tr><th>PR</th><th>${T('Title','Tiêu đề')}</th><th>Owner</th><th>${T('Age','Tuổi')}</th><th>Mergeable</th><th></th></tr></thead><tbody>${rowsH}</tbody></table></div>`+
      `<div class="rel-meta">${T('Approved first, then oldest. Owner = GitHub assignee; most PRs have none, then the author is shown.','PR đã duyệt lên trước, rồi cũ nhất. Owner = người được giao trên GitHub; đa số PR không có, khi đó hiện tác giả.')}</div></details>`;}
  const redLine=x=>`${ent(x.key,x.slug+' #'+x.number)} <span class="rel-meta">(${x.green_at?T('last green','xanh cuối')+' '+(x.green_url?`<a href="${esc(x.green_url)}" target="_blank" rel="noopener">#${x.green_num}</a>`:'#'+x.green_num)+' '+esc(x.green_at.slice(0,10)):T('no green build since','không có build xanh từ')+' '+esc((x.history_from||'').slice(0,10))}${x.red_builds?' · '+x.red_builds+' '+T('red builds since','build đỏ từ đó'):''})</span>`;
  function render(){
    const c=D.counts;
    H.textContent=(document.getElementById('dkWhere')?'4 · ':'0 · ')+T('Today action inbox','Hộp việc hôm nay');
    SUB.textContent=T(`Most urgent first. Hover a chip for its rule. Snapshot ${ut(D.snap_at)}.`,`Gấp nhất ở trên. Rê chuột lên chip để xem luật. Snapshot ${ut(D.snap_at)}.`);   // round 3 (B_content #38)
    const hd=`<div class="tdy-row hd"><div>${T('Decision','Quyết định')}</div><div>${T('Object','Đối tượng')}</div><div>${T('Why','Vì sao')}</div><div>${T('Evidence','Bằng chứng')}</div></div>`;
    const vis=more?D.rows:D.rows.slice(0,D.visible),rest=D.rows.length-vis.length;
    // round 2 B4: built from the PR / CI snapshot; when it is old the rows may contradict the verdict banner above
    const sH=hOf(D.snap_at),stl=sH>48?`<div class="ux-stalebox" style="margin:0 0 8px"><b>${T(`Built from the snapshot of ${ut(D.snap_at)} (${fmtAge(sH)} old).`,`Dựng từ snapshot ${ut(D.snap_at)} (đã ${fmtAge(sH)}).`)}</b> ${T('Rows may be out of date: the verdict banner and the top blocker above use the current release data and win when they disagree.','Các dòng có thể đã cũ: banner verdict và top blocker phía trên dùng dữ liệu release hiện tại và được ưu tiên khi hai bên khác nhau.')}</div>`:'';
    const list=D.rows.length?`${stl}<div class="tdy-list${sH>48?' tdy-old':''}">${hd}${vis.map(row).join('')}</div>`+(rest>0?`<button type="button" class="tdy-more" id="tdyMore">${T(`Show ${rest} more`,`Hiện thêm ${rest}`)}</button>`:''):
      `<div class="tdy-empty">${T('Nothing needs a decision now.','Hiện không có gì cần quyết.')}</div>`;
    const foot=`<div class="tdy-foot">`+
      (c.release_decisions.length?`<div>${T(`Release Lead decisions still open: ${c.release_decisions.join(', ')}`,`Quyết định của Release Lead còn mở: ${c.release_decisions.join(', ')}`)} · <button type="button" data-goto="obs/coming">${T('Release cockpit','Release cockpit')} →</button></div>`:'')+
      `<div>${T(`${c.review_queue} PRs wait for a review; ${c.author} wait for their author`,`${c.review_queue} PR chờ review; ${c.author} PR chờ tác giả`)} · <button type="button" data-goto="obs/overlap">${T('Rebase risk','Rủi ro rebase')} →</button></div>`+
      (D.known_red.length?`<div>${T('Dev known red','Dev đỏ đã biết')}: ${D.known_red.map(redLine).join(' · ')}</div>`:'')+
      `</div>`;
    const rules=`<details class="tdy-rules"><summary>${T('How each verb is decided (decisions.py)','Mỗi động từ được quyết thế nào (decisions.py)')}</summary><dl>`+
      Object.keys(D.rules).map(v=>`<dt>${chip(v,v==='block'?'agent':'rule')}</dt><dd>${esc(L(D.rules[v]))}</dd>`).join('')+`</dl></details>`;
    // the Release Desk sections (build_desk.py) above already show verdict, $GOOD and blockers: no second Go/No-Go strip then
    // ready-for-'full' queue: one copy only, on Rebase risk (#ovReady, merged 2026-11-24); here a count + link
    const readyLine=()=>{const n=(D.ready||[]).length;return n?`<div class="tdy-foot"><div><b>${n}</b> ${T("PRs are green on CPU + GPU unit and wait for a maintainer to add 'full'","PR đã xanh CPU + GPU unit, chờ maintainer gắn 'full'")} · <button type="button" data-goto="obs/overlap">${T('Rebase risk','Rủi ro rebase')} →</button></div></div>`:'';};
    body.innerHTML=(document.getElementById('dkWhere')?'':strip())+tiles()+list+(document.getElementById('ovReady')?readyLine():readyBox())+foot+rules;
    const m=document.getElementById('tdyMore'); if(m) m.addEventListener('click',()=>{more=true;render();});
    body.querySelectorAll('.tdy-copy').forEach(b=>b.addEventListener('click',()=>copyCmd(b)));
  }
  // tooltip for [data-rule] chips anywhere on the page (Today rows and entity cards)
  const tip=document.createElement('div');tip.className='tdy-tip';tip.setAttribute('role','tooltip');
  const showTip=e=>{const t=e.target.closest&&e.target.closest('[data-rule]');if(!t){tip.style.display='none';return;}
    if(!tip.isConnected)(document.querySelector('.viz-root')||document.body).appendChild(tip);
    tip.textContent=t.getAttribute('data-rule');tip.style.display='block';const r=t.getBoundingClientRect();
    let x=r.left,y=r.bottom+6;if(x+tip.offsetWidth>innerWidth-8)x=innerWidth-8-tip.offsetWidth;if(y+tip.offsetHeight>innerHeight-8)y=r.top-6-tip.offsetHeight;
    tip.style.left=Math.max(8,x)+'px';tip.style.top=y+'px';};
  document.addEventListener('pointerover',showTip);document.addEventListener('focusin',showTip);
  document.addEventListener('scroll',()=>{tip.style.display='none';},true);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')tip.style.display='none';});
  // Releases tab: verdict per release, decision first (PRs -> features -> blockers -> evidence)
  function renderRel(){const sec=document.getElementById('relVerdict');if(!sec||!D.releases)return;
    const first=document.querySelector('section[data-view="obs"][data-tab="release"]:not(#relVerdict)');if(first&&sec.nextElementSibling!==first)first.before(sec);
    document.getElementById('relH').textContent='1 · '+T('Verdict per release','Kết luận từng release');
    document.getElementById('relSub').textContent=T('Newest first. Verdict = rule from decisions.py (hover the chip). Features = areas changed by the PRs of the tag range; dot = their CPU tests now.',
      'Mới nhất ở trên. Kết luận = luật trong decisions.py (rê chuột lên chip). Feature = nhóm bị đổi bởi các PR trong khoảng tag; chấm = test CPU của nhóm hiện tại.');
    const hd=`<div class="rel-row hd"><div>${T('Release','Release')}</div><div>${T('Verdict','Kết luận')}</div><div>${T('Features changed (PRs)','Feature bị đổi (số PR)')}</div><div>${T('Blockers','Blocker')}</div><div>${T('Evidence','Bằng chứng')}</div></div>`;
    const row=r=>`<div class="rel-row"><div>${ent(r.key,r.tag)}<div class="rel-meta">${esc((r.at||'').slice(0,10))} · ${r.n_prs} PR</div></div>`+
      `<div>${chip(r.verb,r.by)}<div class="rel-meta">${esc(L(r.short))}</div>${regLine(r.tag)}</div>`+
      `<div>${r.feats.map(([k,c,s])=>`<span class="rel-feat"><i class="${esc(s||'')}"></i>${ent(k,k.split(':')[1])}<small>${c}</small></span>`).join('')}${r.n_feats>5?`<span class="rel-meta">+${r.n_feats-5}</span>`:''}</div>`+
      `<div>${r.blockers.length?r.blockers.map(b=>`<div>${ent('pr:'+b.num,'#'+b.num)} <span class="rel-meta">${b.fix_pr?T('fixed by','sửa bởi')+' '+ent('pr:'+b.fix_pr,'#'+b.fix_pr):T('open','còn mở')}</span></div>`).join(''):`<span class="rel-meta">–</span>`}</div>`+
      `<div>${r.ev?`<a class="tdy-ev" data-ev href="${esc(r.ev)}" target="_blank" rel="noopener">${esc(L(r.evl))} ↗</a>`:''}</div></div>`;
    const nx=D.next_release;
    document.getElementById('relBody').innerHTML=`<div class="tdy-list">${hd}${D.releases.map(row).join('')}</div>`+
      (nx&&nx.tag?`<div class="tdy-foot"><div>${T('Next','Tiếp theo')}: ${nx.key?ent(nx.key,nx.tag):esc(nx.tag)} · <button type="button" data-goto="obs/coming">${T('Next release','Release tới')} →</button></div></div>`:'')+matrixBox();}
  // Registry facts (ops-app): what users really got per tag. A red publish run does not always mean nothing shipped.
  function regLine(tag){const x=D.desk&&D.desk.releases[tag];if(!x||x.verdict==='no_data')return '';
    const cls=x.n_ok===x.n_expected?'t-ok':x.n_ok?'t-do':'t-act';
    return `<div class="rel-meta" style="margin-top:3px"><span class="tdy-v ${cls}" data-rule="${esc(T('Checked in PyPI, GitHub Releases and Docker Hub (ops-app).','Kiểm tra trực tiếp PyPI, GitHub Releases, Docker Hub (ops-app).'))}" tabindex="0">${T('Registry','Registry')} ${x.n_ok}/${x.n_expected}</span>`+
      `${x.missing.length?`<span class="obsraw">`+esc(T('missing: ','thiếu: ')+x.missing.map(m=>m.label+(m.detail&&!/^(no tag|not on PyPI)$/.test(m.detail)?' ('+m.detail+')':'')).join(', '))+'</span>':''}</div>`;}
  function matrixBox(){const M=D.desk;if(!M||!M.focus.length)return '';
    const tags=M.focus.filter(t=>M.matrix[t]);const codes=M.matrix[tags[0]].map(r=>r.code);const by={};
    tags.forEach(t=>M.matrix[t].forEach(r=>{(by[r.code]=by[r.code]||{})[t]=r;}));
    const cell=r=>{if(!r||!r.expected)return '<span class="rel-meta">—</span>';if(r.present==null)return '?';
      const k=r.ok?['t-ok','✓']:r.present?['t-do','!']:['t-act','✗'];
      return `<a class="tdy-v ${k[0]}" href="${esc(r.url||'#')}" target="_blank" rel="noopener" title="${esc([r.ref,r.detail].filter(Boolean).join(' · '))}">${k[1]}</a>${!r.ok&&r.detail?`<div class="rel-meta obsraw">${esc(r.detail)}</div>`:''}`;};
    const gd=M.good;
    return `<h3 class="mx-h">${T('What users actually got (registries)','Người dùng thực sự nhận được gì (registry)')}</h3>`+
      `<p class="sub">${T('✓ present and correct · ! present but wrong (e.g. per-arch tags only, wrong version) · ✗ missing · — not expected for this kind of tag.','✓ có và đúng · ! có nhưng sai (vd. chỉ tag per-arch, sai version) · ✗ thiếu · — không yêu cầu cho loại tag này.')}`+
      (gd?` ${T('Rollback target','Bản rollback')} ($GOOD): <b>${esc(gd.tag)}</b>.`:'')+`</p>`+
      `<div class="tdy-scroll"><table class="tdy-rtab mx"><thead><tr><th>Artifact</th>${tags.map(t=>`<th>${esc(t)}</th>`).join('')}</tr></thead><tbody>`+
      codes.map(c=>`<tr><td>${esc(by[c][tags[0]].label)}</td>${tags.map(t=>`<td>${cell(by[c][t])}</td>`).join('')}</tr>`).join('')+`</tbody></table></div>`;}
  // Rebase risk tab: the same ready-for-'full' queue, first on the tab (approved first)
  function renderOv(){const sec=document.getElementById('ovReady');if(!sec)return;
    const first=document.querySelector('section[data-view="obs"][data-tab="overlap"]:not(#ovReady)');if(first&&sec.nextElementSibling!==first)first.before(sec);
    document.getElementById('ovReadyH').textContent=T("PR queue · ready for 'full'","Hàng đợi PR · sẵn sàng gắn 'full'");
    document.getElementById('ovReadySub').textContent=T('Green on DCO, code quality and GPU unit; the required MP suite has not run. "Rebase now" is above; the overlap pairs follow below.','Đã xanh DCO, code quality và GPU unit; bộ MP bắt buộc chưa chạy. "Rebase ngay" ở phía trên; các cặp PR chồng lấn ở bên dưới.');
    const b=document.getElementById('ovReadyBody');b.innerHTML=readyBox().replace('<details class="tdy-ready">','<details class="tdy-ready" open>');
    {const rows=[...b.querySelectorAll('tbody tr')],sc=b.querySelector('.tdy-scroll');if(rows.length>5&&sc){rows.slice(5).forEach(r=>r.hidden=true);   // round 3 (C_ia P4): top 5 + more
      const m=document.createElement('button');m.type='button';m.className='tdy-copy';m.textContent=T(`Show ${rows.length-5} more`,`Hiện thêm ${rows.length-5}`);m.addEventListener('click',()=>{rows.forEach(r=>r.hidden=false);m.remove();});sc.after(m);}}
    b.querySelectorAll('.tdy-copy').forEach(x=>x.addEventListener('click',()=>copyCmd(x)));}
  const start=()=>{render();renderRel();renderOv();addEventListener('langchange',()=>{render();renderRel();renderOv();});};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
</script>
<!-- TODAY:JS:END -->
"""


def put(page, start, end, block, anchor, before=True):
    if start in page:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block.strip(), page, flags=re.S)
    i = page.index(anchor) if before else page.index(anchor) + len(anchor)
    return page[:i] + block.strip() + "\n" + page[i:]


def main():
    bad = DEC.check()
    if bad:
        print("today: decisions.py rule text and docstring differ for", bad)
        return 1
    data = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    page = open(PAGE, encoding="utf-8").read()
    page = put(page, "/* TODAY:CSS:START */", "/* TODAY:CSS:END */", CSS, "/* NAV:CSS:START */")   # top level: not inside OBS CSS
    page = put(page, "<!-- TODAY:HTML:START -->", "<!-- TODAY:HTML:END -->", HTML, "<!-- OPS:HTML:START -->")
    js = JS.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    page = put(page, "<!-- TODAY:JS:START -->", "<!-- TODAY:JS:END -->", js, "</body>")
    open(PAGE, "w", encoding="utf-8").write(page)
    c = data["counts"]
    print(f"today: {c['decide']} to decide {c['by_verb']} · watch {c['watch']} {c['watch_parts']} · done {c['done']}/{c['merged_24h']}"
          f" · snapshot {at(data['snap_at'])} UTC · cards {len(data['dec'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
