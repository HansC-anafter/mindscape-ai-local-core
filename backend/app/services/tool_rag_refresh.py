import logging

logger = logging.getLogger(__name__)


async def refresh_tool_rag_corpus(
    *,
    log_prefix: str = "Tool RAG refresh",
):
    """Ensure the tool embedding table exists and refresh the shared corpus."""
    from backend.app.services.tool_embedding_service import ToolEmbeddingService

    tes = ToolEmbeddingService()
    await tes.ensure_table()
    try:
        indexed_count = await tes.ensure_indexed()
        mode = "ensure_indexed"
    except RuntimeError:
        indexed_count = await tes.index_all_tools()
        mode = "index_all_tools_fallback"

    logger.info("%s completed: indexed=%d mode=%s", log_prefix, indexed_count, mode)
    return tes, indexed_count, mode
