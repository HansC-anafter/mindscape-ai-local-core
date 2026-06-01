from pathlib import Path
from types import SimpleNamespace

import yaml

from backend.app.services.orchestration.meeting.prompt_core.tool_inventory_mixin import (
    MeetingPromptToolInventoryMixin,
)


class StubPromptInventory(MeetingPromptToolInventoryMixin):
    def __init__(self, manifest_path: Path):
        self.session = SimpleNamespace(
            workspace_id="ws_demo",
            metadata={"active_capability_code": "ig"},
        )
        self.workspace = SimpleNamespace(id="ws_demo")
        self._manifest_path = manifest_path

    def _capability_manifest_paths(self, pack_id: str) -> list[Path]:
        return [self._manifest_path]


def test_active_pack_inventory_prefers_planner_contract_tools(tmp_path):
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        """
code: ig
tools:
  - name: ig_query_references
    code: ig_query_references
    backend: capabilities.ig.tools.ig_query_references:ig_query_references
    description: Query IG references.
    planner_contract:
      exposed: true
      consumers:
        - meeting_engine
      resource_kind: reference
      effect: read
      workspace_scoped: true
      input_schema: capabilities.ig.tools.schemas:QueryReferencesInput
      output_schema: capabilities.ig.tools.schemas:QueryReferencesOutput
      pagination:
        cursor_field: cursor
        next_cursor_field: next_cursor
        max_limit: 200
      idempotency: none
      audit_fields:
        - workspace_id
  - name: ig_legacy_tool
    code: ig_legacy_tool
    backend: capabilities.ig.tools.legacy:run
    description: Legacy tool.
""",
        encoding="utf-8",
    )

    block = StubPromptInventory(manifest_path)._build_active_pack_tool_inventory_block(
        "ig",
        yaml,
    )

    assert "ig.ig_query_references" in block
    assert "planner_contract effect=read resource=reference" in block
    assert "ig.ig_legacy_tool" not in block
