# SPDX-License-Identifier: Apache-2.0
import importlib.metadata
import unittest
from unittest.mock import patch
import warnings
from lmcache import _check_hardware_distribution_conflicts


class TestConflictGuard(unittest.TestCase):
    def test_conflict_guard_warns_on_multiple_packages(self):
        def mock_version(pkg_name):
            if pkg_name in ("lmcache", "lmcache-rocm"):
                return "0.5.8"
            raise importlib.metadata.PackageNotFoundError(pkg_name)

        with patch("importlib.metadata.version", side_effect=mock_version):
            with warnings.catch_warnings(record=True) as recorded:
                warnings.simplefilter("always")
                _check_hardware_distribution_conflicts()
                self.assertTrue(any("Multiple LMCache hardware packages detected" in str(w.message) for w in recorded))

    def test_conflict_guard_no_warning_on_single_package(self):
        def mock_version(pkg_name):
            if pkg_name == "lmcache-cu129":
                return "0.5.8"
            raise importlib.metadata.PackageNotFoundError(pkg_name)

        with patch("importlib.metadata.version", side_effect=mock_version):
            with warnings.catch_warnings(record=True) as recorded:
                warnings.simplefilter("always")
                _check_hardware_distribution_conflicts()
                self.assertEqual(len(recorded), 0)


if __name__ == "__main__":
    unittest.main()
