"""MCP event hook service orchestration."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .contracts import HookResults, ReceiptDecision
from .hook_runtime import (
    extract_intents,
    parse_sampling_intents,
    run_steward,
    ws_extract_intents,
)
from .persistence import (
    build_key,
    emit,
    get_hook_run,
    record_hook_run,
    run_idempotent,
)
from .receipts import emit_receipt_audit, evaluate_receipt

logger = logging.getLogger("backend.app.services.mcp_event_hooks")


class MCPEventHookService:
    """
    Triggered by chat_sync. Idempotent hook runner.

    The service preserves receipts-over-claims, event audit writes, hook-run
    idempotency, and the default policy gate.
    """

    DEFAULT_ENABLED_HOOKS = {"intent_extract", "steward_analyze"}

    def __init__(
        self,
        store: Any = None,
        workspace_id: Optional[str] = None,
        sampling_gate: Any = None,
        mcp_server: Any = None,
    ) -> None:
        self.store = store
        self.workspace_id = workspace_id
        self.sampling_gate = sampling_gate
        self.mcp_server = mcp_server

    async def on_chat_synced(
        self,
        workspace_id: str,
        profile_id: str,
        message: str,
        message_id: str,
        trace_id: str,
        thread_id: Optional[str] = None,
        ide_receipts: Optional[List[Dict[str, Any]]] = None,
    ) -> HookResults:
        """Process hooks after a chat sync."""
        receipts = ide_receipts or []
        results = HookResults()

        intent_decision = self._evaluate_receipt("intent_extract", receipts)
        results.receipt_decisions.append(intent_decision)

        await self._emit_receipt_audit(
            decision=intent_decision,
            workspace_id=workspace_id,
            trace_id=trace_id,
        )

        if intent_decision.should_run:
            idem_key = self._build_key(workspace_id, message_id, "intent_extract")
            intent_tags = await self._run_idempotent(
                idem_key=idem_key,
                hook_type="intent_extract",
                workspace_id=workspace_id,
                fn=self._extract_intents,
                workspace_id_arg=workspace_id,
                profile_id=profile_id,
                message=message,
                message_id=message_id,
                thread_id=thread_id,
            )
            results.intent_tags = intent_tags
            results.triggered_hooks.append("intent_extract")

            await self._emit(
                event_type="intent_extracted",
                source="ws_hook",
                workspace_id=workspace_id,
                trace_id=trace_id,
                payload={"count": len(intent_tags or [])},
            )
        else:
            results.skipped_hooks.append("intent_extract")

        steward_decision = self._evaluate_receipt("steward_analyze", receipts)
        results.receipt_decisions.append(steward_decision)

        await self._emit_receipt_audit(
            decision=steward_decision,
            workspace_id=workspace_id,
            trace_id=trace_id,
        )

        if results.intent_tags and steward_decision.should_run:
            gate = self._gate("steward_analyze", workspace_id)
            if gate:
                idem_key = self._build_key(workspace_id, message_id, "steward")
                layout = await self._run_idempotent(
                    idem_key=idem_key,
                    hook_type="steward_analyze",
                    workspace_id=workspace_id,
                    fn=self._run_steward,
                    workspace_id_arg=workspace_id,
                    profile_id=profile_id,
                    intent_tags=results.intent_tags,
                    message=message,
                )
                results.layout_plan = layout
                results.triggered_hooks.append("steward_analyze")

                await self._emit(
                    event_type="steward_analyzed",
                    source="ws_hook",
                    workspace_id=workspace_id,
                    trace_id=trace_id,
                    payload={"has_layout": layout is not None},
                )
        elif not steward_decision.should_run:
            results.skipped_hooks.append("steward_analyze")

        return results

    def _evaluate_receipt(
        self, step: str, receipts: List[Dict[str, Any]]
    ) -> ReceiptDecision:
        return evaluate_receipt(step, receipts)

    def _should_run_hook(self, step: str, receipts: List[Dict[str, Any]]) -> bool:
        return self._evaluate_receipt(step, receipts).should_run

    async def _emit_receipt_audit(
        self,
        decision: ReceiptDecision,
        workspace_id: str,
        trace_id: str,
    ) -> None:
        await emit_receipt_audit(self, decision, workspace_id, trace_id)

    async def _run_idempotent(
        self,
        idem_key: str,
        hook_type: str,
        workspace_id: str,
        fn: Callable,
        **kwargs: Any,
    ) -> Any:
        return await run_idempotent(
            self,
            idem_key=idem_key,
            hook_type=hook_type,
            workspace_id=workspace_id,
            fn=fn,
            **kwargs,
        )

    def _gate(self, step: str, workspace_id: str) -> bool:
        enabled = getattr(self, "enabled_hooks", self.DEFAULT_ENABLED_HOOKS)
        if step not in enabled:
            logger.info("Policy gate: %s is disabled for ws=%s", step, workspace_id)
            return False
        return True

    async def _extract_intents(
        self,
        workspace_id_arg: str,
        profile_id: str,
        message: str,
        message_id: str,
        thread_id: Optional[str] = None,
    ) -> List[Any]:
        return await extract_intents(
            self,
            workspace_id_arg=workspace_id_arg,
            profile_id=profile_id,
            message=message,
            message_id=message_id,
            thread_id=thread_id,
        )

    async def _ws_extract_intents(
        self,
        workspace_id_arg: str,
        profile_id: str,
        message: str,
        message_id: str,
    ) -> List[Any]:
        return await ws_extract_intents(
            self,
            workspace_id_arg=workspace_id_arg,
            profile_id=profile_id,
            message=message,
            message_id=message_id,
        )

    def _parse_sampling_intents(
        self,
        sampling_result: Any,
        workspace_id: str,
        profile_id: str,
        message_id: str,
    ) -> List[Any]:
        return parse_sampling_intents(
            sampling_result,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message_id=message_id,
        )

    async def _run_steward(
        self,
        workspace_id_arg: str,
        profile_id: str,
        intent_tags: List[Any],
        message: str,
    ) -> Any:
        return await run_steward(
            self,
            workspace_id_arg=workspace_id_arg,
            profile_id=profile_id,
            intent_tags=intent_tags,
            message=message,
        )

    def _build_key(self, workspace_id: str, message_id: str, step: str) -> str:
        return build_key(workspace_id, message_id, step)

    async def _emit(
        self,
        event_type: str,
        source: str,
        workspace_id: str,
        trace_id: str,
        payload: Dict[str, Any],
    ) -> str:
        return await emit(
            self,
            event_type=event_type,
            source=source,
            workspace_id=workspace_id,
            trace_id=trace_id,
            payload=payload,
        )

    async def _get_hook_run(self, idem_key: str) -> Optional[Dict[str, Any]]:
        return await get_hook_run(self, idem_key)

    async def _record_hook_run(
        self,
        idem_key: str,
        hook_type: str,
        workspace_id: str,
        status: str,
        result_summary: Any,
    ) -> None:
        await record_hook_run(
            self,
            idem_key=idem_key,
            hook_type=hook_type,
            workspace_id=workspace_id,
            status=status,
            result_summary=result_summary,
        )
