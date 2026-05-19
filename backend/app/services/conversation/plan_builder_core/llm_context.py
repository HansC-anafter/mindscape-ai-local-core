"""Context assembly helpers for LLM plan generation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.services.capability_registry import get_registry
from backend.app.services.external_backend import (
    filter_mindscape_results,
    validate_mindscape_boundary,
)
from backend.app.services.pack_info_collector import PackInfoCollector

logger = logging.getLogger(__name__)

TEAM_MENTION_TERMS = [
    "\u5718\u968a",
    "\u56e2\u961f",
    "team",
    "\u80fd\u529b",
    "\u80fd\u529b\u5305",
]


async def build_workspace_context(
    builder: Any,
    context_builder: Any,
    *,
    message: str,
    workspace_id: str,
    profile_id: str,
    thread_id: Optional[str],
    max_tokens_for_planning: int,
) -> Tuple[Any, str]:
    """Build local planning context and return the workspace object."""
    workspace = None
    try:
        workspace = await builder.store.get_workspace(workspace_id)
    except Exception as exc:
        logger.debug("Could not get workspace object: %s", exc)

    workspace_context_budget = int(max_tokens_for_planning * 0.6)
    workspace_context = await context_builder.build_planning_context(
        workspace_id=workspace_id,
        message=message,
        profile_id=profile_id,
        workspace=workspace,
        target_tokens=workspace_context_budget,
        mode="planning",
        thread_id=thread_id,
        side_chain_mode="auto",
    )
    return workspace, workspace_context


async def build_project_context(
    builder: Any,
    *,
    project_id: Optional[str],
    workspace_id: str,
    project_assignment_decision: Optional[Dict[str, Any]],
) -> str:
    """Build optional project continuation context."""
    if not project_id or not project_assignment_decision:
        return ""

    try:
        from backend.app.services.project.project_manager import ProjectManager

        project_manager = ProjectManager(builder.store)
        project = await project_manager.get_project(
            project_id,
            workspace_id=workspace_id,
        )

        if not project:
            return ""

        recent_phases_str = await _build_recent_phase_context(builder, project_id)
        assignment_relation = project_assignment_decision.get("relation", "unknown")
        confidence = project_assignment_decision.get("confidence", 0.0)
        reasoning = project_assignment_decision.get("reasoning", "N/A")
        project_summary = (
            project.metadata.get("summary", "N/A") if project.metadata else "N/A"
        )

        return f"""

[PROJECT CONTEXT]

- Active project_id: {project_id}
- Project title: "{project.title}"
- Project type: {project.type}
- Project summary: {project_summary}
- This message is classified as: "{assignment_relation}", confidence = {confidence:.2f}
- Reasoning: {reasoning}
{recent_phases_str}

IMPORTANT: When interpreting the user's request, treat it as a continuation of the above Project, unless the user explicitly states they want to start a completely different work item.
"""
    except Exception as exc:
        logger.warning("Failed to build project context: %s", exc)
        return ""


async def _build_recent_phase_context(builder: Any, project_id: str) -> str:
    try:
        from backend.app.services.project.project_phase_manager import (
            ProjectPhaseManager,
        )

        phase_manager = ProjectPhaseManager(store=builder.store)
        recent_phases = await phase_manager.get_recent_phases(
            project_id=project_id,
            limit=3,
        )
        if not recent_phases:
            return ""

        phase_lines = [
            f"  {index + 1}. Phase {phase.kind}: {phase.summary[:80]}"
            for index, phase in enumerate(recent_phases)
        ]
        return "\n- Related previous phases:\n" + "\n".join(phase_lines)
    except Exception as exc:
        logger.debug("Failed to load recent phases for project %s: %s", project_id, exc)
        return ""


async def build_cloud_rag_context(
    builder: Any,
    *,
    workspace: Any,
    workspace_id: str,
    message: str,
    profile_id: str,
) -> Tuple[str, int, int]:
    """Build optional external context with a strict timeout."""
    cloud_rag_context = ""
    cloud_rag_snippet_limit = 5
    cloud_rag_char_limit = 200

    await builder._ensure_external_backend_loaded(profile_id)
    if not builder.external_backend:
        return cloud_rag_context, cloud_rag_snippet_limit, cloud_rag_char_limit

    try:
        workspace_context_dict = {
            "workspace_title": workspace.title if workspace else None,
            "workspace_description": workspace.description if workspace else None,
            "workspace_mode": workspace.mode if workspace else None,
            "conversation_history": [],
            "user_language": builder.default_locale,
        }

        cloud_result = await asyncio.wait_for(
            builder.external_backend.retrieve_context(
                workspace_id=workspace_id,
                message=message,
                workspace_context=workspace_context_dict,
                profile_id=profile_id,
                session_id=f"{workspace_id}_{profile_id}",
            ),
            timeout=1.5,
        )

        client_kind = "mindscape_edge"
        _, violations = validate_mindscape_boundary(
            client_kind=client_kind,
            memory_policy={"allow_chat_history_write": False},
            request_metadata={},
        )

        if violations:
            logger.warning("Boundary rule violations detected: %s", violations)

        if not cloud_result.get("success") or not cloud_result.get(
            "retrieved_snippets"
        ):
            return cloud_rag_context, cloud_rag_snippet_limit, cloud_rag_char_limit

        filtered_snippets = filter_mindscape_results(
            cloud_result.get("retrieved_snippets", []),
            client_kind,
        )
        if not filtered_snippets:
            return cloud_rag_context, cloud_rag_snippet_limit, cloud_rag_char_limit

        snippet_lines = [
            f"- {snippet.get('content', '')[:cloud_rag_char_limit]}..."
            for snippet in filtered_snippets[:cloud_rag_snippet_limit]
        ]
        cloud_rag_context = f"""

