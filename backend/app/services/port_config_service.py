"""
Port Configuration Service

Unified interface for port configuration management.
"""

import os
import json
import logging
from typing import Optional, Dict, Tuple, List
from ..models.port_config import PortConfig, ServiceURLConfig, HostConfig
from .system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)

# Global settings store instance
settings_store = SystemSettingsStore()


class PortConfigService:
    """Port configuration service."""

    # Default port configuration
    DEFAULT_PORTS = {
        "backend_api": 8200,
        "frontend": 8300,
        "ocr_service": 8400,
        "postgres": 5440,
        "cloud_api": 8500,
        "cloud_provider_api": 8102,
        "media_proxy": 8202,
    }

    # Environment variable mapping (backward compatible)
    ENV_VAR_MAPPING = {
        "backend_api": "BACKEND_PORT",
        "frontend": "FRONTEND_PORT",
        "ocr_service": "OCR_PORT",
        "postgres": "POSTGRES_PORT",
        "cloud_api": "CLOUD_API_PORT",
        "cloud_provider_api": "CLOUD_PROVIDER_API_PORT",
        "media_proxy": "MEDIA_PROXY_PORT",
    }

    def __init__(self):
        self._config_cache: Optional[PortConfig] = None
        self._cache_key: Optional[str] = None

    def get_port_config(
        self,
        cluster: Optional[str] = None,
        environment: Optional[str] = None,
        site: Optional[str] = None,
        force_reload: bool = False,
    ) -> PortConfig:
        """
        Get port configuration with cluster/environment/site scoping.

        Resolution priority (most specific to most general):
        1. System settings (system.ports.{cluster}.{env}.{site}.*) - cluster+env+site
        2. System settings (system.ports.{cluster}.{env}.*) - cluster+env
        3. System settings (system.ports.{cluster}.{site}.*) - cluster+site (skip env)
        4. System settings (system.ports.{cluster}.*) - cluster only
        5. System settings (system.ports.{env}.{site}.*) - env+site (no cluster)
        6. System settings (system.ports.{env}.*) - env only (no cluster)
        7. System settings (system.ports.{site}.*) - site only (no cluster/env)
        8. System settings (system.ports.*) - global default
        9. Environment variables (BACKEND_PORT, etc.)
        10. Default values (DEFAULT_PORTS)

        Args:
            cluster: Cluster identifier
            environment: Environment identifier
            site: Site identifier
            force_reload: Force reload from storage
        """
        config_dict = {}

        # Build cache key from actual query values for consistency
        cache_key = f"{cluster}:{environment}:{site}"
        if self._config_cache and not force_reload and cache_key == self._cache_key:
            return self._config_cache

        for key, default_port in self.DEFAULT_PORTS.items():
            port_value = None

            # 1. Try scoped system settings (most specific to most general)
            setting_keys = []

            # Most specific: cluster + environment + site
            if cluster and environment and site:
                setting_keys.append(
                    f"system.ports.{cluster}.{environment}.{site}.{key}"
                )

            # cluster + environment
            if cluster and environment:
                setting_keys.append(f"system.ports.{cluster}.{environment}.{key}")

            # cluster + site (skip environment)
            if cluster and site:
                setting_keys.append(f"system.ports.{cluster}.{site}.{key}")

            # cluster only
            if cluster:
                setting_keys.append(f"system.ports.{cluster}.{key}")

            # environment + site (no cluster)
            if environment and site and not cluster:
                setting_keys.append(f"system.ports.{environment}.{site}.{key}")

            # environment only (no cluster)
            if environment and not cluster:
                setting_keys.append(f"system.ports.{environment}.{key}")

            # site only (no cluster or environment)
            if site and not cluster and not environment:
                setting_keys.append(f"system.ports.{site}.{key}")

            # Global default
            setting_keys.append(f"system.ports.{key}")

            for setting_key in setting_keys:
                setting = settings_store.get_setting(setting_key)
                if setting and setting.value is not None:
                    try:
                        port_value = int(setting.value)
                        logger.debug(
                            f"Port config from system settings: {setting_key} = {port_value}"
                        )
                        break
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Invalid port value in system settings: {setting_key} = {setting.value}"
                        )

            # 2. Fall back to environment variables
            if port_value is None:
                env_var = self.ENV_VAR_MAPPING.get(key)
                if env_var:
                    env_value = os.getenv(env_var)
                    if env_value:
                        try:
                            port_value = int(env_value)
                            logger.debug(
                                f"Port config from env var: {env_var} = {port_value}"
                            )
                        except (ValueError, TypeError):
                            logger.warning(
                                f"Invalid port value in env var: {env_var} = {env_value}"
                            )

            # 3. Use default value
            config_dict[key] = port_value if port_value is not None else default_port
            if port_value is None:
                logger.debug(f"Using default port config: {key} = {default_port}")

        # Attach scope info (preserve original passed values, no defaults)
        config_dict["cluster"] = cluster
        config_dict["environment"] = environment
        config_dict["site"] = site

        self._config_cache = PortConfig(**config_dict)
        self._cache_key = cache_key
        return self._config_cache

    def validate_port_conflict(self, config: PortConfig) -> Tuple[bool, List[str]]:
        """
        Validate port conflicts.

        Returns:
            (is_valid, conflict_messages)
        """
        import socket

        conflicts = []

        # Check for duplicate ports
        port_values = {
            "backend_api": config.backend_api,
            "frontend": config.frontend,
            "ocr_service": config.ocr_service,
            "postgres": config.postgres,
        }
        if config.cloud_api:
            port_values["cloud_api"] = config.cloud_api
        if config.cloud_provider_api:
            port_values["cloud_provider_api"] = config.cloud_provider_api
        if getattr(config, "media_proxy", None):
            port_values["media_proxy"] = config.media_proxy

        # Check internal port duplicates
        seen_ports = {}
        for service, port in port_values.items():
            if port in seen_ports:
                conflicts.append(
                    f"Port {port} is used by both {seen_ports[port]} and {service}"
                )
            else:
                seen_ports[port] = service

        # Check if ports are already in use (optional, requires permissions)
        try:
            for service, port in port_values.items():
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()
                if result == 0:
                    conflicts.append(f"Port {port} ({service}) is already in use")
        except Exception as e:
            logger.warning(
                f"Port availability check failed (may require permissions): {e}"
            )

        return len(conflicts) == 0, conflicts

    def update_port_config(self, config: PortConfig) -> Tuple[bool, Optional[str]]:
        """
        Update port configuration.

        Saves configuration to system settings and returns whether services need restart.

        Returns:
            (success, restart_message)
        """
        try:
            # Validate port conflicts
            is_valid, conflicts = self.validate_port_conflict(config)
            if not is_valid:
                error_msg = "Port configuration conflict:\n" + "\n".join(conflicts)
                logger.error(error_msg)
                return False, error_msg

            # Build scope prefix (supports independent environment and site scoping)
            scope_parts = []
            if config.cluster:
                scope_parts.append(config.cluster)
            if config.environment:
                scope_parts.append(config.environment)
            if config.site:
                scope_parts.append(config.site)

            scope_prefix = ".".join(scope_parts) + "." if scope_parts else ""

            # Prepare update dictionary
            updates = {}
            for key, value in config.dict(exclude_none=True).items():
                # Skip scope fields
                if key in ["cluster", "environment", "site"]:
                    continue

                setting_key = f"system.ports.{scope_prefix}{key}"
                updates[setting_key] = str(value)

            # Batch update settings
            settings_store.update_settings(updates)

            # Clear cache
            self._config_cache = None
            self._cache_key = None

            logger.info(f"Port config updated: {config.dict()}")

            # Build restart notification
            restart_services = []
            if config.backend_api:
                restart_services.append("Backend API")
            if config.frontend:
                restart_services.append("Frontend Web Console")
            if config.ocr_service:
                restart_services.append("OCR Service")
            if config.postgres:
                restart_services.append(
                    "PostgreSQL (connection string update required)"
                )

            restart_message = f"Port config saved. Services requiring restart: {', '.join(restart_services)}"
            return True, restart_message
        except Exception as e:
            logger.error(f"Failed to update port config: {e}", exc_info=True)
            return False, str(e)

    def get_host_config(self) -> HostConfig:
        """
        Get hostname configuration.

        Resolution priority:
        1. System settings (system.hosts.*)
        2. Environment variables (BACKEND_HOST, etc.)
        3. Default value (localhost)
        """
        host_dict = {}

        # Read hostname config from system settings
        host_keys = {
            "backend_api_host": "backend_api",
            "frontend_host": "frontend",
            "ocr_service_host": "ocr_service",
            "cloud_api_host": "cloud_api",
            "cloud_provider_api_host": "cloud_provider_api",
        }

        for host_key, service_key in host_keys.items():
            setting_key = f"system.hosts.{service_key}"
            setting = settings_store.get_setting(setting_key)
            if setting and setting.value:
                host_dict[host_key] = setting.value
            else:
                # Fall back to environment variable
                env_var = f"{service_key.upper()}_HOST"
                env_value = os.getenv(env_var)
                host_dict[host_key] = env_value if env_value else "localhost"

        # Read CORS configuration
        cors_setting = settings_store.get_setting("system.cors.origins")
        if cors_setting and cors_setting.value:
            try:
                host_dict["cors_origins"] = json.loads(cors_setting.value)
            except:
                host_dict["cors_origins"] = []
        else:
            host_dict["cors_origins"] = []

        return HostConfig(**host_dict)

    def get_service_url(
        self,
        service: str,
        cluster: Optional[str] = None,
        environment: Optional[str] = None,
        site: Optional[str] = None,
        protocol: str = "http",
    ) -> str:
        """
        Get service URL (auto-resolves hostname and port from config with scoping).

        Args:
            service: Service name (backend_api, frontend, ocr_service, cloud_api, cloud_provider_api)
            cluster: Cluster identifier (optional)
            environment: Environment identifier (optional)
            site: Site identifier (optional)
            protocol: Protocol (default: http)
        """
        # Get port config with scope parameters
        config = self.get_port_config(
            cluster=cluster, environment=environment, site=site
        )
        port = getattr(config, service, None)

        if port is None:
            raise ValueError(f"Unknown service: {service}")

        # Resolve hostname from config
        host_config = self.get_host_config()
        host_key = f"{service}_host"
        host = getattr(host_config, host_key, "localhost")

        return f"{protocol}://{host}:{port}"

    def get_all_service_urls(
        self,
        cluster: Optional[str] = None,
        environment: Optional[str] = None,
        site: Optional[str] = None,
        protocol: str = "http",
    ) -> ServiceURLConfig:
        """
        Get all service URLs (auto-resolves hostnames from config).

        Args:
            cluster: Cluster identifier
            environment: Environment identifier
            site: Site identifier
            protocol: Protocol (default: http)
        """
        config = self.get_port_config(
            cluster=cluster, environment=environment, site=site
        )
        host_config = self.get_host_config()

        return ServiceURLConfig(
            backend_api_url=f"{protocol}://{host_config.backend_api_host}:{config.backend_api}",
            frontend_url=f"{protocol}://{host_config.frontend_host}:{config.frontend}",
            ocr_service_url=f"{protocol}://{host_config.ocr_service_host}:{config.ocr_service}",
            cloud_api_url=(
                f"{protocol}://{host_config.cloud_api_host}:{config.cloud_api}"
                if config.cloud_api and host_config.cloud_api_host
                else None
            ),
            cloud_provider_api_url=(
                f"{protocol}://{host_config.cloud_provider_api_host}:{config.cloud_provider_api}"
                if config.cloud_provider_api and host_config.cloud_provider_api_host
                else None
            ),
        )


# Global singleton
port_config_service = PortConfigService()
