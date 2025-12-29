"""
Execution Context Builder

Builds execution context for tasks from playbook context and execution results.
"""

import logging
from typing import Dict, Any, Optional

from ...core.domain_context import LocalDomainContext

logger = logging.getLogger(__name__)


class ExecutionContextBuilder:
    """
    Builds execution context for tasks

    Responsibilities:
    - Build execution context from playbook context
    - Calculate total_steps from playbook or execution result
    - Extract intent information from playbook context
    - Handle trigger source determination
    """

    def __init__(self, store, tasks_store, playbook_resolver):
        """
        Initialize ExecutionContextBuilder

        Args:
            store: MindscapeStore instance
            tasks_store: TasksStore instance
            playbook_resolver: PlaybookResolver instance
        """
        self.store = store
        self.tasks_store = tasks_store
        self.playbook_resolver = playbook_resolver

    async def build(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        ctx: LocalDomainContext,
        execution_result: Optional[Dict[str, Any]] = None,
        execution_mode: str = "conversation",
    ) -> Dict[str, Any]:
        """
        Build execution context for task

        Args:
            playbook_code: Playbook code
            playbook_context: Playbook context
            ctx: Execution context
            execution_result: Optional execution result
            execution_mode: Execution mode (workflow/conversation)

        Returns:
            Execution context dict
        """
        trigger_source = self._determine_trigger_source(playbook_context)

        origin_intent_id, origin_intent_label, intent_confidence = (
            self._extract_intent_info(playbook_context)
        )

        total_steps = await self._calculate_total_steps(
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            ctx=ctx,
            execution_result=execution_result,
            execution_mode=execution_mode,
        )

        default_cluster = playbook_context.get("default_cluster", "local_mcp")

        execution_context = {
            "playbook_code": playbook_code,
            "playbook_version": playbook_context.get("playbook_version"),
            "trigger_source": trigger_source,
            "current_step_index": 0,
            "total_steps": total_steps,
            "paused_at": None,
            "origin_intent_id": origin_intent_id,
            "origin_intent_label": origin_intent_label,
            "intent_confidence": intent_confidence,
            "origin_suggestion_id": playbook_context.get("suggestion_id"),
            "initiator_user_id": ctx.actor_id,
            "failure_type": None,
            "failure_reason": None,
            "default_cluster": default_cluster,
        }

        if ctx.tags:
            execution_context.update(ctx.tags)

        return execution_context

    def _determine_trigger_source(self, playbook_context: Dict[str, Any]) -> str:
        """
        Determine trigger source from playbook context

        Args:
            playbook_context: Playbook context

        Returns:
            Trigger source string (manual/suggestion/auto)
        """
        if playbook_context.get("suggestion_id"):
            return "suggestion"
        elif playbook_context.get("auto_execute"):
            return "auto"
        return "manual"

    def _extract_intent_info(
        self, playbook_context: Dict[str, Any]
    ) -> tuple[Optional[str], Optional[str], Optional[float]]:
        """
        Extract intent information from playbook context

        Args:
            playbook_context: Playbook context

        Returns:
            Tuple of (origin_intent_id, origin_intent_label, intent_confidence)
        """
        if not playbook_context.get("confirmed_intent_id"):
            return None, None, None

        try:
            from ...services.stores.intent_tags_store import IntentTagsStore

            intent_tags_store = IntentTagsStore(db_path=self.store.db_path)
            intent_tag = intent_tags_store.get_intent_tag(
                playbook_context["confirmed_intent_id"]
            )
            if intent_tag and intent_tag.status.value == "confirmed":
                return intent_tag.id, intent_tag.label, intent_tag.confidence
        except Exception as e:
            logger.warning(f"Failed to extract intent info: {e}")

        return None, None, None

    async def _calculate_total_steps(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        ctx: LocalDomainContext,
        execution_result: Optional[Dict[str, Any]] = None,
        execution_mode: str = "conversation",
    ) -> int:
        """
        Calculate total steps from playbook context, execution result, or playbook

        Args:
            playbook_code: Playbook code
            playbook_context: Playbook context
            ctx: Execution context
            execution_result: Optional execution result
            execution_mode: Execution mode

        Returns:
            Total steps count
        """
        total_steps = playbook_context.get("total_steps", 0)

        if total_steps > 0:
            return total_steps

        # Try to get steps count from execution_result (for workflow mode)
        if execution_mode == "workflow" and execution_result:
            workflow_result = execution_result.get("result", {})
            if isinstance(workflow_result, dict) and "steps" in workflow_result:
                return len(workflow_result["steps"])
            elif execution_result.get("execution_id"):
                task = self.tasks_store.get_task_by_execution_id(
                    execution_result.get("execution_id")
                )
                if task and task.execution_context:
                    steps = task.execution_context.get("total_steps", 0)
                    if steps > 0:
                        return steps

        # Fallback: Try to get steps count from playbook
        try:
            playbook = await self.playbook_resolver.get_playbook(playbook_code, ctx=ctx)
            if playbook:
                if hasattr(playbook, "playbook_json") and playbook.playbook_json:
                    if playbook.playbook_json.steps:
                        return len(playbook.playbook_json.steps)
                elif hasattr(playbook, "steps"):
                    return len(playbook.steps) if isinstance(playbook.steps, list) else 1
        except Exception as e:
            logger.warning(f"Failed to get step count from playbook: {e}")

        return 1
