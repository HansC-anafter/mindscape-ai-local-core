import asyncio

import pytest

from backend.app.models.task_ir import ArtifactReference
from backend.app.services.artifact_registry import (
    ArtifactNotFoundError,
    ArtifactRegistry,
    ArtifactStorageBackend,
    ArtifactStorageError,
    FilesystemStorageBackend,
    S3StorageBackend,
)


def run_async(coro):
    return asyncio.run(coro)


def test_public_facade_exports_legacy_classes(tmp_path):
    registry = ArtifactRegistry(base_path=str(tmp_path))

    assert registry.storage_backend == "filesystem"
    assert isinstance(registry.backend, FilesystemStorageBackend)
    assert issubclass(FilesystemStorageBackend, ArtifactStorageBackend)
    assert issubclass(S3StorageBackend, ArtifactStorageBackend)
    assert issubclass(ArtifactNotFoundError, ArtifactStorageError)


def test_filesystem_registry_roundtrips_text_json_and_binary_content(tmp_path):
    registry = ArtifactRegistry(base_path=str(tmp_path))

    text_artifact = run_async(
        registry.create_artifact_reference(
            id="task/phase/note.txt",
            type="text/plain",
            source="test:source",
            content="plain text",
            metadata={"kind": "note"},
        )
    )
    json_artifact = run_async(
        registry.create_artifact_reference(
            id="task/phase/payload.json",
            type="application/json",
            source="test:source",
            content={"ok": True},
            metadata={"kind": "payload"},
        )
    )
    binary_artifact = run_async(
        registry.create_artifact_reference(
            id="task/phase/blob",
            type="application/octet-stream",
            source="test:source",
            content=b"\xff\x00",
            metadata={"kind": "blob"},
        )
    )

    assert text_artifact.uri.startswith("file://")
    assert json_artifact.uri.startswith("file://")
    assert binary_artifact.uri.startswith("file://")
    assert run_async(registry.load_artifact_content(text_artifact.id)) == "plain text"
    assert run_async(registry.load_artifact_content(json_artifact.id)) == {"ok": True}
    assert run_async(registry.load_artifact_content(binary_artifact.id)) == b"\xff\x00"


def test_registry_filters_summary_and_delete_use_single_index(tmp_path):
    registry = ArtifactRegistry(base_path=str(tmp_path))
    artifact = run_async(
        registry.create_artifact_reference(
            id="task/phase/result.md",
            type="text/markdown",
            source="skill:test",
            content="result",
            metadata={"phase_id": "phase"},
        )
    )
    run_async(
        registry.create_artifact_reference(
            id="task/phase/raw.bin",
            type="application/octet-stream",
            source="playbook:test",
            content=b"\x01",
        )
    )

    assert registry.get_artifact(artifact.id) is artifact
    assert [item.id for item in registry.list_artifacts({"source": "skill:test"})] == [
        "task/phase/result.md"
    ]
    assert [item.id for item in registry.list_artifacts({"type": "text/"})] == [
        "task/phase/result.md"
    ]

    summary = run_async(registry.get_artifact_summary(artifact.id))
    assert summary["id"] == artifact.id
    assert summary["type"] == "text/markdown"
    assert summary["source"] == "skill:test"
    assert summary["metadata"] == {"phase_id": "phase"}
    assert summary["size"] == len("result")

    assert run_async(registry.delete_artifact(artifact.id)) is True
    assert registry.get_artifact(artifact.id) is None
    assert run_async(registry.delete_artifact(artifact.id)) is False


def test_invalid_filesystem_uri_and_missing_artifact_errors_are_preserved(tmp_path):
    backend = FilesystemStorageBackend(str(tmp_path))
    registry = ArtifactRegistry(base_path=str(tmp_path))

    with pytest.raises(ArtifactStorageError):
        run_async(backend.load_artifact("s3://bucket/key"))

    with pytest.raises(ArtifactNotFoundError):
        run_async(backend.load_artifact(f"file://{tmp_path / 'missing.txt'}"))

    missing = ArtifactReference(
        id="missing",
        type="text/plain",
        source="test:source",
        uri="",
    )
    with pytest.raises(ArtifactNotFoundError):
        run_async(registry.load_artifact_content(missing.id))
