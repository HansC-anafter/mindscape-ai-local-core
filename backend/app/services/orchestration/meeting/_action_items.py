"""
Meeting engine action item mixin.

Handles action item extraction from executor output, playbook launching,
task creation, and JSON payload parsing.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.workspace import Task, TaskStatus

logger = logging.getLogger(__name__)


class MeetingActionItemsMixin:
    """Mixin providing action item methods for MeetingEngine."""

    async def _build_action_items(
        self,
        decision: str,
        user_message: str,
        critic_notes: List[str],
        planner_proposals: List[str],
    ) -> List[Dict[str, Any]]:
        """Generate action items by running an executor turn and parsing output."""
        executor_turn = await self._agent_turn(
            "executor",
            round_num=max(1, self.session.round_count),
            user_message=user_message,
            decision=decision,
            planner_proposals=planner_proposals,
            critic_notes=critic_notes,
        )
        self._emit_turn(executor_turn)

        return self._parse_action_items(executor_turn.content, decision)

    async def _land_action_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create a task projection for an action item.

        Actual dispatch is handled by DispatchOrchestrator via engine.run().
        This method only creates the task record (projection).
        """
        item.setdefault("meeting_session_id", self.session.id)
        item.setdefault("execution_id", None)
        item.setdefault("task_id", None)

        item["task_id"] = self._create_action_task(item)
        item["landing_status"] = "task_created" if item.get("task_id") else "planned"

        return item

    def _create_action_task(self, item: Dict[str, Any]) -> Optional[str]:
        """Create a Task record for an action item that was not launched as a playbook."""
        if not self.tasks_store:
            return None
        try:
            task_id = str(uuid.uuid4())
            # Use target_workspace_id from planner routing, fallback to session
            target_ws = item.get("target_workspace_id") or self.session.workspace_id

            # 5B-2: Three-way task_type dispatch
            if item.get("playbook_code"):
                task_type = "playbook_execution"
                pack_id = item["playbook_code"]
            elif item.get("tool_name"):
                task_type = "tool_execution"
                pack_id = item["tool_name"]
            else:
                task_type = "meeting_action_item"
                pack_id = "meeting_action_item"

            task = Task(
                id=task_id,
                workspace_id=target_ws,
                message_id=(self._events[-1].id if self._events else str(uuid.uuid4())),
                execution_id=item.get("execution_id"),
                project_id=self.project_id,
                pack_id=pack_id,
                task_type=task_type,
                status=TaskStatus.PENDING,
                params={
                    "meeting_session_id": self.session.id,
                    "thread_id": getattr(self.session, "thread_id", None),
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "priority": item.get("priority"),
                    "tool_name": item.get("tool_name"),
                    "input_params": item.get("input_params"),
                },
                result=None,
                execution_context={
                    "trigger_source": "meeting_engine",
                    "meeting_session_id": self.session.id,
                    "thread_id": getattr(self.session, "thread_id", None),
                    "tool_name": item.get("tool_name"),
                    "inputs": item.get("input_params") or {},
                },
                created_at=datetime.now(timezone.utc),
            )
            self.tasks_store.create_task(task)
            return task_id
        except Exception as exc:
            logger.warning(
                "MeetingEngine failed to create action task: %s", exc, exc_info=True
            )
            return None

    def _parse_action_items(
        self, executor_output: str, decision: str
    ) -> List[Dict[str, Any]]:
        """Parse action items from executor output (JSON or bullet fallback)."""
        payload = self._extract_json_payload(executor_output)
        items: List[Dict[str, Any]] = []

        if isinstance(payload, dict) and isinstance(payload.get("action_items"), list):
            payload = payload.get("action_items")
        if isinstance(payload, list):
            for raw_item in payload[:3]:
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
