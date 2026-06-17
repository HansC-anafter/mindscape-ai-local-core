import logging
import uuid
from typing import Any, Dict

from fastapi import Body, HTTPException

from .mcp_bridge_models import ProjectDetectRequest

logger = logging.getLogger("backend.app.routes.mcp_bridge")


async def project_detect(req: ProjectDetectRequest = Body(...)) -> Dict[str, Any]:
    """
    Detect whether a message suggests a new Project, then dedup and create.

    This is a governed operation that requires confirmation in tool_access_policy.
    Uses ProjectSuggestion model for schema alignment.
    """
    profile_id = req.profile_id or "default-user"

    try:
        from ..models.project import ProjectSuggestion
        from ..services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        store.ensure_default_profile()

        suggestion = ProjectSuggestion(
            mode=req.detected_project.mode,
            project_type=req.detected_project.project_type,
            project_title=req.detected_project.project_title,
            playbook_sequence=req.detected_project.playbook_sequence,
            initial_spec_md=req.detected_project.initial_spec_md,
            confidence=req.detected_project.confidence,
        )

        project_id = None
        created = False
        reason = None

        try:
            existing_projects = (
                store.list_projects(profile_id=profile_id)
                if hasattr(store, "list_projects")
                else []
            )
            title_lower = (suggestion.project_title or "").lower().strip()

            duplicate = None
            for proj in existing_projects:
                if hasattr(proj, "title") and proj.title.lower().strip() == title_lower:
                    duplicate = proj
                    break

            if duplicate:
                project_id = duplicate.id if hasattr(duplicate, "id") else None
                reason = f"Duplicate project found: {duplicate.title if hasattr(duplicate, 'title') else 'unknown'}"
            else:
                new_project_id = str(uuid.uuid4())
                try:
                    if hasattr(store, "create_project"):
                        result = store.create_project(
                            profile_id=profile_id,
                            title=suggestion.project_title or "Untitled Project",
                            description=suggestion.initial_spec_md or "",
                            project_type=suggestion.project_type,
                            metadata={
                                "mode": suggestion.mode,
                                "playbook_sequence": suggestion.playbook_sequence,
                                "confidence": suggestion.confidence,
                                "source": "mcp_bridge",
                                "workspace_id": req.workspace_id,
                            },
                        )
                        project_id = (
                            result.id if hasattr(result, "id") else new_project_id
                        )
                        created = True
                    else:
                        project_id = new_project_id
                        reason = (
                            "Project creation not yet supported \u2014 suggestion recorded"
                        )
                except Exception as e:
                    reason = f"Project creation failed: {str(e)}"

        except Exception as e:
            reason = f"Duplicate check failed: {str(e)}"

        return {
            "project_id": project_id,
            "created": created,
            "reason": reason,
            "suggestion": {
                "mode": suggestion.mode,
                "project_title": suggestion.project_title,
                "project_type": suggestion.project_type,
                "confidence": suggestion.confidence,
            },
        }

    except ImportError as e:
        logger.warning(f"Project detect \u2014 missing dependency: {e}")
        raise HTTPException(status_code=501, detail="Project models not available")
    except Exception as e:
        logger.error(f"project_detect failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Project detection failed: {str(e)}"
        )
