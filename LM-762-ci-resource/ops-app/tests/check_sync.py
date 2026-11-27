"""Cross-tab consistency gate: every tab of the built page shows ONE snapshot. Python stdlib only.

  python -X utf8 check_sync.py [--site ../dist]       # exit 1 on any FAIL (refresh.ps1 then publishes nothing)

FAIL  data files missing or not matching manifest.json; a freshness time without a zone or later than the build;
      blocks built from different collector snapshots; Optimal CI and CI Baseline on different baseline windows;
      the same entity (stable release, merged-in-24h, open PRs) with different values on different tabs;
      PR Inspector not on origin/dev.
WARN  known gaps written to manifest.json partial_errors (shown in the header sync status): PR list truncated,
      hand-made / frozen blocks, manual sources.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
CLONE = APP.parents[1] / "third_party" / "LMCache"
FRESH_KEYS = {"made", "at", "snap_at", "bk_at", "ci_at", "collected_at", "head_at", "ov_at", "w0", "patches_at", "facts_made", "git_at"}
ISO = re.compile(r"^\d{4}-\d\d-\d\d[T ]\d\d:\d\d(:\d\d(\.\d+)?)?(Z|[+-]\d\d:?\d\d| UTC)?$")
RES = {"FAIL": [], "WARN": [], "PASS": []}


def out(kind, name, detail=""):
    RES[kind].append((name, detail))
    print(f"{kind:4}  {name}" + (f"  ({detail})" if detail else ""))


def parse(s):
    """ISO / 'YYYY-MM-DD HH:MM[ UTC]' -> aware datetime; None if not a time. Naive 'YYYY-MM-DD HH:MM' is UTC by the
    builders' convention (they say tz UTC); a 'T' time without a zone is an error the caller reports."""
    if not isinstance(s, str) or not ISO.match(s.strip()):
        return None
    t = s.strip().replace(" UTC", "").replace("Z", "+00:00")
    if " " in t and "T" not in t:
        t = t.replace(" ", "T") + ("+00:00" if not re.search(r"[+-]\d\d:?\d\d$", t) else "")
    d = dt.datetime.fromisoformat(t)
    return d if d.tzinfo else None


