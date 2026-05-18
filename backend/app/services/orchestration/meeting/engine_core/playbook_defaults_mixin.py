"""Request-contract playbook input default helpers for MeetingEngine."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.default_input_resolvers import (
    apply_declarative_input_defaults,
    load_playbook_meeting_input_defaults,
)


class MeetingEnginePlaybookDefaultsMixin:
        def _extract_request_contract_playbook_input_defaults(
            self,
            contract: Optional[Dict[str, Any]],
        ) -> List[Dict[str, Any]]:
            """Read generic playbook input bootstrap defaults from the contract."""
            if not isinstance(contract, dict):
                return []

            raw_defaults: List[Dict[str, Any]] = []

            direct_defaults = contract.get("playbook_input_defaults")
            if isinstance(direct_defaults, list):
                raw_defaults.extend(
                    candidate for candidate in direct_defaults if isinstance(candidate, dict)
                )

            governance_constraints = contract.get("governance_constraints")
            if not isinstance(governance_constraints, dict):
                governance_constraints = contract.get("constraints")
            if isinstance(governance_constraints, dict):
                nested_defaults = governance_constraints.get("playbook_input_defaults")
                if isinstance(nested_defaults, list):
                    raw_defaults.extend(
                        candidate
                        for candidate in nested_defaults
                        if isinstance(candidate, dict)
                    )

            attachment_defaults = self._collect_playbook_input_defaults_from_attachments(
                contract.get("context_attachments")
            )
            raw_defaults.extend(attachment_defaults)

            normalized_defaults: List[Dict[str, Any]] = []
            seen_defaults = set()
            for raw_default in raw_defaults:
                normalized = self._normalize_request_contract_playbook_input_default(
                    raw_default
                )
                if not normalized:
                    continue
                default_key = (
                    str(normalized.get("playbook_code") or "").strip(),
                    tuple(normalized.get("deliverable_ids") or []),
                    tuple(sorted(normalized.get("input_params", {}).keys())),
                )
                if default_key in seen_defaults:
                    continue
                seen_defaults.add(default_key)
                normalized_defaults.append(normalized)
            return normalized_defaults

        def _collect_playbook_input_defaults_from_attachments(
            self,
            attachments: Any,
        ) -> List[Dict[str, Any]]:
            if not isinstance(attachments, list):
                return []
            defaults: List[Dict[str, Any]] = []
            for attachment in attachments:
                if not isinstance(attachment, dict):
                    continue
                typed_marker = str(
                    attachment.get("type")
                    or attachment.get("kind")
                    or attachment.get("name")
                    or attachment.get("attachment_type")
                    or ""
                ).strip()
                payload = attachment.get("payload")
                nested_default = attachment.get("playbook_input_default")
                nested_defaults = attachment.get("playbook_input_defaults")

                if typed_marker == "playbook_input_default":
                    if isinstance(payload, dict):
                        defaults.append(payload)
                    elif isinstance(nested_default, dict):
                        defaults.append(nested_default)
                    continue

                if typed_marker == "playbook_input_defaults":
                    if isinstance(payload, list):
                        defaults.extend(
                            candidate for candidate in payload if isinstance(candidate, dict)
                        )
                    elif isinstance(nested_defaults, list):
                        defaults.extend(
                            candidate
                            for candidate in nested_defaults
                            if isinstance(candidate, dict)
                        )
                    continue

                if isinstance(nested_default, dict):
                    defaults.append(nested_default)
                if isinstance(nested_defaults, list):
                    defaults.extend(
                        candidate for candidate in nested_defaults if isinstance(candidate, dict)
                    )
            return defaults

        def _normalize_request_contract_playbook_input_default(
            self,
            raw_default: Dict[str, Any],
        ) -> Optional[Dict[str, Any]]:
            if not isinstance(raw_default, dict):
                return None
            input_params = raw_default.get("input_params")
            if not isinstance(input_params, dict) or not input_params:
                return None

            playbook_code = str(raw_default.get("playbook_code") or "").strip()
            deliverable_ids = self._clean_string_list(
                raw_default.get("deliverable_ids")
                or raw_default.get("handled_deliverable_ids")
            )
            if not playbook_code and not deliverable_ids:
                return None

            normalized: Dict[str, Any] = {
                "input_params": deepcopy(input_params),
            }
            if playbook_code:
                normalized["playbook_code"] = playbook_code
            if deliverable_ids:
                normalized["deliverable_ids"] = deliverable_ids

            source = str(raw_default.get("request_contract_source") or "").strip()
            if source:
                normalized["request_contract_source"] = source
            return normalized

        def _hydrate_action_items_for_policy_gate(
            self, action_items: List[Dict[str, Any]]
        ) -> None:
            """Fill deterministic bootstrap inputs before policy validation."""
            contract = self._get_request_contract_metadata()
            playbook_input_defaults = (
                self._extract_request_contract_playbook_input_defaults(contract)
            )
            deliverables = {
                d.get("id"): d
                for d in contract.get("deliverables", [])
                if isinstance(d, dict) and d.get("id")
            }
            source_message = contract.get("source_message") if contract else ""
            goals = contract.get("goals") if contract else []
            success_criteria = getattr(self.session, "success_criteria", None) or []
            agenda = getattr(self.session, "agenda", None) or []
            lens_id = getattr(self.session, "lens_id", None)
            if self.session.metadata is None:
                self.session.metadata = {}
            if playbook_input_defaults:
                self.session.metadata["request_contract_playbook_input_defaults"] = [
                    {
                        "playbook_code": rule.get("playbook_code"),
                        "deliverable_ids": rule.get("deliverable_ids", []),
                        "source": rule.get("request_contract_source", "explicit"),
                        "input_param_keys": sorted(rule.get("input_params", {}).keys()),
                    }
                    for rule in playbook_input_defaults
                ]
            elif "request_contract_playbook_input_defaults" in self.session.metadata:
                self.session.metadata.pop("request_contract_playbook_input_defaults", None)

            for item in action_items:
                params = item.get("input_params")
                if not isinstance(params, dict):
                    params = {}
                    item["input_params"] = params

                deliverable_id = self._extract_deliverable_id(item)
                deliverable = deliverables.get(deliverable_id or "")
                deliverable_name = (
                    deliverable.get("name")
                    if isinstance(deliverable, dict)
                    else params.get("deliverable_name")
                )

                if lens_id and not params.get("lens_id"):
                    params["lens_id"] = lens_id

                if deliverable_id and not params.get("deliverable_id"):
                    params["deliverable_id"] = deliverable_id
                if deliverable_name and not params.get("deliverable_name"):
                    params["deliverable_name"] = deliverable_name
                if deliverable_id and not params.get("deliverable_path"):
                    params["deliverable_path"] = self._resolve_deliverable_path(
                        deliverable_id=deliverable_id,
                        deliverable_name=deliverable_name,
                    )

                self._apply_request_contract_playbook_input_defaults_to_item(
                    rules=playbook_input_defaults,
                    item=item,
                    params=params,
                    deliverable_id=deliverable_id,
                )
                self._apply_playbook_spec_input_defaults_to_item(
                    item=item,
                    params=params,
                    deliverable_id=deliverable_id,
                    deliverable_name=deliverable_name,
                    source_message=source_message,
                    goals=goals,
                    agenda=agenda,
                    success_criteria=success_criteria,
                    lens_id=lens_id,
                )

        def _apply_request_contract_playbook_input_defaults_to_item(
            self,
            *,
            rules: List[Dict[str, Any]],
            item: Dict[str, Any],
            params: Dict[str, Any],
            deliverable_id: Optional[str],
        ) -> None:
            playbook_code = str(item.get("playbook_code") or "").strip()
            for rule in rules:
                rule_playbook_code = str(rule.get("playbook_code") or "").strip()
                if rule_playbook_code and rule_playbook_code != playbook_code:
                    continue
                deliverable_ids = self._clean_string_list(rule.get("deliverable_ids"))
                if deliverable_ids and deliverable_id not in deliverable_ids:
                    continue
                input_params = rule.get("input_params")
                if not isinstance(input_params, dict):
                    continue
                for key, value in input_params.items():
                    if params.get(key) in (None, "", [], {}):
                        params[key] = deepcopy(value)

        def _apply_playbook_spec_input_defaults_to_item(
            self,
            *,
            item: Dict[str, Any],
            params: Dict[str, Any],
            deliverable_id: Optional[str],
            deliverable_name: Optional[str],
            source_message: str,
            goals: List[Any],
            agenda: List[Any],
            success_criteria: List[Any],
            lens_id: Optional[str],
        ) -> None:
            playbook_code = str(item.get("playbook_code") or "").strip()
            if not playbook_code:
                return
            rules = load_playbook_meeting_input_defaults(playbook_code)
            if not rules:
                return
            apply_declarative_input_defaults(
                params=params,
                rules=rules,
                resolver_context={
                    "item": item,
                    "deliverable_id": deliverable_id,
                    "deliverable_name": deliverable_name,
                    "source_message": source_message,
                    "goals": goals,
                    "agenda": agenda,
                    "success_criteria": success_criteria,
                    "lens_id": lens_id,
                },
            )
