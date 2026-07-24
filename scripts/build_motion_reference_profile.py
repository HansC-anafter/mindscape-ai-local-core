#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

from rtmp_motion_publisher.capture import FfmpegRawFrameCapture
from rtmp_motion_publisher.pose import PoseDetector, pose_sample_from_result
from rtmp_motion_publisher.reference_profile import (
    build_motion_reference_profile,
    load_course_chapters,
)
from rtmp_motion_publisher.reference_evidence import (
    ReferenceVisualEvidenceRecorder,
)
from rtmp_motion_publisher.settings import (
    DEFAULT_FFMPEG_BIN,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_WIDTH,
    DEFAULT_MODEL_ASSET_PATH,
)
from rtmp_motion_publisher.windows import MotionWindowAccumulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an independent compact motion reference profile from local media.",
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--chapters-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--reference-evidence-output-dir", required=True)
    parser.add_argument("--reference-evidence-storage-dir", required=True)
    parser.add_argument("--api-base", default="http://127.0.0.1:8200")
    parser.add_argument("--api-timeout-sec", type=float, default=30.0)
    parser.add_argument("--jpeg-quality", type=int, default=78)
    parser.add_argument("--sample-fps", type=float, default=1.0)
    parser.add_argument("--window-sec", type=float, default=2.0)
    parser.add_argument("--frame-width", type=int, default=DEFAULT_FRAME_WIDTH)
    parser.add_argument("--frame-height", type=int, default=DEFAULT_FRAME_HEIGHT)
    parser.add_argument("--ffmpeg-bin", default=DEFAULT_FFMPEG_BIN)
    parser.add_argument("--model-asset-path", default=str(DEFAULT_MODEL_ASSET_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chapters = load_course_chapters(args.chapters_json)
    capture = FfmpegRawFrameCapture(
        rtmp_url=args.input,
        ffmpeg_bin=args.ffmpeg_bin,
        sample_fps=args.sample_fps,
        frame_width=args.frame_width,
        frame_height=args.frame_height,
        read_timeout_sec=30.0,
        avfoundation_framerate=60.0,
        ffmpeg_realtime_input=False,
    )
    if not capture.isOpened():
        raise RuntimeError("reference_media_open_failed")
    detector = PoseDetector.create(args.model_asset_path)
    accumulator = MotionWindowAccumulator(
        live_session_id=args.profile_id,
        source_session_id=f"reference:{args.profile_id}",
        window_ms=max(250.0, args.window_sec * 1000.0),
        max_samples=max(1, round(args.sample_fps * args.window_sec)),
    )
    evidence = ReferenceVisualEvidenceRecorder(
        chapters=chapters,
        profile_id=args.profile_id,
        source_ref=args.source_ref,
        workspace_id=args.workspace_id,
        output_dir=args.reference_evidence_output_dir,
        storage_dir=args.reference_evidence_storage_dir,
        api_base=args.api_base,
        jpeg_quality=args.jpeg_quality,
        api_timeout_sec=args.api_timeout_sec,
    )
    windows: list[dict] = []
    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            timestamp_ms = frame_index * 1000.0 / max(0.1, args.sample_fps)
            result = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), timestamp_ms)
            evidence.observe(frame, timestamp_ms)
            window = accumulator.push(pose_sample_from_result(result, timestamp_ms))
            if window is not None:
                windows.append(window)
            frame_index += 1
            if frame_index % max(1, round(args.sample_fps * 60)) == 0:
                print(
                    json.dumps(
                        {
                            "event": "reference_profile_progress",
                            "media_ms": round(timestamp_ms),
                            "window_count": len(windows),
                        }
                    ),
                    file=sys.stderr,
                    flush=True,
                )
        final_window = accumulator.flush(
            frame_index * 1000.0 / max(0.1, args.sample_fps)
        )
        if final_window is not None:
            windows.append(final_window)
    finally:
        detector.close()
        capture.release()
    visual_evidence = evidence.finalize()
    profile = build_motion_reference_profile(
        profile_id=args.profile_id,
        source_ref=args.source_ref,
        chapters=chapters,
        windows=windows,
        visual_evidence=visual_evidence,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=True, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "event": "reference_profile_complete",
                "output": str(output),
                "frame_count": frame_index,
                "window_count": len(windows),
                "chapter_count": len(profile["chapters"]),
                "reference_visual_count": len(visual_evidence),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
