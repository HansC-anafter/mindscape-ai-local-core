"""
Trace Normalizer

Langfuse → TraceGraph 正規化層。
這是 EGB 與觀測後端之間的「抗耦合保險」。

設計目的：
1. 將 Langfuse 原生資料（trace/generation/span/observation）轉為統一格式
2. 未來換供應商（OTel / Phoenix / 其他後端）時只需改這一層
3. 確保 EvidenceReducer 不依賴任何特定觀測後端的資料結構
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from dataclasses import dataclass, field
from enum import Enum

from backend.app.core.trace.trace_schema import (
    TraceGraph,
    TraceNode,
    TraceEdge,
    TraceNodeType,
    TraceEdgeType,
    TraceStatus,
    TraceMetadata,
)

# ⚠️ P0-8 新增：ExternalJobNode（延遲導入，避免循環依賴）
try:
    from backend.app.core.trace.external_job_node import ExternalJobNode
except ImportError:
    ExternalJobNode = None

logger = logging.getLogger(__name__)


class ObservationType(str, Enum):
    """Langfuse observation 類型"""
    GENERATION = "generation"  # LLM 呼叫
    SPAN = "span"              # 一般 span
    EVENT = "event"            # 事件


@dataclass
class NormalizationResult:
    """正規化結果"""
    success: bool
    trace_graph: Optional[TraceGraph] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    # 統計
    total_observations: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    retrieval_calls: int = 0


class TraceNormalizer:
    """
    Trace 正規化器

    將 Langfuse 原生資料轉換為 EGB 統一的 TraceGraph 格式。

    Input: Langfuse trace payload（dict）
    Output: TraceGraph（nodes: llm/tool/retrieval/policy_check, edges: parent-child, plus metrics）

    使用方式：
        normalizer = TraceNormalizer()
        result = normalizer.normalize(langfuse_trace_payload)
        if result.success:
            trace_graph = result.trace_graph
    """

    # Langfuse observation type → TraceNodeType 映射
    NODE_TYPE_MAPPING = {
        "generation": TraceNodeType.LLM,
        "span": TraceNodeType.TOOL,  # 預設，會根據名稱再判斷
        "event": TraceNodeType.STATE,
    }

    # 用於識別特定類型 span 的關鍵字
    RETRIEVAL_KEYWORDS = ["retrieval", "search", "vector", "embed", "rag", "query"]
    POLICY_KEYWORDS = ["policy", "governance", "check", "gate", "validate"]
    TOOL_KEYWORDS = ["tool", "execute", "call", "invoke", "run"]

    def __init__(self):
        """初始化 TraceNormalizer"""
        pass

    def normalize(
        self,
        langfuse_payload: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> NormalizationResult:
        """
        將 Langfuse trace payload 正規化為 TraceGraph

        ⚠️ P0-1 硬規則：run_id 是單一真相（run_id == trace_id）
        Langfuse trace.id 直接作為 run_id

        Args:
            langfuse_payload: Langfuse trace 的原始資料
            run_id: 可選的 run_id（如不提供則從 payload 的 trace.id 取）

        Returns:
            NormalizationResult: 正規化結果
        """
        result = NormalizationResult(success=False)

        try:
            # ⚠️ P0-1：提取 run_id（Langfuse trace.id 直接作為 run_id）
            extracted_run_id = run_id or langfuse_payload.get("id", "")
            if not extracted_run_id:
                result.error = "Missing run_id in payload (expected trace.id)"
                return result

            # 創建 TraceGraph（使用 run_id）
            trace_graph = TraceGraph(run_id=extracted_run_id)

            # 提取 observations
            observations = langfuse_payload.get("observations", [])
            result.total_observations = len(observations)

            # 按 startTime 排序
            observations = sorted(
                observations,
                key=lambda x: x.get("startTime", "")
            )

            # 轉換每個 observation
            node_map: Dict[str, TraceNode] = {}  # observation_id -> TraceNode

            for obs in observations:
                node = self._convert_observation(obs, langfuse_payload)
                if node:
                    trace_graph.nodes.append(node)
                    node_map[obs.get("id", "")] = node

                    # 統計
                    if node.node_type == TraceNodeType.LLM:
                        result.llm_calls += 1
                    elif node.node_type == TraceNodeType.TOOL:
                        if self._is_retrieval_node(node.name):
                            result.retrieval_calls += 1
                        else:
                            result.tool_calls += 1

            # 建立 edges（parent-child 關係）
            for obs in observations:
                parent_id = obs.get("parentObservationId")
                if parent_id and parent_id in node_map:
                    child_id = obs.get("id", "")
                    if child_id in node_map:
                        edge = TraceEdge(
                            edge_id=f"{parent_id}->{child_id}",
                            source_node_id=node_map[parent_id].node_id,
                            target_node_id=node_map[child_id].node_id,
                            edge_type=TraceEdgeType.SEQUENTIAL,
                        )
                        trace_graph.edges.append(edge)

            # 設置 root node
            if trace_graph.nodes:
                # 找沒有 parent 的節點作為 root
                nodes_with_parent = set(
                    obs.get("id") for obs in observations
                    if obs.get("parentObservationId")
                )
                root_nodes = [
                    n for n in trace_graph.nodes
                    if n.node_id not in nodes_with_parent
                ]
                if root_nodes:
                    trace_graph.root_node_id = root_nodes[0].node_id

            result.success = True
            result.trace_graph = trace_graph

            logger.debug(
                f"TraceNormalizer: Normalized trace {extracted_run_id} with "
                f"{len(trace_graph.nodes)} nodes, {len(trace_graph.edges)} edges"
            )

        except Exception as e:
            logger.error(f"TraceNormalizer: Failed to normalize trace: {e}")
            result.error = str(e)

        return result

    def normalize_from_observations(
        self,
        observations: List[Dict[str, Any]],
        run_id: str,  # ⚠️ P0-1：改為 run_id
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NormalizationResult:
        """
        從 observations 列表正規化（不需要完整 trace payload）

        ⚠️ P0-1 硬規則：run_id 是單一真相（run_id == trace_id）

        Args:
            observations: Langfuse observations 列表
            run_id: Run ID（= trace_id）
            metadata: 額外的 metadata

        Returns:
            NormalizationResult
        """
        # 構建 fake payload
        payload = {
            "id": run_id,  # ⚠️ P0-1：使用 run_id
            "observations": observations,
            "metadata": metadata or {},
        }
        return self.normalize(payload, run_id=run_id)

    def _convert_observation(
        self,
        obs: Dict[str, Any],
        trace_payload: Dict[str, Any],
    ) -> Optional[TraceNode]:
        """
        將單個 observation 轉換為 TraceNode

        ⚠️ P0-8 擴展：支援 ExternalJob node
        """
        try:
            obs_id = obs.get("id", "")
            obs_type = obs.get("type", "span")
            name = obs.get("name", "unknown")

            # ⚠️ P0-8：檢查是否是 ExternalJob（從 metadata 判斷）
            metadata = obs.get("metadata", {})
            if metadata.get("egb_node_type") == "external_job" and ExternalJobNode:
                return self._convert_external_job_observation(obs, trace_payload)

            # 確定 node type
            node_type = self._determine_node_type(obs_type, name)

            # 確定 status
            status = self._determine_status(obs)

            # 解析時間
            start_time = self._parse_datetime(obs.get("startTime"))
            end_time = self._parse_datetime(obs.get("endTime"))

            # 構建 metadata
            workspace_id = trace_payload.get("metadata", {}).get("workspace_id", "")
            execution_id = trace_payload.get("id", "")

            node_metadata = TraceMetadata(
                workspace_id=workspace_id,
                execution_id=execution_id,
                model_name=obs.get("model"),
                cost_tokens=self._extract_tokens(obs),
                latency_ms=self._calculate_latency(start_time, end_time),
                error_message=obs.get("statusMessage") if status == TraceStatus.FAILED else None,
                custom_metadata=obs.get("metadata", {}),
            )

            # 構建 input/output
            input_data = obs.get("input")
            if isinstance(input_data, str):
                input_data = {"text": input_data}
            elif not isinstance(input_data, dict):
                input_data = {"value": input_data} if input_data else None

            output_data = obs.get("output")
            if isinstance(output_data, str):
                output_data = {"text": output_data}
            elif not isinstance(output_data, dict):
                output_data = {"value": output_data} if output_data else None

            return TraceNode(
                node_id=obs_id,
                node_type=node_type,
                name=name,
                status=status,
                start_time=start_time or _utc_now(),
                end_time=end_time,
                metadata=node_metadata,
                input_data=input_data,
                output_data=output_data,
            )

        except Exception as e:
            logger.warning(f"TraceNormalizer: Failed to convert observation: {e}")
            return None

    def _convert_external_job_observation(
        self,
        obs: Dict[str, Any],
        trace_payload: Dict[str, Any],
    ) -> Optional[ExternalJobNode]:
        """
        將 observation 轉換為 ExternalJobNode

        ⚠️ P0-8 新增：處理外部工作流節點
        """
        try:
            obs_id = obs.get("id", "")
            name = obs.get("name", "unknown")
            metadata = obs.get("metadata", {})

            # 提取外部 job 資訊
            tool_name = metadata.get("tool_name") or metadata.get("egb_tool_name") or name
            external_job_id = metadata.get("external_job_id") or obs_id
            external_run_id = metadata.get("external_run_id")
            deep_link = metadata.get("deep_link_to_external_log")

            # 解析時間
            start_time = self._parse_datetime(obs.get("startTime"))
            end_time = self._parse_datetime(obs.get("endTime"))

            # 確定 status
            status = self._determine_status(obs)

            # 提取 output_fingerprint
            output_data = obs.get("output")
            output_fingerprint = None
            if output_data:
                import hashlib
                import json
                output_str = json.dumps(output_data, sort_keys=True, ensure_ascii=False)
                output_fingerprint = hashlib.sha256(output_str.encode()).hexdigest()[:32]

            # 創建 ExternalJobNode
            node = ExternalJobNode.create(
                tool_name=tool_name,
                external_job_id=external_job_id,
                name=name,
                external_run_id=external_run_id,
                deep_link=deep_link,
                span_id=obs_id,
            )

            # 設置狀態和時間
            node.status = status
            node.start_time = start_time or _utc_now()
            if end_time:
                node.end_time = end_time
            node.output_fingerprint = output_fingerprint
            node.retry_count = metadata.get("retry_count", 0)

            return node

        except Exception as e:
            logger.warning(f"TraceNormalizer: Failed to convert external job observation: {e}")
            return None

    def _determine_node_type(self, obs_type: str, name: str) -> TraceNodeType:
        """根據 observation type 和 name 確定 node type"""
        # 先根據 observation type 判斷
        if obs_type == "generation":
            return TraceNodeType.LLM

        # 再根據 name 關鍵字判斷
        name_lower = name.lower()

        if any(kw in name_lower for kw in self.RETRIEVAL_KEYWORDS):
            return TraceNodeType.TOOL  # retrieval 也是一種 tool

        if any(kw in name_lower for kw in self.POLICY_KEYWORDS):
            return TraceNodeType.POLICY

        if any(kw in name_lower for kw in self.TOOL_KEYWORDS):
            return TraceNodeType.TOOL

        # 預設
        return self.NODE_TYPE_MAPPING.get(obs_type, TraceNodeType.TOOL)

    def _determine_status(self, obs: Dict[str, Any]) -> TraceStatus:
        """確定 observation 的狀態"""
        level = obs.get("level", "").upper()
        status_message = obs.get("statusMessage", "")

        if level == "ERROR" or "error" in status_message.lower():
            return TraceStatus.FAILED
        elif level == "WARNING":
            return TraceStatus.SUCCESS  # warning 仍算成功
        elif obs.get("endTime"):
            return TraceStatus.SUCCESS
        else:
            return TraceStatus.RUNNING

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """解析 datetime 字串"""
        if not dt_str:
            return None
        try:
            # Langfuse 使用 ISO 格式
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return None

    def _extract_tokens(self, obs: Dict[str, Any]) -> Optional[int]:
        """提取 token 數量"""
        # Langfuse generation 有 usage 欄位
        usage = obs.get("usage", {})
        if usage:
            input_tokens = usage.get("inputTokens", 0) or usage.get("promptTokens", 0)
            output_tokens = usage.get("outputTokens", 0) or usage.get("completionTokens", 0)
            return input_tokens + output_tokens

        # 也可能在 metadata 中
        metadata = obs.get("metadata", {})
        if metadata.get("tokens"):
            return metadata["tokens"]

        return None

    def _calculate_latency(
        self,
        start_time: Optional[datetime],
        end_time: Optional[datetime]
    ) -> Optional[int]:
        """計算延遲（毫秒）"""
        if start_time and end_time:
            delta = end_time - start_time
            return int(delta.total_seconds() * 1000)
        return None

    def _is_retrieval_node(self, name: str) -> bool:
        """判斷是否為 retrieval 節點"""
        name_lower = name.lower()
        return any(kw in name_lower for kw in self.RETRIEVAL_KEYWORDS)


# 便捷函數
def normalize_langfuse_trace(
    payload: Dict[str, Any],
    run_id: Optional[str] = None
) -> Optional[TraceGraph]:
    """
    便捷函數：將 Langfuse payload 正規化為 TraceGraph

    Args:
        payload: Langfuse trace payload
        run_id: 可選的 run_id

    Returns:
        TraceGraph 或 None
    """
    normalizer = TraceNormalizer()
    result = normalizer.normalize(payload, run_id)
    return result.trace_graph if result.success else None

