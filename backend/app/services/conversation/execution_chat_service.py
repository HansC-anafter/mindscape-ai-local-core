"""
Execution Chat Service

Handles LLM reply generation for execution-scoped chat.
Aligned with Port architecture using ExecutionContext.
"""

import logging
import uuid
import re
from typing import Dict, Any, Optional
from datetime import datetime

from ...core.execution_context import ExecutionContext
from ...models.workspace import ExecutionSession, PlaybookExecutionStep, ExecutionChatMessage
from ...models.playbook import PlaybookMetadata
from ...models.mindscape import MindEvent, EventType, EventActor
from ...services.mindscape_store import MindscapeStore
from ...services.stores.tasks_store import TasksStore
from ...capabilities.core_llm.services.generate import run as generate_text
from ...services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)


def detect_language_from_text(text: str) -> str:
    """
    Detect language from text content

    Returns:
        Language code: "zh-TW" if contains Chinese characters, "en" otherwise
    """
    if not text:
        return "en"

    # Check for Chinese characters (CJK Unified Ideographs)
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
    if chinese_pattern.search(text):
        return "zh-TW"

    return "en"


async def build_execution_chat_context(
    execution_id: str,
    ctx: ExecutionContext,
    current_message: str
) -> str:
    """
    Build Execution Chat context string (for LLM prompt)

    Note: Method name is `build_execution_chat_context` to avoid conflict with `ExecutionContext` class.

    Args:
        execution_id: Execution ID
        ctx: ExecutionContext (contains workspace_id, actor_id, tags)
        current_message: Current user message

    Returns:
        Context string for LLM prompt
    """
    context_parts = []
    store = MindscapeStore()
    tasks_store = TasksStore(db_path=store.db_path)

    try:
        # Get execution (Task) by execution_id
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            logger.warning(f"Execution {execution_id} not found")
            return f"## Execution Context\nExecution ID: {execution_id}\nWorkspace ID: {ctx.workspace_id}\n\n## User Message\n{current_message}"

        # Build ExecutionSession view model
        execution = ExecutionSession.from_task(task)

        # Execution basic info
        context_parts.append("## Current Execution Context")
        context_parts.append(f"Execution ID: {execution_id}")
        context_parts.append(f"Workspace ID: {ctx.workspace_id}")
        context_parts.append(f"Playbook: {execution.playbook_code}")
        context_parts.append(f"Status: {execution.task.status if execution.task else 'unknown'}")
        context_parts.append(f"Current Step: {execution.current_step_index + 1}/{execution.total_steps}")

        # Get execution steps (MindEvents with PLAYBOOK_STEP)
        # Use get_events_by_workspace and filter by event_type and payload.execution_id
        all_events = store.get_events_by_workspace(
            workspace_id=ctx.workspace_id,
            limit=200
        )
        events = [
            e for e in all_events
            if e.event_type == EventType.PLAYBOOK_STEP
            and isinstance(e.payload, dict)
            and e.payload.get("execution_id") == execution_id
        ]

        steps = []
        for event in events:
            try:
                step = PlaybookExecutionStep.from_mind_event(event)
                steps.append(step)
            except Exception as e:
                logger.warning(f"Failed to create ExecutionStep from event {event.id}: {e}")

        if steps:
            context_parts.append(f"\n## Execution Steps ({len(steps)} steps)")
            for step in sorted(steps, key=lambda s: s.step_index):
                context_parts.append(f"Step {step.step_index + 1}: {step.step_name or 'Unnamed'}")
                context_parts.append(f"  Status: {step.status}")
                if step.agent_type:
                    context_parts.append(f"  Agent: {step.agent_type}")
                if step.log_summary:
                    context_parts.append(f"  Summary: {step.log_summary}")

        # Get stage results (if available)
        # TODO: Implement get_execution_stage_results when StageResult table is ready
        # stage_results = get_execution_stage_results(execution_id, workspace_id=ctx.workspace_id)
        # if stage_results:
        #     context_parts.append(f"\n## Stage Results ({len(stage_results)} results)")
        #     for result in stage_results:
        #         context_parts.append(f"- {result.stage_name}: {result.result_type}")

        # Get chat history (recent 10 messages)
        # Use get_events_by_workspace and filter by event_type and entity_ids
        all_chat_events = store.get_events_by_workspace(
            workspace_id=ctx.workspace_id,
            limit=200
        )
        chat_events = [
            e for e in all_chat_events
            if e.event_type == EventType.EXECUTION_CHAT
            and execution_id in (e.entity_ids or [])
        ][:10]  # Limit to 10 most recent

        if chat_events:
            context_parts.append(f"\n## Recent Conversation")
            for event in sorted(chat_events, key=lambda e: e.timestamp):
                try:
                    msg = ExecutionChatMessage.from_mind_event(event)
                    context_parts.append(f"{msg.role}: {msg.content}")
                except Exception as e:
                    logger.warning(f"Failed to create ExecutionChatMessage from event {event.id}: {e}")

    except Exception as e:
        logger.error(f"Failed to build execution chat context: {e}", exc_info=True)
        context_parts.append(f"\n## Error\nFailed to load execution context: {str(e)}")

    return "\n".join(context_parts)


