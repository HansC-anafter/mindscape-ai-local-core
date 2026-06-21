from pathlib import Path

import pytest

from backend.app.services.tools.base import ToolConnection
from backend.app.services.tools.wordpress import wordpress_tools
from backend.app.services.tools.wordpress import wordpress_tools_v2


def _connection() -> ToolConnection:
    return ToolConnection(
        id="wp-v2-test",
        tool_type="wordpress",
        base_url="https://example.test/",
        api_key="admin",
        api_secret="app-password",
    )


def test_v2_exports_reuse_canonical_classes():
    expected_pairs = [
        ("WordPressListPostsTool", wordpress_tools.WordPressListPostsTool),
        ("WordPressGetPostTool", wordpress_tools.WordPressGetPostTool),
        ("WordPressCreateDraftTool", wordpress_tools.WordPressCreateDraftTool),
        ("WordPressUpdatePostTool", wordpress_tools.WordPressUpdatePostTool),
        ("WordPressListOrdersTool", wordpress_tools.WordPressListOrdersTool),
        (
            "WordPressUpdateOrderStatusTool",
            wordpress_tools.WordPressUpdateOrderStatusTool,
        ),
    ]

    for export_name, canonical_class in expected_pairs:
        assert getattr(wordpress_tools_v2, export_name) is canonical_class


def test_v2_factory_preserves_six_tool_order():
    tools = wordpress_tools_v2.create_wordpress_tools(_connection())

    assert [tool.metadata.name for tool in tools] == [
        "wordpress.list_posts",
        "wordpress.get_post",
        "wordpress.create_draft",
        "wordpress.update_post",
        "wordpress.list_orders",
        "wordpress.update_order_status",
    ]


def test_v2_lookup_preserves_mapping_and_error():
    tool = wordpress_tools_v2.get_wordpress_tool_by_name(
        _connection(),
        "wordpress.update_order_status",
    )

    assert isinstance(tool, wordpress_tools.WordPressUpdateOrderStatusTool)
    with pytest.raises(ValueError, match="Unknown tool name: wordpress.missing"):
        wordpress_tools_v2.get_wordpress_tool_by_name(
            _connection(),
            "wordpress.missing",
        )


def test_v2_facade_does_not_own_resource_paths():
    repo_root = Path(__file__).resolve().parents[3]
    text = (
        repo_root
        / "backend/app/services/tools/wordpress/wordpress_tools_v2.py"
    ).read_text(encoding="utf-8")
    disallowed_markers = [
        "aiohttp.ClientSession",
        "WORDPRESS_URL",
        "/wp-json/wp/v2/posts",
        "/wp-json/wc/v3/orders",
        "APIRouter",
        "create_engine",
        "sessionmaker",
        "PgBouncer",
        "create_task",
        "subprocess",
        "Thread(",
        "Process(",
        "setInterval",
        "polling",
    ]

    for marker in disallowed_markers:
        assert marker not in text
