"""Step 1b: fetch GitHub PR + check data for the fixed window of window.json (read-only, through the logged-in gh CLI).

  python -I -X utf8 outputs/P1/fetch_gh_checks.py                 # PRs + commits + checks (~15 min)
  python -I -X utf8 outputs/P1/fetch_gh_checks.py --orphans-only  # only re-read force-pushed commits by SHA
Run after fetch_builds.py: force-pushed commits are found through the Buildkite builds.

For every PR that was open at any time in the window (created before `until`, updated after `since`):
  - PR facts: number, author, created / merged / closed time, base branch, 'full' label events
  - every commit (last 100): its check suites (GitHub Actions workflows, DCO, ...) with ALL check runs, including the
    attempts that were re-run (filterBy checkType ALL), plus the latest commit status of each Buildkite context.
Writes raw/gh_checks_30d.json. GitHub Actions check runs = GitHub Actions jobs (one CPU runner each).
Not available from the API at this scale: the time a GitHub Actions job waited for a runner (only suite creation and
job start are exposed), so 'start delay' = job start - workflow (suite) creation, which also holds waits for earlier jobs."""
import json, os, subprocess, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WIN = json.load(open(os.path.join(HERE, "window.json"), encoding="utf-8"))
OWNER, NAME = WIN["repo"].split("/")


