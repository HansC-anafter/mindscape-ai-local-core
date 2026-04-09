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
    ) -> List["ActionIntent"]:
        """Generate action items by running an executor turn and normalizing output.

        Returns List[ActionIntent] via SemanticNormalizer (sole normalization
        authority per v3 OP-2).  Legacy dict-based parsing is retained as a
        fallback inside SemanticNormalizer itself.
        """
        from backend.app.models.action_intent import ActionIntent
        from backend.app.services.orchestration.meeting.program_spec_bridge import (
            action_intents_from_program_spec,
            parse_program_spec_from_output,
        )
        from backend.app.services.orchestration.meeting.semantic_normalizer import (
            SemanticNormalizer,
        )

        self._pending_program_spec = None
        self._pending_program_spec_source = None

        try:
            if hasattr(self, "_prepare_round_routing_graph"):
                try:
                    self._prepare_round_routing_graph(
                        round_number=max(1, self.session.round_count),
                        next_role_id="executor",
                        facilitator_summary=getattr(
                            self,
                            "_current_round_facilitator_summary",
                            decision,
                        ),
                        decision=decision,
                        planner_proposals=planner_proposals,
                        critic_notes=critic_notes,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to prepare executor routing graph: %s",
                        exc,
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

            workspace_id = getattr(self.session, "workspace_id", None)
            structured_program_spec = parse_program_spec_from_output(
                executor_turn.content,
                fallback_scale=self._resolve_program_spec_scale(),
                coverage_snapshot=self._get_program_spec_coverage_snapshot(),
            )
            if structured_program_spec is not None:
                intents = action_intents_from_program_spec(
                    structured_program_spec,
                    default_workspace_id=workspace_id,
                )
                self._pending_program_spec = structured_program_spec
                self._pending_program_spec_source = "executor_structured"
                return intents

            # L2: SemanticNormalizer is the sole normalization authority
            normalizer = SemanticNormalizer()

            intents = normalizer.normalize(
                executor_output=executor_turn.content,
                decision=decision,
                workspace_id=workspace_id,
            )

            # Stamp meeting_session_id onto each intent for session correlation
            for intent in intents:
                if not intent.target_workspace_id:
                    intent.target_workspace_id = workspace_id

            return intents
        except Exception as exc:
            fallback_intents = self._build_request_contract_fallback_action_intents(
                decision=decision,
                user_message=user_message,
                error=exc,
            )
            if fallback_intents is not None:
                return fallback_intents
            raise

    @staticmethod
    def _is_runtime_quota_or_rate_limit_error(exc: Exception) -> bool:
        text = str(exc or "").lower()
        patterns = (
            "usage limit",
            "rate limit",
            "quota",
            "too many requests",
            "resource_exhausted",
            "resource exhausted",
            "exhausted your capacity",
        )
        return any(pattern in text for pattern in patterns)

    def _build_request_contract_fallback_action_intents(
        self,
        *,
        decision: str,
        user_message: str,
        error: Exception,
    ) -> Optional[List["ActionIntent"]]:
        from backend.app.models.action_intent import IntentConfidence
        from backend.app.models.program_spec import ProgramSpec, Workstream
        from backend.app.services.orchestration.meeting.program_spec_bridge import (
            action_intents_from_program_spec,
        )

        if not self._is_runtime_quota_or_rate_limit_error(error):
            return None

        contract = getattr(self, "_request_contract", None)
        raw_deliverables = getattr(contract, "deliverables", None)
        if not raw_deliverables:
            session_metadata = getattr(self.session, "metadata", None) or {}
            raw_contract = session_metadata.get("request_contract")
            if isinstance(raw_contract, dict):
                raw_deliverables = raw_contract.get("deliverables")

        normalized_deliverables: List[Dict[str, Any]] = []
        for index, raw_deliverable in enumerate(raw_deliverables or [], start=1):
            if hasattr(raw_deliverable, "model_dump"):
                candidate = raw_deliverable.model_dump(mode="json")
            elif isinstance(raw_deliverable, dict):
                candidate = dict(raw_deliverable)
            else:
                candidate = {
                    "id": getattr(raw_deliverable, "id", None),
                    "name": getattr(raw_deliverable, "name", None),
                    "quantity": getattr(raw_deliverable, "quantity", None),
                    "acceptance_criteria": getattr(
                        raw_deliverable,
                        "acceptance_criteria",
                        None,
                    ),
                }

            deliverable_id = str(candidate.get("id") or f"D{index}").strip()
            deliverable_name = str(
                candidate.get("name") or f"deliverable_{index}"
            ).strip()
            if not deliverable_id or not deliverable_name:
                continue
            normalized_deliverables.append(
                {
                    "id": deliverable_id,
                    "name": deliverable_name,
                    "quantity": candidate.get("quantity"),
                    "acceptance_criteria": candidate.get("acceptance_criteria") or [],
                }
            )

        if not normalized_deliverables:
            return None

        workstreams: List[Workstream] = []
        target_outputs: List[str] = []
        for index, deliverable in enumerate(normalized_deliverables, start=1):
            deliverable_id = deliverable["id"]
            deliverable_name = deliverable["name"]
            acceptance_criteria = [
                str(item).strip()
                for item in deliverable.get("acceptance_criteria") or []
                if str(item).strip()
            ]
            description_lines = [
                f"Create the requested deliverable '{deliverable_name}'.",
            ]
            decision_text = str(decision or "").strip()
            if decision_text:
                description_lines.append(decision_text)
            elif str(user_message or "").strip():
                description_lines.append(str(user_message or "").strip())
            if acceptance_criteria:
                description_lines.append(
                    "Acceptance criteria: " + "; ".join(acceptance_criteria)
                )
            workstreams.append(
                Workstream(
                    id=f"WS_{deliverable_id}",
                    name=deliverable_name,
                    description=" ".join(
                        part.strip() for part in description_lines if part.strip()
                    ),
                    produces_deliverables=[deliverable_id],
                    estimated_units=max(int(deliverable.get("quantity") or 1), 1),
                    eligible_engines=[],
                )
            )
            target_outputs.append(deliverable_name)

        if not workstreams:
            return None

        fallback_program_spec = ProgramSpec(
            workstreams=workstreams,
            milestones=[],
            dependency_graph={workstream.id: [] for workstream in workstreams},
            target_outputs=target_outputs,
            scale=self._resolve_program_spec_scale(),
            coverage_snapshot=self._get_program_spec_coverage_snapshot(),
        )
        workspace_id = getattr(self.session, "workspace_id", None)
        intents = action_intents_from_program_spec(
            fallback_program_spec,
            default_workspace_id=workspace_id,
        )

        for intent, deliverable in zip(intents, normalized_deliverables):
            intent.confidence = IntentConfidence.HIGH
            intent.input_params = {
                "deliverable_id": deliverable["id"],
                "deliverable_name": deliverable["name"],
            }

        self._pending_program_spec = fallback_program_spec
        self._pending_program_spec_source = "request_contract_fallback"
        logger.warning(
            "Executor action extraction failed with quota/rate-limit error; "
            "bootstrapping ProgramSpec from %d request-contract deliverables "
            "for session %s: %s",
            len(intents),
            getattr(self.session, "id", None),
            error,
        )
        return intents

    def _resolve_program_spec_scale(self):
        from backend.app.models.request_contract import ScaleEstimate

        raw_scale = getattr(getattr(self, "_request_contract", None), "scale_estimate", None)
        raw_value = getattr(raw_scale, "value", raw_scale)
        try:
            return ScaleEstimate(str(raw_value))
        except ValueError:
            return ScaleEstimate.STANDARD

    def _get_program_spec_coverage_snapshot(self) -> Optional[Dict[str, Any]]:
        metadata = getattr(self.session, "metadata", None) or {}
        snapshot = metadata.get("last_coverage_matrix")
        return snapshot if isinstance(snapshot, dict) else None

    def _persist_program_spec(
        self,
        program_spec: "ProgramSpec",
        *,
        source: str,
    ) -> None:
        if self.session.metadata is None:
            self.session.metadata = {}
        payload = program_spec.model_dump(mode="json")
        self.session.metadata["last_program_spec"] = payload
        self.session.metadata["last_program_spec_source"] = source
        self.session.metadata["last_program_spec_workstream_count"] = len(
            program_spec.workstreams
        )
        self.session.metadata["last_program_spec_recorded_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        try:
            self.session_store.update(self.session)
        except Exception as exc:
            logger.warning("Failed to persist session after ProgramSpec bridge: %s", exc)

    def _persist_program_spec_from_final_intents(
        self,
        action_intents: List["ActionIntent"],
        *,
        decision: str,
    ) -> None:
        from backend.app.services.orchestration.meeting.program_spec_bridge import (
            bootstrap_program_spec_from_intents,
            merge_program_spec_with_intents,
        )

        pending_program_spec = getattr(self, "_pending_program_spec", None)
        pending_source = getattr(self, "_pending_program_spec_source", None)
        try:
            if pending_program_spec is not None:
                final_program_spec = merge_program_spec_with_intents(
                    pending_program_spec,
                    action_intents,
                )
                source = str(pending_source or "structured_seed")
            else:
                final_program_spec = bootstrap_program_spec_from_intents(
                    action_intents,
                    decision=decision,
                    fallback_scale=self._resolve_program_spec_scale(),
                    coverage_snapshot=self._get_program_spec_coverage_snapshot(),
                )
                source = "action_intent_bootstrap"
            self._persist_program_spec(final_program_spec, source=source)
        finally:
            self._pending_program_spec = None
            self._pending_program_spec_source = None

    async def _land_action_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create a task projection for an action item.

        Actual dispatch is handled by DispatchOrchestrator via engine.run().
        This method only creates the task record (projection).

        EXIT CRITERIA — safe to delete when ALL of the following hold:
        1. DispatchOrchestrator._launch_playbook() has been verified in
           production (inputs/ctx/trace_id/session-metadata parity with
           the old direct-launch path).
        2. _project_to_task() in DispatchOrchestrator covers the
           task-creation fallback that _create_action_task() provides.
        3. No callers remain in engine.py or _dispatch.py.
        """
        item.setdefault("meeting_session_id", self.session.id)
        item.setdefault("execution_id", None)
        item.setdefault("task_id", None)

        item["task_id"] = self._create_action_task(item)
        item["landing_status"] = "task_created" if item.get("task_id") else "planned"

        return item

    def _create_action_task(self, item: Dict[str, Any]) -> Optional[str]:
        """Create a Task record for an action item that was not launched as a playbook.

        Coupled to _land_action_item — same exit criteria apply.
        """
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
                # No playbook or tool match — skip task creation.
                # Display is covered by session layer (SSE + session.action_items).
                # Continuity is covered by _build_previous_decisions_context().
                # No consumer exists for meeting_action_item task_type.
                logger.debug(
                    "Skipping task creation for unmatched action item: %s",
                    item.get("title", "?"),
                )
                return None

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
