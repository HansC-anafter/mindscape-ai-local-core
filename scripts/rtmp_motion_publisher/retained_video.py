from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class RetainedVideoProbe:
    duration_ms: float
    browser_metadata_duration_ms: float
    codec_name: str
    width: int
    height: int


@dataclass(frozen=True)
class RegisteredRetainedVideo:
    artifact_id: str
    duration_ms: float


def _read_mp4_box_header(
    handle: Any,
    *,
    container_end: int,
) -> tuple[bytes, int, int] | None:
    box_start = handle.tell()
    header = handle.read(8)
    if not header:
        return None
    if len(header) != 8:
        raise RuntimeError("learner_retained_video_mp4_box_invalid")
    size_32, box_type = struct.unpack(">I4s", header)
    header_size = 8
    if size_32 == 1:
        extended_size = handle.read(8)
        if len(extended_size) != 8:
            raise RuntimeError("learner_retained_video_mp4_box_invalid")
        box_size = struct.unpack(">Q", extended_size)[0]
        header_size = 16
    elif size_32 == 0:
        box_size = container_end - box_start
    else:
        box_size = size_32
    box_end = box_start + box_size
    if box_size < header_size or box_end > container_end:
        raise RuntimeError("learner_retained_video_mp4_box_invalid")
    return box_type, box_start + header_size, box_end


def read_mp4_movie_header_duration_ms(path: Path) -> float:
    file_end = path.stat().st_size
    with path.open("rb") as handle:
        while handle.tell() < file_end:
            top_level = _read_mp4_box_header(handle, container_end=file_end)
            if top_level is None:
                break
            box_type, payload_start, box_end = top_level
            if box_type != b"moov":
                handle.seek(box_end)
                continue
            handle.seek(payload_start)
            while handle.tell() < box_end:
                child = _read_mp4_box_header(handle, container_end=box_end)
                if child is None:
                    break
                child_type, child_payload_start, child_end = child
                if child_type != b"mvhd":
                    handle.seek(child_end)
                    continue
                handle.seek(child_payload_start)
                version_and_flags = handle.read(4)
                if len(version_and_flags) != 4:
                    raise RuntimeError(
                        "learner_retained_video_browser_metadata_invalid"
                    )
                if version_and_flags[0] == 0:
                    fields = handle.read(16)
                    if len(fields) != 16:
                        raise RuntimeError(
                            "learner_retained_video_browser_metadata_invalid"
                        )
                    timescale = struct.unpack(">I", fields[8:12])[0]
                    duration = struct.unpack(">I", fields[12:16])[0]
                    unknown_duration = duration == 0xFFFFFFFF
                elif version_and_flags[0] == 1:
                    fields = handle.read(28)
                    if len(fields) != 28:
                        raise RuntimeError(
                            "learner_retained_video_browser_metadata_invalid"
                        )
                    timescale = struct.unpack(">I", fields[16:20])[0]
                    duration = struct.unpack(">Q", fields[20:28])[0]
                    unknown_duration = duration == 0xFFFFFFFFFFFFFFFF
                else:
                    raise RuntimeError(
                        "learner_retained_video_browser_metadata_invalid"
                    )
                if timescale <= 0 or duration <= 0 or unknown_duration:
                    raise RuntimeError(
                        "learner_retained_video_browser_metadata_invalid"
                    )
                return duration * 1000.0 / timescale
            raise RuntimeError("learner_retained_video_browser_metadata_invalid")
    raise RuntimeError("learner_retained_video_browser_metadata_invalid")


