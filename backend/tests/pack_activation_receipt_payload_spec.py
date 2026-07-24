import json
from datetime import datetime, timezone

from backend.app.services.pack_activation_types import PackActivationRecord


def test_activation_receipt_payload_serializes_timestamps_without_changing_store_types():
    activated_at = datetime(2026, 7, 17, 15, 39, tzinfo=timezone.utc)
    embeddings_updated_at = datetime(2026, 7, 17, 15, 38, tzinfo=timezone.utc)
    record = PackActivationRecord(
        pack_id="yogacoach",
        pack_family="yogacoach",
        enabled=True,
        install_state="installed",
        migration_state="applied",
        activation_state="active",
        activation_mode="install_hot_reload",
        embedding_state="indexed",
        embedding_error=None,
        embeddings_updated_at=embeddings_updated_at,
        manifest_hash="a" * 64,
        registered_prefixes=["/api/v1/capabilities/yogacoach"],
        last_error=None,
        activated_at=activated_at,
    )

    store_payload = record.to_store_payload()
    receipt_payload = record.to_receipt_payload()

    assert store_payload["activated_at"] is activated_at
    assert store_payload["embeddings_updated_at"] is embeddings_updated_at
    assert receipt_payload["activated_at"] == activated_at.isoformat()
    assert receipt_payload["embeddings_updated_at"] == embeddings_updated_at.isoformat()
    json.dumps(receipt_payload)
