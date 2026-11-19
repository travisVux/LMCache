# SPDX-License-Identifier: Apache-2.0
"""Fast-Fail & Cancel: stop running PR CI once a required pipeline fails.

Supports bidirectional cancellation across GitHub Actions and Buildkite for
the same PR and head commit SHA, using only the Python standard library.
"""

# Future
from __future__ import annotations

# Standard
from typing import Any
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PROTECTED_BRANCHES = {"dev", "main", "master"}


def _http_request(
    url: str,
    method: str = "GET",
    token: str | None = None,
    auth_prefix: str = "Bearer ",
    timeout: int = 20,
    retries: int = 3,
) -> tuple[int, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "lmcache-ci-fast-fail",
    }
    if token:
        headers["Authorization"] = f"{auth_prefix}{token}"

    req = urllib.request.Request(url, headers=headers, method=method)
    last_err = ""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if not raw:
                    return resp.getcode(), None
                text = raw.decode("utf-8", errors="replace")
                try:
                    return resp.getcode(), json.loads(text)
                except json.JSONDecodeError:
                    return resp.getcode(), text
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            if attempt < retries - 1:
                time.sleep(1.0)
    return -1, last_err


def is_current_build_failing(
    org: str,
    pipeline: str,
    build_number: str,
    token: str,
) -> bool:
    """Return True if the specified Buildkite build is failing or failed."""
    url = (
        f"https://api.buildkite.com/v2/organizations/{org}"
        f"/pipelines/{pipeline}/builds/{build_number}"
    )
    code, data = _http_request(url, token=token)
    if code != 200 or not isinstance(data, dict):
        print(f"[WARN] Could not verify build state (HTTP {code}); skipping.")
        return False
    state = data.get("state", "")
    return state in {"failing", "failed"}


def cancel_github_actions(
    commit_sha: str,
    repo: str,
    token: str,
    current_run_id: str | None = None,
    dry_run: bool = False,
    reason: str = "",
) -> list[dict[str, Any]]:
    """Cancel queued or in-progress PR GitHub Actions runs for commit_sha."""
    cancelled: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    for status in ("in_progress", "queued"):
        qs = urllib.parse.urlencode(
            {"head_sha": commit_sha, "status": status, "per_page": 100}
        )
        url = f"https://api.github.com/repos/{repo}/actions/runs?{qs}"
        code, data = _http_request(url, token=token, auth_prefix="token ")
        if code != 200 or not isinstance(data, dict):
            print(f"[WARN] Failed to list GHA runs ({status}, HTTP {code})")
            continue

        for run in data.get("workflow_runs") or []:
            run_id = run.get("id")
            if not run_id or run_id in seen_ids:
                continue
            seen_ids.add(run_id)

            if current_run_id and str(run_id) == str(current_run_id):
                continue
            if run.get("event") not in {"pull_request", "pull_request_target"}:
                continue

            name = run.get("name") or str(run_id)
            if dry_run:
                print(f"[DRY-RUN] Would cancel GHA run {run_id} ({name}): {reason}")
                cancelled.append({"id": run_id, "name": name, "dry_run": True})
                continue

            c_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/cancel"
            c_code, _ = _http_request(
                c_url, method="POST", token=token, auth_prefix="token "
            )
            if c_code in (202, 200):
                print(f"Cancelled GHA run {run_id} ({name})")
                cancelled.append({"id": run_id, "name": name})
            else:
                print(f"[WARN] Failed to cancel GHA run {run_id} (HTTP {c_code})")
    return cancelled


