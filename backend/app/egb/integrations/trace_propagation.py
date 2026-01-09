"""
Trace Propagation Middleware

Trace 傳播中間件，確保關聯 ID 在整個執行過程中傳播。

⚠️ P0-3 硬規則：EGBTracePropagation 是唯一負責寫入 trace/span metadata 的元件
⚠️ P0-F 硬規則：使用 @asynccontextmanager 支援 async 環境
"""

import logging
from typing import Optional, Callable, Any
from contextvars import ContextVar
from functools import wraps
from contextlib import asynccontextmanager

from backend.app.egb.schemas.correlation_ids import CorrelationIds
from backend.app.egb.integrations.external_boundary import get_external_boundary  # ⚠️ P0-7 新增

logger = logging.getLogger(__name__)

# Context variables for storing current trace and correlation IDs
_current_trace: ContextVar[Optional[Any]] = ContextVar("egb_current_trace", default=None)
_current_correlation_ids: ContextVar[Optional[CorrelationIds]] = ContextVar(
    "egb_correlation_ids", default=None
)


def get_current_correlation_ids() -> Optional[CorrelationIds]:
    """獲取當前上下文中的關聯 ID"""
    return _current_correlation_ids.get()


def set_current_correlation_ids(correlation_ids: CorrelationIds) -> None:
    """設置當前上下文中的關聯 ID"""
    _current_correlation_ids.set(correlation_ids)


class EGBTracePropagation:
    """
    EGB Trace 傳播中間件

    職責：
    1. 建立 Langfuse trace（使用 run_id 作為 trace.id）
    2. 傳播 correlation_ids 到所有子 span 的 metadata
    3. 管理 trace 生命週期

    ⚠️ P0-3 硬規則：這是唯一寫入 span metadata 的地方
    ⚠️ P0-F 硬規則：使用 @asynccontextmanager 支援 async 環境
    """

    def __init__(self, langfuse_adapter=None):
        """
        初始化 EGBTracePropagation

        Args:
            langfuse_adapter: LangfuseAdapter 實例（可選）
        """
        self.langfuse_adapter = langfuse_adapter

    @asynccontextmanager
    async def trace_context(
        self,
        correlation_ids: CorrelationIds
    ):
        """
        建立 trace 上下文，自動傳播 ID 到所有子 span

        ⚠️ P0-F：使用 async context manager，確保在 async 環境下正確運作
        ⚠️ 工程硬規範：任何開 span 的地方都必須在同一 task context
        ⚠️ P0-1 硬規則：run_id == trace_id（run_id 直接作為 Langfuse trace.id）

        Args:
            correlation_ids: CorrelationIds（必須包含 run_id）

        Yields:
            trace: Langfuse trace 對象
        """
        if not self.langfuse_adapter:
            # Fallback: 無 Langfuse 時使用 mock
            logger.warning("EGBTracePropagation: No langfuse_adapter, using mock trace")
            token_correlation = _current_correlation_ids.set(correlation_ids)
            try:
                yield None
            finally:
                _current_correlation_ids.reset(token_correlation)
            return

        # ⚠️ P0-1：使用 run_id 作為 trace.id
        # ⚠️ P0-F：注意：langfuse_adapter.trace_context 是同步的，但我們在 async context 中使用
        # 這在單線程 async 環境下是安全的，但並行 task 需要確保在同一 task context

        # 使用同步 contextmanager（langfuse_adapter 是同步的）
        # 在 async context 中使用同步 contextmanager 是安全的（Python 3.7+）
        from contextlib import contextmanager

        with self.langfuse_adapter.trace_context(correlation_ids) as trace_ctx:
            trace = trace_ctx.trace if hasattr(trace_ctx, 'trace') else None

            # ⚠️ P0-F：使用 ContextVar 但確保在 async task 內正確傳播
            # ⚠️ 工程硬規範：所有會 create_span 的並行工作必須用同一套可傳遞 context 的 task 建立方式
            # 或明確禁止在 MVP 做跨 task span 建立，只記錄一層 tool_path summary
            token_trace = _current_trace.set(trace)
            token_correlation = _current_correlation_ids.set(correlation_ids)

            try:
                yield trace
            finally:
                if trace and hasattr(trace, 'end'):
                    trace.end()
                _current_trace.reset(token_trace)
                _current_correlation_ids.reset(token_correlation)

    async def create_span(
        self,
        name: str,
        **kwargs
    ):
        """
        建立子 span，自動繼承 correlation_ids

        ⚠️ P0-F：必須在 trace_context 的 async context 內呼叫
        """
        trace = _current_trace.get()
        correlation_ids = _current_correlation_ids.get()

        if not trace or not correlation_ids:
            raise RuntimeError("Must be within trace_context")

        if hasattr(trace, 'span'):
            return trace.span(
                name=name,
                metadata={
                    "intent_id": correlation_ids.intent_id,
                    "strictness_level": correlation_ids.strictness_level,
                    **kwargs.get("metadata", {}),
                },
                **{k: v for k, v in kwargs.items() if k != "metadata"}
            )
        else:
            # Fallback for mock trace
            logger.debug(f"EGBTracePropagation: Creating span {name} (mock)")
            return None

    def inject_outbound_headers(
        self,
        correlation_ids: CorrelationIds,
        span_id: Optional[str] = None
    ) -> Dict[str, str]:
        """
        注入出站 headers（P0-7 新增）

        ⚠️ P0-7 硬規則：所有 HTTP client / webhook / workflow 工具觸發時必須調用

        Args:
            correlation_ids: CorrelationIds
            span_id: 可選的 span_id

        Returns:
            Headers 字典
        """
        boundary = get_external_boundary()
        return boundary.inject_outbound_headers(correlation_ids, span_id)


