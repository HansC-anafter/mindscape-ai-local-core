"""
Runtime services - Runtime implementations and factory
"""

_AGENT_EXECUTOR_EXPORTS = {
    "LangChainAgentExecutor",
    "MindscapeAgentExecutor",
    "AgentResult",
    "AgentStep",
    "AgentStatus",
    "create_agent_executor",
    "LANGCHAIN_AGENTS_AVAILABLE",
}
_RUNTIME_FACTORY_EXPORTS = {"RuntimeFactory"}
_SIMPLE_RUNTIME_EXPORTS = {"SimpleRuntime"}


def __getattr__(name: str):
    if name in _RUNTIME_FACTORY_EXPORTS:
        from backend.app.services.runtime.runtime_factory import RuntimeFactory

        return RuntimeFactory
    if name in _SIMPLE_RUNTIME_EXPORTS:
        from backend.app.services.runtime.simple_runtime import SimpleRuntime

        return SimpleRuntime
    if name in _AGENT_EXECUTOR_EXPORTS:
        from backend.app.services.runtime import agent_executor

        return getattr(agent_executor, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "RuntimeFactory",
    "SimpleRuntime",
    "LangChainAgentExecutor",
    "MindscapeAgentExecutor",
    "AgentResult",
    "AgentStep",
    "AgentStatus",
    "create_agent_executor",
    "LANGCHAIN_AGENTS_AVAILABLE",
]
