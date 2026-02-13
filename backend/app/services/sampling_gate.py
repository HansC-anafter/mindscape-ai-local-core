"""
MCP Sampling Safety Gate — Phase 3

Controls server-initiated LLM calls to the IDE client via MCP Sampling.

Security measures:
  - ALLOWED_TEMPLATES: only predefined prompt templates can be sampled
  - Rate limit: per-workspace sliding window (default 10/min)
  - Prompt redaction: strip PII before sending to client
  - Fallback: Sampling → WS LLM → pending card

Usage:
    gate = SamplingGate()
    result = await gate.with_fallback(
        sampling_fn=lambda: server.createMessage(...),
        fallback_fn=lambda: local_intent_extractor.extract(...),
        workspace_id="ws-123",
        template="intent_extract",
    )
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SamplingNotSupported(Exception):
    """Raised when MCP client does not support sampling."""

    pass


class SamplingRateLimitExceeded(Exception):
    """Raised when per-workspace sampling rate limit is exceeded."""

    pass


class SamplingTemplateNotAllowed(Exception):
    """Raised when a sampling template is not in the allowlist."""

    pass


@dataclass
class SamplingResult:
    """Result from a sampling attempt."""

    source: str  # "sampling" | "ws_llm" | "pending_card"
    data: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0


class SamplingGate:
    """
    Safety gate for MCP Sampling requests.

    Enforces:
      - Template allowlist (only predefined prompt templates)
      - Per-workspace rate limiting (sliding window)
      - Prompt redaction (PII removal stub)
      - Graceful fallback chain
    """

    # Templates that are allowed to be sent via MCP Sampling.
    # Only these can trigger server→client LLM calls.
    ALLOWED_TEMPLATES: Set[str] = {
        "intent_extract",
        "steward_analyze",
        "plan_build",
        "agent_task_dispatch",
    }

    # Rate limit: max requests per workspace per window
    RATE_LIMIT: int = 10
    RATE_WINDOW_SECONDS: int = 60

    # Sampling timeout (seconds)
    SAMPLING_TIMEOUT: float = 30.0

    def __init__(
        self,
        allowed_templates: Optional[Set[str]] = None,
        rate_limit: Optional[int] = None,
        rate_window: Optional[int] = None,
        timeout: Optional[float] = None,
    ):
        self.allowed_templates = allowed_templates or self.ALLOWED_TEMPLATES
        self.rate_limit = rate_limit or self.RATE_LIMIT
        self.rate_window = rate_window or self.RATE_WINDOW_SECONDS
        self.timeout = timeout or self.SAMPLING_TIMEOUT

        # Per-workspace rate limit tracking: {workspace_id: [timestamps]}
        self._rate_buckets: Dict[str, List[float]] = defaultdict(list)

    # ============================================================
    #  Main API: with_fallback
    # ============================================================

    async def with_fallback(
        self,
        sampling_fn: Callable[[], Coroutine[Any, Any, Any]],
        fallback_fn: Callable[[], Coroutine[Any, Any, Any]],
        workspace_id: str,
        template: str,
        pending_card_fn: Optional[Callable[[], Coroutine[Any, Any, Any]]] = None,
    ) -> SamplingResult:
        """
        Execute sampling with three-tier fallback:
          1. MCP Sampling (server → client LLM)
          2. WS LLM fallback (local intent extractor)
          3. Pending card (create placeholder for manual review)

        Args:
            sampling_fn: Async function that calls server.createMessage()
            fallback_fn: Async function that runs WS-side LLM processing
            workspace_id: Workspace ID for rate limiting
            template: Template name (must be in ALLOWED_TEMPLATES)
            pending_card_fn: Optional async function to create a pending card
        """
        # Gate 1: Template allowlist
        if template not in self.allowed_templates:
            logger.warning(
                f"Sampling template '{template}' not in allowlist, "
                f"falling back to WS LLM"
            )
            return await self._run_fallback(
                fallback_fn,
                pending_card_fn,
                skip_reason=f"template_not_allowed:{template}",
            )

        # Gate 2: Rate limit
        if not self._check_rate_limit(workspace_id):
            logger.warning(
                f"Sampling rate limit exceeded for ws={workspace_id}, "
                f"falling back to WS LLM"
            )
            return await self._run_fallback(
                fallback_fn,
                pending_card_fn,
                skip_reason="rate_limit_exceeded",
            )

        # Gate 3: Try sampling with timeout
        start = time.monotonic()
        try:
            self._record_request(workspace_id)
            result = await asyncio.wait_for(sampling_fn(), timeout=self.timeout)
            elapsed = (time.monotonic() - start) * 1000
            logger.info(
                f"Sampling succeeded for '{template}' "
                f"(ws={workspace_id}, {elapsed:.0f}ms)"
            )
            return SamplingResult(
                source="sampling",
                data=result,
                latency_ms=elapsed,
            )

        except SamplingNotSupported:
            elapsed = (time.monotonic() - start) * 1000
            logger.info(
                f"Sampling not supported by client, falling back to WS LLM "
                f"({elapsed:.0f}ms)"
            )
            return await self._run_fallback(
                fallback_fn,
                pending_card_fn,
                skip_reason="sampling_not_supported",
            )

        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning(
                f"Sampling timed out after {self.timeout}s for '{template}' "
                f"(ws={workspace_id}, {elapsed:.0f}ms)"
            )
            return await self._run_fallback(
                fallback_fn,
                pending_card_fn,
                skip_reason="sampling_timeout",
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(
                f"Sampling failed for '{template}': {e} ({elapsed:.0f}ms)",
                exc_info=True,
            )
            return await self._run_fallback(
                fallback_fn,
                pending_card_fn,
                skip_reason=f"sampling_error:{type(e).__name__}",
            )

    # ============================================================
    #  Fallback chain
    # ============================================================

    async def _run_fallback(
        self,
        fallback_fn: Callable[[], Coroutine[Any, Any, Any]],
        pending_card_fn: Optional[Callable[[], Coroutine[Any, Any, Any]]],
        skip_reason: str,
    ) -> SamplingResult:
        """
        Tier 2: WS LLM → Tier 3: Pending card.
        """
        start = time.monotonic()

        try:
            result = await fallback_fn()
            elapsed = (time.monotonic() - start) * 1000
            logger.info(f"WS LLM fallback succeeded ({elapsed:.0f}ms)")
            return SamplingResult(
                source="ws_llm",
                data=result,
                latency_ms=elapsed,
            )
        except Exception as fallback_err:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning(
                f"WS LLM fallback also failed: {fallback_err} ({elapsed:.0f}ms)"
            )

            # Tier 3: Pending card
            if pending_card_fn:
                try:
                    card = await pending_card_fn()
                    return SamplingResult(
                        source="pending_card",
                        data=card,
                        error=f"Fallback chain: {skip_reason} → ws_llm_failed",
                        latency_ms=(time.monotonic() - start) * 1000,
                    )
                except Exception as card_err:
                    logger.error(f"Pending card creation failed: {card_err}")

            return SamplingResult(
                source="pending_card",
                data=None,
                error=f"All tiers failed: {skip_reason} → ws_llm → card",
                latency_ms=(time.monotonic() - start) * 1000,
            )

    # ============================================================
    #  Rate limiting (sliding window)
    # ============================================================

    def _check_rate_limit(self, workspace_id: str) -> bool:
        """Check if workspace is within rate limit."""
        now = time.monotonic()
        cutoff = now - self.rate_window
        bucket = self._rate_buckets[workspace_id]

        # Prune old entries
        self._rate_buckets[workspace_id] = [ts for ts in bucket if ts > cutoff]

        return len(self._rate_buckets[workspace_id]) < self.rate_limit

    def _record_request(self, workspace_id: str) -> None:
        """Record a sampling request for rate limiting."""
        self._rate_buckets[workspace_id].append(time.monotonic())

    # ============================================================
    #  Prompt redaction (Phase 3 stub — expand with PII detection)
    # ============================================================

    @staticmethod
    def redact_prompt(prompt: str) -> str:
        """
        Redact PII from prompts before sending via sampling.

        Phase 3: basic redaction. Future: integrate with PII detection
        service (email, phone, SSN patterns).
        """
        import re

        # Redact email addresses
        prompt = re.sub(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "[REDACTED_EMAIL]",
            prompt,
        )

        # Redact phone numbers (basic patterns)
        prompt = re.sub(
            r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
            "[REDACTED_PHONE]",
            prompt,
        )

        return prompt

    # ============================================================
    #  Sampling prompt builders
    # ============================================================

    @staticmethod
    def build_intent_extract_prompt(message: str, context: str = "") -> dict:
        """
        Build a structured prompt for intent extraction via sampling.

        Returns a dict matching MCP CreateMessageRequest params shape.
        """
        system_prompt = (
            "You are an intent extraction assistant for the Mindscape AI platform. "
            "Extract user intents from the conversation message. "
            "Return a JSON array of objects with 'label', 'confidence' (0-1), "
            "and 'reasoning' fields."
        )

        redacted_message = SamplingGate.redact_prompt(message)

        return {
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": (
                            f"Extract intents from this message:\n\n"
                            f"{redacted_message}"
                            + (f"\n\nContext:\n{context}" if context else "")
                        ),
                    },
                }
            ],
            "systemPrompt": system_prompt,
            "maxTokens": 1024,
            "metadata": {
                "template": "intent_extract",
                "source": "mindscape_gateway",
            },
        }

    @staticmethod
    def build_steward_analyze_prompt(
        signals: list, message: str, existing_cards: list = None
    ) -> dict:
        """
        Build a structured prompt for steward analysis via sampling.
        """
        system_prompt = (
            "You are the IntentSteward for Mindscape AI. "
            "Given recent intent signals and the current message, "
            "produce an IntentLayoutPlan that creates, updates, or archives "
            "IntentCards. Return valid JSON matching the IntentLayoutPlan schema."
        )

        signals_text = "\n".join(
            f"- {s.get('label', s)} (confidence: {s.get('confidence', '?')})"
            for s in (signals or [])
        )
        cards_text = "\n".join(f"- {c.get('title', c)}" for c in (existing_cards or []))

        redacted_message = SamplingGate.redact_prompt(message)

        return {
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": (
                            f"Analyze these intent signals and produce a layout plan:\n\n"
                            f"**Message:** {redacted_message}\n\n"
                            f"**Signals:**\n{signals_text}\n\n"
                            f"**Existing cards:**\n{cards_text or 'None'}"
                        ),
                    },
                }
            ],
            "systemPrompt": system_prompt,
            "maxTokens": 2048,
            "metadata": {
                "template": "steward_analyze",
                "source": "mindscape_gateway",
            },
        }

    @staticmethod
    def build_agent_task_dispatch_prompt(
        task: str,
        execution_id: str,
        workspace_id: str,
        allowed_tools: list = None,
        context: dict = None,
    ) -> dict:
        """
        Build a structured prompt for dispatching a coding task to the IDE agent.

        Returns a dict matching MCP CreateMessageRequest params shape.
        """
        system_prompt = (
            "You are receiving a task dispatch from Mindscape AI. "
            "Execute the coding task described below using the allowed tools. "
            "Return a JSON object with: status ('completed' or 'failed'), "
            "output (summary of work done), files_modified (list), "
            "files_created (list), and error (null or error message)."
        )

        ctx = context or {}
        tools_text = ", ".join(allowed_tools or [])
        context_lines = "\n".join(f"  {k}: {v}" for k, v in ctx.items() if v)

        redacted_task = SamplingGate.redact_prompt(task)

        return {
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": (
                            f"## Task Dispatch\n\n"
                            f"**Execution ID:** {execution_id}\n"
                            f"**Workspace:** {workspace_id}\n"
                            f"**Allowed Tools:** {tools_text}\n\n"
                            f"**Task:**\n{redacted_task}"
                            + (
                                f"\n\n**Context:**\n{context_lines}"
                                if context_lines
                                else ""
                            )
                        ),
                    },
                }
            ],
            "systemPrompt": system_prompt,
            "maxTokens": 4096,
            "metadata": {
                "template": "agent_task_dispatch",
                "source": "mindscape_gateway",
                "execution_id": execution_id,
            },
        }
