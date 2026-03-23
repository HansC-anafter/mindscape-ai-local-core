"""
Lazy shared singleton access for playbook execution services.

The execution routes are imported during FastAPI app startup. Constructing
PlaybookRunExecutor / PlaybookRunner at import time can pull a large service
graph into startup and block the API from binding its socket. Keep the public
`playbook_executor` / `playbook_runner` names stable, but instantiate them only
when a route or service first dereferences them.
"""

from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING, Callable, Generic, TypeVar

if TYPE_CHECKING:
    from ...services.playbook_run_executor import PlaybookRunExecutor
    from ...services.playbook_runner import PlaybookRunner
    from ...services.playbook_service import PlaybookService

T = TypeVar("T")


class _LazySingletonProxy(Generic[T]):
    def __init__(self, factory: Callable[[], T]) -> None:
        object.__setattr__(self, "_factory", factory)
        object.__setattr__(self, "_instance", None)
        object.__setattr__(self, "_lock", Lock())

    def _get_instance(self) -> T:
        instance = object.__getattribute__(self, "_instance")
        if instance is not None:
            return instance

        lock = object.__getattribute__(self, "_lock")
        with lock:
            instance = object.__getattribute__(self, "_instance")
            if instance is None:
                instance = object.__getattribute__(self, "_factory")()
                object.__setattr__(self, "_instance", instance)
        return instance

    def __getattr__(self, name: str):
        return getattr(self._get_instance(), name)

    def __setattr__(self, name: str, value) -> None:
        if name in {"_factory", "_instance", "_lock"}:
            object.__setattr__(self, name, value)
            return
        setattr(self._get_instance(), name, value)

    def __repr__(self) -> str:
        instance = object.__getattribute__(self, "_instance")
        if instance is None:
            return "<LazySingletonProxy unresolved>"
        return repr(instance)


def _create_playbook_executor() -> "PlaybookRunExecutor":
    from ...services.playbook_run_executor import PlaybookRunExecutor

    return PlaybookRunExecutor()


def _create_playbook_runner() -> "PlaybookRunner":
    from ...services.playbook_runner import PlaybookRunner

    return PlaybookRunner()


def _create_playbook_service() -> "PlaybookService":
    from ...services.mindscape_store import MindscapeStore
    from ...services.playbook_service import PlaybookService

    return PlaybookService(store=MindscapeStore())


playbook_executor: "PlaybookRunExecutor" = _LazySingletonProxy(_create_playbook_executor)  # type: ignore[assignment]
playbook_runner: "PlaybookRunner" = _LazySingletonProxy(_create_playbook_runner)  # type: ignore[assignment]
playbook_service: "PlaybookService" = _LazySingletonProxy(_create_playbook_service)  # type: ignore[assignment]
