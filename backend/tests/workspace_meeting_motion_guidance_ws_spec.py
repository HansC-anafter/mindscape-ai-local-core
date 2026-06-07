from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.models.meeting_motion_guidance import (
    MeetingMotionGuidanceClientMessage,
)
from backend.app.services.orchestration.meeting.motion_guidance_service import (
    MeetingMotionGuidanceService,
    MotionGuidanceError,
    MotionGuidanceSession,
)


def _load_meeting_motion_guidance_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routes"
        / "core"
        / "workspace"
        / "meeting_motion_guidance.py"
    )
    spec = importlib.util.spec_from_file_location(
        "meeting_motion_guidance_route_under_test",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_app(module, *, service):
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1/workspaces")
    app.dependency_overrides[module.get_workspace] = lambda: SimpleNamespace(
        id="ws_motion",
        default_locale="zh-TW",
    )
    app.dependency_overrides[module.get_motion_guidance_service] = lambda: service
    return app


def _session() -> MotionGuidanceSession:
    return MotionGuidanceSession(
        workspace_id="ws_motion",
        meeting_id="mtg_motion",
        practice_session_id="practice_1",
    )


def _message(**kwargs) -> MeetingMotionGuidanceClientMessage:
    return MeetingMotionGuidanceClientMessage.model_validate(kwargs)


def _receive(ws):
    return json.loads(ws.receive_text())


def test_motion_guidance_service_throttles_speakable_duplicate_cues() -> None:
    service = MeetingMotionGuidanceService()
    session = _session()

    ready = service.handle_message(
        session=session,
        message=_message(type="session_start"),
        now_epoch=1.0,
    )
    assert ready is not None
    assert ready.type == "session_ready"

    first = service.handle_message(
        session=session,
        message=_message(
            type="motion_window",
            motion_window_ref="window_1",
            confidence=0.9,
            top_findings=["Shift weight back over the standing foot."],
        ),
        now_epoch=10.0,
    )
    assert first is not None
    assert first.type == "guidance_cue"
    assert first.speakable is True
    assert first.cue_priority == "correction"

    throttled = service.handle_message(
        session=session,
        message=_message(
            type="motion_window",
            motion_window_ref="window_2",
            confidence=0.9,
            top_findings=["Open the left shoulder before the turn."],
        ),
        now_epoch=11.0,
    )
    assert throttled is not None
    assert throttled.type == "guidance_suppressed"
    assert throttled.reason == "cue_throttled"

    duplicate = service.handle_message(
        session=session,
        message=_message(
            type="motion_window",
            motion_window_ref="window_3",
            confidence=0.9,
            top_findings=["Shift weight back over the standing foot."],
        ),
        now_epoch=20.0,
    )
    assert duplicate is not None
    assert duplicate.type == "guidance_suppressed"
    assert duplicate.reason == "duplicate_cue"


def test_motion_guidance_service_low_confidence_is_not_speakable() -> None:
    service = MeetingMotionGuidanceService()
    event = service.handle_message(
        session=_session(),
        message=_message(
            type="motion_window",
            motion_window_ref="window_low",
            confidence=0.2,
            top_findings=["Do not speak this correction."],
        ),
        now_epoch=10.0,
    )

    assert event is not None
    assert event.type == "guidance_cue"
    assert event.cue_priority == "warning"
    assert event.speakable is False
    assert "camera view" in str(event.cue_text)


def test_motion_guidance_service_rejects_raw_payload_keys() -> None:
    service = MeetingMotionGuidanceService()
    try:
        service.handle_message(
            session=_session(),
            message=_message(
                type="motion_window",
                motion_window_ref="window_raw",
                metadata={"keypoints": [[1, 2, 3]]},
            ),
            now_epoch=10.0,
        )
    except MotionGuidanceError as exc:
        assert exc.reason == "raw_motion_payload_rejected"
        assert exc.recoverable is False
    else:
        raise AssertionError("raw payload was not rejected")


def test_motion_guidance_ws_streams_bounded_cue_events() -> None:
    module = _load_meeting_motion_guidance_module()
    service = MeetingMotionGuidanceService()
    client = TestClient(_build_app(module, service=service))

    with client.websocket_connect(
        "/api/v1/workspaces/ws_motion/meetings/mtg_motion/"
        "motion-guidance/practice_1/stream"
    ) as ws:
        ws.send_json({"type": "session_start"})
        assert _receive(ws)["type"] == "session_ready"

        ws.send_json(
            {
                "type": "motion_window",
                "event_id": "event_1",
                "motion_window_ref": "window_1",
                "confidence": 0.95,
                "top_findings": ["Shift weight back over the standing foot."],
            }
        )
        cue = _receive(ws)
        assert cue["type"] == "guidance_cue"
        assert cue["event_id"] == "event_1"
        assert cue["speakable"] is True
        assert cue["motion_window_ref"] == "window_1"

        ws.send_json({"type": "session_close"})
        assert _receive(ws)["type"] == "session_closed"
