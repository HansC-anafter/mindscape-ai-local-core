import logging

logger = logging.getLogger(__name__)


async def refresh_tool_rag_corpus(
    *,
    log_prefix: str = "Tool RAG refresh",
    include_playbooks: bool = True,
    skip_when_index_exists: bool = False,
):
    """Ensure the tool embedding table exists and refresh the shared corpus."""
    from backend.app.services.tool_embedding_service import ToolEmbeddingService

    tes = ToolEmbeddingService()
    await tes.ensure_table()
    if skip_when_index_exists and await tes.has_existing_index():
        logger.info("%s skipped: existing tool embeddings present", log_prefix)
        return tes, 0, "existing_index_skip"
    try:
        indexed_count = await tes.ensure_indexed(include_playbooks=include_playbooks)
        mode = "ensure_indexed"
    except RuntimeError:
        indexed_count = await tes.index_all_tools(include_playbooks=include_playbooks)
        mode = "index_all_tools_fallback"

    logger.info("%s completed: indexed=%d mode=%s", log_prefix, indexed_count, mode)
    return tes, indexed_count, mode
