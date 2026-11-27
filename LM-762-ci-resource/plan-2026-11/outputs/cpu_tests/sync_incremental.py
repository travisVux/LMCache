"""Incremental checkpoint sync for LMCache CI Observation Dashboard.

Runs in < 15 seconds. Uses 'made' timestamp as watermark checkpoint.
Fetches only delta changes from GitHub API (and Buildkite if token provided),
merges & deduplicates into report_data.json, and rebuilds the HTML dashboard.
"""
import os
import sys
import json
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "report_data.json")
HTML_FILE = os.path.join(HERE, "..", "..", "06_PR_TO_CI_VISUAL.html")
REPO = "LMCache/LMCache"
# Pruning window in days: 0 (default) = keep everything. Override with env R1130_SYNC_DAYS or --days N.
# --no-build: update report_data.json only (do not rebuild the page).
SLIDING_WINDOW_DAYS = int(os.environ.get("R1130_SYNC_DAYS") or 0)
if "--days" in sys.argv:
    SLIDING_WINDOW_DAYS = int(sys.argv[sys.argv.index("--days") + 1])
NO_BUILD = "--no-build" in sys.argv

def run_gh_json(args):
    try:
        res = subprocess.run(["gh"] + args, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except Exception as e:
        print(f"Warning: gh command failed ({args[:3]}...): {e}")
        return []

def main():
    if not os.path.exists(DATA_FILE):
        print(f"Error: {DATA_FILE} not found!")
        sys.exit(1)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    last_made = data.get("made", "2026-11-01T00:00:00Z")
    print(f"[*] Last checkpoint: {last_made}")

    # Search window: 2 days before checkpoint to catch state changes
    try:
        dt_last = datetime.fromisoformat(last_made.replace("Z", "+00:00"))
    except Exception:
        dt_last = datetime.now(timezone.utc) - timedelta(days=2)
    since_date = (dt_last - timedelta(days=2)).strftime("%Y-%m-%d")

    # 1. Incremental Merged PRs
    print(f"[*] Fetching merged PRs since {since_date}...")
    recent_merged = run_gh_json([
        "pr", "list", "--repo", REPO, "--state", "merged", "--base", "dev",
        "--search", f"merged:>={since_date}", "--json", "number,createdAt,mergedAt,title,url",
        "--limit", "100"
    ])
    merged_map = {p["n"]: p for p in data.get("merged_prs", [])}
    for p in recent_merged:
        merged_map[p["number"]] = {
            "n": p["number"],
            "c": p.get("createdAt"),
            "m": p.get("mergedAt"),
            "t": p.get("title", ""),
            "u": p.get("url", "")
        }
    data["merged_prs"] = sorted(merged_map.values(), key=lambda x: x.get("m") or x.get("c") or "")
    print(f"    -> Total merged PRs: {len(data['merged_prs'])}")

    # 2. Incremental Opened PRs
    print(f"[*] Fetching opened PRs since {since_date}...")
    recent_opened = run_gh_json([
        "pr", "list", "--repo", REPO, "--state", "all", "--base", "dev",
        "--search", f"created:>={since_date}", "--json", "number,createdAt,title,url",
        "--limit", "100"
    ])
    opened_map = {p["n"]: p for p in data.get("opened_prs", [])}
    for p in recent_opened:
        opened_map[p["number"]] = {
            "n": p["number"],
            "c": p.get("createdAt"),
            "t": p.get("title", ""),
            "u": p.get("url", "")
        }
    data["opened_prs"] = sorted(opened_map.values(), key=lambda x: x.get("c") or "")
    print(f"    -> Total opened PRs: {len(data['opened_prs'])}")

    # 3. Incremental Releases
    print("[*] Fetching recent releases...")
    recent_releases = run_gh_json(["api", f"repos/{REPO}/releases", "--paginate=false", "-q", ".[:20]"])
    rel_map = {r["tag"]: r for r in data.get("releases", [])}
    for r in recent_releases:
        tag = r.get("tag_name")
        if tag:
            rel_map[tag] = {
                "tag": tag,
                "at": r.get("published_at") or r.get("created_at"),
                "url": r.get("html_url", "")
            }
    data["releases"] = sorted(rel_map.values(), key=lambda x: x.get("at") or "")
    print(f"    -> Total releases: {len(data['releases'])}")

    # 4. Incremental publish.yml runs
    print("[*] Fetching recent publish.yml runs...")
    recent_pub = run_gh_json([
        "run", "list", "--repo", REPO, "--workflow", "publish.yml", "--limit", "30",
        "--json", "databaseId,status,conclusion,createdAt,headBranch,event,url"
    ])
    pub_map = {r["id"]: r for r in data.get("publish", [])}
    for r in recent_pub:
        pub_map[r["databaseId"]] = {
            "id": r["databaseId"],
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "created_at": r.get("createdAt"),
            "head_branch": r.get("headBranch"),
            "event": r.get("event"),
            "url": r.get("url")
        }
    data["publish"] = sorted(pub_map.values(), key=lambda x: x.get("created_at") or "")

    # 5. Incremental nightly_build.yml runs
    print("[*] Fetching recent nightly_build.yml runs...")
    recent_nightly = run_gh_json([
        "run", "list", "--repo", REPO, "--workflow", "nightly_build.yml", "--limit", "20",
        "--json", "databaseId,status,conclusion,createdAt,conclusion,url"
    ])
    nightly_map = {r["id"]: r for r in data.get("nightly", [])}
    for r in recent_nightly:
        nightly_map[r["databaseId"]] = {
            "id": r["databaseId"],
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "created_at": r.get("createdAt"),
            "url": r.get("url")
        }
    data["nightly"] = sorted(nightly_map.values(), key=lambda x: x.get("created_at") or "")

    # 6. Optional sliding-window pruning. Default 0 = keep the full history, so the CI Baseline tab
    #    (#r1130, weekly / monthly merges) never loses old PRs. Set R1130_SYNC_DAYS=N or --days N to cap it.
    now_utc = datetime.now(timezone.utc)
    if SLIDING_WINDOW_DAYS > 0:
        cutoff_date = (now_utc - timedelta(days=SLIDING_WINDOW_DAYS)).strftime("%Y-%m-%d")
        print(f"[*] Pruning data older than {cutoff_date} ({SLIDING_WINDOW_DAYS}-day sliding window)...")
        before_pr = len(data.get("merged_prs", []))
        data["merged_prs"] = [p for p in data.get("merged_prs", []) if (p.get("m") or p.get("c") or "")[:10] >= cutoff_date]
        data["opened_prs"] = [p for p in data.get("opened_prs", []) if (p.get("c") or "")[:10] >= cutoff_date]
        data["publish"] = [r for r in data.get("publish", []) if (r.get("created_at") or "")[:10] >= cutoff_date]
        data["nightly"] = [r for r in data.get("nightly", []) if (r.get("created_at") or "")[:10] >= cutoff_date]
        data["start"] = max(data.get("start", cutoff_date), cutoff_date)
        print(f"    -> Kept {len(data['merged_prs'])}/{before_pr} merged PRs within the {SLIDING_WINDOW_DAYS}-day window.")
    else:
        print(f"[*] No pruning (full history): {len(data.get('merged_prs', []))} merged PRs since {data.get('start')}.")

    # 7. Update Checkpoint Watermark
    data["end"] = now_utc.strftime("%Y-%m-%d")
    data["made"] = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[✓] Checkpoint saved: {data['made']}")

    # 7. Rebuild Model & Visualizer
    if NO_BUILD:
        print("[*] --no-build: report_data.json updated, page not rebuilt.")
        return
    print("[*] Rebuilding report model and HTML dashboard...")
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_page.py")], check=True)
    print(f"[✓] Successfully updated {HTML_FILE}!")

if __name__ == "__main__":
    main()

