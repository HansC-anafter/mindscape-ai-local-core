"""HTTP facade for installed Settings extension descriptors."""

import logging
import re
from typing import Annotated, Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database.session import get_db_postgres as get_db
from backend.app.routes.core.settings_extensions_core import projection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

_OWNER_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _validated_owner_query(
    capability_code: Optional[str],
    component_code: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Validate the optional paired exact-owner query contract."""
    if (capability_code is None) != (component_code is None):
        raise HTTPException(
            status_code=422,
            detail="capability_code and component_code must be provided together",
        )
    if capability_code is None or component_code is None:
        return None, None
    if not (
        _OWNER_IDENTIFIER_PATTERN.fullmatch(capability_code)
        and _OWNER_IDENTIFIER_PATTERN.fullmatch(component_code)
    ):
        raise HTTPException(
            status_code=422,
            detail="invalid settings extension owner identifier",
        )
    return capability_code, component_code


@router.get("/extensions")
async def get_settings_extensions(
    section: Annotated[
        Optional[str], Query(description="Filter by section")
    ] = None,
    workspace_id: Annotated[
        Optional[str],
        Query(description="Workspace ID for workspace-scoped settings panels"),
    ] = None,
    capability_code: Annotated[
        Optional[str],
        Query(
            max_length=128,
            description="Exact installed capability owner",
        ),
    ] = None,
    component_code: Annotated[
        Optional[str],
        Query(
            max_length=128,
            description="Exact installed component owner",
        ),
    ] = None,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Return filtered Settings extension descriptors from installed packs."""
    exact_capability, exact_component = _validated_owner_query(
        capability_code,
        component_code,
    )
    try:
        return projection.get_settings_extension_descriptors(
            section=section,
            workspace_id=workspace_id,
            capability_code=exact_capability,
            component_code=exact_component,
            db=db,
        )
    except Exception as exc:
        logger.error(
            "Failed to get settings extensions: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="settings_extensions_unavailable",
        ) from exc
