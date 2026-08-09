"""Candidate capability import facade for staged migration graphs."""

from __future__ import annotations

import importlib
import threading
from pathlib import Path
from types import ModuleType


_IMPORT_SCOPE_LOCK = threading.RLock()


class CandidateCapabilityImportScope:
    """Temporarily expose one staging root through ``app.capabilities``."""

    def __init__(self, capabilities_dir: Path, capability_code: str):
        self.capabilities_dir = Path(capabilities_dir).resolve()
        self.capability_code = str(capability_code).strip()
        self._package: ModuleType | None = None
        self._original_path: list[str] | None = None
        self._active = False

    def activate(self) -> None:
        if self._active:
            return
        candidate_dir = self.capabilities_dir / self.capability_code
        if not candidate_dir.is_dir():
            raise RuntimeError(
                f"candidate_capability_import_root_missing:{candidate_dir}"
            )

        _IMPORT_SCOPE_LOCK.acquire()
        try:
            package = importlib.import_module("app.capabilities")
            original_path = [str(path) for path in package.__path__]
            candidate_root = self.capabilities_dir.as_posix()
            package.__path__ = [
                candidate_root,
                *(path for path in original_path if path != candidate_root),
            ]
            importlib.invalidate_caches()
            self._package = package
            self._original_path = original_path
            self._active = True
        except Exception:
            _IMPORT_SCOPE_LOCK.release()
            raise

    def restore(self) -> None:
        if not self._active:
            return
        try:
            if self._package is not None and self._original_path is not None:
                self._package.__path__ = list(self._original_path)
                importlib.invalidate_caches()
        finally:
            self._active = False
            self._package = None
            self._original_path = None
            _IMPORT_SCOPE_LOCK.release()
