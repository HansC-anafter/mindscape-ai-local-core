from pydantic import ValidationError
import pytest

from backend.app.models.run_harness import RunHarnessWorkspaceBoundary


def test_workspace_boundary_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RunHarnessWorkspaceBoundary(
            workspace_id="workspace-1",
            writable_roots=["/workspace"],
            unexpected=True,
        )

