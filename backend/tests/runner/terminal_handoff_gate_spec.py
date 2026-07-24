import asyncio

import pytest

from backend.app.runner import terminal_handoff_gate


class _FakeQueue:
    def __init__(self, acquire_results):
        self.acquire_results = list(acquire_results)
        self.acquire_calls = []
        self.release_calls = []

    async def acquire_lock(self, key, owner_id, ttl_seconds):
        self.acquire_calls.append((key, owner_id, ttl_seconds))
        return self.acquire_results.pop(0)

    async def release_lock(self, key, owner_id):
        self.release_calls.append((key, owner_id))
        return True


@pytest.mark.asyncio
async def test_terminal_handoff_waits_then_keeps_lease_until_successor_claim(
    monkeypatch,
):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_TERMINAL_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("LOCAL_CORE_RUNNER_TERMINAL_HANDOFF_POLL_INTERVAL_MS", "10")
    queue = _FakeQueue([False, True])
    sleeps = []

    async def _sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    acquired = await terminal_handoff_gate.acquire_terminal_handoff(
        queue,
        runner_id="slot-2",
    )

    assert acquired is True
    assert len(queue.acquire_calls) == 2
    assert sleeps == [0.01]
    assert queue.release_calls == []

    released = await terminal_handoff_gate.release_terminal_handoff_after_claim(
        queue,
        runner_id="slot-2",
    )

    assert released is True
    assert queue.release_calls == [
        (
            terminal_handoff_gate.DEFAULT_LOCK_KEY,
            "slot-2:terminal-handoff",
        )
    ]


@pytest.mark.asyncio
async def test_terminal_handoff_is_inert_when_disabled(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_TERMINAL_HANDOFF_ENABLED", "false")
    queue = _FakeQueue([True])

    assert not await terminal_handoff_gate.acquire_terminal_handoff(
        queue,
        runner_id="slot-1",
    )
    assert not await terminal_handoff_gate.release_terminal_handoff_after_claim(
        queue,
        runner_id="slot-1",
    )
    assert queue.acquire_calls == []
    assert queue.release_calls == []


def test_terminal_handoff_defaults_on_for_steady_browser_slots(monkeypatch):
    monkeypatch.delenv("LOCAL_CORE_RUNNER_TERMINAL_HANDOFF_ENABLED", raising=False)
    monkeypatch.setenv(
        "LOCAL_CORE_RUNNER_ID",
        "default-browser-steady-six-slot-4",
    )

    assert terminal_handoff_gate.terminal_handoff_enabled() is True

    monkeypatch.setenv(
        "LOCAL_CORE_RUNNER_ID",
        "default-browser-steady-five-slot-2",
    )
    assert terminal_handoff_gate.terminal_handoff_enabled() is True
