from types import SimpleNamespace

from backend.app.models.mindscape import EventActor, EventType
from backend.app.models.workspace_runtime_profile import QualityGates
from backend.app.services.conversation import quality_gate_checker as facade_module
from backend.app.services.conversation.quality_gate_checker import (
    QualityGateChecker,
    QualityGateResult,
)
from backend.app.services.conversation.quality_gate_checker_core import checks


class FakeEventStore:
    def __init__(self):
        self.created = []

    def create(self, event):
        self.created.append(event)
        return event


class BrokenEventStore:
    def create(self, event):
        raise RuntimeError("store unavailable")


def test_quality_gate_checker_method_surface_and_result_defaults():
    expected = [
        "check_quality_gates",
        "_record_quality_gate_event",
        "_check_lint",
        "_check_tests",
        "_check_docs",
        "_check_changelist",
        "_check_rollback_plan",
        "_check_citations",
    ]

    first = QualityGateResult(passed=True)
    second = QualityGateResult(passed=True)

    assert [name for name in expected if not hasattr(QualityGateChecker, name)] == []
    assert first.failed_gates == []
    assert first.details == {}
    assert first.failed_gates is not second.failed_gates
    assert first.details is not second.details


def test_quality_gate_checker_facade_delegates(monkeypatch):
    checker = QualityGateChecker(
        workspace_id="ws_1",
        project_path="/tmp/project",
        execution_id="exec_1",
        profile_id="profile_1",
        event_store=object(),
    )
    observed = {}

    def fake_check_quality_gates(**kwargs):
        observed["quality"] = kwargs
        return QualityGateResult(passed=True)

    def fake_record_event(**kwargs):
        observed["event"] = kwargs

    monkeypatch.setattr(
        facade_module,
        "check_quality_gates_helper",
        fake_check_quality_gates,
    )
    monkeypatch.setattr(facade_module, "record_quality_gate_event", fake_record_event)
    monkeypatch.setattr(
        facade_module,
        "check_lint",
        lambda **kwargs: {"helper": "lint", **kwargs},
    )
    monkeypatch.setattr(
        facade_module,
        "check_tests",
        lambda **kwargs: {"helper": "tests", **kwargs},
    )
    monkeypatch.setattr(
        facade_module,
        "check_docs",
        lambda **kwargs: {"helper": "docs", **kwargs},
    )
    monkeypatch.setattr(
        facade_module,
        "check_changelist",
        lambda **kwargs: {"helper": "changelist", **kwargs},
    )
    monkeypatch.setattr(
        facade_module,
        "check_rollback_plan",
        lambda **kwargs: {"helper": "rollback", **kwargs},
    )
    monkeypatch.setattr(
        facade_module,
        "check_citations",
        lambda **kwargs: {"helper": "citations", **kwargs},
    )

    quality_gates = QualityGates()
    result = QualityGateResult(passed=True)

    assert checker.check_quality_gates(quality_gates=quality_gates).passed is True
    checker._record_quality_gate_event(quality_gates, result)
    assert checker._check_lint(["app.py"])["project_path"] == "/tmp/project"
    assert checker._check_tests()["project_path"] == "/tmp/project"
    assert checker._check_docs(["README.md"])["changed_files"] == ["README.md"]
    assert checker._check_changelist(["app.py"])["changed_files"] == ["app.py"]
    assert checker._check_rollback_plan({"rollback_plan": "restore"})[
        "execution_result"
    ] == {"rollback_plan": "restore"}
    assert checker._check_citations({"output": "[1]"})["execution_result"] == {
        "output": "[1]"
    }
    assert observed["quality"]["checker"] is checker
    assert observed["event"]["event_store"] is checker.event_store
    assert observed["event"]["execution_id"] == "exec_1"


def test_check_quality_gates_aggregates_enabled_gate_failures(monkeypatch):
    checker = QualityGateChecker()
    recorded = {}

    monkeypatch.setattr(
        checker,
        "_check_lint",
        lambda changed_files=None: {
            "passed": False,
            "output": "",
            "errors": ["lint error"],
        },
    )
    monkeypatch.setattr(
        checker,
        "_check_tests",
        lambda: {"passed": True, "output": "", "errors": []},
    )
    monkeypatch.setattr(
        checker,
        "_check_docs",
        lambda changed_files=None: {
            "passed": False,
            "output": "No documentation files were updated",
            "errors": ["Documentation update required but no doc files changed"],
        },
    )
    monkeypatch.setattr(
        checker,
        "_check_changelist",
        lambda changed_files=None: {
            "passed": True,
            "output": "Change list provided (1 files)",
            "errors": [],
        },
    )
    monkeypatch.setattr(
        checker,
        "_check_rollback_plan",
        lambda execution_result=None: {
            "passed": True,
            "output": "Rollback plan provided",
            "errors": [],
        },
    )
    monkeypatch.setattr(
        checker,
        "_check_citations",
        lambda execution_result=None: {
            "passed": False,
            "output": "No citations found in output",
            "errors": ["Citations required but not found in output"],
        },
    )
    monkeypatch.setattr(
        checker,
        "_record_quality_gate_event",
        lambda quality_gates, result: recorded.update(
            {"quality_gates": quality_gates, "result": result}
        ),
    )

    result = checker.check_quality_gates(
        quality_gates=QualityGates(
            require_lint=True,
            require_tests=True,
            require_docs=True,
            require_changelist=True,
            require_rollback_plan=True,
            require_citations=True,
        ),
        execution_result={"output": "No references", "rollback_plan": "restore"},
        changed_files=["backend/app/service.py"],
    )

    assert result.passed is False
    assert result.failed_gates == ["lint", "docs", "citations"]
    assert sorted(result.details) == ["citations", "docs", "lint"]
    assert recorded["result"] is result


