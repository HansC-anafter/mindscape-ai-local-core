"""
Meeting engine tool discovery mixin.

Handles progressive tool discovery: Layer-0c agenda decomposition
and Layer-C gap-refetch for null actuators.
"""

import asyncio
import logging
from typing import Any, List

logger = logging.getLogger(__name__)


class MeetingToolDiscoveryMixin:
    """Mixin providing progressive tool discovery for MeetingEngine."""

    async def _ensure_agenda_decomposed(self, user_message: str) -> bool:
        """Layer 0c: decompose single-item agenda into sub-tasks.

        If agenda has ≤1 items (session created without decomposition),
        split user_message into sub-tasks so per-agenda multi-query activates.
        Persists decomposed agenda to session_store.

        Returns True if decomposition happened, False otherwise.
        """
        _l0_agenda = getattr(self.session, "agenda", None) or []
        if len(_l0_agenda) > 1 or not user_message or len(user_message.strip()) < 10:
            return False

        try:
            from backend.app.services.conversation.pipeline_meeting import (
                _decompose_agenda,
            )

            decomposed = await _decompose_agenda(
                user_message,
                model_name=self.model_name,
                executor_runtime=self.executor_runtime,
                llm_generate_fn=self._generate_text,
            )
            if len(decomposed) > 1:
                self.session.agenda = decomposed
                # Persist to store so reuse path also benefits
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: self.session_store.update(self.session),
                    )
                except Exception:
                    pass  # non-fatal
                logger.info(
                    "Layer-0c: decomposed agenda into %d items for session %s",
                    len(decomposed),
                    self.session.id,
                )
                return True
        except Exception as exc:
            logger.warning("Layer-0c decomposition failed (non-fatal): %s", exc)
        return False

    async def _gap_refetch_for_null_actuators(
        self,
        action_items: list,
        *,
        decision: Any = None,
        user_message: str = "",
        critic_notes: str = "",
        planner_proposals: str = "",
    ) -> list:
        """Layer C: re-fetch tools for any action item missing actuator.

        For each item with tool_name=None AND playbook_code=None, query RAG
        with the item title. If new tools are found, retry _build_action_items
        and accept the result only if it improves binding coverage.

        Accepts both ActionIntent objects (attribute access) and legacy dicts.
        Returns the (possibly improved) action_items list.
        """
        has_tool_context = self._has_workspace_tool_bindings() or bool(
            getattr(self, "_rag_tool_cache", [])
        )

        def _get(item, key):
            """Unified accessor for both ActionIntent and dict."""
            return getattr(item, key, None) or (
                item.get(key) if isinstance(item, dict) else None
            )

        def _set(item, key, value):
            """Unified setter for both ActionIntent and dict."""
            if isinstance(item, dict):
                item[key] = value
            else:
                setattr(item, key, value)

        null_actuator = [
            i
            for i in action_items
            if not _get(i, "tool_name") and not _get(i, "playbook_code")
        ]
        if not null_actuator or not has_tool_context:
            return action_items

        try:
            from backend.app.services.tool_rag import retrieve_relevant_tools

            cache_ids = {t["tool_id"] for t in self._rag_tool_cache}
            enriched = 0
            bound = 0
            for item in null_actuator:
                title = _get(item, "title") or ""
                if not title:
                    continue
                aug = self._verb_augment(title)
                q = f"{title} {aug}".strip() if aug else title
                hits = await retrieve_relevant_tools(
                    q,
                    top_k=3,
                    workspace_id=self.session.workspace_id,
                )
                for h in hits:
                    if h["tool_id"] not in cache_ids:
                        cache_ids.add(h["tool_id"])
                        self._rag_tool_cache.append(h)
                        enriched += 1
                top_hit = next(
                    (
                        hit
                        for hit in hits
                        if isinstance(hit, dict) and str(hit.get("tool_id") or "").strip()
                    ),
                    None,
                )
                if top_hit and not _get(item, "tool_name") and not _get(item, "playbook_code"):
                    tool_id = str(top_hit.get("tool_id") or "").strip()
                    if tool_id:
                        _set(item, "tool_name", tool_id)
                        if not _get(item, "engine"):
                            _set(item, "engine", f"tool:{tool_id}")
                        if not _get(item, "binding_source"):
                            _set(item, "binding_source", "layer_c_tool_gap_fill")
                        bound += 1
            if enriched or bound:
                logger.info(
                    "Layer-C gap-fill: +%d tools, +%d bindings for %d null-actuator items",
                    enriched,
                    bound,
                    len(null_actuator),
                )
        except Exception as exc:
            logger.debug("Layer-C gap-fill failed (non-fatal): %s", exc)

        # ── Layer-C playbook gap-refetch ──────────────────────────────
        # Same pattern as tool gap-refetch but for still-unbound playbook_code.
        null_pb = [
            i
            for i in action_items
            if not _get(i, "playbook_code") and not _get(i, "tool_name")
        ]
        if null_pb and has_tool_context:
            try:
                from app.services.tool_embedding_service import (
                    ToolEmbeddingService,
                )

                pb_cache = getattr(self, "_rag_playbook_cache", [])
                pb_ids = {p.get("playbook_code") or p.get("tool_id") for p in pb_cache}
                tes = ToolEmbeddingService()
                pb_enriched = 0
                pb_bound = 0
                for item in null_pb:
                    title = _get(item, "title") or ""
                    if not title:
                        continue
                    pb_matches, _ = await tes.search_rrf(
                        query=title, top_k=5, min_score=0.10
                    )
                    for m in pb_matches:
                        if m.category == "playbook" and m.tool_id not in pb_ids:
                            pb_ids.add(m.tool_id)
                            pb_cache.append(
                                {
                                    "tool_id": m.tool_id,
                                    "playbook_code": m.tool_id,
                                    "display_name": m.display_name,
                                    "description": m.description,
                                }
                            )
                            pb_enriched += 1
                    top_match = next(
                        (
                            match
                            for match in pb_matches
                            if getattr(match, "category", None) == "playbook"
                            and str(getattr(match, "tool_id", "") or "").strip()
                        ),
                        None,
                    )
                    if top_match and not _get(item, "playbook_code") and not _get(item, "tool_name"):
                        playbook_code = str(getattr(top_match, "tool_id", "") or "").strip()
                        if playbook_code:
                            _set(item, "playbook_code", playbook_code)
                            if not _get(item, "engine"):
                                _set(item, "engine", f"playbook:{playbook_code}")
                            if not _get(item, "binding_source"):
                                _set(item, "binding_source", "layer_c_playbook_gap_fill")
                            pb_bound += 1

                self._rag_playbook_cache = pb_cache
                if pb_enriched or pb_bound:
                    logger.info(
                        "Layer-C playbook gap-fill: +%d playbooks, +%d bindings "
                        "for %d null-pb items",
                        pb_enriched,
                        pb_bound,
                        len(null_pb),
                    )
            except Exception as pb_exc:
                logger.debug(
                    "Layer-C playbook gap-fill failed (non-fatal): %s",
                    pb_exc,
                )

        return action_items