def cancel_buildkite_builds(
    commit_sha: str,
    pr_number: str,
    org: str,
    token: str,
    current_build_id: str | None = None,
    dry_run: bool = False,
    reason: str = "",
) -> list[dict[str, Any]]:
    """Cancel scheduled, running, or failing Buildkite PR builds for commit_sha."""
    cancelled: list[dict[str, Any]] = []
    params = [
        ("commit", commit_sha),
        ("state[]", "scheduled"),
        ("state[]", "running"),
        ("state[]", "failing"),
        ("per_page", "100"),
    ]
    url = (
        f"https://api.buildkite.com/v2/organizations/{org}/builds?"
        + urllib.parse.urlencode(params)
    )
    code, builds = _http_request(url, token=token)
    if code != 200 or not isinstance(builds, list):
        print(f"[WARN] Failed to list Buildkite builds (HTTP {code})")
        return cancelled

    for b in builds:
        bid = b.get("id")
        if current_build_id and str(bid) == str(current_build_id):
            continue
        pr_obj = b.get("pull_request")
        if not isinstance(pr_obj, dict) or str(pr_obj.get("id")) != str(pr_number):
            continue

        pipeline = (b.get("pipeline") or {}).get("slug") or "unknown"
        number = b.get("number")
        if dry_run:
            print(f"[DRY-RUN] Would cancel Buildkite {pipeline} #{number}: {reason}")
            cancelled.append({"pipeline": pipeline, "number": number, "dry_run": True})
            continue

        c_url = (
            f"https://api.buildkite.com/v2/organizations/{org}"
            f"/pipelines/{pipeline}/builds/{number}/cancel"
        )
        c_code, _ = _http_request(c_url, method="PUT", token=token)
        if c_code in (200, 202):
            print(f"Cancelled Buildkite {pipeline} #{number}")
            cancelled.append({"pipeline": pipeline, "number": number})
        else:
            print(
                f"[WARN] Failed to cancel Buildkite {pipeline} #{number} "
                f"(HTTP {c_code})"
            )
    return cancelled


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Cancel sibling PR CI runs/builds when a required check fails."
    )
    ap.add_argument("--commit", required=True)
    ap.add_argument("--pr-number", default=os.environ.get("BUILDKITE_PULL_REQUEST", ""))
    ap.add_argument("--branch", default=os.environ.get("BUILDKITE_BRANCH", ""))
    ap.add_argument("--org", default="lmcache")
    ap.add_argument("--repo", default="LMCache/LMCache")
    ap.add_argument("--current-build-id", default=os.environ.get("BUILDKITE_BUILD_ID"))
    ap.add_argument(
        "--current-build-number", default=os.environ.get("BUILDKITE_BUILD_NUMBER")
    )
    ap.add_argument(
        "--current-pipeline", default=os.environ.get("BUILDKITE_PIPELINE_SLUG")
    )
    ap.add_argument("--current-run-id", default=os.environ.get("GITHUB_RUN_ID"))
    ap.add_argument("--only-if-build-failing", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reason", default="Required CI pipeline failed")
    args = ap.parse_args()

    if not args.pr_number or args.pr_number == "false":
        print("Not a PR build; skipping fast-fail cancellation.")
        return 0
    if args.branch in PROTECTED_BRANCHES:
        print(f"Protected branch '{args.branch}'; skipping fast-fail cancellation.")
        return 0

    bk_token = os.environ.get("BUILDKITE_API_TOKEN") or os.environ.get("BK_TOKEN")
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    if args.only_if_build_failing:
        if not bk_token or not args.current_pipeline or not args.current_build_number:
            print(
                "[WARN] Missing Buildkite context/token for build state check; "
                "skipping."
            )
            return 0
        if not is_current_build_failing(
            args.org, args.current_pipeline, args.current_build_number, bk_token
        ):
            print("Current Buildkite build is not failing; no cancellation needed.")
            return 0

    if bk_token:
        cancel_buildkite_builds(
            commit_sha=args.commit,
            pr_number=args.pr_number,
            org=args.org,
            token=bk_token,
            current_build_id=args.current_build_id,
            dry_run=args.dry_run,
            reason=args.reason,
        )
    else:
        print("[WARN] BUILDKITE_API_TOKEN not set; skipping Buildkite cancellation.")

    if gh_token:
        cancel_github_actions(
            commit_sha=args.commit,
            repo=args.repo,
            token=gh_token,
            current_run_id=args.current_run_id,
            dry_run=args.dry_run,
            reason=args.reason,
        )
    else:
        print("[WARN] GITHUB_TOKEN not set; skipping GitHub Actions cancellation.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
