import asyncio
import os
import time

from backend.app.routes.core.tools import filtered, manifest_tools


def _write_manifest(path, *, tool_code):
    path.write_text(
        "\n".join(
            (
                "code: sample_pack",
                "tools:",
                f"  - code: {tool_code}",
                "    description: Sample tool",
                "",
            )
        ),
        encoding="utf-8",
    )


def test_filtered_tools_collects_tools_without_blocking_event_loop(monkeypatch):
    def _slow_collect(*_args, **_kwargs):
        time.sleep(0.1)
        return []

    monkeypatch.setattr(filtered, "_collect_all_tools", _slow_collect)

    async def _run():
        request_task = asyncio.create_task(
            filtered.list_filtered_tools(
                filtered.FilteredToolsRequest(include_playbooks=False),
                registry=object(),
                playbook_service=object(),
            )
        )
        await asyncio.sleep(0.02)
        assert not request_task.done()
        response = await request_task
        assert response.meta.tool_count == 0

    asyncio.run(_run())


def test_manifest_tool_cache_reuses_unchanged_fingerprint(tmp_path, monkeypatch):
    capability_dir = tmp_path / "sample_pack"
    capability_dir.mkdir()
    manifest_path = capability_dir / "manifest.yaml"
    _write_manifest(manifest_path, tool_code="first")
    fingerprint = manifest_tools._installed_manifest_fingerprint(tmp_path)
    manifest_tools._load_manifest_tools_for_fingerprint.cache_clear()

    safe_load = manifest_tools.yaml.safe_load
    parse_count = 0

    def _counted_safe_load(value):
        nonlocal parse_count
        parse_count += 1
        return safe_load(value)

    monkeypatch.setattr(manifest_tools.yaml, "safe_load", _counted_safe_load)

    first = manifest_tools._load_manifest_tools_for_fingerprint(fingerprint)
    second = manifest_tools._load_manifest_tools_for_fingerprint(fingerprint)

    assert [tool.tool_id for tool in first] == ["sample_pack.first"]
    assert second is first
    assert parse_count == 1


def test_manifest_tool_cache_invalidates_after_manifest_change(tmp_path):
    capability_dir = tmp_path / "sample_pack"
    capability_dir.mkdir()
    manifest_path = capability_dir / "manifest.yaml"
    _write_manifest(manifest_path, tool_code="first")
    manifest_tools._load_manifest_tools_for_fingerprint.cache_clear()

    first_fingerprint = manifest_tools._installed_manifest_fingerprint(tmp_path)
    first = manifest_tools._load_manifest_tools_for_fingerprint(first_fingerprint)

    _write_manifest(manifest_path, tool_code="second_with_new_size")
    stat = manifest_path.stat()
    os.utime(manifest_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1))
    second_fingerprint = manifest_tools._installed_manifest_fingerprint(tmp_path)
    second = manifest_tools._load_manifest_tools_for_fingerprint(second_fingerprint)

    assert first_fingerprint != second_fingerprint
    assert [tool.tool_id for tool in first] == ["sample_pack.first"]
    assert [tool.tool_id for tool in second] == [
        "sample_pack.second_with_new_size"
    ]
