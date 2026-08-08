import os
import pickle
import stat

from backend.app.runner import task_executor_process
from backend.app.runner.task_executor_process import (
    RunnerChildProcess,
    create_child_payload_file,
    start_child_process,
)


def test_child_payload_file_is_private_and_pickled(tmp_path, monkeypatch):
    monkeypatch.setattr(task_executor_process.tempfile, "tempdir", str(tmp_path))

    payload_file = create_child_payload_file("task-one", {"value": {1, 2}})

    assert stat.S_IMODE(os.stat(payload_file).st_mode) == 0o600
    with open(payload_file, "rb") as file_obj:
        assert pickle.load(file_obj) == {"value": {1, 2}}


def test_child_process_uses_lightweight_module_not_multiprocessing_spawn(
    monkeypatch,
):
    calls = {}

    class ForbiddenMultiprocessingContext:
        def Process(self, **_kwargs):
            raise AssertionError("multiprocessing spawn is forbidden")

    class FakePopen:
        pid = 321

        def __init__(self, command, **kwargs):
            calls["command"] = command
            calls["kwargs"] = kwargs

        def poll(self):
            return None

        def wait(self, timeout=None):
            calls["wait_timeout"] = timeout
            return 0

        def terminate(self):
            calls["terminated"] = True

        def kill(self):
            calls["killed"] = True

    class Task:
        id = "task-one"
        pack_id = "ig_analyze_following"

    monkeypatch.setattr(
        task_executor_process,
        "create_child_payload_file",
        lambda *_args: "/tmp/runner-payload.pickle",
    )
    monkeypatch.setattr(task_executor_process.subprocess, "Popen", FakePopen)

    process = start_child_process(
        ctx_mp=ForbiddenMultiprocessingContext(),
        target=lambda _payload: None,
        payload={"task_id": "task-one"},
        task=Task(),
        trace_heartbeat=False,
    )

    assert isinstance(process, RunnerChildProcess)
    assert calls["command"] == [
        task_executor_process.sys.executable,
        "-u",
        "-m",
        "backend.app.runner.task_executor_child",
        "--payload-file",
        "/tmp/runner-payload.pickle",
    ]
    assert calls["kwargs"] == {"close_fds": True}
