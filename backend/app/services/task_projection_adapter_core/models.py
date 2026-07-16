"""Typed task projection adapter contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


ALLOWED_PROJECTION_REASONS = frozenset({"created", "identity_changed"})


@dataclass(frozen=True)
class TaskProjectionAdapterDefinition:
    """Pack-owned typed projection registration."""

    capability_code: str
    pack_id_patterns: tuple[str, ...]
    backend_path: str
    table: str
    identity_fields: tuple[str, ...]
    indexes: tuple[str, ...]
    display_backend_path: str = ""
    display_bulk_backend_path: str = ""
    capability_dir: Optional[Path] = None
    callable_override: Optional[Callable[..., Any]] = None
    display_callable_override: Optional[Callable[..., Any]] = None
    display_bulk_callable_override: Optional[Callable[..., Any]] = None

    def validate(self) -> None:
        if not self.capability_code.strip():
            raise ValueError("task_projection_adapter_capability_code_required")
        if not self.pack_id_patterns or any(
            not pattern.strip() for pattern in self.pack_id_patterns
        ):
            raise ValueError("task_projection_adapter_pack_id_patterns_required")
        if not self.backend_path.strip() and self.callable_override is None:
            raise ValueError("task_projection_adapter_backend_required")
        if not self.table.startswith(f"{self.capability_code}_"):
            raise ValueError("task_projection_adapter_table_must_be_pack_owned")
        if not self.identity_fields:
            raise ValueError("task_projection_adapter_identity_fields_required")
        if len(self.indexes) > 4:
            raise ValueError("task_projection_adapter_index_budget_exceeded")
