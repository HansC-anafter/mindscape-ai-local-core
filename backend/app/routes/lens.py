"""
Lens API routes for Mind-Lens unified implementation.

Provides APIs for:
- Effective Lens resolution
- Workspace Override management
- Session Override management
"""

import asyncio
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path, Query, Body
from pydantic import BaseModel

from ..models.graph import (
    LensNodeState,
    WorkspaceLensOverride,
    MindLensProfile,
    MindLensProfileCreate,
)
from ..models.lens_kernel import EffectiveLens
from ..models.lens_receipt import LensReceipt
from ..models.changeset import (
    ChangeSet,
    ChangeSetCreateRequest,
    ChangeSetApplyRequest,
    ApplyTarget,
)
from ..models.lens_package import LensPresetPackage
from ..models.preset_diff import PresetDiff
from ..services.stores.graph_store import GraphStore
from ..services.lens.effective_lens_resolver import EffectiveLensResolver
from ..services.lens.session_override_store import InMemorySessionStore
from ..services.lens.preset_diff_service import PresetDiffService
from ..core.deps import get_current_profile_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mindscape/lens", tags=["lens"])


# Initialize stores
def get_graph_store() -> GraphStore:
    """Get graph store instance"""
    return GraphStore()


# Global session store instance (in-memory for now)
_session_store = InMemorySessionStore()


def get_lens_resolver() -> EffectiveLensResolver:
    """Get effective lens resolver instance"""
    graph_store = get_graph_store()
    return EffectiveLensResolver(graph_store, _session_store)


# ============================================================================
# Preset Diff API
# ============================================================================


@router.get("/profiles/{preset_id}/diff", response_model=PresetDiff)
async def get_preset_diff(
    preset_id: str = Path(..., description="要比较的 Preset ID"),
    compare_with: str = Query(..., description="比较基准 Preset ID"),
):
    """
    获取两个 Preset 之间的差异

    比较 preset_id 和 compare_with 两个 Preset 的节点状态差异
    """
    graph_store = get_graph_store()
    diff_service = PresetDiffService(graph_store)

    try:
        diff = await asyncio.to_thread(diff_service.compare, preset_id, compare_with)
        return diff
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Request/Response Models
# ============================================================================


class SetWorkspaceOverrideRequest(BaseModel):
    """Request to set workspace override"""

    state: LensNodeState


class SetSessionOverrideRequest(BaseModel):
    """Request to set session override"""

    state: LensNodeState


class ChatRequest(BaseModel):
    """Request for Mind-Lens chat"""

    mode: str  # 'mirror' | 'experiment' | 'writeback'
    message: str
    profile_id: str
    workspace_id: Optional[str] = None
    session_id: Optional[str] = None
    effective_lens: Optional[dict] = None
    selected_node_ids: Optional[List[str]] = None


class ChatResponse(BaseModel):
    """Response from Mind-Lens chat"""

    response: str
    mode: str
    suggestions: Optional[List[str]] = None


class PresetSnapshotRequest(BaseModel):
    """Request to create a preset snapshot"""

    profile_id: str
    name: str
    workspace_id: Optional[str] = None
    session_id: Optional[str] = None
    description: Optional[str] = None


# ============================================================================
# Effective Lens API
# ============================================================================