class TracePropagationMiddleware:
    """
    Trace 傳播中間件

    確保在 Playbook 執行過程中，關聯 ID 被正確傳播到：
    1. 所有 LLM 呼叫
    2. 所有工具執行
    3. 所有政策檢查
    """

    def __init__(self, langfuse_adapter=None):
        """
        初始化中間件

        Args:
            langfuse_adapter: Langfuse 適配器（可選）
        """
        self.langfuse_adapter = langfuse_adapter

    def propagate(self, correlation_ids: CorrelationIds):
        """
        裝飾器：傳播關聯 ID 到函數執行上下文

        使用方式：
            @middleware.propagate(correlation_ids)
            async def execute_playbook(...):
                ...
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # 設置關聯 ID
                token = _current_correlation_ids.set(correlation_ids)
                try:
                    # 如果有 Langfuse，創建 trace 上下文
                    if self.langfuse_adapter:
                        with self.langfuse_adapter.trace_context(correlation_ids):
                            return await func(*args, **kwargs)
                    else:
                        return await func(*args, **kwargs)
                finally:
                    # 恢復之前的值
                    _current_correlation_ids.reset(token)

            return wrapper
        return decorator

    def inject_ids(self, metadata: dict) -> dict:
        """
        將當前關聯 ID 注入到 metadata

        使用方式：
            metadata = middleware.inject_ids(metadata)
        """
        correlation_ids = get_current_correlation_ids()
        if correlation_ids:
            metadata.update(correlation_ids.to_langfuse_metadata())
        return metadata

    def get_tags(self) -> list:
        """獲取當前關聯 ID 的 tags"""
        correlation_ids = get_current_correlation_ids()
        if correlation_ids:
            return correlation_ids.to_langfuse_tags()
        return []


def with_egb_context(correlation_ids: CorrelationIds):
    """
    裝飾器：為函數添加 EGB 上下文

    使用方式：
        @with_egb_context(correlation_ids)
        async def my_function():
            # 可以使用 get_current_correlation_ids() 獲取關聯 ID
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            token = _current_correlation_ids.set(correlation_ids)
            try:
                return await func(*args, **kwargs)
            finally:
                _current_correlation_ids.reset(token)
        return wrapper
    return decorator


def egb_span(name: str):
    """
    裝飾器：為函數創建 EGB span

    使用方式：
        @egb_span("my_operation")
        async def my_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            correlation_ids = get_current_correlation_ids()

            if correlation_ids:
                logger.debug(
                    f"EGB Span: {name} (run_id={correlation_ids.run_id[:8]}...)"
                )

            # 這裡可以添加實際的 span 記錄邏輯
            return await func(*args, **kwargs)
        return wrapper
    return decorator

