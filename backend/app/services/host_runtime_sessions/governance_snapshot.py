"""Governance snapshot helpers for host runtime turns."""

from __future__ import annotations

from hashlib import sha256
from typing import Any


def hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def compact_prompt(value: str) -> str:
    return " ".join(value.strip().split())


def build_governance_refs(
    *,
    workspace_id: str,
    prompt: str,
    context_ref: dict[str, Any] | None = None,
    intent_ref: dict[str, Any] | None = None,
    lens_ref: dict[str, Any] | None = None,
    policy_ref: dict[str, Any] | None = None,
    artifact_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt_hash = hash_text(compact_prompt(prompt))
    governance_trace_ref = f"host-runtime:{workspace_id}:{prompt_hash[:16]}"
    return {
        "prompt_hash": prompt_hash,
        "compiled_prompt_hash": prompt_hash,
        "intent_ref": intent_ref or {
            "source": "host_runtime_session_gateway",
            "intent_hash": prompt_hash,
            "version": "2026-06-16",
        },
        "lens_ref": lens_ref or {
            "source": "workspace_default",
            "lens_id": "default",
            "version": "2026-06-16",
        },
        "policy_ref": policy_ref or {
            "source": "host_runtime_policy",
            "approval_required": True,
            "version": "2026-06-16",
        },
        "context_ref": context_ref or {
            "workspace_id": workspace_id,
            "source": "aol_graph_runtime",
        },
        "artifact_ref": artifact_ref or {},
        "governance_trace_ref": governance_trace_ref,
    }


def validate_governance_refs(refs: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("intent_ref", "lens_ref", "policy_ref", "context_ref"):
        if not isinstance(refs.get(key), dict) or not refs.get(key):
            errors.append(f"{key} is required")
    if not refs.get("prompt_hash"):
        errors.append("prompt_hash is required")
    if not refs.get("compiled_prompt_hash"):
        errors.append("compiled_prompt_hash is required")
    if not refs.get("governance_trace_ref"):
        errors.append("governance_trace_ref is required")
    return errors
