# SPDX-License-Identifier: Apache-2.0
"""Unit tests for .buildkite/scripts/fast_fail_cancel.py."""

# Future
from __future__ import annotations

# Standard
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import patch
import importlib.util
import urllib.error

# Third Party
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / ".buildkite" / "scripts" / "fast_fail_cancel.py"

_spec = importlib.util.spec_from_file_location("fast_fail_cancel", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
ffc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ffc)


def test_cancel_buildkite_filters_by_pr_and_excludes_self() -> None:
    """Only matching PR builds (not dev or self) are cancelled."""
    sample_builds = [
        {
            "id": "self-id",
            "number": 100,
            "pipeline": {"slug": "k3-unit-tests"},
            "pull_request": {"id": "42"},
        },
        {
            "id": "sibling-smoke",
            "number": 200,
            "pipeline": {"slug": "k3-multiprocess-smoke"},
            "pull_request": {"id": "42"},
        },
        {
            "id": "dev-build-same-sha",
            "number": 300,
            "pipeline": {"slug": "k3-multiprocess-test"},
            "pull_request": None,
        },
        {
            "id": "other-pr",
            "number": 400,
            "pipeline": {"slug": "rbln-mp-test"},
            "pull_request": {"id": "99"},
        },
    ]
    calls: list[tuple[str, str]] = []

    def fake_http(
        url: str,
        method: str = "GET",
        **_kwargs: Any,
    ) -> tuple[int, Any]:
        calls.append((method, url))
        if method == "GET":
            return 200, sample_builds
        return 200, {}

    with patch.object(ffc, "_http_request", side_effect=fake_http):
        res = ffc.cancel_buildkite_builds(
            commit_sha="abc12345",
            pr_number="42",
            org="lmcache",
            token="bk-tok",
            current_build_id="self-id",
        )

    assert res == [{"pipeline": "k3-multiprocess-smoke", "number": 200}]
    put_urls = [u for m, u in calls if m == "PUT"]
    assert len(put_urls) == 1
    assert "k3-multiprocess-smoke/builds/200/cancel" in put_urls[0]


def test_cancel_github_actions_excludes_self_and_non_pr() -> None:
    """Only pull_request / pull_request_target runs (not self) are cancelled."""
    in_prog = {
        "workflow_runs": [
            {"id": 10, "name": "Code Quality", "event": "pull_request"},
            {"id": 11, "name": "CPU Device Tests", "event": "pull_request"},
            {"id": 12, "name": "Nightly", "event": "schedule"},
        ]
    }
    queued = {
        "workflow_runs": [
            {"id": 13, "name": "PR Full Build", "event": "pull_request"},
        ]
    }
    post_urls: list[str] = []

    def fake_http(
        url: str,
        method: str = "GET",
        **_kwargs: Any,
    ) -> tuple[int, Any]:
        if method == "GET":
            return 200, (in_prog if "in_progress" in url else queued)
        post_urls.append(url)
        return 202, {}

    with patch.object(ffc, "_http_request", side_effect=fake_http):
        res = ffc.cancel_github_actions(
            commit_sha="abc12345",
            repo="LMCache/LMCache",
            token="gh-tok",
            current_run_id="10",
        )

    assert [r["id"] for r in res] == [11, 13]
    assert len(post_urls) == 2


def test_only_if_build_failing_skips_when_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--only-if-build-failing does not cancel siblings when current build passed."""
    monkeypatch.setenv("BUILDKITE_API_TOKEN", "bk-tok")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-tok")

    def fake_http(url: str, **_kwargs: Any) -> tuple[int, Any]:
        assert "/builds/55" in url
        return 200, {"state": "passed"}

    with (
        patch.object(ffc, "_http_request", side_effect=fake_http),
        patch.object(ffc, "cancel_buildkite_builds") as mock_bk,
        patch.object(ffc, "cancel_github_actions") as mock_gh,
        patch.object(
            ffc.sys,
            "argv",
            [
                "fast_fail_cancel.py",
                "--commit",
                "abc12345",
                "--pr-number",
                "42",
                "--current-pipeline",
                "k3-multiprocess-smoke",
                "--current-build-number",
                "55",
                "--only-if-build-failing",
            ],
        ),
    ):
        rc = ffc.main()

    assert rc == 0
    mock_bk.assert_not_called()
    mock_gh.assert_not_called()


def test_protected_branch_and_missing_tokens_graceful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protected branches and missing tokens exit 0 without API calls."""
    monkeypatch.delenv("BUILDKITE_API_TOKEN", raising=False)
    monkeypatch.delenv("BK_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    with (
        patch.object(ffc, "_http_request") as mock_http,
        patch.object(
            ffc.sys,
            "argv",
            [
                "fast_fail_cancel.py",
                "--commit",
                "abc12345",
                "--pr-number",
                "42",
                "--branch",
                "dev",
            ],
        ),
    ):
        assert ffc.main() == 0
    mock_http.assert_not_called()

    with (
        patch.object(ffc, "_http_request") as mock_http,
        patch.object(
            ffc.sys,
            "argv",
            [
                "fast_fail_cancel.py",
                "--commit",
                "abc12345",
                "--pr-number",
                "42",
                "--branch",
                "feat/x",
            ],
        ),
    ):
        assert ffc.main() == 0
    mock_http.assert_not_called()


