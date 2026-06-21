from datetime import datetime, timezone
from pathlib import Path

from backend.app.services.host_resources import manager
from backend.app.services.host_resources.manager_core import reservation_state


ROOT = Path(__file__).resolve().parents[2]
MANAGER_PATH = ROOT / "backend" / "app" / "services" / "host_resources" / "manager.py"
CORE_DIR = ROOT / "backend" / "app" / "services" / "host_resources" / "manager_core"


def test_manager_reexports_moved_helper_aliases() -> None:
    assert manager._parse_datetime is reservation_state.parse_datetime
    assert manager._reservation_is_active is reservation_state.reservation_is_active
    assert (
        manager._reservation_matches_state_filter
        is reservation_state.reservation_matches_state_filter
    )
    assert (
        manager._clamped_reservation_limit
        is reservation_state.clamped_reservation_limit
    )
    assert manager._reservation_sort_key is reservation_state.reservation_sort_key
    assert manager._normalized_route_request is reservation_state.normalized_route_request
    assert (
        manager._normalize_runner_claim_gate
        is reservation_state.normalize_runner_claim_gate
    )
    assert manager._ttl_seconds_from_payload({"ttl_seconds": "10"}) == 60


def test_pure_reservation_state_helpers_preserve_filters_limits_and_ttl() -> None:
    now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    active = {
        "reservation_id": "active",
        "state": "reserved_waiting",
        "created_at": "2026-06-21T11:00:00+00:00",
        "expires_at": "2026-06-21T13:00:00+00:00",
    }
    expired = {
        "reservation_id": "expired",
        "state": "reserved_waiting",
        "created_at": "2026-06-21T10:00:00+00:00",
        "expires_at": "2026-06-21T11:59:00+00:00",
    }
    cancelled = {
        "reservation_id": "cancelled",
        "state": "cancelled",
        "created_at": "2026-06-21T09:00:00+00:00",
    }

    assert reservation_state.reservation_is_active(active, now=now) is True
    assert reservation_state.reservation_is_active(expired, now=now) is False
    assert reservation_state.reservation_matches_state_filter(active, "active") is True
    assert reservation_state.reservation_matches_state_filter(cancelled, "history") is True
    assert reservation_state.reservation_matches_state_filter(cancelled, "all") is True
    assert reservation_state.clamped_reservation_limit(0) == 100
    assert reservation_state.clamped_reservation_limit(999) == 200
    assert reservation_state.ttl_seconds_from_payload(
        {"ttl_seconds": "10"},
        default_ttl=3600,
    ) == 60
    assert reservation_state.ttl_seconds_from_payload(
        {"ttl_seconds": "120"},
        default_ttl=3600,
    ) == 120
    assert reservation_state.reservation_sort_key(active) == datetime(
        2026,
        6,
        21,
        11,
        0,
        tzinfo=timezone.utc,
    )


def test_route_request_and_runner_claim_gate_normalization_are_preserved() -> None:
    from_nested = reservation_state.normalized_route_request(
        {
            "route_request": {
                "lane_id": "runner:default_local_browser",
                "resource_groups": ["browser"],
            },
            "ttl_seconds": 120,
        }
    )
    from_flat = reservation_state.normalized_route_request(
        {
            "lane_id": "runner:vision_local",
            "resource_groups": ["vision"],
        }
    )

    assert from_nested["target_lane"] == "runner:default_local_browser"
    assert from_nested["resource_groups"] == ["browser"]
    assert from_flat["target_lane"] == "runner:vision_local"
    assert reservation_state.normalize_runner_claim_gate(
        None,
        source="default",
    ) == {
        "state": "open",
        "reason": None,
        "source": "default",
        "persisted": False,
    }
    assert reservation_state.normalize_runner_claim_gate(
        {"state": "paused", "reason": "maintenance"},
        source="redis",
    ) == {
        "state": "paused",
        "reason": "maintenance",
        "source": "redis",
        "persisted": True,
    }
    assert reservation_state.normalize_runner_claim_gate(
        {"state": "closed", "reason": "done"},
        source="memory",
    )["state"] == "open"


def test_manager_core_has_no_resource_access_markers() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in CORE_DIR.glob("*.py"))
    forbidden_markers = [
        "get_cache_service",
        "HostResourceReservationStore",
        "call_host_resource_probe",
        "load_lane_registry",
        "snapshot_from_probe",
        "degraded_snapshot",
        "asyncio.Lock",
        "Session(",
        "PgBouncer",
        "create_task(",
        "EventSource",
        "websocket",
        "subprocess",
    ]

    for marker in forbidden_markers:
        assert marker not in source


def test_host_resource_manager_seam_files_stay_below_line_gate() -> None:
    paths = [
        MANAGER_PATH,
        *(sorted(CORE_DIR.glob("*.py"))),
        Path(__file__),
    ]

    for path in paths:
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 500, path
