"""
Blueprint service for loading and managing workspace blueprints

Blueprints are workspace templates that include:
- Workspace configuration
- Recommended playbooks
- Initial artifacts
- Capability configurations
"""

from .blueprint_loader import BlueprintLoader, BlueprintInfo, BlueprintLoadResult

__all__ = [
    "BlueprintLoader",
    "BlueprintInfo",
    "BlueprintLoadResult",
]
