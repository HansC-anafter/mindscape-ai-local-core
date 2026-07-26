from backend.app.services.artifact_disclosure.composition import (
    build_artifact_disclosure_port,
)
from backend.app.services.tools.reporting.report_bundle_graph import (
    collect_report_bundle_graph,
)
from backend.app.services.tools.reporting.report_disclosure_adapter import (
    WorkspaceReportDisclosureAdapter,
)
from backend.app.services.unified_tool_executor_core.governance_context import (
    VerifiedToolExecutionContext,
)
from backend.app.services.workspace_groups.contracts import (
    AuthorizedSharedAssetScope,
    SharedAssetScopeResolution,
    SharedAssetSelector,
)


class _Resolver:
    def __init__(self):
        self.calls = []

    def resolve(self, **kwargs):
        self.calls.append(kwargs)
        return SharedAssetScopeResolution(
            scopes=[
                AuthorizedSharedAssetScope(
                    scope_key="scope-a",
                    active_workspace_id="workspace-a",
                    source_workspace_id="workspace-source",
                    source_workspace_title="Source",
                    group_id="group-a",
                    group_title="Group A",
                    group_revision=7,
                    binding_id="binding-a",
                    resource_id="resource-a",
                    selector=SharedAssetSelector(
                        reference_seed="ref",
                        following_seed="follow",
                        include_future_matches=True,
                    ),
                    active_workspace_owner_user_id="owner-a",
                    group_owner_user_id="owner-a",
                    source_workspace_owner_user_id="owner-a",
                )
            ],
            errors=[],
            scope_fingerprint="f" * 64,
        )


def _context():
    return VerifiedToolExecutionContext(
        snapshot_hash="1" * 64,
        workspace_id="workspace-a",
        actor_user_id="owner-a",
        allowed_workspace_ids=("workspace-a",),
        allowed_group_ids=("group-a",),
        workspace_owner_user_id="owner-a",
        active_group_id="group-a",
        group_owner_user_id="owner-a",
        root_execution_id="root-a",
        trace_id="trace-a",
        source_entry="local",
        selector_lineage=("workspace_package_report",),
        context_sha256="2" * 64,
    )


def _graph(tmp_path):
    sandbox = tmp_path / "sandbox"
    report = sandbox / "reports" / "report.html"
    style = sandbox / "reports" / "style.css"
    report.parent.mkdir(parents=True)
    report.write_text(
        '<link rel="stylesheet" href="style.css">',
        encoding="utf-8",
    )
    style.write_text("body { color: #111; }", encoding="utf-8")
    return collect_report_bundle_graph(
        sandbox_root=sandbox,
        report_path=report,
        include_linked_files=True,
    )


def _manifest(graph):
    return {
        "files": [
            {
                "source_path": item.sandbox_relative_path,
                "source_sha256": item.sha256,
                "origin": "workspace_group_shared",
                "source_workspace_id": "workspace-source",
                "group_id": "group-a",
                "group_revision": 7,
                "binding_id": "binding-a",
                "resource_id": "resource-a",
                "scope_fingerprint": "f" * 64,
            }
            for item in graph.files
        ]
    }


def test_group_provenance_uses_one_resolver_call_for_the_graph(tmp_path):
    graph = _graph(tmp_path)
    resolver = _Resolver()
    adapter = WorkspaceReportDisclosureAdapter(
        disclosure_port=build_artifact_disclosure_port(),
        shared_scope_resolver=resolver,
    )

    plan = adapter.evaluate(
        graph=graph,
        governance_context=_context(),
        distribution_scope="external",
        recipient_ref="recipient:a",
        provenance_manifest=_manifest(graph),
    )

    assert len(resolver.calls) == 1
    assert plan.decision.blocking_codes == ()
    assert plan.decision.share_authorization == (
        "external_review_required"
    )


def test_group_provenance_hash_drift_fails_before_policy(tmp_path):
    graph = _graph(tmp_path)
    resolver = _Resolver()
    manifest = _manifest(graph)
    manifest["files"][0]["source_sha256"] = "0" * 64
    adapter = WorkspaceReportDisclosureAdapter(
        disclosure_port=build_artifact_disclosure_port(),
        shared_scope_resolver=resolver,
    )

    try:
        adapter.evaluate(
            graph=graph,
            governance_context=_context(),
            distribution_scope="external",
            recipient_ref="recipient:a",
            provenance_manifest=manifest,
        )
    except ValueError as exc:
        assert str(exc) == "provenance_source_hash_mismatch"
    else:
        raise AssertionError("hash drift must fail closed")
