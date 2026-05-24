"""Shared service endpoint registry."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from backend.app.models.service_endpoint import (
    EndpointAudience,
    RuntimeServiceEndpointSnapshot,
    ServiceEndpoint,
    ServiceEndpointSnapshot,
)


SEED_FILENAME = "service-endpoints.seed.json"


def _default_seed_candidates() -> List[Path]:
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        Path("/app/config") / SEED_FILENAME,
        repo_root / "config" / SEED_FILENAME,
        Path.cwd() / "config" / SEED_FILENAME,
    ]
    configured_path = os.getenv("MINDSCAPE_SERVICE_ENDPOINT_SEED")
    if configured_path:
        candidates.insert(0, Path(configured_path))
    return candidates


def _first_existing_seed_path() -> Path:
    for candidate in _default_seed_candidates():
        if str(candidate) and candidate.is_file():
            return candidate
    return Path("/app/config") / SEED_FILENAME


def _setting_key(service_id: str, audience: str) -> str:
    return f"system.service_endpoints.{service_id}.{audience}.url"


def _env_key(service_id: str, audience: str) -> str:
    raw = f"{service_id}_{audience}_url"
    return raw.upper().replace(".", "_").replace("-", "_")


def _port_from_url(url: str) -> Optional[int]:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.port


class ServiceEndpointRegistry:
    """Resolve endpoint URLs from seed, environment, and settings overrides."""

    def __init__(self, seed_path: Optional[Path] = None, settings_store: Any = None):
        self.seed_path = seed_path
        self._settings_store = settings_store

    @property
    def settings_store(self) -> Any:
        """Resolve the settings store lazily to keep imports test-friendly."""
        if self._settings_store is None:
            from backend.app.services.system_settings_store import SystemSettingsStore

            self._settings_store = SystemSettingsStore()
        return self._settings_store

    def _load_seed(self) -> ServiceEndpointSnapshot:
        path = self.seed_path or _first_existing_seed_path()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ServiceEndpointSnapshot(**payload)

    def _iter_overridden_endpoints(
        self, endpoints: Iterable[ServiceEndpoint]
    ) -> List[ServiceEndpoint]:
        resolved: List[ServiceEndpoint] = []
        for endpoint in endpoints:
            data = endpoint.model_dump()
            env_value = os.getenv(_env_key(endpoint.service_id, endpoint.audience))
            if env_value is not None:
                data["url"] = env_value
                data["source"] = "env"
                resolved.append(ServiceEndpoint(**data))
                continue

            try:
                setting = self.settings_store.get_setting(
                    _setting_key(endpoint.service_id, endpoint.audience)
                )
            except Exception:
                setting = None

            if setting and getattr(setting, "value", None) is not None:
                data["url"] = str(setting.value)
                data["source"] = "settings"
            resolved.append(ServiceEndpoint(**data))
        return resolved

    def get_snapshot(self) -> ServiceEndpointSnapshot:
        """Return the current endpoint registry snapshot."""
        seed = self._load_seed()
        return ServiceEndpointSnapshot(
            version=seed.version,
            endpoints=self._iter_overridden_endpoints(seed.endpoints),
        )

    def list_service_endpoints(self, service_id: str) -> List[ServiceEndpoint]:
        """Return all endpoints for one service id."""
        return [
            endpoint
            for endpoint in self.get_snapshot().endpoints
            if endpoint.service_id == service_id
        ]

    def get_endpoint(
        self, service_id: str, audience: EndpointAudience | str
    ) -> Optional[ServiceEndpoint]:
        """Return one endpoint for a service id and audience."""
        audience_value = audience.value if isinstance(audience, EndpointAudience) else audience
        for endpoint in self.get_snapshot().endpoints:
            if endpoint.service_id == service_id and endpoint.audience == audience_value:
                return endpoint
        return None

    def get_endpoint_url(
        self,
        service_id: str,
        audience: EndpointAudience | str,
        default: Optional[str] = None,
    ) -> Optional[str]:
        """Return a URL for a service id and audience."""
        endpoint = self.get_endpoint(service_id, audience)
        if endpoint is None:
            return default
        return endpoint.url

    def update_endpoint_url(
        self, service_id: str, audience: EndpointAudience | str, url: str
    ) -> ServiceEndpoint:
        """Persist an endpoint URL override in system settings."""
        audience_value = audience.value if isinstance(audience, EndpointAudience) else audience
        current = self.get_endpoint(service_id, audience_value)
        if current is None:
            raise KeyError(f"Unknown service endpoint: {service_id}/{audience_value}")

        self.settings_store.update_settings({_setting_key(service_id, audience_value): url})
        data = current.model_dump()
        data["url"] = url
        data["source"] = "settings"
        return ServiceEndpoint(**data)

    def get_port_projection(self) -> Dict[str, int]:
        """Project registry endpoints into the legacy port contract."""
        mappings = {
            "backend_api": ("local_core.execution_api", EndpointAudience.HOST_PUBLIC),
            "frontend": ("local_core.web_console", EndpointAudience.BROWSER_PUBLIC),
            "ocr_service": ("ocr.service", EndpointAudience.HOST_PUBLIC),
            "postgres": ("local_core.postgres_pool", EndpointAudience.HOST_PUBLIC),
            "cloud_api": ("cloud.api", EndpointAudience.HOST_PUBLIC),
            "cloud_provider_api": ("cloud.provider_api", EndpointAudience.HOST_PUBLIC),
            "media_proxy": ("local_core.media_proxy", EndpointAudience.HOST_PUBLIC),
        }
        projection: Dict[str, int] = {}
        for key, (service_id, audience) in mappings.items():
            url = self.get_endpoint_url(service_id, audience)
            port = _port_from_url(url or "")
            if port is not None:
                projection[key] = port
        return projection

    def get_legacy_service_url_projection(self) -> Dict[str, Optional[str]]:
        """Project registry endpoints into the legacy service URL contract."""
        return {
            "backend_api_url": self.get_endpoint_url(
                "local_core.execution_api", EndpointAudience.HOST_PUBLIC
            ),
            "frontend_url": self.get_endpoint_url(
                "local_core.web_console", EndpointAudience.BROWSER_PUBLIC
            ),
            "ocr_service_url": self.get_endpoint_url(
                "ocr.service", EndpointAudience.HOST_PUBLIC
            ),
            "cloud_api_url": self.get_endpoint_url(
                "cloud.api", EndpointAudience.HOST_PUBLIC
            ),
            "cloud_provider_api_url": self.get_endpoint_url(
                "cloud.provider_api", EndpointAudience.HOST_PUBLIC
            ),
            "media_proxy_url": self.get_endpoint_url(
                "local_core.media_proxy", EndpointAudience.HOST_PUBLIC
            ),
        }

    def get_runtime_context_snapshot(self) -> RuntimeServiceEndpointSnapshot:
        """Return the JSON-safe endpoint snapshot used by capability runtime context."""
        snapshot = self.get_snapshot()
        return RuntimeServiceEndpointSnapshot(
            version=snapshot.version,
            endpoints=[
                {
                    "service_id": endpoint.service_id,
                    "audience": str(endpoint.audience),
                    "url": endpoint.url,
                    "source": endpoint.source,
                }
                for endpoint in snapshot.endpoints
            ],
        )


def build_runtime_service_endpoint_context() -> Dict[str, Any]:
    """Build a JSON-safe runtime context fragment for capability tools."""
    snapshot = service_endpoint_registry.get_runtime_context_snapshot()
    return {"service_endpoints": snapshot.model_dump()}


def resolve_service_endpoint(
    runtime_context: Dict[str, Any],
    service_id: str,
    audience: str,
) -> Optional[str]:
    """Resolve an endpoint URL from a JSON-safe runtime context."""
    service_endpoints = runtime_context.get("service_endpoints")
    if not isinstance(service_endpoints, dict):
        return None
    endpoints = service_endpoints.get("endpoints")
    if not isinstance(endpoints, list):
        return None
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        if endpoint.get("service_id") == service_id and endpoint.get("audience") == audience:
            url = endpoint.get("url")
            return str(url) if url is not None else ""
    return None


service_endpoint_registry = ServiceEndpointRegistry()
