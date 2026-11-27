"""Step-by-step progress of the running (or last) refresh, read from ops-app/logs/refresh-*.log.

Shared by server.py (local "Refresh data" button: GET /api/refresh/status) and deploy/web_refresh.py (web button:
pushed to Cloudflare KV while the run goes on). Python stdlib only. The page shows one row per data source:
what it updates, where from, state (pending / running / done / skipped / failed), seconds and what came in.

  python -X utf8 refresh_progress.py     # print the progress of the newest log (debug)
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
LOGS = APP_DIR / "logs"

# (id, what it updates EN, VI, source, needs Buildkite token)
STEPS = [
    ("observe_collect", "Open PRs, checks, reviews + Buildkite builds", "PR đang mở, check, review + build Buildkite", "GitHub · Buildkite", False),
    ("observe_ops_collect", "CI of the last 24 h (runs, jobs, time)", "CI 24 giờ qua (run, job, thời gian)", "GitHub Actions · Buildkite", True),
    ("git_fetch", "New tags and branches (local clone)", "Tag và nhánh mới (clone local)", "git", False),
    ("overlap_collect", "Diffs of open PRs (rebase risk)", "Diff của PR đang mở (rủi ro rebase)", "GitHub", False),
    ("mp_pr_collect", "Multiprocess test builds per PR", "Build test multiprocess theo PR", "Buildkite", True),
    ("collect_release", "Releases: tags, publish runs, PyPI, Docker Hub", "Release: tag, publish, PyPI, Docker Hub", "GitHub · PyPI · Docker Hub", False),
    ("collect_weekly", "Weekly full build (GitHub Actions + report.json)", "Weekly full build (GitHub Actions + report.json)", "GitHub Actions", False),
    ("collect_ci_impact", "CI impact: before / after the merged CI changes", "Tác động CI: trước / sau các thay đổi CI đã merge", "Buildkite · GitHub Actions", True),
    ("etl_window", "CI baseline: jobs into the lake, P1 export", "Baseline CI: job vào lake, xuất P1", "Buildkite · GitHub Actions", True),
    ("ingest_files", "Load everything into the database", "Nạp tất cả vào database", "ops.db", False),
    ("build_page", "Rebuild every tab", "Build lại các tab", "build", False),
    ("verify_page", "Check the page", "Kiểm tra trang", "check", False),
    ("build_today", "Rebuild Today", "Build lại Hôm nay", "build", False),
    ("export_static", "Export the static copy", "Xuất bản tĩnh", "build", False),
    ("check_sync", "Check every tab shows one snapshot", "Kiểm tra mọi tab cùng một snapshot", "check", False),
    ("check_app", "Check every view (desktop + phone)", "Kiểm tra mọi view (desktop + điện thoại)", "check", False),
    ("publish", "Privacy scan, go live on the release PC", "Quét privacy, đưa lên máy release", "publish", False),
    ("digest", "Daily summary", "Tóm tắt trong ngày", "digest", False),
    ("d1_push", "Copy the database to Cloudflare (one snapshot)", "Đồng bộ database lên Cloudflare (một snapshot)", "Cloudflare D1", False),
    ("d1_verify", "Check the Cloudflare database row by row", "Kiểm tra database trên Cloudflare từng dòng", "Cloudflare D1", False),
    ("pages_deploy", "Upload to the web copy", "Upload lên bản web", "Cloudflare Pages", False),
]
COLLECT = {"etl_window", "observe_collect", "observe_ops_collect", "git_fetch", "overlap_collect", "mp_pr_collect", "collect_release", "collect_weekly", "collect_ci_impact"}
TS = re.compile(r"^\ufeff?(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (.*)$")


def _note(sid, lines):
    """What came in, from the step's own output (short, numbers only; never paths)."""
    t = "\n".join(lines)
    f = lambda p: (re.search(p, t) or [None, None])[1]   # noqa: E731
    if sid == "observe_collect":
        kb, err = f(r"snapshot .*?: (\d+) KB"), f(r"errors=(\d+)")
        bk = "Buildkite: kept old data (no token)" if "buildkite: no token" in t else None
        return "; ".join(x for x in [kb and f"{kb} KB snapshot" + (f", {err} errors" if err and err != "0" else ""), bk] if x)
    if sid == "observe_ops_collect":
        a, b = f(r"gha runs (\d+)"), f(r"bk builds (\d+)")
        return a and f"{a} GitHub runs · {b or 0} Buildkite builds"
    if sid == "git_fetch":
        return f(r"exit (\d+)") == "0" and "fetched" or "fetch failed (old refs kept)"
    if sid == "overlap_collect":
        n = f(r"PRs (\d+)")
        return n and f"{n} open PRs"
    if sid == "mp_pr_collect":
        m = re.search(r"(\d+) builds \((\d+) passed\) for (\d+) PRs", t)
        return m and f"{m[1]} builds ({m[2]} passed) · {m[3]} PRs"
    if sid == "collect_release":
        a, b = f(r"github tags +(\d+)"), f(r"artifacts +(\d+)")
        return a and f"{a} tags · {b} artifacts"
    if sid == "collect_weekly":
        n = f(r"weekly runs: (\d+)")
        return n and f"{n} weekly runs"
    if sid == "collect_ci_impact":
        if "ci impact: FAILED" in t:
            return "failed, kept the last result"
        m = re.search(r"after ([\d.]+) d \((\d+) BK jobs, (\d+) GHA jobs\)", t)
        return m and f"after window {m[1]} d · {m[2]} Buildkite + {m[3]} GitHub jobs"
    if sid == "ingest_files":
        a, b = f(r"\n  pr +(\d+)"), f(r"bk_build +(\d+)")
        return a and f"{a} PRs · {b} builds in ops.db"
    if sid == "verify_page":
        return f(r"RESULT: (\w+)")
    if sid == "check_app":
        ok = len(re.findall(r"^\S+ +OK ", t, re.M))
        bad = len(re.findall(r"^\S+ +(?:FAIL|ERROR)", t, re.M))
        return ok and f"{ok} views OK" + (f", {bad} failed" if bad else "")
    if sid == "publish":
        rel, hits = f(r"live: (\S+)"), f(r"privacy scan: (\d+) hits")
        return rel and f"live {rel} · privacy {hits} hits"
    if sid == "check_sync":
        return f(r"RESULT: (.+)")
    if sid == "d1_push":
        sn, w = f(r"d1 push: snapshot (\d+)"), f(r"(\d+) rows written")
        return sn and f"snapshot {sn} · {w} rows written"
    if sid == "d1_verify":
        return "all tables equal" if "all equal to the local ops.db" in t else (f(r"(\d+ differ)") or None)
    if sid == "pages_deploy":
        n = f(r"Uploaded (\d+) files")
        return "uploaded" + (f" ({n} changed files)" if n else "")
    return None