def test_record_quality_gate_event_preserves_payload_and_fail_open():
    event_store = FakeEventStore()
    checker = QualityGateChecker(
        workspace_id="ws_1",
        execution_id="exec_1",
        profile_id="profile_1",
        event_store=event_store,
    )

    checker._record_quality_gate_event(
        QualityGates(require_lint=True, require_tests=True),
        QualityGateResult(
            passed=False,
            failed_gates=["lint"],
            details={"lint": {"passed": False}},
        ),
    )

    event = event_store.created[0]
    assert event.actor == EventActor.SYSTEM
    assert event.event_type == EventType.QUALITY_GATE_CHECK
    assert event.workspace_id == "ws_1"
    assert event.profile_id == "profile_1"
    assert event.payload["execution_id"] == "exec_1"
    assert event.payload["passed"] is False
    assert event.payload["failed_gates"] == ["lint"]
    assert event.payload["enabled_gates"]["require_lint"] is True
    assert event.payload["enabled_gates"]["require_tests"] is True

    broken_checker = QualityGateChecker(
        execution_id="exec_2",
        event_store=BrokenEventStore(),
    )
    broken_checker._record_quality_gate_event(QualityGates(), QualityGateResult(True))


def test_policy_checks_preserve_fail_open_and_fail_close_behavior():
    assert checks.check_docs(["docs/readme.md"])["passed"] is True
    assert checks.check_docs(["backend/app/service.py"]) == {
        "passed": False,
        "output": "No documentation files were updated",
        "errors": ["Documentation update required but no doc files changed"],
    }
    assert checks.check_docs(None)["passed"] is True
    assert checks.check_changelist(["a.py"])["output"] == "Change list provided (1 files)"
    assert checks.check_changelist(None)["passed"] is True
    assert checks.check_rollback_plan({"rollback_plan": "restore"})["passed"] is True
    assert checks.check_rollback_plan(None)["passed"] is True
    assert checks.check_citations({"output": "## References\n[1]"})["passed"] is True
    assert checks.check_citations({"output": "\u53c2\u8003\u6587\u732e"})["passed"] is True
    assert checks.check_citations({"output": "plain text"}) == {
        "passed": False,
        "output": "No citations found in output",
        "errors": ["Citations required but not found in output"],
    }
    assert checks.check_citations(None)["passed"] is True


def test_lint_check_preserves_ruff_flake8_and_fail_open_paths(monkeypatch):
    monkeypatch.setattr(
        checks.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="clean",
            stderr="",
        ),
    )
    assert checks.check_lint(project_path="/tmp/project") == {
        "passed": True,
        "output": "clean",
        "errors": [],
    }

    monkeypatch.setattr(
        checks.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="out",
            stderr="err\nmore",
        ),
    )
    assert checks.check_lint(project_path="/tmp/project", changed_files=["a.py"]) == {
        "passed": False,
        "output": "out",
        "errors": ["err", "more"],
        "tool": "ruff",
    }

    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 1:
            raise FileNotFoundError()
        return SimpleNamespace(returncode=0, stdout="flake8 clean", stderr="")

    monkeypatch.setattr(checks.subprocess, "run", fake_run)
    assert checks.check_lint(project_path="/tmp/project") == {
        "passed": True,
        "output": "flake8 clean",
        "errors": [],
    }
    assert calls == [["ruff", "check", "."], ["flake8", "."]]

    monkeypatch.setattr(
        checks.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert checks.check_lint(project_path="/tmp/project") == {
        "passed": True,
        "output": "Lint check error: boom",
        "errors": [],
    }


def test_test_check_preserves_success_failure_and_fail_open(monkeypatch):
    monkeypatch.setattr(
        checks.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="tests passed",
            stderr="",
        ),
    )
    assert checks.check_tests(project_path="/tmp/project") == {
        "passed": True,
        "output": "tests passed",
        "errors": [],
    }

    monkeypatch.setattr(
        checks.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="failed",
            stderr="trace",
        ),
    )
    assert checks.check_tests(project_path="/tmp/project") == {
        "passed": False,
        "output": "failed",
        "errors": ["trace"],
        "tool": "pytest",
    }

    monkeypatch.setattr(
        checks.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    assert checks.check_tests(project_path="/tmp/project") == {
        "passed": True,
        "output": "No test tool available",
        "errors": [],
    }

    monkeypatch.setattr(
        checks.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert checks.check_tests(project_path="/tmp/project") == {
        "passed": True,
        "output": "Test check error: boom",
        "errors": [],
    }
