"""
Sandbox type implementations

Provides concrete implementations for different sandbox types.
"""

from typing import Type, Dict, List
from backend.app.services.sandbox.base_sandbox import BaseSandbox

_sandbox_registry: Dict[str, Type[BaseSandbox]] = {}


def register_sandbox_type(sandbox_type: str, sandbox_class: Type[BaseSandbox]):
    """
    Register a sandbox type implementation

    Args:
        sandbox_type: Type identifier (e.g., "threejs_hero")
        sandbox_class: Sandbox class implementation
    """
    _sandbox_registry[sandbox_type] = sandbox_class


def get_sandbox_class(sandbox_type: str) -> Type[BaseSandbox]:
    """
    Get sandbox class for type

    Args:
        sandbox_type: Type identifier

    Returns:
        Sandbox class

    Raises:
        ValueError: If sandbox type not registered
    """
    if sandbox_type not in _sandbox_registry:
        raise ValueError(f"Unknown sandbox type: {sandbox_type}")
    return _sandbox_registry[sandbox_type]


def get_available_types() -> List[str]:
    """
    Get list of available sandbox types

    Returns:
        List of sandbox type identifiers
    """
    return list(_sandbox_registry.keys())


from backend.app.services.sandbox.types.web_page_sandbox import WebPageSandbox
from backend.app.services.sandbox.types.threejs_hero_sandbox import ThreeJSHeroSandbox
from backend.app.services.sandbox.types.writing_project_sandbox import WritingProjectSandbox
from backend.app.services.sandbox.types.project_repo_sandbox import ProjectRepoSandbox

register_sandbox_type("web_page", WebPageSandbox)
register_sandbox_type("threejs_hero", ThreeJSHeroSandbox)
register_sandbox_type("writing_project", WritingProjectSandbox)
register_sandbox_type("project_repo", ProjectRepoSandbox)

__all__ = [
    "register_sandbox_type",
    "get_sandbox_class",
    "get_available_types",
    "WebPageSandbox",
    "ThreeJSHeroSandbox",
    "WritingProjectSandbox",
    "ProjectRepoSandbox",
]