def build_execution_chat_prompt(
    user_message: str,
    execution_context: str,
    execution_id: str,
    playbook_metadata: Optional[PlaybookMetadata] = None,
    discussion_agent: Optional[str] = None
) -> str:
    """
    Build LLM prompt for Execution Chat

    Includes hard boundaries:
    - Only discuss this specific execution
    - Can propose but cannot secretly change flow
    - Only affects this run, not Playbook blueprint

    Args:
        user_message: User message
        execution_context: Context string from build_execution_chat_context
        execution_id: Execution ID
        playbook_metadata: Optional playbook metadata
        discussion_agent: Optional agent persona

    Returns:
        LLM prompt string
    """
    agent_persona = discussion_agent or (playbook_metadata.discussion_agent if playbook_metadata else None) or "assistant"

    prompt = f"""You are a {agent_persona} agent helping the driver (user) optimize and refine the current playbook execution.

## Execution Context
{execution_context}

## Your Role - Playbook Optimization Assistant
You are here to help optimize THIS specific execution (execution_id: {execution_id}) by analyzing the execution and providing suggestions for improving the playbook (playbook.md and playbook.json).

You can:

1. **Analyze the current execution**: Understand what's happening, identify issues, explain steps, detect problems
2. **Generate playbook revision suggestions**: Provide specific suggestions for improving playbook.md (SOP content) and playbook.json (execution steps)
3. **Suggest execution parameter adjustments**: Recommend specific values, constraints, or instructions for this run
4. **Answer questions**: Explain execution status, steps, errors, or design decisions

## Critical Boundaries (MUST FOLLOW)
1. **Scope**: Focus ONLY on this specific execution (execution_id: {execution_id}). Do NOT discuss other executions or unrelated topics.
2. **Playbook Revision Focus**: Your main role is to suggest improvements to the playbook itself (playbook.md and playbook.json), which the user can review and apply in the "Revision Draft" area.
3. **Structured Suggestions**: When suggesting playbook improvements, be specific about:
   - What should be changed in playbook.md (SOP steps, descriptions, examples)
   - What should be changed in playbook.json (execution steps, tool calls, dependencies)
   - Why these changes will help
4. **Natural Language**: Express suggestions naturally and clearly. Focus on explaining what needs to be improved and how.

## Response Style Guidelines
- **Analyze first**: Start by explaining what you observe about the current execution
- **Suggest playbook improvements**: Provide specific suggestions for playbook.md and playbook.json changes
- **Be concrete**: Give specific examples of what should be changed
- **Explain reasoning**: Help the user understand WHY your suggestions will help
- **Focus on structure**: When suggesting playbook.json changes, describe the step structure, tool calls, and dependencies

## Example Good Response Format

"I notice Step 1 has been running for a while. Here are my suggestions to improve the playbook:

**For playbook.md:**
- Add a clearer description for Step 1: 'Collect and normalize all input notes, grouping by source (meeting/article/idea) and date. Output a structured list ready for clustering.'

**For playbook.json:**
- Add a preprocessing step before the main clustering: a 'normalize_notes' step that groups notes by source and date
- Add input constraints: limit processing to last 7 days or 20 most recent notes to prevent timeouts
- Break Step 1 into smaller sub-steps with clear dependencies

These changes will make the execution more reliable and easier to debug."

## User Message
{user_message}

## Your Response
Analyze the execution, identify issues, and provide specific suggestions for improving playbook.md and playbook.json. Focus on structural improvements that will make the playbook more reliable and effective."""

    return prompt


async def generate_execution_chat_reply(
    execution_id: str,
    ctx: ExecutionContext,
    user_message: str,
    user_message_id: str,
    playbook_metadata: Optional[PlaybookMetadata] = None
) -> Dict[str, Any]:
    """
    Asynchronously generate LLM reply for Execution Chat

    Implementation:
    - Uses existing generate_text (from capabilities.core_llm.services.generate)
    - Uses build_execution_chat_context method
    - Async processing, does not block POST request
    - Aligned with Port architecture using ExecutionContext

    Args:
        execution_id: Execution ID
        ctx: ExecutionContext (contains workspace_id, actor_id, tags)
        user_message: User message content
        user_message_id: User message event ID
        playbook_metadata: Optional playbook metadata

    Returns:
        Dict with assistant message and event
    """
    try:
        store = MindscapeStore()

        # Build context
        execution_context_str = await build_execution_chat_context(
            execution_id=execution_id,
            ctx=ctx,
            current_message=user_message
        )

        # Build prompt
        prompt = build_execution_chat_prompt(
            user_message=user_message,
            execution_context=execution_context_str,
            execution_id=execution_id,
            playbook_metadata=playbook_metadata,
            discussion_agent=playbook_metadata.discussion_agent if playbook_metadata else None
        )

        # Detect language from user message
        target_language = detect_language_from_text(user_message)

        # Call LLM
        # Note: generate_text (run) function gets model from system settings internally
        result = await generate_text(
            prompt=prompt,
            workspace_id=ctx.workspace_id,
            target_language=target_language
        )

        # Extract text from result dict
        assistant_content = result.get("text", "")

        # Create assistant message MindEvent (add profile_id)
        assistant_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.SYSTEM,
            channel="workspace",
            profile_id=ctx.actor_id,  # ⭐ Add profile_id (required by MindEvent)
            workspace_id=ctx.workspace_id,
            event_type=EventType.EXECUTION_CHAT,
            payload={
                "execution_id": execution_id,
                "step_id": None,  # Can be set based on current step
                "role": "assistant",
                "speaker": playbook_metadata.discussion_agent if playbook_metadata and playbook_metadata.discussion_agent else "assistant",
                "content": assistant_content,
                "message_type": "question",  # Or determine based on content
            },
            entity_ids=[execution_id],
            metadata={
                "is_execution_chat": True
            }
        )

        # Save and return
        store.create_event(assistant_event)

        assistant_message = ExecutionChatMessage.from_mind_event(assistant_event)

        return {
            "message": assistant_message,
            "event": assistant_event
        }

    except Exception as e:
        logger.error(f"Failed to generate execution chat reply: {e}", exc_info=True)
        raise

