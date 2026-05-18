"""Request-contract metadata helpers for MeetingEngine."""

from __future__ import annotations

from typing import Any, Dict, Optional


class MeetingEngineRequestContractMixin:
        def _merge_request_contract_metadata(
            self,
            *,
            contract_data: Optional[Dict[str, Any]],
            handoff_in: Optional[Any],
            user_message: str,
        ) -> Dict[str, Any]:
            """Merge handoff governance payload into request-contract metadata."""
            metadata = dict(contract_data or {})
            if not metadata and handoff_in is None:
                return {}
            metadata.setdefault("source_message", user_message)
            metadata.setdefault("workspace_scope", getattr(self.session, "workspace_id", ""))

            if handoff_in is None:
                normalized_playbook_requests = (
                    self._extract_request_contract_playbook_requests(metadata)
                )
                normalized_playbook_input_defaults = (
                    self._extract_request_contract_playbook_input_defaults(metadata)
                )
                if normalized_playbook_requests:
                    metadata["playbook_requests"] = normalized_playbook_requests
                elif isinstance(metadata.get("playbook_requests"), list):
                    metadata["playbook_requests"] = []
                if normalized_playbook_input_defaults:
                    metadata["playbook_input_defaults"] = (
                        normalized_playbook_input_defaults
                    )
                elif isinstance(metadata.get("playbook_input_defaults"), list):
                    metadata["playbook_input_defaults"] = []
                return metadata

            goals = getattr(handoff_in, "goals", None) or []
            if goals and not metadata.get("goals"):
                metadata["goals"] = list(goals)

            acceptance_tests = getattr(handoff_in, "acceptance_tests", None)
            if acceptance_tests and not metadata.get("acceptance_tests"):
                metadata["acceptance_tests"] = list(acceptance_tests)

            if not metadata.get("deliverables"):
                deliverables = getattr(handoff_in, "deliverables", None) or []
                serialized_deliverables = [
                    deliverable.model_dump()
                    if hasattr(deliverable, "model_dump")
                    else dict(deliverable)
                    for deliverable in deliverables
                    if isinstance(deliverable, dict) or hasattr(deliverable, "model_dump")
                ]
                if serialized_deliverables:
                    metadata["deliverables"] = serialized_deliverables

            contract_constraints = metadata.get("constraints")
            if not isinstance(contract_constraints, dict):
                contract_constraints = {}
            governance_constraints = getattr(handoff_in, "governance_constraints", None)
            if isinstance(governance_constraints, dict) and governance_constraints:
                merged_constraints = dict(contract_constraints)
                for field_name, value in governance_constraints.items():
                    if field_name not in merged_constraints or merged_constraints[field_name] in (
                        None,
                        "",
                        [],
                        {},
                    ):
                        merged_constraints[field_name] = value
                metadata["constraints"] = merged_constraints
                metadata["governance_constraints"] = dict(governance_constraints)
            elif contract_constraints:
                metadata["constraints"] = contract_constraints

            context_attachments = getattr(handoff_in, "context_attachments", None)
            if isinstance(context_attachments, list) and context_attachments:
                metadata["context_attachments"] = [
                    item for item in context_attachments if isinstance(item, dict)
                ]

            handoff_metadata = getattr(handoff_in, "metadata", None)
            if isinstance(handoff_metadata, dict):
                addressable_object_layer = handoff_metadata.get("addressable_object_layer")
                if isinstance(addressable_object_layer, dict) and addressable_object_layer:
                    metadata["addressable_object_layer"] = dict(addressable_object_layer)

            human_instructions = getattr(handoff_in, "human_instructions", None)
            if isinstance(human_instructions, str) and human_instructions.strip():
                metadata["human_instructions"] = human_instructions.strip()

            requested_output_type = getattr(handoff_in, "requested_output_type", None)
            if (
                isinstance(requested_output_type, str)
                and requested_output_type.strip()
                and not metadata.get("requested_output_type")
            ):
                metadata["requested_output_type"] = requested_output_type.strip()

            playbook_requests = getattr(handoff_in, "playbook_requests", None)
            if isinstance(playbook_requests, list) and not metadata.get("playbook_requests"):
                metadata["playbook_requests"] = list(playbook_requests)

            playbook_input_defaults = getattr(handoff_in, "playbook_input_defaults", None)
            if isinstance(playbook_input_defaults, list) and not metadata.get(
                "playbook_input_defaults"
            ):
                metadata["playbook_input_defaults"] = list(playbook_input_defaults)

            normalized_playbook_requests = self._extract_request_contract_playbook_requests(
                metadata
            )
            normalized_playbook_input_defaults = (
                self._extract_request_contract_playbook_input_defaults(metadata)
            )
            if normalized_playbook_requests:
                metadata["playbook_requests"] = normalized_playbook_requests
            elif isinstance(metadata.get("playbook_requests"), list):
                metadata["playbook_requests"] = []
            if normalized_playbook_input_defaults:
                metadata["playbook_input_defaults"] = normalized_playbook_input_defaults
            elif isinstance(metadata.get("playbook_input_defaults"), list):
                metadata["playbook_input_defaults"] = []

            self._apply_quality_target_to_request_contract_metadata(metadata)
            return metadata

        @classmethod
        def _apply_quality_target_to_request_contract_metadata(
            cls,
            metadata: Dict[str, Any],
        ) -> None:
            quality_requirements = cls._quality_requirements_from_contract_metadata(metadata)
            scene_count = cls._target_scene_count_from_quality_requirements(
                quality_requirements
            )
            if scene_count <= 1:
                return

            deliverables = metadata.get("deliverables")
            if not isinstance(deliverables, list) or not deliverables:
                metadata["deliverables"] = [
                    {
                        "id": "D1",
                        "name": f"{scene_count}-scene storyboard",
                        "quantity": scene_count,
                        "requires": [],
                        "acceptance_criteria": [],
                    }
                ]
            else:
                total_quantity = 0
                for item in deliverables:
                    if not isinstance(item, dict):
                        continue
                    try:
                        total_quantity += max(1, int(item.get("quantity", 1)))
                    except (TypeError, ValueError):
                        total_quantity += 1
                if total_quantity < scene_count:
                    first_deliverable = deliverables[0]
                    if isinstance(first_deliverable, dict):
                        first_deliverable["quantity"] = scene_count
                        if not str(first_deliverable.get("name") or "").strip():
                            first_deliverable["name"] = f"{scene_count}-scene storyboard"

            metadata["scale_estimate"] = cls._scale_estimate_from_total_units(scene_count)

        @staticmethod
        def _quality_requirements_from_contract_metadata(
            metadata: Dict[str, Any],
        ) -> Dict[str, Any]:
            candidates = []
            if isinstance(metadata, dict):
                candidates.append(metadata.get("quality_requirements"))
                constraints = metadata.get("constraints")
                if isinstance(constraints, dict):
                    candidates.append(constraints.get("quality_requirements"))
                addressable_object_layer = metadata.get("addressable_object_layer")
                if isinstance(addressable_object_layer, dict):
                    candidates.append(addressable_object_layer.get("quality_requirements"))
            for candidate in candidates:
                if isinstance(candidate, dict) and candidate:
                    return candidate
            return {}

        @staticmethod
        def _target_scene_count_from_quality_requirements(
            quality_requirements: Dict[str, Any],
        ) -> int:
            target = (
                quality_requirements.get("target")
                if isinstance(quality_requirements, dict)
                else None
            )
            if not isinstance(target, dict):
                return 0
            for key in ("scene_count_target", "scene_count", "min_scene_count", "scene_count_floor"):
                try:
                    value = int(target.get(key, 0) or 0)
                except (TypeError, ValueError):
                    value = 0
                if value > 1:
                    return value
            return 0

        @staticmethod
        def _scale_estimate_from_total_units(total_units: int) -> str:
            if total_units <= 3:
                return "trivial"
            if total_units <= 15:
                return "standard"
            if total_units <= 50:
                return "program"
            return "campaign"

        def _get_request_contract_metadata(self) -> Dict[str, Any]:
            metadata = getattr(self.session, "metadata", None)
            if not isinstance(metadata, dict):
                return {}
            contract = metadata.get("request_contract")
            return contract if isinstance(contract, dict) else {}
