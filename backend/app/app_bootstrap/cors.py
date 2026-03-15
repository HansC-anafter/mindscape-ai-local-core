import os
import logging
import re

logger = logging.getLogger(__name__)

def get_cors_origins():
    """Get CORS allowed origins from port config service"""
    try:
        from backend.app.services.port_config_service import port_config_service

        # Get current scope from environment variables or config
        current_cluster = os.getenv("CLUSTER_NAME")
        current_env = os.getenv("ENVIRONMENT")
        current_site = os.getenv("SITE_NAME")

        # Get frontend URL (automatically read hostname and port from config)
        frontend_url = port_config_service.get_service_url(
            "frontend",
            cluster=current_cluster,
            environment=current_env,
            site=current_site,
        )
        port_config = port_config_service.get_port_config(
            cluster=current_cluster, environment=current_env, site=current_site
        )
        host_config = port_config_service.get_host_config()

        # Build CORS allowed origins (automatically read hostname from config)
        allow_origins = [frontend_url]

        # If frontend hostname is not localhost, also add 127.0.0.1 variant
        if "localhost" in frontend_url:
            allow_origins.append(frontend_url.replace("localhost", "127.0.0.1"))

        # Add Cloud API if configured
        if port_config.cloud_api and host_config.cloud_api_host:
            cloud_api_url = port_config_service.get_service_url(
                "cloud_api",
                cluster=current_cluster,
                environment=current_env,
                site=current_site,
            )
            allow_origins.append(cloud_api_url)
            if "localhost" in cloud_api_url:
                allow_origins.append(cloud_api_url.replace("localhost", "127.0.0.1"))

        # Add other origins from CORS config if configured
        if host_config.cors_origins:
            allow_origins.extend(host_config.cors_origins)

        return allow_origins
    except Exception as e:
        logger.warning(
            f"Failed to get CORS origins from port config service, using defaults: {e}"
        )
        # Fallback to default values (backward compatibility)
        return [
            "http://localhost:8300",  # New default frontend port
            "http://127.0.0.1:8300",
            "http://localhost:3000",  # Keep old port for compatibility
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ]

def get_cors_origin_regex() -> str:
    """Return strict regex for chrome extensions"""
    return r"^chrome-extension://.*$"

def resolve_error_cors_origin(request_origin: str) -> str:
    """Unifies checking logic for exception handlers"""
    allowed_origins = get_cors_origins()
    
    # Fast path exact origin match
    if request_origin in allowed_origins:
        return request_origin
        
    # Regex path for chrome extensions
    if request_origin and re.match(get_cors_origin_regex(), request_origin):
        return request_origin
        
    # Safe default
    return allowed_origins[0] if allowed_origins else "*"
