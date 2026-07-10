from backend.app.runner.cgroup_memory_events import (
    has_oom_kill_delta,
    memory_event_delta,
    read_cgroup_memory_events,
)
from backend.app.runner.resource_pressure import classify_subprocess_resource_failure


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_v2_oom_kill_delta_is_correlated_with_failing_child(tmp_path):
    _write(tmp_path / "memory.events", "low 0\nhigh 1\nmax 2\noom 3\noom_kill 4\noom_group_kill 0\n")
    before = read_cgroup_memory_events(tmp_path)
    _write(tmp_path / "memory.events", "low 0\nhigh 1\nmax 3\noom 4\noom_kill 5\noom_group_kill 0\n")
    after = read_cgroup_memory_events(tmp_path)

    delta = memory_event_delta(before, after)

    assert delta["available"] is True
    assert delta["counters"]["oom_kill"] == 1
    assert has_oom_kill_delta(delta) is True
    assert classify_subprocess_resource_failure(
        1,
        "child failed",
        before_snapshot={"memory_events": before},
        after_snapshot={"memory_events": after},
    ) == "runner_cgroup_oom_correlated"


def test_plain_sigkill_without_oom_delta_stays_unclassified(tmp_path):
    _write(tmp_path / "memory.events", "oom 3\noom_kill 4\noom_group_kill 0\n")
    snapshot = read_cgroup_memory_events(tmp_path)

    assert classify_subprocess_resource_failure(
        -9,
        "",
        before_snapshot={"memory_events": snapshot},
        after_snapshot={"memory_events": snapshot},
    ) == "unclassified_sigkill"


def test_counter_reset_and_v1_failcnt_cannot_prove_oom(tmp_path):
    before = {
        "available": True,
        "cgroup_version": 2,
        "counters": {"oom": 4, "oom_kill": 4, "oom_group_kill": 1},
    }
    after = {
        "available": True,
        "cgroup_version": 2,
        "counters": {"oom": 0, "oom_kill": 0, "oom_group_kill": 0},
    }
    assert memory_event_delta(before, after)["reason"] == "counter_reset"

    _write(tmp_path / "memory" / "memory.failcnt", "9")
    v1 = read_cgroup_memory_events(tmp_path)
    assert v1["available"] is False
    assert v1["v1_failcnt"] == 9
    assert has_oom_kill_delta(memory_event_delta(v1, v1)) is False
