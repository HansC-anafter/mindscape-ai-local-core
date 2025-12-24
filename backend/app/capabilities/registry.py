"""
Capability Registry
Loads and manages all capability pack manifests, provides tool lookup functionality
"""

import yaml
import importlib
import inspect
from pathlib import Path
from typing import Dict, Optional, Callable, Any, List
import logging

logger = logging.getLogger(__name__)

# Global capability registry
CAPABILITY_REGISTRY: Dict[str, Dict] = {}
TOOL_REGISTRY: Dict[str, Dict] = {}  # tool_name -> {capability, tool_info, backend}


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
            if not capability_dir.is_dir() or capability_dir.name.startswith('_'):
                continue

            manifest_path = capability_dir / "manifest.yaml"
            if not manifest_path.exists():
                logger.debug(f"No manifest.yaml found in {capability_dir}, skipping")
                continue

            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = yaml.safe_load(f)

                capability_code = manifest.get('code')
                if not capability_code:
                    logger.warning(f"Manifest in {capability_dir} missing 'code', skipping")
                    continue

                self.capabilities[capability_code] = {
                    'manifest': manifest,
                    'directory': capability_dir,
                }

                # Register all tools (prefix: capability_code.tool_name)
                for tool in manifest.get('tools', []):
                    tool_name = tool.get('name')
                    if not tool_name:
                        continue

                    full_tool_name = f"{capability_code}.{tool_name}"
                    self.tools[full_tool_name] = {
                        'capability': capability_code,
                        'tool_name': tool_name,
                        'tool_info': tool,
                        'backend': tool.get('backend'),
                    }

                logger.info(f"Loaded capability: {capability_code} ({len(manifest.get('tools', []))} tools)")

            except Exception as e:
                logger.error(f"Failed to load manifest from {capability_dir}: {e}", exc_info=True)

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


def load_capabilities(capabilities_dir: Optional[Path] = None):
    """Load all capability packs (typically called on application startup)"""
    if capabilities_dir is None:
        # Default to loading from app/capabilities directory
        app_dir = Path(__file__).parent.parent
        capabilities_dir = app_dir / "capabilities"

    _registry.load_from_directory(capabilities_dir)
    logger.info(f"Loaded {len(_registry.capabilities)} capabilities, {len(_registry.tools)} tools")


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
    import sys

    tool_name = f"{capability}.{tool}"
    tool_info = _registry.get_tool(tool_name)

    if not tool_info:
        raise ValueError(f"Tool not found: {tool_name}")

    backend_path = tool_info.get('backend')
    if not backend_path:
        raise ValueError(f"Tool {tool_name} has no backend defined")

    # Ensure capability directory is in sys.path for imports
    capability_info = _registry.get_capability(capability)
    if capability_info:
        capability_dir = capability_info.get('directory')
        if capability_dir:
            # Add parent of capabilities directory to sys.path (for imports like 'capabilities.xxx')
            capabilities_parent = capability_dir.parent
            if str(capabilities_parent) not in sys.path:
                sys.path.insert(0, str(capabilities_parent))

            # Also add cloud root (parent of capabilities) for imports like 'services.xxx'
            cloud_root = capabilities_parent.parent
            if str(cloud_root) not in sys.path:
                sys.path.insert(0, str(cloud_root))

    # Parse backend path
    # Format 1: 'module.path:function' - module-level function
    # Format 2: 'module.path:Class.method' - class method
    module_path, target = backend_path.rsplit(':', 1)

    # Normalize module path: if it starts with 'app.', prepend 'backend.'
    if module_path.startswith('app.'):
        module_path = 'backend.' + module_path

    try:
        # Try importing as module first
        try:
            module = importlib.import_module(module_path)
        except (ImportError, ModuleNotFoundError) as import_error:
            # If import fails (e.g., missing __init__.py), try loading file directly
            capability_info = _registry.get_capability(capability)
            if capability_info:
                capability_dir = capability_info.get('directory')
                if capability_dir:
                    # Try to find the file based on backend path
                    # backend path format: capabilities.xxx.tools.xxx_tools:function
                    # Extract file path: capabilities/xxx/tools/xxx_tools.py
                    parts = module_path.split('.')
                    if len(parts) >= 2 and parts[0] == 'capabilities':
                        # capabilities.xxx.tools.xxx_tools -> capabilities/xxx/tools/xxx_tools.py
                        file_path = capability_dir
                        for part in parts[1:]:  # Skip 'capabilities'
                            file_path = file_path / part
                        file_path = file_path.with_suffix('.py')

                        if file_path.exists():
                            import importlib.util as importlib_util
                            spec = importlib_util.spec_from_file_location(module_path, file_path)
                            if spec and spec.loader:
                                module = importlib_util.module_from_spec(spec)
                                spec.loader.exec_module(module)
                                logger.debug(f"Loaded module {module_path} from file: {file_path}")
                            else:
                                raise import_error
                        else:
                            raise import_error
                    else:
                        raise import_error
            else:
                raise import_error

        # Check if it's a class method (format: Class.method)
        if '.' in target:
            class_name, method_name = target.rsplit('.', 1)
            # Get class
            cls = getattr(module, class_name)
            # Instantiate class (no-arg constructor)
            instance = cls()
            # Get method
            func = getattr(instance, method_name)
        else:
            # Module-level function
            func = getattr(module, target)

        # Check if it's an async function
        if inspect.iscoroutinefunction(func):
            import asyncio
            # If async, need to await in outer layer
            # Return coroutine here, let caller decide how to handle
            return func(**kwargs)
        else:
            return func(**kwargs)

    except Exception as e:
        error_msg = f"Failed to call tool {tool_name} (backend: {backend_path}): {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


