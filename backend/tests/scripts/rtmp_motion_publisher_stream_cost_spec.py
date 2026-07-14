from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import sys
import types


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rtmp_motion_publisher import api_client, closeout, stream_cost  # noqa: E402


class Frame:
    shape = (720, 1280, 3)


def _args() -> Namespace:
    return Namespace(
        rtmp_url="rtmp://example.invalid/external-camera",
        api_base="http://localhost:8200",
        workspace_id="workspace-1",
        meeting_id="meeting-1",
        source_session_id="device-session-1",
        source_kind="external_stream",
        transport_kind="local_rtmp",
        append_owner_id="",
        live_session_id=None,
        duration_sec=360.0,
        expected_duration_ms=0.0,
        sample_fps=5.0,
        capture_backend="opencv",
        stream_cost_provider="gcp",
        stream_cost_region="asia-east1",
        stream_cost_direction="remote_pull",
        stream_cost_transport="",
        stream_cost_codec="h264",
        stream_cost_billing_tier=None,
        stream_cost_source_width=0,
        stream_cost_source_height=0,
        stream_cost_source_fps=30.0,
        stream_cost_source_bitrate_mbps=4.5,
        disable_stream_cost=False,
        api_timeout_sec=1.0,
        api_retry_count=1,
        api_retry_backoff_sec=0.0,
    )


def _quoted_metadata() -> dict:
    return {
        "schema_version": "stream_cost_metadata.v1",
        "state": "quoted",
        "provider": "gcp",
        "service": "live_stream_api",
        "region": "asia-east1",
        "direction": "remote_pull",
        "transport": "rtmp",
        "rate_snapshot": {
            "quote_id": "scq_test",
            "quality_tier": "hd",
            "line_items": [{"unit_price": 0.59}],
        },
    }


def test_tracker_quotes_first_frame_and_finishes_with_same_snapshot(monkeypatch) -> None:
    args = _args()
    calls: list[dict] = []
    events: list[dict] = []

    def fake_tool(**kwargs):
        calls.append(kwargs)
        if kwargs["action"] == "start":
            return {"stream_cost": _quoted_metadata()}
        finished = {
            **kwargs["stream_cost"],
            "state": "estimated",
            "quality_end": kwargs["quality_end"],
            "estimate": {
                "currency": "USD",
                "amount": 0.173333,
                "observed_duration_sec": kwargs["duration_sec"],
                "billing_tier": "hd",
                "is_estimate": True,
            },
        }
        return {"stream_cost": finished}

    ticks = iter([100.0, 460.0])
    monkeypatch.setattr(stream_cost, "_load_stream_cost_tool", lambda: fake_tool)
    monkeypatch.setattr(stream_cost, "emit", events.append)
    monkeypatch.setattr(stream_cost.time, "monotonic", lambda: next(ticks))

    tracker = stream_cost.start_stream_cost_tracking(args, Frame())
    assert tracker is not None
    assert calls[0]["action"] == "start"
    assert calls[0]["transport"] == "rtmp"
    assert calls[0]["quality_start"]["width_px"] == 1280
    assert calls[0]["quality_start"]["height_px"] == 720
    assert calls[0]["quality_start"]["basis"] == "decoded_frame"
    assert args.stream_cost_metadata["rate_snapshot"]["quote_id"] == "scq_test"

    finished = tracker.finish(Frame())
    assert calls[1]["action"] == "finish"
    assert calls[1]["stream_cost"]["rate_snapshot"]["quote_id"] == "scq_test"
    assert calls[1]["duration_sec"] == 360.0
    assert finished["estimate"]["amount"] == 0.173333
    assert args.stream_cost_metadata["state"] == "estimated"
    assert [event["event"] for event in events] == [
        "stream_cost_quoted",
        "stream_cost_estimated",
    ]


