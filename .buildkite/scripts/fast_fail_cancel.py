#!/usr/bin/env python3
"""
Fast-Fail & Cancel Script: Stop Parallel and Downstream CI on First Failure.
Supports bidirectional cancellation:
- Cancels sibling GitHub Actions workflow runs for the same commit.
- Cancels sibling Buildkite builds for the same commit.

Zero third-party dependencies (pure standard library).
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

PROTECTED_BRANCHES = {"dev", "main", "master"}


def get_token_buildkite(explicit_token: Optional[str]) -> Optional[str]:
    """Retrieve Buildkite token from argument, environment, or local fallback."""
    if explicit_token:
        return explicit_token
    token = os.environ.get("BUILDKITE_API_TOKEN") or os.environ.get("BK_TOKEN")
    if token:
        return token
    # Optional local fallback (used in development/testing environments)
    try:
        p = os.path.expanduser(r"~\.claude.json.bak-buildkite")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            h = d.get("mcpServers", {}).get("buildkite", {}).get("headers", {}).get("Authorization", "")
            if h:
                return h.split(" ", 1)[1] if h.lower().startswith("bearer ") else h
    except Exception:
        pass
    return None


def get_token_github(explicit_token: Optional[str]) -> Optional[str]:
    """Retrieve GitHub token from argument or environment."""
    if explicit_token:
        return explicit_token
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _http_request(
    url: str,
    method: str = "GET",
    token: Optional[str] = None,
    auth_header_prefix: str = "Bearer ",
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    retries: int = 3,
) -> Tuple[int, Any]:
    """Helper to send HTTP requests using urllib.request with retry on transient network errors."""
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "CacheAgent-P1",
    }
    if token:
        req_headers["Authorization"] = f"{auth_header_prefix}{token}"
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    last_err = ""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.getcode()
                body = response.read()
                if body:
                    try:
                        return status_code, json.loads(body.decode("utf-8"))
                    except Exception:
                        return status_code, body.decode("utf-8")
                return status_code, None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return e.code, body
        except Exception as e:
            last_err = str(e)
            if attempt < retries - 1:
                import time
                time.sleep(1.0)
                continue
            return -1, last_err
    return -1, last_err


# ---------------------------------------------------------------------------
# GitHub Actions Cancellation
# ---------------------------------------------------------------------------


def cancel_github_actions(
    commit_sha: str,
    repo: str,
    token: str,
    current_run_id: Optional[str],
    dry_run: bool = False,
    reason: str = "",
) -> List[Dict[str, Any]]:
    """Find and cancel sibling GitHub Actions runs for the given commit SHA."""
    print(f"\n[Fast-Fail] Querying GitHub Actions runs for commit {commit_sha[:8]} in {repo}...")
    cancelled = []

    # Query in_progress and queued runs for the target commit
    url = f"https://api.github.com/repos/{repo}/actions/runs?head_sha={commit_sha}&status=in_progress"
    status_code, resp = _http_request(url, token=token, auth_header_prefix="token ")
    if status_code != 200 or not isinstance(resp, dict):
        # Fallback without status filter if needed or report error
        print(f"  [WARN] Failed to list GHA runs (HTTP {status_code}): {resp}")
        return cancelled

    runs = resp.get("workflow_runs", [])

    # Also check queued runs
    url_queued = f"https://api.github.com/repos/{repo}/actions/runs?head_sha={commit_sha}&status=queued"
    status_code_q, resp_q = _http_request(url_queued, token=token, auth_header_prefix="token ")
    if status_code_q == 200 and isinstance(resp_q, dict):
        runs.extend(resp_q.get("workflow_runs", []))

    # Deduplicate runs
    unique_runs = {str(r.get("id")): r for r in runs if r.get("id")}

    for run_id_str, run in unique_runs.items():
        if current_run_id and run_id_str == str(current_run_id):
            print(f"  -> Skipping current runner run ID: {run_id_str} ({run.get('name')})")
            continue

        branch = run.get("head_branch")
        if branch in PROTECTED_BRANCHES and not run.get("pull_requests"):
            print(f"  -> Skipping protected branch {branch}: run {run_id_str}")
            continue

        run_info = {
            "id": run_id_str,
            "name": run.get("name"),
            "status": run.get("status"),
            "url": run.get("html_url"),
        }

        if dry_run:
            print(f"  [DRY-RUN] Would cancel GHA run {run_id_str}: {run.get('name')} ({run.get('html_url')})")
            cancelled.append(run_info)
        else:
            cancel_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id_str}/cancel"
            c_status, c_resp = _http_request(cancel_url, method="POST", token=token, auth_header_prefix="token ")
            if c_status in (202, 200):
                print(f"  [CANCELLED] GHA run {run_id_str}: {run.get('name')}")
                cancelled.append(run_info)
            else:
                print(f"  [WARN] Failed to cancel GHA run {run_id_str} (HTTP {c_status}): {c_resp}")

    return cancelled


# ---------------------------------------------------------------------------
# Buildkite Cancellation
# ---------------------------------------------------------------------------


def cancel_buildkite_builds(
    commit_sha: str,
    org: str,
    token: str,
    current_build_id: Optional[str],
    dry_run: bool = False,
    reason: str = "",
) -> List[Dict[str, Any]]:
    """Find and cancel sibling Buildkite builds for the given commit SHA."""
    print(f"\n[Fast-Fail] Querying Buildkite builds for commit {commit_sha[:8]} in org '{org}'...")
    cancelled = []

    # Query builds for commit (and filter running/scheduled in memory for maximum API compatibility)
    url = f"https://api.buildkite.com/v2/organizations/{org}/builds?commit={commit_sha}"
    status_code, resp = _http_request(url, token=token)
    if status_code != 200 or not isinstance(resp, list):
        print(f"  [WARN] Failed to list Buildkite builds (HTTP {status_code}): {resp}")
        return cancelled

    for build in resp:
        state = build.get("state")
        if state not in ("running", "scheduled"):
            continue

        build_id = str(build.get("id"))
        build_num = build.get("number")
        pipeline = build.get("pipeline", {}).get("slug", "unknown")
        branch = build.get("branch")
        web_url = build.get("web_url")

        if current_build_id and build_id == str(current_build_id):
            print(f"  -> Skipping current Buildkite build: {build_num} ({pipeline})")
            continue

        if branch in PROTECTED_BRANCHES and not build.get("pull_request"):
            print(f"  -> Skipping protected branch {branch}: build {build_num} ({pipeline})")
            continue

        build_info = {
            "id": build_id,
            "number": build_num,
            "pipeline": pipeline,
            "web_url": web_url,
        }

        if dry_run:
            print(f"  [DRY-RUN] Would cancel Buildkite build #{build_num} ({pipeline}): {web_url}")
            cancelled.append(build_info)
        else:
            cancel_url = f"https://api.buildkite.com/v2/organizations/{org}/pipelines/{pipeline}/builds/{build_num}/cancel"
            c_status, c_resp = _http_request(cancel_url, method="PUT", token=token)
            if c_status in (200, 202):
                print(f"  [CANCELLED] Buildkite build #{build_num} ({pipeline})")
                cancelled.append(build_info)
            else:
                print(f"  [WARN] Failed to cancel Buildkite build #{build_num} (HTTP {c_status}): {c_resp}")

    return cancelled


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast-Fail CI Cancel: stop sibling GHA runs and Buildkite builds.")
    parser.add_argument(
        "--commit",
        default=os.environ.get("BUILDKITE_COMMIT") or os.environ.get("GITHUB_SHA"),
        help="Git commit SHA to cancel sibling builds for (default: from env)",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "LMCache/LMCache"),
        help="GitHub repository owner/name (default: LMCache/LMCache)",
    )
    parser.add_argument(
        "--org",
        default=os.environ.get("BUILDKITE_ORGANIZATION_SLUG", "lmcache"),
        help="Buildkite organization slug (default: lmcache)",
    )
    parser.add_argument(
        "--current-run-id",
        default=os.environ.get("GITHUB_RUN_ID"),
        help="Current GitHub Actions run ID to exclude from cancellation",
    )
    parser.add_argument(
        "--current-build-id",
        default=os.environ.get("BUILDKITE_BUILD_ID"),
        help="Current Buildkite build ID to exclude from cancellation",
    )
    parser.add_argument("--github-token", help="GitHub token with actions:write permission")
    parser.add_argument("--buildkite-token", help="Buildkite token with write_builds permission")
    parser.add_argument("--no-cancel-gha", action="store_true", help="Do not cancel GitHub Actions runs")
    parser.add_argument("--no-cancel-bk", action="store_true", help="Do not cancel Buildkite builds")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without cancelling")
    parser.add_argument("--reason", default="Fast-fail: required check failed", help="Reason for cancellation")

    args = parser.parse_args()

    if not args.commit:
        print("[Fast-Fail] Error: No commit SHA specified (--commit or BUILDKITE_COMMIT/GITHUB_SHA).", file=sys.stderr)
        return 0  # Exit 0 so failure hooks do not crash CI

    print(f"=== Fast-Fail Cancel Triggered ===")
    print(f"Commit: {args.commit}")
    print(f"Reason: {args.reason}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE CANCEL'}")

    gh_token = get_token_github(args.github_token)
    bk_token = get_token_buildkite(args.buildkite_token)

    total_gha_cancelled = 0
    total_bk_cancelled = 0

    # 1. Cancel GitHub Actions sibling runs
    if not args.no_cancel_gha:
        if gh_token:
            gha_cancelled = cancel_github_actions(
                commit_sha=args.commit,
                repo=args.repo,
                token=gh_token,
                current_run_id=args.current_run_id,
                dry_run=args.dry_run,
                reason=args.reason,
            )
            total_gha_cancelled = len(gha_cancelled)
        else:
            print("\n[Fast-Fail] Skipping GitHub Actions cancellation (no GITHUB_TOKEN available).")

    # 2. Cancel Buildkite sibling builds
    if not args.no_cancel_bk:
        if bk_token:
            bk_cancelled = cancel_buildkite_builds(
                commit_sha=args.commit,
                org=args.org,
                token=bk_token,
                current_build_id=args.current_build_id,
                dry_run=args.dry_run,
                reason=args.reason,
            )
            total_bk_cancelled = len(bk_cancelled)
        else:
            print("\n[Fast-Fail] Skipping Buildkite cancellation (no BUILDKITE_API_TOKEN available).")

    print("\n=== Fast-Fail Summary ===")
    print(f"GitHub Actions runs cancelled: {total_gha_cancelled}")
    print(f"Buildkite builds cancelled:    {total_bk_cancelled}")
    print("=========================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
