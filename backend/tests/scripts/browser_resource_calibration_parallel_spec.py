from __future__ import annotations

import json
import threading

from scripts.maintenance.browser_resource_calibration_core.collectors import (
    CalibrationCollector,
)


def test_lean_cgroup_snapshots_run_in_bounded_parallel_and_keep_order() -> None:
    class Commands:
        def __init__(self) -> None:
            self.barrier = threading.Barrier(2)
            self.calls: list[tuple[tuple[str, ...], int]] = []

        def run(self, argv: list[str], *, timeout_seconds: int):
            self.calls.append((tuple(argv), timeout_seconds))
            if argv[-1] == "/proc/meminfo":
                output = "MemTotal: 16384 kB\nMemAvailable: 8192 kB\n"
            elif argv[3] == "python":
                self.barrier.wait(timeout=2)
                current = 1000 if argv[2] == "runner-a" else 2000
                output = json.dumps(
                    {
                        "memory_current_bytes": current,
                        "memory_peak_bytes": current + 100,
                        "inactive_file_bytes": current // 10,
                        "oom_kill": 0,
                        "oom_group_kill": 0,
                    }
                )
            else:
                raise AssertionError(argv)
            return type(
                "Result",
                (),
                {"returncode": 0, "stdout": output, "stderr": ""},
            )()

    commands = Commands()
    sample = CalibrationCollector(
        browser_containers=("runner-a", "runner-b"),
        command_runner=commands,
    ).collect_node(include_all_containers=False)

    assert [row["container"] for row in sample["browser_cgroups"]] == [
        "runner-a",
        "runner-b",
    ]
    assert sample["browser_container_working_set_bytes"] == 2700
    python_calls = [
        (call, timeout)
        for call, timeout in commands.calls
        if call[3] == "python"
    ]
    assert len(python_calls) == 2
    assert [timeout for _, timeout in python_calls] == [8, 8]
