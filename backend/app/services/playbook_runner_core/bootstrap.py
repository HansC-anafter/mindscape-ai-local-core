"""Bootstrap helpers for playbook runner startup."""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


async def resolve_locale(
    *,
    inputs: Optional[Dict[str, Any]],
    workspace_id: Optional[str],
    get_workspace_fn: Callable[[str], Awaitable[Any]],
    default_locale: str = "zh-TW",
) -> str:
    """Resolve execution locale from inputs, workspace, or default."""
    locale = inputs.get("locale") if inputs else None
    if not locale and workspace_id:
        try:
            workspace = await get_workspace_fn(workspace_id)
            locale = workspace.default_locale if workspace else None
        except Exception:
            pass
    return locale or default_locale


async def load_playbook_bundle(
    *,
    playbook_code: str,
    workspace_id: Optional[str],
    inputs: Optional[Dict[str, Any]],
    get_workspace_fn: Callable[[str], Awaitable[Any]],
    get_playbook_fn: Callable[..., Awaitable[Any]],
    load_playbook_json_fn: Callable[[str], Any],
) -> Tuple[Any, Any, str, int]:
    """Load playbook metadata, playbook.json, locale, and total step count."""
    locale = await resolve_locale(
        inputs=inputs,
        workspace_id=workspace_id,
        get_workspace_fn=get_workspace_fn,
    )
    playbook = await get_playbook_fn(
        playbook_code=playbook_code,
        locale=locale,
        workspace_id=workspace_id,
    )
    if not playbook:
        raise ValueError(f"Playbook not found: {playbook_code}")

    playbook_json = load_playbook_json_fn(playbook_code)

    total_steps = 1
    if playbook_json and getattr(playbook_json, "steps", None):
        total_steps = len(playbook_json.steps)
        logger.info(
            "PlaybookRunner: Playbook %s has JSON with %s steps",
            playbook_code,
            total_steps,
        )
    else:
        logger.info(
            "PlaybookRunner: Playbook %s using conversation mode (no JSON)",
            playbook_code,
        )

    return playbook, playbook_json, locale, total_steps


def resolve_variant(
    *,
    registry: Any,
    playbook_code: str,
    variant_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Resolve an optional personalized playbook variant."""
    if not variant_id:
        return None

    variant = registry.get_variant(playbook_code, variant_id)
    if not variant:
        logger.warning("Variant '%s' not found for %s", variant_id, playbook_code)
    return variant


async def resolve_project_execution_context(
    *,
    project_id: Optional[str],
    inputs: Optional[Dict[str, Any]],
    workspace_id: Optional[str],
    get_project_fn: Callable[..., Awaitable[Any]],
    get_unified_sandbox_fn: Callable[..., Awaitable[Tuple[Optional[str], Optional[Any]]]],
    get_legacy_sandbox_path_fn: Callable[..., Awaitable[Optional[Any]]],
) -> Dict[str, Any]:
    """Resolve project object and sandbox compatibility paths for playbook execution."""
    normalized_project_id = project_id
    project_obj = None
    project_sandbox_path = None
    sandbox_id = None

    if not normalized_project_id and inputs and inputs.get("project_id"):
        candidate_project_id = inputs.get("project_id")
        candidate_project = await get_project_fn(
            project_id=candidate_project_id,
            workspace_id=workspace_id,
        )
        if candidate_project:
            normalized_project_id = candidate_project_id
            project_obj = candidate_project
            logger.info(
                "Playbook execution in Project mode (from inputs): %s",
                normalized_project_id,
            )

    if not normalized_project_id:
        return {
            "project_id": None,
            "project_obj": None,
            "project_sandbox_path": None,
            "sandbox_id": None,
        }

    if project_obj is None:
        project_obj = await get_project_fn(
            project_id=normalized_project_id,
            workspace_id=workspace_id,
        )

    if project_obj:
        logger.info("Playbook execution in Project mode: %s", normalized_project_id)
        try:
            sandbox_id, project_sandbox_path = await get_unified_sandbox_fn(
                project_id=normalized_project_id,
                workspace_id=workspace_id,
            )
            logger.info(
                "Using unified sandbox %s for project %s: %s",
                sandbox_id,
                normalized_project_id,
                project_sandbox_path,
            )
        except Exception as exc:
            logger.warning(
                "Failed to get unified sandbox, falling back to legacy: %s",
                exc,
            )
            try:
                project_sandbox_path = await get_legacy_sandbox_path_fn(
                    project_id=normalized_project_id,
                    workspace_id=workspace_id,
                )
                logger.info(
                    "Using legacy project sandbox: %s",
                    project_sandbox_path,
                )
            except Exception as legacy_exc:
                logger.warning("Failed to get project sandbox: %s", legacy_exc)
    else:
        logger.warning(
            "Project %s not found, continuing without Project mode",
            normalized_project_id,
        )
        normalized_project_id = None

    return {
        "project_id": normalized_project_id,
        "project_obj": project_obj,
        "project_sandbox_path": project_sandbox_path,
        "sandbox_id": sandbox_id,
    }
