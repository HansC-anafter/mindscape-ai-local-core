"""
Execution Context Shim for Local-Core

Provides local alternative for Cloud environment contracts.execution_context.
Features are degraded but API remains compatible.

Usage:
    # In capability code
    try:
        from contracts.execution_context import ExecutionContext
    except ImportError:
        from mindscape.shims.execution_context import ExecutionContext

    # Or use unified entry point (recommended)
    from mindscape.shims.execution_context import get_execution_context
    ctx = get_execution_context()
"""

from typing import Optional, Dict, Any, Generator
from dataclasses import dataclass, field
from contextlib import contextmanager
import uuid
import logging
import threading
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

logger = logging.getLogger(__name__)

# Thread-local storage for current execution context
_context_local = threading.local()


@dataclass
class ExecutionContext:
    """
    Local-Core compatible ExecutionContext

    API compatible with Cloud version, but the following features are unavailable:
    - Distributed tracing (distributed_tracing)
    - Tenant isolation (tenant_isolation)
    - Cloud Task scheduling (cloud_task_scheduling)
    - Multi-tenant database routing (multi_tenant_db_routing)

    In Local-Core:
    - tenant_id is fixed to "local-default-tenant"
    - All operations execute synchronously
    - Uses local SQLite database
    """

    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = "local-default-tenant"
    actor_id: Optional[str] = None
    subject_user_id: Optional[str] = None
    trace_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid4()))
    span_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid4())[:16])
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Degradation flag
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
        """Check if running in Cloud environment"""
        return False

    def is_degraded(self) -> bool:
        """Check if running in degraded mode"""
        return self._is_degraded

    def get_unavailable_features(self) -> list:
        """Get list of unavailable features"""
        return self._unavailable_features.copy()

    def get_tenant_db_session(self):
        """
        Get tenant database session

        Local-Core uses local SQLite, no multi-tenant routing needed.
        Returns default local database session.
        """
        try:
            from backend.app.database import get_local_session
            return get_local_session()
        except ImportError:
            # Try alternative import paths
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
        Dispatch Cloud Task

        Degraded to synchronous execution in Local-Core.

        Args:
            task_name: Task name
            payload: Task parameters
            queue: Queue name (ignored in local-core)
            delay_seconds: Delay in seconds (ignored in local-core)

        Returns:
            task_id: Task ID (result ID for synchronous execution in local-core)
        """
        task_id = str(uuid.uuid4())

        logger.warning(
            f"Cloud Task '{task_name}' dispatched in Local-Core mode. "
            f"Executing synchronously instead of async. "
            f"task_id={task_id}, queue={queue}, delay={delay_seconds}s"
        )

        # Synchronous execution fallback for Local-Core
        try:
            try:
                from app.capabilities.registry import call_tool
            except ImportError:
                from backend.app.capabilities.registry import call_tool

            # Parse task_name as capability.tool format
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
        Start a tracing span

        Returns a no-op span context in Local-Core.
        """
        return SpanContext(name=name, parent_context=self)

    def log_event(self, event_type: str, data: Dict[str, Any] = None):
        """
        Log event

        Logs to local log in Local-Core.
        """
        logger.info(
            f"[ExecutionContext Event] type={event_type}, "
            f"execution_id={self.execution_id}, "
            f"data={data}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
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
    Tracing Span Context

    No-op implementation in Local-Core.
    """
    name: str
    parent_context: ExecutionContext
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    start_time: datetime = field(default_factory=datetime.utcnow)

    def __enter__(self) -> "SpanContext":
        logger.debug(f"[Span Start] {self.name}, span_id={self.span_id}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (_utc_now() - self.start_time).total_seconds()
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
        """Set span attribute (no-op in local-core)"""
        pass

    def add_event(self, name: str, attributes: Dict[str, Any] = None):
        """Add span event (logs to local log in local-core)"""
        logger.debug(f"[Span Event] {name}, attributes={attributes}")


def get_execution_context(**kwargs) -> ExecutionContext:
    """
    Factory function to create ExecutionContext

    Compatible factory function with Cloud version.

    Args:
        **kwargs: Parameters passed to ExecutionContext

    Returns:
        ExecutionContext instance
    """
    return ExecutionContext(**kwargs)


def get_current_context() -> Optional[ExecutionContext]:
    """
    Get current thread's execution context

    Returns:
        Current ExecutionContext or None
    """
    return getattr(_context_local, 'context', None)


def set_current_context(context: ExecutionContext):
    """
    Set current thread's execution context

    Args:
        context: ExecutionContext instance
    """
    _context_local.context = context


@contextmanager
def execution_context_scope(**kwargs) -> Generator[ExecutionContext, None, None]:
    """
    Context manager: create and set execution context

    Usage:
        with execution_context_scope(actor_id="user-123") as ctx:
            # ctx is now the current context
            do_something()
    """
    previous = get_current_context()
    context = get_execution_context(**kwargs)
    set_current_context(context)
    try:
        yield context
    finally:
        set_current_context(previous)


# Exports
__all__ = [
    "ExecutionContext",
    "SpanContext",
    "get_execution_context",
    "get_current_context",
    "set_current_context",
    "execution_context_scope",
]



