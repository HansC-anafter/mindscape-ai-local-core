"""Neutral outcome-adapter registry for projection/meeting consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class OutcomeAdapterDescriptor:
    adapter_id: str
    outcome_kind: str
    handler: Callable[[Mapping[str, Any]], Mapping[str, Any]]


class OutcomeAdapterDispatcher:
    """Dispatch by registered descriptor; no product-pack literal is embedded."""

    def __init__(self, descriptors: tuple[OutcomeAdapterDescriptor, ...] = ()) -> None:
        self._descriptors = {item.adapter_id: item for item in descriptors}

    def register(self, descriptor: OutcomeAdapterDescriptor) -> None:
        if descriptor.adapter_id in self._descriptors:
            raise ValueError(f"duplicate_outcome_adapter:{descriptor.adapter_id}")
        self._descriptors[descriptor.adapter_id] = descriptor

    def dispatch(self, adapter_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        descriptor = self._descriptors.get(adapter_id)
        if descriptor is None:
            raise KeyError(f"unknown_outcome_adapter:{adapter_id}")
        result = descriptor.handler(payload)
        if not isinstance(result, Mapping):
            raise TypeError("outcome_adapter_must_return_mapping")
        return dict(result)

    def list(self) -> tuple[OutcomeAdapterDescriptor, ...]:
        return tuple(self._descriptors.values())


__all__ = ["OutcomeAdapterDescriptor", "OutcomeAdapterDispatcher"]
