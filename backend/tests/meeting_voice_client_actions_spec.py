from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.models.meeting_command import (
    MeetingCommandRecord,
    MeetingRequestedAction,
    MeetingCommandStatus,
)
from backend.app.models.meeting_voice_context import MeetingVoiceCommandContext
from backend.app.services.meeting_command_dispatch_client_actions import (
    dispatch_client_action_for_command,
)
from backend.app.services.meeting_command_dispatch_routing import (
    should_route_client_action,
    should_route_meeting_orchestration,
)
from backend.app.services.orchestration.meeting.voice_client_actions import (
    build_voice_command_envelope,
    resolve_voice_client_action,
)


class _Registry:
    def get_capability(self, capability_code):
        if capability_code != "yogacoach":
            return None
        return {
            "manifest": {
                "aol_client_interactions": {
                    "voice_intents": [
                        {
                            "code": "prepare_default_practice",
                            "match": {
                                "mode": "contains",
                                "phrases": ["播放瑜伽練習", "play yoga practice"],
                            },
                            "action": {
                                "code": "yogacoach.prepare_reference_practice",
                                "requires_confirmation": True,
                                "payload": {
                                    "reference": {
                                        "provider": "bilibili",
                                        "source_url": "https://www.bilibili.com/video/BV13g4y1u7di/",
                                    },
                                    "playback_duration_ms": 1_800_000,
                                },
                            },
                        },
                        {
                            "code": "confirm_practice",
                            "match": {
                                "mode": "exact",
                                "phrases": ["開始", "確認開始"],
                            },
                            "action": {
                                "code": "yogacoach.confirm_reference_practice",
                                "requires_confirmation": False,
                                "payload": {"countdown_seconds": 5},
                            },
                        },
                    ]
                }
            }
        }


def _session(pack_code: str = "yogacoach"):
    return SimpleNamespace(metadata={"active_capability_code": pack_code})


def test_pack_manifest_resolves_prepare_and_confirmation_voice_actions() -> None:
    prepare = resolve_voice_client_action(
        transcript="請幫我播放瑜伽練習參考影片",
        session=_session(),
        registry=_Registry(),
    )
    confirm = resolve_voice_client_action(
        transcript="確認 開始！",
        session=_session(),
        registry=_Registry(),
    )

    assert prepare is not None
    assert prepare.action_code == "yogacoach.prepare_reference_practice"
    assert prepare.requires_confirmation is True
    assert prepare.payload["playback_duration_ms"] == 1_800_000
    assert confirm is not None
    assert confirm.action_code == "yogacoach.confirm_reference_practice"
    assert confirm.payload["countdown_seconds"] == 5


def test_installed_yogacoach_v2_manifest_does_not_double_match_legacy_actions() -> None:
    prepare = resolve_voice_client_action(
        transcript="播放瑜伽練習",
        session=_session(),
    )
    confirm = resolve_voice_client_action(
        transcript="確認開始",
        session=_session(),
    )

    assert prepare is None
    assert confirm is None


def test_voice_action_does_not_cross_pack_boundary() -> None:
    assert resolve_voice_client_action(
        transcript="播放瑜伽練習",
        session=_session("ig"),
        registry=_Registry(),
    ) is None


@pytest.mark.asyncio
async def test_client_action_uses_direct_ledger_dispatch_without_meeting_worker() -> None:
    resolution = resolve_voice_client_action(
        transcript="播放瑜伽練習",
        session=_session(),
        registry=_Registry(),
    )
    assert resolution is not None
    envelope = build_voice_command_envelope(
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        origin_surface="meeting_voice",
        transcript="播放瑜伽練習",
        metadata={"client_turn_id": "turn_1"},
        context_objects=[],
        resolution=resolution,
    )

    assert should_route_client_action(envelope) is True
    assert should_route_meeting_orchestration(envelope) is False
    command = MeetingCommandRecord(
        command_id="cmd_voice",
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        origin_surface="meeting_voice",
        actor="user",
        intent_text=envelope.intent_text,
        requested_action=envelope.requested_action,
        status=MeetingCommandStatus.ACCEPTED,
        metadata=envelope.metadata,
    )
    completed, dispatch_result = await dispatch_client_action_for_command(
        command=command,
        canonical=envelope,
    )

    assert completed.status == MeetingCommandStatus.COMPLETED
    assert completed.metadata["dispatch_mode"] == "route_client_action"
    assert dispatch_result["client_action"]["pack_code"] == "yogacoach"
    assert dispatch_result["client_action"]["payload"]["reference"]["provider"] == "bilibili"


def test_explicit_frozen_requested_action_is_not_replaced_by_pack_voice_intent() -> None:
    resolution = resolve_voice_client_action(
        transcript="播放瑜伽練習",
        session=_session(),
        registry=_Registry(),
    )
    assert resolution is not None
    envelope = build_voice_command_envelope(
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        origin_surface="meeting_voice",
        transcript="播放瑜伽練習",
        metadata={"client_turn_id": "turn_explicit"},
        context_objects=[],
        resolution=resolution,
        command_context=MeetingVoiceCommandContext(
            requested_action=MeetingRequestedAction(
                verb="execute_playbook",
                pack_code="ig",
                playbook_code="selected_playbook",
                parameters={"instruction": "Voice command"},
            ),
            thread_id="mtg_voice",
        ),
    )

    assert envelope.requested_action is not None
    assert envelope.requested_action.pack_code == "ig"
    assert envelope.requested_action.playbook_code == "selected_playbook"
    assert envelope.requested_action.parameters["instruction"] == "播放瑜伽練習"
    assert should_route_client_action(envelope) is False
