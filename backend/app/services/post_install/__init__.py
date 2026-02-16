"""
Post Install Bootstrap System

Uses strategy pattern to handle bootstrap operations, avoiding hardcoded business logic.
"""

from .bootstrap_registry import BootstrapRegistry
from .bootstrap_strategies import (
    BootstrapStrategy,
    PythonScriptStrategy,
    ContentVaultInitStrategy,
    CloudProviderRuntimeInitStrategy,
    ConditionalBootstrapStrategy,
)

# Import PostInstallHandler from parent module (post_install.py file)
# This is needed because PostInstallHandler is in post_install.py, not in this directory
import sys
from pathlib import Path

parent_dir = Path(__file__).parent.parent
post_install_py = parent_dir / "post_install.py"
if post_install_py.exists():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "app.services.post_install_module", post_install_py
    )
    if spec and spec.loader:
        post_install_module = importlib.util.module_from_spec(spec)
        sys.modules["app.services.post_install_module"] = post_install_module
        spec.loader.exec_module(post_install_module)
        PostInstallHandler = getattr(post_install_module, "PostInstallHandler", None)

__all__ = [
    "BootstrapRegistry",
    "BootstrapStrategy",
    "PythonScriptStrategy",
    "ContentVaultInitStrategy",
    "CloudProviderRuntimeInitStrategy",
    "ConditionalBootstrapStrategy",
]

if "PostInstallHandler" in locals() and PostInstallHandler:
    __all__.append("PostInstallHandler")
