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
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from backend.app.models.guided_learning_contract import (
    GuidedLearningContext,
)


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


class DataOperationEffect(str, Enum):
    """Planner-visible data operation effect."""

    READ = "read"
    WRITE = "write"
    ACTION = "action"
    DELETE = "delete"


class DataOperationContract(BaseModel):
    """Contract-level data operation intent before tool binding."""

    id: str = Field(..., description="Contract-scoped stable ID: OP1, OP2, ...")
    resource_kind: str = Field(
        ..., description="Pack resource kind such as seed, reference, or creative_space"
    )
    effect: DataOperationEffect = Field(..., description="Requested data effect")
    tool_name: Optional[str] = Field(
        default=None,
        description="Optional explicit planner tool name when the compiler can infer it",
    )
    query: Optional[Dict[str, Any]] = Field(
        default=None, description="Structured read/write selector or payload hints"
    )
    target_object_kind: Optional[str] = Field(
        default=None, description="Optional AOL object kind targeted by the operation"
    )
    acceptance_condition: Optional[str] = Field(
        default=None, description="Operation-level acceptance condition"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional planner-safe operation metadata"
    )


class GroundedKnowledgeAnswerRequest(BaseModel):
    """Typed request for one bounded, citation-verified knowledge answer."""

    question: str = Field(min_length=1, max_length=8000)
    retrieval_modes: List[
        Literal["hybrid", "local_graph", "multi_hop", "global_graph"]
    ] = Field(default_factory=list, max_length=2)
    scope: Literal["workspace", "active_group"] = "workspace"
    frontier_preview: bool = False
    guided_learning_context: Optional[GuidedLearningContext] = None


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
    playbook_requests: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Deterministic downstream playbook requests carried by the request "
            "contract. These are generic contract-level directives that let "
            "upstream layers request a specific pack/playbook handoff without "
            "teaching MeetingEngine pack-specific routing rules."
        ),
    )
    playbook_input_defaults: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Generic bootstrap defaults for action items selected during "
            "deliberation. Rules can target a playbook_code and optional "
            "deliverable_ids, then provide input_params defaults so meeting "
            "merges pack-specific bootstrap data via the request contract "
            "instead of host-core hardcoding."
        ),
    )
    data_operations: List[DataOperationContract] = Field(
        default_factory=list,
        description=(
            "Planner-visible data read/write/action intents preserved before "
            "binding them to installed capability planner_contract tools."
        ),
    )
    grounded_knowledge_answer: Optional[
        GroundedKnowledgeAnswerRequest
    ] = None
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
            # Handle compound CJK numerals.
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
                r"([一二三四五六七八九十百千兩]+)\s*(鏡頭|[篇張個支則條筆鏡場幕])",
                _repl,
                text,
            )

        def _has_countable_unit(unit: str) -> bool:
            normalized = (unit or "").strip().lower()
            return normalized in {
                "篇",
                "張",
                "個",
                "支",
                "則",
                "條",
                "筆",
                "鏡",
                "鏡頭",
                "場",
                "幕",
                "post",
                "posts",
                "image",
                "images",
                "item",
                "items",
                "article",
                "articles",
                "scene",
                "scenes",
                "shot",
                "shots",
                "frame",
                "frames",
                "storyboard",
                "storyboards",
            }

        def _extract_quantity(text: str) -> int:
            """Extract the first explicit deliverable quantity from text."""
            text = _normalize_cn_nums(text)
            m = re.search(
                r"(\d+)\s*(篇|張|個|支|則|條|筆|鏡頭|鏡|場|幕)"
                r"|(\d+)\s*(posts?|images?|items?|articles?|scenes?|shots?|frames?|storyboards?)\b",
                text,
                re.IGNORECASE,
            )
            if m and _has_countable_unit(m.group(2) or m.group(4) or ""):
                return int(m.group(1) or m.group(3))
            return 1

        def _split_compound(text: str) -> List[Dict[str, Any]]:
            """Heuristic: split a compound sentence into sub-deliverables."""
            text = _normalize_cn_nums(text)
            cjk_segments = [
                (qty, unit, name)
                for qty, unit, name in re.findall(
                    r"(\d+)\s*(篇|張|個|支|則|條|筆|鏡頭|鏡|場|幕)\s*([^,，、。]*)",
                    text,
                )
                if _has_countable_unit(unit)
            ]
            english_segments = [
                (qty, unit, name)
                for qty, unit, name in re.findall(
                    r"(\d+)\s*(posts?|images?|items?|articles?|scenes?|shots?|frames?|storyboards?)\b\s*([^,，、。]*)",
                    text,
                    re.IGNORECASE,
                )
                if _has_countable_unit(unit)
            ]
            segments = cjk_segments + english_segments
            if len(segments) >= 2:
                results = []
                for qty_str, unit, name in segments:
                    label = (name or "").strip().rstrip("的並且和及要")
                    if not label:
                        label = unit
                    if label and len(label) >= 2:
                        results.append({"name": label, "quantity": int(qty_str)})
                if results:
                    return results
            return []

        def _looks_like_tracking_agenda_item(text: str) -> bool:
            normalized = (text or "").strip()
            return bool(
                re.search(r"\bE2E[-_]", normalized, re.IGNORECASE)
                or re.search(r"\b20\d{6}\b", normalized)
                or re.search(r"\b[A-Z]{2,}(?:[-_][A-Z0-9]+){2,}\b", normalized)
            )

        deliverables: List[DeliverableSpec] = []
        agenda_items = [item for item in agenda if str(item or "").strip()]
        if (
            len(agenda_items) == 1
            and user_message
            and user_message.strip()
            and _looks_like_tracking_agenda_item(agenda_items[0])
        ):
            agenda_items = [user_message]

        if len(agenda_items) == 1 and agenda_items[0]:
            # Single compound sentence — try heuristic split
            sub_items = _split_compound(agenda_items[0])
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
                        name=agenda_items[0].strip(),
                        quantity=_extract_quantity(agenda_items[0]),
                    )
                )
        else:
            # Multi-item agenda — each item is a deliverable
            for i, item in enumerate(agenda_items, start=1):
                deliverables.append(
                    DeliverableSpec(
                        id=f"D{i}",
                        name=item.strip(),
                        quantity=_extract_quantity(item),
                    )
                )

        contract = cls(
            goals=[item.strip() for item in agenda_items] if agenda_items else [user_message],
            deliverables=deliverables,
            source_message=user_message,
            workspace_scope=workspace_id,
            scale_estimate=cls._estimate_scale(sum(d.quantity for d in deliverables)),
        )
        return cls._with_grounded_answer_if_applicable(
            contract,
            user_message=user_message,
        )

    @classmethod
    def _with_grounded_answer_if_applicable(
        cls,
        contract: "RequestContract",
        *,
        user_message: str,
    ) -> "RequestContract":
        if contract.grounded_knowledge_answer is not None:
            return contract
        question = " ".join(str(user_message or "").split())
        if not cls._is_read_only_information_question(question):
            return contract
        return contract.model_copy(
            update={
                "grounded_knowledge_answer": GroundedKnowledgeAnswerRequest(
                    question=question,
                    retrieval_modes=[cls._infer_grounded_answer_mode(question)],
                )
            }
        )

    @staticmethod
    def _is_read_only_information_question(question: str) -> bool:
        import re

        if not question:
            return False
        side_effect = re.search(
            r"(建立|新增|刪除|移除|發布|安裝|執行|製作|產生|生成|寄送|安排|"
            r"\bcreate\b|\bdelete\b|\bremove\b|\bpublish\b|\binstall\b|"
            r"\bexecute\b|\brun\b|\bbuild\b|\bwrite\b|\bsend\b|\bschedule\b)",
            question,
            re.IGNORECASE,
        )
        if side_effect:
            return False
        return bool(
            question.endswith(("?", "？"))
            or re.match(
                r"^(為什麼|什麼|如何|怎麼|誰|哪|何時|何地|是否|能否|是不是|"
                r"有沒有|why\b|what\b|how\b|who\b|which\b|when\b|where\b|"
                r"is\b|are\b|can\b|could\b|does\b|do\b)",
                question,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _infer_grounded_answer_mode(
        question: str,
    ) -> Literal["hybrid", "local_graph", "multi_hop", "global_graph"]:
        normalized = question.lower()
        if any(
            token in normalized
            for token in (
                "跨領域",
                "整體",
                "全局",
                "主要主題",
                "broad theme",
                "overall",
                "across domains",
            )
        ):
            return "global_graph"
        if any(
            token in normalized
            for token in (
                "多跳",
                "經由",
                "透過哪些",
                "如何連到",
                "how does",
                "through which",
                "multi-hop",
            )
        ):
            return "multi_hop"
        if any(
            token in normalized
            for token in (
                "關係",
                "機制",
                "實體",
                "relation",
                "mechanism",
                "entity",
            )
        ):
            return "local_graph"
        return "hybrid"

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
        llm_generate_fn: Optional[Callable[..., Awaitable[str]]] = None,
    ) -> "RequestContract":
        """LLM-assisted contract compilation.

        Uses the supplied meeting-scoped generation callback to extract
        deliverables with name, quantity, and production dependencies from the
        user's natural language request. Falls back to ``compile_from_agenda``
        on any error. Direct provider routing has been removed.
        """
        import json as _json
        import logging
        import re as _re

        _log = logging.getLogger(__name__)

        combined_parts = []
        if user_message and user_message.strip():
            combined_parts.append(f"User request: {user_message.strip()}")
        agenda_items = [str(item).strip() for item in agenda if str(item).strip()]
        if agenda_items:
            combined_parts.append("Agenda: " + " | ".join(agenda_items))
        combined = "\n".join(combined_parts) if combined_parts else user_message

        try:
            if not model_name or llm_generate_fn is None:
                _log.debug("compile_with_llm: no model_name, falling back to regex")
                return cls.compile_from_agenda(user_message, agenda, workspace_id)

            messages = [
                {
                    "role": "system",
                    "content": (
                        "Extract deliverables from the user request. "
                        "Return ONLY a JSON array of objects. Each object: "
                        '{"name": "short label", "quantity": number, '
                        '"requires": ["dependency1", "dependency2"]}. '
                        "Use quantity only for countable deliverable units such as "
                        "posts, images, scenes, shots, frames, articles, 篇, 張, 鏡, 鏡頭. "
                        "Do not treat tracking IDs, dates, version numbers, or durations "
                        "such as 90s as deliverable quantities. "
                        "Example for '調研十篇研究，做30篇IG post，要配圖': "
                        '[{"name":"前沿研究調研","quantity":10,"requires":[]},'
                        '{"name":"IG post 貼文","quantity":30,'
                        '"requires":["research","caption","image"]},'
                        '{"name":"配圖","quantity":30,"requires":[]}]'
                    ),
                },
                {"role": "user", "content": combined[:800]},
            ]
            raw = await llm_generate_fn(messages, model=model_name)
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
                    quantity = max(1, int(item.get("quantity", 1)))
                    has_countable_unit = bool(
                        _re.search(
                            r"\b(posts?|images?|items?|articles?|scenes?|shots?|frames?|storyboards?)\b"
                            r"|[篇張個支則條筆鏡場幕]",
                            name,
                            _re.IGNORECASE,
                        )
                    )
                    if not has_countable_unit:
                        if quantity > 1000 or _re.search(
                            rf"\b{quantity}\s*s\b", combined, _re.IGNORECASE
                        ):
                            quantity = 1
                    deliverables.append(
                        DeliverableSpec(
                            id=f"D{i}",
                            name=name,
                            quantity=quantity,
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
                    return cls._with_grounded_answer_if_applicable(
                        contract,
                        user_message=user_message,
                    )

        except Exception as exc:
            _log.warning("compile_with_llm failed (falling back to regex): %s", exc)

        return cls.compile_from_agenda(user_message, agenda, workspace_id)
