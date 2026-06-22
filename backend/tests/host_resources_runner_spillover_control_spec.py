import pytest

from backend.app.services.host_resources import runner_spillover_control


@pytest.mark.asyncio
async def test_spillover_status_blocks_when_device_node_tool_missing(monkeypatch):
    async def _list_device_node_tools(**_kwargs):
        return ["host_resource_probe"]

    monkeypatch.setattr(
        runner_spillover_control,
        "list_device_node_tools",
        _list_device_node_tools,
    )

    result = await runner_spillover_control.runner_spillover_status()

    assert result["accepted"] is False
    assert result["reason"] == "spillover_control_tool_unavailable"
    assert result["required_tool"] == "host_resource_runner_spillover_control"


@pytest.mark.asyncio
async def test_spillover_action_normalizes_payload_and_calls_fixed_tool(monkeypatch):
    received = {}

    async def _list_device_node_tools(**_kwargs):
        return ["host_resource_runner_spillover_control"]

    async def _call_host_resource_runner_spillover_control(arguments):
        received.update(arguments)
        return {
            "accepted": True,
            "action": arguments["action"],
            "profile_code": arguments["profile_code"],
            "max_inflight": arguments["max_inflight"],
        }

    monkeypatch.setattr(
        runner_spillover_control,
        "list_device_node_tools",
        _list_device_node_tools,
    )
    monkeypatch.setattr(
        runner_spillover_control,
        "call_host_resource_runner_spillover_control",
        _call_host_resource_runner_spillover_control,
    )

    result = await runner_spillover_control.runner_spillover_action(
        {
            "action": "start",
            "profile_code": "browser_local",
            "max_inflight": 99,
        }
    )

    assert result["accepted"] is True
    assert result["action"] == "start"
    assert result["profile_code"] == "browser_local"
    assert result["max_inflight"] == 4
    assert received == {
        "action": "start",
        "profile_code": "browser_local",
        "max_inflight": 4,
    }


@pytest.mark.asyncio
async def test_spillover_defaults_to_default_local_maintenance_capacity(monkeypatch):
    received = {}

    async def _list_device_node_tools(**_kwargs):
        return ["host_resource_runner_spillover_control"]

    async def _call_host_resource_runner_spillover_control(arguments):
        received.update(arguments)
        return {
            "accepted": True,
            "action": arguments["action"],
            "profile_code": arguments["profile_code"],
            "max_inflight": arguments["max_inflight"],
        }

    monkeypatch.setattr(
        runner_spillover_control,
        "list_device_node_tools",
        _list_device_node_tools,
    )
    monkeypatch.setattr(
        runner_spillover_control,
        "call_host_resource_runner_spillover_control",
        _call_host_resource_runner_spillover_control,
    )

    result = await runner_spillover_control.runner_spillover_action(
        {
            "action": "start",
        }
    )

    assert result["accepted"] is True
    assert result["profile_code"] == "default_local"
    assert result["max_inflight"] == 1
    assert received == {
        "action": "start",
        "profile_code": "default_local",
        "max_inflight": 1,
    }


@pytest.mark.asyncio
async def test_default_local_browser_spillover_override_stays_temporary(monkeypatch):
    received = {}

    async def _list_device_node_tools(**_kwargs):
        return ["host_resource_runner_spillover_control"]

    async def _call_host_resource_runner_spillover_control(arguments):
        received.update(arguments)
        return {
            "accepted": True,
            "action": arguments["action"],
            "profile_code": arguments["profile_code"],
            "max_inflight": arguments["max_inflight"],
        }

    monkeypatch.setattr(
        runner_spillover_control,
        "list_device_node_tools",
        _list_device_node_tools,
    )
    monkeypatch.setattr(
        runner_spillover_control,
        "call_host_resource_runner_spillover_control",
        _call_host_resource_runner_spillover_control,
    )

    result = await runner_spillover_control.runner_spillover_action(
        {
            "action": "start",
            "profile_code": "default_local_browser",
        }
    )

    assert result["accepted"] is True
    assert result["profile_code"] == "default_local_browser"
    assert result["max_inflight"] == 1
    assert received == {
        "action": "start",
        "profile_code": "default_local_browser",
        "max_inflight": 1,
    }


@pytest.mark.asyncio
async def test_spillover_action_rejects_unsupported_profile():
    with pytest.raises(ValueError, match="unsupported_spillover_profile"):
        await runner_spillover_control.runner_spillover_action(
            {
                "action": "start",
                "profile_code": "unknown",
            }
        )


@pytest.mark.asyncio
async def test_spillover_action_accepts_custom_profile_with_required_fields(monkeypatch):
    received = {}

    async def _list_device_node_tools(**_kwargs):
        return ["host_resource_runner_spillover_control"]

    async def _call_host_resource_runner_spillover_control(arguments):
        received.update(arguments)
        return {
            "accepted": True,
            "action": arguments["action"],
            "profile_code": arguments["profile_code"],
        }

    monkeypatch.setattr(
        runner_spillover_control,
        "list_device_node_tools",
        _list_device_node_tools,
    )
    monkeypatch.setattr(
        runner_spillover_control,
        "call_host_resource_runner_spillover_control",
        _call_host_resource_runner_spillover_control,
    )

    result = await runner_spillover_control.runner_spillover_action(
        {
            "action": "start",
            "profile_code": "35b_synthesis",
            "accepted_partitions": "decision_synthesis",
            "accepted_resource_classes": "compute",
            "accepted_capability_codes": "decision_assets.synthesize",
            "runtime_endpoint": "http://host.docker.internal:8212",
            "runtime_id": "runtime-35b-synthesis",
            "runtime_model": "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit",
            "runtime_max_output_tokens": "4096",
            "runtime_context_budget_tokens": "8192",
            "display_name": "Decision Synthesis 35B Runner",
            "db_application_name": "local-core-runner-decision-synthesis-35b",
            "max_inflight": 1,
        }
    )

    assert result["accepted"] is True
    assert result["profile_code"] == "35b_synthesis"
    assert received == {
        "action": "start",
        "profile_code": "35b_synthesis",
        "max_inflight": 1,
        "accepted_partitions": "decision_synthesis",
        "accepted_resource_classes": "compute",
        "accepted_capability_codes": "decision_assets.synthesize",
        "runtime_endpoint": "http://host.docker.internal:8212",
        "runtime_id": "runtime-35b-synthesis",
        "runtime_model": "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit",
        "runtime_max_output_tokens": "4096",
        "runtime_context_budget_tokens": "8192",
        "display_name": "Decision Synthesis 35B Runner",
        "db_application_name": "local-core-runner-decision-synthesis-35b",
    }


@pytest.mark.asyncio
async def test_spillover_action_rejects_incomplete_custom_profile():
    with pytest.raises(ValueError, match="accepted_capability_codes_required"):
        await runner_spillover_control.runner_spillover_action(
            {
                "action": "start",
                "profile_code": "35b_synthesis",
                "accepted_partitions": "decision_synthesis",
                "accepted_resource_classes": "compute",
                "runtime_endpoint": "http://host.docker.internal:8212",
            }
        )
