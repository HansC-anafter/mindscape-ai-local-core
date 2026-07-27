"""
Capability Registry
Loads and manages all capability pack manifests, provides tool lookup functionality
"""

import inspect
import yaml
import sys
from pathlib import Path
from typing import Dict, Optional, Callable, Any, List
import logging
import threading
from app.services.runtime_pack_hygiene import is_ignored_runtime_pack_dir
from app.services.capability_backend_loader import (
    resolve_capability_backend_callable,
)
from app.services.capability_tool_invocation import (
    invoke_capability_tool,
    invoke_capability_tool_async,
)

logger = logging.getLogger(__name__)

# The backend is importable through both roots during the compatibility period.
# Keep one module object so both import forms share the same registries and lock.
_CURRENT_MODULE = sys.modules[__name__]
sys.modules.setdefault("app.services.capability_registry", _CURRENT_MODULE)
sys.modules.setdefault("backend.app.services.capability_registry", _CURRENT_MODULE)

# Global capability registry
CAPABILITY_REGISTRY: Dict[str, Dict] = {}
TOOL_REGISTRY: Dict[str, Dict] = {}  # tool_name -> {capability, tool_info, backend}
_REGISTRY_LOCK = threading.RLock()


class CapabilityRegistry:
    """Capability pack registry"""

    def __init__(self):
        self.capabilities: Dict[str, Dict] = {}
        self.tools: Dict[str, Dict] = {}

    def load_from_directory(self, capabilities_dir: Path):
        """Scan capabilities directory on startup, load all manifest.yaml files"""
        if not capabilities_dir.exists():
            logger.warning(f"Capabilities directory not found: {capabilities_dir}")
            return

        for capability_dir in capabilities_dir.iterdir():
            if (
                not capability_dir.is_dir()
                or is_ignored_runtime_pack_dir(capability_dir.name)
            ):
                continue

            self.load_capability_from_directory(capability_dir)

    def load_capability_from_directory(
        self,
        capability_dir: Path,
        *,
        expected_code: Optional[str] = None,
    ) -> Optional[str]:
        """Load one manifest and replace only that capability's registry entries."""

        manifest_path = capability_dir / "manifest.yaml"
        if not manifest_path.exists():
            logger.debug(f"No manifest.yaml found in {capability_dir}, skipping")
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                manifest = yaml.safe_load(manifest_file)
            if not isinstance(manifest, dict):
                raise ValueError("manifest_root_must_be_mapping")
            capability_code = str(manifest.get("code") or "").strip()
            if not capability_code:
                raise ValueError("manifest_capability_code_missing")
            if expected_code and capability_code != expected_code:
                raise ValueError(
                    f"manifest_capability_code_mismatch:{capability_code}:{expected_code}"
                )

            stale_tools = [
                tool_name
                for tool_name, tool_info in self.tools.items()
                if tool_info.get("capability") == capability_code
            ]
            for tool_name in stale_tools:
                self.tools.pop(tool_name, None)
            self.capabilities[capability_code] = {
                "manifest": manifest,
                "directory": capability_dir,
            }
            from backend.app.services.task_projection_adapters import register_manifest
            from backend.app.services.knowledge_projection.retrievable.adapter_registry import (
                register_manifest as register_knowledge_projection_manifest,
            )

            register_manifest(capability_code, manifest, capability_dir)
            register_knowledge_projection_manifest(
                capability_code,
                manifest,
                capability_dir,
            )
            for tool in manifest.get("tools", []):
                if not isinstance(tool, dict):
                    continue
                tool_name = str(tool.get("name") or "").strip()
                if not tool_name:
                    continue
                self.tools[f"{capability_code}.{tool_name}"] = {
                    "capability": capability_code,
                    "tool_name": tool_name,
                    "tool_info": tool,
                    "backend": tool.get("backend"),
                }

            logger.info(
                "Loaded capability: %s (%d tools)",
                capability_code,
                len(manifest.get("tools", [])),
            )
            return capability_code
        except Exception as exc:
            logger.error(
                "Failed to load manifest from %s: %s",
                capability_dir,
                exc,
                exc_info=True,
            )
            return None

    def get_tool(self, tool_name: str) -> Optional[Dict]:
        """Get tool definition by tool name"""
        return self.tools.get(tool_name)

    def list_tools(self) -> list[str]:
        """List all available tool names"""
        return list(self.tools.keys())

    def list_capabilities(self) -> list[str]:
        """List all capability pack codes"""
        return list(self.capabilities.keys())

    def get_capability(self, capability_code: str) -> Optional[Dict]:
        """Get capability pack definition"""
        return self.capabilities.get(capability_code)

    def get_capability_playbooks(self, capability_code: str) -> List[str]:
        """
        Get list of playbooks defined by the capability pack

        Args:
            capability_code: Capability pack code

        Returns:
            List of playbook file names (without path)
        """
        capability = self.capabilities.get(capability_code)
        if not capability:
            return []

        manifest = capability.get('manifest', {})
        playbooks = manifest.get('playbooks', [])
        return playbooks if isinstance(playbooks, list) else []

    def has_pack_executor(self, capability_code: str) -> bool:
        """
        Check if capability pack has pack_executor service

        Args:
            capability_code: Capability pack code

        Returns:
            True if pack_executor exists, False otherwise
        """
        capability = self.capabilities.get(capability_code)
        if not capability:
            return False

        # Check if pack_executor.py file exists
        directory: Path = capability.get('directory')
        if directory:
            pack_executor_path = directory / "services" / "pack_executor.py"
            return pack_executor_path.exists()

        return False

    def get_execution_method(self, capability_code: str) -> str:
        """
        Get execution method for capability pack

        Returns:
            'pack_executor' - Has pack_executor service
            'playbook' - Has playbooks
            'unknown' - Unknown
        """
        if self.has_pack_executor(capability_code):
            return 'pack_executor'

        playbooks = self.get_capability_playbooks(capability_code)
        if playbooks:
            return 'playbook'

        return 'unknown'


