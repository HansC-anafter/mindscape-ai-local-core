from typing import Dict

async def _get_packs_catalog(provider, bundle: str = "default") -> Dict:
    """
    Get packs catalog from provider API

    Hard Rule: local-core backend calls provider API (not site-hub directly)
    Returns neutral Provider Contract format (actions[] instead of purchase_url)
    """
    import httpx

    api_url = provider.get_api_url() if hasattr(provider, 'get_api_url') else None
    api_key = provider.get_api_key() if hasattr(provider, 'get_api_key') else None

    if not api_url:
        raise ValueError("Provider API URL not configured")

    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{api_url}/api/v1/packs",
                params={"bundle": bundle},
                headers=headers
            )

            if response.status_code == 403:
                # Check if response contains neutral Provider Contract format
                try:
                    error_data = response.json()
                except Exception:
                    # If JSON parsing fails, return a default ACTION_REQUIRED response
                    return {
                        "state": "ACTION_REQUIRED",
                        "reason": "ENTITLEMENT_REQUIRED",
                        "actions": [],
                        "retry_after_sec": 5
                    }

                # FastAPI HTTPException wraps detail in {"detail": {...}}
                # Check if detail exists and extract it
                if "detail" in error_data and isinstance(error_data["detail"], dict):
                    error_data = error_data["detail"]

                # Support both old format (backward compatibility) and new format
                if error_data.get("state") == "ACTION_REQUIRED" or error_data.get("reason") == "ENTITLEMENT_REQUIRED" or error_data.get("error") == "ENTITLEMENT_REQUIRED":
                    # Convert old format to new format if needed
                    if "actions" in error_data:
                        return error_data  # Already in new format
                    elif "purchase_url" in error_data:
                        # Convert old format to new format
                        return {
                            "state": "ACTION_REQUIRED",
                            "reason": error_data.get("error") or error_data.get("reason", "ENTITLEMENT_REQUIRED"),
                            "actions": [
                                {
                                    "type": "BROWSER_AUTH",
                                    "label": "Login / Purchase",
                                    "rel": "purchase",
                                    "url": error_data.get("purchase_url"),
                                    "expires_at": None
                                }
                            ],
                            "retry_after_sec": 5
                        }
                    else:
                        return {
                            "state": "ACTION_REQUIRED",
                            "reason": error_data.get("error") or error_data.get("reason", "ENTITLEMENT_REQUIRED"),
                            "actions": error_data.get("actions", []),
                            "retry_after_sec": 5
                        }

            response.raise_for_status()
            catalog_data = response.json()

            # Site-Hub API returns {"packs": [...]} directly
            # Ensure we return a dict with "packs" key
            if isinstance(catalog_data, dict):
                # If it already has "packs" key, return as is
                if "packs" in catalog_data:
                    return catalog_data
                # If it's a list, wrap it
                elif isinstance(catalog_data, list):
                    return {"packs": catalog_data}
                else:
                    return {"packs": []}
            else:
                return {"packs": []}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                try:
                    error_data = e.response.json()
                except Exception:
                    return {
                        "state": "ACTION_REQUIRED",
                        "reason": "ENTITLEMENT_REQUIRED",
                        "actions": [],
                        "retry_after_sec": 5
                    }

                # FastAPI HTTPException wraps detail in {"detail": {...}}
                # Check if detail exists and extract it
                if "detail" in error_data and isinstance(error_data["detail"], dict):
                    error_data = error_data["detail"]

                # Convert old format to new format if needed
                if error_data.get("state") == "ACTION_REQUIRED" or error_data.get("reason") == "ENTITLEMENT_REQUIRED" or error_data.get("error") == "ENTITLEMENT_REQUIRED":
                    if "actions" in error_data:
                        return error_data
                    elif "purchase_url" in error_data:
                        return {
                            "state": "ACTION_REQUIRED",
                            "reason": error_data.get("error") or error_data.get("reason", "ENTITLEMENT_REQUIRED"),
                            "actions": [
                                {
                                    "type": "BROWSER_AUTH",
                                    "label": "Login / Purchase",
                                    "rel": "purchase",
                                    "url": error_data.get("purchase_url"),
                                    "expires_at": None
                                }
                            ],
                            "retry_after_sec": 5
                        }
                    else:
                        return {
                            "state": "ACTION_REQUIRED",
                            "reason": error_data.get("error") or error_data.get("reason", "ENTITLEMENT_REQUIRED"),
                            "actions": error_data.get("actions", []),
                            "retry_after_sec": 5
                        }
            raise
