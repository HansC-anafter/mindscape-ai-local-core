"""
Filtered tools endpoint for server-side tool selection.

Combines Tool RAG filtering with safe defaults and deterministic ordering
to return a right-sized tool set for MCP gateway consumption.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, validator

from backend.app.models.tool_registry import RegisteredTool
from backend.app.services.tool_registry import ToolRegistryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])

# Hard cap to prevent payload bloat even if safe default grows
MAX_TOTAL_TOOLS = 50
MAX_PLAYBOOKS = 10
TASK_HINT_MAX_LEN = 500

# Safe default: readonly-only builtin tools (always returned)
# These are the actual metadata.name values from workspace_tools.py and filesystem_tools.py
SAFE_DEFAULT_TOOL_IDS = [
    "workspace_list_executions",
    "workspace_get_execution",
    "workspace_get_execution_steps",
    "workspace_query_database",
    "filesystem_list_files",
    "filesystem_read_file",
]


class FilteredToolsRequest(BaseModel):
    """Request body for filtered tools endpoint."""

    task_hint: str = Field(
        default="",
        description="Task prompt for RAG filtering (truncated to 500 chars)",
    )
    max_tools: int = Field(
        default=30,
        description="Max task-relevant tools (excludes safe default reservation)",
    )
    include_playbooks: bool = Field(default=True)
    enabled_only: bool = Field(default=True)

    @validator("max_tools", pre=True, always=True)
    def clamp_max_tools(cls, v):
        """Clamp to valid range instead of rejecting with 422."""
        try:
            v = int(v)
        except (TypeError, ValueError):
            return 30
        if v < 1:
            return 1
        if v > 100:
            return 100
        return v


class FilteredToolsMeta(BaseModel):
    """Observability metadata for the filtered response."""

    tool_count: int
    playbook_count: int
    rag_status: str  # hit | miss | error | skipped
    pack_codes: List[str] = Field(default_factory=list)
    safe_default_used: bool = False


class FilteredToolsResponse(BaseModel):
    """Response for filtered tools endpoint."""

    tools: List[RegisteredTool]
    playbooks: List[dict] = Field(default_factory=list)
    meta: FilteredToolsMeta


def _get_tool_registry() -> ToolRegistryService:
    """Initialize tool registry with extensions."""
    import os

    data_dir = os.getenv("DATA_DIR", "./data")
    registry = ToolRegistryService(data_dir=data_dir)
    try:
        from backend.app.extensions.console_kit import register_console_kit_tools

        register_console_kit_tools(registry)
    except ImportError:
        pass
    try:
        from backend.app.extensions.community import register_community_extensions

        register_community_extensions(registry)
    except ImportError:
        pass
    return registry


def _collect_all_tools(
    registry: ToolRegistryService,
    enabled_only: bool = True,
) -> List[RegisteredTool]:
    """Collect all tools from all sources: discovered + builtin + capability.

    Uses ToolListService.get_all_tools() to ensure builtin tools are included.
    """
    all_tools: List[RegisteredTool] = []
    existing_ids: set = set()

    # 1. Discovered tools from ToolRegistryService
    discovered = registry.get_tools(enabled_only=enabled_only)
    for t in discovered:
        all_tools.append(t)
        existing_ids.add(t.tool_id)

    # 2. Builtin + capability tools from ToolListService (includes workspace, filesystem, etc.)
    try:
        from backend.app.services.tool_list_service import ToolListService

        tool_list_svc = ToolListService()

        # Builtin tools
        builtin_tools = tool_list_svc._get_builtin_tools()
        for t_info in builtin_tools:
            if t_info.tool_id in existing_ids:
                continue
            if enabled_only and not t_info.enabled:
                continue
            all_tools.append(
                RegisteredTool(
                    tool_id=t_info.tool_id,
                    site_id="builtin",
                    provider="builtin",
                    display_name=t_info.name,
                    origin_capability_id="",
                    category=t_info.category,
                    description=t_info.description,
                    endpoint="",
                    methods=[],
                    danger_level="low",
                    input_schema=(
                        t_info.metadata.get("tool", {})
                        .to_dict()
                        .get("input_schema", {})
                        if hasattr(t_info.metadata.get("tool", {}), "to_dict")
                        else {}
                    ),
                    enabled=t_info.enabled,
                    read_only=True,
                    allowed_agent_roles=[],
                    side_effect_level="none",
                    scope="system",
                )
            )
            existing_ids.add(t_info.tool_id)

        # Capability tools
        cap_tools = tool_list_svc._get_capability_tools()
        for t_info in cap_tools:
            if t_info.tool_id in existing_ids:
                continue
            if enabled_only and not t_info.enabled:
                continue
            all_tools.append(
                RegisteredTool(
                    tool_id=t_info.tool_id,
                    site_id="capability",
                    provider="capability",
                    display_name=t_info.name,
                    origin_capability_id=t_info.tool_id,
                    category=t_info.category,
                    description=t_info.description,
                    endpoint="",
                    methods=[],
                    danger_level="low",
                    input_schema={},
                    enabled=t_info.enabled,
                    read_only=False,
                    allowed_agent_roles=[],
                    side_effect_level="none",
                    scope="system",
                )
            )
            existing_ids.add(t_info.tool_id)
    except Exception as e:
        logger.warning(f"Failed to load tools from ToolListService: {e}", exc_info=True)

    # 3. Fallback from installed manifests (if no capability tools found)
    try:
        if not any(t.provider == "capability" for t in all_tools):
            from backend.app.routes.core.tools.base import (
                _load_capability_tools_from_installed_manifests,
            )

            for t in _load_capability_tools_from_installed_manifests():
                if t.tool_id not in existing_ids:
                    all_tools.append(t)
                    existing_ids.add(t.tool_id)
    except Exception as e:
        logger.warning(f"Manifest fallback failed: {e}", exc_info=True)

    return all_tools


def _deterministic_sort_key(tool: RegisteredTool) -> tuple:
    """Sort key: source priority (builtin=0, discovered=1, capability=2) then tool_id ASC.

    Uses provider field: 'builtin' maps to 0, 'capability' maps to 2,
    everything else (generic_http, webhook, etc.) maps to 1 (discovered).
    """
    if tool.provider == "builtin":
        source_priority = 0
    elif tool.provider == "capability":
        source_priority = 2
    else:
        source_priority = 1  # discovered / generic_http / webhook / etc.
    cap_code = getattr(tool, "origin_capability_id", "") or ""
    # For capability tools, extract pack code prefix for grouping
    cap_prefix = cap_code.split(".")[0] if "." in cap_code else cap_code
    return (source_priority, cap_prefix, tool.tool_id)


@router.post("/filtered", response_model=FilteredToolsResponse)
async def list_filtered_tools(
    body: FilteredToolsRequest,
    registry: ToolRegistryService = Depends(_get_tool_registry),
):
    """Return a filtered, right-sized tool set for MCP gateway consumption.

    Filtering modes:
    - task_hint provided: RAG search, return safe defaults + top matches
    - task_hint empty: deterministic ordering, return safe defaults + top by priority

    Guarantees:
    - Always returns at least the safe default tools that exist in the registry
    - Never returns an empty tool set (safe defaults are always present)
    """
    task_hint = body.task_hint[:TASK_HINT_MAX_LEN].strip()
    all_tools = _collect_all_tools(registry, enabled_only=body.enabled_only)

    # Build lookup
    tool_by_id = {t.tool_id: t for t in all_tools}

    # 1. Safe default set (readonly builtins, always included)
    safe_defaults = [
        tool_by_id[tid] for tid in SAFE_DEFAULT_TOOL_IDS if tid in tool_by_id
    ]
    safe_default_ids = {t.tool_id for t in safe_defaults}

    if not safe_defaults:
        logger.warning(
            "No safe default tools found in registry. "
            f"Expected IDs: {SAFE_DEFAULT_TOOL_IDS}, "
            f"Available IDs (sample): {list(tool_by_id.keys())[:10]}"
        )

    rag_status = "skipped"
    pack_codes: List[str] = []
    safe_default_used = False

    if task_hint:
        # 2a. RAG filtering
        try:
            from backend.app.services.tool_embedding_service import (
                ToolEmbeddingService,
            )

            svc = ToolEmbeddingService()
            matches, rag_status = await svc.search(
                query=task_hint,
                top_k=body.max_tools,
                min_score=0.3,
            )

            if rag_status == "hit" and matches:
                rag_tool_ids = [m.tool_id for m in matches]
                pack_codes = sorted(
                    {m.capability_code for m in matches if m.capability_code}
                )
                # Union: safe defaults + RAG matches, deduped
                combined = dict.fromkeys(
                    [t.tool_id for t in safe_defaults] + rag_tool_ids
                )
                result_tools = [
                    tool_by_id[tid] for tid in combined if tid in tool_by_id
                ]
            else:
                # miss: fail-open to safe defaults only
                safe_default_used = True
                result_tools = list(safe_defaults)
        except Exception as e:
            logger.error(f"Filtered tools RAG failed: {e}", exc_info=True)
            rag_status = "error"
            safe_default_used = True
            result_tools = list(safe_defaults)
    else:
        # 2b. No task hint: deterministic ordering
        remaining = [t for t in all_tools if t.tool_id not in safe_default_ids]
        remaining.sort(key=_deterministic_sort_key)
        result_tools = list(safe_defaults) + remaining[: body.max_tools]

    # 3. Hard cap
    result_tools = result_tools[:MAX_TOTAL_TOOLS]

    # 4. Playbook filtering (synchronized with RAG pass)
    result_playbooks: List[dict] = []
    if body.include_playbooks:
        try:
            from backend.app.services.playbook_service import PlaybookService

            pb_service = PlaybookService()
            all_playbooks = await pb_service.list_playbooks()

            if pack_codes:
                # RAG hit: include system playbooks + those matching RAG pack codes
                pack_set = set(pack_codes)
                filtered = [
                    pb
                    for pb in all_playbooks
                    if pb.capability_code is None or pb.capability_code in pack_set
                ]
            else:
                # No RAG or miss/error: only system playbooks (no capability_code)
                filtered = [pb for pb in all_playbooks if pb.capability_code is None]

            # Cap and serialize
            filtered = filtered[:MAX_PLAYBOOKS]
            result_playbooks = [
                pb.dict(exclude_none=True) if hasattr(pb, "dict") else pb
                for pb in filtered
            ]
        except Exception as e:
            logger.warning(f"Playbook filtering failed: {e}", exc_info=True)

    meta = FilteredToolsMeta(
        tool_count=len(result_tools),
        playbook_count=len(result_playbooks),
        rag_status=rag_status,
        pack_codes=pack_codes,
        safe_default_used=safe_default_used,
    )

    logger.info(
        f"Filtered tools: {meta.tool_count} tools, "
        f"{meta.playbook_count} playbooks, rag={rag_status}, "
        f"packs={pack_codes}"
    )

    return FilteredToolsResponse(
        tools=result_tools,
        playbooks=result_playbooks,
        meta=meta,
    )
