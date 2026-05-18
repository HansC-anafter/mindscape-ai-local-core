"""Native spatial prompt helpers for MeetingPromptsMixin."""

from typing import Any, Dict, List


class MeetingPromptNativeSpatialMixin:
    def _matches_native_spatial_topic(self, user_message: str) -> bool:
        text = " ".join(
            [
                str(user_message or ""),
                " ".join(str(item or "") for item in (self.session.agenda or [])),
                str(getattr(self.session, "title", "") or ""),
            ]
        ).lower()
        explicit_phrases = (
            "native spatial",
            "spatial pd",
            "spatial schedule",
            "spatial execution",
            "spatial handoff",
            "spatial blocking",
            "bounded spatial",
            "downstream spatial",
            "blender downstream",
            "world handoff",
        )
        if any(phrase in text for phrase in explicit_phrases):
            return True
        has_spatial = "spatial" in text
        has_runtime_target = any(
            word in text
            for word in (
                "handoff",
                "blocking",
                "anchor",
                "world",
                "blender",
                "downstream",
            )
        )
        return has_spatial and has_runtime_target

    def _is_full_review_native_spatial_meeting(self, user_message: str) -> bool:
        runtime_id = str(getattr(self, "executor_runtime", "") or "").strip().lower()
        if runtime_id != "codex_cli":
            return False
        if self._has_external_playbook_affordance_contract():
            return False
        requires_full_review = False
        review_gate = getattr(self, "_requires_full_deliberation_review", None)
        if callable(review_gate):
            try:
                requires_full_review = bool(review_gate())
            except Exception:
                requires_full_review = False
        if not requires_full_review:
            return False
        return self._matches_native_spatial_topic(user_message)

    def _has_external_playbook_affordance_contract(self) -> bool:
        contract = self._prompt_request_contract_metadata()
        if not contract:
            return False
        governance_constraints = contract.get("governance_constraints")
        if not isinstance(governance_constraints, dict):
            governance_constraints = contract.get("constraints")
        if not isinstance(governance_constraints, dict):
            governance_constraints = {}

        aol = contract.get("addressable_object_layer")
        if not isinstance(aol, dict):
            aol = governance_constraints.get("addressable_object_layer")
        if isinstance(aol, dict):
            candidate_playbooks = aol.get("candidate_playbooks")
            if isinstance(candidate_playbooks, list) and any(
                isinstance(item, dict) and item.get("playbook_code")
                for item in candidate_playbooks
            ):
                return True

        quality_requirements = contract.get("quality_requirements")
        if not isinstance(quality_requirements, dict):
            quality_requirements = governance_constraints.get("quality_requirements")
        if isinstance(quality_requirements, dict):
            target = quality_requirements.get("target")
            if isinstance(target, dict) and any(
                target.get(key)
                for key in (
                    "deliverable_kind",
                    "scene_count",
                    "visual_scope",
                    "target_platform",
                )
            ):
                return True
        return False

    def _prompt_request_contract_metadata(self) -> Dict[str, Any]:
        getter = getattr(self, "_get_request_contract_metadata", None)
        if callable(getter):
            try:
                contract = getter()
            except Exception:
                contract = {}
            if isinstance(contract, dict):
                return contract
        metadata = getattr(getattr(self, "session", None), "metadata", None)
        if isinstance(metadata, dict):
            contract = metadata.get("request_contract")
            if isinstance(contract, dict):
                return contract
        return {}

    def _extract_native_spatial_storyboard_acceptance(self) -> Dict[str, Any]:
        contract = self._prompt_request_contract_metadata()
        governance_constraints = contract.get("governance_constraints")
        if not isinstance(governance_constraints, dict):
            governance_constraints = contract.get("constraints")
        if not isinstance(governance_constraints, dict):
            return {}
        spatial_schedule = governance_constraints.get("spatial_schedule")
        if not isinstance(spatial_schedule, dict):
            return {}
        candidate = spatial_schedule.get("storyboard_acceptance")
        return dict(candidate) if isinstance(candidate, dict) else {}

    @staticmethod
    def _render_native_spatial_storyboard_benchmark(
        benchmark: Dict[str, Any],
    ) -> str:
        acceptance_checks = (
            dict(benchmark.get("acceptance_checks") or {})
            if isinstance(benchmark.get("acceptance_checks"), dict)
            else {}
        )
        lines: List[str] = []
        storyboard_id = str(benchmark.get("storyboard_id") or "").strip()
        if storyboard_id:
            lines.append(f"Storyboard ID: {storyboard_id}")
        intent_summary = str(benchmark.get("intent_summary") or "").strip()
        if intent_summary:
            lines.append(f"Intent: {intent_summary}")
        production_bar = str(benchmark.get("production_bar") or "").strip()
        if production_bar:
            lines.append(f"Production bar: {production_bar}")

        for label, values in (
            ("Canonical actor IDs", acceptance_checks.get("required_actor_ids") or []),
            ("Canonical object IDs", acceptance_checks.get("required_object_ids") or []),
            ("Canonical anchor IDs", acceptance_checks.get("required_anchor_ids") or []),
            (
                "Required performance beats",
                acceptance_checks.get("required_performance_beats") or [],
            ),
            (
                "Required interaction beats",
                acceptance_checks.get("required_interaction_beats") or [],
            ),
            (
                "Required segment titles",
                acceptance_checks.get("required_segment_titles") or [],
            ),
            (
                "Camera must-hold",
                acceptance_checks.get("required_camera_must_hold") or [],
            ),
        ):
            normalized = [str(item).strip() for item in values if str(item).strip()]
            if normalized:
                lines.append(f"{label}: {', '.join(normalized)}")

        camera_pattern = str(
            acceptance_checks.get("required_camera_pattern") or ""
        ).strip()
        if camera_pattern:
            lines.append(f"Camera pattern: {camera_pattern}")

        cards = [
            card for card in list(benchmark.get("storyboard_cards") or []) if isinstance(card, dict)
        ]
        if cards:
            lines.append("Storyboard cards:")
            for card in cards:
                title = str(card.get("title") or card.get("card_id") or "").strip()
                beat_ids = [
                    str(item).strip()
                    for item in list(card.get("required_beat_ids") or [])
                    if str(item).strip()
                ]
                segment_title = str(
                    card.get("required_segment_title") or card.get("title") or ""
                ).strip()
                summary_bits: List[str] = []
                if segment_title:
                    summary_bits.append(f"segment={segment_title}")
                if beat_ids:
                    summary_bits.append(f"beats={', '.join(beat_ids)}")
                note_items = [
                    str(item).strip()
                    for item in list(card.get("notes") or [])
                    if str(item).strip()
                ]
                if note_items:
                    summary_bits.append(f"notes={' | '.join(note_items)}")
                if title:
                    lines.append(f"- {title}: {'; '.join(summary_bits)}")

        return "\n".join(lines)

    def _build_native_spatial_contract_block(self) -> str:
        contract = self._prompt_request_contract_metadata()
        sections: List[str] = []
        human_instructions = str(contract.get("human_instructions") or "").strip()
        if human_instructions:
            sections.append(
                "=== Handoff Instructions ===\n"
                f"{human_instructions}\n"
                "=== End Handoff Instructions ===\n\n"
            )
        benchmark = self._extract_native_spatial_storyboard_acceptance()
        if benchmark:
            sections.append(
                "=== Storyboard Acceptance Benchmark ===\n"
                f"{self._render_native_spatial_storyboard_benchmark(benchmark)}\n"
                "=== End Storyboard Acceptance Benchmark ===\n\n"
            )
        return "".join(sections)

    def _build_request_affordance_block(self) -> str:
        contract = self._prompt_request_contract_metadata()
        if not contract:
            return ""
        governance_constraints = contract.get("governance_constraints")
        if not isinstance(governance_constraints, dict):
            governance_constraints = contract.get("constraints")
        if not isinstance(governance_constraints, dict):
            governance_constraints = {}
        aol = contract.get("addressable_object_layer")
        if not isinstance(aol, dict):
            aol = governance_constraints.get("addressable_object_layer")
        if not isinstance(aol, dict):
            aol = {}

        lines: List[str] = []
        human_instructions = str(contract.get("human_instructions") or "").strip()
        if human_instructions:
            lines.append(f"Handoff instructions: {human_instructions}")

        quality_requirements = contract.get("quality_requirements")
        if not isinstance(quality_requirements, dict):
            quality_requirements = governance_constraints.get("quality_requirements")
        if isinstance(quality_requirements, dict) and quality_requirements:
            target = quality_requirements.get("target")
            target_bits: List[str] = []
            if isinstance(target, dict):
                for key in (
                    "deliverable_kind",
                    "scene_count",
                    "min_scene_count",
                    "duration_sec",
                    "visual_scope",
                    "target_platform",
                ):
                    value = target.get(key)
                    if value not in (None, "", [], {}):
                        target_bits.append(f"{key}={value}")
            gate_bits = [
                key
                for key in (
                    "grounding_required",
                    "require_scene_judge",
                    "require_visual_scope_gate",
                    "strict_acceptance_required",
                    "rewrite_until_quality_passed",
                    "require_real_prompt_regression",
                )
                if quality_requirements.get(key) is True
            ]
            if target_bits:
                lines.append("Quality target: " + ", ".join(target_bits))
            if gate_bits:
                lines.append("Required gates: " + ", ".join(gate_bits))

        selected_refs = aol.get("selected_object_refs")
        if isinstance(selected_refs, list) and selected_refs:
            ref_ids = [
                str(ref.get("object_id") or ref.get("uri") or "").strip()
                for ref in selected_refs
                if isinstance(ref, dict) and (ref.get("object_id") or ref.get("uri"))
            ]
            if ref_ids:
                lines.append("Selected object refs: " + ", ".join(ref_ids[:12]))

        candidate_playbooks = aol.get("candidate_playbooks")
        if isinstance(candidate_playbooks, list) and candidate_playbooks:
            lines.append("Candidate playbooks available for selection:")
            seen = set()
            for candidate in candidate_playbooks[:12]:
                if not isinstance(candidate, dict):
                    continue
                playbook_code = str(candidate.get("playbook_code") or "").strip()
                if not playbook_code or playbook_code in seen:
                    continue
                seen.add(playbook_code)
                pack_code = str(candidate.get("pack_code") or "").strip()
                source = str(candidate.get("source") or "candidate").strip()
                confidence = str(candidate.get("confidence") or "").strip()
                prefix = f"{pack_code}.{playbook_code}" if pack_code else playbook_code
                suffix = f"source={source}"
                if confidence:
                    suffix += f", confidence={confidence}"
                lines.append(f"  - {prefix} ({suffix})")

        if not lines:
            return ""
        return (
            "=== Request Affordances ===\n"
            + "\n".join(lines)
            + "\nUse these affordances as planning evidence. Choose a candidate playbook only when it matches the contract deliverables and quality gates.\n"
            "=== End Request Affordances ===\n\n"
        )

    def _use_native_spatial_planner_mode(
        self, role_id: str, user_message: str
    ) -> bool:
        if role_id != "planner":
            return False
        if self._has_external_playbook_affordance_contract():
            return False
        if self._is_full_review_native_spatial_meeting(user_message):
            return False
        runtime_id = str(getattr(self, "executor_runtime", "") or "").strip().lower()
        if runtime_id != "codex_cli":
            return False
        return self._matches_native_spatial_topic(user_message)
