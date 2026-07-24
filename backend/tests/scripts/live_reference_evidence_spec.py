from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from scripts.rtmp_motion_publisher import reference_evidence


def _chapters() -> list[dict]:
    return [
        {"chapter_id": "reference:001", "start_ms": 0.0, "end_ms": 1000.0},
        {
            "chapter_id": "reference:002",
            "start_ms": 1000.0,
            "end_ms": 2000.0,
        },
    ]


def test_reference_evidence_registers_one_independent_frame_per_chapter(
    tmp_path,
    monkeypatch,
) -> None:
    requests: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        reference_evidence,
        "api_post",
        lambda _base, route, payload, **_kwargs: requests.append((route, payload))
        or {"id": "reference-contact-sheet-one"},
    )
    monkeypatch.setattr(
        reference_evidence,
        "cv2",
        SimpleNamespace(
            INTER_AREA=1,
            IMWRITE_JPEG_QUALITY=2,
            resize=lambda frame, _size, interpolation: frame,
            imwrite=lambda path, _image, _options: (
                __import__("pathlib").Path(path).write_bytes(b"jpeg") > 0
            ),
        ),
    )
    recorder = reference_evidence.ReferenceVisualEvidenceRecorder(
        chapters=_chapters(),
        profile_id="profile-one",
        source_ref="https://example.test/reference",
        workspace_id="workspace-one",
        output_dir=tmp_path / "host",
        storage_dir="/app/data/workspaces/workspace-one/reference",
        api_base="http://127.0.0.1:8200",
    )
    recorder.observe(np.full((90, 160, 3), 10, dtype=np.uint8), 400.0)
    recorder.observe(np.full((90, 160, 3), 20, dtype=np.uint8), 600.0)
    recorder.observe(np.full((90, 160, 3), 30, dtype=np.uint8), 1500.0)

    assets = recorder.finalize()

    assert len(assets) == 2
    assert {asset["chapter_id"] for asset in assets} == {
        "reference:001",
        "reference:002",
    }
    assert all(asset["role"] == "reference" for asset in assets)
    assert all(asset["source_kind"] == "reference_asset" for asset in assets)
    assert all("capture_session_id" not in asset for asset in assets)
    assert requests[0][0] == "/api/v1/artifacts"
    assert requests[0][1]["metadata"]["role"] == "reference"
    assert (tmp_path / "host/reference-chapter-contact-sheet.jpg").is_file()


def test_reference_evidence_fails_closed_when_any_chapter_frame_is_missing(
    tmp_path,
) -> None:
    recorder = reference_evidence.ReferenceVisualEvidenceRecorder(
        chapters=_chapters(),
        profile_id="profile-one",
        source_ref="https://example.test/reference",
        workspace_id="workspace-one",
        output_dir=tmp_path / "host",
        storage_dir="/app/data/workspaces/workspace-one/reference",
        api_base="http://127.0.0.1:8200",
    )
    recorder.observe(np.zeros((90, 160, 3), dtype=np.uint8), 500.0)

    with pytest.raises(
        ValueError,
        match="reference_visual_evidence_chapter_frames_missing:reference:002",
    ):
        recorder.finalize()
