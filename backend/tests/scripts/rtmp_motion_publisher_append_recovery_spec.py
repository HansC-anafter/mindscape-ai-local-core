from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rtmp_motion_publisher.append_recovery import (  # noqa: E402
    schedule_append_confirmation,
)


def test_append_confirmation_uses_bounded_exponential_schedule() -> None:
    first = schedule_append_confirmation(
        now_monotonic=100.0,
        first_failure_monotonic=None,
        completed_rounds=0,
        maximum_rounds=4,
        base_backoff_sec=8.0,
        maximum_recovery_sec=130.0,
    )
    assert first is not None
    assert first.confirmation_round == 1
    assert first.next_attempt_monotonic == 108.0

    fourth = schedule_append_confirmation(
        now_monotonic=156.0,
        first_failure_monotonic=100.0,
        completed_rounds=3,
        maximum_rounds=4,
        base_backoff_sec=8.0,
        maximum_recovery_sec=130.0,
    )
    assert fourth is not None
    assert fourth.confirmation_round == 4
    assert fourth.retry_delay_sec == 64.0
    assert fourth.next_attempt_monotonic == 220.0


def test_append_confirmation_stops_at_time_or_round_budget() -> None:
    assert schedule_append_confirmation(
        now_monotonic=230.0,
        first_failure_monotonic=100.0,
        completed_rounds=3,
        maximum_rounds=4,
        base_backoff_sec=8.0,
        maximum_recovery_sec=130.0,
    ) is None
    assert schedule_append_confirmation(
        now_monotonic=120.0,
        first_failure_monotonic=100.0,
        completed_rounds=4,
        maximum_rounds=4,
        base_backoff_sec=8.0,
        maximum_recovery_sec=130.0,
    ) is None
