import base64
import hashlib
import json
from pathlib import Path

from backend.app.services.file_analysis_service_core import (
    calculate_file_hash_for_analysis,
    resolve_file_path_by_id,
    store_uploaded_file,
    write_analysis_sidecar,
)


def _data_url(content: bytes, mime_type: str = "text/plain") -> str:
    encoded = base64.b64encode(content).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def test_store_uploaded_file_persists_content_and_metadata(tmp_path):
    result = store_uploaded_file(
        workspace_id="workspace-1",
        file_data=_data_url(b"hello"),
        file_name="note",
        file_type="text/plain",
        file_size=None,
        uploads_dir=str(tmp_path),
        file_id_factory=lambda: "file-1",
    )

    stored_path = tmp_path / "workspace-1" / "file-1.txt"
    metadata_path = tmp_path / "workspace-1" / "file-1.meta.json"
    expected_hash = hashlib.sha256(b"hello").hexdigest()

    assert result == {
        "file_id": "file-1",
        "file_path": str(stored_path),
        "file_name": "note",
        "file_type": "text/plain",
        "file_size": 5,
        "file_hash": expected_hash,
    }
    assert stored_path.read_bytes() == b"hello"
    assert json.loads(metadata_path.read_text()) == {
        "file_id": "file-1",
        "original_name": "note",
        "file_type": "text/plain",
        "file_size": 5,
        "file_hash": expected_hash,
    }


def test_resolve_file_path_by_id_prefers_lookup_then_upload_scan(tmp_path):
    assert resolve_file_path_by_id(
        "file-1",
        file_path_lookup=lambda file_id: f"/core-files/{file_id}.pdf",
    ) == "/core-files/file-1.pdf"

    fallback_file = tmp_path / "file-2.pdf"
    fallback_file.write_bytes(b"pdf")

    def missing_lookup(_file_id):
        raise ImportError("core files unavailable")

    assert resolve_file_path_by_id(
        "file-2",
        uploads_dir=str(tmp_path),
        file_path_lookup=missing_lookup,
    ) == str(fallback_file)


def test_calculate_file_hash_for_analysis_uses_path_data_then_id(tmp_path):
    path_file = tmp_path / "path.txt"
    path_file.write_bytes(b"path-content")
    data_url = _data_url(b"data-content")

    path_result = calculate_file_hash_for_analysis(
        file_path=str(path_file),
        file_data=data_url,
        file_id="file-id",
        workspace_id="workspace-1",
        file_name="path.txt",
        uploads_dir=str(tmp_path),
    )
    assert path_result.file_hash == hashlib.sha256(b"path-content").hexdigest()
    assert path_result.file_path == str(path_file)

    data_result = calculate_file_hash_for_analysis(
        file_path=None,
        file_data=data_url,
        file_id="file-id",
        workspace_id="workspace-1",
        file_name="data.txt",
        uploads_dir=str(tmp_path),
    )
    assert data_result.file_hash == hashlib.sha256(b"data-content").hexdigest()
    assert data_result.file_path is None

    workspace_upload = tmp_path / "workspace-1" / "file-id.pdf"
    workspace_upload.parent.mkdir(parents=True)
    workspace_upload.write_bytes(b"id-content")
    id_result = calculate_file_hash_for_analysis(
        file_path=None,
        file_data=None,
        file_id="file-id",
        workspace_id="workspace-1",
        file_name="id.pdf",
        uploads_dir=str(tmp_path),
    )
    assert id_result.file_hash == hashlib.sha256(b"id-content").hexdigest()
    assert id_result.file_path == str(workspace_upload)


def test_write_analysis_sidecar_preserves_schema(tmp_path):
    file_path = tmp_path / "document.pdf"
    file_path.write_bytes(b"pdf")

    sidecar_path = write_analysis_sidecar(
        file_path=str(file_path),
        analysis_result={"file_info": {"pages": 2}},
        event_id="event-1",
        file_hash="hash-1",
        file_name="document.pdf",
        file_type="application/pdf",
        workspace_id="workspace-1",
    )

    assert sidecar_path == tmp_path / "document.analysis.json"
    assert json.loads(sidecar_path.read_text()) == {
        "file_info": {"pages": 2},
        "event_id": "event-1",
        "file_hash": "hash-1",
        "file_name": "document.pdf",
        "file_type": "application/pdf",
        "workspace_id": "workspace-1",
    }


def test_file_analysis_storage_files_stay_below_line_gate():
    repo_root = Path(__file__).resolve().parents[2]
    paths = [
        repo_root / "backend/app/services/file_analysis_service.py",
        repo_root / "backend/app/services/file_analysis_service_core/__init__.py",
        repo_root / "backend/app/services/file_analysis_service_core/file_storage.py",
        repo_root / "backend/tests/file_analysis_service_storage_seams_spec.py",
    ]

    for path in paths:
        assert len(path.read_text().splitlines()) <= 500, path


def test_file_analysis_storage_seam_has_no_store_or_background_markers():
    repo_root = Path(__file__).resolve().parents[2]
    source = (
        repo_root / "backend/app/services/file_analysis_service_core/file_storage.py"
    ).read_text()
    markers = [
        "Mindscape" + "Store",
        "TimelineItems" + "Store",
        "Tasks" + "Store",
        "MultiAICollaboration" + "Service",
        "session" + "maker",
        "create" + "_engine",
        "Pg" + "Bouncer",
        "create" + "_task",
        "Queue" + "(",
        "Thread" + "(",
        "Process" + "(",
        "red" + "is",
        "poll" + "ing",
        "Event" + "Source",
        "Web" + "Socket",
        "web" + "socket",
        "set" + "Interval",
        "set" + "Timeout",
        "work" + "er",
    ]

    assert not [marker for marker in markers if marker in source]
