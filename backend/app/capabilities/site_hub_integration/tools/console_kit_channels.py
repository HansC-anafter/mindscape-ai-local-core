"""
Site-Hub Console Kit Channels Tool

Provides tools for retrieving channel information from Site-Hub Console Kit
after Google OAuth authentication.
"""

import os
import httpx
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from .runtime_validator import validate_url

logger = logging.getLogger(__name__)


def get_auth_headers_from_runtime(
    runtime_data: Dict[str, Any], execution_context: Optional[Dict[str, Any]] = None
) -> Dict[str, str]:
    """
    Get auth headers from runtime environment (OAuth2 token or API key).
    """
    headers: Dict[str, str] = {}

    auth_type = runtime_data.get("auth_type", "none")
    auth_config = (
        runtime_data.get("auth_config")
        if isinstance(runtime_data.get("auth_config"), dict)
        else None
    )

    if auth_type == "oauth2" and auth_config:
        # Decrypt token blob if present (auth_config may be encrypted)
        try:
            from app.services.runtime_auth_service import RuntimeAuthService

            svc = RuntimeAuthService()
            token_data = svc.decrypt_token_blob(auth_config)
            access_token = token_data.get("access_token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
        except Exception as e:
            logger.warning(f"Failed to decrypt OAuth token from runtime: {e}")
            # Fallback: try reading plain access_token (legacy path)
            access_token = auth_config.get("access_token") or auth_config.get("token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"

    elif auth_type == "api_key" and auth_config:
        try:
            from app.services.runtime_auth_service import RuntimeAuthService

            svc = RuntimeAuthService()
            decrypted = svc.decrypt_credentials(auth_config)
            api_key = decrypted.get("api_key")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
        except Exception as e:
            logger.warning(f"Failed to decrypt API key from runtime: {e}")
            api_key = auth_config.get("api_key")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

    if not headers.get("Authorization"):
        if execution_context:
            token = execution_context.get("auth_token")
            if token:
                headers["Authorization"] = f"Bearer {token}"

    if not headers.get("Authorization"):
        api_key = os.getenv("SITE_HUB_API_TOKEN")
        if api_key:
            logger.warning(
                "Runtime auth_config not available; falling back to SITE_HUB_API_TOKEN env. "
                "Configure runtime auth_config or ensure execution_context carries credentials."
            )
            headers["Authorization"] = f"Bearer {api_key}"

    return headers


def get_site_hub_base_url(
    runtime_data: Dict[str, Any], config_url: str
) -> Optional[str]:
    """
    Get Site-Hub base URL from runtime environment.
    """
    metadata = (
        runtime_data.get("metadata")
        if isinstance(runtime_data.get("metadata"), dict)
        else {}
    )
    if metadata:
        signature = metadata.get("signature") if isinstance(metadata, dict) else None
        if isinstance(signature, dict):
            base_url = signature.get("base_url")
            if base_url:
                return base_url.rstrip("/")

    if config_url:
        parsed = urlparse(config_url)
        path = parsed.path or ""
        base_path = path.split("/settings", 1)[0] if "/settings" in path else path
        normalized_path = base_path.rstrip("/")

        if normalized_path:
            return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"
        return f"{parsed.scheme}://{parsed.netloc}"

    return None


async def get_console_kit_channels(
    runtime_id: str,
    agency: Optional[str] = None,
    tenant: Optional[str] = None,
    chainagent: Optional[str] = None,
    channel_type: Optional[str] = None,
    local_core_api_base: Optional[str] = None,
    execution_context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Get Console Kit channels from Site-Hub after Google OAuth authentication.

    This tool retrieves channel information from Site-Hub Console Kit API.
    It requires the runtime environment to have OAuth2 authentication configured.

    Args:
        runtime_id: Site-Hub runtime environment ID
        agency: Filter by agency name (optional)
        tenant: Filter by tenant name (optional)
        chainagent: Filter by chainagent name (optional)
        channel_type: Filter by channel type (optional, e.g., "line")
        local_core_api_base: Local-Core API base URL (injected internally)
        execution_context: Execution context (injected internally)
        **kwargs: Additional parameters

    Returns:
        Dictionary with channels list and metadata
    """
    if not execution_context:
        execution_context = kwargs.get("execution_context")

    if not local_core_api_base:
        local_core_api_base = os.getenv(
            "LOCAL_CORE_API_BASE", "http://localhost:8000"
        ).rstrip("/")

    try:
        # Query runtime directly from database for auth access
        # (REST API strips auth_config via include_sensitive=False)
        from app.models.runtime_environment import RuntimeEnvironment
        from app.services.runtime_auth_service import RuntimeAuthService
        from app.database import get_db_postgres

        runtime_obj = None
        runtime_data = {}
        auth_headers_resolved = {}

        try:
            db_gen = get_db_postgres()
            db = next(db_gen)
            initiator_user_id = (
                execution_context.get("initiator_user_id")
                if execution_context
                else None
            )
            query = db.query(RuntimeEnvironment).filter(
                RuntimeEnvironment.id == runtime_id
            )
            if initiator_user_id:
                query = query.filter(RuntimeEnvironment.user_id == initiator_user_id)
            runtime_obj = query.first()

            if not runtime_obj:
                return {
                    "success": False,
                    "error": f"Runtime environment not found: {runtime_id}",
                }

            runtime_data = runtime_obj.to_dict(include_sensitive=False)
            # Get auth headers via RuntimeAuthService (handles decryption + refresh)
            auth_svc = RuntimeAuthService()
            auth_headers_resolved = await auth_svc.get_auth_headers(runtime_obj, db=db)
        except Exception as db_err:
            logger.warning(
                f"Direct DB lookup failed, falling back to REST API: {db_err}"
            )
            # Fallback: fetch via REST API (no auth_config)
            async with httpx.AsyncClient(
                timeout=10.0, follow_redirects=False
            ) as client:
                internal_token = (
                    execution_context.get("auth_token")
                    if execution_context
                    else os.getenv("LOCAL_CORE_API_KEY", "")
                )
                internal_headers = {}
                if internal_token:
                    internal_headers["Authorization"] = f"Bearer {internal_token}"

                runtime_response = await client.get(
                    f"{local_core_api_base}/api/v1/runtime-environments/{runtime_id}",
                    headers=internal_headers,
                )

                if runtime_response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Failed to get runtime environment: {runtime_response.status_code}",
                        "http_status": runtime_response.status_code,
                    }

                runtime_data = runtime_response.json()
                auth_headers_resolved = get_auth_headers_from_runtime(
                    runtime_data, execution_context
                )

        # Early check: if no auth headers available, the token is expired or missing
        if not auth_headers_resolved.get("Authorization"):
            # Determine if this is an expiry vs never-configured situation
            auth_status = (
                getattr(runtime_obj, "auth_status", None) if runtime_obj else None
            )
            if auth_status == "expired":
                return {
                    "success": False,
                    "error": "OAuth token has expired. Please re-authenticate by clicking the 'Connect Google' button.",
                    "auth_expired": True,
                    "runtime_id": runtime_id,
                }
            else:
                return {
                    "success": False,
                    "error": "No valid authentication token found. Please authenticate by clicking the 'Connect Google' button.",
                    "auth_expired": True,
                    "runtime_id": runtime_id,
                }

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:

            config_url = runtime_data.get("config_url", "")
            site_hub_base = get_site_hub_base_url(runtime_data, config_url)
            if not site_hub_base:
                return {
                    "success": False,
                    "error": "Cannot determine Site-Hub base URL from runtime environment. "
                    "Please ensure runtime has config_url or metadata.signature.base_url",
                }

            parsed = urlparse(site_hub_base)
            host_url = f"{parsed.scheme}://{parsed.netloc}"

            is_valid, error_msg = validate_url(host_url)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"URL validation failed: {error_msg}",
                    "security_note": "For security, only URLs from allowlist are accepted.",
                    "site_hub_base": site_hub_base,
                }

            # Get chainagent_id from merged metadata (workspace override > global override > base)
            runtime_metadata = runtime_data.get("metadata", {}) or {}

            # If workspace_id is available, merge with workspace-scoped overrides
            workspace_id = kwargs.get("workspace_id")
            if not workspace_id and execution_context:
                workspace_id = execution_context.get("workspace_id")

            if runtime_obj:
                try:
                    from app.routes.core.workspace_runtime_config import (
                        resolve_runtime_metadata,
                    )

                    runtime_metadata = resolve_runtime_metadata(
                        runtime_obj, workspace_id, db
                    )
                except Exception as merge_err:
                    logger.debug(f"Runtime config merge skipped: {merge_err}")

            chainagent_id = runtime_metadata.get("chainagent_id")
            if not chainagent_id:
                return {
                    "success": False,
                    "error": "Runtime metadata missing 'chainagent_id'. "
                    "Please configure ChainAgent ID in workspace Runtime Settings "
                    "or Settings > Runtime Environments > Site-Hub.",
                    "site_hub_base": site_hub_base,
                }

            # Build registry API endpoint for listing channels
            channels_url = (
                f"{site_hub_base.rstrip('/')}"
                f"/api/v1/registry/chainagents/{chainagent_id}/channels"
            )

            # Add query parameters for filtering
            params = {}
            if channel_type:
                params["channel_type"] = channel_type
            if agency:
                params["agency"] = agency
            if tenant:
                params["tenant"] = tenant

            channels_response = await client.get(
                channels_url, headers=auth_headers_resolved, params=params
            )

            if channels_response.status_code == 200:
                channels_data = channels_response.json()

                # Registry API returns: { success, data: { channels, pagination } }
                if isinstance(channels_data, dict):
                    data_payload = channels_data.get("data", channels_data)
                    channels = (
                        data_payload.get("channels", [])
                        if isinstance(data_payload, dict)
                        else []
                    )
                elif isinstance(channels_data, list):
                    channels = channels_data
                else:
                    channels = []

                return {
                    "success": True,
                    "channels": channels,
                    "runtime_id": runtime_id,
                    "chainagent_id": chainagent_id,
                    "site_hub_base": site_hub_base,
                    "filters_applied": {
                        "agency": agency,
                        "tenant": tenant,
                        "chainagent": chainagent,
                        "channel_type": channel_type,
                    },
                    "total_count": len(channels),
                }
            else:
                error_detail = {
                    "success": False,
                    "error": f"Failed to get channels from registry API: {channels_response.status_code}",
                    "http_status": channels_response.status_code,
                    "channels_url": channels_url,
                    "site_hub_base": site_hub_base,
                    "chainagent_id": chainagent_id,
                    "response_text": (
                        channels_response.text[:200] if channels_response.text else None
                    ),
                }
                # 401/403 = auth issue, signal frontend to re-authenticate
                if channels_response.status_code in (401, 403):
                    error_detail["auth_expired"] = True
                    error_detail["error"] = (
                        "OAuth token is invalid or expired. "
                        "Please re-authenticate by clicking the 'Connect Google' button."
                    )
                return error_detail

    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Timeout connecting to Site-Hub or Local-Core API",
        }
    except Exception as e:
        logger.error(f"Error getting Console Kit channels: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Error getting Console Kit channels: {str(e)}",
        }
