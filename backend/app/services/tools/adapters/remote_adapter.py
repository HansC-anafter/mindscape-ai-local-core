"""
Remote Tool Adapter

Generic HTTP adapter for calling remote tool services.
Provides unified interface for remote tool API calls without vendor-specific bindings.
"""
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class RemoteToolAdapter:
    """Generic Remote Tool API calling adapter

    Provides HTTP API interface for calling remote tool services.
    Handles authentication, error handling, and retry logic.
    """

    def __init__(self, timeout: float = 30.0):
        """
        Initialize Remote Tool Adapter

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout

    async def call_remote_tool(
        self,
        cluster_url: str,
        tool_type: str,
        action: str,
        params: Dict[str, Any],
        api_token: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call remote tool API

        Args:
            cluster_url: Remote tool service base URL
            tool_type: Tool type (line, wp, slack, ...)
            action: Action name (send_message, publish_post, ...)
            params: Tool parameters (explicitly specified by each Tool, e.g., channel_id, site_id)
            api_token: API authentication token
            context: Execution context (tenant_id, workspace_id, execution_id, etc.)

        Returns:
            API response result

        Raises:
            httpx.HTTPError: HTTP request failed
            RuntimeError: Tool execution failed
        """
        endpoint = f"{cluster_url.rstrip('/')}/v1/tools/{tool_type}.{action}"

        headers = {
            "Content-Type": "application/json"
        }
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        payload = {**params}

        if context:
            payload["context"] = context

        logger.info(
            f"Calling remote tool: {tool_type}.{action}",
            extra={
                "endpoint": endpoint,
                "tool_type": tool_type,
                "action": action,
                "has_context": bool(context)
            }
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers
                )

                response.raise_for_status()

                result = response.json()

                if not result.get("success", False):
                    error_info = result.get("error", {})
                    error_message = error_info.get("message", "Unknown error")
                    error_code = error_info.get("code", "TOOL_EXECUTION_ERROR")

                    logger.error(
                        f"Remote tool execution failed: {error_code} - {error_message}",
                        extra={
                            "tool_type": tool_type,
                            "action": action,
                            "error_code": error_code,
                            "error_details": error_info.get("details", {})
                        }
                    )

                    raise RuntimeError(
                        f"Remote tool execution failed: {error_code} - {error_message}"
                    )

                logger.info(
                    f"Remote tool execution succeeded: {tool_type}.{action}",
                    extra={
                        "tool_type": tool_type,
                        "action": action
                    }
                )

                return result

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error calling remote tool: {e.response.status_code}",
                extra={
                    "endpoint": endpoint,
                    "status_code": e.response.status_code,
                    "response_text": e.response.text[:200] if e.response.text else None
                }
            )
            raise
        except httpx.TimeoutException as e:
            logger.error(
                f"Timeout calling remote tool: {endpoint}",
                extra={"endpoint": endpoint, "timeout": self.timeout}
            )
            raise RuntimeError(f"Remote tool API timeout: {endpoint}") from e
        except httpx.RequestError as e:
            logger.error(
                f"Request error calling remote tool: {endpoint}",
                extra={"endpoint": endpoint, "error": str(e)}
            )
            raise RuntimeError(f"Remote tool API request failed: {endpoint}") from e
        except Exception as e:
            logger.error(
                f"Unexpected error calling remote tool: {endpoint}",
                extra={"endpoint": endpoint, "error": str(e)},
                exc_info=True
            )
            raise

