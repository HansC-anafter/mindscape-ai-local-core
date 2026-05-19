"""QA context assembly for ContextBuilder."""

import logging
from typing import Any, Optional, Tuple

from ..tool_context import build_tool_context_section

logger = logging.getLogger(__name__)


class QAContextMixin:
    """Build QA context strings from workspace runtime data."""

    async def build_qa_context(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        workspace: Optional[Any] = None,
        project_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        hours: int = 24,
        side_chain_mode: str = "off",
    ) -> str:
        """
        Build context string for QA mode LLM prompts.

        Args:
            workspace_id: Workspace ID.
            message: User message.
            profile_id: Optional profile ID for retrieving intents.
            workspace: Optional workspace object for metadata.
            project_id: Optional project ID for project-specific context.
            thread_id: Optional thread ID for thread-specific references.
            hours: Hours to look back for context.
            side_chain_mode: Side-chain policy.

        Returns:
            Context string to inject into LLM prompt.
        """
        context_parts = []
        governance_packet = await self._load_governance_context_packet(
            workspace_id=workspace_id,
            profile_id=profile_id,
            workspace=workspace,
            project_id=project_id,
        )

        if governance_packet:
            compiled_packet = self.memory_packet_compiler.compile_for_context(
                governance_packet
            )
            if compiled_packet:
                context_parts.append("\n## Governance Context Packet:")
                context_parts.append(compiled_packet)
                logger.info(
                    "Injected governance packet with route=%s",
                    self.memory_packet_compiler.build_route_plan(governance_packet),
                )

        if not governance_packet:
            context_parts.extend(
                await self._build_layered_memory_context(
                    workspace_id, profile_id, project_id
                )
            )

        context_parts.extend(
            self._build_workspace_metadata_context(workspace, workspace_id)
        )
        context_parts.extend(await self._build_active_intents_context(profile_id))
        context_parts.extend(
            await self._build_current_tasks_context(workspace_id, thread_id)
        )
        context_parts.extend(await self._build_recent_files_context(workspace_id))
        context_parts.extend(
            await self._build_timeline_context(workspace_id, thread_id)
        )
        context_parts.extend(
            await self._build_thread_references_context(workspace_id, thread_id)
        )

        thread_context_count = 0
        try:
            if self.store:
                max_events = self.preset["MAX_EVENTS_FOR_QUERY"]
                max_messages = self.preset["MAX_HISTORY_MESSAGES"]
                max_chars = self.preset["MAX_MESSAGE_CHARS"]

                conversation_context, summary_context = (
                    await self.conversation_history_manager.get_conversation_history_with_summary(
                        workspace_id=workspace_id,
                        max_events=max_events,
                        max_messages=max_messages,
                        max_chars=max_chars,
                        thread_id=thread_id,
                    )
                )

                if summary_context:
                    context_parts.append("\n## Conversation Summary (Earlier Context):")
                    context_parts.append(summary_context)
                    logger.info("Injected conversation summary into QA context")

                if conversation_context:
                    context_parts.append("\n## Recent Conversation:")
                    context_parts.extend(conversation_context)
                    thread_context_count = len(conversation_context)
                    logger.info(
                        f"Injected {len(conversation_context)} conversation messages into QA context"
                    )
        except Exception as e:
            logger.error(f"Failed to get conversation context: {e}", exc_info=True)

        try:
            if self.side_chain_handler.should_include_side_chain(
                side_chain_mode=side_chain_mode,
                thread_id=thread_id,
                message=message,
                thread_context_count=thread_context_count,
            ):
                side_chain_parts = (
                    self.side_chain_handler.build_workspace_side_chain_context(
                        workspace_id=workspace_id
                    )
                )
                if side_chain_parts:
                    context_parts.extend(side_chain_parts)
                    logger.info("Injected workspace side-chain into QA context")
        except Exception as e:
            logger.warning(f"Failed to build workspace side-chain context: {e}")

        try:
            long_term_memory = await self.memory_retriever.get_long_term_memory_context(
                workspace_id=workspace_id, message=message, profile_id=profile_id
            )
            if long_term_memory:
                if governance_packet:
                    context_parts.append("\n## Semantic Memory Hits:")
                    context_parts.append(long_term_memory)
                    logger.info(
                        "Injected semantic memory tail into QA context (route=%s)",
                        self.memory_packet_compiler.build_route_plan(
                            governance_packet, include_semantic_hits=True
                        ),
                    )
                else:
                    context_parts.append("\n## Long-term Knowledge:")
                    context_parts.append(long_term_memory)
                    logger.info("Injected long-term memory context into QA context")
        except Exception as e:
            logger.debug(f"Failed to get long-term memory context: {e}")

        context_parts.extend(
            await build_tool_context_section(
                message=message,
                workspace_id=workspace_id,
            )
        )

        return "\n".join(context_parts) if context_parts else ""

    async def build_qa_context_with_token_count(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        workspace: Optional[Any] = None,
        thread_id: Optional[str] = None,
        hours: int = 24,
        side_chain_mode: str = "off",
    ) -> Tuple[str, int]:
        """
        Build context string and return token count.

        Returns:
            Tuple of context string and token count.
        """
        context = await self.build_qa_context(
            workspace_id=workspace_id,
            message=message,
            profile_id=profile_id,
            workspace=workspace,
            thread_id=thread_id,
            hours=hours,
            side_chain_mode=side_chain_mode,
        )
        enhanced_prompt = self.build_enhanced_prompt(message=message, context=context)
        token_count = self.estimate_token_count(enhanced_prompt, self.model_name)
        return context, token_count
