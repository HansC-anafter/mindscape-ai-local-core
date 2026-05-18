"""Request-contract playbook request helpers for MeetingEngine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class MeetingEnginePlaybookRequestsMixin:
        def _apply_request_contract_playbook_requests(
            self,
            *,
            action_items: List[Dict[str, Any]],
            action_intents: Optional[List[Any]],
        ) -> tuple[List[Any], List[Dict[str, Any]]]:
            """Apply deterministic playbook requests carried by the request contract."""
            contract = self._get_request_contract_metadata()
            requested_items = self._extract_request_contract_playbook_requests(contract)
            if not requested_items:
                return action_intents or [], action_items
            replace_codes = {
                code
                for item in requested_items
                for code in self._clean_string_list(item.get("replace_existing_playbook_codes"))
            }
            normalized_items: List[Dict[str, Any]] = []
            replaced_count = 0
            for item in action_items:
                playbook_code = str(item.get("playbook_code") or "").strip()
                if playbook_code and playbook_code in replace_codes:
                    replaced_count += 1
                    continue
                normalized_items.append(item)
            normalized_items.extend(requested_items)

            from backend.app.models.action_intent import ActionIntent

            normalized_intents = [
                ActionIntent.from_action_item_dict(item) for item in normalized_items
            ]
            if self.session.metadata is None:
                self.session.metadata = {}
            self.session.metadata["request_contract_playbook_requests"] = [
                {
                    "playbook_code": item.get("playbook_code"),
                    "intent_id": item.get("intent_id"),
                    "source": item.get("request_contract_source", "explicit"),
                    "replace_existing_playbook_codes": self._clean_string_list(
                        item.get("replace_existing_playbook_codes")
                    ),
                    "handled_deliverable_ids": self._clean_string_list(
                        item.get("handled_deliverable_ids")
                    ),
                }
                for item in requested_items
            ]
            return normalized_intents, normalized_items

        def _extract_request_contract_playbook_requests(
            self,
            contract: Optional[Dict[str, Any]],
        ) -> List[Dict[str, Any]]:
            """Read explicit deterministic playbook requests from the request contract."""
            if not isinstance(contract, dict):
                return []

            raw_requests: List[Dict[str, Any]] = []
            explicit_request_markers = False

            direct_requests = contract.get("playbook_requests")
            if isinstance(direct_requests, list):
                explicit_request_markers = True
                raw_requests.extend(
                    request for request in direct_requests if isinstance(request, dict)
                )

            governance_constraints = contract.get("governance_constraints")
            if not isinstance(governance_constraints, dict):
                governance_constraints = contract.get("constraints")
            if isinstance(governance_constraints, dict):
                nested_requests = governance_constraints.get("playbook_requests")
                if isinstance(nested_requests, list):
                    explicit_request_markers = True
                    raw_requests.extend(
                        request for request in nested_requests if isinstance(request, dict)
                    )

            attachments = contract.get("context_attachments")
            attachment_requests, attachment_markers = self._collect_playbook_requests_from_attachments(
                attachments
            )
            explicit_request_markers = explicit_request_markers or attachment_markers
            raw_requests.extend(attachment_requests)

            normalized_requests: List[Dict[str, Any]] = []
            seen_requests = set()
            for raw_request in raw_requests:
                normalized = self._normalize_request_contract_playbook_request(
                    raw_request=raw_request,
                    contract=contract,
                )
                if not normalized:
                    continue
                request_key = (
                    str(normalized.get("playbook_code") or "").strip(),
                    str(normalized.get("intent_id") or "").strip(),
                )
                if request_key in seen_requests:
                    continue
                seen_requests.add(request_key)
                normalized_requests.append(normalized)
            return normalized_requests

        def _collect_playbook_requests_from_attachments(
            self,
            attachments: Any,
        ) -> tuple[List[Dict[str, Any]], bool]:
            if not isinstance(attachments, list):
                return [], False
            requests: List[Dict[str, Any]] = []
            found_marker = False
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
                nested_request = attachment.get("playbook_request")
                nested_requests = attachment.get("playbook_requests")

                if typed_marker in {"playbook_request", "atomic_playbook_request"}:
                    found_marker = True
                    if isinstance(payload, dict):
                        requests.append(payload)
                    elif isinstance(nested_request, dict):
                        requests.append(nested_request)
                    continue

                if typed_marker in {"playbook_requests", "atomic_playbook_requests"}:
                    found_marker = True
                    if isinstance(payload, list):
                        requests.extend(
                            request for request in payload if isinstance(request, dict)
                        )
                    elif isinstance(nested_requests, list):
                        requests.extend(
                            request
                            for request in nested_requests
                            if isinstance(request, dict)
                        )
                    continue

                if isinstance(nested_request, dict):
                    found_marker = True
                    requests.append(nested_request)
                if isinstance(nested_requests, list):
                    found_marker = True
                    requests.extend(
                        request for request in nested_requests if isinstance(request, dict)
                    )
            return requests, found_marker

        def _normalize_request_contract_playbook_request(
            self,
            *,
            raw_request: Dict[str, Any],
            contract: Dict[str, Any],
        ) -> Optional[Dict[str, Any]]:
            if not isinstance(raw_request, dict):
                return None

            playbook_code = str(raw_request.get("playbook_code") or "").strip()
            if not playbook_code:
                return None

            workspace_id = (
                str(
                    raw_request.get("target_workspace_id")
                    or raw_request.get("workspace_id")
                    or getattr(self.session, "workspace_id", "")
                ).strip()
                or None
            )
            project_id = (
                str(
                    raw_request.get("project_id")
                    or getattr(self, "project_id", None)
                    or ""
                ).strip()
                or None
            )

            input_params = (
                dict(raw_request.get("input_params"))
                if isinstance(raw_request.get("input_params"), dict)
                else {}
            )
            if workspace_id and "workspace_id" not in input_params:
                input_params["workspace_id"] = workspace_id
            if project_id and "project_id" not in input_params:
                input_params["project_id"] = project_id

            title = str(raw_request.get("title") or "").strip() or playbook_code
            description = str(raw_request.get("description") or "").strip() or (
                f"Execute request-contract playbook '{playbook_code}' with explicit "
                "inputs from the upstream contract."
            )
            replacement_codes = self._clean_string_list(
                raw_request.get("replace_existing_playbook_codes")
                or raw_request.get("replace_existing_codes")
            )
            if not replacement_codes:
                replacement_codes = [playbook_code]

            item: Dict[str, Any] = {
                "title": title,
                "description": description,
                "playbook_code": playbook_code,
                "engine": str(raw_request.get("engine") or "").strip()
                or f"playbook:{playbook_code}",
                "priority": str(raw_request.get("priority") or "").strip() or "high",
                "intent_id": str(raw_request.get("intent_id") or "").strip()
                or f"PB_{playbook_code}",
                "input_params": input_params,
                "replace_existing_playbook_codes": replacement_codes,
                "preserve_atomic_playbook": bool(
                    raw_request.get("preserve_atomic_playbook", True)
                ),
            }
            if workspace_id:
                item["target_workspace_id"] = workspace_id

            handled_deliverable_ids = self._clean_string_list(
                raw_request.get("handled_deliverable_ids")
                or raw_request.get("deliverable_ids")
            )
            if handled_deliverable_ids:
                item["handled_deliverable_ids"] = handled_deliverable_ids

            for field_name in (
                "acceptance_tests",
                "governance_constraints",
                "context_attachments",
                "human_instructions",
                "requested_output_type",
                "capability_profile",
            ):
                candidate = raw_request.get(field_name)
                if candidate in (None, "", [], {}):
                    candidate = contract.get(field_name)
                if candidate not in (None, "", [], {}):
                    item[field_name] = candidate

            source = str(raw_request.get("request_contract_source") or "").strip()
            if source:
                item["request_contract_source"] = source

            return item
