import logging
from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/capabilities", tags=["capability-installation"])


@router.post("/install", status_code=status.HTTP_410_GONE)
async def install_capability_from_mindpack():
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="This endpoint has been deprecated. Use /api/v1/capability-packs/install-from-file instead."
    )
