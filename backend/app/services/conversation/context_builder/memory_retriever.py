"""
Memory Retriever Module

Handles hierarchical memory retrieval from multiple scopes (Global/Workspace/Intent).
"""

import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


def _format_document_locations(locations: list[dict[str, Any]]) -> str:
    labels = []
    for location in locations:
        if location.get("page_or_slide") is not None:
            label = f"page/slide {location['page_or_slide']}"
        else:
            label = str(location.get("logical_position") or "logical location")
        bounds = location.get("bounds")
        if isinstance(bounds, dict):
            label += (
                f" bbox({bounds.get('x')},{bounds.get('y')},"
                f"{bounds.get('width')},{bounds.get('height')})"
            )
        if label not in labels:
            labels.append(label)
    return ", ".join(labels)


def _format_document_hit(hit: dict[str, Any]) -> Optional[str]:
    citation = hit.get("citation") or {}
    text = str(hit.get("retrievable_text") or "").strip()
    if not text or not citation.get("chunk_id"):
        return None
    source = str(hit.get("source_label") or citation.get("document_id") or "document")
    heading_path = " > ".join(hit.get("heading_path") or [])
    locations = _format_document_locations(citation.get("source_locations") or [])
    labels = [source]
    if heading_path:
        labels.append(heading_path)
    if locations:
        labels.append(locations)
    labels.append(f"chunk {citation['chunk_id']}")
    return f"- [{' | '.join(labels)}] {text[:500]}"


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

            # One canonical authorization-aware knowledge query covers local
            # folders, content vault, and uploaded documents.
            try:
                from backend.app.dependencies.auth import AuthContext
                from backend.app.services.knowledge_authorization.access_context_factory import (
                    RetrievalAccessContextFactory,
                )
                from backend.app.services.knowledge_retrieval import (
                    AuthorizationAwareKnowledgeRetrievalFacade,
                    KnowledgeRetrievalRequest,
                )

                retrieval_context = RetrievalAccessContextFactory().build(
                    AuthContext(
                        user_id=profile_id or "default-user",
                        tenant_id="local",
                        workspace_ids=[workspace_id],
                        is_cloud_mode=False,
                    ),
                    requested_workspace_ids=(workspace_id,),
                )
                knowledge_result = await (
                    AuthorizationAwareKnowledgeRetrievalFacade(
                    vector_service=search_service
                    ).search(
                        KnowledgeRetrievalRequest(
                            query=query,
                            access_context=retrieval_context,
                            scope_type="workspace",
                            scope_id=workspace_id,
                            top_k=10,
                            source_apps=(
                                "local_folder",
                                "content-vault",
                                "document_ingestion",
                            ),
                        )
                    )
                )
                formatted_documents = []
                formatted_local = []
                for hit in knowledge_result.hits:
                    if hit.source_app == "document_ingestion":
                        metadata = dict(hit.metadata)
                        formatted = _format_document_hit(
                            {
                                "source_label": metadata.get("file_name"),
                                "heading_path": metadata.get(
                                    "heading_path"
                                )
                                or [],
                                "retrievable_text": hit.content,
                                "citation": {
                                    "document_id": metadata.get(
                                        "document_id"
                                    ),
                                    "chunk_id": metadata.get("chunk_id"),
                                    "source_locations": metadata.get(
                                        "source_locations"
                                    )
                                    or [],
                                },
                            }
                        )
                        if formatted:
                            formatted_documents.append(formatted)
                    elif hit.content:
                        formatted_local.append(
                            f"- [{hit.metadata.get('file_name', hit.source_id)}] "
                            f"{hit.content[:500]}"
                        )
                if formatted_local:
                    formatted_parts.append("\n## Local Knowledge Base:")
                    formatted_parts.extend(formatted_local)
                if formatted_documents:
                    formatted_parts.append("\n## Workspace Documents:")
                    formatted_parts.extend(formatted_documents)
            except Exception as e:
                logger.error(
                    "Authorization-aware knowledge retrieval failed: %s",
                    e,
                    exc_info=True,
                )

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
