"""Pytest import bootstrap for installed capability-pack modules."""

from __future__ import annotations

import sys
from pathlib import Path


LOCAL_CORE_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "mindscape-ai-local-core"
)
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
APP_ROOT = BACKEND_ROOT / "app"

for path in (LOCAL_CORE_ROOT, BACKEND_ROOT, APP_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