---

## Cloud Retrieved Knowledge (for reference only):
{chr(10).join(snippet_lines)}"""
        logger.info(
            "Cloud RAG retrieval completed: %s snippets, confidence=%.2f",
            len(filtered_snippets),
            cloud_result.get("retrieval_metadata", {}).get("confidence_score", 0),
        )
    except asyncio.TimeoutError:
        logger.warning("Cloud RAG retrieval timeout (1.5s), using local context only")
    except Exception as exc:
        logger.warning("Cloud RAG retrieval failed, using local context only: %s", exc)

    return cloud_rag_context, cloud_rag_snippet_limit, cloud_rag_char_limit


def collect_pack_context(
    builder: Any,
    *,
    workspace_id: str,
    message: str,
    available_packs: List[str],
) -> Tuple[PackInfoCollector, List[Dict[str, Any]], str, Set[str], str]:
    """Collect installed-pack descriptions and keyword hints."""
    pack_collector = PackInfoCollector(builder.store.db_path)
    installed_packs = pack_collector.get_all_installed_packs(workspace_id)
    installed_pack_ids = {pack["pack_id"] for pack in installed_packs}

    registry = get_registry()
    for pack_id in available_packs:
        if pack_id in installed_pack_ids:
            continue
        capability_info = registry.capabilities.get(pack_id)
        if not capability_info:
            continue
        manifest = capability_info.get("manifest", {})
        installed_packs.append(
            {
                "pack_id": pack_id,
                "display_name": manifest.get("display_name", pack_id),
                "description": manifest.get("description", ""),
                "side_effect_level": manifest.get("side_effect_level", "readonly"),
                "manifest": manifest,
                "metadata": {},
            }
        )

    filtered_packs = [
        pack for pack in installed_packs if pack.get("pack_id") in available_packs
    ]

    from backend.app.services.pack_suggester import PackSuggester

    pack_suggester = PackSuggester()
    detected_packs = pack_suggester.suggest_packs(message, available_packs)
    detected_pack_ids = (
        {suggestion["pack_id"] for suggestion in detected_packs}
        if detected_packs
        else set()
    )

    pack_descriptions = pack_collector.build_pack_description_list(filtered_packs)
    if not pack_descriptions or pack_descriptions == "No packs available":
        pack_descriptions = "\n".join(
            [
                f"- {pack_id}: Available pack (check registry for details)"
                for pack_id in available_packs
            ]
        )

    logger.info(
        "Built pack_descriptions for %s packs, available_packs=%s, pack_descriptions length=%s chars",
        len(filtered_packs),
        len(available_packs),
        len(pack_descriptions),
    )

    intent_hint = ""
    if detected_pack_ids:
        detected_pack_list = list(detected_pack_ids)
        intent_hint = (
            "\n\nKeyword-based suggestions: "
            f"{', '.join(detected_pack_list)} "
            "(for reference only, analyze full message content)"
        )

    return (
        pack_collector,
        filtered_packs,
        pack_descriptions,
        detected_pack_ids,
        intent_hint,
    )


def build_message_analysis_notes(message: str) -> str:
    """Build heuristic context notes for the planning prompt."""
    message_length = len(message)
    has_numbered_list = any(
        char.isdigit() and char in message for char in "123456789"
    )
    has_team_mentions = any(term in message for term in TEAM_MENTION_TERMS)

    context_notes = []
    if message_length > 500:
        context_notes.append(
            "Long message, may contain multiple capability or requirement descriptions"
        )
    if has_numbered_list:
        context_notes.append(
            "Message contains numbered list, may describe multiple different capabilities/teams"
        )
    if has_team_mentions:
        context_notes.append(
            "Message explicitly mentions 'team' or 'capability', need to identify all mentioned capabilities"
        )

    if not context_notes:
        return ""

    return "\n".join([f"- {note}" for note in context_notes])
