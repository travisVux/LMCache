# SPDX-License-Identifier: Apache-2.0
"""LMCache setup script — policy-driven extension build.

Uses the strategy pattern so that each platform lives in its own file
under ``setup_extensions/build_profiles/``.  Adding a new platform requires
zero changes to this file.
"""

# Standard
from pathlib import Path
from types import ModuleType
import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Dynamic Environment Variable Handling
# ---------------------------------------------------------------------------
TARGET_DEVICE = os.environ.get("LMCACHE_TARGET_DEVICE", "").strip().lower()
if TARGET_DEVICE:
    for var in ["BUILD_WITH_CUDA", "BUILD_WITH_ROCM", "BUILD_WITH_SYCL", "BUILD_WITH_MUSA", "BUILD_WITH_RBLN"]:
        os.environ.pop(var, None)
    if TARGET_DEVICE in ("cuda", "cu129", "cu128", "cu130", "cu124", "cu121"):
        os.environ["BUILD_WITH_CUDA"] = "1"
    elif TARGET_DEVICE in ("rocm", "rocm-torch210", "hip"):
        os.environ["BUILD_WITH_ROCM"] = "1"
    elif TARGET_DEVICE in ("xpu", "sycl", "intel"):
        os.environ["BUILD_WITH_SYCL"] = "1"
    elif TARGET_DEVICE in ("musa", "mthreads"):
        os.environ["BUILD_WITH_MUSA"] = "1"
    elif TARGET_DEVICE in ("rbln", "rebellions"):
        os.environ["BUILD_WITH_RBLN"] = "1"
    elif TARGET_DEVICE in ("cpu", "none"):
        os.environ["NO_GPU_EXT"] = "1"

PACKAGE_NAME = os.environ.get("LMCACHE_PACKAGE_NAME", "lmcache").strip()
BUILD_VERSION = os.environ.get("LMCACHE_BUILD_VERSION", "").strip()
if PACKAGE_NAME and PACKAGE_NAME != "lmcache":
    import setuptools.dist

    _orig_finalize = setuptools.dist.Distribution.finalize_options

    def _finalize_options(self):
        _orig_finalize(self)
        self.metadata.name = PACKAGE_NAME

    setuptools.dist.Distribution.finalize_options = _finalize_options

if BUILD_VERSION:
    os.environ["SETUPTOOLS_SCM_PRETEND_VERSION"] = BUILD_VERSION

ROOT_DIR = Path(__file__).parent
# Ensure the project root is importable when ``setup.py`` runs inside a
# PEP 517 build subprocess (where CWD is not added to ``sys.path``).
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Third Party
from setuptools import find_packages, setup  # noqa: E402
from setuptools.command.build_py import build_py as _build_py  # noqa: E402

# First Party
from setup_extensions import BuildPolicy, BuildProfile  # noqa: E402


def _read_requirements(path: Path) -> list[str]:
    if not path.exists():
        return []
    reqs: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            reqs.append(line)
    return reqs


def _load_proto_generator() -> ModuleType:
    """Load the proto generator without importing the LMCache package."""
    generator_path = (
        ROOT_DIR
        / "lmcache"
        / "v1"
        / "multiprocess"
        / "transport"
        / "grpc_impl"
        / "_proto_gen"
        / "_generate.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_lmcache_proto_generate", generator_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load gRPC proto generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _BuildPyWithGrpcStubs(_build_py):
    """Generate ignored gRPC bindings before packaging LMCache."""

    def run(self) -> None:
        distribution_name = self.distribution.get_name().replace("_", "-").lower()
        if distribution_name != "lmcache-cli":
            generator = _load_proto_generator()
            for package in generator.GENERATED_PACKAGES:
                generator.generate(package)
        super().run()


if __name__ == "__main__":
    policy = BuildPolicy()
    profile = policy.resolve_profile()
    ext_modules, cmdclass, req_file = policy.collect_extensions(profile)
    cmdclass["build_py"] = _BuildPyWithGrpcStubs

    install_requires = _read_requirements(ROOT_DIR / "requirements" / "common.txt")
    # Platform-neutral extras; the build profile adds its own below.
    extras_require: dict[str, list[str]] = {
        "kafka": _read_requirements(ROOT_DIR / "requirements" / "kafka.txt"),
        "raw-block": ["lmcache-rust-raw-block-io"],
        "grpc-native": _read_requirements(
            ROOT_DIR / "requirements" / "grpc_native.txt"
        ),
    }
    if (
        not BuildProfile.is_gpu_ext_disabled()
        and req_file is not None
        and profile is not None
    ):
        install_requires += _read_requirements(ROOT_DIR / "requirements" / req_file)
        for extra_name, extra_req_file in profile.extras_requirements().items():
            extras_require[extra_name] = _read_requirements(
                ROOT_DIR / "requirements" / extra_req_file
            )

    setup_kwargs = {
        "packages": find_packages(exclude=("csrc",)),
        "ext_modules": ext_modules,
        "cmdclass": cmdclass,
        "include_package_data": True,
        "install_requires": install_requires,
        "extras_require": extras_require,
    }
    if BUILD_VERSION:
        setup_kwargs["version"] = BUILD_VERSION

    setup(**setup_kwargs)
