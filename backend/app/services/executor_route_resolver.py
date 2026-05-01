"""
Canonical workspace-scoped executor route resolution.

This service normalizes workspace-aware route selection for pool-backed
CLI runtimes into a single contract so downstream consumers do not need
surface-specific resolver branching.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional


_SUPPORTED_SURFACES = frozenset({"codex_cli", "gemini_cli"})


@dataclass(frozen=True)
class ExecutorRouteSelection:
    """Normalized route selection for a workspace-scoped CLI surface."""

    surface: str
    executor_runtime: str
    requested_workspace_id: str
    effective_workspace_id: str
    preferred_runtime_id: Optional[str]
    selection_reason: str
    auth_workspace_id: Optional[str] = None
    source_workspace_id: Optional[str] = None
    trace: tuple[dict[str, Any], ...] = ()

    @property
    def policy_mode(self) -> str:
        """Pinned when a concrete runtime is pre-selected, else no concrete runtime is bound yet."""
        if self.selection_reason == "workspace_pool" and not self.preferred_runtime_id:
            return "pool_rotation"
        return "pinned_runtime" if self.preferred_runtime_id else "unbound_runtime"


class ExecutorRouteResolver:
    """Resolve workspace-scoped route policy for supported CLI surfaces."""

    def __init__(
        self,
        resolver_factories: Optional[Mapping[str, Callable[[], Any]]] = None,
    ):
        self._resolver_factories = dict(resolver_factories or self._default_factories())

    def supports_surface(self, surface: str) -> bool:
        return self._normalize_surface(surface) in self._resolver_factories

    def resolve(
        self,
        *,
        surface: str,
        workspace_id: str,
        auth_workspace_id: Optional[str] = None,
        source_workspace_id: Optional[str] = None,
    ) -> ExecutorRouteSelection:
        normalized_surface = self._normalize_surface(surface)
        factory = self._resolver_factories.get(normalized_surface)
        if factory is None:
            supported = ", ".join(sorted(self._resolver_factories))
            raise ValueError(
                f"Unsupported executor route surface '{surface}'. Supported: {supported}"
            )

        resolver = factory()
        selection = resolver.resolve(
            workspace_id=workspace_id,
            auth_workspace_id=auth_workspace_id,
            source_workspace_id=source_workspace_id,
        )
        return ExecutorRouteSelection(
            surface=normalized_surface,
            executor_runtime=normalized_surface,
            requested_workspace_id=selection.requested_workspace_id,
            effective_workspace_id=selection.effective_workspace_id,
            preferred_runtime_id=getattr(selection, "selected_runtime_id", None),
            selection_reason=selection.selection_reason,
            auth_workspace_id=getattr(selection, "auth_workspace_id", None),
            source_workspace_id=getattr(selection, "source_workspace_id", None),
            trace=tuple(getattr(selection, "trace", ()) or ()),
        )

    @staticmethod
    def _normalize_surface(surface: str) -> str:
        return str(surface or "").strip().lower()

    @staticmethod
    def _default_factories() -> Mapping[str, Callable[[], Any]]:
        return {
            "codex_cli": ExecutorRouteResolver._build_codex_resolver,
            "gemini_cli": ExecutorRouteResolver._build_gca_resolver,
        }

    @staticmethod
    def _build_codex_resolver():
        from backend.app.services.codex_workspace_resolver import CodexWorkspaceResolver

        return CodexWorkspaceResolver()

    @staticmethod
    def _build_gca_resolver():
        from backend.app.services.gca_workspace_resolver import GCAWorkspaceResolver

        return GCAWorkspaceResolver()
