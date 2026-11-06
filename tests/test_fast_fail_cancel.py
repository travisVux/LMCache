import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add .buildkite/scripts to sys.path
scripts_dir = Path(__file__).resolve().parent.parent / ".buildkite" / "scripts"
sys.path.insert(0, str(scripts_dir))

import fast_fail_cancel


class TestFastFailCancel(unittest.TestCase):
    def setUp(self):
        self.commit = "a1b2c3d4e5f67890123456789012345678901234"
        self.repo = "LMCache/LMCache"
        self.org = "lmcache"

    @patch("fast_fail_cancel._http_request")
    def test_cancel_github_actions_dry_run(self, mock_http):
        # Mock response from GitHub Actions listing runs
        mock_http.side_effect = [
            (
                200,
                {
                    "workflow_runs": [
                        {
                            "id": 1001,
                            "name": "Code Quality",
                            "head_branch": "feature-1",
                            "status": "in_progress",
                            "html_url": "https://github.com/run/1001",
                        },
                        {
                            "id": 1002,
                            "name": "CPU Tests",
                            "head_branch": "feature-1",
                            "status": "in_progress",
                            "html_url": "https://github.com/run/1002",
                        },
                    ]
                },
            ),
            (200, {"workflow_runs": []}),  # queued runs
        ]

        # Dry-run with current_run_id=1001: should exclude 1001 and only list 1002
        cancelled = fast_fail_cancel.cancel_github_actions(
            commit_sha=self.commit,
            repo=self.repo,
            token="fake_gh_token",
            current_run_id="1001",
            dry_run=True,
        )

        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["id"], "1002")
        # Only GET requests were made, no POST cancel requests
        for call_args in mock_http.call_args_list:
            self.assertNotEqual(call_args[1].get("method"), "POST")

    @patch("fast_fail_cancel._http_request")
    def test_cancel_github_actions_live(self, mock_http):
        mock_http.side_effect = [
            (
                200,
                {
                    "workflow_runs": [
                        {
                            "id": 1002,
                            "name": "CPU Tests",
                            "head_branch": "feature-1",
                            "status": "in_progress",
                            "html_url": "https://github.com/run/1002",
                        }
                    ]
                },
            ),
            (200, {"workflow_runs": []}),  # queued
            (202, {}),  # cancel POST response
        ]

        cancelled = fast_fail_cancel.cancel_github_actions(
            commit_sha=self.commit,
            repo=self.repo,
            token="fake_gh_token",
            current_run_id=None,
            dry_run=False,
        )

        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["id"], "1002")
        # Verify POST cancel call
        post_calls = [c for c in mock_http.call_args_list if c[1].get("method") == "POST"]
        self.assertEqual(len(post_calls), 1)
        self.assertIn("1002/cancel", post_calls[0][0][0])

    @patch("fast_fail_cancel._http_request")
    def test_cancel_buildkite_builds_excludes_current_and_protected(self, mock_http):
        mock_http.return_value = (
            200,
            [
                {
                    "id": "bk-uuid-1",
                    "number": 101,
                    "pipeline": {"slug": "k3-unit-tests"},
                    "branch": "feature-1",
                    "state": "running",
                    "pull_request": {"id": 12},
                    "web_url": "https://buildkite.com/101",
                },
                {
                    "id": "bk-uuid-2",
                    "number": 102,
                    "pipeline": {"slug": "k3-multiprocess-test"},
                    "branch": "feature-1",
                    "state": "running",
                    "pull_request": {"id": 12},
                    "web_url": "https://buildkite.com/102",
                },
                {
                    "id": "bk-uuid-3",
                    "number": 103,
                    "pipeline": {"slug": "nightly"},
                    "branch": "dev",
                    "state": "running",
                    "pull_request": None,  # protected branch without PR
                    "web_url": "https://buildkite.com/103",
                },
            ],
        )

        cancelled = fast_fail_cancel.cancel_buildkite_builds(
            commit_sha=self.commit,
            org=self.org,
            token="fake_bk_token",
            current_build_id="bk-uuid-1",
            dry_run=True,
        )

        # bk-uuid-1 excluded because current_build_id
        # bk-uuid-3 excluded because dev branch without PR
        # Only bk-uuid-2 (102) should be selected
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["number"], 102)
        self.assertEqual(cancelled[0]["pipeline"], "k3-multiprocess-test")

    @patch("fast_fail_cancel.cancel_github_actions")
    @patch("fast_fail_cancel.cancel_buildkite_builds")
    def test_main_cli_execution(self, mock_cancel_bk, mock_cancel_gha):
        mock_cancel_gha.return_value = [{"id": "1001"}]
        mock_cancel_bk.return_value = [{"number": 101}]

        test_args = [
            "fast_fail_cancel.py",
            "--commit",
            self.commit,
            "--github-token",
            "test_gh",
            "--buildkite-token",
            "test_bk",
            "--dry-run",
        ]
        with patch.object(sys, "argv", test_args):
            exit_code = fast_fail_cancel.main()
            self.assertEqual(exit_code, 0)
            mock_cancel_gha.assert_called_once()
            mock_cancel_bk.assert_called_once()


if __name__ == "__main__":
    unittest.main()
