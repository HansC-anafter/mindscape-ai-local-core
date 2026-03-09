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
            logger.debug("Layer-0c fallback failed (non-fatal): %s", exc)
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
            if enriched:
                logger.info(
                    "Layer-C gap-fill: +%d tools for %d null-actuator items",
                    enriched,
                    len(null_actuator),
                )
                # Retry executor with enriched cache
                try:
                    retry = await self._build_action_items(
                        decision=decision,
                        user_message=user_message,
                        critic_notes=critic_notes,
                        planner_proposals=planner_proposals,
                    )
                    new_bound = sum(
                        1
                        for i in retry
                        if _get(i, "tool_name") or _get(i, "playbook_code")
                    )
                    old_bound = sum(
                        1
                        for i in action_items
                        if _get(i, "tool_name") or _get(i, "playbook_code")
                    )
                    if new_bound > old_bound:
                        action_items = retry
                        logger.info(
                            "Layer-C retry improved binding: %d -> %d actuators",
                            old_bound,
                            new_bound,
                        )
                except Exception:
                    pass  # keep original
        except Exception as exc:
            logger.debug("Layer-C gap-fill failed (non-fatal): %s", exc)

        return action_items
