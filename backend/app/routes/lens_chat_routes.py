import asyncio
import logging

from fastapi import APIRouter, Body, HTTPException

from .lens_dependencies import _session_store, get_lens_resolver
from .lens_models import ChatRequest, ChatResponse

logger = logging.getLogger("backend.app.routes.lens")
router = APIRouter()


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
