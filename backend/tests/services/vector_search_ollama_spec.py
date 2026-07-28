import httpx
import pytest

from backend.app.services import vector_search_ollama
from backend.app.services.vector_search_ollama import OllamaEmbeddingClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, *, outcomes, calls, timeout=None):
        self.outcomes = outcomes
        self.calls = calls
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url):
        self.calls.append(("GET", url, None))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def post(self, url, json):
        self.calls.append(("POST", url, json))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def install_fake_client(monkeypatch, outcomes):
    calls = []

    def factory(*, timeout=None):
        return FakeAsyncClient(
            outcomes=outcomes,
            calls=calls,
            timeout=timeout,
        )

    monkeypatch.setattr(vector_search_ollama.httpx, "AsyncClient", factory)
    return calls


@pytest.mark.asyncio
async def test_embed_uses_canonical_endpoint_and_response_shape(
    monkeypatch,
):
    monkeypatch.setenv("OLLAMA_HOST", "http://provider:11434/")
    calls = install_fake_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "model": "bge-m3:latest",
                    "embeddings": [[0.1, 0.2, 0.3]],
                }
            )
        ],
    )

    outcome = await OllamaEmbeddingClient().embed(
        "hello",
        model="bge-m3",
        is_query=False,
    )

    assert outcome.ok is True
    assert outcome.dimension == 3
    assert outcome.model == "bge-m3:latest"
    assert calls == [
        (
            "POST",
            "http://provider:11434/api/embed",
            {"model": "bge-m3", "input": "hello"},
        )
    ]


@pytest.mark.asyncio
async def test_nomic_prefix_is_owned_by_provider_leaf(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://provider:11434")
    calls = install_fake_client(
        monkeypatch,
        [FakeResponse(payload={"embeddings": [[0.4, 0.5]]})],
    )

    outcome = await OllamaEmbeddingClient().embed(
        "sleep consistency",
        model="nomic-embed-text:latest",
        is_query=True,
    )

    assert outcome.ok is True
    assert calls[0][2]["input"] == "search_query: sleep consistency"


@pytest.mark.asyncio
async def test_connect_failure_uses_next_unique_endpoint(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://first:11434")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://second:11434")
    request = httpx.Request("POST", "http://first:11434/api/embed")
    calls = install_fake_client(
        monkeypatch,
        [
            httpx.ConnectError("unavailable", request=request),
            FakeResponse(payload={"embeddings": [[0.6, 0.7]]}),
        ],
    )

    outcome = await OllamaEmbeddingClient().embed(
        "hello",
        model="bge-m3",
        is_query=False,
    )

    assert outcome.ok is True
    assert [call[1] for call in calls] == [
        "http://first:11434/api/embed",
        "http://second:11434/api/embed",
    ]


@pytest.mark.asyncio
async def test_read_timeout_is_typed_and_never_retried(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://first:11434")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://second:11434")
    request = httpx.Request("POST", "http://first:11434/api/embed")
    calls = install_fake_client(
        monkeypatch,
        [httpx.ReadTimeout("late", request=request)],
    )

    outcome = await OllamaEmbeddingClient().embed(
        "hello",
        model="bge-m3",
        is_query=False,
    )

    assert outcome.ok is False
    assert outcome.error_code == "read_timeout"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_invalid_embedding_shape_fails_closed(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://provider:11434")
    install_fake_client(
        monkeypatch,
        [FakeResponse(payload={"embeddings": []})],
    )

    outcome = await OllamaEmbeddingClient().embed(
        "hello",
        model="bge-m3",
        is_query=False,
    )

    assert outcome.ok is False
    assert outcome.error_code == "invalid_embedding_shape"


@pytest.mark.asyncio
async def test_model_selection_prefers_installed_bge(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://provider:11434")
    install_fake_client(
        monkeypatch,
        [
            FakeResponse(
                payload={
                    "models": [
                        {"name": "nomic-embed-text:latest"},
                        {"name": "bge-m3:latest"},
                    ]
                }
            )
        ],
    )

    model = await OllamaEmbeddingClient().select_embedding_model()

    assert model == "bge-m3"
