from pathlib import Path
from typing import Any, Dict, Optional
import importlib
import inspect
import logging
import sys

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolDangerLevel,
    ToolInputSchema,
    ToolMetadata,
    ToolSourceType,
)
from backend.app.services.unified_tool_executor_core.runtime_context import (
    _inject_runtime_context,
)

logger = logging.getLogger("backend.app.services.unified_tool_executor")

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def resolve_capability_tool(tool_id: str) -> Optional[MindscapeTool]:
    """
    Resolve a capability tool by tool_id using installed manifest.yaml backend mapping.

    Expected tool_id format: "{capability_code}.{tool_code}"
    """
    try:
        if "." not in tool_id:
            return None
        cap_code, tool_code = tool_id.split(".", 1)
        if not cap_code or not tool_code:
            return None

        if yaml is None:
            return None

        app_dir = Path(__file__).resolve().parents[2]
        app_dir_str = str(app_dir)
        if app_dir_str not in sys.path:
            sys.path.insert(0, app_dir_str)
        capabilities_dir = app_dir / "capabilities"
        manifest_path = capabilities_dir / cap_code / "manifest.yaml"
        if not manifest_path.exists():
            return None

        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        backend = None
        tool_desc = ""
        for tool_cfg in manifest.get("tools", []) or []:
            if not isinstance(tool_cfg, dict):
                continue
            if (tool_cfg.get("code") or tool_cfg.get("name")) == tool_code:
                backend = tool_cfg.get("backend")
                tool_desc = tool_cfg.get("description") or ""
                break

        if not backend or ":" not in backend:
            return None

        module_path, target = backend.rsplit(":", 1)
        module = importlib.import_module(module_path)
        fn = _resolve_backend_target(module, target)
        if fn is None:
            return None

        factory_tool = _resolve_tool_factory(fn)
        if factory_tool is not None:
            return factory_tool

        return _CapabilityToolWrapper(
            cap_code=cap_code,
            tool_code=tool_code,
            tool_id=tool_id,
            tool_desc=tool_desc,
            fn=fn,
        )
    except Exception as exc:
        logger.debug(
            "Capability tool resolve failed for %s: %s", tool_id, exc, exc_info=True
        )
        return None


def _resolve_backend_target(module, target: str):
    current = module
    for part in target.split("."):
        if inspect.isclass(current):
            current = current()
        current = getattr(current, part, None)
        if current is None:
            return None
    if inspect.isclass(current):
        return current()
    return current


def _resolve_tool_factory(fn) -> Optional[MindscapeTool]:
    if isinstance(fn, MindscapeTool):
        return fn
    if not callable(fn):
        return None

    signature = inspect.signature(fn)
    required_params = [
        param
        for param in signature.parameters.values()
        if param.default is inspect.Signature.empty
        and param.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    ]
    if required_params:
        return None

    candidate = fn()
    if isinstance(candidate, MindscapeTool):
        return candidate
    return None


class _CapabilityToolWrapper(MindscapeTool):
    def __init__(self, *, cap_code: str, tool_code: str, tool_id: str, tool_desc: str, fn):
        metadata = ToolMetadata(
            name=tool_code,
            description=(tool_desc or f"Capability tool '{tool_id}' wrapper."),
            input_schema=ToolInputSchema(type="object", properties={}, required=[]),
            category=ToolCategory.AUTOMATION,
            source_type=ToolSourceType.CUSTOM,
            provider=cap_code,
            danger_level=ToolDangerLevel.LOW,
        )
        super().__init__(metadata)
        self._fn = fn
        self._signature = inspect.signature(fn)

    def validate_input(self, **kwargs) -> Dict[str, Any]:  # type: ignore[override]
        return kwargs

    async def execute(self, **kwargs) -> Any:  # type: ignore[override]
        result = self._fn(**_inject_runtime_context(kwargs, self._signature))
        if inspect.isawaitable(result):
            return await result
        return result
