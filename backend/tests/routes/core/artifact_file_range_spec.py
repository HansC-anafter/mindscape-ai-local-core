from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.app.routes.core.artifacts_core.artifact_file_range import (
    PreviewDataTooLarge,
    PreviewDataUnsupported,
    RangeNotSatisfiable,
    build_preview_data_payload,
    build_range_file_response,
    parse_single_byte_range,
    validate_preview_content_request,
    validate_preview_media_file,
)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=2-5", (2, 5)),
        ("bytes=7-", (7, 9)),
        ("bytes=-3", (7, 9)),
        ("bytes=8-99", (8, 9)),
    ],
)
def test_parse_single_byte_range(header: str, expected: tuple[int, int]) -> None:
    assert parse_single_byte_range(header, 10) == expected


@pytest.mark.parametrize(
    "header",
    ["items=0-1", "bytes=", "bytes=4-2", "bytes=10-11", "bytes=0-1,4-5"],
)
def test_parse_single_byte_range_rejects_unsupported_ranges(header: str) -> None:
    with pytest.raises(RangeNotSatisfiable):
        parse_single_byte_range(header, 10)


def test_range_response_streams_only_requested_bytes(tmp_path) -> None:
    artifact = tmp_path / "sample.mp4"
    artifact.write_bytes(b"0123456789")

    response = build_range_file_response(
        artifact,
        range_header="bytes=3-6",
        media_type="video/mp4",
        filename=artifact.name,
    )

    async def read_body() -> bytes:
        return b"".join([chunk async for chunk in response.body_iterator])

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 3-6/10"
    assert response.headers["content-length"] == "4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-disposition"] == 'attachment; filename="sample.mp4"'
    assert asyncio.run(read_body()) == b"3456"


def test_range_response_can_render_safe_media_inline(tmp_path) -> None:
    artifact = tmp_path / "sample.mp4"
    artifact.write_bytes(b"0123456789")

    response = build_range_file_response(
        artifact,
        range_header="bytes=0-3",
        media_type="video/mp4",
        filename=artifact.name,
        content_disposition_type="inline",
    )

    assert response.headers["content-disposition"] == 'inline; filename="sample.mp4"'


def test_preview_data_payload_is_bounded_and_base64_encoded(tmp_path) -> None:
    artifact = tmp_path / "sample.jpg"
    artifact.write_bytes(b"frame")

    payload = build_preview_data_payload(
        artifact,
        media_type="image/jpeg",
        allowed_media_types={"image/jpeg"},
        max_bytes=8,
    )

    assert payload == {
        "mime_type": "image/jpeg",
        "bytes": 5,
        "data_base64": "ZnJhbWU=",
    }


def test_preview_data_payload_rejects_type_and_size(tmp_path) -> None:
    artifact = tmp_path / "sample.bin"
    artifact.write_bytes(b"0123456789")

    with pytest.raises(PreviewDataUnsupported):
        build_preview_data_payload(
            artifact,
            media_type="application/octet-stream",
            allowed_media_types={"image/jpeg"},
            max_bytes=20,
        )
    with pytest.raises(PreviewDataTooLarge):
        build_preview_data_payload(
            artifact,
            media_type="image/jpeg",
            allowed_media_types={"image/jpeg"},
            max_bytes=5,
        )


def test_preview_media_file_validation_supports_bounded_binary_delivery(tmp_path) -> None:
    artifact = tmp_path / "sample.mp4"
    artifact.write_bytes(b"bounded-video")

    assert validate_preview_media_file(
        artifact,
        media_type="video/mp4",
        allowed_media_types={"video/mp4"},
        max_bytes=32,
    ) == 13

    with pytest.raises(PreviewDataTooLarge):
        validate_preview_media_file(
            artifact,
            media_type="video/mp4",
            allowed_media_types={"video/mp4"},
            max_bytes=8,
        )


def test_large_preview_video_requires_byte_range_streaming(tmp_path) -> None:
    artifact = tmp_path / "sample.mp4"
    artifact.write_bytes(b"oversized-video")

    assert validate_preview_content_request(
        artifact,
        media_type="video/mp4",
        allowed_media_types={"video/mp4"},
        max_bytes=8,
        range_header="bytes=0-",
    ) == 15
    with pytest.raises(PreviewDataTooLarge):
        validate_preview_content_request(
            artifact,
            media_type="video/mp4",
            allowed_media_types={"video/mp4"},
            max_bytes=8,
            range_header=None,
        )


def test_large_preview_image_remains_bounded_even_with_range(tmp_path) -> None:
    artifact = tmp_path / "sample.jpg"
    artifact.write_bytes(b"oversized-image")

    with pytest.raises(PreviewDataTooLarge):
        validate_preview_content_request(
            artifact,
            media_type="image/jpeg",
            allowed_media_types={"image/jpeg"},
            max_bytes=8,
            range_header="bytes=0-3",
        )


def _request(path: str, range_header: str | None = None) -> Request:
    headers = [] if range_header is None else [(b"range", range_header.encode())]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": headers,
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )


def _load_file_routes(monkeypatch, artifact):
    state_name = "backend.app.routes.core.artifacts_core.state"
    module_name = "backend.app.routes.core.artifacts_core.file_routes"
    fake_state = ModuleType(state_name)
    fake_state.logger = logging.getLogger("artifact-file-range-spec")
    fake_state.store = SimpleNamespace(
        artifacts=SimpleNamespace(get_artifact=lambda _artifact_id: artifact)
    )
    monkeypatch.setitem(sys.modules, state_name, fake_state)
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_preview_content_route_streams_large_video_with_range(
    monkeypatch,
    tmp_path,
) -> None:
    video = tmp_path / "learner.mp4"
    video.write_bytes(b"oversized-video")
    artifact = SimpleNamespace(
        workspace_id="workspace-1",
        metadata={"file_path": str(video)},
        storage_ref=None,
    )
    file_routes = _load_file_routes(monkeypatch, artifact)
    monkeypatch.setattr(file_routes, "MAX_PREVIEW_DATA_BYTES", 8)

    response = asyncio.run(
        file_routes.get_artifact_file(
            _request(
                "/api/v1/workspaces/workspace-1/media-assets/artifact-1/preview-content",
                "bytes=0-3",
            ),
            workspace_id="workspace-1",
            artifact_id="artifact-1",
        )
    )

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-3/15"
    assert response.headers["content-disposition"] == (
        'inline; filename="learner.mp4"'
    )


def test_preview_content_route_rejects_large_video_without_range(
    monkeypatch,
    tmp_path,
) -> None:
    video = tmp_path / "learner.mp4"
    video.write_bytes(b"oversized-video")
    artifact = SimpleNamespace(
        workspace_id="workspace-1",
        metadata={"file_path": str(video)},
        storage_ref=None,
    )
    file_routes = _load_file_routes(monkeypatch, artifact)
    monkeypatch.setattr(file_routes, "MAX_PREVIEW_DATA_BYTES", 8)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            file_routes.get_artifact_file(
                _request(
                    "/api/v1/workspaces/workspace-1/media-assets/artifact-1/preview-content"
                ),
                workspace_id="workspace-1",
                artifact_id="artifact-1",
            )
        )

    assert exc_info.value.status_code == 413