@router.get("/effective-lens", response_model=EffectiveLens)
async def get_effective_lens(
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
    session_id: Optional[str] = Query(None, description="Session ID"),
    profile_id: str = Query(..., description="Profile ID"),
) -> EffectiveLens:
    """Get effective lens with three-layer stacking"""
    resolver = get_lens_resolver()
    try:
        effective_lens = await asyncio.to_thread(
            resolver.resolve,
            profile_id=profile_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        return effective_lens
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Workspace Override API
# ============================================================================


@router.get(
    "/workspaces/{workspace_id}/lens-overrides",
    response_model=List[WorkspaceLensOverride],
)
async def get_workspace_overrides(
    workspace_id: str = Path(..., description="Workspace ID")
) -> List[WorkspaceLensOverride]:
    """Get all workspace lens overrides"""
    store = get_graph_store()
    overrides = await asyncio.to_thread(store.get_workspace_overrides, workspace_id)
    return overrides


@router.put(
    "/workspaces/{workspace_id}/lens-overrides/{node_id}",
    response_model=WorkspaceLensOverride,
)
async def set_workspace_override(
    workspace_id: str = Path(..., description="Workspace ID"),
    node_id: str = Path(..., description="Node ID"),
    request: SetWorkspaceOverrideRequest = Body(...),
) -> WorkspaceLensOverride:
    """Set workspace lens override for a node"""
    store = get_graph_store()
    override = await asyncio.to_thread(
        store.set_workspace_override, workspace_id, node_id, request.state
    )
    return override


@router.delete("/workspaces/{workspace_id}/lens-overrides/{node_id}", status_code=204)
async def remove_workspace_override(
    workspace_id: str = Path(..., description="Workspace ID"),
    node_id: str = Path(..., description="Node ID"),
):
    """Remove workspace lens override for a node"""
    store = get_graph_store()
    await asyncio.to_thread(store.remove_workspace_override, workspace_id, node_id)


# ============================================================================
# Session Override API
# ============================================================================


@router.get("/session/{session_id}/overrides")
async def get_session_overrides(
    session_id: str = Path(..., description="Session ID")
) -> dict:
    """Get all session overrides"""
    overrides = _session_store.get(session_id)
    return {"overrides": overrides or {}}


@router.put("/session/{session_id}/overrides/{node_id}")
async def set_session_override(
    session_id: str = Path(..., description="Session ID"),
    node_id: str = Path(..., description="Node ID"),
    request: SetSessionOverrideRequest = Body(...),
) -> dict:
    """Set session override for a node"""
    _session_store.set(session_id, node_id, request.state)
    return {"node_id": node_id, "state": request.state}


@router.delete("/session/{session_id}/overrides", status_code=204)
async def clear_session_overrides(
    session_id: str = Path(..., description="Session ID")
):
    """Clear all session overrides"""
    _session_store.clear(session_id)


# ============================================================================
# Lens Receipt API
# ============================================================================


@router.get("/receipts/{execution_id}", response_model=LensReceipt)
async def get_lens_receipt(
    execution_id: str = Path(..., description="Execution ID")
) -> LensReceipt:
    """Get lens receipt for an execution"""
    from ..services.lens.lens_receipt_store import LensReceiptStore

    receipt_store = LensReceiptStore()
    receipt = await asyncio.to_thread(receipt_store.get_by_execution_id, execution_id)

    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return receipt


# ============================================================================
# Preview API
# ============================================================================


@router.post("/preview")
async def generate_preview(
    profile_id: str = Query(..., description="Profile ID"),
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
    session_id: Optional[str] = Query(None, description="Session ID"),
    request: dict = Body(...),
) -> dict:
    """Generate preview with Base vs Lens comparison"""
    from ..services.lens.preview_service import PreviewService

    resolver = get_lens_resolver()
    preview_service = PreviewService(resolver)

    effective_lens = await asyncio.to_thread(
        resolver.resolve,
        profile_id=profile_id,
        workspace_id=workspace_id,
        session_id=session_id,
    )

    result = await asyncio.to_thread(
        preview_service.generate_preview,
        effective_lens=effective_lens,
        input_text=request.get("input_text", ""),
        preview_type=request.get("preview_type", "rewrite"),
    )

    return {
        "base_output": result.base_output,
        "lens_output": result.lens_output,
        "diff_summary": result.diff_summary,
        "triggered_nodes": [
            {
                "node_id": n.node_id,
                "node_label": n.node_label,
                "state": n.state,
                "effective_scope": n.effective_scope,
            }
            for n in result.triggered_nodes
        ],
    }


# ============================================================================
# ChangeSet API
# ============================================================================


@router.post("/changesets", response_model=ChangeSet)
async def create_changeset(request: ChangeSetCreateRequest = Body(...)) -> ChangeSet:
    """
    Create changeset with server-side diff

    Flow:
    1. Get baseline (workspace override or global preset)
    2. Get current (session overrides applied)
    3. Diff (session vs baseline) → changes[]
    """
    from ..services.lens.changeset_service import ChangeSetService

    resolver = get_lens_resolver()
    store = get_graph_store()
    change_set_service = ChangeSetService(store, resolver, _session_store)

    changeset = await asyncio.to_thread(
        change_set_service.create_changeset,
        profile_id=request.profile_id,
        session_id=request.session_id,
        workspace_id=request.workspace_id,
    )

    return changeset


@router.post("/changesets/apply", status_code=204)
async def apply_changeset(request: ChangeSetApplyRequest = Body(...)):
    """Apply changeset to target scope"""
    from ..services.lens.changeset_service import ChangeSetService

    resolver = get_lens_resolver()
    store = get_graph_store()
    change_set_service = ChangeSetService(store, resolver, _session_store)

    await asyncio.to_thread(
        change_set_service.apply_changeset,
        changeset=request.changeset,
        apply_to=request.apply_to,
        target_workspace_id=request.target_workspace_id,
    )


# ============================================================================
# Preset Snapshot API
# ============================================================================


@router.post("/profiles/snapshot", response_model=MindLensProfile)
async def create_preset_snapshot(
    request: PresetSnapshotRequest = Body(...),
) -> MindLensProfile:
    """
    Create a new Preset from current effective lens state

    This creates a snapshot of the current effective lens (including workspace
    and session overrides) as a new Preset.
    """
    resolver = get_lens_resolver()
    store = get_graph_store()

    # Get current effective lens
    effective_lens = await asyncio.to_thread(
        resolver.resolve,
        profile_id=request.profile_id,
        workspace_id=request.workspace_id,
        session_id=request.session_id,
    )

    # Create new preset
    from ..models.graph import MindLensProfileCreate

    preset_create = MindLensProfileCreate(
        name=request.name,
        description=request.description
        or f"Snapshot from {effective_lens.global_preset_name}",
        is_default=False,
    )

    new_preset = await asyncio.to_thread(
        store.create_lens_profile, preset_create, request.profile_id
    )

    # Copy node states from effective lens to new preset
    for node in effective_lens.nodes:
        # Use the method that creates or updates lens profile node
        from ..models.graph import LensNodeState

        # Convert string state to enum if needed
        if isinstance(node.state, str):
            state = LensNodeState(node.state)
        else:
            state = node.state

        # Use the GraphStore upsert method
        await asyncio.to_thread(
            store.upsert_lens_profile_node,
            preset_id=new_preset.id,
            node_id=node.node_id,
            state=state,
        )

    return new_preset


# ============================================================================
# Package API
# ============================================================================


@router.post("/packages", response_model=LensPresetPackage)
async def create_package(
    preset_id: str = Query(..., description="Preset ID"),
    version: str = Query("1.0.0", description="Package version"),
) -> LensPresetPackage:
    """Create a preset package"""
    from ..services.lens.preset_package_service import PresetPackageService

    store = get_graph_store()
    package_service = PresetPackageService(store)
    package = await asyncio.to_thread(
        package_service.create_package, preset_id, version
    )
    return package


@router.post("/packages/install", response_model=MindLensProfile)
async def install_package(package_data: dict = Body(...)) -> MindLensProfile:
    """Install a preset package"""
    from ..services.lens.preset_package_service import PresetPackageService

    store = get_graph_store()
    package_service = PresetPackageService(store)
    profile = await asyncio.to_thread(package_service.install_package, package_data)
    return profile


# ============================================================================
# Evidence API
# ============================================================================


@router.get("/evidence/nodes/{node_id}")
async def get_node_evidence(
    node_id: str = Path(..., description="Node ID"),
    profile_id: str = Query(..., description="Profile ID"),
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
    limit: int = Query(10, description="Limit"),
) -> dict:
    """Get evidence for a node"""
    from ..services.lens.evidence_service import EvidenceService

    evidence_service = EvidenceService()
    evidence_list = await asyncio.to_thread(
        evidence_service.get_node_evidence,
        node_id=node_id,
        workspace_id=workspace_id,
        limit=limit,
    )

    return {"node_id": node_id, "evidence": [e.dict() for e in evidence_list]}


@router.get("/evidence/drift")
async def get_drift_report(
    profile_id: str = Query(..., description="Profile ID"),
    days: int = Query(30, description="Days to analyze"),
) -> dict:
    """Get lens drift report"""
    from ..services.lens.evidence_service import EvidenceService

    evidence_service = EvidenceService()
    drift_report = await asyncio.to_thread(
        evidence_service.compute_drift, profile_id=profile_id, days=days
    )

    return drift_report.dict()


# ============================================================================
# Chat API
# ============================================================================


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest = Body(...)) -> ChatResponse:
    """
    Mind-Lens Chat API

    Three modes:
    - mirror: 看見自己 - 總結 Preset、查看節點例子
    - experiment: 調色實驗 - 實驗性調整並預覽效果
    - writeback: 寫回 Workspace - 將實驗結果寫回
    """
    from ..services.lens.mindscape_chat_service import MindscapeChatService

    resolver = get_lens_resolver()
    chat_service = MindscapeChatService(resolver, _session_store)

    try:
        response = await asyncio.to_thread(
            chat_service.handle_message,
            mode=request.mode,
            message=request.message,
            profile_id=request.profile_id,
            workspace_id=request.workspace_id,
            session_id=request.session_id,
            effective_lens=request.effective_lens,
            selected_node_ids=request.selected_node_ids or [],
        )
        return ChatResponse(response=response, mode=request.mode)
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
