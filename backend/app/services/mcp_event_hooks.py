"""
MCP Event Hook Service — Phase 2a+2b (Strategy A + C)

Idempotent hook runner triggered by chat_sync.
Enforces governance invariants:
  - Inv.1 Evented: all actions produce events
  - Inv.2 Idempotent: same input → same result (dedup via idempotency_key)
  - Inv.3 Receipts over Claims: ide_receipts skip hooks (Phase 2b: full validation)
  - Inv.4 Policy Gates: hook execution gated by policy

Phase 2b additions:
  - ReceiptDecision dataclass for structured receipt validation
  - output_hash format validation (hex, min 16 chars)
  - Receipt audit events (receipt_accepted / receipt_rejected)
  - Configurable hook enable/disable via ENABLED_HOOKS

Tables used:
  - mcp_events: event audit log
  - mcp_hook_runs: idempotency dedup
"""

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Regex for valid SHA-256 hex hash (at least 16 hex chars)
_HASH_RE = re.compile(r"^[0-9a-fA-F]{16,64}$")


@dataclass
class ReceiptDecision:
    """Structured result from receipt validation (Phase 2b)."""

    step: str
    should_run: bool  # True = run hook, False = skip (receipt accepted)
    reason: str  # Human-readable reason
    receipt_trace_id: Optional[str] = None
    receipt_output_hash: Optional[str] = None


@dataclass
class HookResults:
    """Aggregated results from all hooks in a chat_sync cycle."""

    intent_tags: Optional[List[Any]] = None
    layout_plan: Optional[Any] = None
    triggered_hooks: List[str] = field(default_factory=list)
    skipped_hooks: List[str] = field(default_factory=list)
    events_emitted: List[str] = field(default_factory=list)
    receipt_decisions: List[ReceiptDecision] = field(default_factory=list)