def sha256_file(path: Path, *, chunk_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(max(4096, chunk_bytes)):
            digest.update(chunk)
    return digest.hexdigest()


def probe_retained_video(
    path: Path,
    *,
    ffmpeg_bin: str,
    timeout_sec: float,
) -> RetainedVideoProbe:
    browser_metadata_duration_ms = read_mp4_movie_header_duration_ms(path)
    ffprobe_bin = str(Path(ffmpeg_bin).expanduser().with_name("ffprobe"))
    result = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            "stream=codec_name,codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=max(1.0, timeout_sec),
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip()[:240]
        raise RuntimeError(
            f"learner_retained_video_probe_failed:{result.returncode}:{detail}"
        )
    try:
        payload = json.loads(result.stdout)
        duration_ms = float(payload["format"]["duration"]) * 1000.0
        stream = next(
            item
            for item in payload.get("streams", [])
            if item.get("codec_type") == "video"
        )
        probe = RetainedVideoProbe(
            duration_ms=duration_ms,
            browser_metadata_duration_ms=browser_metadata_duration_ms,
            codec_name=str(stream.get("codec_name") or "").strip(),
            width=int(stream.get("width") or 0),
            height=int(stream.get("height") or 0),
        )
    except (
        KeyError,
        StopIteration,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError("learner_retained_video_probe_invalid") from exc
    if (
        probe.duration_ms <= 0
        or probe.browser_metadata_duration_ms <= 0
        or not probe.codec_name
        or probe.width <= 0
        or probe.height <= 0
    ):
        raise RuntimeError("learner_retained_video_probe_invalid")
    duration_delta_ms = abs(
        probe.duration_ms - probe.browser_metadata_duration_ms
    )
    duration_tolerance_ms = max(500.0, probe.duration_ms * 0.001)
    if duration_delta_ms > duration_tolerance_ms:
        raise RuntimeError(
            "learner_retained_video_browser_duration_mismatch:"
            f"{round(probe.duration_ms, 3)}:"
            f"{round(probe.browser_metadata_duration_ms, 3)}"
        )
    return probe


def max_segment_end_ms(segments: list[dict[str, Any]]) -> float:
    end_ms = 0.0
    for segment in segments:
        raw = segment.get("segment_end_ms") or segment.get("end_ms")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            end_ms = max(end_ms, float(raw))
    return end_ms


def validate_retained_video_coverage(
    probe: RetainedVideoProbe,
    segments: list[dict[str, Any]],
    *,
    tolerance_ms: float = 500.0,
) -> None:
    required_end_ms = max_segment_end_ms(segments)
    if required_end_ms <= 0:
        raise RuntimeError("learner_retained_video_missing_segment_range")
    available_duration_ms = min(
        probe.duration_ms,
        probe.browser_metadata_duration_ms,
    )
    if available_duration_ms + max(0.0, tolerance_ms) < required_end_ms:
        raise RuntimeError(
            "learner_retained_video_coverage_short:"
            f"{round(available_duration_ms, 3)}:{round(required_end_ms, 3)}"
        )


def register_retained_video(
    *,
    args: Any,
    host_root: Path,
    storage_root: Path,
    live_session_id: str,
    segments: list[dict[str, Any]],
    input_kind: str,
    input_uri: str,
    probe: Callable[[Path], RetainedVideoProbe],
    register_artifact: Callable[..., Mapping[str, Any]],
) -> RegisteredRetainedVideo:
    parts = sorted(host_root.glob("learner-capture-part-*.mp4"))
    parts = [path for path in parts if path.stat().st_size > 0]
    if len(parts) != 1:
        raise RuntimeError(
            f"learner_retained_video_requires_single_contiguous_part:{len(parts)}"
        )
    path = parts[0]
    media_probe = probe(path)
    validate_retained_video_coverage(media_probe, segments)
    playback_duration_ms = min(
        media_probe.duration_ms,
        media_probe.browser_metadata_duration_ms,
    )
    checksum = sha256_file(path)
    response = register_artifact(
        args.api_base,
        "/api/v1/artifacts",
        {
            "workspace_id": args.workspace_id,
            "type": "video",
            "title": f"YogaCoach learner capture video: {live_session_id}",
            "description": (
                "Contiguous learner capture retained by the same FFmpeg reader "
                "that produced the analyzed motion frames."
            ),
            "file_path": str(storage_root / path.name),
            "metadata": {
                "kind": "yogacoach_learner_capture_video",
                "playbook_code": "yogacoach_practice_diary",
                "role": "learner",
                "source_kind": "learner_capture",
                "capture_session_id": args.source_session_id,
                "media_session_id": getattr(args, "media_session_id", "") or None,
                "live_session_id": live_session_id,
                "meeting_session_id": args.meeting_id,
                "receiver_identity": getattr(args, "receiver_identity", "") or None,
                "transport_kind": getattr(args, "transport_kind", "") or None,
                "capture_input_kind": input_kind,
                "capture_input_uri": input_uri,
                "lineage": "learner_capture_retained_by_analysis_reader",
                "mime_type": "video/mp4",
                "sha256": checksum,
                "byte_count": path.stat().st_size,
                "media_duration_ms": round(media_probe.duration_ms, 3),
                "browser_metadata_duration_ms": round(
                    media_probe.browser_metadata_duration_ms,
                    3,
                ),
                "playback_duration_ms": round(playback_duration_ms, 3),
                "video_codec": media_probe.codec_name,
                "video_width": media_probe.width,
                "video_height": media_probe.height,
                "adaptive_segment_count": len(segments),
            },
        },
        timeout_sec=args.api_timeout_sec,
        retry_count=args.api_retry_count,
        retry_backoff_sec=args.api_retry_backoff_sec,
    )
    artifact_id = str(response.get("id") or "").strip()
    if not artifact_id:
        raise RuntimeError(
            "learner retained video artifact registration returned no id"
        )
    return RegisteredRetainedVideo(
        artifact_id=artifact_id,
        duration_ms=playback_duration_ms,
    )
