"""
ig_list_references — Query pinned references with filters.

Reads from _index.json for efficient querying.
Supports filtering by source_handle, tags, collection.
Excludes soft-deleted entries by default.
"""

import logging
from typing import Any, Dict, List, Optional

from capabilities.ig.services.reference_index import ReferenceIndex
from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


async def ig_list_references(
    workspace_id: str,
    source_handle: Optional[str] = None,
    tags: Optional[List[str]] = None,
    collection: Optional[str] = None,
    project_id: Optional[str] = None,
    include_deleted: bool = False,
    analysis_profile: Optional[str] = None,
    schema_version: Optional[str] = None,
    has_analysis: Optional[bool] = None,
    **kwargs,
) -> Dict[str, Any]:
    """List pinned references from workspace with optional filters.

    Args:
        workspace_id: Target workspace.
        source_handle: Filter by Instagram handle.
        tags: Filter by tags (any match).
        collection: Filter by collection name.
        include_deleted: Whether to include soft-deleted references.

    Returns:
        Dict with references list and total count.
    """
    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    results = index.query(
        source_handle=source_handle,
        tags=tags,
        collection=collection,
        project_id=project_id,
        include_deleted=include_deleted,
        analysis_profile=analysis_profile,
        schema_version=schema_version,
        has_analysis=has_analysis,
    )

    return {
        "status": "success",
        "references": results,
        "total": len(results),
        "filters": {
            "source_handle": source_handle,
            "tags": tags,
            "collection": collection,
            "include_deleted": include_deleted,
        },
    }
