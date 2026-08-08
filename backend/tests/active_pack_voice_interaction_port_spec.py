from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.app.services.orchestration.meeting.active_pack_voice_interaction_port import (
    ActivePackVoiceInteractionPort,
    resolve_legacy_voice_client_action,
)


PACK_CODE = "sample_coach"


def _session(pack_code: str = PACK_CODE):
    return SimpleNamespace(metadata={"active_capability_code": pack_code})


class _Registry:
    def __init__(self, manifest):
        self.manifest = manifest

    def get_capability(self, capability_code):
        if capability_code != PACK_CODE:
            return None
        return {"manifest": self.manifest}


def _v2_manifest():
    return {
        "code": PACK_CODE,
        "tools": [{"name": "voice_interaction", "backend": "sample:resolve"}],
        "object_exports": [{"kind": "segment"}],
        "meeting_projections": [{"kind": "segment"}],
        "aol_client_interactions": {
            "schema_version": "aol.client_interactions.v2",
            "semantic_resolver": {
                "tool_name": "voice_interaction",
                "result_schema_version": "aol.voice_interaction_result.v1",
            },
            "voice_intents": [],
        },
    }


@pytest.mark.asyncio
async def test_v2_dispatches_once_and_validates_grounded_material() -> None:
    calls = []

    async def _dispatch(tool_fqn, arguments):
        calls.append((tool_fqn, arguments))
        return {
            "schema_version": "aol.voice_interaction_result.v1",
            "outcome": "grounded_material",
            "decision_code": "grounded_material",
            "confidence": 0.91,
            "candidates": [
                {
                    "object_ref": {
                        "uri": f"mindscape://{PACK_CODE}/segment/seg-1",
                        "owner_pack": PACK_CODE,
                        "object_kind": "segment",
                        "object_id": "seg-1",
                    },
                    "display_label": "Short practice",
                    "score": 0.91,
                    "metadata": {"safe_pack_detail": "not_forwarded"},
                }
            ],
            "evidence": [],
            "answer_text": None,
            "clarification_reason": None,
            "client_action": None,
        }

    port = ActivePackVoiceInteractionPort(
        registry=_Registry(_v2_manifest()),
        tool_dispatch=_dispatch,
    )
    result = await port.resolve(
        transcript="Recommend a short practice.",
        workspace_id="ws_voice",
        language="en",
        session=_session(),
        resolved_references=[],
    )

    assert result.outcome == "grounded_material"
    assert result.candidates[0].object_ref.workspace_id == "ws_voice"
    assert len(calls) == 1
    assert calls[0][0] == f"{PACK_CODE}.voice_interaction"
    assert calls[0][1]["tenant_id"] == "ws_voice"


@pytest.mark.asyncio
async def test_v2_preserves_explicit_answer_language_only_when_pack_supplies_it() -> None:
    async def _dispatch(tool_fqn, arguments):
        return {
            "schema_version": "aol.voice_interaction_result.v1",
            "outcome": "grounded_answer",
            "decision_code": "grounded_answer",
            "confidence": 0.88,
            "candidates": [],
            "evidence": [
                {
                    "source_ref": f"mindscape://{PACK_CODE}/knowledge/k-1",
                    "title": "Grounded source",
                    "excerpt": "Keep the knee aligned with the toes.",
                    "score": 0.88,
                    "asana_id": None,
                }
            ],
            "answer_text": "膝蓋應與腳趾方向一致。",
            "answer_language": "zh-TW",
            "clarification_reason": None,
            "client_action": None,
        }

    result = await ActivePackVoiceInteractionPort(
        registry=_Registry(_v2_manifest()),
        tool_dispatch=_dispatch,
    ).resolve(
        transcript="What should I watch for?",
        workspace_id="ws_voice",
        language="en",
        session=_session(),
        resolved_references=[],
    )

    assert result.answer_language == "zh-TW"
    assert result.answer_language != "en"


