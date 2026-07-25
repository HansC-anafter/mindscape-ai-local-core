"""Pinned in-process version dispatch; missing history support fails closed."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


class IncompatibleHistory(RuntimeError):
    """Raised when a pinned workflow dependency is absent from this build."""


@dataclass
class CompatibilityRegistry:
    workflow_definitions: dict[str, object] = field(default_factory=dict)
    reducers: dict[str, Callable] = field(default_factory=dict)
    effect_adapters: dict[str, object] = field(default_factory=dict)

    def require(self, identity: dict) -> tuple[object, Callable, object]:
        keys = (
            ("workflow_definition_version", self.workflow_definitions),
            ("reducer_version", self.reducers),
            ("effect_adapter_registry_version", self.effect_adapters),
        )
        resolved = []
        for field_name, registry in keys:
            version = identity[field_name]
            if version not in registry:
                raise IncompatibleHistory(
                    f"pinned {field_name} {version!r} is unavailable"
                )
            resolved.append(registry[version])
        return tuple(resolved)  # type: ignore[return-value]
