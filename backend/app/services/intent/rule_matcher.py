"""
Rule-Based Intent Matcher

Layer 1 rule-based matching for interaction type classification.
"""

import re
from typing import Optional
import logging

from .models import InteractionType

logger = logging.getLogger(__name__)


class RuleBasedIntentMatcher:
    """Rule-based matching for Layer 1 (Interaction Type)"""

    # Command patterns for starting playbooks
    START_PLAYBOOK_PATTERNS = [
        r"/start\s+(\w+)",
        r"/start\s+proposal",
        r"/start\s+yearly",
        r"開始\s+(\w+)",
        r"啟動\s+(\w+)",
        r"執行\s+(\w+)",
        r"我想.*寫.*(?:補助|計畫|申請)",
        r"我想.*(?:年度|年終).*(?:回顧|出書)",
        r"幫我.*(?:整理|學習).*(?:習慣)",
    ]

    # Settings management patterns
    SETTINGS_PATTERNS = [
        r"/settings?",
        r"/設定",
        r"設定",
        r"配置",
        r"語言.*設定",
        r"設定.*語言",
        r"preferences?",
        r"settings?",
    ]

    # Export patterns
    EXPORT_PATTERNS = [
        r"匯出",
        r"匯出\s+docx",
        r"匯出\s+markdown",
        r"export",
        r"export\s+docx",
        r"export\s+markdown",
    ]

    def match_command(self, user_input: str) -> Optional[str]:
        """
        Match specific commands from user input

        Returns:
            Command name if matched, None otherwise
        """
        user_input_lower = user_input.lower().strip()

        # Check for export commands
        for pattern in self.EXPORT_PATTERNS:
            if re.search(pattern, user_input_lower, re.IGNORECASE):
                if "docx" in user_input_lower:
                    return "export_docx"
                elif "markdown" in user_input_lower:
                    return "export_markdown"
                else:
                    return "export"

        # Check for playbook start commands
        for pattern in self.START_PLAYBOOK_PATTERNS:
            match = re.search(pattern, user_input_lower, re.IGNORECASE)
            if match:
                if match.groups():
                    return f"start_{match.group(1)}"
                return "start_playbook"

        # Check for settings commands
        for pattern in self.SETTINGS_PATTERNS:
            if re.search(pattern, user_input_lower, re.IGNORECASE):
                return "manage_settings"

        return None

    def match_channel_specific(
        self, user_input: str, channel: str
    ) -> Optional[InteractionType]:
        """
        Match channel-specific patterns

        Args:
            user_input: User input text
            channel: Channel (api, line, wp, playbook)

        Returns:
            InteractionType if matched, None otherwise
        """
        user_input_lower = user_input.lower().strip()

        # Line channel: commands typically start with /
        if channel == "line":
            if user_input_lower.startswith("/"):
                # Extract command after /
                command = (
                    user_input_lower[1:].split()[0] if user_input_lower[1:] else ""
                )
                if command in ["start", "settings", "設定", "設定語言"]:
                    if command in ["start"]:
                        return InteractionType.START_PLAYBOOK
                    else:
                        return InteractionType.MANAGE_SETTINGS

        # WordPress webhook: may have specific patterns
        if channel == "wp":
            # WordPress webhook patterns can be added here
            pass

        return None

    def match_interaction_type(
        self, user_input: str, channel: str = "api"
    ) -> Optional[InteractionType]:
        """
        Match interaction type using rules

        Args:
            user_input: User input text
            channel: Channel (api, line, wp, playbook)

        Returns:
            InteractionType or None if no match
        """
        # Try channel-specific matching first
        channel_result = self.match_channel_specific(user_input, channel)
        if channel_result:
            return channel_result

        user_input_lower = user_input.lower().strip()

        # Check for playbook start patterns
        for pattern in self.START_PLAYBOOK_PATTERNS:
            if re.search(pattern, user_input_lower, re.IGNORECASE):
                return InteractionType.START_PLAYBOOK

        # Check for settings patterns
        for pattern in self.SETTINGS_PATTERNS:
            if re.search(pattern, user_input_lower, re.IGNORECASE):
                return InteractionType.MANAGE_SETTINGS

        # Default: no match (will be handled by LLM layer if enabled)
        return None
