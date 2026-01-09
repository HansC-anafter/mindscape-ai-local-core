"""
Evidence Injector（證據注入器）

負責在 Runtime 層面注入 EvidenceRef，確保 StrictnessGate Level 2 的檢查是「機械 gate」。

設計原則：
- evidence refs 由 runtime 注入，不依賴模型「自覺」寫 citations
- 所有 retrieval/tool 結果都自動生成 EvidenceRef
- 最終輸出引用的 evidence refs 由系統填入/校驗
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class InjectedEvidence:
    """
    注入的證據

    這是 EvidenceInjector 產生的證據記錄，
    可被 StrictnessGate 驗證。
    """
    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # 來源類型
    source_type: str = ""  # "retrieval" | "tool" | "llm" | "policy"
    source_name: str = ""  # retrieval source name, tool name, etc.

    # 來源識別
    span_id: Optional[str] = None
    trace_id: Optional[str] = None

    # 內容摘要（不存原始內容，避免 PII）
    content_hash: str = ""
    content_length: int = 0

    # 可選的結構化摘要
    summary: Optional[str] = None
    key_fields: Dict[str, Any] = field(default_factory=dict)

    # 時間戳
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_ref(self) -> str:
        """
        轉換為 EvidenceRef 格式（Canonical 格式）

        ⚠️ P0-2 硬規則：必須使用前綴格式
        格式：{source_type}:{id}
        例如：span:abc123, chunk:def456, policy:ghi789
        """
        if self.source_type == "retrieval" and self.key_fields.get("chunk_id"):
            return f"chunk:{self.key_fields['chunk_id']}"
        elif self.source_type == "tool" and self.span_id:
            return f"span:{self.span_id}"
        elif self.source_type == "policy" and self.span_id:
            return f"policy:{self.span_id}"
        elif self.span_id:
            return f"span:{self.span_id}"
        else:
            # Fallback：使用 evidence_id
            return f"{self.source_type}:{self.evidence_id}"


@dataclass
class InjectionContext:
    """注入上下文"""
    run_id: str
    trace_id: str
    workspace_id: str
    strictness_level: int = 0

    # 收集的證據
    evidences: List[InjectedEvidence] = field(default_factory=list)

    # 證據索引
    _evidence_by_type: Dict[str, List[str]] = field(default_factory=dict)

    def add_evidence(self, evidence: InjectedEvidence) -> None:
        """添加證據"""
        self.evidences.append(evidence)

        # 更新索引
        if evidence.source_type not in self._evidence_by_type:
            self._evidence_by_type[evidence.source_type] = []
        self._evidence_by_type[evidence.source_type].append(evidence.evidence_id)

    def get_evidence_ids(self, source_type: Optional[str] = None) -> List[str]:
        """獲取證據 ID 列表"""
        if source_type:
            return self._evidence_by_type.get(source_type, [])
        return [e.evidence_id for e in self.evidences]

    def get_all_refs(self) -> List[str]:
        """
        獲取所有證據引用（Canonical 格式）

        ⚠️ P0-2 硬規則：返回前綴格式的 ID 列表
        """
        return [e.to_ref() for e in self.evidences]


class EvidenceInjector:
    """
    證據注入器

    在 PlaybookRunner/ToolRunner 中使用，自動為以下操作注入證據：
    1. Retrieval（檢索結果）
    2. Tool execution（工具執行結果）
    3. LLM generation（LLM 生成，可選）
    4. Policy check（政策檢查結果）

    使用方式：
        injector = EvidenceInjector()
        context = injector.create_context(run_id, trace_id, workspace_id)

        # 在 retrieval 後
        injector.inject_retrieval(context, chunks, source_name, span_id)

        # 在 tool 執行後
        injector.inject_tool_result(context, result, tool_name, span_id)

        # 獲取所有證據引用
        refs = context.get_all_refs()
    """

    def __init__(self):
        """初始化 EvidenceInjector"""
        self._active_contexts: Dict[str, InjectionContext] = {}

    def create_context(
        self,
        run_id: str,
        trace_id: str,
        workspace_id: str,
        strictness_level: int = 0,
    ) -> InjectionContext:
        """
        創建注入上下文

        Args:
            run_id: Run ID（= trace_id）
            trace_id: Trace ID
            workspace_id: Workspace ID
            strictness_level: 嚴謹度等級

        Returns:
            InjectionContext
        """
        context = InjectionContext(
            run_id=run_id,
            trace_id=trace_id,
            workspace_id=workspace_id,
            strictness_level=strictness_level,
        )
        self._active_contexts[run_id] = context
        return context

    def get_context(self, run_id: str) -> Optional[InjectionContext]:
        """獲取注入上下文"""
        return self._active_contexts.get(run_id)

    def close_context(self, run_id: str) -> Optional[InjectionContext]:
        """關閉並返回上下文"""
        return self._active_contexts.pop(run_id, None)

    def inject_retrieval(
        self,
        context: InjectionContext,
        chunks: List[Dict[str, Any]],
        source_name: str,
        span_id: Optional[str] = None,
    ) -> List[InjectedEvidence]:
        """
        注入檢索證據

        Args:
            context: 注入上下文
            chunks: 檢索到的 chunks
            source_name: 來源名稱
            span_id: Span ID

        Returns:
            注入的證據列表
        """
        evidences = []

        for chunk in chunks:
            content = chunk.get("content", "") or chunk.get("text", "")
            chunk_id = chunk.get("id") or chunk.get("chunk_id")

            evidence = InjectedEvidence(
                source_type="retrieval",
                source_name=source_name,
                span_id=span_id,
                trace_id=context.trace_id,
                content_hash=self._compute_hash(content),
                content_length=len(content),
                key_fields={
                    "chunk_id": chunk_id,
                    "source": chunk.get("source"),
                    "score": chunk.get("score"),
                },
            )

            context.add_evidence(evidence)
            evidences.append(evidence)

        logger.debug(
            f"EvidenceInjector: Injected {len(evidences)} retrieval evidences "
            f"from {source_name}"
        )

        return evidences

    def inject_tool_result(
        self,
        context: InjectionContext,
        result: Any,
        tool_name: str,
        span_id: Optional[str] = None,
        success: bool = True,
    ) -> InjectedEvidence:
        """
        注入工具執行證據

        Args:
            context: 注入上下文
            result: 工具執行結果
            tool_name: 工具名稱
            span_id: Span ID
            success: 是否成功

        Returns:
            注入的證據
        """
        # 序列化結果
        if isinstance(result, dict):
            content = str(result)
            key_fields = {k: v for k, v in result.items() if self._is_safe_value(v)}
        elif isinstance(result, str):
            content = result
            key_fields = {}
        else:
            content = str(result)
            key_fields = {}

        evidence = InjectedEvidence(
            source_type="tool",
            source_name=tool_name,
            span_id=span_id,
            trace_id=context.trace_id,
            content_hash=self._compute_hash(content),
            content_length=len(content),
            key_fields={
                **key_fields,
                "success": success,
            },
        )

        context.add_evidence(evidence)

        logger.debug(
            f"EvidenceInjector: Injected tool evidence for {tool_name} "
            f"(success={success})"
        )

        return evidence

    def inject_llm_output(
        self,
        context: InjectionContext,
        output: str,
        model_name: str,
        span_id: Optional[str] = None,
        structured_output: Optional[Dict[str, Any]] = None,
    ) -> InjectedEvidence:
        """
        注入 LLM 輸出證據

        Args:
            context: 注入上下文
            output: LLM 輸出
            model_name: 模型名稱
            span_id: Span ID
            structured_output: 結構化輸出（如果有）

        Returns:
            注入的證據
        """
        key_fields = {}

        if structured_output:
            # 提取結構化輸出的關鍵欄位
            key_fields = {
                k: v for k, v in structured_output.items()
                if self._is_safe_value(v)
            }

        evidence = InjectedEvidence(
            source_type="llm",
            source_name=model_name,
            span_id=span_id,
            trace_id=context.trace_id,
            content_hash=self._compute_hash(output),
            content_length=len(output),
            key_fields=key_fields,
        )

        context.add_evidence(evidence)

        return evidence

    def inject_policy_check(
        self,
        context: InjectionContext,
        policy_name: str,
        passed: bool,
        reason: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> InjectedEvidence:
        """
        注入政策檢查證據

        Args:
            context: 注入上下文
            policy_name: 政策名稱
            passed: 是否通過
            reason: 原因
            span_id: Span ID

        Returns:
            注入的證據
        """
        evidence = InjectedEvidence(
            source_type="policy",
            source_name=policy_name,
            span_id=span_id,
            trace_id=context.trace_id,
            content_hash="",  # 政策檢查不需要 hash
            content_length=0,
            key_fields={
                "passed": passed,
                "reason": reason,
            },
        )

        context.add_evidence(evidence)

        return evidence

    def validate_output_refs(
        self,
        context: InjectionContext,
        claimed_refs: List[str],
    ) -> Dict[str, Any]:
        """
        驗證輸出聲稱的證據引用

        用於 StrictnessGate Level 2：檢查模型聲稱的引用是否真的存在。

        Args:
            context: 注入上下文
            claimed_refs: 模型聲稱的證據 ID 列表

        Returns:
            驗證結果
        """
        valid_refs = []
        invalid_refs = []

        all_evidence_ids = set(context.get_evidence_ids())

        for ref_id in claimed_refs:
            if ref_id in all_evidence_ids:
                valid_refs.append(ref_id)
            else:
                invalid_refs.append(ref_id)

        return {
            "valid": len(invalid_refs) == 0,
            "valid_refs": valid_refs,
            "invalid_refs": invalid_refs,
            "missing_count": len(invalid_refs),
            "total_available": len(all_evidence_ids),
        }

    def _compute_hash(self, content: str) -> str:
        """計算內容 hash"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _is_safe_value(self, value: Any) -> bool:
        """判斷值是否安全（不包含 PII）"""
        if value is None:
            return True
        if isinstance(value, (bool, int, float)):
            return True
        if isinstance(value, str):
            # 簡單檢查：不包含 email、phone 等模式
            # 實際應使用更完善的 PII 檢測
            return len(value) < 100 and "@" not in value
        if isinstance(value, list):
            return len(value) < 10
        return False


# 全局實例
_global_injector: Optional[EvidenceInjector] = None


def get_evidence_injector() -> EvidenceInjector:
    """獲取全局 EvidenceInjector 實例"""
    global _global_injector
    if _global_injector is None:
        _global_injector = EvidenceInjector()
    return _global_injector

