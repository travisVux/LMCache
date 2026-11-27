"""Collect release facts from GitHub (gh CLI), PyPI and Docker Hub into the database.

Run locally:  python -X utf8 collect_release.py [--no-logs]
- Uses the `gh` login you already have. PyPI and Docker Hub are public, no token.
- Failed-job logs are read once; the first error line is stored and never fetched again.
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import urllib.request

from config import (DOCKER_REPOS, FIRST_LINE, PYPI_PROJECTS, REPO, WF_NIGHTLY, WF_PUBLISH, parse_tag)
from db import connect, ensure_release, new_snapshot, now_iso, upsert
from ingest_files import iso, put_job, put_run


def gh_json(path, paginate=False):
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if paginate:
        cmd.insert(2, "--paginate")
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=180)
    if out.returncode:
        raise RuntimeError(f"gh api {path}: {out.stderr.strip()[:200]}")
    txt = out.stdout.strip()
    if paginate and txt.startswith("[") and "][" in txt.replace("]\n[", "]["):
        txt = "[" + txt.strip("[]").replace("]\n[", ",").replace("][", ",") + "]"
    return json.loads(txt or "null")


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ops-app/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TS = re.compile(r"^\S*\d{4}-\d\d-\d\dT[\d:.]+Z\s?")
NOISE = re.compile(r"Process completed with exit code|^\s*$|##\[group\]|##\[endgroup\]")
HINT = re.compile(r"(Error|error:|ERROR|Exception|No module|not found|No such|denied|Traceback|FAILED|fatal:)")


def first_error(log):
    """The line that explains a failure: the ##[error] text, or the closest error-looking line above it."""
    lines = [TS.sub("", ANSI.sub("", x)) for x in log.splitlines()]
    for i, ln in enumerate(lines):
        if "##[error]" not in ln:
            continue
        msg = ln.split("##[error]", 1)[1].strip()
        if msg and not NOISE.search(msg):
            return msg[:300]
        for back in range(i - 1, max(0, i - 60), -1):
            if HINT.search(lines[back]) and "pip's dependency resolver" not in lines[back]:
                return lines[back].strip()[:300]
        return msg[:300] or None
    return None


def job_error(job_id):
    out = subprocess.run(["gh", "api", "--allow-escape-sequences", f"repos/{REPO}/actions/jobs/{job_id}/logs"], capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=180)
    return first_error(out.stdout) if out.returncode == 0 else None


# ───────────── collectors ─────────────
def collect_github(con, snap, logs=True):
    rel = gh_json(f"repos/{REPO}/releases?per_page=100", paginate=True)
    gh_tags = {}
    for r in rel:
        if r.get("draft"):
            continue
        p = parse_tag(r["tag_name"])
        if not p or p["ver"] < FIRST_LINE:
            continue
        gh_tags[r["tag_name"]] = r
        if not p["plat"]:
            ensure_release(con, r["tag_name"], snap, tagged_at=iso(r.get("created_at")),
                           published_at=iso(r.get("published_at")), prerelease=int(bool(r.get("prerelease"))),
                           url=r.get("html_url"))
    mains = [t for t, r in gh_tags.items() if not parse_tag(t)["plat"]]
    for tag in mains:
        runs = gh_json(f"repos/{REPO}/actions/workflows/{WF_PUBLISH}/runs?branch={tag}&per_page=20")
        for r in runs.get("workflow_runs") or []:
            put_run(con, r, snap, WF_PUBLISH)
            done = con.execute("SELECT COUNT(*) FROM wf_job WHERE run_id=?", (r["id"],)).fetchone()[0]
            if done and r.get("status") == "completed" and con.execute(
                    "SELECT 1 FROM wf_run WHERE run_id=? AND updated_at=?", (r["id"], iso(r.get("updated_at")))).fetchone():
                continue
            jobs = gh_json(f"repos/{REPO}/actions/runs/{r['id']}/jobs?per_page=100&filter=latest")
            for j in jobs.get("jobs") or []:
                put_job(con, r["id"], j, snap)
    for wid in (WF_PUBLISH, WF_NIGHTLY):
        runs = gh_json(f"repos/{REPO}/actions/workflows/{wid}/runs?branch=dev&per_page=30")
        for r in runs.get("workflow_runs") or []:
            put_run(con, r, snap, wid)
    if logs:
        todo = con.execute("""SELECT j.job_id FROM wf_job j JOIN wf_run r ON r.run_id=j.run_id
                              WHERE j.conclusion='failure' AND j.error_line IS NULL AND r.release_tag IS NOT NULL""").fetchall()
        for (jid,) in todo:
            con.execute("UPDATE wf_job SET error_line=? WHERE job_id=?", (job_error(jid) or "(no error line found)", jid))
    con.commit()
    return gh_tags


def collect_pypi():
    out = {}
    for proj in PYPI_PROJECTS:
        try:
            d = http_json(f"https://pypi.org/pypi/{proj}/json")
        except Exception as e:  # noqa: BLE001 - registry down must not stop the run
            print(f"  pypi {proj}: {e}")
            continue
        out[proj] = {v: (files[0]["upload_time_iso_8601"] if files else None) for v, files in d["releases"].items()}
    return out


