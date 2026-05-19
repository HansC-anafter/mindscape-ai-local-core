"""Executor action item build helpers."""

from typing import List


class ActionItemBuilderMixin:
    async def _build_action_items(
        self,
        decision: str,
        user_message: str,
        critic_notes: List[str],
        planner_proposals: List[str],
    ) -> List["ActionIntent"]:
        """Generate action items by running an executor turn and normalizing output."""
        from backend.app.services.orchestration.meeting.semantic_normalizer import (
            SemanticNormalizer,
        )

        executor_turn = await self._role_turn(
            "executor",
            round_num=max(1, self.session.round_count),
            user_message=user_message,
            decision=decision,
            planner_proposals=planner_proposals,
            critic_notes=critic_notes,
        )
        self._emit_turn(executor_turn)

        normalizer = SemanticNormalizer()
        workspace_id = getattr(self.session, "workspace_id", None)

        intents = normalizer.normalize(
            executor_output=executor_turn.content,
            decision=decision,
            workspace_id=workspace_id,
        )

        for intent in intents:
            if not intent.target_workspace_id:
                intent.target_workspace_id = workspace_id

        return intents
