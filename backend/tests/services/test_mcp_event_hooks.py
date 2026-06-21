from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.services.mcp_event_hooks import (
    HookResults,
    MCPEventHookService,
    ReceiptDecision,
)

VALID_HASH = "a" * 64


class FakeStore:
    def __init__(self) -> None:
        self.hook_runs = {}
        self.calls = []

    async def execute_raw(self, sql, params):
        self.calls.append((sql, params))
        normalized_sql = " ".join(sql.split())

        if normalized_sql.startswith("SELECT * FROM mcp_hook_runs"):
            idem_key = params[0]
            row = self.hook_runs.get(idem_key)
            return [row] if row else []

        if "INSERT INTO mcp_hook_runs" in normalized_sql:
            idem_key, hook_type, workspace_id, status, result_summary, _created_at = (
                params
            )
            self.hook_runs.setdefault(
                idem_key,
                {
                    "idempotency_key": idem_key,
                    "hook_type": hook_type,
                    "workspace_id": workspace_id,
                    "status": status,
                    "result_summary": result_summary,
                },
            )
            return None

        return None


def accepted_receipt(step: str):
    return {
        "step": step,
        "trace_id": "trace-1",
        "output_hash": VALID_HASH,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def test_public_facade_exports_service_contracts() -> None:
    assert MCPEventHookService is not None
    assert HookResults.__name__ == "HookResults"
    assert ReceiptDecision.__name__ == "ReceiptDecision"


def test_receipt_validation_preserves_reason_strings() -> None:
    service = MCPEventHookService()

    accepted = service._evaluate_receipt(
        "intent_extract", [accepted_receipt("intent_extract")]
    )
    assert accepted.should_run is False
    assert accepted.reason == "receipt_accepted"

    missing = service._evaluate_receipt("intent_extract", [])
    assert missing.should_run is True
    assert missing.reason == "no_receipt"

    invalid = service._evaluate_receipt(
        "intent_extract",
        [
            {
                "step": "intent_extract",
                "trace_id": "trace-1",
                "output_hash": "not-a-hex-hash",
            }
        ],
    )
    assert invalid.should_run is True
    assert invalid.reason == "invalid_output_hash"


@pytest.mark.asyncio
async def test_on_chat_synced_skips_receipted_hooks_without_running_runtime() -> None:
    service = MCPEventHookService()
    emitted = []

    async def fail_extract(*args, **kwargs):
        raise AssertionError("receipted hook should not run")

    async def capture_emit(**kwargs):
        emitted.append(kwargs)
        return f"event-{len(emitted)}"

    service._extract_intents = fail_extract
    service._emit = capture_emit

    result = await service.on_chat_synced(
        workspace_id="ws-1",
        profile_id="profile-1",
        message="hello",
        message_id="msg-1",
        trace_id="trace-1",
        ide_receipts=[
            accepted_receipt("intent_extract"),
            accepted_receipt("steward_analyze"),
        ],
    )

    assert result.triggered_hooks == []
    assert result.skipped_hooks == ["intent_extract", "steward_analyze"]
    assert [event["event_type"] for event in emitted] == [
        "receipt_accepted",
        "receipt_accepted",
    ]


@pytest.mark.asyncio
async def test_run_idempotent_uses_cached_result_and_records_once() -> None:
    store = FakeStore()
    service = MCPEventHookService(store=store)
    call_count = 0

    async def hook():
        nonlocal call_count
        call_count += 1
        return ["tag"]

    idem_key = service._build_key("ws-1", "msg-1", "intent_extract")
    first = await service._run_idempotent(
        idem_key=idem_key,
        hook_type="intent_extract",
        workspace_id="ws-1",
        fn=hook,
    )
    second = await service._run_idempotent(
        idem_key=idem_key,
        hook_type="intent_extract",
        workspace_id="ws-1",
        fn=hook,
    )

    assert first == ["tag"]
    assert second == store.hook_runs[idem_key]["result_summary"]
    assert call_count == 1
    assert len(idem_key) == 48
