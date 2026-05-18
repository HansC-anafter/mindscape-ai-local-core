"""Request-contract fallback and deliverable helpers for MeetingEngine."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MeetingEngineFallbackDeliverableMixin:
        def _apply_request_contract_fallback_if_needed(
            self,
            *,
            action_items: List[Dict[str, Any]],
            action_intents: Optional[List[Any]],
        ) -> tuple[List[Any], List[Dict[str, Any]]]:
            """Replace blocked deliverables with executable writer agent tasks."""
            contract = self._get_request_contract_metadata()
            deliverables = contract.get("deliverables", []) if contract else []
            if not isinstance(deliverables, list) or not deliverables:
                return action_intents or [], action_items

            blocked_deliverables: List[str] = []
            blocked_reasons: List[str] = []
            for item in action_items:
                reason_code = str(item.get("policy_reason_code") or "").strip()
                if reason_code not in {"REQUIRED_INPUT_MISSING", "UNKNOWN_PLAYBOOK"}:
                    continue
                deliverable_id = self._extract_deliverable_id(item)
                if deliverable_id:
                    blocked_deliverables.append(deliverable_id)
                    blocked_reasons.append(reason_code)

            if not blocked_deliverables:
                return action_intents or [], action_items

            from backend.app.models.action_intent import ActionIntent

            preserved_atomic_items = [
                item
                for item in action_items
                if item.get("landing_status") != "policy_blocked"
                and bool(item.get("preserve_atomic_playbook"))
            ]
            covered_deliverables = set()
            for item in preserved_atomic_items:
                handled_ids = item.get("handled_deliverable_ids")
                if isinstance(handled_ids, list):
                    for raw_deliverable_id in handled_ids:
                        deliverable_id = str(raw_deliverable_id or "").strip()
                        if deliverable_id:
                            covered_deliverables.add(deliverable_id)
                deliverable_id = self._extract_deliverable_id(item)
                if deliverable_id:
                    covered_deliverables.add(deliverable_id)

            source_message = contract.get("source_message") or ""
            goals = contract.get("goals") if isinstance(contract.get("goals"), list) else []
            constraints = contract.get("constraints")
            acceptance_tests = contract.get("acceptance_tests")
            deliverable_names = [
                str(d.get("name")).strip()
                for d in deliverables
                if isinstance(d, dict) and d.get("name")
            ]
            workspace = getattr(self, "workspace", None)
            resolved_runtime = None
            for candidate in (
                getattr(workspace, "resolved_executor_runtime", None),
                getattr(self, "executor_runtime", None),
            ):
                if isinstance(candidate, str) and candidate.strip():
                    resolved_runtime = candidate.strip()
                    break
            default_agent_engine = (
                f"agent:{resolved_runtime}"
                if isinstance(resolved_runtime, str) and resolved_runtime.strip()
                else "agent:auto"
            )
            fallback_items: List[Dict[str, Any]] = []
            for raw_deliverable in deliverables:
                if not isinstance(raw_deliverable, dict):
                    continue
                deliverable_id = str(raw_deliverable.get("id") or "").strip()
                deliverable_name = str(raw_deliverable.get("name") or "").strip()
                if not deliverable_id or not deliverable_name:
                    continue
                if deliverable_id in covered_deliverables:
                    continue
                deliverable_path = self._resolve_deliverable_path(
                    deliverable_id=deliverable_id,
                    deliverable_name=deliverable_name,
                )
                user_request = (
                    f"Create the deliverable '{deliverable_name}' as a polished markdown "
                    f"document and save the final output to '{deliverable_path}'. "
                    "Use the exact target filename instead of generic defaults."
                )
                context_lines = []
                if source_message:
                    context_lines.append(f"Original request: {source_message}")
                if deliverable_names:
                    context_lines.append(
                        "Deliverable set: " + "; ".join(deliverable_names)
                    )
                context_lines.append(
                    f"Current deliverable: {deliverable_name} ({deliverable_id})"
                )
                context_lines.append(f"Target file path: {deliverable_path}")
                context_lines.append(
                    "Write the final markdown to the target file path exactly. "
                    "Do not stop at generic files like draft_content.md."
                )
                if goals:
                    context_lines.append(
                        "Goals: " + "; ".join(str(goal).strip() for goal in goals if goal)
                    )
                if constraints is not None:
                    context_lines.append(
                        "Constraints: "
                        + json.dumps(constraints, ensure_ascii=False, sort_keys=True)
                    )
                if acceptance_tests is not None:
                    context_lines.append(
                        "Acceptance tests: "
                        + json.dumps(acceptance_tests, ensure_ascii=False, sort_keys=True)
                    )
                fallback_items.append(
                    {
                        "title": deliverable_name,
                        "description": (
                            f"Create the requested deliverable '{deliverable_name}'. "
                            "Proceed with request-contract fallback for the original request: "
                            f"{source_message}\n"
                            f"Deliverables: {'; '.join(deliverable_names)}\n"
                            "Preserve constraints and produce readable, file-backed outputs "
                            "for each deliverable."
                        ),
                        "intent_id": f"WS_{deliverable_id}",
                        "source_intent_id": f"WS_{deliverable_id}",
                        "source_phase_id": f"WS_{deliverable_id}",
                        "priority": "high",
                        "target_workspace_id": getattr(self.session, "workspace_id", None),
                        "engine": default_agent_engine,
                        "input_params": {
                            "workspace_id": getattr(self.session, "workspace_id", None),
                            "deliverable_id": deliverable_id,
                            "deliverable_name": deliverable_name,
                            "deliverable_path": deliverable_path,
                            "user_request": user_request,
                            "context": "\n".join(
                                line for line in context_lines if line
                            ),
                        },
                    }
                )

            if not fallback_items:
                if preserved_atomic_items:
                    preserved_intents = [
                        ActionIntent.from_action_item_dict(item)
                        for item in preserved_atomic_items
                    ]
                    return preserved_intents, preserved_atomic_items
                return action_intents or [], action_items

            if self.session.metadata is None:
                self.session.metadata = {}
            self.session.metadata["policy_gate_fallback"] = {
                "reason": "policy_blocked_deliverables",
                "blocked_deliverables": sorted(set(blocked_deliverables)),
                "policy_reason_codes": sorted(set(blocked_reasons)),
                "replacement_intent_ids": [
                    item.get("intent_id") for item in fallback_items if item.get("intent_id")
                ],
                "preserved_intent_ids": [
                    item.get("intent_id")
                    for item in preserved_atomic_items
                    if item.get("intent_id")
                ],
            }
            logger.info(
                "Replacing %d action items with request-contract fallback writers for session %s (blocked deliverables=%s reasons=%s)",
                len(action_items),
                getattr(self.session, "id", "?"),
                sorted(set(blocked_deliverables)),
                sorted(set(blocked_reasons)),
            )
            merged_items = preserved_atomic_items + fallback_items
            fallback_intents = [
                ActionIntent.from_action_item_dict(item) for item in merged_items
            ]
            return fallback_intents, merged_items

        def _extract_deliverable_id(self, item: Dict[str, Any]) -> Optional[str]:
            params = item.get("input_params")
            if isinstance(params, dict):
                for key in ("deliverable_id", "deliverable"):
                    value = params.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            for key in ("deliverable_id", "deliverable"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for field_name in ("title", "description"):
                raw_value = item.get(field_name)
                if not isinstance(raw_value, str) or not raw_value.strip():
                    continue
                match = re.search(r"\b(D[1-9]\d*)\b", raw_value, re.IGNORECASE)
                if match:
                    return match.group(1).upper()
            return None

        def _resolve_deliverable_path(
            self,
            *,
            deliverable_id: Optional[str],
            deliverable_name: Optional[str],
        ) -> str:
            name = (deliverable_name or "").strip().lower()
            if deliverable_id == "D1" or any(
                token in name
                for token in ("operating system", "\u89d2\u8272", "\u8a9e\u6c23", "\u50f9\u503c\u4e3b\u5f35", "\u7d05\u7dda")
            ):
                return "persona_operating_system.md"
            if deliverable_id == "D2" or any(
                token in name
                for token in ("instagram", "ig", "7 \u5929", "7-day", "cta", "\u7bc0\u594f")
            ):
                return "instagram_week1_calendar.md"
            if deliverable_id == "D3" or any(
                token in name for token in ("reel", "hook")
            ):
                return "reel_hook_bank.md"

            slug_source = deliverable_name or deliverable_id or "deliverable"
            slug = re.sub(r"[^a-z0-9]+", "_", slug_source.lower()).strip("_")
            return f"{slug or 'deliverable'}.md"

        @staticmethod
        def _is_storyboard_deliverable(
            *,
            deliverable_id: Optional[str],
            deliverable_name: Optional[str],
        ) -> bool:
            name = (deliverable_name or "").strip().lower()
            storyboard_tokens = (
                "storyboard",
                "pd intake",
                "mms execution",
                "mms",
                "\u9810\u89bd\u57f7\u884c",
                "\u5206\u93e1",
            )
            if any(token in name for token in storyboard_tokens):
                return True
            return False

        def _collect_storyboard_deliverable_ids(
            self,
            contract: Optional[Dict[str, Any]],
        ) -> List[str]:
            if not isinstance(contract, dict):
                return []
            deliverables = contract.get("deliverables")
            if not isinstance(deliverables, list):
                return []
            handled_ids: List[str] = []
            for raw_deliverable in deliverables:
                if not isinstance(raw_deliverable, dict):
                    continue
                deliverable_id = str(raw_deliverable.get("id") or "").strip()
                if not deliverable_id:
                    continue
                deliverable_name = str(raw_deliverable.get("name") or "").strip()
                if self._is_storyboard_deliverable(
                    deliverable_id=deliverable_id,
                    deliverable_name=deliverable_name,
                ):
                    handled_ids.append(deliverable_id)
            return handled_ids

        @staticmethod
        def _clean_string_list(values: Any) -> List[str]:
            if not isinstance(values, list):
                return []
            normalized: List[str] = []
            for value in values:
                text = str(value or "").strip()
                if text:
                    normalized.append(text)
            return normalized
