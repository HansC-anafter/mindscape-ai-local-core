"""MindscapeTool adapter for the one public knowledge_query contract."""

from __future__ import annotations

from typing import Any, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolInputSchema, ToolMetadata

from .contracts import KnowledgeQueryInput
from .query_service import KnowledgeQueryService


class KnowledgeQueryTool(MindscapeTool):
    def __init__(
        self,
        service: Optional[KnowledgeQueryService] = None,
    ) -> None:
        self._service = service
        super().__init__(
            ToolMetadata(
                name="knowledge_query",
                description=(
                    "Search authorized workspace or active-group knowledge "
                    "with explicit hybrid or graph retrieval modes."
                ),
                input_schema=ToolInputSchema(
                    type="object",
                    properties={
                        "operation": {
                            "type": "string",
                            "enum": [
                                "search",
                                "aggregate",
                                "fetch_by_citation",
                                "explain_coverage",
                            ],
                            "default": "search",
                        },
                        "query": {"type": "string"},
                        "retrieval_mode": {
                            "type": "string",
                            "enum": [
                                "hybrid",
                                "local_graph",
                                "multi_hop",
                                "global_graph",
                            ],
                            "default": "hybrid",
                        },
                        "scope": {
                            "type": "string",
                            "enum": ["workspace", "active_group"],
                            "default": "workspace",
                        },
                        "modality_filter": {
                            "type": "string",
                            "enum": ["text", "image", "video", "audio"],
                        },
                        "resource_filters": {
                            "type": "object",
                            "properties": {
                                "source_apps": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "owner_capabilities": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "source_kinds": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "object",
                                            "artifact",
                                            "memory",
                                            "document",
                                        ],
                                    },
                                },
                                "record_kinds": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                        "facet_predicates": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "key": {"type": "string"},
                                    "operator": {
                                        "type": "string",
                                        "enum": [
                                            "eq",
                                            "in",
                                            "gt",
                                            "gte",
                                            "lt",
                                            "lte",
                                        ],
                                    },
                                    "value": {},
                                },
                                "required": ["key", "operator", "value"],
                            },
                        },
                        "query_evidence_refs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "citation_id": {"type": "string"},
                                    "content_hash": {"type": "string"},
                                },
                                "required": [
                                    "citation_id",
                                    "content_hash",
                                ],
                            },
                        },
                        "citations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "citation_id": {"type": "string"},
                                    "content_hash": {"type": "string"},
                                },
                                "required": [
                                    "citation_id",
                                    "content_hash",
                                ],
                            },
                        },
                        "group_by": {"type": "string"},
                        "measure": {
                            "type": "string",
                            "enum": ["count", "distinct_count"],
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 20,
                            "default": 10,
                        },
                    },
                    required=[],
                ),
                category="data",
                source_type="builtin",
                provider="knowledge_foundation",
                danger_level="low",
            )
        )

    async def execute(self, **kwargs) -> Any:
        del kwargs
        raise ValueError("verified_tool_execution_context_required")

    async def execute_with_context(
        self,
        *,
        governance_context: Any = None,
        **kwargs,
    ) -> Any:
        if governance_context is None:
            raise ValueError("verified_tool_execution_context_required")
        request = KnowledgeQueryInput.model_validate(kwargs)
        service = self._service
        if service is None:
            service = KnowledgeQueryService()
        return await service.execute(
            request,
            governance_context=governance_context,
        )


__all__ = ["KnowledgeQueryTool"]
