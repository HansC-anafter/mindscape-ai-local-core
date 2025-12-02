"""
HandoffPlan Extractor

Extracts HandoffPlan from LLM response containing <playbook_handoff> tags.
"""

import re
import json
import logging
from typing import Optional, Dict, Any

from backend.app.models.playbook import HandoffPlan

logger = logging.getLogger(__name__)


class HandoffPlanExtractor:
    """Extract HandoffPlan from LLM response"""

    HANDOFF_TAG_PATTERN = re.compile(
        r'<playbook_handoff>(.*?)</playbook_handoff>',
        re.DOTALL
    )

    @staticmethod
    def extract_handoff_plan(llm_response: str) -> Optional[HandoffPlan]:
        """
        Extract HandoffPlan from LLM response

        Args:
            llm_response: LLM response text that may contain <playbook_handoff> tags

        Returns:
            HandoffPlan object if found, None otherwise
        """
        match = HandoffPlanExtractor.HANDOFF_TAG_PATTERN.search(llm_response)
        if not match:
            return None

        json_str = match.group(1).strip()
        try:
            data = json.loads(json_str)
            handoff_plan = HandoffPlan(**data)
            logger.info(f"Extracted HandoffPlan with {len(handoff_plan.steps)} steps")
            return handoff_plan
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse HandoffPlan JSON: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to create HandoffPlan: {e}")
            return None

    @staticmethod
    def has_handoff_plan(llm_response: str) -> bool:
        """
        Check if LLM response contains HandoffPlan

        Args:
            llm_response: LLM response text

        Returns:
            True if <playbook_handoff> tags are found
        """
        return bool(HandoffPlanExtractor.HANDOFF_TAG_PATTERN.search(llm_response))

    @staticmethod
    def remove_handoff_tags(llm_response: str) -> str:
        """
        Remove <playbook_handoff> tags from response for user display

        Args:
            llm_response: LLM response text

        Returns:
            Response text with handoff tags removed
        """
        return HandoffPlanExtractor.HANDOFF_TAG_PATTERN.sub('', llm_response).strip()

