"""Private filesystem helpers for file analysis service."""

from .file_storage import (
    FileHashResult,
    calculate_file_hash_for_analysis,
    resolve_file_path_by_id,
    store_uploaded_file,
    write_analysis_sidecar,
)
from .document_ingestion_artifact_store import (
    DocumentArtifactPointer,
    DocumentIngestionArtifactStore,
)
from .document_ingestion_facade import (
    DocumentIngestionHostFacade,
    DocumentIngestionHostResult,
    build_event_analysis_projection,
)

__all__ = [
    "FileHashResult",
    "calculate_file_hash_for_analysis",
    "resolve_file_path_by_id",
    "store_uploaded_file",
    "write_analysis_sidecar",
    "DocumentArtifactPointer",
    "DocumentIngestionArtifactStore",
    "DocumentIngestionHostFacade",
    "DocumentIngestionHostResult",
    "build_event_analysis_projection",
]
