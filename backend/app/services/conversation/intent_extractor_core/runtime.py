"""Runtime orchestration for intent extraction."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

from backend.app.models.workspace import TimelineItem
from backend.app.services.conversation.intent_extractor_core.auto_execution import (
    create_auto_execution_timeline_item,
    should_auto_execute_intent_extraction,
)
from backend.app.services.conversation.intent_extractor_core.intent_tags import (
    create_candidate_intent_tags,
)
from backend.app.services.conversation.intent_extractor_core.suggestion_task import (
    create_suggestion_task,
)

logger = logging.getLogger(__name__)


async def extract_and_create_timeline_item(
    *,
    extractor: Any,
    ctx: Any,
    message: str,
    message_id: str,
    locale: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> Optional[TimelineItem]:
    enable_llm_extractor = (
        os.getenv("ENABLE_LLM_INTENT_EXTRACTOR", "true").lower() == "true"
    )
    if not enable_llm_extractor:
        logger.info("LLM intent extractor is disabled via ENABLE_LLM_INTENT_EXTRACTOR")
        print(
            "LLM intent extractor is disabled via ENABLE_LLM_INTENT_EXTRACTOR",
            file=sys.stderr,
        )
        return None

    try:
        logger.info(
            "Intent extractor: Starting extraction for workspace %s, message: %s...",
            ctx.workspace_id,
            message[:100],
        )
        print(
            f"Intent extractor: Starting extraction for workspace {ctx.workspace_id}, message: {message[:100]}...",
            file=sys.stderr,
        )

        context_str = ""
        try:
            context_str = await extractor.context_builder.build_qa_context(
                workspace_id=ctx.workspace_id, message=message, hours=24
            )
            logger.info(
                "Intent extractor: Built context (%s chars)",
                len(context_str),
            )
        except Exception as ctx_err:
            logger.warning(
                "Intent extractor: failed to build context: %s",
                ctx_err,
                exc_info=True,
            )

        logger.info("Intent extractor: Calling intent registry with message and context")
        resolution_result = await extractor.intent_registry.resolve_intent(
            user_input=message,
            ctx=ctx,
            context=context_str,
            locale=locale or extractor.default_locale,
        )
        logger.info(
            "Intent extractor: Registry returned: %s intents, %s themes",
            resolution_result.intents,
            resolution_result.themes,
        )
        print(
            "Intent extractor: Registry returned: "
            f"{len(resolution_result.intents)} intents, "
            f"{len(resolution_result.themes)} themes",
            file=sys.stderr,
        )

        intents_list = resolution_result.intents
        themes_list = resolution_result.themes

        logger.info(
            "Intent extractor: Parsed %s intents, %s themes",
            len(intents_list),
            len(themes_list),
        )
        print(
            f"Intent extractor: Parsed {len(intents_list)} intents, {len(themes_list)} themes",
            file=sys.stderr,
        )

        intent_tag_ids = create_candidate_intent_tags(
            intent_tags_store=extractor.intent_tags_store,
            ctx=ctx,
            message_id=message_id,
            intents=intents_list,
            confidence=resolution_result.confidence,
            llm_analysis=resolution_result.llm_analysis,
        )

        if not intents_list and not themes_list:
            logger.info(
                "Intent extractor: No intents or themes extracted, returning None"
            )
            print(
                "Intent extractor: No intents or themes extracted, returning None",
                file=sys.stderr,
            )
            return None

        from backend.app.services.stores.postgres.workspaces_store import (
            PostgresWorkspacesStore,
        )

        workspaces_store = PostgresWorkspacesStore()
        workspace = await workspaces_store.get_workspace(ctx.workspace_id)
        auto_exec_config = (
            workspace.playbook_auto_execution_config if workspace else None
        )

        should_auto_execute = should_auto_execute_intent_extraction(
            auto_exec_config,
            resolution_result.confidence,
        )
        if should_auto_execute:
            return create_auto_execution_timeline_item(
                extractor=extractor,
                ctx=ctx,
                message_id=message_id,
                intents_list=intents_list,
                themes_list=themes_list,
                intent_tag_ids=intent_tag_ids,
                thread_id=thread_id,
            )

        create_suggestion_task(
            ctx=ctx,
            message_id=message_id,
            intents_list=intents_list,
            themes_list=themes_list,
            llm_analysis=resolution_result.llm_analysis,
        )
        return None

    except Exception as exc:
        logger.warning(
            "Intent extractor failed (falling back to rule-based): %s",
            exc,
            exc_info=True,
        )
        return None
