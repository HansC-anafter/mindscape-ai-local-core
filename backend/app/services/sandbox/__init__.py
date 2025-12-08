"""
Sandbox system for AI write operations

Provides unified abstraction for all AI write operations with version management,
storage abstraction, and type-specific implementations.
"""

from backend.app.services.sandbox.sandbox_manager import SandboxManager
from backend.app.services.sandbox.base_sandbox import BaseSandbox

__all__ = [
    "SandboxManager",
    "BaseSandbox",
]

