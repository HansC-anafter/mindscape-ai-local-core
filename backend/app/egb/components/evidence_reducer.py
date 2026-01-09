"""
EvidenceReducer（證據收斂器）

職責：把 raw trace → 結構化證據（數字、diff、路徑序列、引用 ids）
這是 EGB 的第二個元件，負責將觀測數據轉為可計算的結構化證據。

關鍵設計：盡量不用 LLM，純計算/規則處理，以控制成本。
"""

import logging
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime

from backend.app.core.trace.trace_schema import (
    TraceGraph,
    TraceNode,
    TraceNodeType,
    TraceStatus,
)
from backend.app.egb.schemas.structured_evidence import (
    StructuredEvidence,
    ToolPath,
    RetrievalEvidence,
    PolicyCheckEvidence,
    StrictnessChange,
    TraceMetrics,
)
from backend.app.egb.schemas.correlation_ids import CorrelationIds

logger = logging.getLogger(__name__)


class EvidenceReducer:
    """
    證據收斂器

    負責：
    1. 從 TraceGraph 提取工具呼叫路徑
    2. 從 TraceGraph 提取檢索證據
    3. 計算各種指標（latency, tokens, cost, error_rate）
    4. 提取政策檢查結果

    設計原則：
    - 純計算/規則處理，不使用 LLM
    - 輸出是 StructuredEvidence，可直接用於 DriftScorer
    """

    def __init__(self):
        """初始化 EvidenceReducer"""
        pass

    async def reduce_trace(
        self,
        trace: TraceGraph,
        correlation_ids: CorrelationIds
    ) -> StructuredEvidence:
        """
        收斂單個 trace 為結構化證據

        ⚠️ P0-1 修正：必須接收 correlation_ids 輸入
        因為 StructuredEvidence 需要 workspace_id/intent_id/strictness_level/policy_version

        Args:
            trace: TraceGraph 對象（使用 trace.run_id）
            correlation_ids: CorrelationIds（包含 intent_id/strictness_level/policy_version 等）

        Returns:
            StructuredEvidence: 結構化證據（包含所有必要欄位）
        """
        # ⚠️ P0-1：使用 trace.run_id（不再用 trace.trace_id）
        run_id = trace.run_id

        evidence = StructuredEvidence(
            evidence_id=f"evidence-{run_id}",
            run_id=run_id,
            # ⚠️ P0-1 新增：CorrelationIds 欄位
            workspace_id=correlation_ids.workspace_id,
            intent_id=correlation_ids.intent_id,
            strictness_level=correlation_ids.strictness_level,
            mind_lens_level=correlation_ids.mind_lens_level,
            policy_version=correlation_ids.policy_version,
            created_at=datetime.utcnow(),
        )

        # 提取工具路徑
        evidence.tool_path = await self.extract_tool_path(trace)

        # 提取檢索證據
        evidence.retrieval_evidence = await self.extract_retrieval_evidence(trace)

        # ⚠️ P0-2 新增：提取證據 ID
        evidence.retrieval_chunk_ids = evidence.retrieval_evidence.chunk_ids
        evidence.tool_span_ids = await self._extract_tool_span_ids(trace)
        evidence.policy_span_ids = await self._extract_policy_span_ids(trace)

        # 計算指標
        evidence.metrics = await self.compute_metrics(trace)

        # 提取政策檢查
        evidence.policy_checks = await self.extract_policy_checks(trace)

        # 提取嚴謹度變更
        evidence.strictness_changes = await self.extract_strictness_changes(trace)

        # 計算輸出摘要
        evidence.output_hash = await self._compute_output_hash(trace)
        evidence.output_length = await self._compute_output_length(trace)

        # ⚠️ P0-5 新增：計算結構化輸出相關 hash（如果 strictness ≥ 1）
        if correlation_ids.strictness_level >= 1:
            evidence.structured_output_hash = await self._compute_structured_output_hash(trace)
            evidence.key_fields_hash_map = await self._compute_key_fields_hash_map(trace, correlation_ids)

        logger.debug(
            f"EvidenceReducer: Reduced trace {run_id} to evidence "
            f"with {len(evidence.tool_path.tool_names)} tools, "
            f"{evidence.metrics.total_tokens} tokens"
        )

        return evidence

    async def _extract_tool_span_ids(self, trace: TraceGraph) -> List[str]:
        """
        提取工具節點的 node_id

        ⚠️ P0-8 擴展：也包含 EXTERNAL_JOB 節點
        """
        return [
            node.node_id
            for node in trace.nodes
            if node.node_type in [TraceNodeType.TOOL, TraceNodeType.EXTERNAL_JOB]
        ]

    async def _extract_policy_span_ids(self, trace: TraceGraph) -> List[str]:
        """提取政策節點的 node_id"""
        return [
            node.node_id
            for node in trace.nodes
            if node.node_type == TraceNodeType.POLICY
        ]

    async def _compute_structured_output_hash(self, trace: TraceGraph) -> Optional[str]:
        """
        計算結構化輸出的 hash

        ⚠️ v1.2.2 修正：使用 structured output 的完整 JSON hash
        算法：找到最後一個 LLM node 的 output，計算 JSON hash
        """
        import json

        # 找到最後一個 LLM node（通常是最終輸出）
        llm_nodes = [
            node for node in trace.nodes
            if node.node_type == TraceNodeType.LLM
        ]

        if not llm_nodes:
            return None

        # 取最後一個 LLM node
        final_llm = llm_nodes[-1]

        # 獲取 output（優先使用 structured output）
        output_data = final_llm.output_data
        if not output_data:
            return None

        # 如果是 dict，視為 structured output
        if isinstance(output_data, dict):
            # 序列化為 JSON（排序鍵以確保一致性）
            json_str = json.dumps(output_data, sort_keys=True, ensure_ascii=False)
            hash_obj = hashlib.sha256(json_str.encode())
            return hash_obj.hexdigest()[:32]  # 返回 32 字元 hash

        # 如果是字串，也計算 hash
        if isinstance(output_data, str):
            hash_obj = hashlib.sha256(output_data.encode())
            return hash_obj.hexdigest()[:32]

        return None

    async def _compute_key_fields_hash_map(
        self,
        trace: TraceGraph,
        correlation_ids: Optional[CorrelationIds] = None
    ) -> Optional[Dict[str, str]]:
        """
        計算 key_fields_hash_map

        ⚠️ v1.2.2 修正：使用 JSON Pointer 白名單
        算法：
        1. 找到最後一個 LLM node 的 structured output
        2. 根據 policy_version 獲取 key_fields whitelist（JSON Pointer 列表）
        3. 對每個 pointer 提取值並計算 hash
        4. 返回 pointer -> hash 的映射

        ⚠️ 注意：如果沒有 policy_version 或 whitelist，返回 None
        """
        import json

        # 找到最後一個 LLM node
        llm_nodes = [
            node for node in trace.nodes
            if node.node_type == TraceNodeType.LLM
        ]

        if not llm_nodes:
            return None

        final_llm = llm_nodes[-1]
        output_data = final_llm.output_data

        if not isinstance(output_data, dict):
            return None

        # TODO: 從 policy_version 獲取 key_fields whitelist
        # 目前先使用預設白名單（所有頂層鍵）
        key_pointers = list(output_data.keys()) if isinstance(output_data, dict) else []

        # 如果沒有 whitelist，返回 None
        if not key_pointers:
            return None

        # 計算每個 pointer 的 hash
        hash_map = {}
        for pointer in key_pointers:
            # 提取值（使用 JSON Pointer 或直接鍵）
            try:
                if pointer.startswith("/"):
                    # JSON Pointer 格式
                    value = self._extract_json_pointer(output_data, pointer)
                else:
                    # 直接鍵
                    value = output_data.get(pointer)

                if value is not None:
                    # 序列化值並計算 hash
                    value_str = json.dumps(value, sort_keys=True, ensure_ascii=False)
                    hash_obj = hashlib.sha256(value_str.encode())
                    hash_map[pointer] = hash_obj.hexdigest()[:16]  # 16 字元 hash
            except Exception as e:
                logger.warning(f"Failed to compute hash for pointer {pointer}: {e}")
                continue

        return hash_map if hash_map else None

    def _extract_json_pointer(self, data: dict, pointer: str) -> Any:
        """
        從 JSON 中提取 JSON Pointer 指向的值

        簡化實現：只支持頂層鍵（/key）
        """
        if not pointer.startswith("/"):
            return None

        key = pointer[1:]  # 移除前導 "/"
        return data.get(key)

    async def extract_tool_path(self, trace: TraceGraph) -> ToolPath:
        """
        提取工具呼叫路徑

        從 trace 的所有 TOOL 類型節點中提取工具呼叫序列。

        ⚠️ P0-8 擴展：也包含 EXTERNAL_JOB 節點
        """
        tool_path = ToolPath()

        # 找出所有 TOOL 和 EXTERNAL_JOB 類型的節點
        tool_nodes = [
            node for node in trace.nodes
            if node.node_type in [TraceNodeType.TOOL, TraceNodeType.EXTERNAL_JOB]
        ]

        # 按時間排序
        tool_nodes.sort(key=lambda x: x.start_time)

        for node in tool_nodes:
            # 工具名
            tool_path.tool_names.append(node.name)

            # 參數 hash
            if node.input_data:
                args_str = str(sorted(node.input_data.items()))
                args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:8]
            else:
                args_hash = "empty"
            tool_path.tool_args_hashes.append(args_hash)

            # 成功標記
            tool_path.success_flags.append(node.status == TraceStatus.SUCCESS)

            # 延遲
            duration = node.duration_ms() or 0
            tool_path.durations_ms.append(duration)

        return tool_path

    async def extract_retrieval_evidence(
        self,
        trace: TraceGraph
    ) -> RetrievalEvidence:
        """
        提取檢索證據

        從 trace 中識別檢索相關的節點並提取證據。
        """
        retrieval = RetrievalEvidence()

        for node in trace.nodes:
            # 檢查是否是檢索相關節點
            if self._is_retrieval_node(node):
                # 從 output_data 提取 chunk IDs
                if node.output_data:
                    chunks = node.output_data.get("chunks", [])
                    for chunk in chunks:
                        if isinstance(chunk, dict):
                            chunk_id = chunk.get("id") or chunk.get("chunk_id")
                            if chunk_id:
                                retrieval.chunk_ids.append(chunk_id)
                            source = chunk.get("source") or chunk.get("file")
                            if source:
                                retrieval.sources.append(source)

                # 從 input_data 提取查詢文本
                if node.input_data:
                    query = node.input_data.get("query") or node.input_data.get("text")
                    if query:
                        retrieval.query_texts.append(query)

        # 計算統計
        retrieval.total_chunks = len(retrieval.chunk_ids)
        retrieval.unique_sources = len(set(retrieval.sources))

        return retrieval

    async def compute_metrics(self, trace: TraceGraph) -> TraceMetrics:
        """
        計算 trace 指標

        包括延遲、token、成本、錯誤數等。
        """
        metrics = TraceMetrics()

        for node in trace.nodes:
            # 計算延遲
            duration = node.duration_ms() or 0
            metrics.total_latency_ms += duration

            if node.node_type == TraceNodeType.LLM:
                metrics.llm_latency_ms += duration
                metrics.llm_calls += 1

                # 從 metadata 提取 token 和成本
                if node.metadata:
                    tokens = node.metadata.cost_tokens or 0
                    metrics.total_tokens += tokens

            elif node.node_type == TraceNodeType.TOOL:
                metrics.tool_latency_ms += duration
                metrics.tool_calls += 1

            # 統計錯誤
            if node.status == TraceStatus.FAILED:
                metrics.error_count += 1

            # 從 metadata 提取 retry 資訊
            if node.metadata and node.metadata.custom_metadata:
                retry_count = node.metadata.custom_metadata.get("retry_count", 0)
                metrics.retry_count += retry_count

        # 計算檢索呼叫數
        metrics.retrieval_calls = len([
            n for n in trace.nodes
            if self._is_retrieval_node(n)
        ])

        return metrics

    async def extract_policy_checks(
        self,
        trace: TraceGraph
    ) -> List[PolicyCheckEvidence]:
        """
        提取政策檢查結果

        從 POLICY 類型節點中提取政策檢查結果。
        """
        policy_checks = []

        for node in trace.nodes:
            if node.node_type == TraceNodeType.POLICY:
                check = PolicyCheckEvidence(
                    policy_name=node.name,
                    check_type=self._infer_policy_type(node.name),
                    passed=node.status == TraceStatus.SUCCESS,
                    reason=node.metadata.error_message if node.metadata else None,
                    span_id=node.node_id,
                )

                # 從 input/output 提取閾值和實際值
                if node.input_data:
                    check.threshold_value = node.input_data.get("threshold")
                if node.output_data:
                    check.actual_value = node.output_data.get("value")

                policy_checks.append(check)

        return policy_checks

    async def extract_strictness_changes(
        self,
        trace: TraceGraph
    ) -> List[StrictnessChange]:
        """
        提取嚴謹度變更

        從 trace metadata 或特定節點中提取嚴謹度變更記錄。
        """
        changes = []

        for node in trace.nodes:
            if node.metadata and node.metadata.custom_metadata:
                strictness_change = node.metadata.custom_metadata.get("strictness_change")
                if strictness_change:
                    changes.append(StrictnessChange(
                        from_level=strictness_change.get("from", 0),
                        to_level=strictness_change.get("to", 0),
                        reason=strictness_change.get("reason", ""),
                        triggered_by=strictness_change.get("triggered_by", "auto"),
                        span_id=node.node_id,
                        timestamp=node.start_time,
                    ))

        return changes

    async def _compute_output_hash(self, trace: TraceGraph) -> str:
        """計算輸出內容的 hash"""
        # 找到最後一個輸出節點
        output_nodes = [
            n for n in trace.nodes
            if n.output_data and n.status == TraceStatus.SUCCESS
        ]

        if not output_nodes:
            return "no_output"

        # 使用最後一個成功節點的輸出
        last_output = output_nodes[-1].output_data
        output_str = str(last_output)

        return hashlib.sha256(output_str.encode()).hexdigest()[:16]

    async def _compute_output_length(self, trace: TraceGraph) -> int:
        """計算輸出長度"""
        output_nodes = [
            n for n in trace.nodes
            if n.output_data and n.status == TraceStatus.SUCCESS
        ]

        if not output_nodes:
            return 0

        last_output = output_nodes[-1].output_data
        return len(str(last_output))

    def _is_retrieval_node(self, node: TraceNode) -> bool:
        """判斷是否為檢索節點"""
        retrieval_keywords = ["retrieval", "search", "vector", "embed", "rag"]
        name_lower = node.name.lower()
        return any(kw in name_lower for kw in retrieval_keywords)

    def _infer_policy_type(self, policy_name: str) -> str:
        """根據政策名稱推斷政策類型"""
        name_lower = policy_name.lower()
        if "cost" in name_lower:
            return "cost"
        elif "node" in name_lower:
            return "node"
        elif "preflight" in name_lower:
            return "preflight"
        else:
            return "custom"

