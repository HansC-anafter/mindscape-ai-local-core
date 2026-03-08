"""
SemanticNormalizer — L2-Online: parse executor output → ActionIntent[].

Sits between raw executor JSON/text and the IR compiler.  Responsible for:
- Extracting structured action items from executor output
- Minting stable intent_ids (INV-1)
- Resolving tool/playbook references where possible
- Flagging low-confidence items
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.action_intent import ActionIntent, IntentConfidence

logger = logging.getLogger(__name__)


class SemanticNormalizer:
    """
    Parse executor output into structured ActionIntent list.

    This is the L2-Online bridge between raw LLM executor output
    and the structured TaskIR compilation pipeline.
    """

    def normalize(
        self,
        executor_output: str,
        decision: str = "",
        *,
        workspace_id: Optional[str] = None,
    ) -> List[ActionIntent]:
        """
        Parse executor output into ActionIntent[].

        Args:
            executor_output: Raw text/JSON from executor.
            decision: Meeting decision text (fallback context).
            workspace_id: Default workspace for routing.

        Returns:
            List of ActionIntent instances.
        """
        if not executor_output or not executor_output.strip():
            # No output → single intent from decision
            if decision:
                return [
                    ActionIntent(
                        title="Execute Decision",
                        description=decision,
                        confidence=IntentConfidence.LOW,
                        target_workspace_id=workspace_id,
                    )
                ]
            return []

        # Try JSON extraction first
        items = self._try_parse_json(executor_output)
        if items:
            intents = [self._dict_to_intent(d, workspace_id) for d in items]
            logger.info(
                "[SemanticNormalizer] Parsed %d intents from JSON", len(intents)
            )
            return intents

        # Fallback: bullet-point parsing
        intents = self._parse_bullets(executor_output, workspace_id)
        if intents:
            logger.info(
                "[SemanticNormalizer] Parsed %d intents from bullets", len(intents)
            )
            return intents

        # Last resort: single intent from full text
        return [
            ActionIntent(
                title=executor_output[:100].strip(),
                description=executor_output,
                confidence=IntentConfidence.LOW,
                target_workspace_id=workspace_id,
            )
        ]

    def _dict_to_intent(
        self, d: Dict[str, Any], default_ws: Optional[str] = None
    ) -> ActionIntent:
        """Convert a parsed dict to ActionIntent."""
        title = d.get("title") or d.get("action") or "Untitled"
        desc = d.get("description") or d.get("detail") or ""
        assignee = d.get("assignee") or d.get("owner") or ""

        # Resolve engine hint
        engine = d.get("engine")
        if not engine:
            playbook_code = d.get("playbook_code")
            if playbook_code:
                engine = f"playbook:{playbook_code}"

        # Confidence: items with tool or playbook are HIGH, otherwise MEDIUM
        has_actuator = bool(d.get("tool_name") or d.get("playbook_code"))
        confidence = IntentConfidence.HIGH if has_actuator else IntentConfidence.MEDIUM

        return ActionIntent(
            title=title,
            description=desc,
            assignee=assignee,
            confidence=confidence,
            tool_name=d.get("tool_name"),
            playbook_code=d.get("playbook_code"),
            input_params=d.get("input_params"),
            target_workspace_id=d.get("target_workspace_id") or default_ws,
            depends_on=d.get("blocked_by") or d.get("depends_on"),
            priority=d.get("priority"),
            engine=engine,
            asset_refs=d.get("asset_refs") or [],
        )

    def _try_parse_json(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Try to extract JSON array or object from text."""
        # Try direct parse
        stripped = text.strip()
        for attempt in [stripped, self._extract_json_block(stripped)]:
            if not attempt:
                continue
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    # Single action item as object
                    items = parsed.get("action_items") or parsed.get("actions")
                    if isinstance(items, list):
                        return items
                    return [parsed]
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    @staticmethod
    def _extract_json_block(text: str) -> Optional[str]:
        """Extract JSON from markdown fenced code block or raw brackets."""
        # Try fenced code block
        match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try raw bracket extraction
        for start, end in [("[", "]"), ("{", "}")]:
            idx_start = text.find(start)
            idx_end = text.rfind(end)
            if idx_start >= 0 and idx_end > idx_start:
                return text[idx_start : idx_end + 1]
        return None

    def _parse_bullets(
        self, text: str, default_ws: Optional[str] = None
    ) -> List[ActionIntent]:
        """Parse bullet-point style action items."""
        lines = text.strip().split("\n")
        intents: List[ActionIntent] = []

        for line in lines:
            line = line.strip()
            # Match lines starting with -, *, or numbered
            match = re.match(r"^[-*•]\s+(.+)$|^(\d+)[.)]\s+(.+)$", line)
            if match:
                title = (match.group(1) or match.group(3) or "").strip()
                if title and len(title) > 3:
                    intents.append(
                        ActionIntent(
                            title=title[:200],
                            description=title,
                            confidence=IntentConfidence.LOW,
                            target_workspace_id=default_ws,
                        )
                    )

        return intents
