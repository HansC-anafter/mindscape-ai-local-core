"""Request-local evidence for exact incident containment mutations."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Mapping


_MUTATION_EVIDENCE: ContextVar[Mapping[str, str]] = ContextVar(
    "runtime_database_mutation_evidence",
    default={},
)


def current_mutation_evidence() -> dict[str, str]:
    return dict(_MUTATION_EVIDENCE.get())


@contextmanager
def runtime_database_mutation_context(
    **evidence: Any,
) -> Iterator[dict[str, str]]:
    normalized = {
        str(key): str(value).strip()
        for key, value in evidence.items()
        if value is not None and str(value).strip()
    }
    token = _MUTATION_EVIDENCE.set(normalized)
    try:
        yield normalized
    finally:
        _MUTATION_EVIDENCE.reset(token)


__all__ = [
    "current_mutation_evidence",
    "runtime_database_mutation_context",
]
