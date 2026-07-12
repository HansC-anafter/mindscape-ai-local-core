from backend.app.runner.browser_fair_candidate_scheduler import (
    BrowserCandidate,
    normalize_browser_lane_key,
    select_browser_fair_candidate,
)

BATCH_PLAYBOOK = "browser_batch_collect"
DETAIL_PLAYBOOK = "browser_detail_collect"
FOLLOWING_PLAYBOOK = "browser_following_collect"
BATCH_LANE = "browser_batch_collect"


def test_selects_lane_with_lowest_running_count():
    decision = select_browser_fair_candidate(
        [
            BrowserCandidate(
                task_id="following-1",
                pack_id=FOLLOWING_PLAYBOOK,
                queue_position=0,
            ),
            BrowserCandidate(
                task_id="batch-1",
                pack_id=BATCH_PLAYBOOK,
                queue_position=1,
            ),
            BrowserCandidate(
                task_id="pin-1",
                pack_id=DETAIL_PLAYBOOK,
                queue_position=2,
            ),
        ],
        {
            FOLLOWING_PLAYBOOK: 3,
            BATCH_PLAYBOOK: 0,
            DETAIL_PLAYBOOK: 0,
        },
    )

    assert decision.selected_task_id == "batch-1"
    assert decision.selected_lane == BATCH_PLAYBOOK
    assert decision.running_count == 0


def test_selects_pin_when_batch_has_more_running_work():
    decision = select_browser_fair_candidate(
        [
            BrowserCandidate(
                task_id="following-1",
                pack_id=FOLLOWING_PLAYBOOK,
                queue_position=0,
            ),
            BrowserCandidate(
                task_id="batch-1",
                pack_id=BATCH_PLAYBOOK,
                queue_position=1,
            ),
            BrowserCandidate(
                task_id="pin-1",
                pack_id=DETAIL_PLAYBOOK,
                queue_position=2,
            ),
        ],
        {
            FOLLOWING_PLAYBOOK: 3,
            BATCH_PLAYBOOK: 1,
            DETAIL_PLAYBOOK: 0,
        },
    )

    assert decision.selected_task_id == "pin-1"
    assert decision.selected_lane == DETAIL_PLAYBOOK


def test_tie_preserves_scan_order():
    decision = select_browser_fair_candidate(
        [
            BrowserCandidate(
                task_id="following-1",
                pack_id=FOLLOWING_PLAYBOOK,
                queue_position=0,
            ),
            BrowserCandidate(
                task_id="batch-1",
                pack_id=BATCH_PLAYBOOK,
                queue_position=1,
            ),
        ],
        {
            FOLLOWING_PLAYBOOK: 0,
            BATCH_PLAYBOOK: 0,
        },
    )

    assert decision.selected_task_id == "following-1"
    assert decision.selected_lane == FOLLOWING_PLAYBOOK


def test_tie_rotates_after_last_selected_lane():
    decision = select_browser_fair_candidate(
        [
            BrowserCandidate(
                task_id="following-1",
                pack_id=FOLLOWING_PLAYBOOK,
                queue_position=0,
            ),
            BrowserCandidate(
                task_id="batch-1",
                pack_id=BATCH_PLAYBOOK,
                queue_position=1,
            ),
            BrowserCandidate(
                task_id="pin-1",
                pack_id=DETAIL_PLAYBOOK,
                queue_position=2,
            ),
        ],
        {
            FOLLOWING_PLAYBOOK: 0,
            BATCH_PLAYBOOK: 0,
            DETAIL_PLAYBOOK: 0,
        },
        last_selected_lane=FOLLOWING_PLAYBOOK,
    )

    assert decision.selected_task_id == "batch-1"
    assert decision.selected_lane == BATCH_PLAYBOOK
    assert decision.reason == "lane_round_robin"


def test_same_lane_window_selects_first_candidate():
    decision = select_browser_fair_candidate(
        [
            BrowserCandidate(
                task_id="batch-1",
                pack_id=BATCH_PLAYBOOK,
                queue_position=0,
            ),
            BrowserCandidate(
                task_id="batch-2",
                pack_id=BATCH_PLAYBOOK,
                queue_position=1,
            ),
        ],
        {BATCH_PLAYBOOK: 2},
    )

    assert decision.selected_task_id == "batch-1"
    assert decision.selected_lane == BATCH_PLAYBOOK


def test_manual_batch_playbook_can_share_declared_fairness_lane(monkeypatch):
    from backend.app.services.runner_topology import task_family_registry

    def _metadata(playbook_code):
        if playbook_code != BATCH_PLAYBOOK:
            return {}
        return {
            "task_family": "browser_batch",
            "managed_runner_role": "managed_browser_batch",
            "fairness_lane_key": BATCH_LANE,
        }

    monkeypatch.setattr(
        task_family_registry,
        "resolve_installed_playbook_runner_metadata",
        _metadata,
    )

    assert (
        normalize_browser_lane_key(BATCH_PLAYBOOK, BATCH_PLAYBOOK)
        == BATCH_LANE
    )
    assert (
        normalize_browser_lane_key(BATCH_PLAYBOOK, "manual_batch_queue")
        == BATCH_LANE
    )
