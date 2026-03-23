from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.features.mindscape.routes_core.intent_logs import (
    annotate_intent_log_record,
    get_intent_log_payload,
    list_intent_logs_payload,
)
from backend.features.mindscape.routes_core.intent_playbooks import (
    remove_intent_playbook_payload,
)
from backend.features.mindscape.routes_core.onboarding_profile import (
    get_onboarding_status_payload,
)
from backend.features.mindscape.routes_core.schemas import AnnotateIntentLogRequest
from backend.features.mindscape.routes_core.timeline_entities import (
    list_entities_payload,
    untag_entity_record,
)


def test_get_onboarding_status_payload_aggregates_service_state():
    onboarding_service = SimpleNamespace(
        get_onboarding_status=lambda user_id: {"user_id": user_id, "task1": True},
        get_completion_count=lambda user_id: 2,
        is_onboarding_complete=lambda user_id: False,
    )

    payload = get_onboarding_status_payload(
        onboarding_service=onboarding_service,
        user_id="user-1",
    )

    assert payload["onboarding_state"]["task1"] is True
    assert payload["completed_count"] == 2
    assert payload["is_complete"] is False


def test_list_intent_logs_payload_parses_iso_filters():
    captured = {}

    store = SimpleNamespace(
        list_intent_logs=lambda **kwargs: captured.setdefault("kwargs", kwargs) or ["ok"]
    )

    result = list_intent_logs_payload(
        store=store,
        profile_id="user-1",
        start_time="2026-03-24T10:00:00",
        end_time="2026-03-24T12:00:00",
        has_override=True,
        limit=5,
    )

    assert result == captured["kwargs"]
    assert captured["kwargs"]["profile_id"] == "user-1"
    assert captured["kwargs"]["has_override"] is True
    assert captured["kwargs"]["limit"] == 5
    assert captured["kwargs"]["start_time"] == datetime(2026, 3, 24, 10, 0, 0)
    assert captured["kwargs"]["end_time"] == datetime(2026, 3, 24, 12, 0, 0)


def test_get_intent_log_payload_raises_for_missing_log():
    store = SimpleNamespace(get_intent_log=lambda log_id: None)

    with pytest.raises(HTTPException) as exc_info:
        get_intent_log_payload(store=store, log_id="missing")

    assert exc_info.value.detail == "Intent log not found"


def test_annotate_intent_log_record_builds_override_dict():
    captured = {}
    expected = {"id": "log-1", "notes": "keep"}

    def _update(log_id, user_override):
        captured["log_id"] = log_id
        captured["user_override"] = user_override
        return expected

    store = SimpleNamespace(update_intent_log_override=_update)
    request = AnnotateIntentLogRequest(
        correct_interaction_type="chat",
        correct_task_domain="analysis",
        notes="keep",
    )

    result = annotate_intent_log_record(
        store=store,
        log_id="log-1",
        request=request,
    )

    assert result == expected
    assert captured["log_id"] == "log-1"
    assert captured["user_override"] == {
        "correct_interaction_type": "chat",
        "correct_task_domain": "analysis",
        "notes": "keep",
    }


def test_list_entities_payload_attaches_entity_tags():
    entity = SimpleNamespace(
        id="entity-1",
        dict=lambda: {"id": "entity-1", "name": "Entity"},
    )
    tag = SimpleNamespace(dict=lambda: {"id": "tag-1", "name": "Important"})
    store = SimpleNamespace(
        list_entities=lambda **kwargs: [entity],
        get_tags_by_entity=lambda entity_id: [tag],
    )

    payload = list_entities_payload(
        store=store,
        profile_id="user-1",
        entity_type=None,
        limit=10,
    )

    assert payload == [
        {
            "id": "entity-1",
            "name": "Entity",
            "tags": [{"id": "tag-1", "name": "Important"}],
        }
    ]


def test_untag_entity_record_raises_for_missing_association():
    store = SimpleNamespace(untag_entity=lambda entity_id, tag_id: False)

    with pytest.raises(HTTPException) as exc_info:
        untag_entity_record(store=store, entity_id="entity-1", tag_id="tag-1")

    assert exc_info.value.detail == "Entity-tag association not found"


def test_remove_intent_playbook_payload_raises_for_missing_association(monkeypatch):
    class _PlaybookService:
        def __init__(self, store):
            self.playbook_store = SimpleNamespace(
                remove_intent_playbook_association=lambda intent_id, playbook_code: False
            )

    monkeypatch.setattr(
        "backend.app.services.playbook_service.PlaybookService",
        _PlaybookService,
    )

    with pytest.raises(HTTPException) as exc_info:
        remove_intent_playbook_payload(
            store=SimpleNamespace(),
            intent_id="intent-1",
            playbook_code="demo",
        )

    assert exc_info.value.detail == "Association not found"
