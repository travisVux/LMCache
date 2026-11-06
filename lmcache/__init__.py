# SPDX-License-Identifier: Apache-2.0

# First Party
from lmcache.logging import init_logger

# --------------------------
# Backend instance & Device detection
# --------------------------
from lmcache.v1.platform import torch_dev as torch_dev
from lmcache.v1.platform import torch_device_type as torch_device_type

try:
    # First Party
    from lmcache._version import __version__
except ImportError:
    __version__ = "unknown"

logger = init_logger(__name__)

__all__ = ["__version__", "torch_dev", "torch_device_type"]


def _check_hardware_distribution_conflicts():
    try:
        import importlib.metadata
        installed = []
        for pkg in (
            "lmcache",
            "lmcache-cu129",
            "lmcache-rocm",
            "lmcache-rocm-torch210",
            "lmcache-xpu",
            "lmcache-musa",
            "lmcache-rbln",
        ):
            try:
                importlib.metadata.version(pkg)
                installed.append(pkg)
            except importlib.metadata.PackageNotFoundError:
                pass
        if len(installed) > 1:
            import warnings
            warnings.warn(
                f"Multiple LMCache hardware packages detected: {installed}. "
                "Having more than one package installed in the same environment may cause "
                "unexpected binary conflicts. Please uninstall the inactive packages.",
                UserWarning,
                stacklevel=2,
            )
    except Exception:
        pass


_check_hardware_distribution_conflicts()


try:
    # First Party
    from lmcache.v1.platform import resolve_device_ops

    device_ops = resolve_device_ops(torch_device_type)
    __all__.append("device_ops")
except Exception as exc:
    logger.warning(
        "No compute backend loaded; CLI-only mode (torch/numba not installed). "
        "Reason: %s",
        exc,
    )
