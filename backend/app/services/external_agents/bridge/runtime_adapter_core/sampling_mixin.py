"""MCP sampling execution helpers for host bridge runtime adapter."""

import hashlib
import json
import logging
import time
from typing import Any, Dict

from backend.app.services.external_agents.core.base_adapter import (
    RuntimeExecRequest,
    RuntimeExecResponse,
)

from .parsing import parse_dispatch_response

logger = logging.getLogger(__name__)


class SamplingExecutionMixin:
    async def _execute_via_sampling(
        self,
        request: RuntimeExecRequest,
        execution_id: str,
    ) -> RuntimeExecResponse:
        """Dispatch task via MCP Sampling createMessage()."""
        start_time = time.monotonic()

        if not self.sampling_gate or not self.mcp_server:
            logger.warning("Sampling not available, falling back to polling strategy")
            return await self._execute_via_polling(request, execution_id)

        from backend.app.services.sampling_gate import SamplingGate

        prompt_params = SamplingGate.build_agent_task_dispatch_prompt(
            task=request.task,
            execution_id=execution_id,
            workspace_id=request.workspace_id or "",
            allowed_tools=request.allowed_tools,
            context={
                "project_id": request.project_id,
                "intent_id": request.intent_id,
                "lens_id": request.lens_id,
            },
        )

        async def sampling_fn():
            return await self.mcp_server.createMessage(**prompt_params)

        async def fallback_fn():
            return await self._execute_via_polling(request, execution_id)

        result = await self.sampling_gate.with_fallback(
            sampling_fn=sampling_fn,
            fallback_fn=fallback_fn,
            workspace_id=request.workspace_id or "",
            template="agent_task_dispatch",
        )

        if result.source == "sampling" and result.data:
            raw_result = self._parse_sampling_result(
                result.data,
                execution_id,
            )
            raw_result.setdefault("metadata", {})["transport"] = "mcp_sampling"
            return parse_dispatch_response(raw_result, start_time)

        if isinstance(result.data, RuntimeExecResponse):
            return result.data

        return RuntimeExecResponse(
            success=False,
            output="",
            duration_seconds=time.monotonic() - start_time,
            error=f"Sampling chain failed: {result.error}",
            agent_metadata={
                "transport": "mcp_sampling",
                "execution_id": execution_id,
                "sampling_source": result.source,
            },
        )

    def _parse_sampling_result(
        self,
        sampling_response: Any,
        execution_id: str,
    ) -> Dict[str, Any]:
        """Parse MCP Sampling response into dispatch response format."""
        try:
            content = sampling_response
            if hasattr(content, "content"):
                content = content.content
            if hasattr(content, "text"):
                content = content.text
            if isinstance(content, dict):
                content = content.get("text", str(content))

            try:
                parsed = json.loads(content) if isinstance(content, str) else content
                if isinstance(parsed, dict):
                    parsed["execution_id"] = execution_id
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

            output_text = str(content)
            return {
                "execution_id": execution_id,
                "status": "completed",
                "output": output_text,
                "governance": {
                    "output_hash": hashlib.sha256(output_text.encode()).hexdigest(),
                },
            }

        except Exception as e:
            logger.error(f"Failed to parse sampling result: {e}")
            return {
                "execution_id": execution_id,
                "status": "failed",
                "error": f"Failed to parse sampling response: {e}",
            }
