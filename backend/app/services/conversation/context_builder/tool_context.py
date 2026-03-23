import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


async def build_tool_context_section(
    *,
    message: str,
    workspace_id: Optional[str],
) -> List[str]:
    """Build the shared tool-context section for QA and planning prompts."""
    try:
        from backend.app.models.workspace_resource_binding import ResourceType
        from backend.app.services.stores.workspace_resource_binding_store import (
            WorkspaceResourceBindingStore,
        )
        from backend.app.services.tool_rag import retrieve_relevant_tools

        tool_matches = await retrieve_relevant_tools(
            message,
            top_k=12,
            workspace_id=workspace_id,
        )

        if workspace_id:
            store = WorkspaceResourceBindingStore()
            bindings = store.list_bindings_by_workspace(
                workspace_id,
                resource_type=ResourceType.TOOL,
            )
            if bindings:
                rag_ids = {tool["tool_id"] for tool in tool_matches}
                for binding in bindings:
                    if binding.resource_id not in rag_ids:
                        tool_matches.append(
                            {
                                "tool_id": binding.resource_id,
                                "display_name": (binding.overrides or {}).get(
                                    "display_name",
                                    binding.resource_id,
                                ),
                            }
                        )

        if not tool_matches:
            return []

        tool_lines = "\n".join(
            f"- {tool['tool_id']}: {tool['display_name']}"
            for tool in tool_matches
        )
        logger.info("Injected %d RAG tools into prompt context", len(tool_matches))
        return [
            "\n## Available Tools (relevant to your request):",
            tool_lines,
        ]
    except Exception as exc:
        logger.debug("Tool RAG context injection failed: %s", exc)
        return []
