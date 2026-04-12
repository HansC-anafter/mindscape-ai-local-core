"""
ig_create_project — Create an IG campaign project in the workspace.

Uses the existing ProjectManager to create a Project with type "ig_campaign".
Can be called by LLM tools or directly via API.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default flow_id for IG campaigns
IG_DEFAULT_FLOW_ID = "ig_campaign_flow"


async def run(
    workspace_id: str,
    title: str,
    project_type: str = "ig_campaign",
    flow_id: str = IG_DEFAULT_FLOW_ID,
    metadata: Optional[Dict[str, Any]] = None,
    reference_ids: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Create an IG campaign project.

    Args:
        workspace_id: Target workspace.
        title: Project title (e.g. "Spring Collection Campaign").
        project_type: Project type (default: ig_campaign).
        flow_id: Playbook flow ID (default: ig_campaign_flow).
        metadata: Additional project metadata.
        reference_ids: Optional list of reference IDs to attach.

    Returns:
        Dict with project details.
    """
    from app.services.project.project_manager import ProjectManager
    from app.services.mindscape_store import MindscapeStore

    try:
        store = MindscapeStore()
        pm = ProjectManager(store)

        initiator_user_id = kwargs.get("actor_id", "system")

        project = await pm.create_project(
            project_type=project_type,
            title=title,
            workspace_id=workspace_id,
            flow_id=flow_id,
            initiator_user_id=initiator_user_id,
            metadata=metadata or {},
        )

        project_id = project.id

        # Attach references if provided
        attached_refs = []
        if reference_ids:
            from capabilities.ig.services.workspace_storage import WorkspaceStorage
            from capabilities.ig.services.reference_index import ReferenceIndex
            from capabilities.ig.models.reference_metadata import ReferenceMetadata
            from capabilities.ig.tools.ig_analyze_reference import _find_metadata_file

            storage = WorkspaceStorage(workspace_id, "ig")
            refs_path = storage.get_references_path()
            index = ReferenceIndex(refs_path)

            for ref_id in reference_ids:
                try:
                    metadata_path = _find_metadata_file(refs_path, ref_id, index)
                    if metadata_path and metadata_path.exists():
                        meta = ReferenceMetadata.from_json(
                            metadata_path.read_text(encoding="utf-8")
                        )
                        meta.project_id = project_id
                        metadata_path.write_text(meta.to_json(), encoding="utf-8")
                        attached_refs.append(ref_id)
                except Exception as e:
                    logger.warning("[CreateProject] Failed to attach ref %s: %s", ref_id, e)

        logger.info(
            "[CreateProject] Created %s (type=%s, refs=%d)",
            project_id, project_type, len(attached_refs),
        )

        return {
            "status": "created",
            "project": project.model_dump(mode="json"),
            "attached_references": attached_refs,
        }

    except Exception as e:
        logger.error("[CreateProject] Failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
