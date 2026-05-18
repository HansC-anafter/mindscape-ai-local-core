import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from .helpers import _safe_screenshot_basename

router = APIRouter()

@router.get("/execute/{execution_id}/debug/screenshot")
async def get_execution_debug_screenshot(
    execution_id: str, file: str = Query(..., description="Screenshot filename")
):
    """
    Serve execution debug screenshots saved under /app/data.
    UI passes only the basename (e.g. ig_debug_scroll_<exec>_..._dialog.png).
    """
    basename = _safe_screenshot_basename(file)
    path = os.path.join("/app/data", basename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )
