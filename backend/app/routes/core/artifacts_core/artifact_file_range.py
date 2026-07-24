"""Bounded single-range streaming for workspace artifact files."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import AsyncIterator, Collection

from fastapi.responses import StreamingResponse


class RangeNotSatisfiable(ValueError):
    """Raised when a byte range cannot be served from the selected file."""


class PreviewDataUnsupported(ValueError):
    """Raised when an artifact MIME cannot be represented as preview data."""


class PreviewDataTooLarge(ValueError):
    """Raised when an artifact exceeds the bounded preview-data budget."""


def build_preview_data_payload(
    path: str | Path,
    *,
    media_type: str,
    allowed_media_types: Collection[str],
    max_bytes: int,
) -> dict[str, str | int]:
    file_path = Path(path)
    validate_preview_media_file(
        file_path,
        media_type=media_type,
        allowed_media_types=allowed_media_types,
        max_bytes=max_bytes,
    )
    content = file_path.read_bytes()
    return {
        "mime_type": media_type,
        "bytes": len(content),
        "data_base64": base64.b64encode(content).decode("ascii"),
    }


def validate_preview_media_file(
    path: str | Path,
    *,
    media_type: str,
    allowed_media_types: Collection[str],
    max_bytes: int,
) -> int:
    file_size = Path(path).stat().st_size
    if media_type not in allowed_media_types:
        raise PreviewDataUnsupported(media_type)
    if file_size > max_bytes:
        raise PreviewDataTooLarge(str(file_size))
    return file_size


def validate_preview_content_request(
    path: str | Path,
    *,
    media_type: str,
    allowed_media_types: Collection[str],
    max_bytes: int,
    range_header: str | None,
) -> int:
    """Permit oversized video only through byte-range streaming."""
    file_size = Path(path).stat().st_size
    if media_type not in allowed_media_types:
        raise PreviewDataUnsupported(media_type)
    if file_size <= max_bytes:
        return file_size
    if media_type.startswith("video/") and range_header:
        return file_size
    raise PreviewDataTooLarge(str(file_size))


def parse_single_byte_range(value: str, file_size: int) -> tuple[int, int]:
    if file_size <= 0 or not value.startswith("bytes=") or "," in value:
        raise RangeNotSatisfiable("unsupported_range")
    start_text, separator, end_text = value[6:].partition("-")
    if separator != "-" or (not start_text and not end_text):
        raise RangeNotSatisfiable("malformed_range")
    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise RangeNotSatisfiable("invalid_suffix_range")
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
    except ValueError as exc:
        raise RangeNotSatisfiable("malformed_range") from exc
    if start < 0 or start >= file_size or end < start:
        raise RangeNotSatisfiable("range_outside_file")
    return start, min(end, file_size - 1)


async def _read_file_range(
    path: Path,
    *,
    start: int,
    end: int,
    chunk_size: int = 1024 * 1024,
) -> AsyncIterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as stream:
        stream.seek(start)
        while remaining > 0:
            chunk = stream.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def build_range_file_response(
    path: str | Path,
    *,
    range_header: str,
    media_type: str,
    filename: str,
    content_disposition_type: str = "attachment",
) -> StreamingResponse:
    file_path = Path(path)
    file_size = file_path.stat().st_size
    start, end = parse_single_byte_range(range_header, file_size)
    safe_filename = filename.replace('"', "")
    return StreamingResponse(
        _read_file_range(file_path, start=start, end=end),
        status_code=206,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": (
                f'{content_disposition_type}; filename="{safe_filename}"'
            ),
            "Content-Length": str(end - start + 1),
            "Content-Range": f"bytes {start}-{end}/{file_size}",
        },
    )


__all__ = [
    "PreviewDataTooLarge",
    "PreviewDataUnsupported",
    "RangeNotSatisfiable",
    "build_preview_data_payload",
    "build_range_file_response",
    "parse_single_byte_range",
    "validate_preview_content_request",
    "validate_preview_media_file",
]
