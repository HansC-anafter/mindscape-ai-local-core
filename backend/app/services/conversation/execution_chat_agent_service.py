"""
Execution chat agent service.

Runs execution-scoped chat through the existing provider + tool loop stack.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.playbook import PlaybookMetadata
from backend.app.services.config_store import ConfigStore
from backend.app.services.conversation.execution_chat_conversation_manager import (
    ExecutionChatConversationManager,
)
from backend.app.services.conversation.execution_chat_config import (
    resolve_execution_chat_config,
)
from backend.app.services.conversation.execution_chat_service import (
    build_execution_chat_context,
    detect_language_from_text,
    persist_execution_chat_reply,
)
from backend.app.services.conversation.execution_chat_tool_catalog import (
    ExecutionChatToolCatalog,
)
from backend.app.services.conversation.workflow_tracker import WorkflowTracker
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook import PlaybookLLMProviderManager, PlaybookToolExecutor
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)


async def handle_execution_chat_agent_turn(
    *,
    execution_id: str,
    ctx: LocalDomainContext,
    user_message: str,
    user_message_id: str,
    playbook_metadata: Optional[PlaybookMetadata] = None,
    profile_id: str = "default-user",
) -> Dict[str, object]:
    """Handle one execution-chat turn using the tool-loop agent path."""
    store = MindscapeStore()
    tasks_store = TasksStore()
    task = tasks_store.get_task_by_execution_id(execution_id)

    execution_context_str = await build_execution_chat_context(
        execution_id=execution_id,
        ctx=ctx,
        current_message=user_message,
    )
    target_language = detect_language_from_text(user_message)
    chat_config = resolve_execution_chat_config(playbook_metadata)

    tool_catalog = ExecutionChatToolCatalog()
    tools = tool_catalog.resolve_tools(
        workspace_id=ctx.workspace_id,
        requested_groups=chat_config.tool_groups,
        user_message=user_message,
    )
    tool_prompt = tool_catalog.format_tools_for_prompt(tools)

    conv_manager = ExecutionChatConversationManager(
        execution_id=execution_id,
        workspace_id=ctx.workspace_id,
        project_id=getattr(task, "project_id", None) if task else None,
        execution_context=execution_context_str,
        tool_prompt=tool_prompt,
        discussion_agent=chat_config.discussion_agent,
        target_language=target_language,
        store=store,
    )
    conv_manager.add_user_message(user_message)

    llm_provider_manager = PlaybookLLMProviderManager(ConfigStore())
    llm_manager = llm_provider_manager.get_llm_manager(profile_id)
    provider = llm_provider_manager.get_llm_provider(llm_manager)
    model_name = llm_provider_manager.get_model_name()

    messages = await conv_manager.get_messages_for_llm()
    assistant_response = await provider.chat_completion(
        messages,
        model=model_name if model_name else None,
        max_tokens=8192,
    )
    conv_manager.add_assistant_message(assistant_response)

    tool_executor = PlaybookToolExecutor(store, WorkflowTracker(store))
    tool_executor.execution_context.update(
        {
            "workspace_id": ctx.workspace_id,
            "execution_id": execution_id,
            "trace_id": execution_id,
            "message_id": user_message_id,
        }
    )
    if task and getattr(task, "project_id", None):
        tool_executor.execution_context["project_id"] = task.project_id

    final_response, used_tools = await tool_executor.execute_tool_loop(
        conv_manager=conv_manager,
        assistant_response=assistant_response,
        execution_id=execution_id,
        profile_id=profile_id,
        provider=provider,
        model_name=model_name,
        workspace_id=ctx.workspace_id,
        max_iterations=chat_config.max_tool_iterations,
    )

    return persist_execution_chat_reply(
        execution_id=execution_id,
        ctx=ctx,
        assistant_content=final_response,
        playbook_metadata=playbook_metadata,
        message_type="question",
        extra_metadata={
            "execution_chat_mode": "agent",
            "user_message_id": user_message_id,
            "used_tools": used_tools,
            "tool_groups": list(chat_config.tool_groups),
        },
    )
