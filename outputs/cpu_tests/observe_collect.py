"""Collect a PR / release snapshot for the "PR / Release watch" view (observe tab).

Runs the SAME requests the page makes on "Refresh" (see build_observe.CONFIG) and keeps only the
fields the page reads, so the page works offline and before anyone pastes a token.

  python -I -X utf8 observe_collect.py            # collect -> observe_snapshot.json -> rebuild page
  python -I -X utf8 observe_collect.py --no-build # collect only

GitHub: `gh` CLI (already logged in). Buildkite: env BUILDKITE_API_TOKEN, else the token in
~/.claude.json.bak-buildkite (never printed). The Buildkite connection from this machine resets
now and then (WinError 10054): every call retries.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import sys  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir
from build_observe import CONFIG, COVER_FIELDS, MSTATE_QUERY, PR_QUERY

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "observe_snapshot.json")
REPO = CONFIG["repo"]
ORG = CONFIG["bk_org"]
ERRORS = []

# ------------------------------------------------------------------ field trimming (same names as the API)
RUN = ["id", "name", "workflow_id", "head_branch", "head_sha", "event", "status", "conclusion", "created_at",
       "updated_at", "run_started_at", "run_attempt", "html_url", "display_title"]
JOB = ["name", "status", "conclusion", "started_at", "completed_at", "html_url"]
REL = ["tag_name", "name", "prerelease", "draft", "created_at", "published_at", "html_url", ("assets", [])]  # the page only counts assets
PULL = ["number", "title", "html_url", "draft", "created_at", "updated_at", ("user", ["login"]),
        ("labels", ["name", "color"]), ("base", ["ref"]), ("milestone", ["title"])]
ISSUE = ["number", "title", "html_url", ("user", ["login"]), ("labels", ["name", "color"]), ("pull_request", ["merged_at"])]
BK_PIPE = ["slug", "name", "web_url", "running_builds_count", "scheduled_builds_count", "running_jobs_count",
           "scheduled_jobs_count", "waiting_jobs_count"]
BK_JOB = ["type", "runnable_at", "started_at"]  # queue wait only
BK_BUILD = ["number", "state", "branch", "commit", "message", "source", "created_at", "scheduled_at", "started_at",
            "finished_at", "web_url", ("pull_request", ["id"]), ("author", ["name", "username"]), ("pipeline", ["slug"])]


def pick(x, spec):
    if isinstance(x, list):
        return [pick(i, spec) for i in x]
    if not isinstance(x, dict):
        return x
    out = {}
    for f in spec:
        if isinstance(f, tuple):
            k, sub = f
            if x.get(k) is not None:
                out[k] = pick(x[k], sub)
        elif f in x:
            out[f] = x[f]
    if "message" in out and isinstance(out["message"], str):
        out["message"] = out["message"].split("\n", 1)[0][:160]
    return out


# ------------------------------------------------------------------ transports
def gh(path, tries=3):
    for i in range(tries):
        p = subprocess.run(["gh", "api", "-H", "X-GitHub-Api-Version: 2022-11-28", path],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0:
            return json.loads(p.stdout)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"gh api {path}: {p.stderr.strip()[:200]}")


def gql(query, after=None, tries=3):
    args = ["gh", "api", "graphql", "-f", "query=" + query] + (["-f", "after=" + after] if after else [])
    for i in range(tries):
        p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0:
            return json.loads(p.stdout)["data"]
        time.sleep(2 * (i + 1))
    raise RuntimeError("graphql: " + p.stderr.strip()[:300])


def prs_gql():
    """Same as the page: CONFIG.pr_pages pages of 50, then mergeStateStatus for approved PRs only."""
    out, after = None, None
    for _ in range(CONFIG["pr_pages"]):
        p = gql(PR_QUERY, after)["repository"]["pullRequests"]
        out = out or dict(totalCount=p["totalCount"], nodes=[])
        out["nodes"] += p["nodes"]
        if not p["pageInfo"]["hasNextPage"]:
            break
        after = p["pageInfo"]["endCursor"]
    ap = [n["number"] for n in out["nodes"] if n["reviewDecision"] == "APPROVED" and not n["isDraft"]]
    if ap:
        d = gql(MSTATE_QUERY.replace("__PRS__", " ".join(f"p{n}:pullRequest(number:{n}){{number mergeStateStatus}}" for n in ap)))
        ms = {x["number"]: x["mergeStateStatus"] for x in d["repository"].values() if x}
        for n in out["nodes"]:
            if n["number"] in ms:
                n["mergeStateStatus"] = ms[n["number"]]
    return out


def bk_token():
    t = os.environ.get("BUILDKITE_API_TOKEN")
    if t:
        return t
    try:
        m = re.search(r"Bearer (bkua_[A-Za-z0-9]+)", open(os.path.expanduser("~/.claude.json.bak-buildkite"), encoding="utf-8").read())
        return m.group(1) if m else None
    except OSError:
        return None


TOK = bk_token()


def bk(path, tries=8):
    last = None
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.buildkite.com/v2/" + path, headers={"Authorization": "Bearer " + TOK})
            return json.load(urllib.request.urlopen(r, timeout=40))
        except Exception as e:  # noqa: BLE001 - connection resets are common here
            last = e
            time.sleep(1 + i)
    raise RuntimeError(f"buildkite {path.split('?')[0]}: {last}")


def safe(label, fn, default=None):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        ERRORS.append(f"{label}: {e}")
        print("  !", label, e)
        return default


def q(s):
    return urllib.parse.quote(s, safe="")


# ------------------------------------------------------------------ collect
def collect_github():
    G = {}
    wf = CONFIG["workflows"]
    jobs = {
        "releases": lambda: pick(gh(f"repos/{REPO}/releases?per_page=100"), REL),
        "runs_dev": lambda: pick(gh(f"repos/{REPO}/actions/runs?branch=dev&per_page=100")["workflow_runs"], RUN),
        "nightly_runs": lambda: pick(gh(f"repos/{REPO}/actions/workflows/{wf['nightly']}/runs?per_page=10")["workflow_runs"], RUN),
        "publish_dev": lambda: pick(gh(f"repos/{REPO}/actions/workflows/{wf['publish']}/runs?branch=dev&per_page=5")["workflow_runs"], RUN),
        "gha_queued": lambda: gh(f"repos/{REPO}/actions/runs?status=queued&per_page=1")["total_count"],
        "gha_running": lambda: gh(f"repos/{REPO}/actions/runs?status=in_progress&per_page=1")["total_count"],
        "prs_gql": prs_gql,
    }
    for k, s in CONFIG["counts"].items():
        jobs["count_" + k] = (lambda s=s: gh(f"search/issues?q={q('repo:' + REPO + ' ' + s)}&per_page=1")["total_count"])
    with ThreadPoolExecutor(8) as ex:
        fut = {k: ex.submit(safe, k, f) for k, f in jobs.items()}
    for k, f in fut.items():
        G[k] = f.result()
    G["counts"] = {k: G.pop("count_" + k) for k in CONFIG["counts"]}
    # trim PR contexts: keep gate checks + anything not green (the page counts failing checks)
    gate_rx = [re.compile(g["re"]) for g in CONFIG["gates"]]
    green = {"SUCCESS", "NEUTRAL", "SKIPPED"}

    def keep(x):
        name = x.get("name") or x.get("context") or ""
        done_ok = (x.get("status") == "COMPLETED" and x.get("conclusion") in green) or x.get("state") == "SUCCESS"
        return any(r.search(name) for r in gate_rx) or not done_ok
    if G.get("prs_gql"):
        for n in G["prs_gql"]["nodes"]:
            for c in n["commits"]["nodes"]:
                r = c["commit"].get("statusCheckRollup")
                if r:
                    r["contexts"]["nodes"] = [{k: v for k, v in x.items() if v is not None and k != "targetUrl" or k == "targetUrl" and "k3-unit" in (x.get("context") or "")}
                                              for x in r["contexts"]["nodes"] if keep(x)]
    # step 2: needs the release list
    rel = G.get("releases") or []
    main = [r for r in rel if re.match(CONFIG["main_tag_re"], r["tag_name"]) and not r["draft"]]
    main.sort(key=lambda r: r["published_at"] or "", reverse=True)
    stable = next((r for r in main if re.match(CONFIG["stable_tag_re"], r["tag_name"])), None)
    G["publish_tags"] = {}
    for r in main[:CONFIG["tag_runs"]]:
        t = r["tag_name"]
        G["publish_tags"][t] = safe("publish " + t, lambda t=t: pick(gh(f"repos/{REPO}/actions/workflows/{wf['publish']}/runs?branch={q(t)}&per_page=3")["workflow_runs"], RUN), [])
    if stable:
        since = stable["published_at"]
        G["merged"] = safe("merged", lambda: pick(gh(f"search/issues?q={q(f'repo:{REPO} is:pr is:merged base:dev merged:>={since}')}&per_page=100&sort=updated")["items"], ISSUE), [])
        G["merged_since"] = stable["tag_name"]
    # Fixed on dev tab: PRs merged into dev in the last COVER_DAYS + files / closed issues / merge commit
    since7 = datetime.fromtimestamp(time.time() - CONFIG["cover_days"] * 86400, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    G["merged_recent"] = safe("merged_recent", lambda: pick(gh(f"search/issues?q={q(f'repo:{REPO} is:pr is:merged base:dev merged:>={since7}')}&per_page=100&sort=updated")["items"], ISSUE), [])
    nums = list(dict.fromkeys([n["number"] for n in ((G.get("prs_gql") or {}).get("nodes") or []) if not n["isDraft"] and n["baseRefName"] == "dev"]
                              + [m["number"] for m in G["merged_recent"] or []]))
    G["pr_files"] = {}
    for i in range(0, len(nums), 40):
        ch = nums[i:i + 40]
        d = safe("pr_files", lambda ch=ch: gql(MSTATE_QUERY.replace("__PRS__", " ".join(f"p{n}:pullRequest(number:{n}){{{COVER_FIELDS}}}" for n in ch))), None)
        for p in ((d or {}).get("repository") or {}).values():
            if p:
                G["pr_files"][str(p["number"])] = dict(merge=(p.get("mergeCommit") or {}).get("oid"), files=[f["path"] for f in (p.get("files") or {}).get("nodes") or []],
                                                     issues=[x["number"] for x in (p.get("closingIssuesReferences") or {}).get("nodes") or []])
    G["publish_jobs"] = {}
    tag_runs = [x for t in G["publish_tags"].values() for x in (t or [])]
    for run in ([max(tag_runs, key=lambda r: r["created_at"])] if tag_runs else []) + (G.get("publish_dev") or [])[:1]:
        G["publish_jobs"][str(run["id"])] = safe("jobs", lambda run=run: pick(gh(f"repos/{REPO}/actions/runs/{run['id']}/jobs?per_page=100")["jobs"], JOB), [])
    rl = safe("rate", lambda: gh("rate_limit")["resources"]["core"], {})
    G["rate"] = rl.get("remaining") if rl else None
    return G


def collect_buildkite():
    if not TOK:
        ERRORS.append("buildkite: no token (set BUILDKITE_API_TOKEN)")
        return None
    B = {}
    jobs = {
        "pipelines": lambda: pick(bk(f"organizations/{ORG}/pipelines?per_page=100"), BK_PIPE),
        "dev_builds": lambda: pick(bk(f"organizations/{ORG}/builds?branch=dev&per_page=100&exclude_jobs=true"), BK_BUILD),
        "active": lambda: pick(bk(f"organizations/{ORG}/builds?state[]=running&state[]=scheduled&state[]=failing&per_page=100&exclude_jobs=true"), BK_BUILD),
    }
    for slug in CONFIG["queue_pipelines"]:
        jobs["recent_" + slug] = (lambda slug=slug: pick(bk(f"organizations/{ORG}/pipelines/{slug}/builds?per_page={CONFIG['queue_builds']}&state[]=passed&state[]=failed"),
                                                         BK_BUILD + [("jobs", BK_JOB)]))
    with ThreadPoolExecutor(4) as ex:
        fut = {k: ex.submit(safe, k, f) for k, f in jobs.items()}
    for k, f in fut.items():
        B[k] = f.result()
    B["recent"] = {s: B.pop("recent_" + s) for s in CONFIG["queue_pipelines"]}
    for bs in B["recent"].values():
        for b in bs or []:
            b["jobs"] = [j for j in b.get("jobs", []) if j.get("type") == "script" and j.get("runnable_at") and j.get("started_at")]
    return B


def main():
    t0 = time.time()
    print("collect github ...")
    G = collect_github()
    print("collect buildkite ...")
    B = collect_buildkite()
    snap = dict(at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), via="collector",
                gh=G, bk=B, errors=ERRORS, mode=dict(gql=bool(G.get("prs_gql")), bk=bool(B)))
    s = json.dumps(snap, ensure_ascii=False, separators=(",", ":"))
    open(OUT, "w", encoding="utf-8").write(s)
    print(f"snapshot {OUT}: {len(s) / 1024:.0f} KB in {time.time() - t0:.0f} s, errors={len(ERRORS)}")
    import observe_history
    observe_history.add_point(snap)  # observe_history/<day>.json for the Trend tab
    if "--no-build" not in sys.argv:
        import build_observe
        build_observe.main()
        import build_i18n
        build_i18n.main()


if __name__ == "__main__":
    main()