def _running(lock):
    if not lock.exists():
        return False
    try:
        with open(lock, "r+b"):
            return False
    except PermissionError:
        return True
    except OSError:
        return False


def progress(log=None, running=None, web=False):
    """{running, started, elapsed_s, outcome, done, total, steps:[{id,en,vi,src,state,secs,note}]}.
    web=True keeps the pages_deploy row (web_refresh.py runs the upload after refresh.ps1)."""
    runs = sorted(LOGS.glob("refresh-*.log"))
    if log is None:
        if not runs:
            return None
        log = runs[-1]
    if running is None:   # the lock belongs to the newest log only
        running = _running(LOGS / "refresh.lock") and bool(runs) and Path(log).name == runs[-1].name
    rows = {s[0]: dict(id=s[0], en=s[1], vi=s[2], src=s[3], state="pending", secs=None, note=None) for s in STEPS}
    out = {s[0]: [] for s in STEPS}
    cur, cur_at, started, offline, nobk, outcome, failed_step, last_at = None, None, None, False, False, None, None, None

    def close(at, state="done"):
        nonlocal cur
        if cur:
            rows[cur]["state"] = state
            rows[cur]["secs"] = int((at - cur_at).total_seconds())
            rows[cur]["note"] = _note(cur, out[cur])
        cur = None

    for ln in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS.match(ln)
        if not m:
            if cur:
                out[cur].append(ln)
            continue
        at, msg = dt.datetime.strptime(m[1], "%Y-%m-%d %H:%M:%S"), m[2]
        last_at, started = at, started or at
        if msg.startswith("refresh start"):
            started, offline = at, "offline=True" in msg
        elif msg.startswith("STEP "):
            sid = msg[5:].strip()
            close(at)
            if sid in rows:
                cur, cur_at = sid, at
                rows[sid]["state"] = "running"
        elif msg.startswith("BUILDKITE_API_TOKEN is empty"):
            close(at)
            nobk = True
        elif msg.startswith("git fetch of the local clone"):
            close(at)
            rows["git_fetch"].update(state="done", secs=0, note=_note("git_fetch", [msg]))
        elif msg.startswith("refresh FAILED"):
            fm = re.search(r"step '(\w+)'", msg)
            failed_step = fm[1] if fm else cur
            close(at, "failed")
            if failed_step in rows and rows[failed_step]["state"] != "failed":
                rows[failed_step]["state"] = "failed"
            outcome = "failed"
        elif msg.startswith("refresh OK"):
            close(at)
            outcome = "warn" if "WARNING" in msg else "ok"
        elif msg.startswith("digest failed") or msg.startswith("web upload FAILED"):
            close(at, "failed")
        elif msg.startswith("another refresh is running"):
            outcome = "busy"
    if cur and not running:            # the run stopped without an end line (killed / PC restarted)
        close(last_at, "failed")
        outcome = outcome or "failed"
    if cur:                             # still running: live note + seconds so far
        rows[cur]["note"] = _note(cur, out[cur])
        rows[cur]["secs"] = int((dt.datetime.now() - cur_at).total_seconds())
    ended = outcome is not None or not running
    for sid, r in rows.items():
        if r["state"] == "pending" and ended and sid != "pages_deploy":
            need_bk = next(s[4] for s in STEPS if s[0] == sid)
            if offline and sid in COLLECT:
                r.update(state="skipped", note="offline run")
            elif nobk and need_bk:
                r.update(state="skipped", note="no Buildkite token")
            elif outcome == "failed":
                r.update(state="skipped", note="stopped after a failed step")
            elif sid == "check_app":
                r.update(state="skipped")
    steps = [r for r in rows.values() if r["id"] != "pages_deploy" or web or r["state"] != "pending"]
    if offline:
        steps = [r for r in steps if r["id"] not in COLLECT]
    done = sum(r["state"] in ("done", "skipped", "failed") for r in steps)
    return dict(running=bool(running and outcome is None), started=started and started.isoformat(timespec="seconds"),
                elapsed_s=int(((dt.datetime.now() if running else (last_at or started)) - started).total_seconds()) if started else None,
                outcome=outcome, done=done, total=len(steps), log=log.name, steps=steps)


if __name__ == "__main__":
    print(json.dumps(progress(web="--web" in sys.argv), ensure_ascii=False, indent=1))
