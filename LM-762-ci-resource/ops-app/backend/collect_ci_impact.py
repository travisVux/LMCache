"""Collect the Before / After CI impact of the merged CI changes into ops.db (tab #obs/impact).

  #6730 tiered pre-review CI    merged 2026-11-24 08:48 UTC  (drafts: Python 3.12 only; L1 Check code quality gates L2
                                 test.yml + cpu_device.yml; k3-unit-tests builds ready commits only, in parallel;
                                 pr_draft_cancel_buildkite.yml cancels builds when a PR goes back to draft)
  #6731 split k3-multiprocess   merged 2026-11-24 11:19 UTC  (k3-multiprocess-smoke on every PR, heavy
                                 k3-multiprocess-test bypassed on ordinary PRs except force-ci / shared CI deps /
                                 SGLang paths / benchmarks/long_doc_qa)
  #6854 weekly full build       merged 2026-11-23 07:28 UTC  (weekly_full_build.yml; runs come from collect_weekly.py)

v0     = the live "before" window: the baseline_days (ci_versions.json, default 30) before the FIRST merge of v1's
         start PRs. Fetched live on every run, like the versions (no frozen report tables).
v1..   = from (latest start-PR merge + burn-in) to the next version start / now.
All windows come from the same fetch, normalized into the columns of the P1 tables with the same GPU-per-workload
map (P1 build_jobs_table.py), then ci_impact.py computes every window with the same functions. The only gap is the
switch-over itself (first start-PR merge -> last merge + burn-in).

Reads: Buildkite REST (BUILDKITE_API_TOKEN from deploy/ops-app.env, read-only calls), GitHub through `gh api`
(read-only). Writes: ops.db tables ci_impact_metric / ci_impact_meta, cache in data/ci_impact_cache/ (normalized
After rows as CSV, PR timelines, finished GitHub runs). Never prints a token.

  python -X utf8 collect_ci_impact.py              # fetch After, compute, store
  python -X utf8 collect_ci_impact.py --offline    # recompute from the cache only (no network)
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.error
import urllib.request

import ci_impact as M
from config import APP, REPO
from db import connect, now_iso, upsert

P1 = APP.parent / "plan-2026-11" / "outputs" / "P1_2026-10-17"
CACHE = APP / "data" / "ci_impact_cache"
VERSIONS = APP / "backend" / "ci_versions.json"   # v1, v2, ... (v0 = baseline_days before v1)
HEADLINE = ["gpu_h_per_push", "retry_waste_gpu", "l12_done_p50", "gpu_queue_p50", "weekly_pass", "weekly_mp_fail"]   # pillars: cheaper x2 · faster x2 · safer x2 (order review 2026-11-26)
PIPES = (M.UNIT, M.MP, M.SMOKE)
EXTRA_GPU = {"client_wheel": 1,   # smoke-pipeline.yml: pod-1gpu-dshm
             "p2p_write": 1, "sleep_mode": 1}   # multiprocess/pipeline.yml (dev, 2026-11-26): pod-1gpu; added after the P1 map
SHARED = re.compile(r"^(\.buildkite/k3_tests/|\.buildkite/k3_harness/|pyproject\.toml$|setup\.py$|requirements/|Dockerfile|docker/)")
SGLANG = re.compile(r"^(lmcache/integration/sglang/|lmcache/v1/common/kv_format/detectors/sglang\.py$)")
LDQA = re.compile(r"^benchmarks/long_doc_qa/")

sys.path.insert(0, str(P1))
from build_jobs_table import GPU as P1_GPU, keep as p1_keep, parse_label  # noqa: E402  (same map + labels as the baseline)


# ---------------------------------------------------------------- io helpers
def load_env():
    f = APP / "deploy" / "ops-app.env"
    if f.is_file():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            t = line.strip()
            if t and not t.startswith("#") and "=" in t:
                k, v = t.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def jload(p, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def jsave(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def gh(path, method_args=()):
    for i in range(4):   # GitHub answers 502 / 503 / 504 now and then on long lists: wait and ask again
        out = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", *method_args, path], capture_output=True, timeout=300)
        err = out.stderr.decode("utf-8", "replace")
        if not out.returncode or not re.search(r"HTTP 50[234]|timeout|EOF", err) or i == 3:
            break
        time.sleep(5 * (i + 1))
    if out.returncode:
        raise RuntimeError(f"gh api {path[:80]}: {out.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return json.loads(out.stdout.decode("utf-8") or "null")


def gql(query):
    """Returns the JSON even when GitHub reports per-field errors (a number that is an issue, not a PR): those fields are null."""
    out = subprocess.run(["gh", "api", "graphql", "--input", "-"], input=json.dumps({"query": query}).encode(), capture_output=True, timeout=300)
    try:
        return json.loads(out.stdout.decode("utf-8") or "null") or {}
    except ValueError:
        raise RuntimeError(f"gh graphql: {out.stderr.decode('utf-8', 'replace').strip()[:200]}") from None


def bk(path):
    """Buildkite GET with pagination; yields JSON items."""
    tok = os.environ.get("BUILDKITE_API_TOKEN")
    if not tok:
        raise RuntimeError("BUILDKITE_API_TOKEN is empty (deploy/ops-app.env)")
    url = path if path.startswith("https://") else "https://api.buildkite.com/v2/" + path
    while url:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
        for i in range(8):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = json.loads(r.read().decode("utf-8"))
                    link = r.headers.get("Link") or ""
                break
            except urllib.error.HTTPError as e:
                # 429 (shared rate limit: refresh.ps1 runs collectors in parallel) and 5xx are retried; 4xx is final
                if (e.code != 429 and e.code < 500) or i == 7:
                    raise
                reset = e.headers.get("RateLimit-Reset") if e.code == 429 else None
                time.sleep(min(int(reset) + 1, 65) if reset and reset.isdigit() else 2 + 2 * i)
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if i == 7:
                    raise
                time.sleep(2 + 2 * i)
        yield from (data if isinstance(data, list) else [data])
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None


# ---------------------------------------------------------------- windows
def cutoffs(offline, prs):
    f = CACHE / "cutoffs.json"
    c = jload(f, {}) or {}
    if not offline:
        for n in prs:
            if not (c.get(str(n)) or {}).get("merged_at"):   # unmerged PRs are asked again on every run
                p = gh(f"repos/{REPO}/pulls/{n}")
                c[str(n)] = dict(merged_at=p.get("merged_at"), sha=(p.get("merge_commit_sha") or "")[:8], title=p.get("title"), url=p.get("html_url"))
        jsave(f, c)
    return c


def read_csv(p):
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- After: Buildkite
def keep(slug, name):
    if slug == M.SMOKE:
        return name.startswith(":zap:")
    return p1_keep(slug, name)


def flatten(builds):
    """Raw Buildkite builds -> rows with the columns of jobs_all_30d.csv (same rules as P1 build_jobs_table.py)."""
    rows = []
    for b in builds:
        slug = b["pipeline_slug"]
        is_pr = b.get("pull_request") is not None
        for j in b.get("jobs") or []:
            if j.get("type") != "script" or not j.get("name") or not keep(slug, j["name"]):
                continue
            w, eng, mode, tr = parse_label(j["name"])
            g = P1_GPU.get(w, EXTRA_GPU.get(w))
            st, fi, ru = M.ts(j.get("started_at")), M.ts(j.get("finished_at")), M.ts(j.get("runnable_at"))
            wall = (fi - st).total_seconds() / 60 if st and fi else None
            q = (st - ru).total_seconds() / 60 if st and ru else None
            rows.append(dict(
                pipeline=slug, build_number=b["number"], build_state=b["state"], is_pr=int(is_pr),
                pr=(b.get("pull_request") or {}).get("id", ""), branch=b.get("branch") or "", build_created=b["created_at"],
                commit=b.get("commit") or "", build_url=b.get("web_url") or "", job_id=j["id"], label=j["name"], workload=w,
                gpus="" if g is None else g, state=j.get("state"), exit_status=j.get("exit_status"), soft_failed=j.get("soft_failed"),
                retried=j.get("retried"), retried_in_job_id=j.get("retried_in_job_id") or "", runnable_at=j.get("runnable_at"),
                started_at=j.get("started_at"), finished_at=j.get("finished_at"),
                wall_min=None if wall is None else round(wall, 3), queue_wait_min=None if q is None else round(q, 3),
                gpu_min=None if (wall is None or g is None) else round(wall * g, 3)))
    return rows


FINAL = ("passed", "failed", "canceled", "skipped", "not_run")


def fetch_bk(since, offline=False):
    """All builds of PIPES created since `since`. Cached per build: finished builds created more than 3 days before the
    last fetch are kept; newer or unfinished ones are asked again (a retry can still change a recent build)."""
    f = CACHE / "bk_builds.json"
    c = jload(f, {}) or {}
    if not offline:
        for slug in PIPES:
            have = [b for b in c.values() if b["pipeline_slug"] == slug and b.get("created_at", "") >= since]
            old = min((b["created_at"] for b in have), default=None)
            cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
            open_ = min((b["created_at"] for b in have if b.get("state") not in FINAL), default=cut)
            frm = since if (not old or old > dt_plus(since, 1)) else min(cut, open_)
            q = urllib.parse.urlencode(dict(created_from=frm, per_page=100, include_retried_jobs="true"))
            n = 0
            for b in bk(f"organizations/lmcache/pipelines/{slug}/builds?{q}"):
                b["pipeline_slug"] = slug
                b.pop("meta_data", None)
                for j in b.get("jobs") or []:
                    for x in ("agent", "artifacts_url", "log_url", "raw_log_url", "command", "step", "agent_query_rules"):
                        j.pop(x, None)
                c[f"{slug}#{b['number']}"] = b
                n += 1
            print(f"buildkite {slug}: {n} builds since {frm[:16]} ({len(have)} cached)")
        jsave(f, c)
    return [b for b in c.values() if (b.get("created_at") or "") >= since]


def dt_plus(t, days):
    return (M.ts(t) + dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def mp_decisions(builds, rows, offline):
    """Heavy-tier decision of each After PR build of k3-multiprocess-test: heavy / bypassed / path_skip (+ why heavy ran)."""
    ann_f = CACHE / "mp_annotations.json"
    ann = jload(ann_f, {}) or {}
    files_f = CACHE / "pr_files.json"
    files = jload(files_f, {}) or {}
    ran = {(r["pipeline"], str(r["build_number"])) for r in rows if r.get("started_at")}
    out = []
    for b in builds:
        if b["pipeline_slug"] != M.MP or not b.get("pull_request") or b.get("state") in ("scheduled", "running", "creating", "canceling"):
            continue
        k = str(b["number"])
        if k not in ann and not offline:
            try:
                ann[k] = [a.get("context") for a in bk(f"organizations/lmcache/pipelines/{M.MP}/builds/{k}/annotations")]
            except Exception as e:  # noqa: BLE001
                print("annotations", k, e)
                continue
        ctx = ann.get(k) or []
        if (M.MP, k) in ran:
            dec = "heavy"
        elif "mp-heavy-skip" in ctx:
            dec = "bypassed"
        elif "skip expensive ci" in ctx:
            dec = "skip_expensive"
        elif "path-filter-skip" in ctx:
            dec = "path_skip"
        else:
            dec = "no_jobs"            # cancelled before the upload step decided, or failed upload
        pr = str(b["pull_request"].get("id") or "")
        reasons = []
        if dec == "heavy":
            labels = [x.strip() for x in str(b["pull_request"].get("labels") or "").split(",")] if isinstance(b["pull_request"].get("labels"), str) else list(b["pull_request"].get("labels") or [])
            if "force-ci" in labels:
                reasons.append("force_ci")
            if "full" in labels:
                reasons.append("full_label")
            if pr and pr not in files and not offline:
                try:
                    fl = []
                    page = 1
                    while True:
                        chunk = gh(f"repos/{REPO}/pulls/{pr}/files?per_page=100&page={page}")
                        fl += [x["filename"] for x in chunk or []]
                        if len(chunk or []) < 100:
                            break
                        page += 1
                    files[pr] = fl
                except Exception as e:  # noqa: BLE001
                    print("pr files", pr, e)
            fl = [f for f in files.get(pr) or [] if not f.endswith(".md")]
            if any(SHARED.match(f) for f in fl):
                reasons.append("shared_ci_deps")
            if any(SGLANG.match(f) for f in fl):
                reasons.append("sglang")
            if any(LDQA.match(f) for f in fl):
                reasons.append("long_doc_qa")
            if not reasons:
                reasons.append("other")   # branch older than the split (old pipeline), MP_FULL_ON_PR, or files changed since
        out.append(dict(number=k, pr=pr, decision=dec, reasons=reasons, created=b.get("created_at")))
    jsave(ann_f, ann)
    jsave(files_f, files)
    return out


# ---------------------------------------------------------------- After: GitHub Actions (Code Quality = L1 + L2)
L2_PREFIX = {"Test": "Test", "CPU device": "CPU Device Tests"}


OLD_L2 = {"test.yml": "Test", "cpu_device.yml": "CPU Device Tests"}   # before #6730 L2 ran as its own workflows


def fetch_gha(since, offline, pr_of_sha, pr_of_branch=None, wf_file="code_quality_checks.yml", until=None):
    """Runs of one workflow (PR events) since `since` (until `until`) with their jobs -> rows of the P1 gh_jobs columns.
    Code Quality jobs named 'Test / x' / 'CPU device / x' are the L2 workflows called by L1 (#6730); a run of
    test.yml / cpu_device.yml (before #6730) gives rows of that workflow."""
    fixed_wf = OLD_L2.get(wf_file)
    runs_f = CACHE / ("gha_runs.json" if not fixed_wf else f"gha_runs_{wf_file.split('.')[0]}.json")
    cache = jload(runs_f, {}) or {}
    if not offline:
        runs, lo = [], M.ts(since)
        end = M.ts(until) if until else dt.datetime.now(dt.timezone.utc)
        while lo < end:   # the runs list stops at 1000 results: ask 5 days at a time
            hi = min(lo + dt.timedelta(days=5), end)
            page = 1
            while True:
                rng = f"{lo:%Y-%m-%dT%H:%M:%SZ}..{hi:%Y-%m-%dT%H:%M:%SZ}"
                j = gh(f"repos/{REPO}/actions/workflows/{wf_file}/runs?event=pull_request&per_page=100&page={page}&created={urllib.parse.quote(rng)}")
                rs = j.get("workflow_runs") or []
                runs += rs
                if len(rs) < 100:
                    break
                page += 1
            lo = hi
        seen = set()
        runs = [r for r in runs if not (r["id"] in seen or seen.add(r["id"]))]
        print(f"github: {len(runs)} {wf_file} runs since {since[:16]}")
        if fixed_wf:
            jsave(CACHE / f"gha_list_{wf_file.split('.')[0]}.json", sorted(str(r["id"]) for r in runs))
        for r in runs:
            k = str(r["id"])
            old = cache.get(k)
            if old:
                old["run"]["head_owner"] = ((r.get("head_repository") or {}).get("owner") or {}).get("login")
            if old and old["run"].get("status") == "completed" and old["run"].get("run_attempt") == r.get("run_attempt"):
                continue
            jobs, page = [], 1
            while True:
                jj = gh(f"repos/{REPO}/actions/runs/{k}/jobs?filter=all&per_page=100&page={page}")
                js = jj.get("jobs") or []
                jobs += js
                if len(js) < 100:
                    break
                page += 1
            keep_r = {x: r.get(x) for x in ("id", "status", "conclusion", "created_at", "head_sha", "head_branch", "run_attempt", "html_url")}
            keep_r["pr"] = (r.get("pull_requests") or [{}])[0].get("number") if r.get("pull_requests") else None
            keep_r["head_owner"] = ((r.get("head_repository") or {}).get("owner") or {}).get("login")
            if len(cache) % 50 == 0:
                jsave(runs_f, cache)   # a long first fetch keeps what it has if it stops
                left = (gh("rate_limit").get("resources") or {}).get("core", {}).get("remaining", 9999)
                if left < 300:   # leave room for the other collectors; the next refresh goes on from the cache
                    raise RuntimeError(f"GitHub API budget low ({left} left): {wf_file} backfill paused at {len(cache)} runs, kept in the cache")
            cache[k] = dict(run=keep_r, jobs=[{x: j.get(x) for x in ("id", "name", "status", "conclusion", "created_at", "started_at", "completed_at", "run_attempt")} for j in jobs])
        jsave(runs_f, cache)
    # most runs come from fork branches: GitHub leaves pull_requests empty, so map the head commit to its PR
    sha_f = CACHE / "pr_of_sha.json"
    sha_pr = jload(sha_f, {}) or {}
    for v in cache.values():
        s = v["run"].get("head_sha")
        br = f"{v['run'].get('head_owner')}:{v['run'].get('head_branch')}"
        if s and not v["run"].get("pr") and s not in pr_of_sha and s not in sha_pr and br not in (pr_of_branch or {}) and not offline:
            try:
                ps = gh(f"repos/{REPO}/commits/{s}/pulls")
                sha_pr[s] = (ps or [{}])[0].get("number") if ps else None
            except RuntimeError as e:
                print("commit pulls", s[:8], e)
    jsave(sha_f, sha_pr)
    rows = []
    for k, v in cache.items():
        r = v["run"]
        pr = (r.get("pr") or pr_of_sha.get(r.get("head_sha")) or sha_pr.get(r.get("head_sha"))
              or (pr_of_branch or {}).get(f"{r.get('head_owner')}:{r.get('head_branch')}") or (pr_of_branch or {}).get(r.get("head_branch") or ""))
        if not pr:
            continue
        for j in v["jobs"]:
            if not j.get("started_at") or j.get("conclusion") in (None, "skipped"):
                if j.get("conclusion") == "skipped" and j.get("name") == "Check code quality" and not fixed_wf:
                    rows.append(dict(run=k, pr=pr, commit=r["head_sha"], workflow="Code Quality", event="pull_request", job="Check code quality",
                                     conclusion="SKIPPED", suite_created=r["created_at"], started=None, completed=None, exec_min=0, attempt=j.get("run_attempt") or 1))
                continue
            name = j["name"]
            wf, job = fixed_wf or "Code Quality", name
            if " / " in name and not fixed_wf:
                head, rest = name.split(" / ", 1)
                if head in L2_PREFIX:
                    wf, job = L2_PREFIX[head], rest
            em = M.mins(j["started_at"], j.get("completed_at"))
            rows.append(dict(run=k, pr=pr, commit=r["head_sha"], workflow=wf, event="pull_request", job=job, conclusion=(j.get("conclusion") or "").upper(),
                             suite_created=r["created_at"], started=j["started_at"], completed=j.get("completed_at"),
                             exec_min=None if em is None else round(max(em, 0.0), 2), attempt=j.get("run_attempt") or 1))
    inwin = [v for v in cache.values() if (v["run"].get("created_at") or "") >= since]
    mapped = sum(1 for v in inwin if v["run"].get("pr") or pr_of_sha.get(v["run"].get("head_sha")) or sha_pr.get(v["run"].get("head_sha"))
                 or (pr_of_branch or {}).get(f"{v['run'].get('head_owner')}:{v['run'].get('head_branch')}") or (pr_of_branch or {}).get(v["run"].get("head_branch") or ""))
    return rows, dict(runs=len(inwin), mapped=mapped)


def draft_cancel_runs(since, offline):
    f = CACHE / "draft_cancel.json"
    if offline:
        return jload(f, []) or []
    j = gh(f"repos/{REPO}/actions/workflows/pr_draft_cancel_buildkite.yml/runs?per_page=100&created=%3E%3D{since[:19]}Z")
    out = [dict(id=r["id"], created_at=r["created_at"], conclusion=r.get("conclusion"), pr=(r.get("pull_requests") or [{}])[0].get("number") if r.get("pull_requests") else None)
           for r in j.get("workflow_runs") or []]
    jsave(f, out)
    return out


# ---------------------------------------------------------------- PR draft timelines (both windows)
def timelines(prs, offline, refresh):
    """{pr: dict(is_draft, events=[(iso, 'ready'|'draft')])}; PRs in `refresh` are fetched again (After window)."""
    f = CACHE / "pr_timeline.json"
    tl = jload(f, {}) or {}
    need = sorted({int(p) for p in prs if str(p).isdigit() and (str(p) not in tl or str(p) in refresh)})
    if not offline:
        for i in range(0, len(need), 40):
            chunk = need[i:i + 40]
            q = "query{repository(owner:\"%s\",name:\"%s\"){%s}}" % (*REPO.split("/"), " ".join(
                f"p{n}:pullRequest(number:{n}){{number isDraft timelineItems(itemTypes:[READY_FOR_REVIEW_EVENT,CONVERT_TO_DRAFT_EVENT],first:100){{nodes{{__typename ... on ReadyForReviewEvent{{createdAt}} ... on ConvertToDraftEvent{{createdAt}}}}}}}}"
                for n in chunk))
            try:
                d = (gql(q).get("data") or {}).get("repository") or {}
            except RuntimeError as e:
                print("timeline", e)
                continue
            for k, v in d.items():
                if not v:
                    continue
                ev = [(x["createdAt"], "ready" if x["__typename"] == "ReadyForReviewEvent" else "draft") for x in (v.get("timelineItems") or {}).get("nodes") or [] if x]
                tl[str(v["number"])] = dict(is_draft=v.get("isDraft"), events=sorted(ev))
        jsave(f, tl)
        print(f"pr timelines: {len(need)} fetched, {len(tl)} cached")
    return tl


def draft_fn(tl):
    def draft(pr, t):
        x = tl.get(str(pr))
        if not x or not t:
            return None
        ev = x["events"]
        if not ev:
            return bool(x["is_draft"])
        state = ev[0][1] == "ready"          # first event "ready" -> it was a draft before; first "draft" -> it was ready
        for at, kind in ev:
            if at <= t:
                state = kind == "draft"
            else:
                break
        return state
    return draft


def conversions(tl, since, until):
    """[(pr, went_to_draft_at, ready_again_at or None)] for conversions inside [since, until)."""
    out = []
    for pr, x in tl.items():
        ev = x["events"]
        for i, (at, kind) in enumerate(ev):
            if kind == "draft" and since <= at < until:
                nxt = next((t for t, k in ev[i + 1:] if k == "ready"), None)
                out.append((pr, at, nxt))
    return out


# ---------------------------------------------------------------- weekly (collect_weekly.py fills these tables)
def weekly_summary(con, since, until="9999"):
    rs = con.execute("SELECT run_number, verdict, created_at FROM weekly_gha_run WHERE created_at >= ? AND created_at < ? ORDER BY created_at DESC", (since, until)).fetchall()
    fin = [r for r in rs if r["verdict"] in ("passed", "failed", "timed_out")]
    p = sum(r["verdict"] == "passed" for r in fin)
    last = fin[0] if fin else None
    lanes = []
    if last:
        lr = con.execute("SELECT run_id, url FROM weekly_gha_run WHERE run_number = ? ORDER BY created_at DESC LIMIT 1", (last["run_number"],)).fetchone()
        if lr:
            lanes = [dict(device=x["device"], state=x["state"]) for x in con.execute("SELECT device, state FROM weekly_gha_lane WHERE run_id = ? ORDER BY device", (lr["run_id"],))]
    return dict(runs=len(rs), finished=len(fin), passed=p, failed=len(fin) - p, other=len(rs) - len(fin),
                pass_pct=100 * p / len(fin) if fin else None, latest=f"#{last['run_number']} {last['verdict']} {last['created_at'][:10]}" if last else None,
                last_number=last["run_number"] if last else None, last_verdict=last["verdict"] if last else None, last_at=last["created_at"] if last else None,
                last_url=(lr["url"] if last and lr else None), last_lanes=lanes, running=sum(r["verdict"] == "running" for r in rs))


# ---------------------------------------------------------------- store
def store(con, base, vers, meta):
    """ci_impact_version (v0 + each version), ci_impact_def (one row per metric), ci_impact_value (metric x version)."""
    for t in ("ci_impact_value", "ci_impact_def", "ci_impact_version", "ci_impact_metric", "ci_impact_meta"):
        con.execute(f"DELETE FROM {t}")
    upsert(con, "ci_impact_version", dict(id="v0", ord=0, title_en=base["title"][0], title_vi=base["title"][1], prs="[]",
                                          since=base["since"], until=base["until"], days=round(base["days"], 2)), ["id"])
    for i, v in enumerate(vers, 1):
        upsert(con, "ci_impact_version", dict(id=v["id"], ord=i, title_en=v["title"][0], title_vi=v["title"][1], prs=json.dumps(v["prs"]),
                                              since=v["since"], until=v["until"], days=round(v["days"], 2)), ["id"])
    first = vers[0]["rows"]
    for i, r in enumerate(first):
        upsert(con, "ci_impact_def", dict(key=r["key"], ord=i, family=r["family"], label_en=r["label"][0], label_vi=r["label"][1], unit=r["unit"],
                                          better=r["better"], min_n=r["min_n"], after_only=int(bool(r["after_only"])),
                                          headline=HEADLINE.index(r["key"]) + 1 if r["key"] in HEADLINE else 0), ["key"])
        if not r["after_only"]:
            upsert(con, "ci_impact_value", dict(key=r["key"], version="v0", value=r["before"], n=r["n_before"], status="baseline",
                                                d_base=None, d_base_pct=None, d_prev=None, d_prev_pct=None, note=None), ["key", "version"])
    prev = {r["key"]: r["before"] for r in first}
    for v in vers:
        for r in v["rows"]:
            ok = r["status"] != "insufficient" and r["after"] is not None
            p = prev.get(r["key"])
            dp = round(r["after"] - p, 2) if ok and p is not None else None
            upsert(con, "ci_impact_value", dict(key=r["key"], version=v["id"], value=r["after"], n=r["n_after"], status=r["status"],
                                                d_base=r["delta"], d_base_pct=r["delta_pct"], d_prev=dp, d_prev_pct=round(100 * dp / p, 1) if dp is not None and p else None,
                                                note=json.dumps(r["note"], ensure_ascii=False) if r["note"] else None), ["key", "version"])
            if ok:
                prev[r["key"]] = r["after"]
    for k, v in meta.items():
        upsert(con, "ci_impact_meta", dict(key=k, value=json.dumps(v, ensure_ascii=False)), ["key"])
    con.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    load_env()
    CACHE.mkdir(parents=True, exist_ok=True)
    now = now_iso()
    conf = json.loads(VERSIONS.read_text(encoding="utf-8"))
    cfg = conf["versions"]
    cut = cutoffs(a.offline, sorted({n for v in cfg for n in v["prs"]}))
    meta_f = CACHE / "after_meta.json"
    until_all = now if not a.offline else (jload(meta_f, {}) or {}).get("until", now)
    vers, first_merge = [], None
    for v in cfg:   # a version is live once all its start PRs are merged; the first one that is not stops the list
        ms = [(cut.get(str(n)) or {}).get("merged_at") for n in v["start_prs"]]
        if not all(ms):
            print(f"ci impact: {v['id']} not live yet (start PR not merged)")
            break
        first_merge = first_merge or min(ms)
        st = M.ts(max(ms)) + dt.timedelta(hours=v.get("burn_in_hours", 24))   # burn-in: branches and caches catch up
        vers.append(dict(v, merged=max(ms), since=st.strftime("%Y-%m-%dT%H:%M:%SZ")))
    if not vers:
        print("ci impact: no live version (run once online)")
        return 1
    vers.sort(key=lambda v: v["since"])
    for i, v in enumerate(vers):
        v["until"] = vers[i + 1]["since"] if i + 1 < len(vers) else until_all
    # v0: the live window before v1 (baseline_days before the first start-PR merge)
    bdays = conf.get("baseline_days", 30)
    base = dict(since=dt_plus(first_merge, -bdays), until=M.ts(first_merge).strftime("%Y-%m-%dT%H:%M:%SZ"),
                title=[f"Before v1 ({bdays} days before #{min(cfg[0]['start_prs'], key=lambda n: cut[str(n)]['merged_at'])})",
                       f"Trước v1 ({bdays} ngày trước #{min(cfg[0]['start_prs'], key=lambda n: cut[str(n)]['merged_at'])})"])
    # one fetch for every window (v0 + versions), normalized to the P1 columns, then cut per window
    builds = fetch_bk(base["since"], a.offline)
    if not a.offline:
        jsave(meta_f, dict(until=until_all))
    rows_all = flatten(builds)
    since0 = vers[0]["since"]

    def in_base(t):
        x = M.ts(t)
        return bool(x) and M.ts(base["since"]) <= x < M.ts(base["until"])
    bk_b = [r for r in rows_all if in_base(r.get("build_created"))]
    bk_a = [r for r in rows_all if (r.get("build_created") or "") >= since0]
    write_csv(CACHE / "jobs_before.csv", bk_b)
    write_csv(CACHE / "jobs_after.csv", bk_a)
    pr_of_sha = {r["commit"]: r["pr"] for r in rows_all if r.get("pr") and r.get("commit")}
    pr_of_branch = {b.get("branch"): str((b.get("pull_request") or {}).get("id")) for b in builds if b.get("pull_request") and b.get("branch")}
    gha_all, _ = fetch_gha(base["since"], a.offline, pr_of_sha, pr_of_branch)
    gha_b = [r for r in gha_all if in_base(r.get("suite_created"))]
    backfill = {}
    for wf in OLD_L2:
        try:
            old_rows, _ = fetch_gha(base["since"], a.offline, pr_of_sha, pr_of_branch, wf_file=wf, until=base["until"])
        except RuntimeError as e:   # budget pause: use the cache, the check below decides
            print("ci impact:", e)
            old_rows, _ = fetch_gha(base["since"], True, pr_of_sha, pr_of_branch, wf_file=wf, until=base["until"])
        want = set(jload(CACHE / f"gha_list_{wf.split('.')[0]}.json", []) or [])
        have = set((jload(CACHE / f"gha_runs_{wf.split('.')[0]}.json", {}) or {}).keys())
        backfill[wf] = dict(have=len(want & have), want=len(want))
        gha_b += [r for r in old_rows if in_base(r.get("suite_created"))]
    l2_ready = all(x["want"] and x["have"] >= x["want"] for x in backfill.values())
    if not l2_ready:   # a partial v0 would compare against too few test / CPU jobs: those v0 numbers stay empty
        gha_b = [r for r in gha_b if r.get("workflow") not in M.L2_WF]
        print(f"ci impact: v0 test / CPU backfill {backfill}: their v0 numbers stay empty")
    for r in gha_b:   # L1 and L2 were separate runs before #6730: group a commit's jobs per (PR, commit) as the P1 tables do
        r["run"] = ""
    gha_a = [r for r in gha_all if (r.get("suite_created") or "") >= since0]
    _, gcov = fetch_gha(since0, True, pr_of_sha, pr_of_branch)   # coverage of the latest windows (cache only)
    write_csv(CACHE / "gh_jobs_before.csv", gha_b)
    write_csv(CACHE / "gh_jobs_after.csv", gha_a)
    mpd = mp_decisions([b for b in builds if (b.get("created_at") or "") >= since0], bk_a, a.offline)
    prs_b = {str(r["pr"]) for r in bk_b if r.get("pr")} | {str(r["pr"]) for r in gha_b if r.get("pr")}
    prs_a = {str(r["pr"]) for r in bk_a if r.get("pr")} | {str(r["pr"]) for r in gha_a if r.get("pr")}
    tl = timelines(prs_b | prs_a, a.offline, refresh=prs_a)
    draft = draft_fn(tl)
    dcr = draft_cancel_runs(since0, a.offline)

    con = connect()
    nb = M.window_numbers(dict(base, bk=bk_b, gha=gha_b, draft=draft, conv=conversions(tl, base["since"], base["until"])))
    base["days"] = nb["days"]
    if not l2_ready:
        for k in ("gha_draft_min_day", "gha_ready_min_day", "gha_ready_per_push", "gha_draft_per_push", "cpu_after_test_fail_day"):
            nb[k] = None
        for k in ("l2_start", "l12_done", "l1_l2_gap"):
            nb[k] = (None, None, 0)
        nb["stop_rate"] = (None, 0)
    for v in vers:
        lo, hi = M.ts(v["since"]), M.ts(v["until"])

        def inw(t, lo=lo, hi=hi):
            x = M.ts(t)
            return bool(x) and lo <= x < hi
        bk_i = [r for r in bk_a if inw(r.get("build_created"))]
        b_i = [b for b in builds if inw(b.get("created_at"))]
        conv_i = conversions(tl, v["since"], v["until"])
        cv = {}
        for pr, at, _e in conv_i:
            cv.setdefault(str(pr), []).append(M.ts(at))

        def cancelled_by_draft(b):   # Buildkite cancelled it within 3 min after a convert-to-draft of its PR (a newer push cancels too: not counted)
            f = M.ts(b.get("finished_at") or b.get("canceled_at"))
            return bool(f) and any(c <= f <= c + dt.timedelta(minutes=3) for c in cv.get(str(b["pull_request"].get("id")), []))
        canc = [b for b in b_i if b.get("pull_request") and b.get("state") == "canceled" and cancelled_by_draft(b)]
        ck = {(b["pipeline_slug"], b["number"]) for b in canc}
        spent = sum(M.gpu(r) for r in bk_i if (r["pipeline"], r["build_number"]) in ck)
        wk_from = (cut.get(str(v.get("weekly_from"))) or {}).get("merged_at") or v["since"]
        wk = weekly_summary(con, wk_from, v["until"])
        n = M.window_numbers(dict(since=v["since"], until=v["until"], bk=bk_i, gha=[r for r in gha_a if inw(r.get("suite_created"))], draft=draft,
                                  conv=conv_i, mp_builds=[b for b in mpd if inw(b.get("created"))]))
        rows = M.compare(nb, n, weekly=wk, after_extra=dict(weekly_runs=(wk or {}).get("runs"), draft_cancel=dict(runs=sum(1 for r in dcr if inw(r.get("created_at"))), cancelled=len(canc), spent_gpu_min=round(spent))))
        M.finish(rows, n["days"])
        v.update(rows=rows, days=n["days"], numbers=n, weekly=wk)
        st = {}
        for r in rows:
            st[r["status"]] = st.get(r["status"], 0) + 1
        print(f"ci impact {v['id']}: {v['since'][:16]} -> {v['until'][:16]} ({n['days']:.2f} d, {len(bk_i)} BK jobs) {st}")
    last = vers[-1]["numbers"]
    meta = dict(collected_at=now if not a.offline else until_all, cutoffs=cut, min_days=M.MIN_DAYS, base_label=base["title"][0], baseline_days=bdays,
                heavy_reasons={v["id"]: v["numbers"].get("heavy_reasons") or {} for v in vers},
                decisions={v["id"]: dict(bypassed=v["numbers"].get("n_bypass"), heavy=v["numbers"].get("n_heavy_dec"), path_skip=v["numbers"].get("n_pathskip"),
                                         skip_expensive=v["numbers"].get("n_skip_exp")) for v in vers},
                coverage=dict(gha_runs=gcov["runs"], gha_runs_with_pr=gcov["mapped"], unmapped_gpu_wall_min={v["id"]: v["numbers"].get("unmapped_gpu_wall_min") for v in vers}),
                burn_in_hours={v["id"]: v.get("burn_in_hours", 24) for v in vers}, merged={v["id"]: v.get("merged") for v in vers},
                weekly={v["id"]: v["weekly"] for v in vers},
                gpu_by_weekday=dict({"v0": nb.get("gpu_by_weekday") or {}}, **{v["id"]: v["numbers"].get("gpu_by_weekday") or {} for v in vers}),
                v0_backfill=dict(ready=l2_ready, workflows=backfill),
                detail=sorted(M.DETAIL | {r["key"] for r in vers[-1]["rows"] if r.get("detail")}),
                switch={v["id"]: dict(first_merge=first_merge if i == 0 else None, merged=v.get("merged"), since=v["since"]) for i, v in enumerate(vers)},
                scope="k3-unit-tests + k3-multiprocess-test + k3-multiprocess-smoke (Buildkite); Code Quality + Test + CPU device (GitHub Actions, PR events)")
    store(con, base, vers, meta)
    print(f"ci impact: before {nb['days']:.1f} d ({len(bk_b)} BK jobs, {len(gha_b)} GHA jobs) · after {last['days']:.2f} d ({len(bk_a)} BK jobs, {len(gha_a)} GHA jobs)")
    print(f"ci impact metrics: {len(vers[-1]['rows'])} x {len(vers) + 1} versions")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001  (the tab is a report: a network error keeps the last stored result, never stops the refresh)
        print(f"ci impact: FAILED, kept the last result ({type(e).__name__}: {str(e)[:200]})")
        sys.exit(0)
