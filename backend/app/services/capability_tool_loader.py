"""
Capability Pack Tool Loader
Loads and registers capability pack tools as MindscapeTool instances
"""

import importlib
import importlib.util
import sys
import inspect
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import logging

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolSourceType,
    create_simple_tool_metadata,
)
from backend.app.services.tools.registry import register_mindscape_tool
from .capability_registry import get_registry

logger = logging.getLogger(__name__)


class CapabilityToolWrapper(MindscapeTool):
    """
    Wrapper for capability pack tools to make them compatible with MindscapeTool interface
    """

    def __init__(
        self,
        tool_name: str,
        tool_func: Callable,
        tool_info: Dict[str, Any],
        capability_code: str,
    ):
        """
        Initialize capability tool wrapper

        Args:
            tool_name: Tool name (e.g., "site_hub_bind_channel")
            tool_func: Tool function from capability pack
            tool_info: Tool info from manifest
            capability_code: Capability code
        """
        # Extract parameters from function signature
        sig = inspect.signature(tool_func)
        parameters = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ["execution_context", "local_core_api_base", "kwargs"]:
                continue  # Skip internal parameters

            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == dict or param.annotation == Dict:
                    param_type = "object"
                elif param.annotation == list or param.annotation == list:
                    param_type = "array"

            parameters[param_name] = {
                "type": param_type,
                "description": f"Parameter {param_name}",
            }

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        # Create tool metadata
        metadata = create_simple_tool_metadata(
            name=tool_name,
            description=tool_info.get(
                "description", f"{capability_code} tool: {tool_name}"
            ),
            parameters=parameters,
            required=required,
        )
        # Set source type to CAPABILITY_PACK
        metadata.source_type = ToolSourceType.BUILTIN

        super().__init__(metadata)

        self.tool_func = tool_func
        self.tool_info = tool_info
        self.capability_code = capability_code

    async def execute(self, **kwargs) -> Any:
        """
        Execute capability tool

        Args:
            **kwargs: Tool parameters

        Returns:
            Tool execution result
        """
        # Remove internal parameters that shouldn't be passed to tool
        tool_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ["execution_context", "local_core_api_base"]
        }

        # Call the tool function
        if inspect.iscoroutinefunction(self.tool_func):
            result = await self.tool_func(**tool_kwargs)
        else:
            result = self.tool_func(**tool_kwargs)

        return result


def load_capability_tool(
    capability_code: str,
    tool_name: str,
    tool_info: Dict[str, Any],
    capability_dir: Path,
) -> Optional[MindscapeTool]:
    """
    Load a capability tool and register it as MindscapeTool

    Args:
        capability_code: Capability code
        tool_name: Tool name
        tool_info: Tool info from manifest
        capability_dir: Capability directory

    Returns:
        MindscapeTool instance or None
    """
    try:
        # Get backend path from tool_info
        backend = tool_info.get("backend")
        if not backend:
            logger.warning(f"Tool {capability_code}.{tool_name} has no backend defined")
            return None

        # Parse backend path (e.g., "app.capabilities.mindscape_cloud_integration.tools.channel_binding:bind_channel")
        if ":" not in backend:
            logger.warning(
                f"Invalid backend format for {capability_code}.{tool_name}: {backend}"
            )
            return None

        module_path, func_name = backend.rsplit(":", 1)

        # Try to import the module
        try:
            # Handle both app.capabilities.* and capabilities.* paths
            # Also handle directory name variations (underscore vs hyphen)
            if module_path.startswith("app.capabilities."):
                # Try direct import first
                try:
                    logger.debug(f"Importing module: {module_path}")
                    module = importlib.import_module(module_path)
                except ImportError:
                    # Try with hyphen-to-underscore conversion in directory name
                    # e.g., app.capabilities.mindscape_cloud_integration -> app.capabilities.mindscape-cloud-integration
                    parts = module_path.split(".")
                    if (
                        len(parts) >= 3 and parts[2]
                    ):  # app.capabilities.{capability_code}
                        capability_code = parts[2]
                        # Check if directory uses hyphen instead of underscore
                        capability_dir = (
                            capability_dir if "capability_dir" in locals() else None
                        )
                        if capability_dir and capability_dir.exists():
                            actual_dir_name = capability_dir.name
                            if actual_dir_name != capability_code:
                                # Replace capability code in module path with actual directory name
                                parts[2] = actual_dir_name
                                alt_module_path = ".".join(parts)
                                try:
                                    module = importlib.import_module(alt_module_path)
                                except ImportError:
                                    raise
                            else:
                                raise
                        else:
                            raise
                    else:
                        raise
            elif module_path.startswith("capabilities."):
                # Try app.capabilities.* first, then capabilities.*
                app_module_path = module_path.replace(
                    "capabilities.", "app.capabilities.", 1
                )
                try:
                    module = importlib.import_module(app_module_path)
                except ImportError:
                    logger.debug(f"Importing module: {module_path}")
                    module = importlib.import_module(module_path)
            else:
                logger.debug(f"Importing module: {module_path}")
                module = importlib.import_module(module_path)

            # Get the function — support dotted names like ClassName.method_name
            if "." in func_name:
                parts = func_name.split(".")
                obj = module
                for i, part in enumerate(parts):
                    next_obj = getattr(obj, part, None)
                    if next_obj is None:
                        logger.warning(f"Attribute '{part}' not found when resolving {func_name} in {module_path}")
                        return None
                    # If this is a class (not the final part), instantiate it
                    if i < len(parts) - 1 and inspect.isclass(next_obj):
                        try:
                            next_obj = next_obj()
                        except Exception as e:
                            logger.warning(f"Failed to instantiate {part} in {module_path}: {e}")
                            return None
                    obj = next_obj
                tool_func = obj
            else:
                tool_func = getattr(module, func_name, None)
            if not tool_func:
                logger.warning(f"Function {func_name} not found in {module_path}")
                return None

            # Create wrapper
            wrapper = CapabilityToolWrapper(
                tool_name=tool_name,
                tool_func=tool_func,
                tool_info=tool_info,
                capability_code=capability_code,
            )

            # Register tool
            full_tool_name = f"{capability_code}.{tool_name}"
            register_mindscape_tool(full_tool_name, wrapper)

            logger.info(f"Registered capability tool: {full_tool_name}")
            return wrapper

        except ImportError as e:
            logger.warning(
                f"Failed to import module {module_path} for tool {capability_code}.{tool_name}: {e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Failed to load tool {capability_code}.{tool_name}: {e}", exc_info=True
            )
            return None

    except Exception as e:
        logger.error(
            f"Error loading capability tool {capability_code}.{tool_name}: {e}",
            exc_info=True,
        )
        return None


def load_all_capability_tools():
    """
    Load all capability pack tools and register them as MindscapeTool instances
    """
    registry = get_registry()
    loaded_count = 0

    for capability_code, capability_data in registry.capabilities.items():
        capability_dir = capability_data.get("directory")
        if not capability_dir:
            continue

        manifest = capability_data.get("manifest", {})
        tools = manifest.get("tools", [])

        for tool_info in tools:
            tool_name = tool_info.get("name")
            if not tool_name:
                continue

            tool = load_capability_tool(
                capability_code=capability_code,
                tool_name=tool_name,
                tool_info=tool_info,
                capability_dir=capability_dir,
            )

            if tool:
                loaded_count += 1

    logger.info(f"Loaded {loaded_count} capability pack tools")
    return loaded_count
