"""Shared support for cross-instance handoff E2E tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_TEST_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _TEST_DIR.parent
_MODELS_DIR = _BACKEND_ROOT / "app" / "models"

_handoff_model_mod = _load_module("handoff_models", _MODELS_DIR / "handoff.py")
HandoffIn = _handoff_model_mod.HandoffIn
Commitment = _handoff_model_mod.Commitment

_bundle_mod = _load_module("signed_bundle", _MODELS_DIR / "signed_bundle.py")
SignedHandoffBundle = _bundle_mod.SignedHandoffBundle


class InMemoryRegistryV2:
    """In-memory registry with trace-context support for cross-instance tests."""

    def __init__(self) -> None:
        self.handoffs: dict[str, dict[str, Any]] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._valid_transitions = {
            "created": ["claimed", "cancelled"],
            "claimed": ["committed", "cancelled"],
            "committed": ["dispatched", "cancelled"],
            "dispatched": ["completed", "failed"],
            "failed": ["claimed"],
        }

    def create(
        self,
        handoff_id: str,
        tenant_id: str,
        payload: dict[str, Any],
        source_device_id: str,
        target_device_id: str | None = None,
    ) -> dict[str, str]:
        self.handoffs[handoff_id] = {
            "id": handoff_id,
            "tenant_id": tenant_id,
            "spec_version": "0.1",
            "state": "created",
            "payload_json": payload,
            "source_device_id": source_device_id,
            "target_device_id": target_device_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.events[handoff_id] = []
        self._append_event(handoff_id, "created", source_device_id, payload)
        return {"handoff_id": handoff_id, "state": "created"}

    def transition(
        self,
        handoff_id: str,
        target_state: str,
        actor_device_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        with self._lock:
            handoff = self.handoffs[handoff_id]
            current = handoff["state"]
            allowed = self._valid_transitions.get(current, [])
            if target_state not in allowed:
                raise ValueError(f"Invalid: {current} -> {target_state}")
            previous_state = current
            handoff["state"] = target_state
            self._append_event(
                handoff_id,
                target_state,
                actor_device_id,
                payload or {},
            )
        return {"previous_state": previous_state, "new_state": target_state}

    def append_event(
        self,
        handoff_id: str,
        event_type: str,
        actor_device_id: str,
        payload: dict[str, Any] | None = None,
        trace_context: dict[str, Any] | None = None,
    ) -> str:
        return self._append_event(
            handoff_id,
            event_type,
            actor_device_id,
            payload or {},
            trace_context=trace_context,
        )

    def get_timeline(self, handoff_id: str) -> dict[str, Any]:
        events = self.events.get(handoff_id, [])
        return {
            "handoff_id": handoff_id,
            "events": events,
            "count": len(events),
            "chain_valid": self._verify_chain(events),
        }

    def get_trace_dag(self, handoff_id: str) -> dict[str, Any]:
        events = self.events.get(handoff_id, [])
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        trace_ids_seen: dict[str, str] = {}

        for index, event in enumerate(events):
            trace_context = event.get("trace_context") or {}
            node = {
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "device_id": event["actor_device_id"],
                "trace_id": trace_context.get("trace_id"),
                "parent_trace_id": trace_context.get("parent_trace_id"),
            }
            nodes.append(node)

            if index > 0:
                edges.append(
                    {
                        "from": events[index - 1]["event_id"],
                        "to": event["event_id"],
                        "relation": "hash_chain",
                    }
                )

            trace_id = trace_context.get("trace_id")
            parent_trace_id = trace_context.get("parent_trace_id")
            if trace_id:
                trace_ids_seen[trace_id] = event["event_id"]
            if parent_trace_id and parent_trace_id in trace_ids_seen:
                edges.append(
                    {
                        "from": trace_ids_seen[parent_trace_id],
                        "to": event["event_id"],
                        "relation": "cross_instance",
                    }
                )

        return {
            "handoff_id": handoff_id,
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    @staticmethod
    def _compute_payload_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _compute_chain_hash(prev_event_id: str, prev_payload_hash: str) -> str:
        combined = f"{prev_event_id}{prev_payload_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _append_event(
        self,
        handoff_id: str,
        event_type: str,
        actor_device_id: str,
        payload: dict[str, Any],
        trace_context: dict[str, Any] | None = None,
    ) -> str:
        events = self.events[handoff_id]
        event_id = str(uuid.uuid4())
        payload_hash = self._compute_payload_hash(payload)

        if events:
            previous = events[-1]
            prev_event_hash = self._compute_chain_hash(
                previous["event_id"],
                previous["payload_hash"],
            )
        else:
            prev_event_hash = "0" * 64

        event = {
            "event_id": event_id,
            "handoff_id": handoff_id,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor_device_id": actor_device_id,
            "payload_hash": payload_hash,
            "prev_event_hash": prev_event_hash,
            "payload_json": payload,
        }
        if trace_context:
            event["trace_context"] = trace_context
        events.append(event)
        return event_id

    def _verify_chain(self, events: list[dict[str, Any]]) -> bool:
        for index, event in enumerate(events):
            if index == 0:
                if event["prev_event_hash"] != "0" * 64:
                    return False
            else:
                previous = events[index - 1]
                expected = self._compute_chain_hash(
                    previous["event_id"],
                    previous["payload_hash"],
                )
                if event["prev_event_hash"] != expected:
                    return False
        return True
