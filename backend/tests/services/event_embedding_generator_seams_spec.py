from types import SimpleNamespace

import pytest

from backend.app.models.mindscape import EventActor, EventType
from backend.app.services.event_embedding_generator import EventEmbeddingGenerator
from backend.app.services.event_embedding_generator_core.storage import (
    build_embedding_storage_payload,
)


def _event(**overrides):
    values = {
        "id": "event_1",
        "event_type": EventType.MESSAGE,
        "payload": {"message": "hello"},
        "metadata": {"should_embed": True},
        "workspace_id": "workspace_1",
        "profile_id": "profile_1",
        "actor": EventActor.USER,
        "channel": "api",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_public_facade_preserves_class_and_method_names() -> None:
    generator = EventEmbeddingGenerator(store=object())
    expected_methods = (
        "should_generate_embedding",
        "generate_embedding_for_event",
        "_extract_text_from_event",
        "_check_existing_embedding",
        "_generate_embedding",
        "_generate_embedding_openai",
        "_generate_embedding_vertex_ai",
        "_store_embedding",
        "_map_event_type_to_seed_type",
    )

    missing = [name for name in expected_methods if not hasattr(generator, name)]

    assert missing == []


def test_eligibility_and_text_extraction_stay_pure() -> None:
    generator = EventEmbeddingGenerator(store=object())
    event = _event(
        event_type=EventType.EXECUTION_PLAN,
        payload={
            "summary": "Launch plan",
            "steps": [
                {"name": "Draft", "description": "write outline"},
                {"name": "Review"},
            ],
        },
        metadata={},
    )

    assert generator.should_generate_embedding(event) is True
    assert generator._extract_text_from_event(event) == (
        "Plan Summary: Launch plan\n\n"
        "Steps:\nStep 1: Draft - write outline\nStep 2: Review"
    )
    assert generator._map_event_type_to_seed_type(EventType.EXECUTION_PLAN) == "plan"


@pytest.mark.asyncio
async def test_generate_embedding_for_event_reuses_single_store_path() -> None:
    generator = EventEmbeddingGenerator(store=object())
    event = _event()
    calls = []

    generator._check_existing_embedding = lambda candidate: None

    async def fake_generate(text):
        calls.append(("generate", text))
        return [0.1, 0.2]

    def fake_store(candidate, text, embedding):
        calls.append(("store", candidate.id, text, embedding))
        return "seed_1"

    generator._generate_embedding = fake_generate
    generator._store_embedding = fake_store

    assert await generator.generate_embedding_for_event(event) == "seed_1"
    assert calls == [
        ("generate", "hello"),
        ("store", "event_1", "hello", [0.1, 0.2]),
    ]


@pytest.mark.asyncio
async def test_existing_embedding_short_circuits_provider_and_store() -> None:
    generator = EventEmbeddingGenerator(store=object())
    event = _event()

    generator._check_existing_embedding = lambda candidate: "seed_existing"

    async def fail_generate(text):
        raise AssertionError("provider should not be called")

    def fail_store(candidate, text, embedding):
        raise AssertionError("store should not be called")

    generator._generate_embedding = fail_generate
    generator._store_embedding = fail_store

    assert await generator.generate_embedding_for_event(event) == "seed_existing"


def test_storage_payload_preserves_memory_embedding_metadata_shape() -> None:
    payload = build_embedding_storage_payload(
        _event(
            event_type=EventType.INTENT_CREATED,
            payload={"id": "intent_1", "priority": "critical"},
            metadata={"tags": "urgent", "file_hash": "hash_1", "file_name": "brief.md"},
        ),
        [0.1, 0.2, 0.3],
        embedding_model_name="text-embedding-3-small",
        embedding_provider="openai",
    )

    assert payload["scope"] == "intent"
    assert payload["intent_id"] == "intent_1"
    assert payload["importance"] == 0.9
    assert payload["source_context"] == (
        "scope:intent|workspace:workspace_1|intent:intent_1"
    )
    assert payload["metadata"] == {
        "event_type": "intent_created",
        "actor": "user",
        "channel": "api",
        "source_id": "event_1",
        "embedding_model": "text-embedding-3-small",
        "embedding_provider": "openai",
        "embedding_dimension": 3,
        "scope": "intent",
        "workspace_id": "workspace_1",
        "intent_id": "intent_1",
        "importance": 0.9,
        "tags": ["urgent"],
        "seed_type": "intent",
        "file_hash": "hash_1",
        "file_name": "brief.md",
    }
