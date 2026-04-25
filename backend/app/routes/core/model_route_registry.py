"""
Unified model-route registry for the Settings page.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.database.session import get_db_postgres as get_db
from backend.app.services.model_route_slot_registry import ModelRouteSlotRegistry

router = APIRouter(prefix="/api/v1/settings/model-route-registry", tags=["settings"])


@router.get("")
def get_model_route_registry(
    installed_only: bool = True,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    registry = ModelRouteSlotRegistry()
    return registry.collect_inventory(db=db, installed_only=installed_only)


@router.post("/reconcile")
def reconcile_model_route_registry(
    installed_only: bool = True,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    registry = ModelRouteSlotRegistry()
    pack_result = registry.reconcile_installed_pack_registrations(
        installed_only=installed_only
    )
    runtime_result = registry.reconcile_runtime_registrations(db=db)
    return {
        **pack_result,
        **runtime_result,
    }