def test_cancel_github_actions_filters_head_repo_and_branch() -> None:
    """Stacked/duplicate-SHA PRs on other branches or repos are not cancelled."""
    runs = {
        "workflow_runs": [
            {
                "id": 21,
                "name": "PR Full Build",
                "event": "pull_request",
                "head_repository": {"full_name": "alice/LMCache"},
                "head_branch": "feat-a",
            },
            {
                "id": 22,
                "name": "PR Full Build",
                "event": "pull_request",
                "head_repository": {"full_name": "bob/LMCache"},
                "head_branch": "feat-a",
            },
            {
                "id": 23,
                "name": "PR Full Build",
                "event": "pull_request",
                "head_repository": {"full_name": "alice/LMCache"},
                "head_branch": "feat-b",
            },
        ]
    }
    post_urls: list[str] = []

    def fake_http(
        url: str,
        method: str = "GET",
        **_kwargs: Any,
    ) -> tuple[int, Any]:
        if method == "GET":
            return 200, (runs if "in_progress" in url else {"workflow_runs": []})
        post_urls.append(url)
        return 202, {}

    with patch.object(ffc, "_http_request", side_effect=fake_http):
        res = ffc.cancel_github_actions(
            commit_sha="abc12345",
            repo="LMCache/LMCache",
            token="gh-tok",
            head_repo="alice/LMCache",
            head_branch="feat-a",
        )

    assert [r["id"] for r in res] == [21]
    assert post_urls == [
        "https://api.github.com/repos/LMCache/LMCache/actions/runs/21/cancel"
    ]


def test_cancel_buildkite_lists_only_scheduled_and_running() -> None:
    """Only scheduled and running states are queried so failing builds keep logs."""
    seen_urls: list[str] = []

    def fake_http(url: str, **_kwargs: Any) -> tuple[int, Any]:
        seen_urls.append(url)
        return 200, []

    with patch.object(ffc, "_http_request", side_effect=fake_http):
        ffc.cancel_buildkite_builds(
            commit_sha="abc12345",
            pr_number="42",
            org="lmcache",
            token="bk-tok",
        )

    assert len(seen_urls) == 1
    assert "state%5B%5D=scheduled" in seen_urls[0]
    assert "state%5B%5D=running" in seen_urls[0]
    assert "failing" not in seen_urls[0]


