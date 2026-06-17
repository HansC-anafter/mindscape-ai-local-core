import asyncio
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query

from ..models.changeset import ChangeSet, ChangeSetApplyRequest, ChangeSetCreateRequest
from ..models.graph import MindLensProfile
from ..models.lens_package import LensPresetPackage
from ..models.lens_receipt import LensReceipt
from .lens_dependencies import _session_store, get_graph_store, get_lens_resolver
from .lens_models import PresetSnapshotRequest

router = APIRouter()


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

    return {"node_id": node_id, "evidence": [e.model_dump() for e in evidence_list]}


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

    return drift_report.model_dump()
