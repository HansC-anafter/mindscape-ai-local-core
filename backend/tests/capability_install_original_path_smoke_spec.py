from io import BytesIO

from backend.app.routes.core.capability_install_core.install_commit_core import (
    original_path_smoke,
)


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return b'{"status":"ok"}'


def test_original_path_smoke_is_bounded_and_uses_configured_url(monkeypatch):
    captured = {}
    monkeypatch.setenv(
        "MINDSCAPE_INSTALL_ORIGINAL_PATH_SMOKE_URL",
        "http://127.0.0.1:8300/healthz",
    )
    monkeypatch.setattr(
        original_path_smoke.urllib.request,
        "urlopen",
        lambda request, timeout: captured.update(
            {"url": request.full_url, "timeout": timeout}
        ) or _Response(),
    )

    receipt = original_path_smoke.verify_original_path_smoke()

    assert captured == {"url": "http://127.0.0.1:8300/healthz", "timeout": 5.0}
    assert receipt.status == 200
