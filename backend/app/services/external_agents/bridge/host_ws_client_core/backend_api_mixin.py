from .base import *


class HostBridgeBackendApiMixin:

    @property
    def backend_api_url(self) -> str:
        backend_url = os.environ.get("MINDSCAPE_BACKEND_API_URL", "").strip()
        if backend_url:
            return backend_url.rstrip("/")
        return _default_backend_api_url(self.host)

    @property
    def backend_api_urls(self) -> List[str]:
        return _backend_api_url_candidates(self.backend_api_url)

    def _backend_request_sync(
        self,
        build_request: Callable[[str], urllib.request.Request],
        *,
        timeout: float,
    ) -> tuple[str, str]:
        last_exc: Optional[BaseException] = None
        for backend_url in self.backend_api_urls:
            try:
                req = build_request(backend_url)
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    body = response.read().decode("utf-8")
                return backend_url, body
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("MINDSCAPE_BACKEND_API_URL is not configured")
