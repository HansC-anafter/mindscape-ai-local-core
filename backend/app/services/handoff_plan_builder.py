"""
HandoffPlan Builder

Builds complete HandoffPlan from simplified workflow steps.
Completes missing fields (kind, interaction_mode, input_mapping) using playbook metadata.
"""

import logging
from typing import Dict, Any, List, Optional

from backend.app.models.playbook import (
    HandoffPlan,
    WorkflowStep,
    PlaybookKind,
    InteractionMode
)
from backend.app.services.playbook_service import PlaybookService

logger = logging.getLogger(__name__)


class HandoffPlanBuilder:
    """Builds complete HandoffPlan from simplified workflow steps"""

    def __init__(self, playbook_service: Optional[PlaybookService] = None):
        """
        Initialize HandoffPlanBuilder

        Args:
            playbook_service: PlaybookService instance (optional, will create if not provided)
        """
        self.playbook_service = playbook_service or PlaybookService()

    def build_handoff_plan(
        self,
        simplified_steps: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        estimated_duration: Optional[int] = None
    ) -> HandoffPlan:
        """
        Build complete HandoffPlan from simplified workflow steps

        Args:
            simplified_steps: List of simplified WorkflowStep dicts (only playbook_code + inputs)
            context: Initial workflow context
            estimated_duration: Estimated execution time in seconds

        Returns:
            Complete HandoffPlan with all fields filled
        """
        if context is None:
            context = {}

        complete_steps = []
        for step_dict in simplified_steps:
            complete_step = self._complete_workflow_step(step_dict)
            complete_steps.append(complete_step)

        return HandoffPlan(
            steps=complete_steps,
            context=context,
            estimated_duration=estimated_duration
        )

    def _complete_workflow_step(self, step_dict: Dict[str, Any]) -> WorkflowStep:
        """
        Complete a simplified workflow step with missing fields

        Args:
            step_dict: Simplified step dict with playbook_code and inputs

        Returns:
            Complete WorkflowStep
        """
        playbook_code = step_dict.get('playbook_code')
        if not playbook_code:
            raise ValueError("playbook_code is required in workflow step")

        # Use PlaybookService to get playbook
        import asyncio
        try:
            playbook = asyncio.run(self.playbook_service.get_playbook(playbook_code))
            if not playbook:
                logger.warning(f"Playbook not found: {playbook_code}, using defaults")
                kind = PlaybookKind.USER_WORKFLOW
                interaction_mode = [InteractionMode.CONVERSATIONAL]
            else:
                kind = playbook.metadata.kind
                interaction_mode = playbook.metadata.interaction_mode
        except Exception as e:
            logger.warning(f"Failed to load playbook {playbook_code}: {e}, using defaults")
            kind = PlaybookKind.USER_WORKFLOW
            interaction_mode = [InteractionMode.CONVERSATIONAL]

        inputs = step_dict.get('inputs', {})
        input_mapping = step_dict.get('input_mapping', {})
        condition = step_dict.get('condition')

        if not input_mapping:
            input_mapping = self._extract_input_mapping(inputs)

        return WorkflowStep(
            playbook_code=playbook_code,
            kind=kind,
            inputs=inputs,
            input_mapping=input_mapping,
            condition=condition,
            interaction_mode=interaction_mode
        )

    def _extract_input_mapping(self, inputs: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract input_mapping from inputs that contain $previous or $context references

        Args:
            inputs: Input dict that may contain workflow-level template variables

        Returns:
            Dict mapping input names to their mapping expressions
        """
        input_mapping = {}
        for key, value in inputs.items():
            if isinstance(value, str) and (value.startswith('$previous.') or value.startswith('$context.')):
                input_mapping[key] = value
        return input_mapping

