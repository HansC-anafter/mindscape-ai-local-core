from datetime import datetime, timedelta, timezone

from scripts.postgres_soak_core import REQUIRED_WORKLOADS, evaluate_soak


def test_soak_requires_72_hours_and_all_workloads():
    verdict = evaluate_soak(
        started_at="2026-07-16T00:00:00+00:00",
        now="2026-07-16T01:00:00+00:00",
        samples=[],
        workloads=[],
    )
    assert not verdict["ok"]
    assert "soak_duration_below_72h" in verdict["failures"]
    assert len([item for item in verdict["failures"] if item.startswith("workload_missing:")]) == len(REQUIRED_WORKLOADS)


def test_soak_accepts_complete_bounded_evidence():
    started = datetime(2026, 7, 13, tzinfo=timezone.utc)
    samples = [
        {
            "ok": True,
            "captured_at": (started + timedelta(seconds=30 * index)).isoformat(),
            "failures": [],
        }
        for index in range((72 * 3600 // 30) + 1)
    ]
    verdict = evaluate_soak(
        started_at="2026-07-13T00:00:00+00:00",
        now="2026-07-16T00:00:00+00:00",
        samples=samples,
        workloads=REQUIRED_WORKLOADS,
    )
    assert verdict["ok"]