def minute(s):
    d = parse(s)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M") if d else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=str(APP / "dist"))
    a = ap.parse_args()
    site = Path(a.site)
    man_f = site / "data" / "manifest.json"
    if not man_f.is_file():
        out("FAIL", "manifest", f"{man_f} missing: run export_static.py")
        sys.exit(1)
    man = json.loads(man_f.read_text(encoding="utf-8"))
    built = parse(man["made"])
    B = {}
    for k, f in man["files"].items():
        p = site / f["path"]
        raw = p.read_bytes() if p.is_file() else None
        if raw is None or hashlib.sha256(raw).hexdigest() != f["sha256"]:
            out("FAIL", f"data file {k}", "missing" if raw is None else "content differs from manifest")
            continue
        B[k] = json.loads(raw.decode("utf-8"))
    out("PASS" if len(B) == len(man["files"]) else "FAIL", "every data file matches the manifest", f"{len(B)}/{len(man['files'])}, build {man['build']}")

    # times: zone present, none in the future
    bad_tz, future = [], []
    for k, d in B.items():
        if not isinstance(d, dict):
            continue
        items = [(f"{k}.{x}", v) for x, v in d.items()] + [(f"{k}.{x}.{y}", w) for x, v in d.items() if isinstance(v, dict) for y, w in v.items()]
        for path, v in items:
            if path.rsplit(".", 1)[-1] not in FRESH_KEYS or not isinstance(v, str) or not ISO.match(v.strip()):
                continue
            t = parse(v)
            if "T" in v and t is None:
                bad_tz.append(f"{path}={v}")
            elif t and built and t > built + dt.timedelta(minutes=5):
                future.append(f"{path}={v}")
    out("FAIL" if bad_tz else "PASS", "every freshness time has a zone", "; ".join(bad_tz[:5]))
    out("FAIL" if future else "PASS", "no freshness time later than the build", "; ".join(future[:5]))

    # one collector snapshot
    snap = minute((B.get("obsSnap") or {}).get("at"))
    uses = {"entData": B.get("entData", {}).get("snap_at"), "opsData": B.get("opsData", {}).get("snap_at"),
            "opsData.overlap": (B.get("opsData", {}).get("overlap") or {}).get("snap_at"), "piData": B.get("piData", {}).get("snap_at"),
            "todayData": B.get("todayData", {}).get("snap_at")}
    diff = {k: v for k, v in uses.items() if v and minute(v) != snap}
    out("FAIL" if diff else "PASS", "every tab is built from the same collector snapshot", f"obsSnap {snap}" + (f"; differ: {diff}" if diff else ""))

    # one baseline window (Optimal CI vs CI Baseline)
    s30 = (((B.get("opsData") or {}).get("opt") or {}).get("v3") or {}).get("stage_costs_30d") or {}
    r11 = (B.get("r11Data") or {}).get("window")
    w_ops = s30.get("window")
    if w_ops and r11:
        same = w_ops[0] == r11[0] and w_ops[1] <= r11[1] and (dt.date.fromisoformat(r11[1]) - dt.date.fromisoformat(w_ops[1])).days <= 1
        out("PASS" if same else "FAIL", "Optimal CI and CI Baseline read the same baseline window",
            f"Optimal CI {w_ops[0]}→{w_ops[1]} ({s30.get('src')}), CI Baseline {r11[0]}→{r11[1]}")
    else:
        out("FAIL", "baseline window present on both tabs", f"Optimal CI {w_ops}, CI Baseline {r11}")

    # same entity, same value
    desk, ops, today = (B.get("deskData") or {}).get("overview") or {}, B.get("opsData") or {}, B.get("todayData") or {}
    st = {"Desk": (desk.get("stable") or {}).get("tag"), "Coming release": (ops.get("coming") or {}).get("stable"), "Today": today.get("current")}
    out("PASS" if len(set(st.values())) == 1 else "FAIL", "same stable release on every tab", json.dumps(st))
    m24 = {"Today": (today.get("counts") or {}).get("merged_24h"), "24 h overlap": len((ops.get("overlap") or {}).get("merged") or []),
           "overlap CI": len((ops.get("overlap") or {}).get("merged_ci") or [])}
    out("PASS" if len(set(m24.values())) == 1 else "FAIL", "same 'merged in 24 h' count on every tab", json.dumps(m24))
    op = {"Coming release": (ops.get("coming") or {}).get("n_open"), "PR stages": (ops.get("prs") or {}).get("n_open")}
    nodes = ((((B.get("obsSnap") or {}).get("gh") or {}).get("prs_gql")) or {})
    nn = nodes.get("nodes") or []
    ready = sum(1 for n in nn if not n.get("isDraft") and n.get("baseRefName") == "dev")
    op["snapshot (non-draft dev PRs)"] = ready
    out("PASS" if len(set(op.values())) == 1 else "FAIL", "same open-PR count on every tab", json.dumps(op))
    warns = []

    # ── review 10.2: what the mutation test showed slipping through ──
    # freshness times at ANY depth, and windows / until that end after the build day + 1
    deep_future = []

    def walk(o, path, depth):
        if depth > 6:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and k in FRESH_KEYS | {"until"} and ISO.match(v.strip()):
                    t = parse(v)
                    # top-level freshness keys are checked strictly above; deeper "at" can be a window end (tomorrow)
                    lim = built + (dt.timedelta(minutes=5) if depth <= 1 and k != "until" else dt.timedelta(days=2))
                    if t and built and t > lim:
                        deep_future.append(f"{path}.{k}={v}")
                else:
                    walk(v, f"{path}.{k}", depth + 1)
        elif isinstance(o, list):
            for i, v in enumerate(o[:200]):
                walk(v, f"{path}[{i}]", depth + 1)
    for k, d in B.items():
        walk(d, k, 0)
    win_bad = [f"{k}.window={d['window']}" for k, d in B.items() if isinstance(d, dict) and isinstance(d.get("window"), list)
               and len(d["window"]) == 2 and isinstance(d["window"][1], str) and built
               and d["window"][1][:10] > (built + dt.timedelta(days=1)).strftime("%Y-%m-%d")]
    out("FAIL" if deep_future or win_bad else "PASS", "no time or window end after the build (any depth)", "; ".join((deep_future + win_bad)[:5]))
    r11d = B.get("r11Data") or {}
    if isinstance(r11d.get("days"), int) and isinstance(r11d.get("window"), list):
        exp = (dt.date.fromisoformat(r11d["window"][1][:10]) - dt.date.fromisoformat(r11d["window"][0][:10])).days + 1
        out("PASS" if r11d["days"] == exp else "FAIL", "CI Baseline day count matches its window", f"days {r11d['days']}, window {exp}")
    # fields every tab relies on
    need = {"todayData": ["snap_at", "made", "counts"], "opsData": ["snap_at", "made"], "entData": ["snap_at"], "piData": ["snap_at", "head"],
            "obsSnap": ["at"], "r11Data": ["window", "days"], "weeklyData": ["runs"], "gatesData": ["jobs"], "impactData": ["collected_at"]}
    missing = [f"{k}.{f}" for k, fs in need.items() for f in fs if not isinstance(B.get(k), dict) or B[k].get(f) in (None, "", [], {})]
    out("FAIL" if missing else "PASS", "required fields present and not empty", ", ".join(missing))
    # against the build that is live now: a list that went empty is a FAIL, one that lost more than half is a WARN
    live = APP / "releases" / ((APP / "releases" / "CURRENT").read_text(encoding="utf-8").strip() if (APP / "releases" / "CURRENT").is_file() else "-") / "site"
    lm = live / "data" / "manifest.json"
    if lm.is_file() and lm.resolve() != man_f.resolve():
        lman = json.loads(lm.read_text(encoding="utf-8"))
        emptied, shrank = [], []
        for k, f in lman.get("files", {}).items():
            if k not in B or not (live / f["path"]).is_file():
                continue
            old = json.loads((live / f["path"]).read_text(encoding="utf-8"))
            new = B[k]
            if not isinstance(old, dict) or not isinstance(new, dict):
                continue
            if old and not new:
                emptied.append(f"{k} (whole block)")
            for kk, ov in old.items():
                nv = new.get(kk)
                if isinstance(ov, (list, dict)) and len(ov) >= 3:
                    n_ = len(nv) if isinstance(nv, (list, dict)) else 0
                    if n_ == 0:
                        emptied.append(f"{k}.{kk} ({len(ov)} → 0)")
                    elif n_ <= len(ov) / 2 and len(ov) >= 6:
                        shrank.append(f"{k}.{kk} {len(ov)} → {n_}")
        out("FAIL" if emptied else "PASS", "no data went empty since the live build", ", ".join(emptied[:6]) + f" (live {live.parent.name})")
        if shrank:
            warns.append({"source": "size", "error": "lost more than half since the live build: " + ", ".join(shrank[:6])})
    tot = nodes.get("totalCount")
    if tot and len(nn) < tot:
        warns.append({"source": "obsSnap.prs_gql", "error": f"PR list truncated: {len(nn)} most recently updated of {tot} open PRs are analysed (pr_pages)"})

    # PR Inspector reads origin/dev
    pi = B.get("piData") or {}
    try:
        od = subprocess.run(["git", "-C", str(CLONE), "rev-parse", "origin/dev"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        od = ""
    if od:
        out("PASS" if pi.get("head") == od else "FAIL", "PR Inspector reads origin/dev", f"page {str(pi.get('head'))[:10]} ({pi.get('head_ref', 'HEAD?')}), origin/dev {od[:10]}")

    # frozen / manual blocks: allowed, but said out loud
    k3 = parse((B.get("k3MonitorData") or {}).get("made"))
    if k3 and built and built - k3 > dt.timedelta(hours=48):
        warns.append({"source": "k3MonitorData", "error": f"K3 monitor is a frozen snapshot from {k3:%Y-%m-%d} (no builder refreshes it)"})
    ta = next((x for x in (desk.get("ages") or []) if x.get("key") == "trace_agent"), None)
    if ta and ta.get("stale"):
        warns.append({"source": "trace_agent", "error": f"Trace Agent is a manual, paid run; last {str(ta.get('at'))[:10]}"})
    # review 2.1: text figures rewritten by build_ux.sync_p1 come from the first 30-day baseline (P1), not the shared one
    plan_out = APP.parent / "plan-2026-11" / "outputs"
    p1w, fw = plan_out / "P1" / "window.json", plan_out / "P1_full" / "window.json"
    if (plan_out / "P1" / "build_level_summary.json").is_file() and fw.is_file():
        try:
            a_ = json.loads(p1w.read_text(encoding="utf-8")) if p1w.is_file() else {}
            b_ = json.loads(fw.read_text(encoding="utf-8"))
            warns.append({"source": "uxData.p1", "error": "GPU figures in the page text (GPU-h, p50 / p90) are from the first baseline P1 "
                          f"({str(a_.get('since', '2026-10-05'))[:10]}→{str(a_.get('until', '2026-11-05'))[:10]}); CI Baseline / Optimal CI use "
                          f"P1_full ({str(b_.get('since'))[:10]}→{str(b_.get('until'))[:10]})"})
        except (OSError, ValueError):
            pass
    for w in warns:
        out("WARN", w["source"], w["error"])

    # record the warnings with the data (shown in the header sync status and returned by /api/sync-status)
    pe = [e for e in (man.get("partial_errors") or []) if not e.get("source", "").startswith(("obsSnap.prs_gql", "k3MonitorData", "trace_agent", "uxData.p1", "size"))]
    man["partial_errors"] = pe + warns
    man["checks"] = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "fail": len(RES["FAIL"]), "warn": len(warns)}
    man_f.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    print("RESULT:", "PASS" if not RES["FAIL"] else f"FAIL ({len(RES['FAIL'])})", f"· {len(RES['PASS'])} passed · {len(warns)} warnings")
    sys.exit(1 if RES["FAIL"] else 0)


if __name__ == "__main__":
    main()
