"""Single active-pack semantic interaction port for Workspace voice turns."""

from __future__ import annotations

import asyncio
import copy
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence

import yaml
from pydantic import ValidationError

from backend.app.capability_host.tool_dispatch import dispatch_capability_tool
from backend.app.models.object_runtime import ObjectRef
from backend.app.models.workspace_voice_semantic_turn import (
    VOICE_INTERACTION_RESULT_SCHEMA_VERSION,
    WorkspaceVoiceClientAction,
    WorkspaceVoicePackInteractionResult,
)
from backend.app.services.capability_registry import get_registry
from backend.app.services.orchestration.meeting.planner_contract_execution.manifest_registry import (
    PlannerContractManifestRegistry,
)


ACTIVE_PACK_TOOL_TIMEOUT_SECONDS = 2.0
MAX_VOICE_INTENTS = 32
MAX_MATCH_PHRASES = 32
MAX_PAYLOAD_KEYS = 64
MAX_PACK_RESULT_BYTES = 64 * 1024

ToolDispatch = Callable[[str, Mapping[str, Any]], Awaitable[Any]]


def active_pack_code(session: Any) -> str:
    """Read active pack identity only from frozen Meeting session metadata."""

    metadata = getattr(session, "metadata", None)
    if not isinstance(metadata, Mapping):
        return ""
    aol = metadata.get("aol")
    nested = aol if isinstance(aol, Mapping) else {}
    for value in (
        metadata.get("active_capability_code"),
        metadata.get("active_pack_code"),
        metadata.get("coach_pack"),
        nested.get("active_capability_code"),
        nested.get("active_pack_code"),
    ):
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def _read_manifest(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return value if isinstance(value, Mapping) else {}


def manifest_for_active_pack(
    pack_code: str,
    *,
    registry: Any | None = None,
) -> Mapping[str, Any]:
    if not pack_code:
        return {}
    active_registry = registry or get_registry()
    capability = active_registry.get_capability(pack_code)
    if isinstance(capability, Mapping):
        manifest = capability.get("manifest")
        if isinstance(manifest, Mapping):
            return manifest
    for manifest_path in (
        PlannerContractManifestRegistry().capability_manifest_paths(pack_code)
    ):
        if manifest_path.exists():
            manifest = _read_manifest(manifest_path)
            if manifest:
                return manifest
    return {}


def _normalized_intent_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\s\W_]+", "", normalized, flags=re.UNICODE)


def _legacy_client_action(
    *,
    transcript: str,
    pack_code: str,
    contract: Mapping[str, Any],
) -> WorkspaceVoiceClientAction | None:
    intents = contract.get("voice_intents")
    if not isinstance(intents, list):
        return None
    normalized_transcript = _normalized_intent_text(transcript)
    for raw_intent in intents[:MAX_VOICE_INTENTS]:
        if not isinstance(raw_intent, Mapping):
            continue
        match = raw_intent.get("match")
        action = raw_intent.get("action")
        if not isinstance(match, Mapping) or not isinstance(action, Mapping):
            continue
        phrases = match.get("phrases")
        if not isinstance(phrases, list):
            continue
        normalized_phrases = [
            phrase
            for raw_phrase in phrases[:MAX_MATCH_PHRASES]
            if (phrase := _normalized_intent_text(raw_phrase))
        ]
        mode = str(match.get("mode") or "contains").strip()
        matched = (
            normalized_transcript in normalized_phrases
            if mode == "exact"
            else mode == "contains"
            and any(phrase in normalized_transcript for phrase in normalized_phrases)
        )
        payload = action.get("payload")
        if not matched or not isinstance(payload, Mapping):
            continue
        if len(payload) > MAX_PAYLOAD_KEYS:
            continue
        intent_code = str(raw_intent.get("code") or "").strip()
        action_code = str(action.get("code") or "").strip()
        if not intent_code or not action_code:
            continue
        return WorkspaceVoiceClientAction(
            pack_code=pack_code,
            intent_code=intent_code,
            action_code=action_code,
            requires_confirmation=bool(action.get("requires_confirmation")),
            payload=copy.deepcopy(dict(payload)),
        )
    return None


def resolve_legacy_voice_client_action(
    *,
    transcript: str,
    session: Any,
    registry: Any | None = None,
) -> WorkspaceVoiceClientAction | None:
    """Compatibility delegate for v1 manifests; v2 is never double-matched."""

    pack_code = active_pack_code(session)
    manifest = manifest_for_active_pack(pack_code, registry=registry)
    contract = manifest.get("aol_client_interactions")
    if not isinstance(contract, Mapping):
        return None
    if contract.get("schema_version") == "aol.client_interactions.v2":
        return None
    return _legacy_client_action(
        transcript=transcript,
        pack_code=pack_code,
        contract=contract,
    )


def _not_applicable(
    *,
    decision_code: str = "not_applicable",
    client_action: WorkspaceVoiceClientAction | None = None,
) -> WorkspaceVoicePackInteractionResult:
    return WorkspaceVoicePackInteractionResult(
        schema_version=VOICE_INTERACTION_RESULT_SCHEMA_VERSION,
        outcome="not_applicable",
        decision_code=decision_code,
        confidence=1.0,
        client_action=client_action,
    )


def _clarification(reason: str) -> WorkspaceVoicePackInteractionResult:
    return WorkspaceVoicePackInteractionResult(
        schema_version=VOICE_INTERACTION_RESULT_SCHEMA_VERSION,
        outcome="clarification",
        decision_code=reason,
        confidence=0.0,
        clarification_reason=reason,
    )


