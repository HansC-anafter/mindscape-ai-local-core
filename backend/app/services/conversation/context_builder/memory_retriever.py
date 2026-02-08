"""
Memory Retriever Module

Handles hierarchical memory retrieval from multiple scopes (Global/Workspace/Intent).
"""

import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """Retrieves memory context from multiple scopes using vector search"""

    def __init__(self, store: Any = None):
        """
        Initialize MemoryRetriever

        Args:
            store: MindscapeStore instance
        """
        self.store = store

    async def get_multi_scope_memory(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        intent_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get hierarchical memory context from multiple scopes (Global/Workspace/Intent)

        Args:
            workspace_id: Workspace ID
            message: Current user message
            profile_id: User profile ID
            intent_id: Optional active intent ID

        Returns:
            Formatted hierarchical memory context string or None
        """
        try:
            from backend.app.services.vector_search import VectorSearchService

            # Check if vector DB is available
            search_service = VectorSearchService()
            if not await search_service.check_connection():
                return None

            # Build query from current message + active intent titles
            query_parts = [message]

            if profile_id and self.store:
                try:
                    from backend.app.models.mindscape import IntentStatus

                    active_intents = self.store.list_intents(
                        profile_id=profile_id, status=IntentStatus.ACTIVE
                    )
                    if active_intents:
                        intent_titles = [intent.title for intent in active_intents[:3]]
                        query_parts.extend(intent_titles)
                        # Use first active intent if intent_id not provided
                        if not intent_id and active_intents:
                            intent_id = active_intents[0].id
                except Exception:
                    pass

            query = " ".join(query_parts)

            # Determine retrieval plan based on context
            scopes = ["global", "workspace"]
            top_k_per_scope = {"global": 3, "workspace": 8}

            # If intent_id provided, add intent scope
            if intent_id:
                scopes.append("intent")
                top_k_per_scope["intent"] = 8

            # Perform multi-scope search (wrapped to not block external docs search)
            multi_scope_results = {}
            try:
                logger.info(
                    f"Multi-scope memory search: query='{query[:100]}...', scopes={scopes}, top_k={top_k_per_scope}"
                )
                multi_scope_results = await search_service.multi_scope_search(
                    query=query,
                    user_id=profile_id or "default_user",
                    workspace_id=workspace_id,
                    intent_id=intent_id,
                    scopes=scopes,
                    top_k_per_scope=top_k_per_scope,
                )

                # Log results
                total_results = sum(
                    len(results) for results in multi_scope_results.values()
                )
                logger.info(
                    f"Multi-scope memory search results: total={total_results}, "
                    f"global={len(multi_scope_results.get('global', []))}, "
                    f"workspace={len(multi_scope_results.get('workspace', []))}, "
                    f"intent={len(multi_scope_results.get('intent', []))}"
                )
            except Exception as e:
                logger.warning(
                    f"Multi-scope search failed (continuing with external docs): {e}"
                )

            # Format results by scope
            formatted_parts = []

            # Global scope
            if "global" in multi_scope_results and multi_scope_results["global"]:
                formatted_parts.append("## Global User / System Profile:")
                for result in multi_scope_results["global"]:
                    content = result.get("content", "") or result.get("text", "")
                    if content:
                        formatted_parts.append(f"- {content[:300]}")

                # Update last_used_at for retrieved records
                record_ids = [
                    str(r.get("id", ""))
                    for r in multi_scope_results["global"]
                    if r.get("id")
                ]
                if record_ids:
                    await search_service.update_last_used_at(record_ids)

            # Workspace scope
            if "workspace" in multi_scope_results and multi_scope_results["workspace"]:
                formatted_parts.append("\n## This Workspace:")
                for result in multi_scope_results["workspace"]:
                    content = result.get("content", "") or result.get("text", "")
                    if content:
                        formatted_parts.append(f"- {content[:300]}")

                # Update last_used_at
                record_ids = [
                    str(r.get("id", ""))
                    for r in multi_scope_results["workspace"]
                    if r.get("id")
                ]
                if record_ids:
                    await search_service.update_last_used_at(record_ids)

            # Intent scope
            if "intent" in multi_scope_results and multi_scope_results["intent"]:
                formatted_parts.append("\n## Current Intent:")
                for result in multi_scope_results["intent"]:
                    content = result.get("content", "") or result.get("text", "")
                    if content:
                        formatted_parts.append(f"- {content[:300]}")

                # Update last_used_at
                record_ids = [
                    str(r.get("id", ""))
                    for r in multi_scope_results["intent"]
                    if r.get("id")
                ]
                if record_ids:
                    await search_service.update_last_used_at(record_ids)

            # External docs scope (RAG from local folders)
            try:
                external_results = await search_service.search_external_docs(
                    query=query,
                    source_apps=["local_folder"],
                    user_id="system",  # LocalFolderIndexer uses 'system' as user_id
                    top_k=5,
                )

                logger.info(
                    f"External docs search completed: found {len(external_results)} results"
                )

                # Filter results by workspace_id if available
                if external_results and workspace_id:
                    workspace_results = [
                        r
                        for r in external_results
                        if r.get("metadata", {}).get("workspace_id") == workspace_id
                    ]
                    if workspace_results:
                        formatted_parts.append("\n## Local Knowledge Base:")
                        for result in workspace_results:
                            content = result.get("content", "")
                            file_name = result.get("metadata", {}).get(
                                "file_name", "Unknown"
                            )
                            if content:
                                formatted_parts.append(
                                    f"- [{file_name}] {content[:500]}"
                                )
                        logger.info(
                            f"Injected {len(workspace_results)} local knowledge chunks into context"
                        )
            except Exception as e:
                logger.error(f"External docs search failed: {e}", exc_info=True)

            if formatted_parts:
                return "\n".join(formatted_parts)

            return None

        except Exception as e:
            logger.debug(f"Multi-scope memory retrieval failed: {e}")
            return None

    async def get_long_term_memory_context(
        self, workspace_id: str, message: str, profile_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Get long-term memory context from pgvector using semantic search
        (Legacy method - now uses multi-scope search)

        Args:
            workspace_id: Workspace ID
            message: Current user message
            profile_id: User profile ID

        Returns:
            Long-term memory context string or None
        """
        return await self.get_multi_scope_memory(
            workspace_id=workspace_id, message=message, profile_id=profile_id
        )
