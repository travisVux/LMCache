"""The four sources. Order matters: each later source plans its partitions from what the earlier ones stored.

  source        API                         partition key                 final (settled) when
  bk_builds     Buildkite REST builds        <pipeline>/<UTC day>          fetched >= 3 days after the day ended and no build unfinished
  gh_prs        GitHub GraphQL PR + checks   <PR number>                   PR closed, fetched >= 1 day after its last change, every check suite concluded
  gh_commits    GitHub GraphQL commit by SHA <sha>  (force-pushed commits) fetched >= 1 day after its last suite change, every suite concluded
  gh_run_jobs   GitHub REST run jobs         <workflow run id>             every job completed (a later re-run moves the suite watermark -> refetch)
"""
import os
from datetime import timedelta

from core.http import BK, GH, graphql, next_link
from core.pipeline import Part, Source, days, ts
from core.lake import now

REPO = "LMCache/LMCache"
OWNER, NAME = REPO.split("/")
BK_PIPELINES = ("k3-multiprocess-test", "k3-unit-tests")
UNFINISHED = ("running", "scheduled", "creating", "canceling", "failing", "blocked")


def _age_ok(fetched, last, settle):
    return bool(fetched and last) and ts(fetched) >= ts(last) + settle


# ------------------------------------------------------------------ Buildkite builds per pipeline-day
class BkBuilds(Source):
    name, workers, SETTLE = "bk_builds", 2, timedelta(days=3)

    def plan(self, ctx, since, until):
        return [Part(f"{pl}/{d}", d, None) for pl in BK_PIPELINES for d in days(since, until)]

    def fetch(self, ctx, part):
        pl, d = part.key.split("/")
        nxt = (ts(d + "T00:00:00Z") + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (f"organizations/lmcache/pipelines/{pl}/builds?created_from={d}T00:00:00Z&created_to={nxt}"
               f"&per_page=100&include_retried_jobs=true")
        out = []
        while url:
            data, h = BK.request(url)
            out.extend(data)
            url = next_link(h)
        for x in out:   # strip fields that may hold secrets (pipeline config / env)
            x.pop("pipeline", None); x.pop("env", None)
            x["pipeline_slug"] = pl
            for j in x.get("jobs", []):
                j.pop("env", None)
        final = _age_ok(now(), nxt, self.SETTLE) and not any(b.get("state") in UNFINISHED for b in out)
        return out, len(out), None, final


# ------------------------------------------------------------------ GitHub PR + every commit's check suites / runs
PR_FIELDS = """number author{login} createdAt updatedAt mergedAt closedAt state baseRefName isDraft url
  commits{totalCount}
  timelineItems(itemTypes:[LABELED_EVENT, UNLABELED_EVENT, HEAD_REF_FORCE_PUSHED_EVENT], first:60){ nodes{ __typename
    ... on LabeledEvent{ createdAt label{name} } ... on UnlabeledEvent{ createdAt label{name} }
    ... on HeadRefForcePushedEvent{ createdAt } } }"""

SUITES = """checkSuites(first:15){ nodes{ app{slug} createdAt updatedAt conclusion
        workflowRun{ databaseId event url workflow{name} }
        checkRuns(first:60, filterBy:{checkType:ALL}){ nodes{ databaseId name status conclusion startedAt completedAt %s } } } }"""


def _commit_query(num, n):
    return f"""{{ repository(owner:"{OWNER}", name:"{NAME}"){{ pullRequest(number:{num}){{ commits(last:{n}){{ nodes{{ commit{{ oid committedDate
      status{{ contexts{{ context state createdAt targetUrl isRequired(pullRequestNumber:{num}) }} }}
      {SUITES % f'isRequired(pullRequestNumber:{num})'} }} }} }} }} }} }}"""


def _suites(commits):
    return [s for c in commits for s in ((c.get("checkSuites") or {}).get("nodes") or [])]


def _suite_last(commits):
    return max([s.get("updatedAt") or "" for s in _suites(commits)] or [""]) or None


def _all_concluded(commits):
    return all(s.get("conclusion") for s in _suites(commits))


class GhPrs(Source):
    name, workers, SETTLE = "gh_prs", 4, timedelta(days=1)

    def plan(self, ctx, since, until):
        """PRs open at some time in the range: created before `until`, updated on or after `since`.
        Search returns at most 1,000 hits per query, so the list is split by creation date (10-day chunks)."""
        s0, u0 = ts(since), ts(until)
        edges = ["<" + (s0 - timedelta(days=90)).strftime("%Y-%m-%d")]
        d = s0 - timedelta(days=90)
        while d < u0:
            e = min(d + timedelta(days=9), u0 - timedelta(days=1))
            edges.append(f"{d:%Y-%m-%d}..{e:%Y-%m-%d}")
            d = e + timedelta(days=1)
        nodes = {}
        for r in edges:
            after = None
            while True:
                q = f'repo:{REPO} is:pr created:{r} updated:>={since[:10]}'
                cur = f', after:"{after}"' if after else ""
                res = graphql(f'{{ search(query:"{q}", type:ISSUE, first:50{cur}){{ issueCount pageInfo{{hasNextPage endCursor}} nodes{{ ... on PullRequest{{ {PR_FIELDS} }} }} }} }}')["search"]
                if res["issueCount"] > 1000:
                    raise RuntimeError(f"search {r} has {res['issueCount']} hits (> 1,000): use smaller chunks")
                for n in res["nodes"]:
                    if n and n["createdAt"] < until:
                        nodes[str(n["number"])] = n
                if not res["pageInfo"]["hasNextPage"]:
                    break
                after = res["pageInfo"]["endCursor"]
        ctx.pr_nodes = nodes
        print(f"[gh_prs] {len(nodes)} PRs open in {since[:10]} .. {until[:10]}", flush=True)
        return [Part(k, n["createdAt"][:10], n["updatedAt"]) for k, n in sorted(nodes.items(), key=lambda kv: int(kv[0]))]

    def fetch(self, ctx, part):
        node = dict(ctx.pr_nodes[part.key])
        n = min(100, max(1, node["commits"]["totalCount"]))
        d = graphql(_commit_query(int(part.key), n))
        node["commit_nodes"] = [c["commit"] for c in d["repository"]["pullRequest"]["commits"]["nodes"]]
        node["fetched_at"] = now()
        return node, len(node["commit_nodes"]), node.get("updatedAt"), pr_is_final(node, node["fetched_at"])


def pr_is_final(node, fetched):
    vals = [x for x in (node.get("updatedAt"), node.get("closedAt"), _suite_last(node.get("commit_nodes") or [])) if x]
    last = max(vals) if vals else None
    return bool(node.get("closedAt")) and _age_ok(fetched, last, GhPrs.SETTLE) and _all_concluded(node.get("commit_nodes") or [])


# ------------------------------------------------------------------ force-pushed commits (Buildkite built them, the PR no longer lists them)
class GhCommits(Source):
    name, workers, SETTLE = "gh_commits", 4, timedelta(days=1)

    def plan(self, ctx, since, until):
        lake, want = ctx.lake, {}
        have = {}
        for pl in BK_PIPELINES:
            for d in days(since, until):
                for b in lake.read("bk_builds", f"{pl}/{d}") or []:
                    if not (b.get("pull_request") and b.get("commit")):
                        continue
                    pr = str(b["pull_request"]["id"])
                    if pr not in have:
                        doc = lake.read("gh_prs", pr)
                        have[pr] = {c["oid"] for c in (doc or {}).get("commit_nodes") or []}
                    if b["commit"] not in have[pr]:
                        want.setdefault(b["commit"], (pr, b["created_at"][:10]))
        ctx.orphan_pr = {k: v[0] for k, v in want.items()}
        return [Part(sha, d, None) for sha, (pr, d) in sorted(want.items())]

    def fetch(self, ctx, part):
        d = graphql('{ repository(owner:"%s", name:"%s"){ object(oid:"%s"){ ... on Commit{ oid committedDate %s } } } }'
                    % (OWNER, NAME, part.key, SUITES % ""))
        node = d["repository"]["object"]
        payload = dict(pr=ctx.orphan_pr.get(part.key), commit=node, fetched_at=now())
        if not node:
            return payload, 0, None, True   # commit gone from GitHub: nothing more will come
        last = _suite_last([node])
        final = _all_concluded([node]) and (last is None or _age_ok(payload["fetched_at"], last, self.SETTLE))
        return payload, len(_suites([node])), last, final


# ------------------------------------------------------------------ GitHub Actions jobs of a workflow run (all attempts): runner queue
class GhRunJobs(Source):
    """created_at of a job = when it entered the runner queue (for a `needs:` job: when its last dependency finished).
    Runner queue = started_at - created_at. Copies of a job in a re-run attempt that did not run again keep the old
    started_at (< created_at): the transform drops them."""
    name, workers = "gh_run_jobs", 4
    KEEP = ("id", "run_id", "run_attempt", "name", "status", "conclusion", "created_at", "started_at", "completed_at")

    def plan(self, ctx, since, until):
        lake, runs = ctx.lake, {}
        docs = [lake.read("gh_prs", k) for k, _ in lake.keys("gh_prs")]
        commits = [c for doc in docs if doc for c in doc.get("commit_nodes") or []]
        commits += [o["commit"] for o in (lake.read("gh_commits", k) for k, _ in lake.keys("gh_commits")) if o and o.get("commit")]
        for s in _suites(commits):
            wr = s.get("workflowRun")
            if not wr or (s.get("app") or {}).get("slug") != "github-actions" or not (since <= s["createdAt"] < until):
                continue
            k = str(wr["databaseId"])
            if k not in runs or (s.get("updatedAt") or "") > (runs[k].watermark or ""):
                runs[k] = Part(k, s["createdAt"][:10], s.get("updatedAt"))
        return sorted(runs.values(), key=lambda p: (p.day, p.key))

    def fetch(self, ctx, part):
        jobs, page = [], 1
        while True:
            d, _ = GH.request(f"repos/{REPO}/actions/runs/{part.key}/jobs?filter=all&per_page=100&page={page}")
            jobs += [{k: j.get(k) for k in self.KEEP} for j in d["jobs"]]
            if len(jobs) >= d["total_count"] or not d["jobs"]:
                break
            page += 1
        final = all(j.get("status") == "completed" for j in jobs)
        return dict(run_id=int(part.key), jobs=jobs), len(jobs), None, final


SOURCES = [BkBuilds(), GhPrs(), GhCommits(), GhRunJobs()]
BY_NAME = {s.name: s for s in SOURCES}
