"""Atomic filesystem artifact seam for compiled document bundles."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class DocumentArtifactPointer:
    storage_key: str
    checksum: str
    byte_size: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "storage_key": self.storage_key,
            "checksum": self.checksum,
            "byte_size": self.byte_size,
            "media_type": "application/json",
        }


class DocumentIngestionArtifactStore:
    """Persist one complete bundle without exposing partial writes."""

    @staticmethod
    def path_for(file_path: str) -> Path:
        return Path(file_path).with_suffix(".document-ingestion.json")

    def write(
        self,
        *,
        file_path: str,
        compilation: Dict[str, Any],
        file_name: str,
        workspace_id: str,
    ) -> DocumentArtifactPointer:
        target = self.path_for(file_path)
        payload = {
            "workspace_id": workspace_id,
            "file_name": file_name,
            "source_path": file_path,
            "compilation": compilation,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        checksum = hashlib.sha256(encoded).hexdigest()

        if target.exists():
            current = target.read_bytes()
            if hashlib.sha256(current).hexdigest() == checksum:
                return DocumentArtifactPointer(
                    storage_key=str(target),
                    checksum=checksum,
                    byte_size=len(encoded),
                )

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, target)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()

        readback = target.read_bytes()
        if hashlib.sha256(readback).hexdigest() != checksum:
            raise RuntimeError("document_ingestion_artifact_readback_mismatch")
        return DocumentArtifactPointer(
            storage_key=str(target),
            checksum=checksum,
            byte_size=len(encoded),
        )


__all__ = ["DocumentArtifactPointer", "DocumentIngestionArtifactStore"]