class MCPEventHookService:
    """
    Triggered by chat_sync. Idempotent hook runner.

    Enforces:
      Inv.1 (Evented) — every action emits to mcp_events
      Inv.2 (Idempotent) — _run_idempotent dedup via mcp_hook_runs
      Inv.3 (Receipts) — _should_run_hook checks ide_receipts
      Inv.4 (Policy Gates) — _gate checks step-level policy
    """

    def __init__(
        self,
        store=None,
        workspace_id: Optional[str] = None,
        sampling_gate=None,
        mcp_server=None,
    ):
        """
        Args:
            store: MindscapeStore instance (for DB access)
            workspace_id: Current workspace ID
            sampling_gate: Optional SamplingGate instance (Phase 3)
            mcp_server: Optional MCP Server ref for createMessage (Phase 3)
        """
        self.store = store
        self.workspace_id = workspace_id
        self.sampling_gate = sampling_gate
        self.mcp_server = mcp_server

    # ============================================================
    #  Main entry: on_chat_synced
    # ============================================================

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
        """
        Process hooks after a chat sync.

        Args:
            workspace_id: Workspace ID
            profile_id: Profile/actor ID
            message: Latest user message content
            message_id: Message ID
            trace_id: Cross-system correlation ID
            thread_id: Thread/conversation ID
            ide_receipts: IDE completion receipts
        """
        receipts = ide_receipts or []
        results = HookResults()

        # --------------------------------------------------------
        # Hook 1: Intent extraction
        # --------------------------------------------------------
        intent_decision = self._evaluate_receipt("intent_extract", receipts)
        results.receipt_decisions.append(intent_decision)

        # Emit receipt audit event (Phase 2b: Inv.3)
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

            # Emit event (Inv.1)
            await self._emit(
                event_type="intent_extracted",
                source="ws_hook",
                workspace_id=workspace_id,
                trace_id=trace_id,
                payload={"count": len(intent_tags or [])},
            )
        else:
            results.skipped_hooks.append("intent_extract")

        # --------------------------------------------------------
        # Hook 2: Steward analysis (gated — only if intents exist)
        # --------------------------------------------------------
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

    # ============================================================
    #  Receipt verification (Inv.3 — Phase 2b: full validation)
    # ============================================================

    def _evaluate_receipt(
        self, step: str, receipts: List[Dict[str, Any]]
    ) -> ReceiptDecision:
        """
        Evaluate an IDE receipt for a given hook step.

        Phase 2b validation rules:
          1. Receipt must exist for this step
          2. trace_id must be non-empty
          3. output_hash must be valid hex, minimum 16 chars (SHA-256 prefix)
          4. If completed_at is present, it must not be in the future

        Returns ReceiptDecision with structured reason for audit.
        """
        receipt = next((r for r in receipts if r.get("step") == step), None)

        if not receipt:
            return ReceiptDecision(
                step=step,
                should_run=True,
                reason="no_receipt",
            )

        trace_id = receipt.get("trace_id", "")
        output_hash = receipt.get("output_hash", "")

        # Rule 2: trace_id must be present
        if not trace_id:
            logger.warning(f"Receipt for {step}: missing trace_id")
            return ReceiptDecision(
                step=step,
                should_run=True,
                reason="missing_trace_id",
                receipt_trace_id=trace_id,
                receipt_output_hash=output_hash,
            )

        # Rule 3: output_hash must be valid hex (≥16 chars)
        if not output_hash or not _HASH_RE.match(output_hash):
            logger.warning(
                f"Receipt for {step}: invalid output_hash "
                f"(got '{output_hash[:20]}...' — expected hex ≥16 chars)"
            )
            return ReceiptDecision(
                step=step,
                should_run=True,
                reason="invalid_output_hash",
                receipt_trace_id=trace_id,
                receipt_output_hash=output_hash,
            )

        # Rule 4: completed_at sanity check (if provided)
        completed_at = receipt.get("completed_at")
        if completed_at:
            try:
                from datetime import datetime as dt

                ts = dt.fromisoformat(completed_at.replace("Z", "+00:00"))
                if ts > _utc_now():
                    logger.warning(f"Receipt for {step}: completed_at is in the future")
                    return ReceiptDecision(
                        step=step,
                        should_run=True,
                        reason="future_completed_at",
                        receipt_trace_id=trace_id,
                        receipt_output_hash=output_hash,
                    )
            except (ValueError, TypeError):
                # If parsing fails, don't block — just log
                logger.debug(f"Receipt for {step}: unparsable completed_at")

        # All checks passed — accept receipt, skip hook
        return ReceiptDecision(
            step=step,
            should_run=False,
            reason="receipt_accepted",
            receipt_trace_id=trace_id,
            receipt_output_hash=output_hash,
        )

    def _should_run_hook(self, step: str, receipts: List[Dict[str, Any]]) -> bool:
        """Backward-compatible wrapper around _evaluate_receipt."""
        return self._evaluate_receipt(step, receipts).should_run

    async def _emit_receipt_audit(
        self,
        decision: ReceiptDecision,
        workspace_id: str,
        trace_id: str,
    ) -> None:
        """
        Emit a receipt audit event (Phase 2b: Inv.3 transparency).

        Every receipt decision is logged for observability.
        """
        if decision.reason == "no_receipt":
            return  # No receipt = no audit needed

        event_type = (
            "receipt_accepted" if not decision.should_run else "receipt_rejected"
        )
        await self._emit(
            event_type=event_type,
            source="receipt_validator",
            workspace_id=workspace_id,
            trace_id=trace_id,
            payload={
                "step": decision.step,
                "reason": decision.reason,
                "receipt_trace_id": decision.receipt_trace_id,
                "receipt_hash_prefix": (
                    decision.receipt_output_hash[:8]
                    if decision.receipt_output_hash
                    else None
                ),
            },
        )

    # ============================================================
    #  Idempotent runner (Inv.2)
    # ============================================================

    async def _run_idempotent(
        self,
        idem_key: str,
        hook_type: str,
        workspace_id: str,
        fn: Callable,
        **kwargs,
    ) -> Any:
        """
        Run a hook function idempotently.

        If idem_key already exists in mcp_hook_runs, return cached result.
        Otherwise execute fn and record the run.
        """
        # Check if already executed
        existing = await self._get_hook_run(idem_key)
        if existing:
            logger.info(
                f"Idempotent skip: {hook_type} already executed "
                f"(key={idem_key[:16]}...)"
            )
            return existing.get("result_summary")

        # Execute the hook
        try:
            result = await fn(**kwargs)

            # Record completion
            await self._record_hook_run(
                idem_key=idem_key,
                hook_type=hook_type,
                workspace_id=workspace_id,
                status="completed",
                result_summary=result,
            )

            return result
        except Exception as e:
            logger.error(f"Hook {hook_type} failed: {e}", exc_info=True)
            await self._record_hook_run(
                idem_key=idem_key,
                hook_type=hook_type,
                workspace_id=workspace_id,
                status="failed",
                result_summary={"error": str(e)},
            )
            return None

    # ============================================================
    #  Policy gate (Inv.4 — Phase 2b: configurable)
    # ============================================================

    # Hooks that are enabled by default. Override via constructor
    # or workspace-level config in Phase 3+.
    DEFAULT_ENABLED_HOOKS = {"intent_extract", "steward_analyze"}

    def _gate(self, step: str, workspace_id: str) -> bool:
        """
        Check if a step is allowed by policy.

        Phase 2b: checks against ENABLED_HOOKS set.
        Phase 3+: will query workspace-level policy store.
        """
        enabled = getattr(self, "enabled_hooks", self.DEFAULT_ENABLED_HOOKS)
        if step not in enabled:
            logger.info(f"Policy gate: {step} is disabled for ws={workspace_id}")
            return False
        return True

    # ============================================================
    #  Hook implementations
    # ============================================================

    async def _extract_intents(
        self,
        workspace_id_arg: str,
        profile_id: str,
        message: str,
        message_id: str,
        thread_id: Optional[str] = None,
    ) -> List[Any]:
        """
        Run intent extraction — sampling-aware (Phase 3).

        Priority: MCP Sampling → WS LLM → empty list.
        """
        # Phase 3: If sampling gate is available, use with_fallback
        if self.sampling_gate and self.mcp_server:
            try:
                from .sampling_gate import SamplingGate

                prompt_params = SamplingGate.build_intent_extract_prompt(message)

                async def sampling_fn():
                    """Server → client LLM sampling."""
                    result = await self.mcp_server.createMessage(prompt_params)
                    # Parse sampling response into intent tags
                    return self._parse_sampling_intents(
                        result, workspace_id_arg, profile_id, message_id
                    )

                async def fallback_fn():
                    """WS-side LLM extraction."""
                    return await self._ws_extract_intents(
                        workspace_id_arg, profile_id, message, message_id
                    )

                sampling_result = await self.sampling_gate.with_fallback(
                    sampling_fn=sampling_fn,
                    fallback_fn=fallback_fn,
                    workspace_id=workspace_id_arg,
                    template="intent_extract",
                )
                return sampling_result.data or []

            except Exception as e:
                logger.warning(f"Sampling-aware extraction failed, using direct: {e}")

        # Direct WS LLM extraction (pre-Phase 3 fallback)
        return await self._ws_extract_intents(
            workspace_id_arg, profile_id, message, message_id
        )

    async def _ws_extract_intents(
        self,
        workspace_id_arg: str,
        profile_id: str,
        message: str,
        message_id: str,
    ) -> List[Any]:
        """WS-side LLM intent extraction (original Phase 2a logic)."""
        try:
            from ..services.conversation.intent_extractor import IntentExtractor
            from ..services.mindscape_store import MindscapeStore
            from ..services.stores.timeline_items_store import TimelineItemsStore
            from ..adapters.local.local_intent_registry_adapter import (
                LocalIntentRegistryAdapter,
            )

            store = self.store or MindscapeStore()
            extractor = IntentExtractor(
                store=store,
                timeline_items_store=TimelineItemsStore(),
                intent_registry=LocalIntentRegistryAdapter(),
            )

            tags = extractor.extract_intents(
                workspace_id=workspace_id_arg,
                profile_id=profile_id,
                message=message,
                message_id=message_id,
            )
            return tags or []

        except ImportError as e:
            logger.warning(f"Intent extraction not available: {e}")
            return []
        except Exception as e:
            logger.error(f"Intent extraction failed: {e}", exc_info=True)
            return []

    def _parse_sampling_intents(
        self,
        sampling_result: Any,
        workspace_id: str,
        profile_id: str,
        message_id: str,
    ) -> List[Any]:
        """
        Parse MCP createMessage response into IntentTag-like objects.
        """
        import json

        try:
            # Extract text content from sampling result
            content = getattr(sampling_result, "content", sampling_result)
            if isinstance(content, dict):
                text = content.get("text", str(content))
            elif hasattr(content, "text"):
                text = content.text
            else:
                text = str(content)

            # Parse JSON from the response
            # Try to extract JSON array from the text
            if "[" in text:
                json_start = text.index("[")
                json_end = text.rindex("]") + 1
                intents = json.loads(text[json_start:json_end])
            else:
                intents = json.loads(text)

            if not isinstance(intents, list):
                intents = [intents]

            # Convert to lightweight intent dicts
            tags = []
            for intent in intents:
                tags.append(
                    {
                        "id": str(uuid.uuid4()),
                        "workspace_id": workspace_id,
                        "profile_id": profile_id,
                        "label": intent.get("label", "unknown"),
                        "confidence": intent.get("confidence", 0.5),
                        "source": "mcp_sampling",
                        "message_id": message_id,
                        "reasoning": intent.get("reasoning", ""),
                    }
                )
            return tags

        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse sampling intents: {e}")
            return []

    async def _run_steward(
        self,
        workspace_id_arg: str,
        profile_id: str,
        intent_tags: List[Any],
        message: str,
    ) -> Any:
        """Run IntentSteward analysis on extracted tags."""
        try:
            from ..services.conversation.intent_steward import IntentStewardService
            from ..services.mindscape_store import MindscapeStore
            from ..models.mindscape import IntentSignal, IntentStewardInput

            store = self.store or MindscapeStore()
            steward = IntentStewardService(store=store)

            # Build signals from intent tags
            signals = []
            for tag in intent_tags:
                signal = IntentSignal(
                    id=getattr(tag, "id", str(uuid.uuid4())),
                    workspace_id=workspace_id_arg,
                    profile_id=profile_id,
                    label=getattr(tag, "label", str(tag)),
                    confidence=getattr(tag, "confidence", 0.5),
                    source="ws_hook",
                    message_id=getattr(tag, "message_id", None),
                )
                signals.append(signal)

            if not signals:
                return None

            # Build steward input
            steward_input = IntentStewardInput(
                recent_messages=[{"role": "user", "content": message}],
                recent_signals=signals,
                current_intent_cards=[],
            )

            # Run steward analysis
            layout = await steward.steward_analyze(
                workspace_id=workspace_id_arg,
                profile_id=profile_id,
                steward_input=steward_input,
            )
            return layout

        except ImportError as e:
            logger.warning(f"Steward analysis not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Steward analysis failed: {e}", exc_info=True)
            return None

    # ============================================================
    #  DB helpers (mcp_events + mcp_hook_runs)
    # ============================================================

    def _build_key(self, workspace_id: str, message_id: str, step: str) -> str:
        """Build deterministic idempotency key."""
        raw = f"{workspace_id}:{message_id}:{step}"
        return hashlib.sha256(raw.encode()).hexdigest()[:48]

    async def _emit(
        self,
        event_type: str,
        source: str,
        workspace_id: str,
        trace_id: str,
        payload: Dict[str, Any],
    ) -> str:
        """
        Emit an MCP event to mcp_events table.

        Returns event_id.
        """
        event_id = str(uuid.uuid4())
        try:
            if self.store and hasattr(self.store, "execute_raw"):
                await self.store.execute_raw(
                    """INSERT INTO mcp_events
                       (event_id, event_type, source, workspace_id,
                        idempotency_key, trace_id, payload, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id,
                        event_type,
                        source,
                        workspace_id,
                        f"{event_type}:{trace_id}",
                        trace_id,
                        str(payload),
                        _utc_now().isoformat(),
                    ),
                )
            else:
                # Fallback: log-only mode until DB is migrated
                logger.info(
                    f"MCP Event [{event_type}] source={source} "
                    f"ws={workspace_id} trace={trace_id} payload={payload}"
                )
        except Exception as e:
            logger.warning(f"Failed to emit MCP event: {e}")

        return event_id

    async def _get_hook_run(self, idem_key: str) -> Optional[Dict[str, Any]]:
        """Check if a hook run already exists."""
        try:
            if self.store and hasattr(self.store, "execute_raw"):
                row = await self.store.execute_raw(
                    "SELECT * FROM mcp_hook_runs WHERE idempotency_key = ?",
                    (idem_key,),
                )
                if row:
                    return row[0] if isinstance(row, list) else row
        except Exception:
            pass

        return None

    async def _record_hook_run(
        self,
        idem_key: str,
        hook_type: str,
        workspace_id: str,
        status: str,
        result_summary: Any,
    ) -> None:
        """Record a hook run for idempotency."""
        try:
            if self.store and hasattr(self.store, "execute_raw"):
                await self.store.execute_raw(
                    """INSERT INTO mcp_hook_runs
                       (idempotency_key, hook_type, workspace_id,
                        status, result_summary, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT (idempotency_key) DO NOTHING""",
                    (
                        idem_key,
                        hook_type,
                        workspace_id,
                        status,
                        str(result_summary),
                        _utc_now().isoformat(),
                    ),
                )
            else:
                logger.info(
                    f"MCP Hook Run [{hook_type}] key={idem_key[:16]}... "
                    f"status={status}"
                )
        except Exception as e:
            logger.warning(f"Failed to record hook run: {e}")
