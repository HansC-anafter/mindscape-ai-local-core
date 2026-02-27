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

        items = self._parse_action_items(executor_turn.content, decision)
        landed_items: List[Dict[str, Any]] = []
        for item in items:
            landed_items.append(await self._land_action_item(item))
        return landed_items

    async def _land_action_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Attempt to launch a playbook or create a task for an action item."""
        item.setdefault("meeting_session_id", self.session.id)
        item.setdefault("execution_id", None)
        item.setdefault("task_id", None)

        if self.execution_launcher and item.get("playbook_code"):
            try:
                ctx = LocalDomainContext(
                    actor_id=self.profile_id,
                    workspace_id=self.session.workspace_id,
                )
                result = await self.execution_launcher.launch(
                    playbook_code=item["playbook_code"],
                    inputs={
                        "task": item["description"],
                        "meeting_session_id": self.session.id,
                        "workspace_id": self.session.workspace_id,
                    },
                    ctx=ctx,
                    project_id=self.project_id,
                    trace_id=str(uuid.uuid4()),
                )
                item["execution_id"] = result.get("execution_id")
                if item["execution_id"]:
                    exec_ids = self.session.metadata.setdefault("execution_ids", [])
                    if item["execution_id"] not in exec_ids:
                        exec_ids.append(item["execution_id"])
                item["landing_status"] = (
                    "launched" if item.get("execution_id") else "launch_failed"
                )
            except Exception as exc:
                logger.warning(
                    "MeetingEngine failed to launch playbook '%s': %s",
                    item.get("playbook_code"),
                    exc,
                    exc_info=True,
                )
                item["landing_status"] = "launch_error"
                item["landing_error"] = str(exc)

        if not item.get("execution_id"):
            item["task_id"] = self._create_action_task(item)
            item["landing_status"] = (
                "task_created" if item.get("task_id") else "planned"
            )

        return item

    def _create_action_task(self, item: Dict[str, Any]) -> Optional[str]:
        """Create a Task record for an action item that was not launched as a playbook."""
        if not self.tasks_store:
            return None
        try:
            task_id = str(uuid.uuid4())
            task = Task(
                id=task_id,
                workspace_id=self.session.workspace_id,
                message_id=(self._events[-1].id if self._events else str(uuid.uuid4())),
                execution_id=item.get("execution_id"),
                project_id=self.project_id,
                pack_id=item.get("playbook_code") or "meeting_action_item",
                task_type="meeting_action_item",
                status=TaskStatus.PENDING,
                params={
                    "meeting_session_id": self.session.id,
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "priority": item.get("priority"),
                },
                result=None,
                execution_context={
                    "trigger_source": "meeting_engine",
                    "meeting_session_id": self.session.id,
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
