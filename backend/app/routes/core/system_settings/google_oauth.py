"""
Google OAuth endpoints
"""
from fastapi import APIRouter, HTTPException, Query, Body, Request
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import logging

from .shared import settings_store
from backend.app.models.system_settings import (
    SystemSetting,
    SettingType
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================
# Google OAuth Configuration Endpoints
# IMPORTANT: These must be defined BEFORE /{key} route to avoid route conflicts
# ============================================

@router.get("/google-oauth", response_model=Dict[str, Any])
async def get_google_oauth_config():
    """Get Google OAuth configuration"""
    try:
        client_id_setting = settings_store.get_setting("google_oauth_client_id")
        client_secret_setting = settings_store.get_setting("google_oauth_client_secret")
        redirect_uri_setting = settings_store.get_setting("google_oauth_redirect_uri")
        backend_url_setting = settings_store.get_setting("backend_url")

        # Mask sensitive values
        client_secret_value = "***" if client_secret_setting and client_secret_setting.value else ""

        return {
            "client_id": str(client_id_setting.value) if client_id_setting and client_id_setting.value else "",
            "client_secret": client_secret_value,
            "redirect_uri": str(redirect_uri_setting.value) if redirect_uri_setting and redirect_uri_setting.value else "",
            "backend_url": str(backend_url_setting.value) if backend_url_setting and backend_url_setting.value else "",
            "is_configured": bool(
                client_id_setting and client_id_setting.value and
                client_secret_setting and client_secret_setting.value
            )
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Google OAuth config: {str(e)}")


class GoogleOAuthConfigUpdate(BaseModel):
    """Google OAuth configuration update request"""
    client_id: Optional[str] = Field(None, description="Google OAuth Client ID")
    client_secret: Optional[str] = Field(None, description="Google OAuth Client Secret")
    redirect_uri: Optional[str] = Field(None, description="OAuth Redirect URI (optional, auto-generated if not provided)")
    backend_url: Optional[str] = Field(None, description="Backend URL for OAuth callback construction")


@router.put("/google-oauth", response_model=Dict[str, Any])
async def update_google_oauth_config(request: GoogleOAuthConfigUpdate):
    """Update Google OAuth configuration"""
    try:
        from backend.app.models.system_settings import SystemSetting, SettingType

        request_dict = request.dict(exclude_none=True)
        logger.info(f"Received Google OAuth update request with {len(request_dict)} fields: {list(request_dict.keys())}")
        for key, value in request_dict.items():
            if key == "client_secret":
                logger.info(f"  {key}: {'*** (masked, length: ' + str(len(value)) + ')' if value else 'empty'}")
            else:
                logger.info(f"  {key}: {str(value)[:50] + '...' if value and len(str(value)) > 50 else (value or 'empty')}")

        updated_settings = {}

        if request.client_id is not None:
            client_id_value = request.client_id.strip() if isinstance(request.client_id, str) else str(request.client_id)
            if client_id_value:
                setting = SystemSetting(
                    key="google_oauth_client_id",
                    value=client_id_value,
                    value_type=SettingType.STRING,
                    category="oauth",
                    description="Google OAuth 2.0 Client ID for Google Drive integration",
                    is_sensitive=False,
                    is_user_editable=True
                )
                logger.info(f"Attempting to save google_oauth_client_id: {client_id_value[:30]}... (length: {len(client_id_value)})")
                settings_store.save_setting(setting)
                updated_settings["client_id"] = client_id_value
                logger.info(f"Save operation completed for google_oauth_client_id")

                # Verify save immediately after commit
                verify = settings_store.get_setting("google_oauth_client_id")
                if verify:
                    verify_value_str = str(verify.value) if verify.value else ""
                    verify_length = len(verify_value_str)
                    logger.info(f"Verification read - key exists: True, value length: {verify_length}, value preview: {verify_value_str[:30] if verify_value_str else '(empty)'}...")
                    if verify_value_str and verify_length > 0:
                        if verify_value_str == client_id_value:
                            logger.info(f"Verified google_oauth_client_id saved successfully (length: {verify_length})")
                        else:
                            logger.error(f"Verification failed - value mismatch! Expected: {client_id_value[:30]}..., Got: {verify_value_str[:30]}...")
                    else:
                        logger.error(f"WARNING: google_oauth_client_id verification failed - value is empty after save! (length: {verify_length})")
                else:
                    logger.error("WARNING: google_oauth_client_id verification failed - setting not found after save!")

        if request.client_secret is not None:
            client_secret_value = request.client_secret.strip() if isinstance(request.client_secret, str) else str(request.client_secret)
            if client_secret_value:
                setting = SystemSetting(
                    key="google_oauth_client_secret",
                    value=client_secret_value,
                    value_type=SettingType.STRING,
                    category="oauth",
                    description="Google OAuth 2.0 Client Secret for Google Drive integration",
                    is_sensitive=True,
                    is_user_editable=True
                )
                logger.info(f"Attempting to save google_oauth_client_secret (length: {len(client_secret_value)})")
                settings_store.save_setting(setting)
                updated_settings["client_secret"] = "***"
                logger.info(f"Save operation completed for google_oauth_client_secret")

                # Verify save
                verify = settings_store.get_setting("google_oauth_client_secret")
                if verify:
                    verify_value_str = str(verify.value) if verify.value else ""
                    verify_length = len(verify_value_str)
                    logger.info(f"Verification read - key exists: True, value length: {verify_length}")
                    if verify_value_str and verify_length > 0:
                        if verify_value_str == client_secret_value:
                            logger.info(f"Verified google_oauth_client_secret saved successfully (length: {verify_length})")
                        else:
                            logger.error(f"Verification failed - value mismatch for client_secret!")
                    else:
                        logger.error(f"WARNING: google_oauth_client_secret verification failed - value is empty after save! (length: {verify_length})")
                else:
                    logger.error("WARNING: google_oauth_client_secret verification failed - setting not found after save!")
            else:
                logger.warning("Received empty client_secret, skipping save")

        if request.redirect_uri is not None:
            redirect_uri_value = request.redirect_uri.strip() if isinstance(request.redirect_uri, str) and request.redirect_uri.strip() else None
            if redirect_uri_value:
                logger.info(f"Attempting to save google_oauth_redirect_uri: {redirect_uri_value}")
                setting = SystemSetting(
                    key="google_oauth_redirect_uri",
                    value=redirect_uri_value,
                    value_type=SettingType.STRING,
                    category="oauth",
                    description="Google OAuth Redirect URI",
                    is_sensitive=False,
                    is_user_editable=True
                )
                settings_store.save_setting(setting)
                updated_settings["redirect_uri"] = redirect_uri_value
                logger.info(f"Save operation completed for google_oauth_redirect_uri")

                # Verify save
                verify = settings_store.get_setting("google_oauth_redirect_uri")
                if verify:
                    verify_value_str = str(verify.value) if verify.value else ""
                    verify_length = len(verify_value_str)
                    if verify_value_str and verify_length > 0:
                        logger.info(f"Verified google_oauth_redirect_uri saved successfully (length: {verify_length})")
                    else:
                        logger.error(f"WARNING: google_oauth_redirect_uri verification failed - value is empty after save!")
                else:
                    logger.error("WARNING: google_oauth_redirect_uri verification failed - setting not found after save!")
            else:
                logger.warning("Received empty redirect_uri, skipping save")

        if request.backend_url is not None:
            backend_url_value = request.backend_url.strip() if isinstance(request.backend_url, str) else str(request.backend_url)
            if backend_url_value:
                setting = SystemSetting(
                    key="backend_url",
                    value=backend_url_value,
                    value_type=SettingType.STRING,
                    category="oauth",
                    description="Backend URL for OAuth callback construction",
                    is_sensitive=False,
                    is_user_editable=True
                )
                logger.info(f"Attempting to save backend_url: {backend_url_value} (length: {len(backend_url_value)})")
                settings_store.save_setting(setting)
                updated_settings["backend_url"] = backend_url_value
                logger.info(f"Save operation completed for backend_url")

                # Verify save
                verify = settings_store.get_setting("backend_url")
                if verify:
                    verify_value_str = str(verify.value) if verify.value else ""
                    verify_length = len(verify_value_str)
                    logger.info(f"Verification read - key exists: True, value length: {verify_length}, value: {verify_value_str}")
                    if verify_value_str and verify_length > 0:
                        if verify_value_str == backend_url_value:
                            logger.info(f"Verified backend_url saved successfully (length: {verify_length})")
                        else:
                            logger.error(f"Verification failed - value mismatch! Expected: {backend_url_value}, Got: {verify_value_str}")
                    else:
                        logger.error(f"WARNING: backend_url verification failed - value is empty after save! (length: {verify_length})")
                else:
                    logger.error("WARNING: backend_url verification failed - setting not found after save!")

        logger.info(f"Google OAuth configuration update completed. Updated fields: {list(updated_settings.keys())}")

        if not updated_settings:
            logger.warning("No fields were updated - all values may be empty or None")

        return {
            "success": True,
            "message": "Google OAuth configuration updated",
            "updated_settings": updated_settings
        }
    except Exception as e:
        logger.error(f"Failed to update Google OAuth config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update Google OAuth config: {str(e)}")


class GoogleOAuthTestRequest(BaseModel):
    """Google OAuth test request body"""
    client_id: Optional[str] = Field(default=None, description="Client ID to test")
    client_secret: Optional[str] = Field(default=None, description="Client Secret to test")


@router.post("/google-oauth/test", response_model=Dict[str, Any])
async def test_google_oauth_config(
    request: Request,
):
    """Test Google OAuth configuration by validating credentials format"""
    try:
        # Read JSON body directly from request
        try:
            request_body = await request.json()
        except Exception as json_error:
            logger.error(f"Failed to parse JSON body: {json_error}")
            logger.info(f"Request Content-Type: {request.headers.get('content-type', 'not set')}")
            raise HTTPException(status_code=400, detail=f"Invalid JSON in request body: {str(json_error)}")

        # Log request headers and body
        content_type = request.headers.get('content-type', 'not set')
        logger.info(f"Received test request - Content-Type: {content_type}")
        logger.info(f"Raw request body type: {type(request_body)}")
        logger.info(f"Raw request body keys: {list(request_body.keys()) if isinstance(request_body, dict) else 'not a dict'}")

        # Extract values from request body
        test_client_id = None
        test_client_secret = None

        # Get client_id from request body
        if isinstance(request_body, dict) and "client_id" in request_body:
            client_id_value = request_body.get("client_id")
            logger.info(f"Raw client_id from request: type={type(client_id_value)}, value={'None' if client_id_value is None else ('empty' if client_id_value == '' else client_id_value[:30] + '...')}")
            if client_id_value is not None:
                if isinstance(client_id_value, str):
                    client_id_trimmed = client_id_value.strip()
                    if client_id_trimmed:
                        test_client_id = client_id_trimmed
                        logger.info(f"Extracted client_id from request body: {test_client_id[:30]}... (length: {len(test_client_id)})")
                else:
                    test_client_id = str(client_id_value).strip()
                    logger.info(f"Extracted client_id from request body (converted to string): {test_client_id[:30]}...")

        # Get client_secret from request body
        if isinstance(request_body, dict) and "client_secret" in request_body:
            client_secret_value = request_body.get("client_secret")
            logger.info(f"Raw client_secret from request: type={type(client_secret_value)}, present={client_secret_value is not None and client_secret_value != ''}")
            if client_secret_value is not None:
                if isinstance(client_secret_value, str):
                    client_secret_trimmed = client_secret_value.strip()
                    if client_secret_trimmed:
                        test_client_secret = client_secret_trimmed
                        logger.info(f"Extracted client_secret from request body (masked, length: {len(test_client_secret)})")
                else:
                    test_client_secret = str(client_secret_value).strip()
                    logger.info(f"Extracted client_secret from request body (converted to string, masked)")

        logger.info(f"After processing - client_id: {'present (length: ' + str(len(test_client_id)) + ')' if test_client_id else 'missing'}, client_secret: {'present' if test_client_secret else 'missing'}")

        # Fall back to database if not provided
        if not test_client_id:
            client_id_setting = settings_store.get_setting("google_oauth_client_id")
            test_client_id = str(client_id_setting.value) if client_id_setting and client_id_setting.value else None
            logger.info(f"Loaded client_id from database: {'present' if test_client_id else 'missing'}")

        if not test_client_secret:
            client_secret_setting = settings_store.get_setting("google_oauth_client_secret")
            test_client_secret = str(client_secret_setting.value) if client_secret_setting and client_secret_setting.value else None
            logger.info(f"Loaded client_secret from database: {'present' if test_client_secret else 'missing'}")

        errors = []
        warnings = []

        logger.info(f"Validating - test_client_id: {'present' if test_client_id else 'None'}, test_client_secret: {'present' if test_client_secret else 'None'}")

        if not test_client_id:
            errors.append("Client ID is required")
        else:
            test_client_id = test_client_id.strip()
            if not test_client_id:
                errors.append("Client ID cannot be empty")
            elif not test_client_id.endswith(".apps.googleusercontent.com"):
                warnings.append("Client ID should end with .apps.googleusercontent.com")

        if not test_client_secret:
            errors.append("Client Secret is required")
        else:
            test_client_secret = test_client_secret.strip()
            if not test_client_secret:
                errors.append("Client Secret cannot be empty")
            elif len(test_client_secret) < 10:
                warnings.append("Client Secret seems too short")

        if errors:
            return {
                "success": False,
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "message": "Configuration validation failed"
            }

        return {
            "success": True,
            "valid": True,
            "warnings": warnings,
            "message": "Configuration format is valid. This only validates format, not actual credentials.",
            "tested_at": _utc_now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to test Google OAuth config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to test Google OAuth config: {str(e)}")
