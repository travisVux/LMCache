# SPDX-License-Identifier: Apache-2.0
"""Unit tests for .buildkite/scripts/fast_fail_cancel.py."""

# Future
from __future__ import annotations

# Standard
from pathlib import Path
from typing import Any
from unittest.mock import patch
import importlib.util

# Third Party
import pytest

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
