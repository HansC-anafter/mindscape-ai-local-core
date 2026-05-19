from types import SimpleNamespace

from backend.app.models.mindscape import EventActor, EventType
from backend.app.services.conversation import policy_guard as facade_module
from backend.app.services.conversation.policy_guard import (
    PolicyCheckResult,
    PolicyGuard,
)
from backend.app.services.conversation.policy_guard_core import messages, runtime


class FakeResolver:
    def __init__(self, policy_info):
        self.policy_info = policy_info
        self.calls = []

    def resolve_policy_info(self, tool_id):
        self.calls.append(tool_id)
        return self.policy_info


class FakeEventStore:
    def __init__(self):
        self.created = []

    def create(self, event):
        self.created.append(event)
        return event


class BrokenEventStore:
    def create(self, event):
        raise RuntimeError("store unavailable")


class FakeChainTracker:
    def __init__(self, length):
        self.length = length

    def get_chain_length(self, previous_tool_id):
        return self.length


def policy_info(capability_code="capability_a", risk_class="readonly"):
    return SimpleNamespace(
        capability_code=capability_code,
        risk_class=risk_class,
    )


def runtime_profile(
    *,
    denylist=None,
    allowlist=None,
    approvals=None,
    max_chain=5,
    confirm_external=True,
    confirm_soft=True,
    auto_read=True,
):
    return SimpleNamespace(
        tool_policy=SimpleNamespace(
            denylist=denylist,
            allowlist=allowlist,
            require_approval_for_capabilities=approvals or [],
            max_tool_call_chain=max_chain,
        ),
        confirmation_policy=SimpleNamespace(
            confirm_external_write=confirm_external,
            confirm_soft_write=confirm_soft,
            auto_read=auto_read,
        ),
    )


def check_with(
    *,
    guard,
    profile=None,
    params=None,
    execution_id=None,
    previous_tool_id=None,
    event_store=None,
):
    return guard.check_tool_call(
        tool_id="tool_a",
        runtime_profile=profile or runtime_profile(),
        tool_call_params=params or {"value": 1},
        tool_registry=object(),
        execution_id=execution_id,
        previous_tool_id=previous_tool_id,
        workspace_id="ws_1",
        profile_id="profile_1",
        event_store=event_store,
    )


def test_policy_guard_method_surface_and_result_defaults():
    expected = [
        "check_tool_call",
        "_build_proposed_action",
        "_record_policy_check_event",
    ]
    result = PolicyCheckResult(True)

    assert [name for name in expected if not hasattr(PolicyGuard, name)] == []
    assert result.allowed is True
    assert result.requires_approval is False
    assert result.reason == ""
    assert result.proposed_action is None
    assert result.user_message is None


def test_policy_guard_facade_delegates(monkeypatch):
    guard = PolicyGuard(strict_mode=True, tool_policy_resolver=FakeResolver(None))
    observed = {}

    def fake_check_tool_call(**kwargs):
        observed["check"] = kwargs
        return PolicyCheckResult(True)

    def fake_record_event(**kwargs):
        observed["event"] = kwargs

    monkeypatch.setattr(facade_module, "check_tool_call_helper", fake_check_tool_call)
    monkeypatch.setattr(
        facade_module,
        "build_proposed_action",
        lambda **kwargs: {"action": kwargs},
    )
    monkeypatch.setattr(facade_module, "record_policy_check_event", fake_record_event)

    assert check_with(guard=guard).allowed is True
    assert guard._build_proposed_action("tool_a", {"value": 1}, "soft_write") == {
        "action": {
            "tool_id": "tool_a",
            "tool_call_params": {"value": 1},
            "risk_class": "soft_write",
        }
    }
    guard._record_policy_check_event(
        tool_id="tool_a",
        capability_code="capability_a",
        risk_class="readonly",
        result=PolicyCheckResult(True),
        execution_id="exec_1",
        workspace_id="ws_1",
        profile_id="profile_1",
        event_store=object(),
    )
    assert observed["check"]["guard"] is guard
    assert observed["event"]["tool_id"] == "tool_a"


def test_tool_missing_strict_and_nonstrict_paths():
    strict_result = check_with(
        guard=PolicyGuard(strict_mode=True, tool_policy_resolver=FakeResolver(None))
    )
    loose_result = check_with(
        guard=PolicyGuard(strict_mode=False, tool_policy_resolver=FakeResolver(None))
    )

    assert strict_result.allowed is False
    assert strict_result.reason == "Tool not found in registry"
    assert strict_result.user_message == messages.tool_not_found_blocked()
    assert loose_result.allowed is True
    assert loose_result.requires_approval is True
    assert loose_result.user_message == messages.tool_not_found_allowed()


def test_missing_capability_strict_and_nonstrict_paths():
    strict_result = check_with(
        guard=PolicyGuard(
            strict_mode=True,
            tool_policy_resolver=FakeResolver(policy_info("unknown", "readonly")),
        )
    )
    loose_result = check_with(
        guard=PolicyGuard(
            strict_mode=False,
            tool_policy_resolver=FakeResolver(policy_info(None, "readonly")),
        )
    )

    assert strict_result.allowed is False
    assert strict_result.reason == "Tool tool_a missing capability_code"
    assert strict_result.user_message == messages.missing_capability_blocked("tool_a")
    assert loose_result.allowed is True
    assert loose_result.requires_approval is True
    assert loose_result.user_message == messages.missing_capability_allowed("tool_a")


