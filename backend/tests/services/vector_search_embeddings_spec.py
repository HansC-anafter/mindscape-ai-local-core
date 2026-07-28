import pytest

from backend.app.services.vector_search_embeddings import (
    VectorEmbeddingGenerator,
)
from backend.app.services.vector_search_ollama import (
    OllamaEmbeddingOutcome,
)


class FakeOllamaClient:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def select_embedding_model(self, preferred=""):
        self.calls.append(("select", preferred))
        return preferred or "bge-m3"

    async def embed(self, text, *, model, is_query):
        self.calls.append(("embed", text, model, is_query))
        return self.outcome

    def get_reachable_base_url(self):
        return "http://provider:11434"


@pytest.mark.asyncio
async def test_generator_preserves_existing_tuple_contract(monkeypatch):
    monkeypatch.delenv("OLLAMA_EMBED_MODEL", raising=False)
    client = FakeOllamaClient(
        OllamaEmbeddingOutcome(
            embedding=(0.1, 0.2),
            model="bge-m3:latest",
            base_url="http://provider:11434",
        )
    )
    generator = VectorEmbeddingGenerator(ollama_client=client)

    embedding, model = await generator.generate_embedding_with_model(
        "hello",
        is_query=False,
    )

    assert embedding == [0.1, 0.2]
    assert model == "bge-m3"
    assert client.calls == [
        ("select", ""),
        ("embed", "hello", "bge-m3", False),
    ]


@pytest.mark.asyncio
async def test_provider_probe_never_contains_embedding(monkeypatch):
    monkeypatch.delenv("OLLAMA_EMBED_MODEL", raising=False)
    generator = VectorEmbeddingGenerator(
        ollama_client=FakeOllamaClient(
            OllamaEmbeddingOutcome(
                embedding=(0.1, 0.2, 0.3),
                model="bge-m3:latest",
                base_url="http://provider:11434",
            )
        )
    )

    receipt = await generator.probe_embedding_provider("admission")

    assert receipt["ok"] is True
    assert receipt["provider"] == "ollama"
    assert receipt["model"] == "bge-m3"
    assert receipt["dimension"] == 3
    assert "embedding" not in receipt


@pytest.mark.asyncio
async def test_openai_fallback_is_preserved(monkeypatch):
    generator = VectorEmbeddingGenerator(
        ollama_client=FakeOllamaClient(
            OllamaEmbeddingOutcome(
                model="bge-m3",
                error_code="read_timeout",
                error_detail="ReadTimeout",
            )
        )
    )

    async def fake_openai(_text):
        return [0.8, 0.9]

    monkeypatch.setattr(
        generator,
        "generate_openai_embedding",
        fake_openai,
    )
    monkeypatch.setattr(
        generator,
        "_configured_openai_model_name",
        lambda: "text-embedding-3-small",
    )

    receipt = await generator.generate_embedding_receipt("hello")

    assert receipt is not None
    assert receipt.provider == "openai"
    assert receipt.model == "text-embedding-3-small"
    assert receipt.dimension == 2


@pytest.mark.asyncio
async def test_provider_probe_fails_closed_without_vector(monkeypatch):
    generator = VectorEmbeddingGenerator(
        ollama_client=FakeOllamaClient(
            OllamaEmbeddingOutcome(
                model="bge-m3",
                error_code="connect_unavailable",
                error_detail="ConnectError",
            )
        )
    )

    async def no_openai(_text):
        raise AssertionError("provider_probe_must_not_touch_openai_or_config_db")

    monkeypatch.setattr(
        generator,
        "generate_openai_embedding",
        no_openai,
    )

    receipt = await generator.probe_embedding_provider()

    assert receipt["ok"] is False
    assert receipt["error_code"] == "embedding_provider_unavailable"
    assert receipt["dimension"] == 0
    assert "embedding" not in receipt


def test_sync_url_wrapper_delegates_to_provider_leaf():
    generator = VectorEmbeddingGenerator(
        ollama_client=FakeOllamaClient(
            OllamaEmbeddingOutcome()
        )
    )

    assert generator.get_ollama_url() == "http://provider:11434"
