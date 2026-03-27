import os
import httpx
import logging
from typing import Optional, Dict, Any
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


async def register_comfyui(
    comfyui_url: str,
    runtime_id: Optional[str] = None,
    execution_context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Register ComfyUI URL in runtime configuration via Local-Core API.
    """
    local_core_api_base = os.getenv("LOCAL_CORE_API_BASE", "http://localhost:8000")

    # 1. Get Auth Headers
    if not execution_context:
        execution_context = kwargs.get("execution_context")

    headers = {}
    if execution_context and execution_context.get("auth_token"):
        headers["Authorization"] = f"Bearer {execution_context['auth_token']}"

    if not headers.get("Authorization"):
        # Fallback to API Key if available (Dev mode)
        api_key = os.getenv("LOCAL_CORE_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            logger.warning("No auth token available for registration")
            return {
                "success": False,
                "message": "Auth token required to register runtime",
                "comfyui_url": comfyui_url,
            }

    comfyui_url = comfyui_url.rstrip("/")
    runtime_name = "ComfyUI Local"

    # 2. Check for existing runtime
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # List existing runtimes
            list_response = await client.get(
                f"{local_core_api_base}/api/v1/runtime-environments", headers=headers
            )

            existing_id = None
            if list_response.status_code == 200:
                response_data = list_response.json()
                # API returns {"runtimes": [...]} wrapper
                if isinstance(response_data, dict):
                    runtimes = response_data.get("runtimes", [])
                else:
                    runtimes = response_data
                for rt in runtimes:
                    if (
                        rt.get("config_url") == comfyui_url
                        or rt.get("name") == runtime_name
                    ):
                        existing_id = rt.get("id")
                        break

            payload = {
                "name": runtime_name,
                "description": "Local ComfyUI instance (Managed by Mindscape)",
                "icon": "🎨",
                "config_url": comfyui_url,  # Using config_url to store the base URL
                "auth_type": "none",
                "metadata": {
                    "runtime_type": "comfyui",
                    "capability_code": "comfyui_runtime",
                },
                "supports_dispatch": True,  # Can receive jobs
                "supports_cell": False,
                "recommended_for_dispatch": True,
            }

            if existing_id:
                # Update
                logger.info(f"Updating existing ComfyUI runtime {existing_id}...")
                resp = await client.put(
                    f"{local_core_api_base}/api/v1/runtime-environments/{existing_id}",
                    json=payload,
                    headers=headers,
                )
                action = "updated"
            else:
                # Create
                logger.info(f"Creating new ComfyUI runtime...")
                resp = await client.post(
                    f"{local_core_api_base}/api/v1/runtime-environments",
                    json=payload,
                    headers=headers,
                )
                action = "created"

            if resp.status_code in [200, 201]:
                data = resp.json()
                return {
                    "success": True,
                    "action": action,
                    "runtime_id": data.get("id"),
                    "message": f"ComfyUI registered at {comfyui_url}",
                    "comfyui_url": comfyui_url,
                }
            else:
                logger.error(f"Failed to register runtime: {resp.text}")
                return {
                    "success": False,
                    "message": f"Failed to register: {resp.status_code}",
                    "details": resp.text,
                }

        except Exception as e:
            logger.error(f"Exception during registration: {e}")
            return {"success": False, "message": str(e), "comfyui_url": comfyui_url}
