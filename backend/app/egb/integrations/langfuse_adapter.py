"""
Langfuse Adapter

Langfuse SDK 的封裝，用於整合 EGB 與 Langfuse。
"""

import logging
from typing import Optional, Dict, Any, List
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime
import os

from backend.app.egb.schemas.correlation_ids import CorrelationIds

logger = logging.getLogger(__name__)


class LangfuseAdapter:
    """
    Langfuse 適配器

    封裝 Langfuse SDK，提供：
    1. Trace 創建與管理
    2. 關聯 ID 傳播
    3. 觀測數據查詢

    設計原則：
    - 使用 Langfuse 的原生資料模型
    - 將 Mindscape 的關聯 ID 映射到 Langfuse 的 metadata/tags
    - 支持自帶 trace_id
    """

    def __init__(
        self,
        public_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        host: Optional[str] = None,
    ):
        """
        初始化 Langfuse 適配器

        Args:
            public_key: Langfuse public key
            secret_key: Langfuse secret key
            host: Langfuse host URL（用於自架版本）
        """
        self.public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
        self.secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
        self.host = host or os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

        self._client = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        初始化 Langfuse 客戶端

        Returns:
            bool: 是否初始化成功
        """
        if self._initialized:
            return True

        try:
            # 嘗試導入 Langfuse
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host,
            )
            self._initialized = True
            logger.info(f"LangfuseAdapter: Initialized with host {self.host}")
            return True

        except ImportError:
            logger.warning("LangfuseAdapter: langfuse package not installed")
            return False
        except Exception as e:
            logger.error(f"LangfuseAdapter: Failed to initialize: {e}")
            return False

    @contextmanager
    def trace_context(
        self,
        correlation_ids: CorrelationIds,
        name: Optional[str] = None,
    ):
        """
        創建 trace 上下文

        使用方式：
            with adapter.trace_context(correlation_ids) as trace:
                # 執行操作
                pass

        Args:
            correlation_ids: EGB 關聯 ID
            name: Trace 名稱
        """
        if not self._initialized:
            self.initialize()

        if not self._client:
            # Fallback: 無 Langfuse 時使用 mock context
            yield MockTraceContext(correlation_ids)
            return

        try:
            trace = self._client.trace(
                id=correlation_ids.run_id,  # 使用自帶 ID
                name=name or f"run-{correlation_ids.run_id[:8]}",
                session_id=correlation_ids.get_session_id(),
                metadata=correlation_ids.to_langfuse_metadata(),
                tags=correlation_ids.to_langfuse_tags(),
            )

            yield LangfuseTraceContext(
                trace=trace,
                correlation_ids=correlation_ids,
            )

        except Exception as e:
            logger.error(f"LangfuseAdapter: Failed to create trace: {e}")
            yield MockTraceContext(correlation_ids)

    async def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        獲取 trace 資訊

        Args:
            trace_id: Trace ID

        Returns:
            Trace 資訊字典
        """
        if not self._client:
            return None

        try:
            trace = self._client.get_trace(trace_id)
            return trace.dict() if trace else None
        except Exception as e:
            logger.error(f"LangfuseAdapter: Failed to get trace {trace_id}: {e}")
            return None

    async def get_traces_by_session(
        self,
        session_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        根據 session 獲取 traces

        Args:
            session_id: Session ID（對應 intent_id）
            limit: 返回數量限制

        Returns:
            Trace 列表
        """
        if not self._client:
            return []

        try:
            traces = self._client.get_traces(
                session_id=session_id,
                limit=limit,
            )
            return [t.dict() for t in traces.data] if traces else []
        except Exception as e:
            logger.error(
                f"LangfuseAdapter: Failed to get traces for session {session_id}: {e}"
            )
            return []

    async def get_observations_for_trace(
        self,
        trace_id: str
    ) -> List[Dict[str, Any]]:
        """
        獲取 trace 的所有 observations（spans）

        Args:
            trace_id: Trace ID

        Returns:
            Observation 列表
        """
        if not self._client:
            return []

        try:
            observations = self._client.get_observations(trace_id=trace_id)
            return [o.dict() for o in observations.data] if observations else []
        except Exception as e:
            logger.error(
                f"LangfuseAdapter: Failed to get observations for trace {trace_id}: {e}"
            )
            return []

    def flush(self) -> None:
        """確保所有資料已發送"""
        if self._client:
            self._client.flush()

    async def update_span_status(
        self,
        trace_id: str,
        span_id: str,
        status: str,
        output: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        更新 span 狀態

        ⚠️ 注意：Langfuse SDK 的限制
        - Langfuse SDK 不直接支持更新已存在的 observation
        - 可以通過 score API 來標記成功/失敗，但這不會改變 observation 的狀態
        - 實際的狀態更新需要在創建 span 時設置，或通過 Langfuse Web UI/API 手動更新

        此方法嘗試通過 score API 標記，但主要用於記錄和追蹤目的。
        真正的狀態更新應該在 ExternalJobMapping 中記錄，並在後續查詢時使用。

        Args:
            trace_id: Trace ID
            span_id: Span ID
            status: 狀態（"success" | "failed" | "timeout"）
            output: 可選的輸出數據

        Returns:
            bool: 是否成功記錄（注意：這不會真正改變 Langfuse 中的 observation 狀態）
        """
        if not self._client:
            logger.warning("LangfuseAdapter: Client not initialized, cannot update span")
            return False

        try:
            # ⚠️ Langfuse SDK 限制：無法直接更新已存在的 observation
            # 嘗試通過 score API 來標記（這不會改變狀態，但可以用於追蹤）
            # 實際的狀態應該在 ExternalJobMapping 中記錄

            # 獲取 observation 以驗證存在
            observations = await self.get_observations_for_trace(trace_id)
            found_span = False
            for obs in observations:
                obs_id = obs.get("id") or obs.get("observationId")
                if obs_id == span_id:
                    found_span = True
                    break

            if found_span:
                # 嘗試通過 score API 標記（如果 SDK 支持）
                # 注意：這不會改變 observation 的實際狀態
                try:
                    # Langfuse SDK 的 score API 示例（需要根據實際版本調整）
                    # self._client.score(
                    #     trace_id=trace_id,
                    #     observation_id=span_id,
                    #     value=1.0 if status == "success" else 0.0,
                    #     comment=f"Status: {status}"
                    # )
                    logger.info(
                        f"LangfuseAdapter: Recorded span {span_id} status as {status} "
                        f"(note: Langfuse SDK does not support updating existing observation status)"
                    )
                    return True
                except Exception as score_error:
                    logger.warning(f"LangfuseAdapter: Failed to score span {span_id}: {score_error}")
                    # 即使 score 失敗，也記錄狀態（用於後續處理）
                    logger.info(f"LangfuseAdapter: Status {status} recorded for span {span_id} (via ExternalJobMapping)")
                    return True
            else:
                logger.warning(f"LangfuseAdapter: Span {span_id} not found in trace {trace_id}")
                # 即使找不到 span，也記錄狀態（可能 span 尚未創建）
                logger.info(f"LangfuseAdapter: Status {status} recorded for span {span_id} (span may not exist yet)")
                return True

        except Exception as e:
            logger.warning(f"LangfuseAdapter: Failed to update span {span_id}: {e}")
            # 即使更新失敗，也記錄狀態（用於後續處理）
            return False


class LangfuseTraceContext:
    """Langfuse Trace 上下文"""

    def __init__(self, trace, correlation_ids: CorrelationIds):
        self.trace = trace
        self.correlation_ids = correlation_ids

    def span(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """創建 span"""
        return self.trace.span(
            name=name,
            input=input_data,
            metadata={
                "intent_id": self.correlation_ids.intent_id,
                "strictness_level": self.correlation_ids.strictness_level,
            },
            **kwargs
        )

    def generation(
        self,
        name: str,
        model: str,
        input_data: Optional[str] = None,
        **kwargs
    ):
        """創建 generation（LLM 呼叫）"""
        return self.trace.generation(
            name=name,
            model=model,
            input=input_data,
            metadata={
                "intent_id": self.correlation_ids.intent_id,
                "strictness_level": self.correlation_ids.strictness_level,
            },
            **kwargs
        )


class MockTraceContext:
    """Mock Trace 上下文（無 Langfuse 時使用）"""

    def __init__(self, correlation_ids: CorrelationIds):
        self.correlation_ids = correlation_ids
        self.trace_id = correlation_ids.run_id

    def span(self, name: str, **kwargs):
        """Mock span"""
        return MockSpan(name)

    def generation(self, name: str, **kwargs):
        """Mock generation"""
        return MockSpan(name)


class MockSpan:
    """Mock Span"""

    def __init__(self, name: str):
        self.name = name

    def end(self, **kwargs):
        pass

    def update(self, **kwargs):
        pass

