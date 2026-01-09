"""
Structured Evidence Schema

結構化證據 - EvidenceReducer 的輸出。
把 raw trace 轉為可計算、可比較的結構化數據。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import hashlib


@dataclass
class ToolPath:
    """
    工具路徑

    記錄一次執行中的工具呼叫序列。
    """
    tool_names: List[str] = field(default_factory=list)  # 工具名序列
    tool_args_hashes: List[str] = field(default_factory=list)  # 參數摘要 hash
    success_flags: List[bool] = field(default_factory=list)  # 各步驟是否成功
    durations_ms: List[int] = field(default_factory=list)  # 各步驟延遲

    @property
    def length(self) -> int:
        """路徑長度"""
        return len(self.tool_names)

    @property
    def success_rate(self) -> float:
        """成功率"""
        if not self.success_flags:
            return 1.0
        return sum(self.success_flags) / len(self.success_flags)

    @property
    def total_duration_ms(self) -> int:
        """總延遲"""
        return sum(self.durations_ms)

    @property
    def path_signature(self) -> str:
        """路徑簽名（用於比較）"""
        return "->".join(self.tool_names)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_names": self.tool_names,
            "tool_args_hashes": self.tool_args_hashes,
            "success_flags": self.success_flags,
            "durations_ms": self.durations_ms,
            "length": self.length,
            "success_rate": self.success_rate,
            "total_duration_ms": self.total_duration_ms,
            "path_signature": self.path_signature,
        }


@dataclass
class RetrievalEvidence:
    """
    檢索證據

    記錄檢索相關的證據。
    """
    chunk_ids: List[str] = field(default_factory=list)  # 檢索到的 chunk IDs
    sources: List[str] = field(default_factory=list)  # 來源（file, url, db）
    query_texts: List[str] = field(default_factory=list)  # 查詢文本

    # 指標
    total_chunks: int = 0
    unique_sources: int = 0
    avg_relevance_score: float = 0.0

    @property
    def sources_signature(self) -> str:
        """來源簽名（用於比較）"""
        return "|".join(sorted(set(self.sources)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_ids": self.chunk_ids,
            "sources": self.sources,
            "query_texts": self.query_texts,
            "total_chunks": self.total_chunks,
            "unique_sources": self.unique_sources,
            "avg_relevance_score": self.avg_relevance_score,
            "sources_signature": self.sources_signature,
        }


@dataclass
class PolicyCheckEvidence:
    """
    政策檢查證據

    記錄政策檢查的結果。
    """
    policy_name: str
    check_type: str              # "cost" | "node" | "preflight" | "custom"
    passed: bool
    reason: Optional[str] = None
    threshold_value: Optional[Any] = None
    actual_value: Optional[Any] = None
    span_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_name": self.policy_name,
            "check_type": self.check_type,
            "passed": self.passed,
            "reason": self.reason,
            "threshold_value": self.threshold_value,
            "actual_value": self.actual_value,
            "span_id": self.span_id,
        }


@dataclass
class StrictnessChange:
    """
    嚴謹度變更

    記錄執行過程中的嚴謹度變更。
    """
    from_level: int
    to_level: int
    reason: str
    triggered_by: str            # "policy" | "user" | "auto"
    span_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_level": self.from_level,
            "to_level": self.to_level,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "span_id": self.span_id,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class TraceMetrics:
    """
    Trace 指標

    計算類指標，純數字。
    """
    total_latency_ms: int = 0
    llm_latency_ms: int = 0
    tool_latency_ms: int = 0

    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    total_cost_usd: float = 0.0

    llm_calls: int = 0
    tool_calls: int = 0
    retrieval_calls: int = 0

    error_count: int = 0
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_latency_ms": self.total_latency_ms,
            "llm_latency_ms": self.llm_latency_ms,
            "tool_latency_ms": self.tool_latency_ms,
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "retrieval_calls": self.retrieval_calls,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
        }


@dataclass
class StructuredEvidence:
    """
    結構化證據

    EvidenceReducer 的輸出。
    把 raw trace 轉為可計算、可比較的結構化數據。

    這是 DriftScorer 的輸入。

    ⚠️ P0-1 硬規則：run_id 是單一真相（run_id == trace_id）
    ⚠️ P0-5 修正：移除 key_assertions，新增 key_fields_hash_map
    """

    # 識別
    evidence_id: str = ""
    run_id: str = ""  # ⚠️ P0-1：統一使用 run_id（不再用 trace_id）

    # ⚠️ P0-1 新增：CorrelationIds 欄位（供 drift 計算使用）
    workspace_id: str = ""
    intent_id: str = ""
    strictness_level: int = 0
    mind_lens_level: int = 0
    policy_version: Optional[str] = None

    # 工具路徑
    tool_path: ToolPath = field(default_factory=ToolPath)

    # 檢索證據
    retrieval_evidence: RetrievalEvidence = field(default_factory=RetrievalEvidence)

    # 政策證據
    policy_checks: List[PolicyCheckEvidence] = field(default_factory=list)
    strictness_changes: List[StrictnessChange] = field(default_factory=list)

    # 指標
    metrics: TraceMetrics = field(default_factory=TraceMetrics)

    # 輸出摘要
    output_hash: str = ""                # 輸出內容 hash（用於語義漂移檢測）
    output_length: int = 0               # 輸出長度

    # ⚠️ P0-5 修正：移除 key_assertions，新增結構化輸出相關欄位
    structured_output_hash: Optional[str] = None    # 整份 JSON hash（strictness ≥ 1）
    key_fields_hash: Optional[str] = None           # 白名單欄位 hash（strictness ≥ 1）
    key_fields_hash_map: Optional[Dict[str, str]] = None  # JSON Pointer → hash 的映射

    # ⚠️ P0-2 新增：證據 ID 集合（供 StrictnessGate L2 檢查）
    retrieval_chunk_ids: List[str] = field(default_factory=list)  # 檢索 chunk IDs
    tool_span_ids: List[str] = field(default_factory=list)  # Tool 節點的 node_id
    policy_span_ids: List[str] = field(default_factory=list)  # Policy 節點的 node_id

    # 時間戳
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def trace_id(self) -> str:
        """
        向後相容：trace_id 就是 run_id（單一真相）
        """
        return self.run_id

    @staticmethod
    def compute_hash(content: str) -> str:
        """計算內容 hash"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @property
    def failed_policy_checks(self) -> List[PolicyCheckEvidence]:
        """獲取失敗的政策檢查"""
        return [p for p in self.policy_checks if not p.passed]

    @property
    def has_strictness_escalation(self) -> bool:
        """是否有嚴謹度升級"""
        return any(
            c.to_level > c.from_level
            for c in self.strictness_changes
        )

    @property
    def final_strictness_level(self) -> int:
        """最終嚴謹度等級"""
        if not self.strictness_changes:
            return self.strictness_level  # 使用初始 strictness_level
        return self.strictness_changes[-1].to_level

    def get_evidence_ids(self) -> set:
        """
        獲取所有證據 ID 的集合（供 StrictnessGate L2 驗證）

        ⚠️ P0-2 硬規則：Canonical 格式（全文件統一）
        - span:<langfuse_span_id>（例如：span:abc123）
        - chunk:<retrieval_chunk_id>（例如：chunk:def456）
        - policy:<policy_node_id>（例如：policy:ghi789）

        理由：
        - 最直觀、最不怕不同系統撞 ID
        - 類型前綴明確，避免 ID 衝突

        Returns:
            Set[str]: 例如 {"chunk:abc123", "span:def456", "policy:ghi789"}
        """
        evidence_ids = set()
        # P0-2 硬規則：Canonical 格式
        evidence_ids.update(f"chunk:{cid}" for cid in self.retrieval_chunk_ids)
        evidence_ids.update(f"span:{sid}" for sid in self.tool_span_ids)
        evidence_ids.update(f"policy:{pid}" for pid in self.policy_span_ids)
        return evidence_ids

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return {
            "evidence_id": self.evidence_id,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            # ⚠️ P0-1：新增 CorrelationIds 欄位
            "workspace_id": self.workspace_id,
            "intent_id": self.intent_id,
            "strictness_level": self.strictness_level,
            "mind_lens_level": self.mind_lens_level,
            "policy_version": self.policy_version,
            "tool_path": self.tool_path.to_dict(),
            "retrieval_evidence": self.retrieval_evidence.to_dict(),
            "policy_checks": [p.to_dict() for p in self.policy_checks],
            "strictness_changes": [s.to_dict() for s in self.strictness_changes],
            "metrics": self.metrics.to_dict(),
            "output_hash": self.output_hash,
            "output_length": self.output_length,
            # ⚠️ P0-5：已移除 key_assertions，改用 key_fields_hash_map
            "structured_output_hash": self.structured_output_hash,
            "key_fields_hash": self.key_fields_hash,
            "key_fields_hash_map": self.key_fields_hash_map,
            # ⚠️ P0-2：新增證據 ID 集合
            "retrieval_chunk_ids": self.retrieval_chunk_ids,
            "tool_span_ids": self.tool_span_ids,
            "policy_span_ids": self.policy_span_ids,
            "has_strictness_escalation": self.has_strictness_escalation,
            "final_strictness_level": self.final_strictness_level,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StructuredEvidence":
        """從字典反序列化"""
        # ⚠️ P0-1：向後相容，支援 trace_id 或 run_id
        run_id = data.get("run_id") or data.get("trace_id", "")
        evidence = cls(
            evidence_id=data.get("evidence_id", ""),
            run_id=run_id,
            workspace_id=data.get("workspace_id", ""),
            intent_id=data.get("intent_id", ""),
            strictness_level=data.get("strictness_level", 0),
            mind_lens_level=data.get("mind_lens_level", 0),
            policy_version=data.get("policy_version"),
            output_hash=data.get("output_hash", ""),
            output_length=data.get("output_length", 0),
            # ⚠️ P0-5：已移除 key_assertions，改用 key_fields_hash_map
            structured_output_hash=data.get("structured_output_hash"),
            key_fields_hash=data.get("key_fields_hash"),
            key_fields_hash_map=data.get("key_fields_hash_map") or {},
            retrieval_chunk_ids=data.get("retrieval_chunk_ids", []),
            tool_span_ids=data.get("tool_span_ids", []),
            policy_span_ids=data.get("policy_span_ids", []),
        )

        # Parse tool path
        if data.get("tool_path"):
            tp = data["tool_path"]
            evidence.tool_path = ToolPath(
                tool_names=tp.get("tool_names", []),
                tool_args_hashes=tp.get("tool_args_hashes", []),
                success_flags=tp.get("success_flags", []),
                durations_ms=tp.get("durations_ms", []),
            )

        # Parse retrieval evidence
        if data.get("retrieval_evidence"):
            re = data["retrieval_evidence"]
            evidence.retrieval_evidence = RetrievalEvidence(
                chunk_ids=re.get("chunk_ids", []),
                sources=re.get("sources", []),
                query_texts=re.get("query_texts", []),
                total_chunks=re.get("total_chunks", 0),
                unique_sources=re.get("unique_sources", 0),
                avg_relevance_score=re.get("avg_relevance_score", 0.0),
            )

        # Parse metrics
        if data.get("metrics"):
            m = data["metrics"]
            evidence.metrics = TraceMetrics(
                total_latency_ms=m.get("total_latency_ms", 0),
                llm_latency_ms=m.get("llm_latency_ms", 0),
                tool_latency_ms=m.get("tool_latency_ms", 0),
                total_tokens=m.get("total_tokens", 0),
                input_tokens=m.get("input_tokens", 0),
                output_tokens=m.get("output_tokens", 0),
                total_cost_usd=m.get("total_cost_usd", 0.0),
                llm_calls=m.get("llm_calls", 0),
                tool_calls=m.get("tool_calls", 0),
                retrieval_calls=m.get("retrieval_calls", 0),
                error_count=m.get("error_count", 0),
                retry_count=m.get("retry_count", 0),
            )

        # Parse created_at
        if data.get("created_at"):
            evidence.created_at = datetime.fromisoformat(data["created_at"])

        return evidence