def collect_docker():
    out = {}
    for repo in DOCKER_REPOS:
        tags, url = set(), f"https://hub.docker.com/v2/repositories/lmcache/{repo}/tags?page_size=100&name=v"
        for _ in range(10):
            try:
                d = http_json(url)
            except Exception as e:  # noqa: BLE001
                print(f"  docker {repo}: {e}")
                break
            tags |= {t["name"] for t in d.get("results") or []}
            url = d.get("next")
            if not url:
                break
        out[repo] = tags
    return out


# ───────────── artifact matrix ─────────────
def wrong_version(vs, p, tag_time):
    """Exact version missing: name the version uploaded closest to the tag, within 24 h (the build made it, but under the
    wrong version). Any version counts, not only the same line: the v0.5.8 run uploaded lmcache-cli 0.5.9.dev0 (review R5)."""
    if not tag_time:
        return "not on PyPI"
    t0 = dt.datetime.fromisoformat(tag_time.replace("Z", "+00:00"))
    best = None
    for v, up in vs.items():
        if not up:
            continue
        h = abs((dt.datetime.fromisoformat(up.replace("Z", "+00:00")) - t0).total_seconds()) / 3600
        if h <= 24 and (best is None or h < best[1]):
            best = (v, h)
    if not best:
        return "not on PyPI"
    dev = re.search(r"\.dev\d*|a\d|b\d|rc\d", best[0])
    return f"uploaded {best[0]} instead" + (" (a pre-release: pip install of this package gets a dev build)" if dev else "")


def artifact_rows(tag, p, gh_tags, pypi, docker, tag_time=None):
    """Yield (spec_code, present, ok, ref, detail, url, published_at)."""
    ver = p["pep440"]
    for proj, code in (("lmcache", "pypi:lmcache"), ("lmcache-cli", "pypi:lmcache-cli"),
                       ("lmcache-rust-raw-block-io", "pypi:lmcache-rust-raw-block-io")):
        vs = pypi.get(proj)
        if vs is None:
            continue
        url = f"https://pypi.org/project/{proj}/{ver}/"
        if ver in vs:
            yield code, 1, 1, ver, None, url, vs[ver]
        else:
            yield code, 0, 0, None, wrong_version(vs, p, tag_time), f"https://pypi.org/project/{proj}/#history", None
    r = gh_tags.get(tag)
    yield "gh:main", int(bool(r)), int(bool(r and r.get("assets"))), \
        (f"{len(r.get('assets') or [])} assets" if r else None), None, (r or {}).get("html_url"), iso((r or {}).get("published_at"))
    for plat in ("rocm", "rocm-torch210", "xpu", "rbln", "musa", "cu129"):
        r = gh_tags.get(f"{tag}-{plat}")
        n = len((r or {}).get("assets") or [])
        yield f"gh:{plat}", int(bool(r)), int(n > 0), (f"{n} assets" if r else None), None, \
            (r or {}).get("html_url") or f"https://github.com/{REPO}/releases", iso((r or {}).get("published_at"))

    def dock(repo, name):
        tags = docker.get(repo)
        if tags is None:
            return None
        url = f"https://hub.docker.com/r/lmcache/{repo}/tags?name={name}"
        if name in tags:
            arch = [a for a in ("amd64", "arm64") if f"{name}-{a}" in tags]
            return 1, 1, name, "multi-arch" + (f" + {'/'.join(arch)}" if arch else ""), url
        arch = [a for a in ("amd64", "arm64") if f"{name}-{a}" in tags]
        if arch:
            return 1, 0, f"{name}-{'/'.join(arch)}", "per-arch tags only, no multi-arch tag", url
        return 0, 0, None, "no tag", url

    for code, repo, name in (("docker:vllm-openai", "vllm-openai", tag),
                             ("docker:vllm-openai:lightweight", "vllm-openai", f"{tag}-lightweight"),
                             ("docker:standalone", "standalone", tag),
                             ("docker:lmcache-payload", "lmcache-payload", tag),
                             ("docker:sglang", "sglang", tag)):
        d = dock(repo, name)
        if d:
            yield (code, *d[:4], d[4], None)


def build_artifacts(con, snap, gh_tags, pypi, docker):
    n = 0
    at = now_iso()
    for tag, tag_time in con.execute("SELECT tag, COALESCE(published_at, tagged_at) FROM release").fetchall():
        p = parse_tag(tag)
        if p["ver"] < FIRST_LINE:
            continue
        for code, present, ok, ref, detail, url, pub in artifact_rows(tag, p, gh_tags, pypi, docker, tag_time):
            upsert(con, "artifact", dict(release_tag=tag, spec_code=code, present=present, ok=ok, ref=ref, detail=detail,
                                         url=url, published_at=pub, checked_at=at, snapshot_id=snap),
                   ["release_tag", "spec_code"])
            n += 1
    con.commit()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-logs", action="store_true", help="skip reading failed-job logs")
    a = ap.parse_args()
    con = connect()
    snap = new_snapshot(con, "collect:gh+pypi+docker")
    gh_tags = collect_github(con, snap, logs=not a.no_logs)
    print(f"github tags   {len(gh_tags)}")
    pypi, docker = collect_pypi(), collect_docker()
    print(f"pypi projects {len(pypi)}  docker repos {len(docker)}")
    print(f"artifacts     {build_artifacts(con, snap, gh_tags, pypi, docker)}")
    import model  # noqa: PLC0415 - model reads the fresh rows
    model.record_verdicts(con, snap)
    con.commit()


if __name__ == "__main__":
    main()
