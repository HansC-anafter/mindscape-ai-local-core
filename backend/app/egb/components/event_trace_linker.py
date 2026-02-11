"""
Event Trace Linker（事件與 trace 的鏈接器）

⚠️ P0-11：事件層（MindEvent）和 trace 層（EGB）的對齊點

負責：
1. 將 MindEvent 鏈接到 trace（run_id）
2. 從事件回溯補全 trace（用於外部 callback 很晚才回的情況）
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from dataclasses import dataclass

from backend.app.egb.schemas.correlation_ids import CorrelationIds
from backend.app.core.trace.trace_schema import TraceGraph, TraceStatus
from backend.app.core.trace.external_job_node import ExternalJobNode

logger = logging.getLogger(__name__)


@dataclass
class EventTraceMapping:
    """事件與 trace 的映射"""
    event_id: str
    run_id: str
    span_id: Optional[str] = None
    event_timestamp: datetime = None
    trace_timestamp: Optional[datetime] = None


class EventTraceLinker:
    """
    事件與 trace 的鏈接器

    ⚠️ P0-11 硬規則：確保每個 MindEvent 都能關聯到 run_id
    """

    def __init__(self, store=None):
        """
        初始化 EventTraceLinker

        Args:
            store: 持久化存儲（可選，用於存儲映射）
        """
        self.store = store
        self._event_mappings: Dict[str, EventTraceMapping] = {}  # event_id -> mapping

    async def link_event_to_trace(
        self,
        event: Dict[str, Any],  # MindEvent dict
        correlation_ids: CorrelationIds
    ) -> EventTraceMapping:
        """
        將事件鏈接到 trace

        ⚠️ P0-11 硬規則：
        1. 如果 event 已有 run_id，直接使用
        2. 如果 event 沒有 run_id，但 correlation_ids 有，則補上
        3. 如果 event 先發生（event_timestamp < trace_timestamp），則建立「延遲鏈接」

        Args:
            event: MindEvent（dict 格式）
            correlation_ids: CorrelationIds

        Returns:
            EventTraceMapping: 映射記錄
        """
        event_id = event.get("id") or event.get("event_id")
        if not event_id:
            raise ValueError("Event must have id or event_id")

        # 提取或設置 run_id
        run_id = event.get("run_id") or correlation_ids.run_id
        if not run_id:
            raise ValueError("Event or correlation_ids must have run_id")

        # 提取 span_id
        span_id = event.get("span_id") or event.get("correlation_ids", {}).get("span_id")

        # 提取時間戳
        event_timestamp = event.get("event_timestamp") or event.get("timestamp")
        if isinstance(event_timestamp, str):
            event_timestamp = datetime.fromisoformat(event_timestamp)
        elif event_timestamp is None:
            event_timestamp = _utc_now()

        trace_timestamp = event.get("trace_timestamp")
        if isinstance(trace_timestamp, str):
            trace_timestamp = datetime.fromisoformat(trace_timestamp)

        # 創建映射
        mapping = EventTraceMapping(
            event_id=event_id,
            run_id=run_id,
            span_id=span_id,
            event_timestamp=event_timestamp,
            trace_timestamp=trace_timestamp,
        )

        # 存儲映射
        self._event_mappings[event_id] = mapping

        # 如果 event 沒有 run_id，補上
        if not event.get("run_id"):
            event["run_id"] = run_id
            if not event.get("correlation_ids"):
                event["correlation_ids"] = {}
            event["correlation_ids"]["run_id"] = run_id

        # 持久化（如果 store 可用）
        if self.store:
            try:
                await self.store.save_event_trace_mapping(
                    event_id=event_id,
                    run_id=run_id,
                    span_id=span_id,
                    event_timestamp=event_timestamp,
                    trace_timestamp=trace_timestamp,
                )
            except Exception as e:
                logger.warning(f"EventTraceLinker: Failed to save mapping to store: {e}")

        logger.debug(
            f"EventTraceLinker: Linked event {event_id} to run {run_id}"
        )

        return mapping

    async def get_run_id_by_event_id(self, event_id: str) -> Optional[str]:
        """
        根據 event_id 獲取 run_id

        ⚠️ P0-11 驗收標準：能用 event_id 反查回 run_id
        """
        mapping = self._event_mappings.get(event_id)
        if mapping:
            return mapping.run_id

        # 從 store 查詢（如果可用）
        if self.store:
            try:
                mapping_dict = await self.store.get_event_trace_mapping(event_id)
                if mapping_dict:
                    return mapping_dict.get("run_id")
            except Exception as e:
                logger.warning(f"EventTraceLinker: Failed to get mapping from store: {e}")

        return None

    async def backfill_trace_from_events(
        self,
        run_id: str,
        events: List[Dict[str, Any]]
    ) -> TraceGraph:
        """
        從事件回溯補全 trace

        ⚠️ P0-11 硬規則：用於外部 callback 很晚才回，但事件已經發生的情況

        Args:
            run_id: Run ID
            events: 事件列表（MindEvent dict 格式）

        Returns:
            TraceGraph: 補全後的 trace graph
        """
        from backend.app.core.trace.trace_schema import TraceGraph

        trace_graph = TraceGraph(run_id=run_id)

        # 找到所有與該 run_id 相關的事件
        related_events = [
            e for e in events
            if e.get("run_id") == run_id or
            e.get("correlation_ids", {}).get("run_id") == run_id
        ]

        # 按時間排序
        related_events.sort(
            key=lambda x: x.get("event_timestamp") or x.get("timestamp") or _utc_now()
        )

        # 補全 trace 的缺失節點
        for event in related_events:
            event_type = event.get("event_type") or event.get("type")
            channel = event.get("channel")

            if event_type == "TOOL_CALL" and channel == "external":
                # 建立 ExternalJob node
                node = await self._create_external_job_node_from_event(event, run_id)
                if node:
                    trace_graph.nodes.append(node)

        logger.info(
            f"EventTraceLinker: Backfilled trace {run_id} with {len(trace_graph.nodes)} nodes from events"
        )

        return trace_graph

    async def _create_external_job_node_from_event(
        self,
        event: Dict[str, Any],
        run_id: str
    ) -> Optional[ExternalJobNode]:
        """
        從事件創建 ExternalJob node

        Args:
            event: MindEvent（dict 格式）
            run_id: Run ID

        Returns:
            ExternalJobNode 或 None
        """
        try:
            tool_name = event.get("tool_name") or event.get("channel", "unknown")
            external_job_id = event.get("external_job_id") or event.get("job_id") or event.get("id")

            if not external_job_id:
                return None

            # 提取時間戳
            event_timestamp = event.get("event_timestamp") or event.get("timestamp")
            if isinstance(event_timestamp, str):
                event_timestamp = datetime.fromisoformat(event_timestamp)
            elif event_timestamp is None:
                event_timestamp = _utc_now()

            # 創建 ExternalJobNode
            node = ExternalJobNode.create(
                tool_name=tool_name,
                external_job_id=external_job_id,
                name=event.get("name") or tool_name,
                external_run_id=event.get("external_run_id"),
                deep_link=event.get("deep_link_to_external_log"),
                span_id=event.get("id"),
            )

            node.status = TraceStatus.PENDING  # 初始狀態
            node.start_time = event_timestamp

            return node

        except Exception as e:
            logger.warning(f"EventTraceLinker: Failed to create external job node from event: {e}")
            return None

