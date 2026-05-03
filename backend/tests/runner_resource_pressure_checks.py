from backend.app.runner import resource_pressure


def _write(path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_runner_resource_snapshot_uses_cgroup_working_set(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_CORE_RUNNER_BROWSER_MEMORY_SOFT_RATIO", raising=False)
    resource_pressure._reset_resource_cooldown_for_tests()

    _write(tmp_path / "memory.current", "900")
    _write(tmp_path / "memory.max", "1000")
    _write(tmp_path / "memory.stat", "inactive_file 300\nanon 500\n")
    _write(tmp_path / "pids.current", "12")
    _write(tmp_path / "pids.max", "max")

    snapshot = resource_pressure.build_runner_resource_snapshot(
        profile_code="runner-browser",
        inflight=1,
        cgroup_root=tmp_path,
        now_epoch=100.0,
    )

    assert snapshot["memory"]["working_set_bytes"] == 600
    assert snapshot["memory"]["working_set_ratio"] == 0.6
    assert snapshot["pids"]["limit"] is None
    assert snapshot["admission"]["state"] == "normal"
    assert snapshot["admission"]["should_defer"] is False


def test_runner_resource_pressure_enters_cooldown(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_BROWSER_MEMORY_HARD_RATIO", "0.90")
    monkeypatch.setenv("LOCAL_CORE_RUNNER_BROWSER_RESOURCE_COOLDOWN_SECONDS", "120")
    resource_pressure._reset_resource_cooldown_for_tests()

    _write(tmp_path / "memory.current", "950")
    _write(tmp_path / "memory.max", "1000")
    _write(tmp_path / "memory.stat", "inactive_file 0\n")

    snapshot = resource_pressure.build_runner_resource_snapshot(
        profile_code="runner-browser",
        cgroup_root=tmp_path,
        now_epoch=100.0,
    )
    assert snapshot["admission"]["state"] == "hard_cooldown"
    assert snapshot["admission"]["should_defer"] is True
    assert snapshot["admission"]["cooldown_until_epoch"] == 220.0

    _write(tmp_path / "memory.current", "100")
    cooled_snapshot = resource_pressure.build_runner_resource_snapshot(
        profile_code="runner-browser",
        cgroup_root=tmp_path,
        now_epoch=101.0,
    )
    assert cooled_snapshot["admission"]["state"] == "cooldown"
    assert cooled_snapshot["admission"]["should_defer"] is True


def test_classify_subprocess_resource_failure():
    assert (
        resource_pressure.classify_subprocess_resource_failure(-9, "")
        == "subprocess_sigkill"
    )
    assert (
        resource_pressure.classify_subprocess_resource_failure(
            1,
            "Browser launch timed out after 60s",
        )
        == "browser_launch_timeout"
    )
    assert (
        resource_pressure.classify_subprocess_resource_failure(
            1,
            "Timed out waiting for IG browser resource lease",
        )
        == "browser_resource_lease"
    )
