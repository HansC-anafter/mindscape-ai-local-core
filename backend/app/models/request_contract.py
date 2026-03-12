"""
Request Contract — structured governance contract compiled from user input.

Layer 1 deliberation の真値基準。Meeting engine compiles this from the
user's natural language request BEFORE entering the deliberation loop.

Lifecycle:
    user_message → RequestContract.compile() → MeetingSession.metadata["request_contract"]
    → CoverageAuditor.audit(contract, draft) → CoverageMatrix
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScaleEstimate(str, Enum):
    """Estimated task scale — drives DecompositionPolicy selection."""

    TRIVIAL = "trivial"  # 1-3 tasks
    STANDARD = "standard"  # 4-15 tasks
    PROGRAM = "program"  # 16-50 tasks
    CAMPAIGN = "campaign"  # 50+ tasks


class DeliverableSpec(BaseModel):
    """A single deliverable in the request contract.

    The ``id`` field is the stable contract-scoped reference used by
    CoverageAuditor for deterministic ID matching (e.g. "D1", "D2").
    """

    id: str = Field(..., description="Contract-scoped stable ID: D1, D2, ...")
    name: str = Field(..., description="Human-readable deliverable name")
    quantity: int = Field(default=1, ge=1, description="Required quantity")
    acceptance_criteria: List[str] = Field(
        default_factory=list,
        description="Acceptance criteria for this deliverable",
    )
    requires: List[str] = Field(
        default_factory=list,
        description="Production dependencies: e.g. ['caption', 'image', 'quality_gate']",
    )


class RequestContract(BaseModel):
    """Structured governance contract compiled from user request.

    This is the single source of truth for what the user asked for.
    All coverage validation, convergence gating, and decomposition
    reference this contract's deliverable IDs.
    """

    goals: List[str] = Field(default_factory=list, description="High-level goals")
    deliverables: List[DeliverableSpec] = Field(
        default_factory=list, description="Deliverables with stable IDs"
    )
    acceptance_tests: List[str] = Field(
        default_factory=list, description="Overall acceptance criteria"
    )
    constraints: Optional[Dict[str, Any]] = Field(
        default=None, description="Constraints (brand tone, timeline, tools)"
    )
    scale_estimate: ScaleEstimate = Field(
        default=ScaleEstimate.STANDARD, description="Estimated scale"
    )
    workspace_scope: str = Field(default="", description="Target workspace ID")
    source_message: str = Field(default="", description="Original user message")

    @classmethod
    def compile_from_agenda(
        cls,
        user_message: str,
        agenda: List[str],
        workspace_id: str = "",
    ) -> "RequestContract":
        """Compile a RequestContract from agenda items.

        If agenda has been decomposed (>1 items), each becomes a deliverable.
        Quantity is extracted from text via regex (e.g. '30 篇 IG post' → 30).

        If agenda is a single compound sentence, attempts heuristic split
        using numeric patterns to identify sub-deliverables.
        """
        import re

        _CN_NUM = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
            "百": 100,
            "千": 1000,
            "兩": 2,
        }

        def _cn_to_int(s: str) -> int:
            """Convert simple Chinese numeral string to int. e.g. '十' → 10, '三十' → 30."""
            if not s:
                return 1
            # Try direct single char
            if len(s) == 1 and s in _CN_NUM:
                return _CN_NUM[s]
            # Handle patterns like 三十, 二十五, 十五
            total = 0
            cur = 0
            for ch in s:
                if ch in _CN_NUM:
                    val = _CN_NUM[ch]
                    if val >= 10:
                        total += max(cur, 1) * val
                        cur = 0
                    else:
                        cur = val
            return total + cur if (total + cur) > 0 else 1

        def _normalize_cn_nums(text: str) -> str:
            """Replace Chinese numeral + counter patterns with Arabic digits."""

            def _repl(m: re.Match) -> str:
                return str(_cn_to_int(m.group(1))) + m.group(2)

            return re.sub(
                r"([一二三四五六七八九十百千兩]+)\s*([篇張個支則條筆])", _repl, text
            )

        def _extract_quantity(text: str) -> int:
            """Extract the first explicit quantity from text."""
            text = _normalize_cn_nums(text)
            m = re.search(
                r"(\d+)\s*[篇張個支則條筆]|(\d+)\s*(?:posts?|images?|items?|articles?)",
                text,
                re.IGNORECASE,
            )
            if m:
                return int(m.group(1) or m.group(2))
            return 1

        def _split_compound(text: str) -> List[Dict[str, Any]]:
            """Heuristic: split a compound sentence into sub-deliverables."""
            text = _normalize_cn_nums(text)
            # Find all numeric-noun segments
            segments = re.findall(
                r"(\d+)\s*[篇張個支則條筆]?\s*([^\d,，、。]+?)(?=[,，、。]|\d|\Z)",
                text,
            )
            if len(segments) >= 2:
                results = []
                for qty_str, name in segments:
                    name = name.strip().rstrip("的並且和及要")
                    if name and len(name) >= 2:
                        results.append({"name": name, "quantity": int(qty_str)})
                if results:
                    return results
            return []

        deliverables: List[DeliverableSpec] = []

        if len(agenda) == 1 and agenda[0]:
            # Single compound sentence — try heuristic split
            sub_items = _split_compound(agenda[0])
            if sub_items:
                for i, sub in enumerate(sub_items, start=1):
                    deliverables.append(
                        DeliverableSpec(
                            id=f"D{i}",
                            name=sub["name"],
                            quantity=sub["quantity"],
                        )
                    )
            else:
                # Fallback: single deliverable with extracted quantity
                deliverables.append(
                    DeliverableSpec(
                        id="D1",
                        name=agenda[0].strip(),
                        quantity=_extract_quantity(agenda[0]),
                    )
                )
        else:
            # Multi-item agenda — each item is a deliverable
            for i, item in enumerate(agenda, start=1):
                deliverables.append(
                    DeliverableSpec(
                        id=f"D{i}",
                        name=item.strip(),
                        quantity=_extract_quantity(item),
                    )
                )

        return cls(
            goals=[item.strip() for item in agenda] if agenda else [user_message],
            deliverables=deliverables,
            source_message=user_message,
            workspace_scope=workspace_id,
            scale_estimate=cls._estimate_scale(sum(d.quantity for d in deliverables)),
        )

    @staticmethod
    def _estimate_scale(total_units: int) -> "ScaleEstimate":
        """Estimate scale from total deliverable units (not count)."""
        if total_units <= 3:
            return ScaleEstimate.TRIVIAL
        if total_units <= 15:
            return ScaleEstimate.STANDARD
        if total_units <= 50:
            return ScaleEstimate.PROGRAM
        return ScaleEstimate.CAMPAIGN

    @classmethod
    async def compile_with_llm(
        cls,
        user_message: str,
        agenda: List[str],
        workspace_id: str = "",
        model_name: Optional[str] = None,
    ) -> "RequestContract":
        """LLM-assisted contract compilation.

        Calls LLM to extract deliverables with name, quantity, and production
        dependencies from the user's natural language request.  Captures
        semantic items (e.g. '配圖') that regex-based parsing misses.

        Falls back to ``compile_from_agenda`` on any LLM error.
        """
        import inspect as _inspect
        import json as _json
        import logging

        _log = logging.getLogger(__name__)

        combined = " | ".join(agenda) if agenda else user_message

        try:
            from backend.features.workspace.chat.utils.llm_provider import (
                get_llm_provider,
                get_llm_provider_manager,
            )

            if not model_name:
                from backend.app.services.system_settings_store import (
                    SystemSettingsStore,
                )

                try:
                    setting = SystemSettingsStore().get_setting("chat_model")
                    if setting and setting.value:
                        model_name = str(setting.value)
                except Exception:
                    pass

            if not model_name:
                _log.debug("compile_with_llm: no model_name, falling back to regex")
                return cls.compile_from_agenda(user_message, agenda, workspace_id)

            manager = get_llm_provider_manager()
            provider, _ = get_llm_provider(
                model_name=model_name,
                llm_provider_manager=manager,
            )

            messages = [
                {
                    "role": "system",
                    "content": (
                        "Extract deliverables from the user request. "
                        "Return ONLY a JSON array of objects. Each object: "
                        '{"name": "short label", "quantity": number, '
                        '"requires": ["dependency1", "dependency2"]}. '
                        "Example for '調研十篇研究，做30篇IG post，要配圖': "
                        '[{"name":"前沿研究調研","quantity":10,"requires":[]},'
                        '{"name":"IG post 貼文","quantity":30,'
                        '"requires":["research","caption","image"]},'
                        '{"name":"配圖","quantity":30,"requires":[]}]'
                    ),
                },
                {"role": "user", "content": combined[:800]},
            ]

            call_kwargs = {
                "messages": messages,
                "model": model_name,
                "temperature": 0.2,
                "max_tokens": 4096,
                "max_completion_tokens": 4096,
            }
            sig = _inspect.signature(provider.chat_completion)
            allowed = set(sig.parameters.keys())
            kwargs = {k: v for k, v in call_kwargs.items() if k in allowed}
            if "messages" not in kwargs:
                kwargs["messages"] = messages

            raw = await provider.chat_completion(**kwargs)
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                text = text[start : end + 1]

            try:
                items = _json.loads(text)
            except _json.JSONDecodeError as e:
                _log.error("Failed to parse LLM output. Raw text: %r", text)
                raise e

            if isinstance(items, list) and len(items) >= 1:
                deliverables = []
                for i, item in enumerate(items, start=1):
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    if not name:
                        continue
                    deliverables.append(
                        DeliverableSpec(
                            id=f"D{i}",
                            name=name,
                            quantity=max(1, int(item.get("quantity", 1))),
                            requires=item.get("requires", []),
                        )
                    )
                if deliverables:
                    contract = cls(
                        goals=(
                            [item.strip() for item in agenda]
                            if agenda
                            else [user_message]
                        ),
                        deliverables=deliverables,
                        source_message=user_message,
                        workspace_scope=workspace_id,
                        scale_estimate=cls._estimate_scale(
                            sum(d.quantity for d in deliverables)
                        ),
                    )
                    _log.info(
                        "compile_with_llm: %d deliverables, scale=%s",
                        len(deliverables),
                        contract.scale_estimate.value,
                    )
                    return contract

        except Exception as exc:
            _log.warning("compile_with_llm failed (falling back to regex): %s", exc)

        return cls.compile_from_agenda(user_message, agenda, workspace_id)
