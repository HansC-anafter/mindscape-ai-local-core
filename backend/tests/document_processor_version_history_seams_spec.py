import hashlib
import json
from pathlib import Path

from backend.app.services import document_processor
from backend.app.services.document_processor import (
    _sanitize_document_id,
    calculate_content_hash,
    chunk_document_to_objects,
    get_document_version_history,
    get_latest_document_version,
    track_document_version,
)


def test_public_document_processor_reexports_version_history_helpers():
    assert document_processor.track_document_version is track_document_version
    assert document_processor.get_document_version_history is get_document_version_history
    assert document_processor.get_latest_document_version is get_latest_document_version
    assert document_processor.calculate_content_hash is calculate_content_hash
    assert callable(chunk_document_to_objects)


def test_track_document_version_persists_and_trims_history(tmp_path):
    storage_dir = str(tmp_path)

    for index in range(55):
        track_document_version(
            document_id="doc-1",
            content=f"content-{index}",
            metadata={"index": index},
            storage_dir=storage_dir,
        )

    history_path = tmp_path / "doc-1.json"
    history_payload = json.loads(history_path.read_text())
    versions = get_document_version_history("doc-1", storage_dir=storage_dir)

    assert history_payload["document_id"] == "doc-1"
    assert "last_updated" in history_payload
    assert len(versions) == 50
    assert versions[0]["metadata"] == {"index": 5}
    assert versions[-1]["metadata"] == {"index": 54}
    assert versions[-1]["content_hash"] == hashlib.sha256(
        b"content-54"
    ).hexdigest()


def test_sanitize_document_id_preserves_safe_names_and_hashes_unsafe_names():
    assert _sanitize_document_id("safe.doc-1") == "safe.doc-1"

    unsafe = "folder/doc:1"
    expected_hash = hashlib.sha256(unsafe.encode("utf-8")).hexdigest()[:16]
    assert _sanitize_document_id(unsafe) == f"folder_doc_1_{expected_hash}"


def test_get_latest_document_version_returns_last_entry(tmp_path):
    storage_dir = str(tmp_path)
    first = track_document_version("doc-2", "first", storage_dir=storage_dir)
    second = track_document_version("doc-2", "second", storage_dir=storage_dir)

    assert first["content_hash"] == hashlib.sha256(b"first").hexdigest()
    assert get_latest_document_version("doc-2", storage_dir=storage_dir) == second
    assert get_latest_document_version("missing", storage_dir=storage_dir) is None


def test_document_processor_files_stay_below_line_gate():
    repo_root = Path(__file__).resolve().parents[2]
    paths = [
        repo_root / "backend/app/services/document_processor.py",
        repo_root / "backend/app/services/document_processor_core/__init__.py",
        repo_root / "backend/app/services/document_processor_core/version_history.py",
        repo_root / "backend/tests/document_processor_version_history_seams_spec.py",
    ]

    for path in paths:
        assert len(path.read_text().splitlines()) <= 500, path


def test_document_processor_core_has_no_background_resource_markers():
    repo_root = Path(__file__).resolve().parents[2]
    source = (
        repo_root / "backend/app/services/document_processor_core/version_history.py"
    ).read_text()
    markers = [
        "Mindscape" + "Store",
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
