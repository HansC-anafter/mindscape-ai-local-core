from types import SimpleNamespace

import pytest

from backend.app.services.tool_slot_resolver import ToolSlotResolution
from backend.app.services.workspace_capability_admission import pinned_tool_slots


class _Resolver:
    def __init__(self):
        self.calls = []

    async def resolve_with_evidence(self, **kwargs):
        self.calls.append(kwargs)
        return ToolSlotResolution(
            slot=kwargs["slot"],
            tool_id="wordpress.divi5_release_adapter",
            mapping_kind="workspace",
            mapping_id="mapping-1",
            mapping_updated_at="2026-07-27T00:00:00+00:00",
        )


@pytest.mark.asyncio
async def test_root_pins_once_and_child_verifies_without_resolution(monkeypatch):
    monkeypatch.setattr(
        pinned_tool_slots,
        "_provider_evidence",
        lambda resolution: {
            "provider_pack": "wordpress",
            "provider_version": "0.2.0",
            "provider_manifest_sha256": "a" * 64,
            "tool_backend": "capabilities.wordpress.tools:release_adapter",
            "tool_artifact_sha256": "b" * 64,
        },
    )
    resolver = _Resolver()
    root_inputs = await pinned_tool_slots.prepare_pinned_tool_slots(
        normalized_inputs={},
        declared_slots=["site_publication.release_adapter"],
        playbook_code="managed_release",
        workspace_id="workspace-1",
        project_id=None,
        resolver=resolver,
    )

    assert len(resolver.calls) == 1
    assert pinned_tool_slots.resolve_pinned_tool_id(
        slot="site_publication.release_adapter",
        playbook_inputs=root_inputs,
    ) == "wordpress.divi5_release_adapter"
    pin = root_inputs["pinned_tool_slots"]["pins"][
        "site_publication.release_adapter"
    ]
    assert pin["tool_artifact_sha256"] == "b" * 64
    assert len(pin["mapping_revision_sha256"]) == 64

    child_inputs = await pinned_tool_slots.prepare_pinned_tool_slots(
        normalized_inputs=dict(root_inputs),
        declared_slots=["site_publication.release_adapter"],
        playbook_code="managed_release",
        workspace_id="workspace-1",
        project_id=None,
        resolver=SimpleNamespace(),
    )
    assert child_inputs["pinned_tool_slots_sha256"] == (
        root_inputs["pinned_tool_slots_sha256"]
    )


def test_pin_hash_tampering_fails_closed(monkeypatch):
    payload = {
        "schema_version": pinned_tool_slots.PIN_SCHEMA_VERSION,
        "playbook_code": "managed_release",
        "root_execution_id": "",
        "workspace_id": "workspace-1",
        "project_id": None,
        "pins": {
            "site_publication.release_adapter": {
                "tool_id": "wordpress.divi5_release_adapter"
            }
        },
    }
    inputs = {
        "admission_pinned_tool_slots": [
            "site_publication.release_adapter"
        ],
        "pinned_tool_slots": payload,
        "pinned_tool_slots_sha256": "0" * 64,
    }

    with pytest.raises(ValueError, match="pinned_tool_slots_hash_mismatch"):
        pinned_tool_slots.resolve_pinned_tool_id(
            slot="site_publication.release_adapter",
            playbook_inputs=inputs,
        )


def test_unpinned_legacy_slot_returns_none():
    assert pinned_tool_slots.resolve_pinned_tool_id(
        slot="legacy.dynamic.slot",
        playbook_inputs={},
    ) is None