def test_main_runs_gha_without_pr_number_and_returns_1_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GHA cancellation still runs without PR number; failed cancels return 1."""
    monkeypatch.delenv("BUILDKITE_API_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-tok")

    def fake_http(
        url: str,
        method: str = "GET",
        **_kwargs: Any,
    ) -> tuple[int, Any]:
        if method == "GET" and "in_progress" in url:
            return 200, {
                "workflow_runs": [{"id": 99, "name": "CodeQL", "event": "pull_request"}]
            }
        if method == "GET":
            return 200, {"workflow_runs": []}
        return 500, {"message": "server error"}

    with (
        patch.object(ffc, "_http_request", side_effect=fake_http),
        patch.object(
            ffc.sys,
            "argv",
            [
                "fast_fail_cancel.py",
                "--commit",
                "abc12345",
                "--repo",
                "LMCache/LMCache",
            ],
        ),
    ):
        rc = ffc.main()

    assert rc == 1


def test_http_request_retries_rate_limit_and_5xx() -> None:
    """_http_request retries HTTP 429/403 rate-limit/5xx before succeeding."""

    class FakeResp:
        def __init__(self, code: int, payload: bytes) -> None:
            self._code = code
            self._payload = payload

        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def getcode(self) -> int:
            return self._code

        def read(self) -> bytes:
            return self._payload

    hdrs = Message()
    hdrs["Retry-After"] = "0"
    rate_err = urllib.error.HTTPError(
        "https://api.github.com/test",
        403,
        "Forbidden",
        hdrs,
        BytesIO(b"API rate limit exceeded"),
    )
    calls = 0

    def fake_urlopen(_req: Any, timeout: int = 20) -> FakeResp:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise rate_err
        return FakeResp(200, b'{"ok": true}')

    with (
        patch.object(ffc.urllib.request, "urlopen", side_effect=fake_urlopen),
        patch.object(ffc.time, "sleep"),
    ):
        code, data = ffc._http_request("https://api.github.com/test", retries=2)

    assert code == 200
    assert data == {"ok": True}
    assert calls == 2


def test_fast_fail_embedded_in_code_quality_and_buildkite_yaml() -> None:
    """Fast-fail lives inside code_quality_checks.yml and required Buildkite YAML."""
    cq_path = REPO_ROOT / ".github" / "workflows" / "code_quality_checks.yml"
    cq = yaml.safe_load(cq_path.read_text(encoding="utf-8"))
    ff_job = cq["jobs"]["stop-cpu-device-on-test-failure"]
    assert set(ff_job["needs"]) == {"pre-commit", "test"}
    assert "!cancelled()" in ff_job["if"]
    assert "needs.pre-commit.result == 'failure'" in ff_job["if"]
    assert "needs.test.result == 'failure'" in ff_job["if"]
    assert "cpu-device" not in ff_job["if"]
    assert ff_job["permissions"] == {"actions": "write", "contents": "read"}
    cancel_step = ff_job["steps"][2]
    assert cancel_step["name"] == "Cancel sibling GHA runs and Buildkite PR builds"
    assert cancel_step["continue-on-error"] is True
    assert "|| true" not in cancel_step["run"]
    self_cancel_step = ff_job["steps"][3]
    assert self_cancel_step["if"] == "needs.test.result == 'failure'"

    unit_path = REPO_ROOT / ".buildkite" / "k3_tests" / "unit" / "pipeline.yml"
    unit = yaml.safe_load(unit_path.read_text(encoding="utf-8"))
    assert unit["steps"][0]["retry"] == {"automatic": [{"exit_status": -1, "limit": 1}]}
    ff_step = unit["steps"][-1]
    assert ff_step["soft_fail"] is True
    assert "$${outcome}" in ff_step["command"]
    assert "hard_failed" in ff_step["command"]
    assert "--head-branch" in ff_step["command"]


def test_repo_from_env_and_write_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_repo_from_env parses BUILDKITE_REPO; _write_summary appends summary."""
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setenv("BUILDKITE_REPO", "https://github.com/travisVux/LMCache.git")
    assert ffc._repo_from_env() == "travisVux/LMCache"

    monkeypatch.setenv("BUILDKITE_REPO", "git@github.com:LMCache/lmcache.v2.git")
    assert ffc._repo_from_env() == "LMCache/lmcache.v2"

    # Fork Buildkite branch prefix "owner:branch" matches GHA head_branch "branch"
    with patch.object(
        ffc,
        "_http_request",
        side_effect=[
            (
                200,
                {
                    "workflow_runs": [
                        {
                            "id": 77,
                            "name": "Code Quality",
                            "event": "pull_request",
                            "head_branch": "feat-fork",
                        }
                    ]
                },
            ),
            (200, {"workflow_runs": []}),
            (200, {"workflow_runs": []}),
            (200, {"workflow_runs": []}),
            (200, {"workflow_runs": []}),
            (202, {}),
        ],
    ):
        res = ffc.cancel_github_actions(
            commit_sha="abc12345",
            repo="LMCache/LMCache",
            token="gh-tok",
            head_branch="alice:feat-fork",
        )
    assert [r["id"] for r in res] == [77]

    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    ffc._write_summary(
        bk_cancelled=[{"pipeline": "k3-multiprocess-smoke", "number": 7}],
        gh_cancelled=[{"id": 99, "name": "CodeQL"}],
        reason="Required test failed",
        dry_run=False,
    )
    text = summary_file.read_text(encoding="utf-8")
    assert "k3-multiprocess-smoke" in text
    assert "CodeQL" in text
