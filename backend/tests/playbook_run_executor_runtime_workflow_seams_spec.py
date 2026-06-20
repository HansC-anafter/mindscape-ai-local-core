from types import SimpleNamespace

import pytest

import backend.app.services.playbook_run_executor_core.runtime_workflow as runtime_module


class _FakeRuntimeFactory:
    def __init__(self, runtime):
        self.runtime = runtime
        self.profiles = []

    def get_runtime(self, execution_profile):
        self.profiles.append(execution_profile)
        return self.runtime


class _FakePlaybookRun:
    def __init__(self, execution_profile="workflow"):
        self.execution_profile = execution_profile

    def get_execution_profile(self):
        return self.execution_profile


@pytest.mark.asyncio
async def test_non_runner_runtime_workflow_registers_one_background_task(monkeypatch):
    calls = {"created": 0, "registered": [], "persisted": [], "started": []}
    task_marker = object()

    class FakeRuntime:
        name = "fake-runtime"

        async def execute(self, **_kwargs):
            raise AssertionError("background coroutine should not run in this seam test")

    def fake_create_task(coro):
        calls["created"] += 1
        coro.close()
        return task_marker

    def fake_register(execution_id, task):
        calls["registered"].append((execution_id, task))

    monkeypatch.setattr(runtime_module.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(runtime_module, "_register_background_task", fake_register)
    monkeypatch.setattr(
        runtime_module,
        "inject_lens_context",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        runtime_module,
        "persist_running_runtime_task",
        lambda **kwargs: calls["persisted"].append(kwargs),
    )
    monkeypatch.setattr(
        runtime_module,
        "record_started",
        lambda **kwargs: calls["started"].append(kwargs),
    )

    executor = SimpleNamespace(runtime_factory=_FakeRuntimeFactory(FakeRuntime()))
    normalized_inputs = {"execution_id": "exec_background"}

    result = await runtime_module.execute_runtime_workflow(
        executor=executor,
        playbook_run=_FakePlaybookRun("profile_background"),
        playbook_code="demo_playbook",
        profile_id="profile_1",
        normalized_inputs=normalized_inputs,
        workspace_id="workspace_1",
        project_id="project_1",
        runtime_result_has_errors_fn=lambda *_args: False,
        is_runner_process_fn=lambda: False,
    )

    assert result == {
        "execution_mode": "workflow",
        "playbook_code": "demo_playbook",
        "execution_id": "exec_background",
        "result": {"status": "running", "execution_id": "exec_background"},
        "has_json": True,
        "runtime": "fake-runtime",
    }
    assert calls["created"] == 1
    assert calls["registered"] == [("exec_background", task_marker)]
    assert calls["persisted"][0]["execution_id"] == "exec_background"
    assert calls["started"][0]["metadata"]["runtime"] == "fake-runtime"


@pytest.mark.asyncio
async def test_runner_runtime_workflow_executes_and_persists_terminal_result(monkeypatch):
    calls = {
        "artifacts": [],
        "receipts": [],
        "persisted_results": [],
        "unregistered": [],
    }
    runtime_result = SimpleNamespace(
        status="completed",
        outputs={"answer": "ok"},
        metadata={"sandbox_id": "sandbox_1", "steps": {"step_1": {"outputs": {"ok": True}}}},
    )

    class FakeRuntime:
        name = "runner-runtime"

        async def execute(self, **kwargs):
            calls["execute_kwargs"] = kwargs
            return runtime_result

    async def fake_create_artifacts(**kwargs):
        calls["artifacts"].append(kwargs)

    def fake_generate_receipt(**kwargs):
        calls["receipts"].append(kwargs)

    def fake_persist_result(**kwargs):
        calls["persisted_results"].append(kwargs)

    def fail_create_task(_coro):
        raise AssertionError("runner branch must not create a background task")

    monkeypatch.setattr(runtime_module.asyncio, "create_task", fail_create_task)
    monkeypatch.setattr(runtime_module, "maybe_create_runtime_output_artifacts", fake_create_artifacts)
    monkeypatch.setattr(runtime_module, "generate_lens_receipt", fake_generate_receipt)
    monkeypatch.setattr(runtime_module, "persist_runtime_result", fake_persist_result)
    monkeypatch.setattr(runtime_module, "_unregister_background_task", lambda execution_id: calls["unregistered"].append(execution_id))
    monkeypatch.setattr(runtime_module, "persist_running_runtime_task", lambda **_kwargs: None)
    monkeypatch.setattr(runtime_module, "record_started", lambda **_kwargs: None)
    monkeypatch.setattr(runtime_module, "inject_lens_context", lambda **_kwargs: "lens_1")

    store = object()
    executor = SimpleNamespace(runtime_factory=_FakeRuntimeFactory(FakeRuntime()), store=store)
    normalized_inputs = {"execution_id": "exec_runner"}

    result = await runtime_module.execute_runtime_workflow(
        executor=executor,
        playbook_run=_FakePlaybookRun("profile_runner"),
        playbook_code="demo_playbook",
        profile_id="profile_1",
        normalized_inputs=normalized_inputs,
        workspace_id="workspace_1",
        project_id="project_1",
        runtime_result_has_errors_fn=lambda *_args: False,
        is_runner_process_fn=lambda: True,
    )

    assert result["result"] == {"status": "completed", "execution_id": "exec_runner"}
    assert calls["execute_kwargs"]["inputs"] is normalized_inputs
    assert calls["artifacts"][0]["store"] is store
    assert calls["artifacts"][0]["sandbox_id"] == "sandbox_1"
    assert calls["receipts"][0]["effective_lens"] == "lens_1"
    assert calls["persisted_results"][0]["runtime_result"] is runtime_result
    assert calls["persisted_results"][0]["result"]["status"] == "completed"
    assert calls["unregistered"] == ["exec_runner"]


def test_runtime_workflow_reexports_helper_names_from_facade_module():
    assert runtime_module._resolve_execution_id({"execution_id": "exec_1"}) == "exec_1"
    assert callable(runtime_module.persist_running_runtime_task)
    assert callable(runtime_module.persist_runtime_result)
    assert callable(runtime_module.inject_lens_context)
