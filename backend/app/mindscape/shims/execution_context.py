"""
Execution Context Shim for Local-Core

提供 Cloud 環境 contracts.execution_context 的本地替代品。
功能降級但保持 API 兼容。

使用方式：
    # 在 capability 代碼中
    try:
        from contracts.execution_context import ExecutionContext
    except ImportError:
        from mindscape.shims.execution_context import ExecutionContext

    # 或使用統一入口（推薦）
    from mindscape.shims.execution_context import get_execution_context
    ctx = get_execution_context()
"""

from typing import Optional, Dict, Any, Generator
from dataclasses import dataclass, field
from contextlib import contextmanager
import uuid
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

# 線程本地存儲，用於存儲當前執行上下文
_context_local = threading.local()


@dataclass
class ExecutionContext:
    """
    Local-Core compatible ExecutionContext

    與 Cloud 版本 API 兼容，但以下功能不可用：
    - 分佈式追蹤 (distributed_tracing)
    - 租戶隔離 (tenant_isolation)
    - Cloud Task 調度 (cloud_task_scheduling)
    - 多租戶數據庫路由 (multi_tenant_db_routing)

    在 Local-Core 中：
    - tenant_id 固定為 "local-default-tenant"
    - 所有操作同步執行
    - 使用本地 SQLite 數據庫
    """

    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = "local-default-tenant"
    actor_id: Optional[str] = None
    subject_user_id: Optional[str] = None
    trace_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid4()))
    span_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid4())[:16])
    created_at: datetime = field(default_factory=datetime.utcnow)

    # 額外元數據
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 降級標記
    _is_degraded: bool = field(default=True, repr=False)
    _unavailable_features: list = field(
        default_factory=lambda: [
            "distributed_tracing",
            "tenant_isolation",
            "cloud_task_scheduling",
            "multi_tenant_db_routing"
        ],
        repr=False
    )

    def is_cloud_environment(self) -> bool:
        """檢查是否在 Cloud 環境中運行"""
        return False

    def is_degraded(self) -> bool:
        """檢查是否在降級模式下運行"""
        return self._is_degraded

    def get_unavailable_features(self) -> list:
        """獲取不可用的功能列表"""
        return self._unavailable_features.copy()

    def get_tenant_db_session(self):
        """
        獲取租戶數據庫會話

        Local-Core 使用本地 SQLite，不需要多租戶路由。
        返回默認的本地數據庫會話。
        """
        try:
            from backend.app.database import get_local_session
            return get_local_session()
        except ImportError:
            # 嘗試其他可能的導入路徑
            try:
                from app.database import get_local_session
                return get_local_session()
            except ImportError:
                logger.warning(
                    "Could not import database session. "
                    "Returning None - database operations may fail."
                )
                return None

    def dispatch_cloud_task(
        self,
        task_name: str,
        payload: Dict[str, Any],
        queue: str = "default",
        delay_seconds: int = 0
    ) -> str:
        """
        派發 Cloud Task

        在 Local-Core 中降級為同步執行。

        Args:
            task_name: 任務名稱
            payload: 任務參數
            queue: 隊列名稱（在 local-core 中忽略）
            delay_seconds: 延遲秒數（在 local-core 中忽略）

        Returns:
            task_id: 任務 ID（在 local-core 中為同步執行的結果 ID）
        """
        task_id = str(uuid.uuid4())

        logger.warning(
            f"Cloud Task '{task_name}' dispatched in Local-Core mode. "
            f"Executing synchronously instead of async. "
            f"task_id={task_id}, queue={queue}, delay={delay_seconds}s"
        )

        # 同步執行替代
        try:
            from mindscape.capabilities.registry import call_tool

            # 解析 task_name 為 capability.tool 格式
            if '.' in task_name:
                capability, tool = task_name.split('.', 1)
                result = call_tool(capability, tool, **payload)
                logger.info(f"Sync task completed: {task_name}, result_type={type(result)}")
            else:
                logger.warning(
                    f"Task name '{task_name}' is not in 'capability.tool' format. "
                    "Cannot execute."
                )
        except Exception as e:
            logger.error(f"Failed to execute sync task {task_name}: {e}")

        return task_id

    def start_span(self, name: str) -> "SpanContext":
        """
        開始一個追蹤 span

        在 Local-Core 中返回一個空操作的 span context。
        """
        return SpanContext(name=name, parent_context=self)

    def log_event(self, event_type: str, data: Dict[str, Any] = None):
        """
        記錄事件

        在 Local-Core 中記錄到本地日誌。
        """
        logger.info(
            f"[ExecutionContext Event] type={event_type}, "
            f"execution_id={self.execution_id}, "
            f"data={data}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            "execution_id": self.execution_id,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "subject_user_id": self.subject_user_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "created_at": self.created_at.isoformat(),
            "is_degraded": self._is_degraded,
            "unavailable_features": self._unavailable_features,
            "metadata": self.metadata,
        }


@dataclass
class SpanContext:
    """
    追蹤 Span 上下文

    在 Local-Core 中為空操作實現。
    """
    name: str
    parent_context: ExecutionContext
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    start_time: datetime = field(default_factory=datetime.utcnow)

    def __enter__(self) -> "SpanContext":
        logger.debug(f"[Span Start] {self.name}, span_id={self.span_id}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.utcnow() - self.start_time).total_seconds()
        if exc_type:
            logger.debug(
                f"[Span End] {self.name}, span_id={self.span_id}, "
                f"duration={duration:.3f}s, error={exc_type.__name__}"
            )
        else:
            logger.debug(
                f"[Span End] {self.name}, span_id={self.span_id}, "
                f"duration={duration:.3f}s"
            )
        return False

    def set_attribute(self, key: str, value: Any):
        """設置 span 屬性（在 local-core 中為 no-op）"""
        pass

    def add_event(self, name: str, attributes: Dict[str, Any] = None):
        """添加 span 事件（在 local-core 中記錄到日誌）"""
        logger.debug(f"[Span Event] {name}, attributes={attributes}")


def get_execution_context(**kwargs) -> ExecutionContext:
    """
    Factory function to create ExecutionContext

    與 Cloud 版本兼容的工廠函數。

    Args:
        **kwargs: 傳遞給 ExecutionContext 的參數

    Returns:
        ExecutionContext 實例
    """
    return ExecutionContext(**kwargs)


def get_current_context() -> Optional[ExecutionContext]:
    """
    獲取當前線程的執行上下文

    Returns:
        當前 ExecutionContext 或 None
    """
    return getattr(_context_local, 'context', None)


def set_current_context(context: ExecutionContext):
    """
    設置當前線程的執行上下文

    Args:
        context: ExecutionContext 實例
    """
    _context_local.context = context


@contextmanager
def execution_context_scope(**kwargs) -> Generator[ExecutionContext, None, None]:
    """
    上下文管理器：創建並設置執行上下文

    Usage:
        with execution_context_scope(actor_id="user-123") as ctx:
            # ctx 現在是當前上下文
            do_something()
    """
    previous = get_current_context()
    context = get_execution_context(**kwargs)
    set_current_context(context)
    try:
        yield context
    finally:
        set_current_context(previous)


# 導出
__all__ = [
    "ExecutionContext",
    "SpanContext",
    "get_execution_context",
    "get_current_context",
    "set_current_context",
    "execution_context_scope",
]



