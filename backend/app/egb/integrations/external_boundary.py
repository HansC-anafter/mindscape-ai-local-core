"""
External Boundary Contract（外部邊界契約）

⚠️ P0-7：出站/入站 correlation propagation

負責：
1. 出站：在所有 HTTP client / webhook / workflow 工具觸發時注入 correlation headers
2. 入站：接收外部 callback 並重新掛回對應的 run
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

from backend.app.egb.schemas.correlation_ids import CorrelationIds

logger = logging.getLogger(__name__)


# ⚠️ P0-7：出站 header 名稱（硬契約）
OUTBOUND_HEADER_RUN_ID = "X-Mindscape-Run-Id"
OUTBOUND_HEADER_INTENT_ID = "X-Mindscape-Intent-Id"
OUTBOUND_HEADER_WORKSPACE_ID = "X-Mindscape-Workspace-Id"
OUTBOUND_HEADER_SPAN_ID = "X-Mindscape-Span-Id"  # 可選


class ExternalBoundaryContract:
    """
    外部邊界契約管理器

    ⚠️ P0-7 硬規則：所有跨平台出站/入站都必須通過這個契約
    """

    def __init__(self):
        """初始化 ExternalBoundaryContract"""
        pass

    def inject_outbound_headers(
        self,
        correlation_ids: CorrelationIds,
        span_id: Optional[str] = None
    ) -> Dict[str, str]:
        """
        注入出站 headers

        ⚠️ P0-7 硬規則：所有 HTTP client / webhook / workflow 工具觸發時必須調用

        Args:
            correlation_ids: CorrelationIds
            span_id: 可選的 span_id（用於把外部 job 回來時掛回某個 span）

        Returns:
            Headers 字典
        """
        headers = {
            OUTBOUND_HEADER_RUN_ID: correlation_ids.run_id,
            OUTBOUND_HEADER_INTENT_ID: correlation_ids.intent_id,
            OUTBOUND_HEADER_WORKSPACE_ID: correlation_ids.workspace_id,
        }

        if span_id:
            headers[OUTBOUND_HEADER_SPAN_ID] = span_id

        return headers

    def inject_outbound_metadata(
        self,
        correlation_ids: CorrelationIds,
        span_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        注入出站 metadata（用於 workflow 工具，如 n8n / Zapier）

        ⚠️ P0-7 硬規則：所有 workflow 工具觸發時必須在 payload metadata 中包含這些欄位

        Args:
            correlation_ids: CorrelationIds
            span_id: 可選的 span_id

        Returns:
            Metadata 字典
        """
        metadata = {
            "mindscape_run_id": correlation_ids.run_id,
            "mindscape_intent_id": correlation_ids.intent_id,
            "mindscape_workspace_id": correlation_ids.workspace_id,
        }

        if span_id:
            metadata["mindscape_span_id"] = span_id

        return metadata

    def extract_inbound_correlation(
        self,
        headers: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[CorrelationIds]:
        """
        從入站請求提取 correlation

        ⚠️ P0-7 硬規則：外部 callback 到達時必須調用此方法

        Args:
            headers: HTTP headers（優先）
            metadata: Metadata（fallback，用於 workflow 工具）

        Returns:
            CorrelationIds 或 None
        """
        # 優先從 headers 提取
        if headers:
            run_id = headers.get(OUTBOUND_HEADER_RUN_ID)
            intent_id = headers.get(OUTBOUND_HEADER_INTENT_ID)
            workspace_id = headers.get(OUTBOUND_HEADER_WORKSPACE_ID)

            if run_id and intent_id and workspace_id:
                return CorrelationIds(
                    workspace_id=workspace_id,
                    intent_id=intent_id,
                    decision_id="",  # callback 可能沒有 decision_id
                    playbook_id="",  # callback 可能沒有 playbook_id
                    run_id=run_id,
                )

        # Fallback 到 metadata
        if metadata:
            run_id = metadata.get("mindscape_run_id")
            intent_id = metadata.get("mindscape_intent_id")
            workspace_id = metadata.get("mindscape_workspace_id")

            if run_id and intent_id and workspace_id:
                return CorrelationIds(
                    workspace_id=workspace_id,
                    intent_id=intent_id,
                    decision_id="",
                    playbook_id="",
                    run_id=run_id,
                )

        return None

    def extract_span_id(
        self,
        headers: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        從入站請求提取 span_id

        Args:
            headers: HTTP headers
            metadata: Metadata

        Returns:
            span_id 或 None
        """
        if headers:
            return headers.get(OUTBOUND_HEADER_SPAN_ID)
        if metadata:
            return metadata.get("mindscape_span_id")
        return None


# 全局實例
_global_boundary: Optional[ExternalBoundaryContract] = None


def get_external_boundary() -> ExternalBoundaryContract:
    """獲取全局 ExternalBoundaryContract 實例"""
    global _global_boundary
    if _global_boundary is None:
        _global_boundary = ExternalBoundaryContract()
    return _global_boundary

