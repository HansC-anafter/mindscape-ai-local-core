from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.http import HttpClient
from remote_workbench_authorization_cutover.io import CutoverError


class FakeResponse:
    status = 200
    headers: dict[str, str] = {}

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self.body[:size]


class FakeOpener:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def open(self, *_args, **_kwargs) -> FakeResponse:
        return self.response


def test_http_client_fails_closed_when_response_exceeds_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *_args: FakeOpener(FakeResponse(b"123456789")),
    )

    with pytest.raises(CutoverError, match="exceeded"):
        HttpClient().request("GET", "https://example.invalid", max_response_bytes=8)


def test_http_client_reads_exact_bound_without_unbounded_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *_args: FakeOpener(FakeResponse(b"12345678")),
    )

    response = HttpClient().request(
        "GET",
        "https://example.invalid",
        max_response_bytes=8,
    )
    assert response.body == b"12345678"
