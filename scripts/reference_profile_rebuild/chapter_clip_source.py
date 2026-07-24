from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

import requests


@dataclass(frozen=True)
class ChapterClip:
    chapter_id: str
    chapter_index: int
    start_ms: float
    end_ms: float
    artifact_id: str
    path: Path


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def chapter_clip_specs(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    chapters = _records(profile.get("chapters"))
    clips_by_chapter = {
        str(item.get("chapter_id") or "").strip(): item
        for item in _records(profile.get("visual_evidence"))
        if item.get("media_kind") == "video_clip"
        and str(item.get("artifact_id") or "").strip()
    }
    specs: list[dict[str, Any]] = []
    missing: list[str] = []
    for index, chapter in enumerate(chapters):
        chapter_id = str(chapter.get("chapter_id") or "").strip()
        clip = clips_by_chapter.get(chapter_id)
        if not chapter_id or clip is None:
            missing.append(chapter_id or f"chapter_{index + 1:03d}")
            continue
        start_ms = float(chapter.get("ts_start_ms") or 0.0)
        end_ms = max(start_ms, float(chapter.get("ts_end_ms") or start_ms))
        if end_ms <= start_ms:
            raise ValueError(f"reference_chapter_range_invalid:{chapter_id}")
        specs.append(
            {
                "chapter_id": chapter_id,
                "chapter_index": index,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "artifact_id": str(clip["artifact_id"]).strip(),
            }
        )
    if missing:
        raise ValueError("reference_chapter_clip_missing:" + ",".join(missing))
    if len(specs) != len(chapters):
        raise ValueError("reference_chapter_clip_coverage_incomplete")
    return specs


def _download_artifact(
    *,
    api_base: str,
    workspace_id: str,
    artifact_id: str,
    target: Path,
    timeout_sec: float,
) -> None:
    url = (
        f"{api_base.rstrip('/')}/api/v1/workspaces/"
        f"{quote(workspace_id, safe='')}/artifacts/{quote(artifact_id, safe='')}/file"
    )
    response = requests.get(url, stream=True, timeout=timeout_sec)
    response.raise_for_status()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".partial")
    with temporary.open("wb") as output:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                output.write(chunk)
    if temporary.stat().st_size < 32:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"reference_chapter_clip_empty:{artifact_id}")
    temporary.replace(target)


def prepare_chapter_clips(
    profile: Mapping[str, Any],
    *,
    api_base: str,
    workspace_id: str,
    cache_dir: str | Path,
    timeout_sec: float,
) -> list[ChapterClip]:
    cache_root = Path(cache_dir).expanduser()
    clips: list[ChapterClip] = []
    for spec in chapter_clip_specs(profile):
        path = cache_root / (
            f"chapter-{int(spec['chapter_index']) + 1:03d}-"
            f"{spec['artifact_id']}.mp4"
        )
        if not path.exists() or path.stat().st_size < 32:
            _download_artifact(
                api_base=api_base,
                workspace_id=workspace_id,
                artifact_id=str(spec["artifact_id"]),
                target=path,
                timeout_sec=timeout_sec,
            )
        clips.append(
            ChapterClip(
                chapter_id=str(spec["chapter_id"]),
                chapter_index=int(spec["chapter_index"]),
                start_ms=float(spec["start_ms"]),
                end_ms=float(spec["end_ms"]),
                artifact_id=str(spec["artifact_id"]),
                path=path,
            )
        )
    return clips


__all__ = ["ChapterClip", "chapter_clip_specs", "prepare_chapter_clips"]

