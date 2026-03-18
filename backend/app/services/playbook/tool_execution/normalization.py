"""
Tool Parameter Normalization Pipeline
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ToolParameterNormalizer:
    """Normalizes tool parameters to match the capability registry expectations"""

    @classmethod
    def normalize(
        cls, 
        tool_fqn: str, 
        kwargs: Dict[str, Any], 
        execution_context: Optional[Dict[str, Any]] = None, 
        workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Normalize tool parameters.
        Returns a new dict with normalized parameters.
        """
        normalized_kwargs = kwargs.copy()
        execution_context = execution_context or {}

        # Parameter normalization: convert common incorrect parameter names to correct ones
        if (
            tool_fqn == "filesystem_write_file"
            and "path" in normalized_kwargs
            and "file_path" not in normalized_kwargs
        ):
            normalized_kwargs["file_path"] = normalized_kwargs.pop("path")
            logger.debug(f"Normalized parameter 'path' -> 'file_path' for {tool_fqn}")

        # Normalize core_llm.structured_extract parameters
        if tool_fqn == "core_llm.structured_extract":
            if "input" in normalized_kwargs and "text" not in normalized_kwargs:
                normalized_kwargs["text"] = normalized_kwargs.pop("input")
                logger.debug(f"Normalized parameter 'input' -> 'text' for {tool_fqn}")
            if "schema" in normalized_kwargs and "schema_description" not in normalized_kwargs:
                normalized_kwargs["schema_description"] = normalized_kwargs.pop("schema")
                logger.debug(f"Normalized parameter 'schema' -> 'schema_description' for {tool_fqn}")

        if tool_fqn.startswith("sandbox."):
            execution_sandbox_id = execution_context.get("sandbox_id")
            execution_workspace_id = workspace_id or execution_context.get("workspace_id")
            if execution_sandbox_id and execution_workspace_id:
                if "sandbox_id" not in normalized_kwargs:
                    normalized_kwargs["sandbox_id"] = execution_sandbox_id
                if "workspace_id" not in normalized_kwargs:
                    normalized_kwargs["workspace_id"] = execution_workspace_id
                logger.debug(f"Auto-injected sandbox_id={execution_sandbox_id} and workspace_id={execution_workspace_id} for {tool_fqn}")

        # Auto-inject workspace_id for capability tools that need it
        if tool_fqn and "." in tool_fqn:
            execution_workspace_id = workspace_id or execution_context.get("workspace_id")
            if execution_workspace_id and "workspace_id" not in normalized_kwargs:
                normalized_kwargs["workspace_id"] = execution_workspace_id
                logger.debug(f"Auto-injected workspace_id={execution_workspace_id} for {tool_fqn}")

        return normalized_kwargs
