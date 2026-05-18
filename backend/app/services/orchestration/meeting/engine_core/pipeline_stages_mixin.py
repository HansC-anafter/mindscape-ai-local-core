"""Pipeline stage helpers for MeetingEngine."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.meeting._dispatch_pipeline import (
    stage_decompose_and_dispatch as meeting_stage_decompose_and_dispatch,
    stage_finalize as meeting_stage_finalize,
)

logger = logging.getLogger(__name__)

_MEETING_RAG_PREFETCH_TIMEOUT_SECONDS = 5.0


class MeetingEnginePipelineStagesMixin:
        async def _stage_agenda_and_rag(self, user_message: str) -> None:
            """S1: Agenda decomposition + RAG tool pre-fetch."""
            await self._emit_meeting_stage("agenda", "Analyzing agenda...")
            await self._ensure_agenda_decomposed(user_message)

            # Pre-fetch RAG tool results using per-agenda multi-query strategy.
            # Each agenda item gets its own focused query so that mixed requests
            # (e.g. "research + content + images") don't let one dominant capability
            # crowd out the others.
            self._rag_tool_cache: list = []
            try:
                from backend.app.services.tool_rag import retrieve_relevant_tools

                agenda = getattr(self.session, "agenda", None) or []
                ws_id = self.session.workspace_id

                async def _lookup_tools(query: str, top_k: int) -> list[dict]:
                    try:
                        return await asyncio.wait_for(
                            retrieve_relevant_tools(
                                query,
                                top_k=top_k,
                                workspace_id=ws_id,
                            ),
                            timeout=_MEETING_RAG_PREFETCH_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Meeting RAG pre-fetch timed out for session %s query=%r",
                            getattr(self.session, "id", "?"),
                            str(query)[:120],
                        )
                        return []

                if agenda and len(agenda) > 1:
                    per_k = max(5, 40 // len(agenda))
                    seen_ids: set = set()
                    combined: list = []
                    for item in agenda:
                        aug = self._verb_augment(str(item))
                        q = f"{item} {aug}".strip() if aug else str(item)
                        hits = await _lookup_tools(q, per_k)
                        for h in hits:
                            if h["tool_id"] not in seen_ids:
                                seen_ids.add(h["tool_id"])
                                combined.append(h)

                    msg_aug = self._verb_augment(str(user_message))
                    msg_q = f"{user_message} {msg_aug}".strip()
                    msg_hits = await _lookup_tools(msg_q, per_k)
                    for h in msg_hits:
                        if h["tool_id"] not in seen_ids:
                            seen_ids.add(h["tool_id"])
                            combined.append(h)

                    self._rag_tool_cache = combined
                else:
                    self._rag_tool_cache = await _lookup_tools(
                        self._build_tool_query_from_context(),
                        40,
                    )

                logger.debug(
                    "Meeting RAG pre-fetch: %d tools cached for session %s (queries=%d)",
                    len(self._rag_tool_cache),
                    self.session.id if hasattr(self, "session") and self.session else "?",
                    max(len(agenda), 1),
                )
            except Exception as exc:
                logger.warning(
                    "Meeting RAG pre-fetch failed (manifest fallback active): %s", exc
                )

            await self._emit_meeting_stage("tool_discovery", "Discovering available tools...")

        async def _stage_compile_contract(
            self,
            user_message: str,
            handoff_in: Optional[Any] = None,
        ) -> None:
            """S2: Preload playbooks + compile RequestContract."""
            self._available_playbooks_cache = await self._async_load_installed_playbooks()

            await self._emit_meeting_stage("deliberation", "Starting multi-role deliberation...")

            self._request_contract = None
            try:
                from backend.app.models.request_contract import RequestContract

                agenda = getattr(self.session, "agenda", None) or []
                self._request_contract = await RequestContract.compile_with_llm(
                    user_message=user_message,
                    agenda=agenda,
                    workspace_id=getattr(self.session, "workspace_id", ""),
                    model_name=self.model_name,
                    llm_generate_fn=self._generate_text,
                )
                if self.session.metadata is None:
                    self.session.metadata = {}
                self.session.metadata["request_contract"] = (
                    self._request_contract.model_dump()
                )
                logger.info(
                    "RequestContract compiled: %d deliverables, scale=%s",
                    len(self._request_contract.deliverables),
                    self._request_contract.scale_estimate.value,
                )
            except Exception as exc:
                logger.warning("RequestContract compile failed (non-fatal): %s", exc)

            request_contract_metadata = self._merge_request_contract_metadata(
                contract_data=(
                    self._request_contract.model_dump()
                    if self._request_contract is not None
                    else None
                ),
                handoff_in=handoff_in,
                user_message=user_message,
            )
            if request_contract_metadata:
                if self.session.metadata is None:
                    self.session.metadata = {}
                self.session.metadata["request_contract"] = request_contract_metadata
                try:
                    from backend.app.models.request_contract import RequestContract

                    self._request_contract = RequestContract.model_validate(
                        request_contract_metadata
                    )
                except Exception:
                    logger.debug(
                        "RequestContract metadata contains extensions beyond the core schema"
                    )

        async def _stage_extract_actions(
            self,
            decision: str,
            user_message: str,
            critic_notes: List[str],
            planner_proposals: List[str],
        ) -> tuple:
            """S4: Build ActionIntents + null-tool gate retry.

            Returns:
                (action_intents, action_items) where action_items are legacy dicts.
            """
            await self._emit_meeting_stage("action_items", "Expanding action items...")
            if self._should_use_single_turn_native_spatial_planner(
                user_message
            ) or self._is_full_review_native_spatial_meeting(user_message):
                native_action_intents = self._build_native_spatial_action_intents(
                    decision=decision,
                    user_message=user_message,
                )
                if native_action_intents:
                    action_items = [
                        intent.to_action_item_dict() for intent in native_action_intents
                    ]
                    return native_action_intents, action_items
            action_intents = await self._build_action_items(
                decision=decision,
                user_message=user_message,
                critic_notes=critic_notes,
                planner_proposals=planner_proposals,
            )
            action_intents = await self._gap_refetch_for_null_actuators(
                action_intents,
                decision=decision,
                user_message=user_message,
                critic_notes=critic_notes,
                planner_proposals=planner_proposals,
            )

            # Pre-dispatch null-tool gate (fires only when ALL null)
            all_null = action_intents and not any(
                i.tool_name or i.playbook_code for i in action_intents
            )
            has_tool_context = self._has_workspace_tool_bindings() or bool(
                getattr(self, "_rag_tool_cache", [])
            )
            if all_null and has_tool_context:
                logger.info(
                    "Pre-dispatch null-tool gate triggered for session %s: "
                    "workspace has explicit TOOL bindings but all action_items "
                    "have tool_name=null and playbook_code=null.  Retrying executor turn.",
                    self.session.id,
                )
                try:
                    retry_intents = await self._build_action_items(
                        decision=decision,
                        user_message=user_message,
                        critic_notes=critic_notes,
                        planner_proposals=planner_proposals,
                    )
                    has_actuator_retry = any(
                        i.tool_name or i.playbook_code for i in retry_intents
                    )
                    if has_actuator_retry:
                        action_intents = retry_intents
                        actuator_count = sum(
                            1 for i in action_intents if i.tool_name or i.playbook_code
                        )
                        logger.info(
                            "Null-tool gate retry produced %d actuator-linked items",
                            actuator_count,
                        )
                        self._emit_event(
                            "tool_name_self_heal",
                            payload={
                                "session_id": self.session.id,
                                "trigger": "null_tool_gate_retry",
                                "actuator_count": actuator_count,
                            },
                        )
                    else:
                        logger.warning(
                            "Null-tool gate retry did not produce actuator items; "
                            "keeping original action_items."
                        )
                except Exception as exc:
                    logger.warning("Null-tool gate retry failed (non-fatal): %s", exc)

            # Bridge: convert ActionIntents to dicts for legacy consumers
            action_items = [i.to_action_item_dict() for i in action_intents]
            return action_intents, action_items

        def _stage_policy_gate_and_emit(
            self,
            action_items: List[Dict[str, Any]],
            action_intents: Optional[List[Any]] = None,
        ) -> tuple[List[Any], List[Dict[str, Any]]]:
            """S5: Policy gate validation + emit action items via SSE."""
            action_intents, action_items = self._apply_request_contract_playbook_requests(
                action_items=action_items,
                action_intents=action_intents,
            )
            self._hydrate_action_items_for_policy_gate(action_items)
            self._ensure_requested_playbooks_in_available_cache()
            try:
                from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
                    check_dispatch_policy,
                )
                from backend.app.services.stores.workspace_resource_binding_store import (
                    WorkspaceResourceBindingStore,
                )

                policy_gate_report = check_dispatch_policy(
                    action_items,
                    workspace_id=self.session.workspace_id,
                    available_playbooks_cache=getattr(
                        self, "_available_playbooks_cache", ""
                    ),
                    binding_store=WorkspaceResourceBindingStore(),
                    workspace_data_sources=(
                        getattr(getattr(self, "workspace", None), "data_sources", None)
                        or {}
                    ),
                    contract_gate_mode=getattr(self, "_contract_gate_mode", "auto"),
                    session_metadata=self.session.metadata,
                    meeting_session_id=self.session.id,
                    project_id=self.project_id,
                )
                if self.session.metadata is None:
                    self.session.metadata = {}
                self.session.metadata["policy_gate"] = policy_gate_report
            except Exception as exc:
                logger.warning("Policy gate check failed (non-fatal): %s", exc)

            action_intents, action_items = self._apply_request_contract_fallback_if_needed(
                action_items=action_items,
                action_intents=action_intents,
            )

            # Emit final action_items AFTER policy gate (SSE events carry landing_status)
            for item in action_items:
                self._emit_action_item(item)
            return action_intents or [], action_items

        async def _stage_decompose_and_dispatch(
            self,
            decision: str,
            action_intents: list,
            action_items: List[Dict[str, Any]],
            handoff_in: Optional[Any] = None,
        ) -> tuple:
            """S6: Dispatch gate → TaskDecomposer → IR compile → DispatchOrchestrator.

            Returns:
                (compiled_ir, dispatch_result)
            """
            return await meeting_stage_decompose_and_dispatch(
                self,
                decision=decision,
                action_intents=action_intents,
                action_items=action_items,
                handoff_in=handoff_in,
            )

        def _stage_finalize(
            self,
            user_message: str,
            decision: str,
            critic_notes: List[str],
            action_items: List[Dict[str, Any]],
            converged: bool,
            compiled_ir: Optional[Any],
            dispatch_result: Optional[Dict[str, Any]],
        ) -> "MeetingResult":
            """S7: Minutes render, session close, L2 bridge, supervisor, completion status."""
            return meeting_stage_finalize(
                self,
                meeting_result_cls=self._meeting_result_class(),
                user_message=user_message,
                decision=decision,
                critic_notes=critic_notes,
                action_items=action_items,
                converged=converged,
                compiled_ir=compiled_ir,
                dispatch_result=dispatch_result,
            )
