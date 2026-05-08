from types import SimpleNamespace

import pytest

from backend.app.services.cloud_connector import messaging_handler as mh


def test_collects_asset_candidates_from_nested_meeting_payload():
    payload = {
        "dispatch_result": {
            "execution_id": "exec_123",
            "outputs": [
                {
                    "artifact_id": "artifact_1",
                    "title": "Storyboard",
                    "metadata": {
                        "actual_file_path": "/tmp/storyboard.md",
                        "artifact_kind": "storyboard",
                    },
                }
            ],
        }
    }

    candidates = mh._collect_asset_candidates(payload)
    assert candidates == [
        {
            "artifact_id": "artifact_1",
            "artifact_kind": "storyboard",
            "title": "Storyboard",
            "file_path": "/tmp/storyboard.md",
            "url": None,
        }
    ]
    assert mh._collect_execution_ids(payload) == ["exec_123"]


@pytest.mark.asyncio
async def test_materialized_assets_do_not_expose_absolute_path_without_public_url(
    tmp_path,
    monkeypatch,
):
    for key in mh._ASSET_UPLOAD_BASE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    file_path = tmp_path / "deliverable.md"
    file_path.write_text("# done", encoding="utf-8")

    assets = await mh._materialize_page_assets(
        [
            {
                "artifact_id": "artifact_1",
                "artifact_kind": "markdown",
                "file_path": str(file_path),
            }
        ],
        workspace_id="workspace_1",
    )
    rendered = mh._format_page_assets_md(assets)

    assert assets[0]["url"] is None
    assert "deliverable.md" in rendered
    assert str(tmp_path) not in rendered
    assert "尚未建立公開下載連結" in rendered


@pytest.mark.asyncio
async def test_materialized_assets_use_uploaded_public_url(tmp_path, monkeypatch):
    file_path = tmp_path / "storyboard.md"
    file_path.write_text("# storyboard", encoding="utf-8")

    async def fake_upload(path, *, workspace_id):
        assert path == file_path
        assert workspace_id == "workspace_1"
        return f"https://agent.example/assets/{path.name}"

    monkeypatch.setattr(mh, "_upload_page_asset", fake_upload)

    assets = await mh._materialize_page_assets(
        [
            {
                "artifact_id": "artifact_1",
                "artifact_kind": "storyboard",
                "title": "Storyboard",
                "file_path": str(file_path),
            }
        ],
        workspace_id="workspace_1",
    )
    rendered = mh._format_page_assets_md(assets)

    assert assets[0]["url"] == "https://agent.example/assets/storyboard.md"
    assert (
        "- [Storyboard](https://agent.example/assets/storyboard.md)"
        in rendered
    )


@pytest.mark.asyncio
async def test_build_meeting_assets_loads_execution_artifacts(monkeypatch):
    class FakeArtifactsStore:
        def get_artifact(self, artifact_id):
            return None

        def list_by_execution_id(self, execution_id):
            assert execution_id == "exec_123"
            return [
                SimpleNamespace(
                    id="artifact_1",
                    title="Storyboard",
                    artifact_type=SimpleNamespace(value="draft"),
                    storage_ref="https://agent.example/assets/storyboard.md",
                    metadata={},
                )
            ]

        def list_artifacts_by_task(self, task_id):
            return []

    store = SimpleNamespace(artifacts=FakeArtifactsStore())
    pipeline_result = SimpleNamespace(
        task_ir_artifacts=[],
        artifact_file_paths=[],
        artifact_ids=[],
        task_ir_id="task_1",
        dispatch_result={"execution_id": "exec_123"},
    )
    handler = mh.MessagingHandler(websocket=SimpleNamespace(), device_id="device_1")

    rendered = await handler._build_meeting_assets_md(
        store, "workspace_1", pipeline_result
    )

    assert "## 📎 產出檔案" in rendered
    assert "[Storyboard](https://agent.example/assets/storyboard.md)" in rendered
