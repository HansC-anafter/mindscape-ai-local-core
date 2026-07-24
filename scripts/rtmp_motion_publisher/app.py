from __future__ import annotations

import signal
import time
from typing import Any

import cv2

from .analysis_metrics import AnalysisStageMetrics
from .api_client import emit_rollup, register_live_session
from .capture import open_stream_capture
from .capture_metrics import CaptureMetricsLedger
from .cli import parse_args
from .closeout import emit_yogacoach_closeout
from .events import configure_event_log, emit
from .evidence import LearnerVisualEvidenceRecorder
from .guidance import BackgroundMotionWindowSender, GuidanceSocket
from .localized_reference_evidence import LocalizedReferenceVisualEvidenceRecorder
from .pose import PoseDetector, pose_sample_from_result
from .reference_profile import load_motion_reference_profile
from .reference_alignment import LiveReferenceAlignmentMatcher
from .reconnect import reconnect_stream
from .receiver_health import (
    public_reference_alignment_status as _public_reference_alignment_status,
    publisher_status_event,
    receiver_metrics as _receiver_metrics,
)
from .receiver_state import transition_receiver_state
from .source_acquisition import acquire_initial_stream as _acquire_initial_stream
from .source_uri import public_input_uri
from .session_policy import ReceiverSessionPolicy
from .stream_cost import start_stream_cost_tracking
from .terminal_window import finalize_terminal_motion_window
from .windows import MotionWindowAccumulator, PendingMotionWindow, PoseSample


def _try_emit_rollup(
    args: Any,
    live_session_id: str,
    *,
    motion_reference_profile: dict[str, Any] | None,
    failure_event: str,
) -> dict[str, Any] | None:
    try:
        return emit_rollup(
            args,
            live_session_id,
            motion_reference_profile=motion_reference_profile,
        )
    except Exception as exc:
        emit(
            {
                "event": failure_event,
                "live_session_id": live_session_id,
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
            }
        )
        return None


