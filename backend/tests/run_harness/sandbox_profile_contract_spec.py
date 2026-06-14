from backend.app.models.run_harness import RunHarnessWorkspaceBoundary, SandboxProfile


def test_sandbox_defaults_fail_closed() -> None:
    profile = SandboxProfile(
        profile_ref="sandbox-1",
        workspace_boundary=RunHarnessWorkspaceBoundary(workspace_id="workspace-1"),
    )
    assert profile.workspace_boundary.allow_host_access is False
    assert profile.credential_exposure.allow_raw_credentials is False
    assert profile.context_quarantine.allow_untrusted_context is False

