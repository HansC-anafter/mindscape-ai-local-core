#!/usr/bin/env python3
"""
CI guard for the local-core core_llm compatibility boundary.

The tracked source-of-truth lives under backend/app/system_capabilities/core_llm.
The manifest-backed capability path may only contain thin shims.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CAPABILITY_ROOT = REPO_ROOT / "backend/app/capabilities/core_llm"
SOURCE_ROOT = REPO_ROOT / "backend/app/system_capabilities/core_llm"

EXPECTED_SERVICE_MODULES = ("data_utils", "generate", "multimodal", "structured")
EXPECTED_SHIM_TEMPLATE = '''"""
Compatibility shim for the manifest-backed ``core_llm`` capability namespace.

Edit ``backend.app.system_capabilities.core_llm.services.{module_name}`` instead.
"""

import sys

from backend.app.system_capabilities.core_llm.services import {module_name} as _impl

sys.modules[__name__] = _impl
'''


def _error(message: str) -> str:
    return f"[core_llm-boundary] {message}"


def main() -> int:
    errors: list[str] = []

    if not SOURCE_ROOT.exists():
        errors.append(
            _error(
                f"Missing system source root: {SOURCE_ROOT.relative_to(REPO_ROOT)}"
            )
        )

    allowed_capability_files = {
        Path("backend/app/capabilities/core_llm/__init__.py"),
        Path("backend/app/capabilities/core_llm/manifest.yaml"),
        Path("backend/app/capabilities/core_llm/services/__init__.py"),
    }
    allowed_capability_files.update(
        Path(f"backend/app/capabilities/core_llm/services/{name}.py")
        for name in EXPECTED_SERVICE_MODULES
    )

    actual_capability_files = {
        path.relative_to(REPO_ROOT)
        for path in CAPABILITY_ROOT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not path.name.startswith(".")
    }
    unexpected_capability_files = sorted(
        actual_capability_files - allowed_capability_files
    )
    if unexpected_capability_files:
        errors.append(
            _error(
                "Unexpected tracked files remain under backend/app/capabilities/core_llm: "
                + ", ".join(str(path) for path in unexpected_capability_files)
            )
        )

    source_service_dir = SOURCE_ROOT / "services"
    for module_name in EXPECTED_SERVICE_MODULES:
        source_file = source_service_dir / f"{module_name}.py"
        if not source_file.exists():
            errors.append(
                _error(
                    f"Missing system source module: {source_file.relative_to(REPO_ROOT)}"
                )
            )

        shim_file = CAPABILITY_ROOT / "services" / f"{module_name}.py"
        if not shim_file.exists():
            errors.append(
                _error(
                    f"Missing capability shim: {shim_file.relative_to(REPO_ROOT)}"
                )
            )
            continue

        expected = EXPECTED_SHIM_TEMPLATE.format(module_name=module_name)
        actual = shim_file.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(
                _error(
                    f"Capability shim drift detected in {shim_file.relative_to(REPO_ROOT)}; "
                    "edit the system source module instead."
                )
            )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("core_llm boundary OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