def gql(query, tries=5):
    for i in range(tries):
        p = subprocess.run(["gh", "api", "graphql", "--input", "-"], input=json.dumps({"query": query}),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0:
            d = json.loads(p.stdout)
            if d.get("data") and not d.get("errors"):
                return d["data"]
            err = str(d.get("errors"))[:300]
        else:
            err = p.stderr.strip()[:300]
        time.sleep(5 * (i + 1))
    raise RuntimeError("graphql: " + err)


PR_FIELDS = """number author{login} createdAt mergedAt closedAt state baseRefName isDraft url
  commits{totalCount}
  timelineItems(itemTypes:[LABELED_EVENT, UNLABELED_EVENT, HEAD_REF_FORCE_PUSHED_EVENT], first:60){ nodes{ __typename
    ... on LabeledEvent{ createdAt label{name} } ... on UnlabeledEvent{ createdAt label{name} }
    ... on HeadRefForcePushedEvent{ createdAt } } }"""


def list_prs():
    """Search caps at 1,000 hits per query, so the PR list is split by creation month."""
    since, until = WIN["since"][:10], WIN["until"][:10]
    ranges = ["<2026-09-01", "2026-09-01..2026-09-30", "2026-10-01..2026-10-20", f"2026-10-21..{until}"]
    out = {}
    for r in ranges:
        after = None
        while True:
            q = f'repo:{OWNER}/{NAME} is:pr created:{r} updated:>={since}'
            cur = f', after:"{after}"' if after else ""
            d = gql(f'{{ search(query:"{q}", type:ISSUE, first:50{cur}){{ issueCount pageInfo{{hasNextPage endCursor}} nodes{{ ... on PullRequest{{ {PR_FIELDS} }} }} }} }}')["search"]
            for n in d["nodes"]:
                if n and n["createdAt"] < WIN["until"]:
                    out[n["number"]] = n
            if not d["pageInfo"]["hasNextPage"]:
                break
            after = d["pageInfo"]["endCursor"]
        print(f"  prs created {r}: total so far {len(out)} (search said {d['issueCount']})", flush=True)
    return out


def commit_block(num, n):
    return f"""p{num}: pullRequest(number:{num}){{ commits(last:{n}){{ nodes{{ commit{{ oid committedDate
      status{{ contexts{{ context state createdAt targetUrl isRequired(pullRequestNumber:{num}) }} }}
      checkSuites(first:15){{ nodes{{ app{{slug}} createdAt updatedAt conclusion
        workflowRun{{ databaseId event url workflow{{name}} }}
        checkRuns(first:60, filterBy:{{checkType:ALL}}){{ nodes{{ databaseId name status conclusion startedAt completedAt isRequired(pullRequestNumber:{num}) }} }} }} }} }} }} }} }}"""


SUITES = """checkSuites(first:15){ nodes{ app{slug} createdAt updatedAt conclusion
        workflowRun{ databaseId event url workflow{name} }
        checkRuns(first:60, filterBy:{checkType:ALL}){ nodes{ databaseId name status conclusion startedAt completedAt } } } }"""


def orphans(out):
    """Buildkite PR builds whose commit is no longer in the PR's commit list (force-pushed away): read that commit's
    checks by SHA, so the GitHub Actions minutes of rebased pushes are not lost."""
    have = {c["oid"] for p in out["prs"] for c in p["commit_nodes"]}
    want = {}
    for fn in ("builds_30d.json", "builds_k3-unit-tests_30d.json"):
        f = os.path.join(HERE, "raw", fn)
        if os.path.exists(f):
            for b in json.load(open(f, encoding="utf-8")):
                if b.get("pull_request") and b.get("commit") and b["commit"] not in have:
                    want[b["commit"]] = str(b["pull_request"]["id"])
    shas, got = sorted(want), {}
    print(f"force-pushed commits to read by SHA: {len(shas)}", flush=True)
    for i in range(0, len(shas), 10):
        part = shas[i:i + 10]
        d = gql("{ repository(owner:\"%s\", name:\"%s\"){ %s } }" % (OWNER, NAME, " ".join(
            f'c{k}: object(oid:"{x}"){{ ... on Commit{{ oid committedDate {SUITES} }} }}' for k, x in enumerate(part))))
        for k, x in enumerate(part):
            node = d["repository"].get(f"c{k}")
            if node:
                got[x] = dict(pr=want[x], commit=node)
        if i % 200 == 0:
            print(f"  {i + len(part)}/{len(shas)}", flush=True)
    out["orphan_commits"] = got
    out["orphans_missing"] = [x for x in shas if x not in got]


def main():
    t0 = time.time()
    fn = os.path.join(HERE, "raw", "gh_checks_30d.json")
    if "--orphans-only" in sys.argv:
        out = json.load(open(fn, encoding="utf-8"))
        orphans(out)
        json.dump(out, open(fn, "w", encoding="utf-8"), separators=(",", ":"))
        print(f"orphans: {len(out['orphan_commits'])} read, {len(out['orphans_missing'])} not found, {time.time() - t0:.0f}s")
        return
    prs = list_prs()
    nums = sorted(prs)
    print(f"{len(nums)} PRs; fetching commits + checks", flush=True)
    batch, cost = [], 0
    def flush(b):
        d = gql("{ repository(owner:\"%s\", name:\"%s\"){ %s } rateLimit{ cost remaining } }" % (OWNER, NAME, " ".join(commit_block(x, min(100, max(1, prs[x]["commits"]["totalCount"]))) for x in b)))
        for x in b:
            prs[x]["commit_nodes"] = [c["commit"] for c in d["repository"][f"p{x}"]["commits"]["nodes"]]
        return d["rateLimit"]
    done = 0
    for x in nums:
        batch.append(x)
        weight = sum(min(100, prs[y]["commits"]["totalCount"]) for y in batch)
        if len(batch) >= 6 or weight >= 40:
            rl = flush(batch); done += len(batch); batch = []
            cost += rl["cost"]
            if done % 60 < 6:
                print(f"  {done}/{len(nums)} PRs, cost {cost}, remaining {rl['remaining']}", flush=True)
    if batch:
        rl = flush(batch); cost += rl["cost"]
    out = dict(made=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), window=[WIN["since"], WIN["until"]],
               repo=WIN["repo"], prs=[prs[n] for n in nums])
    orphans(out)
    json.dump(out, open(fn, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"wrote raw/gh_checks_30d.json: {len(nums)} PRs, graphql cost {cost}, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