def test_denylist_allowlist_and_explicit_approval_paths():
    denied = check_with(
        guard=PolicyGuard(
            strict_mode=True,
            tool_policy_resolver=FakeResolver(policy_info("blocked", "readonly")),
        ),
        profile=runtime_profile(denylist=["blocked"]),
    )
    not_allowed = check_with(
        guard=PolicyGuard(
            strict_mode=True,
            tool_policy_resolver=FakeResolver(policy_info("other", "readonly")),
        ),
        profile=runtime_profile(allowlist=["allowed"]),
    )
    approval = check_with(
        guard=PolicyGuard(
            strict_mode=True,
            tool_policy_resolver=FakeResolver(policy_info("needs_approval", "readonly")),
        ),
        profile=runtime_profile(approvals=["needs_approval"]),
    )

    assert denied.allowed is False
    assert denied.user_message == messages.capability_denied("blocked")
    assert not_allowed.allowed is False
    assert not_allowed.user_message == messages.capability_not_allowed("other")
    assert approval.allowed is True
    assert approval.requires_approval is True
    assert approval.proposed_action == {
        "tool_id": "tool_a",
        "params": {"value": 1},
        "risk_class": "readonly",
        "requires_confirmation": True,
    }


def test_risk_confirmation_readonly_and_default_allow_paths():
    external = check_with(
        guard=PolicyGuard(
            strict_mode=True,
            tool_policy_resolver=FakeResolver(policy_info("writer", "external_write")),
        )
    )
    soft = check_with(
        guard=PolicyGuard(
            strict_mode=True,
            tool_policy_resolver=FakeResolver(policy_info("editor", "soft_write")),
        )
    )
    readonly = check_with(
        guard=PolicyGuard(
            strict_mode=True,
            tool_policy_resolver=FakeResolver(policy_info("reader", "readonly")),
        )
    )
    default = check_with(
        guard=PolicyGuard(
            strict_mode=True,
            tool_policy_resolver=FakeResolver(policy_info("reader", "readonly")),
        ),
        profile=runtime_profile(auto_read=False),
    )

    assert external.allowed is True
    assert external.requires_approval is True
    assert external.user_message == messages.risk_requires_confirmation(
        "writer",
        "external_write",
    )
    assert soft.requires_approval is True
    assert soft.user_message == messages.risk_requires_confirmation(
        "editor",
        "soft_write",
    )
    assert readonly.allowed is True
    assert readonly.requires_approval is False
    assert readonly.reason == "Read-only operation, auto-allowed"
    assert default.allowed is True
    assert default.reason == "No policy restrictions apply"


def test_chain_length_exceeds_max_blocks(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "get_chain_tracker_for_execution",
        lambda execution_id: FakeChainTracker(length=5),
    )

    result = check_with(
        guard=PolicyGuard(
            strict_mode=True,
            tool_policy_resolver=FakeResolver(policy_info("reader", "readonly")),
        ),
        profile=runtime_profile(max_chain=5),
        execution_id="exec_1",
        previous_tool_id="previous",
    )

    assert result.allowed is False
    assert result.reason == "Tool call chain length (6) exceeds maximum (5)"
    assert result.user_message == messages.chain_too_long(6, 5)


def test_policy_check_event_payload_and_fail_open():
    event_store = FakeEventStore()
    guard = PolicyGuard(
        strict_mode=True,
        tool_policy_resolver=FakeResolver(policy_info("reader", "readonly")),
    )

    result = check_with(
        guard=guard,
        execution_id="exec_1",
        event_store=event_store,
    )

    event = event_store.created[0]
    assert event.actor == EventActor.SYSTEM
    assert event.event_type == EventType.POLICY_CHECK
    assert event.workspace_id == "ws_1"
    assert event.profile_id == "profile_1"
    assert event.payload["execution_id"] == "exec_1"
    assert event.payload["tool_id"] == "tool_a"
    assert event.payload["capability_code"] == "reader"
    assert event.payload["risk_class"] == "readonly"
    assert event.payload["allowed"] is result.allowed
    assert event.payload["requires_approval"] is result.requires_approval
    assert event.payload["reason"] == result.reason

    guard._record_policy_check_event(
        tool_id="tool_a",
        capability_code="reader",
        risk_class="readonly",
        result=result,
        execution_id="exec_2",
        workspace_id="ws_1",
        profile_id="profile_1",
        event_store=BrokenEventStore(),
    )


def test_lazy_resolver_requires_registry_when_missing():
    guard = PolicyGuard(strict_mode=True)

    try:
        guard.check_tool_call(
            tool_id="tool_a",
            runtime_profile=runtime_profile(),
            tool_call_params={},
            tool_registry=None,
        )
    except ValueError as exc:
        assert "PolicyGuard requires either tool_registry" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