async def call_tool_async(capability: str, tool: str, **kwargs) -> Any:
    """
    Asynchronously call capability pack tool
    """
    import sys

    tool_name = f"{capability}.{tool}"
    tool_info = _registry.get_tool(tool_name)

    if not tool_info:
        raise ValueError(f"Tool not found: {tool_name}")

    backend_path = tool_info.get('backend')
    if not backend_path:
        raise ValueError(f"Tool {tool_name} has no backend defined")

    # Ensure capability directory is in sys.path for imports
    capability_info = _registry.get_capability(capability)
    if capability_info:
        capability_dir = capability_info.get('directory')
        if capability_dir:
            # Add parent of capabilities directory to sys.path (for imports like 'capabilities.xxx')
            capabilities_parent = capability_dir.parent
            if str(capabilities_parent) not in sys.path:
                sys.path.insert(0, str(capabilities_parent))

            # Also add cloud root (parent of capabilities) for imports like 'services.xxx'
            cloud_root = capabilities_parent.parent
            if str(cloud_root) not in sys.path:
                sys.path.insert(0, str(cloud_root))

    # Parse backend path
    # Format 1: 'module.path:function' - Module-level function
    # Format 2: 'module.path:Class.method' - Class method
    module_path, target = backend_path.rsplit(':', 1)

    # Normalize module path: if it starts with 'app.', prepend 'backend.'
    if module_path.startswith('app.'):
        module_path = 'backend.' + module_path

    try:
        # Try importing as module first
        try:
            module = importlib.import_module(module_path)
        except (ImportError, ModuleNotFoundError) as import_error:
            # If import fails (e.g., missing __init__.py), try loading file directly
            capability_info = _registry.get_capability(capability)
            if capability_info:
                capability_dir = capability_info.get('directory')
                if capability_dir:
                    # Try to find the file based on backend path
                    # backend path format: capabilities.xxx.tools.xxx_tools:function
                    # Extract file path: capabilities/xxx/tools/xxx_tools.py
                    parts = module_path.split('.')
                    if len(parts) >= 2 and parts[0] == 'capabilities':
                        # capabilities.xxx.tools.xxx_tools -> capabilities/xxx/tools/xxx_tools.py
                        file_path = capability_dir
                        for part in parts[1:]:  # Skip 'capabilities'
                            file_path = file_path / part
                        file_path = file_path.with_suffix('.py')

                        if file_path.exists():
                            import importlib.util as importlib_util
                            spec = importlib_util.spec_from_file_location(module_path, file_path)
                            if spec and spec.loader:
                                module = importlib_util.module_from_spec(spec)
                                spec.loader.exec_module(module)
                                logger.debug(f"Loaded module {module_path} from file: {file_path}")
                            else:
                                raise import_error
                        else:
                            raise import_error
                    else:
                        raise import_error
            else:
                raise import_error

        # Check if it's a class method (format: Class.method)
        if '.' in target:
            class_name, method_name = target.rsplit('.', 1)
            # Get class
            cls = getattr(module, class_name)
            # Instantiate class (no-arg constructor)
            instance = cls()
            # Get method
            func = getattr(instance, method_name)
        else:
            # Module-level function
            func = getattr(module, target)

        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            return func(**kwargs)

    except Exception as e:
        # Avoid recursion in error logging - use simple error message
        error_msg = f"Failed to call tool {tool_name} (backend: {backend_path}): {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def get_registry() -> CapabilityRegistry:
    """Get global registry instance"""
    return _registry