@pytest.mark.asyncio
async def test_v2_rejects_non_locale_answer_language() -> None:
    async def _dispatch(tool_fqn, arguments):
        return {
            "schema_version": "aol.voice_interaction_result.v1",
            "outcome": "grounded_answer",
            "decision_code": "grounded_answer",
            "confidence": 0.88,
            "candidates": [],
            "evidence": [
                {
                    "source_ref": f"mindscape://{PACK_CODE}/knowledge/k-1",
                    "title": "Grounded source",
                    "excerpt": "Keep the knee aligned with the toes.",
                    "score": 0.88,
                    "asana_id": None,
                }
            ],
            "answer_text": "Grounded answer",
            "answer_language": "not a locale",
            "clarification_reason": None,
            "client_action": None,
        }

    result = await ActivePackVoiceInteractionPort(
        registry=_Registry(_v2_manifest()),
        tool_dispatch=_dispatch,
    ).resolve(
        transcript="What should I watch for?",
        workspace_id="ws_voice",
        language="en",
        session=_session(),
        resolved_references=[],
    )

    assert result.outcome == "clarification"
    assert result.decision_code == "active_pack_voice_unavailable"


@pytest.mark.asyncio
async def test_v2_timeout_and_invalid_pack_identity_fail_to_clarification() -> None:
    async def _timeout(tool_fqn, arguments):
        await asyncio.sleep(0.02)
        return {}

    timeout = await ActivePackVoiceInteractionPort(
        registry=_Registry(_v2_manifest()),
        tool_dispatch=_timeout,
        timeout_seconds=0.001,
    ).resolve(
        transcript="Question",
        workspace_id="ws_voice",
        language="en",
        session=_session(),
        resolved_references=[],
    )

    async def _invalid_identity(tool_fqn, arguments):
        return {
            "schema_version": "aol.voice_interaction_result.v1",
            "outcome": "grounded_material",
            "decision_code": "grounded_material",
            "confidence": 0.9,
            "candidates": [
                {
                    "object_ref": {
                        "uri": "mindscape://other/segment/seg-1",
                        "owner_pack": "other",
                        "object_kind": "segment",
                        "object_id": "seg-1",
                    },
                    "display_label": "Wrong pack",
                    "score": 0.9,
                    "metadata": {},
                }
            ],
            "evidence": [],
            "answer_text": None,
            "clarification_reason": None,
            "client_action": None,
        }

    invalid = await ActivePackVoiceInteractionPort(
        registry=_Registry(_v2_manifest()),
        tool_dispatch=_invalid_identity,
    ).resolve(
        transcript="Question",
        workspace_id="ws_voice",
        language="en",
        session=_session(),
        resolved_references=[],
    )

    assert timeout.outcome == "clarification"
    assert timeout.decision_code == "active_pack_voice_timeout"
    assert invalid.outcome == "clarification"
    assert invalid.decision_code == "active_pack_voice_unavailable"


def test_v1_compatibility_has_one_matcher_and_v2_never_double_matches() -> None:
    v1_manifest = {
        "aol_client_interactions": {
            "schema_version": "aol.client_interactions.v1",
            "voice_intents": [
                {
                    "code": "prepare",
                    "match": {"mode": "contains", "phrases": ["start practice"]},
                    "action": {
                        "code": f"{PACK_CODE}.prepare",
                        "requires_confirmation": True,
                        "payload": {"duration": 30},
                    },
                }
            ],
        }
    }
    v1 = resolve_legacy_voice_client_action(
        transcript="Please start practice.",
        session=_session(),
        registry=_Registry(v1_manifest),
    )
    v2 = resolve_legacy_voice_client_action(
        transcript="Please start practice.",
        session=_session(),
        registry=_Registry(_v2_manifest()),
    )

    assert v1 is not None
    assert v1.action_code == f"{PACK_CODE}.prepare"
    assert v2 is None
