"""Action item JSON and fallback parsing helpers."""

import json
import re
from typing import Any, Dict, List


class ActionItemParserMixin:
    def _parse_action_items(
        self, executor_output: str, decision: str
    ) -> List[Dict[str, Any]]:
        """Parse action items from executor output."""
        payload = self._extract_json_payload(executor_output)
        items: List[Dict[str, Any]] = []

        if isinstance(payload, dict) and isinstance(payload.get("action_items"), list):
            payload = payload.get("action_items")
        if isinstance(payload, list):
            for raw_item in payload:
                if not isinstance(raw_item, dict):
                    continue
                items.append(
                    {
                        "meeting_session_id": self.session.id,
                        "title": str(raw_item.get("title") or "Action Item").strip(),
                        "description": str(
                            raw_item.get("description") or decision
                        ).strip(),
                        "assigned_to": str(
                            raw_item.get("assigned_to") or "executor"
                        ).strip(),
                        "priority": str(raw_item.get("priority") or "medium").strip(),
                        "playbook_code": (
                            str(raw_item.get("playbook_code")).strip()
                            if raw_item.get("playbook_code")
                            else None
                        ),
                        "target_workspace_id": (
                            str(raw_item.get("target_workspace_id")).strip()
                            if raw_item.get("target_workspace_id")
                            else None
                        ),
                        "tool_name": (
                            str(raw_item.get("tool_name")).strip()
                            if raw_item.get("tool_name")
                            else None
                        ),
                        "input_params": (
                            raw_item.get("input_params")
                            if isinstance(raw_item.get("input_params"), dict)
                            else None
                        ),
                        "blocked_by": (
                            raw_item.get("blocked_by")
                            if isinstance(raw_item.get("blocked_by"), list)
                            else None
                        ),
                        "asset_refs": raw_item.get("asset_refs") or [],
                        "execution_id": None,
                    }
                )

        if items:
            return items

        bullet_items = re.findall(r"(?:^|\n)\s*(?:[-*]|\d+\.)\s+(.+)", executor_output)
        if bullet_items:
            return [
                {
                    "meeting_session_id": self.session.id,
                    "title": bullet_items[0][:80],
                    "description": bullet_items[0],
                    "assigned_to": "executor",
                    "priority": "medium",
                    "playbook_code": None,
                    "execution_id": None,
                }
            ]

        return [
            {
                "meeting_session_id": self.session.id,
                "title": "Implement finalized decision",
                "description": decision,
                "assigned_to": "executor",
                "priority": "medium",
                "playbook_code": None,
                "execution_id": None,
            }
        ]

    def _extract_json_payload(self, text: str) -> Any:
        """Try to extract a JSON object or array from mixed text."""
        candidates: List[str] = []
        fenced = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            candidates.append(fenced.group(1))

        bracket = re.search(r"(\[[\s\S]*\])", text)
        if bracket:
            candidates.append(bracket.group(1))

        brace = re.search(r"(\{[\s\S]*\})", text)
        if brace:
            candidates.append(brace.group(1))

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except Exception:
                continue
        return None
