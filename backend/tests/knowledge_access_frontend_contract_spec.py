"""Static request-budget guard for the Knowledge access governance UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SURFACE = (
    ROOT
    / "web-console/src/app/workspaces/[workspaceId]/governance/components"
    / "knowledgeAccess"
)


def test_knowledge_access_ui_has_no_polling_or_success_refetch() -> None:
    content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(SURFACE.glob("*.ts*"))
    )
    for forbidden in (
        "setInterval(",
        "setTimeout(",
        "refreshInterval",
        "useSWR(",
    ):
        assert forbidden not in content
    hook = (SURFACE / "useKnowledgeAccess.ts").read_text(
        encoding="utf-8"
    )
    assert hook.count("loadKnowledgeAccessSummary(") == 1
    assert hook.count("loadKnowledgeAccessDetail(") == 1
    assert "setDetail(replaced)" in hook
    assert "setActionReceipt(receipt)" in hook


def test_knowledge_access_api_uses_one_facade_collection() -> None:
    api = (SURFACE / "api.ts").read_text(encoding="utf-8")
    assert "/knowledge-access`" in api
    assert "method: 'PUT'" in api
    assert "method: 'POST'" in api
    assert "/actions`" in api
    assert api.count("fetch(") == 4
