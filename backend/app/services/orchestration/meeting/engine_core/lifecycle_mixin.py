"""Top-level lifecycle method for MeetingEngine."""

from __future__ import annotations

from typing import Any, Optional


class MeetingEngineLifecycleMixin:
        async def run(
            self,
            user_message: str,
            handoff_in: Optional[Any] = None,
        ) -> MeetingResult:
            """Execute a bounded meeting and return generated minutes + action items.

            Orchestrates a 7-stage pipeline:
              S1 agenda + RAG → S2 contract → S3 deliberation →
              S4 action extraction → S5 policy gate → S6 dispatch → S7 finalize.

            Args:
                user_message: User message that triggered the meeting.
                handoff_in: Optional HandoffIn for governance context.
            """
            # Cache user_message for _build_tool_query_from_context()
            # MUST be set before _rag_tool_cache pre-fetch below.
            self._last_user_message = user_message

            # S1: Agenda decomposition + RAG pre-fetch
            await self._stage_agenda_and_rag(user_message)

            # S2: Playbook cache + RequestContract compile
            await self._stage_compile_contract(user_message, handoff_in=handoff_in)

            grounded_answer_result = await self._stage_grounded_knowledge_answer(
                handoff_in=handoff_in,
            )
            if grounded_answer_result is not None:
                return grounded_answer_result

            direct_result = await self._stage_explicit_playbook_direct_dispatch(
                user_message=user_message,
                handoff_in=handoff_in,
            )
            if direct_result is not None:
                return direct_result

            # S3: Multi-round deliberation
            decision, planner_proposals, critic_notes, converged = (
                await self._stage_deliberation(user_message)
            )

            # S4: Action intent extraction + null-tool gate
            action_intents, action_items = await self._stage_extract_actions(
                decision=decision,
                user_message=user_message,
                critic_notes=critic_notes,
                planner_proposals=planner_proposals,
            )

            # S5: Policy gate check + emit action items
            action_intents, action_items = self._stage_policy_gate_and_emit(
                action_items,
                action_intents,
            )

            # S6: Decompose + IR compile + DAG dispatch
            compiled_ir, dispatch_result = await self._stage_decompose_and_dispatch(
                decision=decision,
                action_intents=action_intents,
                action_items=action_items,
                handoff_in=handoff_in,
            )

            # S7: Finalize (minutes, supervisor, completion status)
            return self._stage_finalize(
                user_message=user_message,
                decision=decision,
                critic_notes=critic_notes,
                action_items=action_items,
                converged=converged,
                compiled_ir=compiled_ir,
                dispatch_result=dispatch_result,
            )
