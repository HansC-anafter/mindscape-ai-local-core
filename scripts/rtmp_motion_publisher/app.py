from __future__ import annotations

import signal
import time
from typing import Any

import cv2

from .api_client import emit_rollup, register_live_session
from .capture import open_stream_capture
from .cli import parse_args
from .closeout import emit_yogacoach_closeout
from .events import configure_event_log, emit
from .evidence import LearnerVisualEvidenceRecorder
from .guidance import BackgroundMotionWindowSender, GuidanceSocket
from .pose import PoseDetector, pose_sample_from_result
from .reference_profile import load_motion_reference_profile
from .reference_alignment import LiveReferenceAlignmentMatcher
from .receiver_state import transition_receiver_state
from .source_uri import public_input_uri
from .stream_cost import start_stream_cost_tracking
from .windows import MotionWindowAccumulator, PendingMotionWindow, PoseSample


def _public_reference_alignment_status(
    summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    metadata = summary.get("metadata")
    if not isinstance(metadata, dict):
        return None
    alignment = metadata.get("reference_alignment")
    if not isinstance(alignment, dict):
        return None
    allowed_keys = (
        "chapter_id",
        "reference_window_index",
        "score",
        "localization_score",
        "confidence",
        "verdict",
        "localization_ready",
        "selection_mode",
        "sequence_history_size",
        "global_candidate_chapter_id",
        "global_candidate_score",
        "full_sequence_candidate_chapter_id",
        "full_sequence_candidate_score",
        "local_candidate_chapter_id",
        "local_candidate_score",
        "previous_chapter_candidate_chapter_id",
        "previous_chapter_candidate_score",
        "ordered_transition_supported",
        "pending_transition_chapter_id",
        "pending_transition_count",
        "pending_relock_chapter_id",
        "pending_relock_count",
    )
    return {key: alignment[key] for key in allowed_keys if key in alignment}


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


def _receiver_metrics(
    *,
    attempted_windows: int,
    sender_stats: dict[str, Any],
    reconnect_attempts: int,
    last_window_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    alignment = _public_reference_alignment_status(last_window_summary)
    return {
        "attempted_windows": attempted_windows,
        "accepted_windows": sender_stats.get("accepted_windows", 0),
        "rejected_windows": sender_stats.get("rejected_windows", 0),
        "failed_windows": sender_stats.get("failed_windows", 0),
        "append_queue_pending": sender_stats.get("append_queue_pending", 0),
        "reconnect_attempts": reconnect_attempts,
        "last_window_end_ms": (
            last_window_summary.get("ts_end_ms")
            if last_window_summary is not None
            else None
        ),
        "reference_chapter_id": (
            alignment.get("chapter_id") if alignment is not None else None
        ),
        "reference_localization_ready": (
            alignment.get("localization_ready") if alignment is not None else None
        ),
    }


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

    capture = open_stream_capture(args)
    input_uri = public_input_uri(args.rtmp_url)
    if not capture.isOpened():
        emit({"event": "stream_open_failed", "input_uri": input_uri})
        capture.release()
        return 2
    first_frame_ok, first_frame = capture.read()
    if not first_frame_ok:
        emit(
            {
                "event": "stream_open_failed",
                "input_uri": input_uri,
                "reason": "initial_frame_unavailable",
            }
        )
        capture.release()
        return 2
    stream_cost_tracker = start_stream_cost_tracking(args, first_frame)
    emit(
        {
            "event": "stream_opened",
            "input_uri": input_uri,
            "capture_backend": args.capture_backend,
            "frame_width": args.frame_width if args.capture_backend == "ffmpeg" else None,
            "frame_height": args.frame_height if args.capture_backend == "ffmpeg" else None,
            "read_timeout_sec": args.stream_read_timeout_sec,
        }
    )
    transition_receiver_state(args, "analyzing")

    try:
        live_session_id = register_live_session(args)
    except Exception:
        if stream_cost_tracker is not None:
            stream_cost_tracker.finish(first_frame)
        capture.release()
        raise
    practice_session_id = args.practice_session_id or f"{args.source_session_id}:live_guidance"
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
        )
        pose = PoseDetector.create(args.model_asset_path)
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
    evidence_recorder = LearnerVisualEvidenceRecorder(args, live_session_id)
    start = time.monotonic()
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

    def enqueue_window_summary(
        summary: dict[str, Any],
        frame: Any | None = None,
    ) -> None:
        nonlocal attempted_windows, last_window_summary
        attempted_windows += 1
        if reference_matcher is not None:
            reference_matcher.annotate(summary)
        last_window_summary = summary
        evidence_recorder.capture_window(frame, summary)
        if sender is None:
            return
        sender.enqueue(
            PendingMotionWindow(
                summary=summary,
                received_at_ms=time.monotonic() * 1000.0,
            )
        )

    def enqueue_sample_window(sample: PoseSample, frame: Any | None = None) -> None:
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

    def reconnect_stream(reason: str) -> bool:
        nonlocal capture, reconnect_attempts, consecutive_read_failures, next_sample_at, pending_first_frame
        if not holdover_active(time.monotonic()):
            accumulator.reset()
        capture.release()
        while not stop_requested:
            if (
                args.stream_reconnect_max_attempts > 0
                and reconnect_attempts >= args.stream_reconnect_max_attempts
            ):
                emit(
                    {
                        "event": "stream_reconnect_give_up",
                        "reason": reason,
                        "attempts": reconnect_attempts,
                        "elapsed_sec": round(time.monotonic() - start, 3),
                    }
                )
                return False
            reconnect_attempts += 1
            emit(
                {
                    "event": "stream_reconnect_started",
                    "reason": reason,
                    "attempt": reconnect_attempts,
                    "elapsed_sec": round(time.monotonic() - start, 3),
                }
            )
            transition_receiver_state(args, "degraded", reason=reason)
            time.sleep(max(0.0, args.stream_reconnect_backoff_sec))
            replacement = open_stream_capture(args)
            if replacement.isOpened():
                first_reconnect_frame_ok, first_reconnect_frame = replacement.read()
                if not first_reconnect_frame_ok:
                    replacement.release()
                    emit(
                        {
                            "event": "stream_reconnect_failed",
                            "reason": "initial_frame_unavailable",
                            "attempt": reconnect_attempts,
                            "elapsed_sec": round(time.monotonic() - start, 3),
                        }
                    )
                    continue
                capture = replacement
                pending_first_frame = first_reconnect_frame
                consecutive_read_failures = 0
                next_sample_at = time.monotonic()
                emit(
                    {
                        "event": "stream_reconnected",
                        "attempt": reconnect_attempts,
                        "elapsed_sec": round(time.monotonic() - start, 3),
                    }
                )
                transition_receiver_state(args, "analyzing")
                return True
            replacement.release()
            emit(
                {
                    "event": "stream_reconnect_failed",
                    "attempt": reconnect_attempts,
                    "elapsed_sec": round(time.monotonic() - start, 3),
                }
            )
        return False

    try:
        while not stop_requested:
            now = time.monotonic()
            if args.duration_sec > 0 and now - start >= args.duration_sec:
                break
            if pending_first_frame is not None:
                ok, frame = True, pending_first_frame
                pending_first_frame = None
            else:
                ok, frame = capture.read()
            if not ok:
                failure_now = time.monotonic()
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
                    if not reconnect_stream("read_failed"):
                        publisher_exit_code = 3
                        break
                time.sleep(0.25)
                continue
            consecutive_read_failures = 0
            last_frame = frame
            if now < next_sample_at:
                continue
            next_sample_at = now + 1.0 / max(0.1, args.sample_fps)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            timestamp_ms = (now - start) * 1000.0
            result = pose.process(rgb, timestamp_ms)
            sample = pose_sample_from_result(result, timestamp_ms)
            last_pose_sample = sample
            last_real_frame_at = now
            enqueue_sample_window(sample, frame)
            if now >= next_status_at:
                sender_stats = sender.stats()
                emit(
                    {
                        "event": "publisher_status",
                        "elapsed_sec": round(now - start, 3),
                        "attempted_windows": attempted_windows,
                        **sender_stats,
                        "last_confidence": (
                            last_window_summary["confidence_stats"]["mean_confidence"]
                            if last_window_summary is not None
                            else None
                        ),
                        "last_findings": (
                            last_window_summary["findings"]
                            if last_window_summary is not None
                            else []
                        ),
                        "reference_alignment": _public_reference_alignment_status(
                            last_window_summary
                        ),
                    }
                )
                transition_receiver_state(
                    args,
                    "analyzing",
                    metrics=_receiver_metrics(
                        attempted_windows=attempted_windows,
                        sender_stats=sender_stats,
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
        terminal_end_ms = max(0.0, (time.monotonic() - start) * 1000.0)
        if args.duration_sec > 0:
            terminal_end_ms = min(terminal_end_ms, args.duration_sec * 1000.0)
        terminal_summary = accumulator.flush(terminal_end_ms)
        if terminal_summary is not None:
            enqueue_window_summary(terminal_summary, last_frame)
            emit(
                {
                    "event": "terminal_motion_window_flushed",
                    "window_id": terminal_summary["window_id"],
                    "start_ms": terminal_summary["ts_start_ms"],
                    "end_ms": terminal_summary["ts_end_ms"],
                }
            )
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
                "final_rollup_ref": None,
                "yogacoach_closeout": None,
                "failure_reason": "final_rollup_failed",
            }
        )
        return publisher_exit_code or 4
    last_rollup = final_rollup
    learner_visual_evidence = evidence_recorder.finalize(last_rollup)
    closeout_result = emit_yogacoach_closeout(
        args,
        live_session_id=live_session_id,
        rollup_response=last_rollup,
        learner_visual_evidence=learner_visual_evidence,
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
            "final_rollup_ref": last_rollup.get("motion_rollup_ref") if last_rollup else None,
            "yogacoach_closeout": closeout_result,
        }
    )
    return publisher_exit_code


def main() -> int:
    return run_receiver(parse_args())