# Global instance
_registry = CapabilityRegistry()


def load_capabilities(capabilities_dir: Optional[Path] = None, reset: bool = False):
    """Load all capability packs (typically called on application startup)."""
    if capabilities_dir is None:
        # Default to loading from app/capabilities directory
        app_dir = Path(__file__).parent.parent
        capabilities_dir = app_dir / "capabilities"

    caller = inspect.stack(context=0)[1]
    logger.info(
        "Loading all capability manifests: reset=%s caller=%s:%s",
        reset,
        Path(caller.filename).name,
        caller.lineno,
    )
    with _REGISTRY_LOCK:
        if reset:
            from backend.app.services.knowledge_projection.retrievable.adapter_registry import (
                reset_registry_for_tests as reset_knowledge_projection_registry,
            )

            _registry.capabilities.clear()
            _registry.tools.clear()
            CAPABILITY_REGISTRY.clear()
            TOOL_REGISTRY.clear()
            reset_knowledge_projection_registry()

        _registry.load_from_directory(capabilities_dir)
        CAPABILITY_REGISTRY.update(_registry.capabilities)
        TOOL_REGISTRY.update(_registry.tools)
    logger.info(f"Loaded {len(_registry.capabilities)} capabilities, {len(_registry.tools)} tools")


def reload_capability(
    capability_code: str,
    capabilities_dir: Optional[Path] = None,
) -> bool:
    """Replace one capability manifest/tool slice without rebuilding all packs."""

    normalized_code = str(capability_code or "").strip()
    if not normalized_code:
        raise ValueError("capability_code_required")
    if capabilities_dir is None:
        capabilities_dir = Path(__file__).parent.parent / "capabilities"
    capability_dir = capabilities_dir / normalized_code
    with _REGISTRY_LOCK:
        loaded_code = _registry.load_capability_from_directory(
            capability_dir,
            expected_code=normalized_code,
        )
        if loaded_code is None:
            return False
        CAPABILITY_REGISTRY[normalized_code] = _registry.capabilities[normalized_code]
        stale_global_tools = [
            tool_name
            for tool_name, tool_info in TOOL_REGISTRY.items()
            if tool_info.get("capability") == normalized_code
        ]
        for tool_name in stale_global_tools:
            TOOL_REGISTRY.pop(tool_name, None)
        TOOL_REGISTRY.update(
            {
                tool_name: tool_info
                for tool_name, tool_info in _registry.tools.items()
                if tool_info.get("capability") == normalized_code
            }
        )
    return True


def get_tool_backend(capability: str, tool: str) -> Optional[str]:
    """Get tool backend path (e.g., 'app.services.xxx:func')"""
    tool_name = f"{capability}.{tool}"
    tool_info = _registry.get_tool(tool_name)
    if tool_info:
        return tool_info.get('backend')
    return None


def call_tool(capability: str, tool: str, **kwargs) -> Any:
    """
    Call capability pack tool

    Args:
        capability: Capability pack code (e.g., 'habit_learning')
        tool: Tool name (e.g., 'observe_event')
        **kwargs: Parameters passed to the tool

    Returns:
        Tool execution result
    """
    tool_name = f"{capability}.{tool}"
    tool_info = _registry.get_tool(tool_name)

    if not tool_info:
        raise ValueError(f"Tool not found: {tool_name}")

    backend_path = tool_info.get('backend')
    if not backend_path:
        raise ValueError(f"Tool {tool_name} has no backend defined")

    capability_info = _registry.get_capability(capability)
    capability_dir = capability_info.get("directory") if capability_info else None

    try:
        func = resolve_capability_backend_callable(
            backend_path=backend_path,
            capability_dir=Path(capability_dir) if capability_dir else None,
        )

        return invoke_capability_tool(func, kwargs)
    except Exception as e:
        error_msg = f"Failed to call tool {tool_name} (backend: {backend_path}): {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


async def call_tool_async(capability: str, tool: str, **kwargs) -> Any:
    """
    Asynchronously call capability pack tool
    """
    tool_name = f"{capability}.{tool}"
    tool_info = _registry.get_tool(tool_name)

    if not tool_info:
        raise ValueError(f"Tool not found: {tool_name}")

    backend_path = tool_info.get('backend')
    if not backend_path:
        raise ValueError(f"Tool {tool_name} has no backend defined")

    capability_info = _registry.get_capability(capability)
    capability_dir = capability_info.get("directory") if capability_info else None

    try:
        func = resolve_capability_backend_callable(
            backend_path=backend_path,
            capability_dir=Path(capability_dir) if capability_dir else None,
        )
        return await invoke_capability_tool_async(func, kwargs)
    except Exception as e:
        # Avoid recursion in error logging - use simple error message
        error_msg = f"Failed to call tool {tool_name} (backend: {backend_path}): {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def get_registry() -> CapabilityRegistry:
    """Get global registry instance"""
    return _registry
