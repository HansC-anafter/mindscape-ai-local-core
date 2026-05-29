from backend.app.runner.browser_fair_candidate_scheduler import (
    BrowserCandidate,
    normalize_browser_lane_key,
    select_browser_fair_candidate,
)


def test_selects_lane_with_lowest_running_count():
    decision = select_browser_fair_candidate(
        [
            BrowserCandidate(
                task_id="following-1",
                pack_id="ig_analyze_following",
                queue_position=0,
            ),
            BrowserCandidate(
                task_id="batch-1",
                pack_id="ig_batch_pin_references",
                queue_position=1,
            ),
            BrowserCandidate(
                task_id="pin-1",
                pack_id="ig_pin_post_detail",
                queue_position=2,
            ),
        ],
        {
            "ig_analyze_following": 3,
            "ig_batch_pin_references": 0,
            "ig_pin_post_detail": 0,
        },
    )

    assert decision.selected_task_id == "batch-1"
    assert decision.selected_lane == "ig_batch_pin_references"
    assert decision.running_count == 0


def test_selects_pin_when_batch_has_more_running_work():
    decision = select_browser_fair_candidate(
        [
            BrowserCandidate(
                task_id="following-1",
                pack_id="ig_analyze_following",
                queue_position=0,
            ),
            BrowserCandidate(
                task_id="batch-1",
                pack_id="ig_batch_pin_references",
                queue_position=1,
            ),
            BrowserCandidate(
                task_id="pin-1",
                pack_id="ig_pin_post_detail",
                queue_position=2,
            ),
        ],
        {
            "ig_analyze_following": 3,
            "ig_batch_pin_references": 1,
            "ig_pin_post_detail": 0,
        },
    )

    assert decision.selected_task_id == "pin-1"
    assert decision.selected_lane == "ig_pin_post_detail"


def test_tie_preserves_scan_order():
    decision = select_browser_fair_candidate(
        [
            BrowserCandidate(
                task_id="following-1",
                pack_id="ig_analyze_following",
                queue_position=0,
            ),
            BrowserCandidate(
                task_id="batch-1",
                pack_id="ig_batch_pin_references",
                queue_position=1,
            ),
        ],
        {
            "ig_analyze_following": 0,
            "ig_batch_pin_references": 0,
        },
    )

    assert decision.selected_task_id == "following-1"
    assert decision.selected_lane == "ig_analyze_following"


def test_same_lane_window_selects_first_candidate():
    decision = select_browser_fair_candidate(
        [
            BrowserCandidate(
                task_id="batch-1",
                pack_id="ig_batch_pin_references",
                queue_position=0,
            ),
            BrowserCandidate(
                task_id="batch-2",
                pack_id="ig_batch_pin_references",
                queue_position=1,
            ),
        ],
        {"ig_batch_pin_references": 2},
    )

    assert decision.selected_task_id == "batch-1"
    assert decision.selected_lane == "ig_batch_pin_references"


def test_batch_pin_manual_and_after_visit_share_batch_lane():
    assert (
        normalize_browser_lane_key("ig_batch_pin_references", "ig_batch_pin_references")
        == "ig_batch_pin_references"
    )
    assert (
        normalize_browser_lane_key("ig_batch_pin_references", "batch_pin_manual_queue")
        == "ig_batch_pin_references"
    )