def run_receiver(args: Any) -> int:
    configure_event_log(args.event_log_path)
    motion_reference_profile = (
        load_motion_reference_profile(args.motion_reference_profile_path)
        if args.motion_reference_profile_path
        else None
    )
    if motion_reference_profile is not None:
        emit(
            {
                "event": "motion_reference_profile_loaded",
                "reference_profile_id": motion_reference_profile["reference_profile_id"],
                "chapter_count": len(motion_reference_profile["chapters"]),
                "comparison_provenance": motion_reference_profile["metadata"][
                    "comparison_provenance"
                ],
            }
        )
    reference_matcher = (
        LiveReferenceAlignmentMatcher(
            motion_reference_profile,
            artifact_id=str(
                getattr(args, "motion_reference_profile_artifact_id", "") or ""
            ),
        )
        if motion_reference_profile is not None
        else None
    )
    stop_requested = False

    def handle_stop(_signum: int, _frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    initial_stream = _acquire_initial_stream(
        args,
        should_stop=lambda: stop_requested,
        open_capture=open_stream_capture,
        emit_event=emit,
        transition_state=transition_receiver_state,
        monotonic=time.monotonic,
        sleep=time.sleep,
    )
    if initial_stream is None:
        return 0 if stop_requested else 2
    capture, first_frame, source_wait_attempts = initial_stream
    input_uri = public_input_uri(args.rtmp_url)
    stream_cost_tracker = start_stream_cost_tracking(args, first_frame)
    emit(
        {
            "event": "stream_opened",
            "input_uri": input_uri,
            "capture_backend": args.capture_backend,
            "frame_width": args.frame_width if args.capture_backend == "ffmpeg" else None,
            "frame_height": args.frame_height if args.capture_backend == "ffmpeg" else None,
            "read_timeout_sec": args.stream_read_timeout_sec,
            "source_wait_attempts": source_wait_attempts,
        }
    )
    transition_receiver_state(args, "receiving")

    try:
        live_session_id = register_live_session(args)
    except Exception:
        if stream_cost_tracker is not None:
            stream_cost_tracker.finish(first_frame)
        capture.release()
        raise
    practice_session_id = args.practice_session_id or f"{args.source_session_id}:live_guidance"
    analysis_metrics = AnalysisStageMetrics(clock=time.perf_counter)
    evidence_recorder = LearnerVisualEvidenceRecorder(args, live_session_id)
    guidance: GuidanceSocket | None = None
    if not args.disable_guidance_ws:
        try:
            guidance = GuidanceSocket(
                api_base=args.api_base,
                workspace_id=args.workspace_id,
                meeting_id=args.meeting_id,
                practice_session_id=practice_session_id,
                live_session_id=live_session_id,
            )
            emit({"event": "guidance_socket_opened", "url": guidance.url})
            for event in guidance.read_events():
                emit({"event": "guidance_event", "payload": event})
        except Exception as exc:
            emit({"event": "guidance_socket_failed", "error": str(exc)})
            guidance = None
    sender: BackgroundMotionWindowSender | None = None
    pose: PoseDetector | None = None
    try:
        sender = BackgroundMotionWindowSender(
            args=args,
            live_session_id=live_session_id,
            practice_session_id=practice_session_id,
            guidance=guidance,
            reference_matcher=reference_matcher,
            reference_alignment_observer=evidence_recorder.record_reference_alignment,
            analysis_metrics=analysis_metrics,
        )
        pose = PoseDetector.create(args.model_asset_path)
        transition_receiver_state(args, "analyzing")
    except Exception:
        if stream_cost_tracker is not None:
            stream_cost_tracker.finish(first_frame)
        capture.release()
        if sender is not None:
            sender.close()
        raise

    accumulator = MotionWindowAccumulator(
        live_session_id=live_session_id,
        source_session_id=args.source_session_id,
        window_ms=args.window_sec * 1000.0,
        max_samples=max(1, args.max_samples),
    )
    start = time.monotonic()
    session_policy = ReceiverSessionPolicy.from_args(
        args,
        started_at=start,
        now_epoch=time.time(),
    )
    capture_metrics = CaptureMetricsLedger()
    next_sample_at = start
    next_status_at = start + args.status_every_sec
    next_rollup_at = start + args.rollup_every_sec
    attempted_windows = 0
    last_window_summary: dict[str, Any] | None = None
    last_rollup: dict[str, Any] | None = None
    consecutive_read_failures = 0
    reconnect_attempts = 0
    last_pose_sample: PoseSample | None = None
    last_real_frame_at: float | None = None
    pending_first_frame: Any | None = first_frame
    last_frame: Any = first_frame
    publisher_exit_code = 0

    def current_receiver_metrics(
        reconnect_attempts_override: int | None = None,
    ) -> dict[str, Any]:
        return _receiver_metrics(
            attempted_windows=attempted_windows,
            sender_stats=sender.stats(),
            capture_stats=capture_metrics.snapshot(capture),
            source_wait_attempts=source_wait_attempts,
            reconnect_attempts=(
                reconnect_attempts
                if reconnect_attempts_override is None
                else reconnect_attempts_override
            ),
            last_window_summary=last_window_summary,
        )

    def enqueue_window_summary(
        summary: dict[str, Any],
        frame: Any | None = None,
    ) -> None:
        nonlocal attempted_windows, last_window_summary
        attempted_windows += 1
        last_window_summary = summary
        stage_started = analysis_metrics.started()
        evidence_recorder.capture_window(frame, summary)
        analysis_metrics.record("learner_snapshot", stage_started)
        if sender is None:
            return
        stage_started = analysis_metrics.started()
        sender.enqueue(
            PendingMotionWindow(
                summary=summary,
                received_at_ms=time.monotonic() * 1000.0,
            )
        )
        analysis_metrics.record("window_enqueue", stage_started)

    def enqueue_sample_window(sample: PoseSample, frame: Any | None = None) -> None:
        stage_started = analysis_metrics.started()
        summary = accumulator.push(sample)
        if summary is not None:
            enqueue_window_summary(summary, frame)

    def holdover_active(now_monotonic: float) -> bool:
        return (
            args.stream_gap_holdover_sec > 0
            and last_pose_sample is not None
            and last_real_frame_at is not None
            and now_monotonic - last_real_frame_at <= args.stream_gap_holdover_sec
        )

    def maybe_emit_holdover_sample(now_monotonic: float) -> None:
        if not holdover_active(now_monotonic) or last_pose_sample is None:
            return
        holdover_confidence = min(
            last_pose_sample.confidence,
            max(0.0, args.stream_gap_holdover_confidence_cap),
        )
        enqueue_sample_window(
            PoseSample(
                timestamp_ms=(now_monotonic - start) * 1000.0,
                confidence=round(holdover_confidence, 3),
                visible_point_count=last_pose_sample.visible_point_count,
                total_point_count=last_pose_sample.total_point_count,
                findings=["transport_frame_holdover"],
            )
        )

    try:
        while not stop_requested:
            now = time.monotonic()
            if session_policy.is_complete(now):
                break
            if pending_first_frame is not None:
                ok, frame = True, pending_first_frame
                pending_first_frame = None
            else:
                stage_started = analysis_metrics.started()
                ok, frame = capture.read()
                analysis_metrics.record("capture_read", stage_started)
            now = time.monotonic()
            if not ok:
                failure_now = now
                if session_policy.is_complete(failure_now):
                    break
                capture_alive = bool(capture.isOpened())
                if capture_alive:
                    consecutive_read_failures = 0
                    emit(
                        {
                            "event": "stream_frame_idle",
                            "elapsed_sec": round(failure_now - start, 3),
                        }
                    )
                    if failure_now >= next_sample_at:
                        maybe_emit_holdover_sample(failure_now)
                        next_sample_at = failure_now + 1.0 / max(0.1, args.sample_fps)
                    transition_receiver_state(
                        args,
                        "degraded",
                        reason="frame_pipe_idle",
                        metrics=current_receiver_metrics(),
                    )
                    continue
                consecutive_read_failures += 1
                emit(
                    {
                        "event": "stream_read_failed",
                        "elapsed_sec": round(failure_now - start, 3),
                        "consecutive_read_failures": consecutive_read_failures,
                    }
                )
                if failure_now >= next_sample_at:
                    maybe_emit_holdover_sample(failure_now)
                    next_sample_at = failure_now + 1.0 / max(0.1, args.sample_fps)
                if consecutive_read_failures >= max(1, args.stream_read_failure_threshold):
                    if not holdover_active(failure_now):
                        accumulator.reset()
                    reconnect_result = reconnect_stream(
                        args=args,
                        capture=capture,
                        reason="read_failed",
                        started_at=start,
                        total_attempts=reconnect_attempts,
                        policy=session_policy,
                        capture_metrics=capture_metrics,
                        receiver_metrics=current_receiver_metrics,
                        should_stop=lambda: stop_requested,
                        open_capture=open_stream_capture,
                        emit_event=emit,
                        transition_state=transition_receiver_state,
                        monotonic=time.monotonic,
                        sleep=time.sleep,
                    )
                    reconnect_attempts = reconnect_result.total_attempts
                    if reconnect_result.outcome == "reconnected":
                        capture = reconnect_result.capture
                        pending_first_frame = reconnect_result.first_frame
                        consecutive_read_failures = 0
                        next_sample_at = time.monotonic()
                        continue
                    if reconnect_result.outcome == "failed":
                        publisher_exit_code = 3
                    break
                time.sleep(0.25)
                continue
            consecutive_read_failures = 0
            sample_timestamp_ms = session_policy.active_elapsed_ms(
                started_at=start,
                now_monotonic=now,
            )
            if sample_timestamp_ms is None:
                break
            last_frame = frame
            if now < next_sample_at:
                continue
            analysis_metrics.record_sample_schedule_lag(
                sampled_at=now,
                scheduled_at=next_sample_at,
            )
            next_sample_at = now + 1.0 / max(0.1, args.sample_fps)
            stage_started = analysis_metrics.started()
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            timestamp_ms = sample_timestamp_ms
            result = pose.process(rgb, timestamp_ms)
            sample = pose_sample_from_result(result, timestamp_ms)
            analysis_metrics.record("pose", stage_started)
            last_pose_sample = sample
            last_real_frame_at = now
            enqueue_sample_window(sample, frame)
            if now >= next_status_at:
                sender_stats = sender.stats()
                capture_stats = capture_metrics.snapshot(capture)
                emit(
                    publisher_status_event(
                        elapsed_sec=now - start,
                        attempted_windows=attempted_windows,
                        sender_stats=sender_stats,
                        capture_stats=capture_stats,
                        analysis_stats=analysis_metrics.snapshot(),
                        last_window_summary=last_window_summary,
                    )
                )
                transition_receiver_state(
                    args,
                    "analyzing",
                    metrics=_receiver_metrics(
                        attempted_windows=attempted_windows,
                        sender_stats=sender_stats,
                        capture_stats=capture_stats,
                        source_wait_attempts=source_wait_attempts,
                        reconnect_attempts=reconnect_attempts,
                        last_window_summary=last_window_summary,
                    ),
                )
                next_status_at = now + args.status_every_sec
            if args.rollup_every_sec > 0 and now >= next_rollup_at:
                rollup_probe = _try_emit_rollup(
                    args,
                    live_session_id,
                    motion_reference_profile=motion_reference_profile,
                    failure_event="periodic_rollup_failed",
                )
                if rollup_probe is not None:
                    last_rollup = rollup_probe
                next_rollup_at = now + args.rollup_every_sec
    finally:
        capture_stats = capture_metrics.snapshot(capture)
        terminal_end_ms = session_policy.terminal_elapsed_ms(
            started_at=start,
            now_monotonic=time.monotonic(),
        )
        terminal_window = finalize_terminal_motion_window(
            accumulator,
            terminal_end_ms,
        )
        if terminal_window.summary is not None:
            enqueue_window_summary(terminal_window.summary, last_frame)
        if terminal_window.event is not None:
            emit(terminal_window.event)
        if stream_cost_tracker is not None:
            stream_cost_tracker.finish(last_frame)
        capture.release()
        if pose is not None:
            pose.close()
        if sender is not None:
            sender.close()
            args.receiver_final_metrics = _receiver_metrics(
                attempted_windows=attempted_windows,
                sender_stats=sender.stats(),
                capture_stats=capture_stats,
                source_wait_attempts=source_wait_attempts,
                reconnect_attempts=reconnect_attempts,
                last_window_summary=last_window_summary,
            )

    final_rollup = _try_emit_rollup(
        args,
        live_session_id,
        motion_reference_profile=motion_reference_profile,
        failure_event="final_rollup_failed",
    )
    if final_rollup is None:
        evidence_recorder.cleanup_transient_frames()
        sender_stats = sender.stats()
        emit(
            {
                "event": "publisher_finished",
                "live_session_id": live_session_id,
            "attempted_windows": attempted_windows,
            **sender_stats,
            "analysis": analysis_metrics.snapshot(),
            "final_rollup_ref": None,
                "yogacoach_closeout": None,
                "failure_reason": "final_rollup_failed",
            }
        )
        return publisher_exit_code or 4
    last_rollup = final_rollup
    learner_visual_evidence = evidence_recorder.finalize(last_rollup)
    reference_visual_evidence = LocalizedReferenceVisualEvidenceRecorder(
        args,
        live_session_id,
        evidence_recorder,
    ).finalize(last_rollup, motion_reference_profile)
    closeout_result = emit_yogacoach_closeout(
        args,
        live_session_id=live_session_id,
        rollup_response=last_rollup,
        learner_visual_evidence=learner_visual_evidence,
        reference_visual_evidence=reference_visual_evidence,
    )
    practice_diary = (
        closeout_result.get("practice_diary")
        if isinstance(closeout_result, dict)
        else None
    )
    diary_materialized = isinstance(practice_diary, dict) and bool(
        practice_diary.get("diary_id")
    )
    if not bool(getattr(args, "materialize_practice_diary", False)) or diary_materialized:
        evidence_recorder.cleanup_transient_frames()
    sender_stats = sender.stats()
    emit(
        {
            "event": "publisher_finished",
            "live_session_id": live_session_id,
            "attempted_windows": attempted_windows,
            **sender_stats,
            "analysis": analysis_metrics.snapshot(),
            "final_rollup_ref": last_rollup.get("motion_rollup_ref") if last_rollup else None,
            "yogacoach_closeout": closeout_result,
        }
    )
    return publisher_exit_code


def main() -> int:
    return run_receiver(parse_args())
