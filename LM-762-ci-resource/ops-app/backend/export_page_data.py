"""Bridge: write the facts the old page needs from ops.db into cpu_tests/release_desk.json (local file, no network).

The old page (06_PR_TO_CI_VISUAL.html) keeps all its tabs; build_today.py reads this file when it exists:
  releases   per tag: registry verdict, artifacts ok/expected, missing, publish runs with failed jobs + first error line
  matrix     artifact matrix for the focus tags (latest tag, stable, previous final)
  good       rollback target ($GOOD) and the rule that chose it
  lkg        per dev gate pipeline: last green build, red since, failed builds since (60 days of history)
  hints      evidence that a release decision was made in practice
  sources    age of every input the Today tab mixes
Run:  python -X utf8 export_page_data.py   (the page chain runs it too, see build_today.py)
"""
import json
import os
from datetime import datetime, timezone

import model
from config import DEV_GATE_PIPELINES, OLD, RELEASE_DIR, parse_tag
from db import connect

OUT = OLD / "release_desk.json"
CORE = model.CORE


def lkg(con):
    out = {}
    for slug in DEV_GATE_PIPELINES:
        last = model.one(con, """SELECT number, state, created_at, url FROM bk_build WHERE pipeline=? AND branch='dev'
                                 AND state IN ('passed','failed') ORDER BY created_at DESC LIMIT 1""", slug)
        if not last:
            continue
        ok = model.one(con, """SELECT number, created_at, url FROM bk_build WHERE pipeline=? AND branch='dev' AND state='passed'
                               ORDER BY created_at DESC LIMIT 1""", slug)
        since = ok["created_at"] if ok else "0"
        red = model.one(con, """SELECT COUNT(*) n, MIN(created_at) first FROM bk_build WHERE pipeline=? AND branch='dev'
                                AND state='failed' AND created_at > ?""", slug, since)
        span = model.one(con, "SELECT MIN(created_at) a FROM bk_build WHERE pipeline=? AND branch='dev'", slug)
        out[slug] = dict(last=last, green=ok, red_since=red["first"], red_builds=red["n"], history_from=span["a"])
    return out


def mtime(p):
    try:
        return datetime.fromtimestamp(os.path.getmtime(p), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        return None


def sources(con, line):
    def jget(name, *path):
        try:
            d = json.loads((OLD / name).read_text(encoding="utf-8"))
            for k in path:
                d = d[k]
            return d
        except Exception:  # noqa: BLE001 - a missing input is shown as unknown age
            return None
    ops = jget("ops_tabs.json") or {}
    r1130 = jget("report1130.json") or {}
    win = (r1130.get("window") or r1130.get("meta", {}).get("window") or [None, None]) if isinstance(r1130, dict) else [None, None]
    collect = model.one(con, "SELECT MAX(taken_at) t FROM snapshot WHERE source LIKE 'collect:%'")
    return [
        dict(key="snapshot", en="PR / CI snapshot", vi="Snapshot PR / CI", at=jget("observe_snapshot.json", "at")),
        dict(key="registries", en="Registries (PyPI, Docker Hub, GitHub)", vi="Registry (PyPI, Docker Hub, GitHub)", at=(collect or {}).get("t")),
        dict(key="trace_agent", en="Trace Agent findings", vi="Kết quả Trace Agent", at=((ops.get("ta_meta") or {}).get("updated"))),
        dict(key="release_prep", en=f"release-{line}/RELEASE_PREP.md (D1–D4, C1–C6)", vi=f"release-{line}/RELEASE_PREP.md (D1–D4, C1–C6)",
             at=mtime(RELEASE_DIR(line) / "RELEASE_PREP.md")),
        dict(key="report1130", en="Report 1130 window end", vi="Report 1130: ngày cuối cửa sổ", at=(win[-1] if win else None)),
        dict(key="cpu_tests", en="CPU test map (cpu_tests.json)", vi="Bản đồ test CPU (cpu_tests.json)", at=mtime(OLD / "cpu_tests.json")),
    ]


def main():
    con = connect()
    rel = model.rows(con, "SELECT * FROM release ORDER BY COALESCE(published_at, tagged_at) DESC, sort_key DESC")
    latest = max(rel, key=lambda r: r["sort_key"]) if rel else None
    stable = next((r for r in rel if r["kind"] in ("final", "post")), None)
    prev_final = next((r for r in rel if r["kind"] == "final" and stable and r["tag"] != stable["tag"]), None)
    rels = {}
    for r in rel[:16]:
        v = model.verdict(con, r["tag"])
        rels[r["tag"]] = dict(kind=r["kind"], at=r["published_at"] or r["tagged_at"], verdict=v["verdict"], n_ok=v["n_ok"],
                              n_expected=v["n_expected"], missing=v["missing"], publish_red=v["publish_red"],
                              runs=[dict(event=x["event"], conclusion=x["conclusion"], status=x["status"], url=x["url"],
                                         created_at=x["created_at"], failed_jobs=x["failed_jobs"]) for x in v["runs"]])
    focus = [r["tag"] for r in (latest, stable, prev_final) if r]
    line = latest["line"] if latest else None
    out = dict(
        made=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        latest=latest and latest["tag"], stable=stable and stable["tag"], line=line,
        next_rc=(f"v{line}rc{latest['seq'] + 1}" if latest and latest["kind"] == "rc" else None),
        releases=rels, focus=focus,
        matrix={t: [dict(code=x["code"], label=x["label"], expected=x["expected"], present=x["present"], ok=x["ok"],
                         ref=x["ref"], detail=x["detail"], url=x["url"]) for x in model.matrix(con, t)] for t in focus},
        good=model.good_target(con), core=list(CORE), lkg=lkg(con),
        hints=model.decision_hints(con, line, latest["tag"]) if latest else {},
        sources=sources(con, line) if line else [],
        # the page's Release Management tabs 'Now · Release Desk' and 'History' (build_desk.py) draw these directly
        overview=model.overview(con), history=model.history(con),
    )
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"release_desk.json: latest {out['latest']} · stable {out['stable']} · $GOOD {(out['good'] or {}).get('tag')} · "
          f"{len(rels)} releases · lkg {len(out['lkg'])}")


if __name__ == "__main__":
    main()
