"""Deliberation loop helpers for MeetingEngine."""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from backend.app.models.meeting_session import MeetingStatus
from backend.app.services.orchestration.meeting_agents import (
    DeliberationDepth,
    DEPTH_ROUND_CAPS,
    select_deliberation_depth,
)

logger = logging.getLogger(__name__)


class MeetingEngineDeliberationMixin:
        async def _stage_deliberation(
            self,
            user_message: str,
        ) -> tuple:
            """S3: Multi-round role deliberation loop.

            Returns:
                (decision, planner_proposals, critic_notes, converged)
            """
            self._start_session()
            base_max_rounds = max(1, int(getattr(self.session, "max_rounds", 1)))

            agenda = getattr(self.session, "agenda", None) or []
            depth = select_deliberation_depth(
                agenda_items=len(agenda),
                estimated_action_count=len(agenda),
                has_tool_ambiguity=len(self._rag_tool_cache) > 15,
                budget_headroom_pct=self.ctx.budget_headroom_pct,
            )
            if self._requires_full_deliberation_review() and depth == DeliberationDepth.SHALLOW:
                depth = DeliberationDepth.STANDARD
            self._deliberation_depth = depth
            max_rounds = min(
                base_max_rounds, DEPTH_ROUND_CAPS.get(depth.value, base_max_rounds)
            )
            logger.info(
                "Meeting depth=%s max_rounds=%d (base=%d) session=%s",
                depth.value,
                max_rounds,
                base_max_rounds,
                self.session.id,
            )

            planner_proposals: List[str] = []
            critic_notes: List[str] = []
            converged = False
            run_error: Optional[Exception] = None
            require_full_review = self._requires_full_deliberation_review()
            single_turn_native_spatial = self._should_use_single_turn_native_spatial_planner(
                user_message
            )

            try:
                if single_turn_native_spatial:
                    round_num = 1
                    self.orchestrator.record_iteration()
                    self._emit_round_event(round_num, status="started")
                    await self._emit_meeting_stage(
                        "deliberation",
                        "Round 1/1 - Native spatial planner closure in progress...",
                    )
                    planner_turn = await self._role_turn(
                        "planner",
                        round_num,
                        user_message,
                        planner_proposals=planner_proposals,
                        critic_notes=critic_notes,
                    )
                    planner_proposals.append(planner_turn.content)
                    self._emit_turn(planner_turn)
                    self._emit_decision_proposal(planner_turn)
                    native_spatial_payload = self._extract_native_spatial_payload(
                        planner_turn.content
                    )
                    if native_spatial_payload:
                        if self.session.metadata is None:
                            self.session.metadata = {}
                        self.session.metadata["native_spatial_decision"] = (
                            native_spatial_payload
                        )
                        self.session.metadata["native_spatial_source"] = (
                            "planner_single_turn"
                        )
                    await self._try_coverage_audit(planner_turn.content, round_num)
                    self.session.round_count = round_num
                    converged = True
                    self._emit_round_event(round_num, status="converged")
                else:
                    for round_num in range(1, max_rounds + 1):
                        if self.orchestrator.should_stop():
                            self._emit_round_event(round_num, status="budget_exhausted")
                            break

                        self.orchestrator.record_iteration()
                        self._emit_round_event(round_num, status="started")

                        await self._emit_meeting_stage(
                            "deliberation",
                            f"Round {round_num}/{max_rounds} - Facilitator turn in progress...",
                        )
                        facilitator_turn = await self._role_turn(
                            "facilitator",
                            round_num,
                            user_message,
                            planner_proposals=planner_proposals,
                            critic_notes=critic_notes,
                        )
                        self._emit_turn(facilitator_turn)

                        await self._emit_meeting_stage(
                            "deliberation",
                            f"Round {round_num}/{max_rounds} - Planner turn in progress...",
                        )
                        planner_turn = await self._role_turn(
                            "planner",
                            round_num,
                            user_message,
                            planner_proposals=planner_proposals,
                            critic_notes=critic_notes,
                        )
                        planner_proposals.append(planner_turn.content)
                        self._emit_turn(planner_turn)
                        self._emit_decision_proposal(planner_turn)

                        # G2: Run CoverageAuditor after planner turn
                        await self._try_coverage_audit(planner_turn.content, round_num)

                        # Skip critic in SHALLOW depth to reduce latency
                        if depth != DeliberationDepth.SHALLOW:
                            await self._emit_meeting_stage(
                                "deliberation",
                                f"Round {round_num}/{max_rounds} - Critic review in progress...",
                            )
                            critic_turn = await self._role_turn(
                                "critic",
                                round_num,
                                user_message,
                                planner_proposals=planner_proposals,
                                critic_notes=critic_notes,
                            )
                            critic_notes.append(critic_turn.content)
                            self._emit_turn(critic_turn)

                        self.session.round_count = round_num
                        if self._is_converged(
                            round_num, max_rounds, facilitator_turn.content
                        ):
                            converged = True
                            self._emit_round_event(round_num, status="converged")
                            break

                        self._emit_round_event(round_num, status="completed")
            except Exception as exc:
                run_error = exc
                logger.error(
                    "Meeting engine failed at round %s: %s",
                    self.session.round_count,
                    exc,
                )
                self.session.status = MeetingStatus.FAILED
                self.session.end()

                # Generate partial minutes from completed rounds
                if self.session.round_count > 0 and planner_proposals:
                    self.session.metadata["partial_rounds"] = self.session.round_count
                    try:
                        partial_decision = planner_proposals[-1]
                        self._emit_decision_final(
                            decision=partial_decision,
                            round_number=self.session.round_count,
                        )
                        minutes_md = self._render_minutes(
                            user_message=user_message,
                            decision=partial_decision,
                            critic_notes=critic_notes,
                            action_items=[],
                            converged=False,
                        )
                        self.session.minutes_md = minutes_md
                        self._emit_minutes_message(minutes_md)
                        logger.info(
                            "Partial minutes generated for %d completed rounds",
                            self.session.round_count,
                        )
                    except Exception as minutes_err:
                        logger.warning(
                            "Failed to generate partial minutes: %s", minutes_err
                        )

                try:
                    self.session_store.update(self.session)
                except Exception:
                    logger.warning("Failed to persist partial meeting session state")

            if run_error:
                raise RuntimeError(
                    f"Meeting failed at round {self.session.round_count}: {run_error}"
                ) from run_error

            if require_full_review and not critic_notes:
                raise RuntimeError(
                    "Full deliberation review required but no critic turn completed"
                )

            decision = (
                planner_proposals[-1] if planner_proposals else "No decision proposed."
            )
            self._emit_decision_final(
                decision=decision, round_number=self.session.round_count
            )
            return decision, planner_proposals, critic_notes, converged

        def _requires_full_deliberation_review(self) -> bool:
            contract = self._get_request_contract_metadata()
            governance_constraints = contract.get("governance_constraints")
            if not isinstance(governance_constraints, dict):
                governance_constraints = contract.get("constraints")
            if not isinstance(governance_constraints, dict):
                governance_constraints = {}

            for key in (
                "meeting_review",
                "meeting",
                "spatial_schedule",
            ):
                candidate = governance_constraints.get(key)
                if not isinstance(candidate, dict):
                    continue
                for flag_name in (
                    "require_full_deliberation_review",
                    "require_critic_turn",
                    "disable_single_turn_native_pd",
                ):
                    if bool(candidate.get(flag_name)):
                        return True
            quality_requirements = self._quality_requirements_from_contract_metadata(contract)
            if quality_requirements:
                content_quality = quality_requirements.get("content_quality")
                if not isinstance(content_quality, dict):
                    content_quality = {}
                if any(
                    bool(content_quality.get(key))
                    for key in (
                        "require_per_scene_judge",
                        "require_reference_grounding",
                        "require_concrete_scene_copy",
                    )
                ):
                    return True
                if any(
                    bool(quality_requirements.get(key))
                    for key in (
                        "rewrite_until_quality_passed",
                        "producer_review_required",
                        "human_review_required_before_publish",
                    )
                ):
                    return True
                target_scene_count = self._target_scene_count_from_quality_requirements(
                    quality_requirements
                )
                if target_scene_count >= 10:
                    return True
            return False

        def _should_use_single_turn_native_spatial_planner(self, user_message: str) -> bool:
            if self._requires_full_deliberation_review():
                return False
            affordance_guard = getattr(self, "_has_external_playbook_affordance_contract", None)
            if callable(affordance_guard) and affordance_guard():
                return False
            runtime_id = str(getattr(self, "executor_runtime", "") or "").strip().lower()
            if runtime_id != "codex_cli":
                return False
            topic_matcher = getattr(self, "_matches_native_spatial_topic", None)
            if callable(topic_matcher):
                return bool(topic_matcher(user_message))
            return False

        async def _role_turn(
            self,
            role_id: str,
            round_num: int,
            user_message: str,
            decision: Optional[str] = None,
            planner_proposals: Optional[List[str]] = None,
            critic_notes: Optional[List[str]] = None,
        ) -> RoleTurnResult:
            """Execute a single deliberation role turn with prompt construction and LLM generation."""
            self.orchestrator.record_turn()
            role_def = self._roster[role_id]
            role = role_def.agent_name

            prompt = self._build_turn_prompt(
                role_id=role_id,
                round_num=round_num,
                user_message=user_message,
                decision=decision,
                planner_proposals=planner_proposals or [],
                critic_notes=critic_notes or [],
            )
            system_content = self._assemble_system_message(
                role_def,
                role_id=role_id,
                user_message=user_message,
            )
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ]

            try:
                content = (
                    await self._generate_text(
                        messages,
                        capability_profile=role_def.capability_profile,
                    )
                ).strip()
                if not content:
                    raise ValueError("empty LLM content")
            except Exception as exc:
                self.orchestrator.record_error()
                logger.error(
                    "MeetingEngine turn failed for %s (round=%s): %s",
                    role_id,
                    round_num,
                    exc,
                )
                raise RuntimeError(
                    f"Meeting turn failed for role '{role_id}' at round {round_num}: {exc}"
                ) from exc

            turn = self._role_turn_result_class()(
                role_id=role_id,
                role_name=role,
                round_number=round_num,
                content=content,
                converged=round_num >= 2,
            )
            self._turn_history.append(
                {
                    "round": round_num,
                    "role_id": role_id,
                    "role": role,
                    "content": content,
                }
            )
            return turn
