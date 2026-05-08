"""
Meeting engine prompt building mixin.

Handles turn prompt construction, locale resolution, project context
injection, history snippets, and convergence detection.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.meeting._prompt_context import (
    append_workspace_identity,
    build_asset_map_context,
    build_lens_context,
    build_previous_decisions_context,
    build_project_context,
    build_workflow_evidence_context,
    format_workspace_identity,
)

logger = logging.getLogger(__name__)

# ── Change 4: Role-specific turn directives (facilitator/planner/critic) ──
_ROLE_TURN_DIRECTIVES: dict[str, str] = {
    "facilitator": (
        "As facilitator, synthesize progress and decide if another round is needed. "
        "If converged, include the marker [CONVERGED]. Keep concise."
    ),
    "planner": (
        "As planner, produce a structured program draft in JSON. "
        "Output a JSON object with a 'workstreams' array. "
        "Each workstream must have: id, name, produces_deliverables (list of deliverable IDs from the contract), "
        "estimated_units (number of tasks), and depends_on (list of workstream IDs). "
        'Schema: {"workstreams": [{"id": "WS1", "name": "...", '
        '"produces_deliverables": ["D1"], "reviews_deliverables": [], '
        '"consumes_deliverables": [], "estimated_units": 10, "depends_on": []}], '
        '"total_estimated_tasks": 30} '
        "EVERY deliverable ID from the contract MUST appear in at least one workstream's "
        "produces_deliverables. Orphan deliverables will cause coverage failure."
    ),
    "critic": (
        "As critic, challenge assumptions, identify risks, and suggest mitigations."
    ),
}

_NATIVE_SPATIAL_PLANNER_DIRECTIVE = (
    "You are the sole spatial planning decision-maker for this turn. "
    "Do NOT ask another facilitator, planner, critic, or user to continue later. "
    "You MUST finish the decision in this one response. "
    "Output ONE final JSON object that can drive downstream spatial execution. "
    'Schema: {"decision_summary":"...",'
    '"actors":[{"id":"actor.primary","role":"...","intent":"..."}],'
    '"objects":[{"id":"object.primary","role":"..."}],'
    '"anchors":[{"id":"anchor.start","purpose":"..."},'
    '{"id":"anchor.target","object_ref":"object.primary","purpose":"..."}],'
    '"blocking_paths":[{"id":"path.primary","actor_ref":"actor.primary","from_anchor":"anchor.start","to_anchor":"anchor.target","carried_object_ref":"object.primary"}],'
    '"camera_blocking":{"camera_id":"camera.main","pattern":"...","keyframes":[{"frame":1,"anchor_id":"anchor.start"},{"frame":72,"anchor_id":"anchor.target"}]},'
    '"performance_beats":[{"id":"beat.primary","actor_ref":"actor.primary","object_ref":"object.primary","anchor_id":"anchor.target","intent":"..."}],'
    '"interaction_beats":[{"id":"interaction.primary","primary_object_ref":"object.primary","interaction":"..."}],'
    '"active_segments":[{"segment_id":"seg.primary","title":"...","entity_refs":["camera.main","actor.primary","object.primary"],"anchor_ids":["anchor.start","anchor.target"]}]'
    "} "
    "Use the smallest bounded world that satisfies the request. "
    "Choose actor, object, anchor, path, beat, interaction, and segment IDs from the user's intent. "
    "Do not reuse example IDs unless the user's request explicitly names those entities. "
    "Prefer one actor, one camera, the minimum required objects, and one primary motion path. "
    "All IDs must be stable and reusable by downstream execution."
)

_FULL_REVIEW_NATIVE_SPATIAL_FACILITATOR_DIRECTIVE = (
    "As facilitator, summarize spatial planning progress, unresolved decisions, and whether another round is needed. "
    "Do NOT converge until the current round includes both a planner spatial proposal and a critic review. "
    "If a Storyboard Acceptance Benchmark is present, do NOT converge while any required card, beat, camera hold, "
    "or canonical ID is still missing or drifting. "
    "If converged, include the marker [CONVERGED]. Keep concise."
)

_FULL_REVIEW_NATIVE_SPATIAL_PLANNER_DIRECTIVE = (
    "As planner, output ONE JSON object describing a bounded spatial planning proposal for this scene. "
    "Required top-level keys: decision_summary, actors, objects, anchors, blocking_paths, camera_blocking, "
    "performance_beats, interaction_beats, active_segments. "
    "Choose the actor, object, anchor, path, camera, and beat IDs yourself from the user's intent unless the request contract "
    "provides a Storyboard Acceptance Benchmark; when it does, preserve those canonical IDs exactly. "
    "Keep the world minimal, replayable, and internally consistent. "
    "Every blocking path must reference defined actors and anchors. "
    "Every camera keyframe must reference defined anchors. "
    "Every performance or interaction beat must reference defined actors or objects. "
    "Use semantic segment titles that match the storyboard phases; do not emit generic titles like segment.1. "
    "Do not compress storyboard phases or beat coverage when a benchmark block is present. "
    "Do not ask another role or the user to finish the proposal later."
)

_FULL_REVIEW_NATIVE_SPATIAL_CRITIC_DIRECTIVE = (
    "As critic, review the planner's spatial planning JSON for gaps, contradictions, and missing execution details. "
    "Check actor/object/anchor continuity, path endpoints, camera coverage, beat completeness, semantic segment titles, "
    "and whether the world stays bounded. "
    "If a Storyboard Acceptance Benchmark is present, explicitly flag ID drift, missing cards, beat compression, "
    "or camera must-hold coverage loss against that benchmark. "
    "Respond with concise findings and concrete change requests. Do not rewrite the full plan."
)

_FULL_REVIEW_NATIVE_SPATIAL_ROLE_OVERRIDES: dict[str, dict[str, object]] = {
    "facilitator": {
        "system_prompt": (
            "You facilitate a spatial planning review meeting and manage convergence."
        ),
        "critical_rules": [
            "NEVER declare convergence before the critic has responded in the current round.",
            "NEVER skip planner proposals — every round must include a planner turn.",
            "NEVER take sides — summarize scene decisions neutrally.",
            "NEVER converge before both a planner spatial proposal and critic review exist.",
        ],
        "communication_style": (
            "Spatial review moderator. Summarize progress, unresolved scene gaps, and the next turn."
        ),
        "success_metrics": [
            "The meeting advances toward a bounded spatial planning proposal.",
            "Convergence happens only after planner and critic contributions exist in the current round.",
        ],
    },
    "planner": {
        "system_prompt": (
            "You design bounded spatial planning proposals for downstream replay and staging."
        ),
        "critical_rules": [
            "NEVER reuse canned IDs or fixed example assets unless the user's intent requires them.",
            "NEVER omit anchors, paths, camera blocking, or performance beats from the proposal.",
            "NEVER leave references dangling — every actor, object, anchor, path, and beat must resolve consistently.",
            "NEVER ignore critic feedback in later rounds.",
        ],
        "communication_style": (
            "Spatial scene planner. Produce compact machine-readable JSON for spatial execution."
        ),
        "success_metrics": [
            "The proposal is bounded, internally consistent, and replayable downstream.",
            "Every referenced entity or anchor is defined exactly once and reused consistently.",
        ],
    },
    "critic": {
        "system_prompt": (
            "You audit spatial planning proposals for continuity, completeness, and replayability."
        ),
        "critical_rules": [
            "NEVER approve a spatial proposal without raising at least one concrete finding or validation point.",
            "NEVER rewrite the full plan — stay in review mode.",
            "NEVER ignore missing anchors, camera coverage gaps, or beat omissions.",
            "NEVER focus on generic project planning when the issue is spatial execution fidelity.",
        ],
        "communication_style": (
            "Spatial reviewer. Format findings as Finding → Impact → Required Change."
        ),
        "success_metrics": [
            "At least one concrete spatial continuity or execution risk is identified per proposal.",
            "Each finding includes a direct change request the planner can address next round.",
        ],
    },
}


class MeetingPromptsMixin:
    """Mixin providing prompt construction methods for MeetingEngine."""

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

    def _build_workspace_instruction_block(self) -> str:
        """Build workspace instruction block for meeting agent turns.

        Meeting agents have their own role definitions (facilitator/planner/
        critic/executor). Workspace instruction is filtered to avoid
        role conflict:
          - persona:    EXCLUDED (would override agent role)
          - anti_goals: EXCLUDED (would reject project-scoped tasks)
          - goals, style_rules, domain_context: INCLUDED as reference

        Returns raw body (no delimiters); caller wraps in its own block.
        Brief fallback is disabled to prevent unfiltered persona leaking.
        """
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        workspace = getattr(self, "workspace", None)
        block, _ = build_workspace_instruction_block(
            workspace,
            caller="meeting",
            exclude_fields=("persona", "anti_goals"),
            fallback_to_brief=False,
            raw_body=True,
        )
        return block

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

    def _build_tool_inventory_block(self) -> str:
        """Build tool inventory for prompt injection.

        Lookup order:
          1. Explicit TOOL bindings (workspace allowlist) — highest priority.
             If RAG cache is available, RAG hits within the allowlist are
             shown first (similarity order), remaining allowlist tools follow.
          2. RAG cache unfiltered — when no explicit bindings exist,
             replaces the 215-line manifest dump with top-K relevant tools.
          3. Installed-pack manifest fallback — unchanged, last resort.
        """
        workspace = getattr(self, "workspace", None)
        workspace_id = (
            getattr(workspace, "id", None)
            or getattr(self, "session", None)
            and self.session.workspace_id
        )
        if not workspace_id:
            return ""

        try:
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )
            from backend.app.models.workspace_resource_binding import ResourceType

            binding_store = WorkspaceResourceBindingStore()
            bindings = binding_store.list_bindings_by_workspace(
                workspace_id, resource_type=ResourceType.TOOL
            )

            if bindings:
                # --- Tier 1: explicit allowlist — RAG reranking within it ---
                allowed_ids = {b.resource_id for b in bindings}
                rag_cache = getattr(self, "_rag_tool_cache", [])
                if rag_cache:
                    hits = [t for t in rag_cache if t["tool_id"] in allowed_ids]
                    rag_ids = {t["tool_id"] for t in hits}
                    rest = [b for b in bindings if b.resource_id not in rag_ids]
                    lines = [f"- {t['tool_id']}: {t['display_name']}" for t in hits]
                    lines += [
                        f"- {b.resource_id}: {(b.overrides or {}).get('display_name', b.resource_id)}"
                        for b in rest
                    ]
                else:
                    lines = [
                        f"- {b.resource_id}: {(b.overrides or {}).get('display_name', b.resource_id)}"
                        for b in bindings
                    ]
                tool_line_count = len(lines)
                logger.debug(
                    "meeting_tool_inventory workspace=%s source=bindings+rag tool_lines=%d",
                    workspace_id,
                    tool_line_count,
                )
                return "\n".join(lines)

            # --- Tier 2: RAG cache (no explicit bindings) ---
            rag_cache = getattr(self, "_rag_tool_cache", [])
            if rag_cache:
                lines = [f"- {t['tool_id']}: {t['display_name']}" for t in rag_cache]
                logger.debug(
                    "meeting_tool_inventory workspace=%s source=rag tool_lines=%d",
                    workspace_id,
                    len(lines),
                )
                return "\n".join(lines)

            # --- Tier 3: manifest fallback (unchanged) ---
            from backend.app.services.stores.installed_packs_store import (
                InstalledPacksStore,
            )
            from pathlib import Path

            try:
                import yaml as _yaml
            except ImportError:
                _yaml = None

            if _yaml is None:
                return ""

            packs_store = InstalledPacksStore()
            pack_ids = packs_store.list_enabled_pack_ids()
            import os

            app_dir = os.getenv("APP_DIR", "/app")
            cap_dirs = [
                Path(app_dir) / "backend" / "app" / "capabilities",
                Path("backend/app/capabilities"),
                Path(os.getenv("DATA_DIR", "data")) / "capabilities",
            ]
            lines = []
            for pack_id in pack_ids:
                for cap_base in cap_dirs:
                    manifest_path = cap_base / pack_id / "manifest.yaml"
                    if not manifest_path.exists():
                        continue
                    try:
                        with manifest_path.open("r", encoding="utf-8") as mf:
                            manifest = _yaml.safe_load(mf) or {}
                        tools = manifest.get("tools", [])
                        for tool in tools:
                            if isinstance(tool, dict):
                                code = tool.get("code", tool.get("name", pack_id))
                                if not code:
                                    continue
                                display = tool.get("display_name", code)
                                code_str = str(code).strip()
                                tool_id = (
                                    code_str
                                    if "." in code_str
                                    else f"{pack_id}.{code_str}"
                                )
                                lines.append(f"- {tool_id}: {display}")
                    except Exception:
                        pass
                    break  # found manifest, skip other cap_dirs
            if lines:
                lines.append("")
                lines.append(
                    "Note: These are system-wide tools. Workspace policy gate "
                    "may restrict which tools are allowed for this workspace."
                )
                logger.debug(
                    "meeting_tool_inventory workspace=%s source=manifest tool_lines=%d",
                    workspace_id,
                    len(lines),
                )
                return "\n".join(lines)

            return ""
        except Exception as exc:
            logger.warning("Failed to build tool inventory: %s", exc)
            return ""

    def _has_workspace_tool_bindings(self) -> bool:
        """Return True when this workspace has actionable tool context.

        Compatibility rules:
          1. Explicit TOOL bindings still count as the strongest signal.
          2. RAG-discovered tools or playbooks also count, so null-tool
             gating still works for RAG-only workspaces.
          3. Manifest fallback alone does not count.
        """
        workspace = getattr(self, "workspace", None)
        workspace_id = getattr(workspace, "id", None) or getattr(
            getattr(self, "session", None), "workspace_id", None
        )

        if workspace_id:
            try:
                from backend.app.services.stores.workspace_resource_binding_store import (
                    WorkspaceResourceBindingStore,
                )
                from backend.app.models.workspace_resource_binding import ResourceType

                store = WorkspaceResourceBindingStore()
                bindings = store.list_bindings_by_workspace(
                    workspace_id, resource_type=ResourceType.TOOL
                )
                if bindings:
                    return True
            except Exception as exc:
                logger.debug("_has_workspace_tool_bindings check failed: %s", exc)

        has_rag_tools = bool(getattr(self, "_rag_tool_cache", []))
        playbooks_cache = getattr(self, "_available_playbooks_cache", "")
        has_playbooks = bool(
            playbooks_cache
            and playbooks_cache
            not in (
                "(no playbooks discovered)",
                "(playbook discovery unavailable)",
            )
        )
        return has_rag_tools or has_playbooks

    # Chinese action-verb → English RAG keywords for cross-lingual recall.
    # These are matched against the user message and appended to the RAG
    # query so that domain-specific Chinese queries still surface the right
    # tool families.
    _VERB_RAG_KEYWORDS: dict[str, str] = {
        "調研": "research academic papers",
        "研究": "research academic frontier",
        "論文": "academic papers fetch",
        "搜尋": "search fetch query",
        "搜索": "search fetch query",
        "製作": "create generate draft content",
        "撰寫": "write draft generate",
        "生成": "generate create build",
        "草稿": "draft content writing",
        "貼文": "post publish content social media",
        "發佈": "publish post schedule",
        "發布": "publish post schedule",
        "排程": "schedule calendar plan",
        "配圖": "image photo visual unsplash",
        "圖片": "image photo visual",
        "分析": "analyze assessment report",
        "規劃": "planning strategy decomposition",
        "品牌": "brand identity CIS",
        "影片": "video chapter ingest render",
        "音頻": "audio sonic embedding",
        "瑜伽": "yoga coach pose asana",
        "網頁": "web generation divi wordpress",
        "SEO": "SEO optimization search engine",
        "補助": "grant scout funding",
        "電子報": "newsletter email campaign",
    }

    def _verb_augment(self, text: str) -> str:
        """Return English RAG keywords matched from Chinese verbs in *text*."""
        if not text:
            return ""
        matched: list[str] = []
        for verb, eng in self._VERB_RAG_KEYWORDS.items():
            if verb in text:
                matched.append(eng)
        return " ".join(matched)

    def _build_tool_query_from_context(self) -> str:
        """Build a text query for RAG tool pre-fetch from meeting context.

        Combines session agenda with the last user message to produce a
        semantically rich query.  Falls back to a generic string.

        When the user message is non-English, matched action-verb keywords
        are appended to improve cross-lingual RAG recall.
        """
        parts: List[str] = []
        agenda = getattr(getattr(self, "session", None), "agenda", None)
        if agenda:
            parts.append(str(agenda)[:300])
        msg = getattr(self, "_last_user_message", None)
        if msg:
            parts.append(str(msg)[:200])
        # Enrich with project context if available
        project = getattr(getattr(self, "session", None), "project_id", None)
        if project:
            parts.append(f"project:{project}")

        # Cross-lingual augmentation
        if msg:
            aug = self._verb_augment(str(msg))
            if aug:
                parts.append(aug)

        return " ".join(parts) or "general task execution"

    def _build_project_context(self) -> str:
        """Fetch project data and recent activity to provide meeting context."""
        return build_project_context(self)

    def _build_asset_map_context(self) -> str:
        """Build workspace group asset map for cross-workspace dispatch routing."""
        return build_asset_map_context(self)

    @staticmethod
    def _format_workspace_identity(ws: Any, parts: List[str]) -> None:
        """Append workspace identity lines from blueprint + suggestions."""
        format_workspace_identity(ws, parts)

    def _append_workspace_identity(
        self, ws_store: Any, ws_id: str, parts: List[str]
    ) -> None:
        """Look up a workspace by ID and append its identity card."""
        append_workspace_identity(self, ws_store, ws_id, parts)

    def _build_lens_context(self) -> str:
        """Build lens context block for prompt injection."""
        return build_lens_context(self)

    def _build_previous_decisions_context(self) -> str:
        """Build previous meeting decisions context from DECISION_FINAL events."""
        return build_previous_decisions_context(self)

    def _build_workflow_evidence_context(self) -> str:
        """Build workflow evidence packet for prompt injection."""
        return build_workflow_evidence_context(self)

    def _build_turn_prompt(
        self,
        role_id: str,
        round_num: int,
        user_message: str,
        decision: Optional[str],
        planner_proposals: List[str],
        critic_notes: List[str],
    ) -> str:
        """Build the full prompt for a single deliberation role turn."""
        history = self._history_snippet()
        agenda = self.session.agenda or [user_message]
        agenda_text = "\n".join([f"- {a}" for a in agenda])
        latest_proposal = planner_proposals[-1] if planner_proposals else "(none)"
        latest_critic = critic_notes[-1] if critic_notes else "(none)"

        locale_map = {
            "zh-TW": "Traditional Chinese (zh-TW)",
            "zh-CN": "Simplified Chinese (zh-CN)",
            "en": "English",
            "ja": "Japanese",
        }
        locale_label = locale_map.get(self._locale, self._locale)
        locale_directive = (
            f"IMPORTANT: All your responses MUST be in {locale_label}. "
            f"Do not mix languages.\n\n"
        )
        project_id = getattr(self, "project_id", None) or getattr(
            self.session, "project_id", None
        )
        minimal_native_spatial_context = self._is_full_review_native_spatial_meeting(
            user_message
        )

        project_block = ""
        if self._project_context:
            project_block = (
                f"=== Project Context ===\n"
                f"{self._project_context}\n"
                f"=== End Project Context ===\n\n"
                f"This meeting is about the project above. "
                f"All discussion, proposals, and action items must be "
                f"relevant to this specific project.\n\n"
            )

        # Inject workspace asset map for cross-workspace dispatch routing
        asset_map_block = ""
        asset_map_ctx = getattr(self, "_asset_map_context", "")
        if asset_map_ctx and not minimal_native_spatial_context:
            asset_map_block = (
                f"=== Workspace Asset Map ===\n"
                f"{asset_map_ctx}\n"
                f"=== End Asset Map ===\n\n"
                f"Use the asset map as context for understanding what data "
                f"is already available. All action items MUST target the "
                f"current workspace — do NOT set target_workspace_id.\n\n"
            )

        common = locale_directive + project_block + asset_map_block

        # Inject available tools block
        tool_ctx = "" if minimal_native_spatial_context else self._build_tool_inventory_block()
        if tool_ctx:
            common += (
                f"=== Available Tools ===\n" f"{tool_ctx}\n" f"=== End Tools ===\n\n"
            )
        # P2 observability: log tool inventory size so session traces are self-contained
        _tool_line_count = len(tool_ctx.strip().splitlines()) if tool_ctx else 0
        logger.debug(
            "meeting_tool_inventory role=%s workspace=%s tool_lines=%d session=%s",
            role_id,
            getattr(getattr(self, "session", None), "workspace_id", "?"),
            _tool_line_count,
            getattr(getattr(self, "session", None), "id", "?"),
        )

        # Inject uploaded files block
        uploaded = getattr(self, "_uploaded_files", [])
        if uploaded and not minimal_native_spatial_context:
            file_lines = []
            for f in uploaded[:10]:
                name = f.get("file_name") or f.get("file_id", "unknown")
                ftype = f.get("file_type", "")
                file_lines.append(f"  - {name} ({ftype})" if ftype else f"  - {name}")
            common += (
                f"=== Uploaded Files ===\n"
                + "\n".join(file_lines)
                + "\n=== End Files ===\n\n"
            )

        common += (
            f"Meeting session: {self.session.id}\n"
            f"Workspace ID: {self.session.workspace_id}\n"
            f"Project ID: {project_id or '(none)'}\n"
            f"Round: {round_num}/{max(1, self.session.max_rounds)}\n"
            f"Agenda:\n{agenda_text}\n\n"
            f"User request:\n{user_message}\n\n"
            f"Current decision draft:\n{decision or '(not finalized)'}\n\n"
            f"Latest planner proposal:\n{latest_proposal}\n\n"
            f"Latest critic note:\n{latest_critic}\n\n"
            f"Recent turns:\n{history}\n\n"
        )
        if not minimal_native_spatial_context:
            affordance_block = self._build_request_affordance_block()
            if affordance_block:
                common += affordance_block
        if minimal_native_spatial_context:
            contract_block = self._build_native_spatial_contract_block()
            if contract_block:
                common += contract_block

        # A1: Inject lens context (AgentSpec Agent Core requirement)
        lens_ctx = "" if minimal_native_spatial_context else self._build_lens_context()
        if lens_ctx:
            common += (
                f"=== Active Lens ===\n"
                f"{lens_ctx}\n"
                f"=== End Lens ===\n\n"
                f"Consider the active lens dimensions when framing your response.\n\n"
            )

        # A1: Inject active intents (AgentSpec Agent Core requirement)
        intent_ids = getattr(self, "_active_intent_ids", [])
        if intent_ids and not minimal_native_spatial_context:
            try:
                intents = self.store.list_intents(
                    self.profile_id,
                    project_id=project_id,
                )
                active = [i for i in intents if i.id in intent_ids]
                if active:
                    intent_lines = []
                    for i in active[:5]:
                        status_val = (
                            i.status.value
                            if hasattr(i.status, "value")
                            else str(i.status)
                        )
                        intent_lines.append(
                            f"  - {i.title} [{status_val}] "
                            f"(progress: {i.progress_percentage}%)"
                        )
                    common += (
                        f"=== Active Intents ===\n"
                        + "\n".join(intent_lines)
                        + "\n=== End Intents ===\n\n"
                    )
            except Exception as exc:
                logger.warning("Failed to inject intents into prompt: %s", exc)

        # A1: Inject previous meeting decisions (Agent Core project memory)
        prev_ctx = (
            "" if minimal_native_spatial_context else self._build_previous_decisions_context()
        )
        if prev_ctx:
            common += (
                f"=== Previous Meeting Decisions ===\n"
                f"{prev_ctx}\n"
                f"=== End Previous Decisions ===\n\n"
            )

        workflow_evidence_ctx = (
            ""
            if minimal_native_spatial_context
            else getattr(self, "_workflow_evidence_context", "")
        )
        if workflow_evidence_ctx:
            common += (
                f"=== Workflow Evidence ===\n"
                f"{workflow_evidence_ctx}\n"
                f"=== End Workflow Evidence ===\n\n"
            )

        # Workspace context as reference (not system-level instruction)
        ws_ctx = "" if minimal_native_spatial_context else self._build_workspace_instruction_block()
        if ws_ctx:
            common += (
                "=== Workspace Context (Reference) ===\n"
                "The following is background context from the workspace. "
                "It does NOT override your deliberation role or the project agenda.\n"
                f"{ws_ctx}\n"
                "=== End Context ===\n\n"
            )

        if role_id == "facilitator":
            if minimal_native_spatial_context:
                return common + _FULL_REVIEW_NATIVE_SPATIAL_FACILITATOR_DIRECTIVE
            return common + _ROLE_TURN_DIRECTIVES["facilitator"]
        if role_id == "planner":
            file_directive = ""
            if getattr(self, "_uploaded_files", None):
                file_directive = (
                    "CONSTRAINT: Uploaded files are present. Your plan MUST include "
                    "at least one step that uses a tool or playbook from Available "
                    "Tools to process these files into structured artifacts. "
                )
            # P2-B: Inject RequestContract deliverables so planner can reference them
            contract_block = ""
            contract = getattr(self, "_request_contract", None)
            if (
                not minimal_native_spatial_context
                and contract
                and hasattr(contract, "deliverables")
                and contract.deliverables
            ):
                d_lines = []
                for d in contract.deliverables:
                    d_lines.append(f"  - {d.id}: {d.name} (qty={d.quantity})")
                contract_block = (
                    f"=== Contract Deliverables ===\n"
                    + "\n".join(d_lines)
                    + "\n=== End Deliverables ===\n\n"
                    "Your workstreams MUST reference these deliverable IDs "
                    "in produces_deliverables / reviews_deliverables fields.\n\n"
                )
            planner_directive = (
                _NATIVE_SPATIAL_PLANNER_DIRECTIVE
                if self._use_native_spatial_planner_mode(role_id, user_message)
                else (
                    _FULL_REVIEW_NATIVE_SPATIAL_PLANNER_DIRECTIVE
                    if minimal_native_spatial_context
                    else _ROLE_TURN_DIRECTIVES["planner"]
                )
            )
            return common + file_directive + contract_block + planner_directive
        if role_id == "critic":
            if minimal_native_spatial_context:
                return common + _FULL_REVIEW_NATIVE_SPATIAL_CRITIC_DIRECTIVE
            file_check = ""
            if getattr(self, "_uploaded_files", None):
                file_check = (
                    "MANDATORY CHECK: Verify the planner's proposal includes "
                    "tool or playbook usage for the uploaded files. If the plan "
                    "only produces text analysis without using available tools, "
                    "flag this as a critical gap. "
                )
            return common + file_check + _ROLE_TURN_DIRECTIVES["critic"]
        # 5A-1: Inject available playbooks for executor
        playbooks_cache = getattr(self, "_available_playbooks_cache", "")
        playbook_block = ""
        if playbooks_cache and role_id == "executor":
            playbook_block = (
                f"=== Available Playbooks ===\n"
                f"{playbooks_cache}\n"
                f"=== End Playbooks ===\n\n"
            )

        # Hard constraint: only enforce when the workspace has EXPLICIT TOOL
        # bindings (admin-configured allowlist).  The manifest fallback is
        # reference-only — we must not force tool usage in pure-discussion
        # sessions where the LLM legitimately has nothing to invoke.
        tool_ctx = self._build_tool_inventory_block()
        has_explicit_bindings = self._has_workspace_tool_bindings()
        has_rag_tools = bool(getattr(self, "_rag_tool_cache", []))
        tool_constraint = ""
        if has_explicit_bindings or has_rag_tools:
            tool_constraint = (
                "MANDATORY: The workspace has been configured with specific tools / "
                "playbooks (see Available Tools / Available Playbooks above). "
                "At least one action item in your JSON array MUST have a non-null "
                "tool_name (chosen exactly from Available Tools) OR a non-null "
                "playbook_code (chosen exactly from Available Playbooks). "
                "Action items with both tool_name=null AND playbook_code=null are "
                "only allowed when no configured tool is relevant to that specific step. "
            )

        return (
            common
            + playbook_block
            + "As executor, produce a JSON array of action items covering all required steps. "
            'Schema: [{"title":"...","description":"...","assigned_to":"executor",'
            '"priority":"low|medium|high","playbook_code":null,'
            '"tool_name":null,"input_params":null,"blocked_by":null}] '
            "playbook_code MUST be selected from Available Playbooks above, or null "
            "if none match. "
            "tool_name is for direct tool invocation without a playbook. "
            "Use tool_name exactly as listed in Available Tools, including the "
            "namespace prefix (e.g., pack.tool). "
            "blocked_by is a list of action item indices (0-based) that must complete first. "
            + tool_constraint
        )

    def _history_snippet(self) -> str:
        """Return a concise summary of recent turn history."""
        if not self._turn_history:
            return "(none)"
        recent = self._turn_history[-6:]
        return "\n".join(
            [f"- R{t['round']} {t['role']}: {t['content'][:220]}" for t in recent]
        )

    def _fallback_turn_text(
        self, role_id: str, round_num: int, user_message: str
    ) -> str:
        """Generate a deterministic fallback turn when LLM is unavailable."""
        if role_id == "facilitator":
            return (
                f"Round {round_num} facilitation summary for '{user_message[:80]}'. "
                "Planner and critic inputs consolidated."
            )
        if role_id == "planner":
            return f"Proposal R{round_num}: execute incrementally, track evidence, and verify outcomes."
        if role_id == "critic":
            return f"Critique R{round_num}: verify data contract, add rollback checks, and test failure paths."
        return json.dumps(
            [
                {
                    "title": "Implement finalized decision",
                    "description": "Translate final meeting decision into executable work.",
                    "assigned_to": "executor",
                    "priority": "medium",
                    "playbook_code": None,
                }
            ]
        )

    def _is_converged(
        self, round_num: int, max_rounds: int, facilitator_text: str
    ) -> bool:
        """Check whether the meeting has converged.

        Uses RoundVerdict.try_parse() for structured convergence checking.
        Stores the parsed verdict on self._last_round_verdict for downstream
        consumers (L2/L3) to inspect confidence and remaining concerns.
        """
        from backend.app.models.layer_artifacts import RoundVerdict

        if round_num >= max_rounds:
            self._last_round_verdict = RoundVerdict(
                converged=True,
                confidence=0.5,
                reason="timebox_exhausted",
                remaining_concerns=["Max rounds reached without explicit convergence"],
            )
            return True

        verdict = RoundVerdict.try_parse(facilitator_text)
        self._last_round_verdict = verdict

        if round_num >= 2 and verdict.converged and verdict.coverage_pass:
            return True

        # If converged but coverage failed, force another round
        if verdict.converged and not verdict.coverage_pass:
            logger.info("Converge blocked: coverage_pass=False")
            return False

        return False

    def _render_minutes(
        self,
        user_message: str,
        decision: str,
        critic_notes: List[str],
        action_items: List[Dict[str, Any]],
        converged: bool,
    ) -> str:
        """Render final meeting minutes as markdown."""
        status = "converged" if converged else "partial"

        # 1. Topic line: prefer project title, fallback to user_message
        topic = self._extract_meeting_topic(user_message)

        # 2. Decision summary: cap at 300 chars
        decision_summary = decision[:300]
        if len(decision) > 300:
            decision_summary += "\n\n_(...truncated)_"

        # 3. Risks summary: cap each critic note at 200 chars
        risk_lines = []
        for note in critic_notes:
            summary = note[:200]
            if len(note) > 200:
                summary += "..."
            risk_lines.append(f"- {summary}")
        risk_text = "\n".join(risk_lines) or "- None"

        # 4. Action Items table
        action_lines = "\n".join(
            [
                (
                    f"| {idx} | {item.get('title', 'Action Item')} | "
                    f"{item.get('assigned_to', 'executor')} | {item.get('priority', 'medium')} |"
                )
                for idx, item in enumerate(action_items, start=1)
            ]
        )
        if not action_lines:
            action_lines = "| 1 | No action item generated | executor | medium |"

        # 5. Agenda from session record (Fix 2), fallback to user_message
        agenda_items = self.session.agenda or [user_message]
        agenda_text = "\n".join([f"- {a}" for a in agenda_items])

        return (
            f"# {topic}\n"
            f"_Meeting {self.session.id[:8]} · {status} · {self.session.round_count} rounds_\n\n"
            f"## Agenda\n{agenda_text}\n\n"
            f"## Decisions\n{decision_summary}\n\n"
            f"## Risks & Concerns\n{risk_text}\n\n"
            "## Action Items\n"
            "| # | Task | Assigned To | Priority |\n"
            "|---|------|-------------|----------|\n"
            f"{action_lines}\n"
        )

    def _assemble_system_message(
        self,
        role_def,
        *,
        role_id: Optional[str] = None,
        user_message: str = "",
    ) -> str:
        """Assemble full system message from role definition fields.

        Combines system_prompt + responsibility_boundary + critical_rules
        + communication_style + success_metrics into a structured block.
        """
        override = None
        if role_id and self._is_full_review_native_spatial_meeting(user_message):
            override = _FULL_REVIEW_NATIVE_SPATIAL_ROLE_OVERRIDES.get(role_id)

        system_prompt = (
            str(override.get("system_prompt"))
            if isinstance(override, dict) and override.get("system_prompt")
            else role_def.system_prompt
        )
        critical_rules = (
            list(override.get("critical_rules") or [])
            if isinstance(override, dict) and override.get("critical_rules")
            else role_def.critical_rules
        )
        communication_style = (
            str(override.get("communication_style"))
            if isinstance(override, dict) and override.get("communication_style")
            else role_def.communication_style
        )
        success_metrics = (
            list(override.get("success_metrics") or [])
            if isinstance(override, dict) and override.get("success_metrics")
            else role_def.success_metrics
        )

        parts = []
        if system_prompt:
            parts.append(system_prompt)

        if role_def.responsibility_boundary:
            parts.append(
                f"\nResponsibility boundary: {role_def.responsibility_boundary}. "
                "Stay strictly within this boundary."
            )

        if critical_rules:
            rules_text = "\n".join(f"- {r}" for r in critical_rules)
            parts.append(f"\nCritical rules you MUST follow:\n{rules_text}")

        if communication_style:
            parts.append(f"\nCommunication style: {communication_style}")

        if success_metrics:
            metrics_text = "\n".join(f"- {m}" for m in success_metrics)
            parts.append(f"\nYour output is successful when:\n{metrics_text}")

        return "\n".join(parts)

    def _extract_meeting_topic(self, user_message: str) -> str:
        """Extract a concise topic line for meeting minutes title."""
        # Prefer project title from context
        project_ctx = getattr(self, "_project_context", "")
        if project_ctx:
            for line in project_ctx.split("\n"):
                if line.startswith("Project:"):
                    return line.replace("Project:", "").strip() + " — Meeting Minutes"

        # Fallback: first 60 chars of user_message
        topic = user_message[:60]
        if len(user_message) > 60:
            topic += "..."
        return f"Meeting Minutes — {topic}"
