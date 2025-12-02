"""
Tool adapters for integrating external tool ecosystems.

This package provides adapters for:
- LangChain tools (Phase 1)
- MCP (Model Context Protocol) tools (Phase 2)
"""

# LangChain adapter
try:
    from backend.app.services.tools.langchain_adapter import (
        LangChainToolAdapter,
        MindscapeToLangChainAdapter,
        from_langchain,
        to_langchain,
        is_langchain_available,
        get_langchain_version,
    )

    LANGCHAIN_AVAILABLE = True

except ImportError:
    # LangChain not installed - graceful degradation
    LANGCHAIN_AVAILABLE = False
    LangChainToolAdapter = None
    MindscapeToLangChainAdapter = None
    from_langchain = None
    to_langchain = None
    is_langchain_available = lambda: False
    get_langchain_version = lambda: None


# MCP adapter
try:
    from backend.app.services.tools.mcp_client import (
        MCPClient,
        MCPServerConfig,
        MCPTransportType,
        JSONRPCError,
    )
    from backend.app.services.tools.mcp_adapter import (
        MCPToolAdapter,
        discover_mcp_tools,
        is_mcp_available,
    )
    from backend.app.services.tools.mcp_manager import (
        MCPServerManager,
    )

    MCP_AVAILABLE = True

except ImportError:
    # MCP dependencies not installed - graceful degradation
    MCP_AVAILABLE = False
    MCPClient = None
    MCPServerConfig = None
    MCPTransportType = None
    JSONRPCError = None
    MCPToolAdapter = None
    discover_mcp_tools = None
    is_mcp_available = lambda: False
    MCPServerManager = None


__all__ = [
    # LangChain
    "LangChainToolAdapter",
    "MindscapeToLangChainAdapter",
    "from_langchain",
    "to_langchain",
    "is_langchain_available",
    "get_langchain_version",
    "LANGCHAIN_AVAILABLE",
    # MCP
    "MCPClient",
    "MCPServerConfig",
    "MCPTransportType",
    "JSONRPCError",
    "MCPToolAdapter",
    "discover_mcp_tools",
    "is_mcp_available",
    "MCPServerManager",
    "MCP_AVAILABLE",
]