def _tool_name(contract: Mapping[str, Any], manifest: Mapping[str, Any]) -> str:
    resolver = contract.get("semantic_resolver")
    if not isinstance(resolver, Mapping):
        return ""
    tool_name = str(resolver.get("tool_name") or "").strip()
    result_schema = str(resolver.get("result_schema_version") or "").strip()
    if (
        not tool_name
        or result_schema != VOICE_INTERACTION_RESULT_SCHEMA_VERSION
    ):
        return ""
    declared_tools = {
        str(tool.get("name") or "").strip()
        for tool in list(manifest.get("tools") or [])
        if isinstance(tool, Mapping)
    }
    return tool_name if tool_name in declared_tools else ""


def _validate_result_size(value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_PACK_RESULT_BYTES:
        raise ValueError("active_pack_voice_result_too_large")


def _canonical_ref(ref: ObjectRef, *, workspace_id: str) -> ObjectRef:
    expected_uri = f"mindscape://{ref.owner_pack}/{ref.object_kind}/{ref.object_id}"
    if ref.uri != expected_uri:
        raise ValueError("pack_candidate_object_ref_invalid")
    if ref.workspace_id and ref.workspace_id != workspace_id:
        raise ValueError("pack_candidate_workspace_mismatch")
    return ref.model_copy(update={"workspace_id": workspace_id})


def _validate_pack_result(
    result: WorkspaceVoicePackInteractionResult,
    *,
    pack_code: str,
    workspace_id: str,
    manifest: Mapping[str, Any],
) -> WorkspaceVoicePackInteractionResult:
    export_kinds = {
        str(entry.get("kind") or "").strip()
        for entry in list(manifest.get("object_exports") or [])
        if isinstance(entry, Mapping)
    }
    projection_kinds = {
        str(entry.get("kind") or "").strip()
        for entry in list(manifest.get("meeting_projections") or [])
        if isinstance(entry, Mapping)
    }
    candidates = []
    for candidate in result.candidates:
        ref = _canonical_ref(candidate.object_ref, workspace_id=workspace_id)
        if (
            ref.owner_pack != pack_code
            or ref.object_kind not in export_kinds
            or ref.object_kind not in projection_kinds
        ):
            raise ValueError("pack_candidate_not_meeting_addressable")
        candidates.append(candidate.model_copy(update={"object_ref": ref}))
    if (
        result.client_action is not None
        and result.client_action.pack_code != pack_code
    ):
        raise ValueError("pack_client_action_identity_mismatch")
    expected_evidence_prefix = f"mindscape://{pack_code}/"
    if any(
        not evidence.source_ref.startswith(expected_evidence_prefix)
        for evidence in result.evidence
    ):
        raise ValueError("pack_evidence_identity_mismatch")
    return result.model_copy(update={"candidates": candidates})


class ActivePackVoiceInteractionPort:
    """Invoke exactly one admitted active-pack semantic decision owner."""

    def __init__(
        self,
        *,
        registry: Any | None = None,
        tool_dispatch: ToolDispatch = dispatch_capability_tool,
        timeout_seconds: float = ACTIVE_PACK_TOOL_TIMEOUT_SECONDS,
    ) -> None:
        self._registry = registry
        self._tool_dispatch = tool_dispatch
        self._timeout_seconds = timeout_seconds

    async def resolve(
        self,
        *,
        transcript: str,
        workspace_id: str,
        language: str | None,
        session: Any,
        resolved_references: Sequence[ObjectRef],
    ) -> WorkspaceVoicePackInteractionResult:
        pack_code = active_pack_code(session)
        manifest = manifest_for_active_pack(pack_code, registry=self._registry)
        contract = manifest.get("aol_client_interactions")
        if not pack_code or not isinstance(contract, Mapping):
            return _not_applicable()

        if contract.get("schema_version") != "aol.client_interactions.v2":
            action = _legacy_client_action(
                transcript=transcript,
                pack_code=pack_code,
                contract=contract,
            )
            return _not_applicable(
                decision_code="declared_client_action" if action else "not_applicable",
                client_action=action,
            )

        tool_name = _tool_name(contract, manifest)
        if not tool_name:
            return _clarification("active_pack_voice_contract_invalid")
        try:
            raw_result = await asyncio.wait_for(
                self._tool_dispatch(
                    f"{pack_code}.{tool_name}",
                    {
                        "transcript": transcript,
                        "tenant_id": workspace_id,
                        "workspace_id": workspace_id,
                        "language": language,
                        "resolved_references": [
                            ref.model_dump(mode="json", exclude_none=True)
                            for ref in resolved_references
                        ],
                        "declared_voice_intents": list(
                            contract.get("voice_intents") or []
                        )[:MAX_VOICE_INTENTS],
                    },
                ),
                timeout=self._timeout_seconds,
            )
            _validate_result_size(raw_result)
            validated = WorkspaceVoicePackInteractionResult.model_validate(raw_result)
            return _validate_pack_result(
                validated,
                pack_code=pack_code,
                workspace_id=workspace_id,
                manifest=manifest,
            )
        except asyncio.TimeoutError:
            return _clarification("active_pack_voice_timeout")
        except (RuntimeError, TypeError, ValueError, ValidationError):
            return _clarification("active_pack_voice_unavailable")


__all__ = [
    "ActivePackVoiceInteractionPort", "active_pack_code",
    "manifest_for_active_pack", "resolve_legacy_voice_client_action",
]