def test_tracker_prefers_configured_transport_quality(monkeypatch) -> None:
    args = _args()
    args.stream_cost_source_width = 3840
    args.stream_cost_source_height = 2160
    args.stream_cost_billing_tier = "uhd"
    calls: list[dict] = []

    def fake_tool(**kwargs):
        calls.append(kwargs)
        return {"stream_cost": _quoted_metadata()}

    monkeypatch.setattr(stream_cost, "_load_stream_cost_tool", lambda: fake_tool)
    monkeypatch.setattr(stream_cost, "emit", lambda _event: None)

    tracker = stream_cost.start_stream_cost_tracking(args, Frame())

    assert tracker is not None
    assert calls[0]["quality_start"]["width_px"] == 3840
    assert calls[0]["quality_start"]["height_px"] == 2160
    assert calls[0]["quality_start"]["tier"] == "uhd"
    assert calls[0]["quality_start"]["basis"] == "configured_transport_quality"


def test_tracker_degrades_without_blocking_stream_when_pack_is_unavailable(monkeypatch) -> None:
    args = _args()
    events: list[dict] = []

    def unavailable():
        raise ImportError("camera capture control not installed")

    monkeypatch.setattr(stream_cost, "_load_stream_cost_tool", unavailable)
    monkeypatch.setattr(stream_cost, "emit", events.append)

    assert stream_cost.start_stream_cost_tracking(args, Frame()) is None
    assert events[0]["event"] == "stream_cost_unavailable"
    assert events[0]["phase"] == "start"


def test_motion_runtime_requests_carry_stream_cost_metadata(monkeypatch) -> None:
    args = _args()
    args.stream_cost_metadata = _quoted_metadata()
    payloads: list[dict] = []

    def fake_post(_api_base, path, payload, **_kwargs):
        payloads.append({"path": path, "payload": payload})
        return {"live_session": {"live_session_id": "lms_test"}}

    monkeypatch.setattr(api_client, "api_post", fake_post)
    monkeypatch.setattr(api_client, "emit", lambda _event: None)

    assert api_client.register_live_session(args) == "lms_test"
    assert payloads[0]["payload"]["metadata"]["stream_cost"]["provider"] == "gcp"


def test_yogacoach_closeout_projects_rollup_stream_cost(monkeypatch) -> None:
    args = _args()
    args.emit_yogacoach_summary = True
    args.practice_session_id = "practice-1"
    args.yogacoach_reference_url = ""
    args.user_id = "user-1"
    args.user_goal = ""
    args.materialize_practice_diary = False
    args.yogacoach_summary_output_dir = ""
    captured: dict = {}

    class LiveRollup:
        practice_session_id = "practice-1"
        window_count = 1
        summary_confidence = "partial"

        def model_dump(self, **_kwargs):
            return {"practice_session_id": self.practice_session_id}

    def build_rollup(_motion_rollup, **kwargs):
        captured["metadata"] = kwargs["metadata"]
        return LiveRollup()

    monkeypatch.setitem(
        sys.modules,
        "capabilities.yogacoach.services.motion_runtime_rollup_adapter",
        types.SimpleNamespace(
            build_live_practice_rollup_from_motion_session_rollup=build_rollup,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "capabilities.yogacoach.tools.yogacoach_build_student_practice_summary",
        types.SimpleNamespace(
            build_student_practice_summary=lambda *_args, **_kwargs: {
                "practice_review_projection": {"course_match_score": {}}
            },
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "capabilities.yogacoach.tools.yogacoach_build_practice_feedback_report",
        types.SimpleNamespace(
            build_practice_feedback_report=lambda **_kwargs: {
                "e2e_acceptance": {"status": "passed"},
                "html": "",
            },
        ),
    )
    monkeypatch.setattr(closeout, "emit", lambda _event: None)

    result = closeout.emit_yogacoach_closeout(
        args,
        live_session_id="lms_test",
        rollup_response={
            "summary": {
                "window_count": 1,
                "metadata": {"stream_cost": _quoted_metadata()},
            }
        },
    )

    assert result is not None
    assert captured["metadata"]["stream_cost"]["provider"] == "gcp"
    assert captured["metadata"]["stream_cost"]["rate_snapshot"]["quote_id"] == "scq_test"
