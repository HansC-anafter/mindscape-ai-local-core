#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from reference_profile_rebuild.chapter_clip_source import prepare_chapter_clips
from reference_profile_rebuild.artifact_registration import artifact_metadata
from reference_profile_rebuild.feature_rebuild import (
    analyze_chapter_clips,
)
from reference_profile_rebuild.profile_upgrade import build_upgraded_profile
from rtmp_motion_publisher.api_client import api_post
from rtmp_motion_publisher.reference_profile import load_motion_reference_profile
from rtmp_motion_publisher.settings import (
    DEFAULT_FFMPEG_BIN,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_WIDTH,
    DEFAULT_MODEL_ASSET_PATH,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild a complete motion reference profile from its registered "
            "chapter clips using the current posture feature schema."
        )
    )
    parser.add_argument("--source-profile", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--api-base", default="http://127.0.0.1:8200")
    parser.add_argument("--api-timeout-sec", type=float, default=60.0)
    parser.add_argument("--sample-fps", type=float, default=1.0)
    parser.add_argument("--window-sec", type=float, default=3.0)
    parser.add_argument("--frame-width", type=int, default=DEFAULT_FRAME_WIDTH)
    parser.add_argument("--frame-height", type=int, default=DEFAULT_FRAME_HEIGHT)
    parser.add_argument("--ffmpeg-bin", default=DEFAULT_FFMPEG_BIN)
    parser.add_argument("--model-asset-path", default=str(DEFAULT_MODEL_ASSET_PATH))
    parser.add_argument(
        "--register-file-path",
        help="Container-visible output path; when set, register the rebuilt profile artifact.",
    )
    return parser.parse_args()


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


def main() -> int:
    args = parse_args()
    source_profile = load_motion_reference_profile(args.source_profile)
    clips = prepare_chapter_clips(
        source_profile,
        api_base=args.api_base,
        workspace_id=args.workspace_id,
        cache_dir=args.cache_dir,
        timeout_sec=args.api_timeout_sec,
    )
    windows = analyze_chapter_clips(
        clips,
        profile_id=args.profile_id,
        model_asset_path=args.model_asset_path,
        ffmpeg_bin=args.ffmpeg_bin,
        sample_fps=args.sample_fps,
        window_sec=args.window_sec,
        frame_width=args.frame_width,
        frame_height=args.frame_height,
        progress=_emit,
    )
    profile = build_upgraded_profile(
        source_profile,
        profile_id=args.profile_id,
        windows=windows,
    )
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(profile, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_id = None
    if args.register_file_path:
        checksum = hashlib.sha256(output.read_bytes()).hexdigest()
        artifact = api_post(
            args.api_base,
            "/api/v1/artifacts",
            {
                "workspace_id": args.workspace_id,
                "type": "json",
                "title": f"YogaCoach motion reference profile: {args.profile_id}",
                "description": (
                    "Complete independent course reference profile with bounded "
                    "posture geometry features and durable visual evidence lineage."
                ),
                "file_path": args.register_file_path,
                "metadata": artifact_metadata(
                    profile=profile,
                    source_profile=source_profile,
                    profile_id=args.profile_id,
                    checksum=checksum,
                ),
            },
            timeout_sec=args.api_timeout_sec,
            retry_count=1,
            retry_backoff_sec=0.0,
        )
        artifact_id = artifact.get("id")
        if not artifact_id:
            raise RuntimeError("rebuilt_reference_profile_artifact_id_missing")
    _emit(
        {
            "event": "reference_profile_feature_rebuild_complete",
            "output": str(output),
            "artifact_id": artifact_id,
            "chapter_count": len(profile["chapters"]),
            "window_count": len(windows),
            "posture_feature_chapter_count": profile["metadata"][
                "posture_feature_chapter_count"
            ],
            "visual_evidence_asset_count": len(profile["visual_evidence"]),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
