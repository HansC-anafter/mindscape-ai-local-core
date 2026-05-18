import pytest

from backend.app.services.read_models.keyset import CursorError, decode_cursor, encode_cursor


def _cursor(**overrides):
    payload = {
        "read_model_id": "demo_targets",
        "contract_version": 1,
        "sort_id": "score_desc",
        "filters": {"workspace_id": "ws-1"},
        "last_values": {"follower_count": 100, "handle": "demo"},
        "ttl_seconds": 900,
        "secret": "test-secret",
        "now": 1_000,
    }
    payload.update(overrides)
    return encode_cursor(**payload)


def test_keyset_cursor_round_trips_signed_payload():
    token = _cursor()

    envelope = decode_cursor(
        token,
        read_model_id="demo_targets",
        contract_version=1,
        sort_id="score_desc",
        filters={"workspace_id": "ws-1"},
        secret="test-secret",
        now=1_100,
    )

    assert envelope.last_values == {"follower_count": 100, "handle": "demo"}
    assert envelope.expires_at == 1_900


def test_keyset_cursor_rejects_filter_mismatch():
    token = _cursor()

    with pytest.raises(CursorError, match="cursor_filter_mismatch"):
        decode_cursor(
            token,
            read_model_id="demo_targets",
            contract_version=1,
            sort_id="score_desc",
            filters={"workspace_id": "ws-2"},
            secret="test-secret",
            now=1_100,
        )


def test_keyset_cursor_rejects_expired_token():
    token = _cursor()

    with pytest.raises(CursorError, match="cursor_expired"):
        decode_cursor(
            token,
            read_model_id="demo_targets",
            contract_version=1,
            sort_id="score_desc",
            filters={"workspace_id": "ws-1"},
            secret="test-secret",
            now=2_000,
        )


def test_keyset_cursor_rejects_tampered_token():
    token = _cursor()
    tampered = f"{token[:-1]}A"

    with pytest.raises(CursorError):
        decode_cursor(
            tampered,
            read_model_id="demo_targets",
            contract_version=1,
            sort_id="score_desc",
            filters={"workspace_id": "ws-1"},
            secret="test-secret",
            now=1_100,
        )
