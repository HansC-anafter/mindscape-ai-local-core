from pathlib import Path

import pytest

from backend.app.services.tools.base import ToolConnection
from backend.app.services.tools.wordpress import wordpress_tools


def _connection():
    return ToolConnection(
        id="wp-test",
        tool_type="wordpress",
        base_url="https://example.test/",
        api_key="admin",
        api_secret="app-password",
    )


def test_legacy_facade_reexports_wordpress_tools():
    expected_names = [
        "WordPressListPostsTool",
        "WordPressGetPostTool",
        "WordPressCreateDraftTool",
        "WordPressUpdatePostTool",
        "WordPressListOrdersTool",
        "WordPressUpdateOrderStatusTool",
        "WordPressCallPluginEndpointTool",
        "create_wordpress_tools",
        "get_wordpress_tool_by_name",
        "validate_wp_connection",
    ]

    for name in expected_names:
        assert hasattr(wordpress_tools, name)


def test_create_wordpress_tools_preserves_order_and_names():
    tools = wordpress_tools.create_wordpress_tools(_connection())

    assert [tool.metadata.name for tool in tools] == [
        "wordpress.list_posts",
        "wordpress.get_post",
        "wordpress.create_draft",
        "wordpress.update_post",
        "wordpress.list_orders",
        "wordpress.update_order_status",
        "wordpress.call_plugin_endpoint",
    ]


def test_get_wordpress_tool_by_name_preserves_mapping_and_error():
    tool = wordpress_tools.get_wordpress_tool_by_name(
        _connection(),
        "wordpress.update_order_status",
    )

    assert isinstance(tool, wordpress_tools.WordPressUpdateOrderStatusTool)
    with pytest.raises(ValueError, match="Unknown tool name: wordpress.missing"):
        wordpress_tools.get_wordpress_tool_by_name(_connection(), "wordpress.missing")


def test_helper_modules_do_not_define_new_resource_paths():
    repo_root = Path(__file__).resolve().parents[3]
    source_paths = [
        "backend/app/services/tools/wordpress/wordpress_tools.py",
        "backend/app/services/tools/wordpress/wordpress_client.py",
        "backend/app/services/tools/wordpress/wordpress_content_tools.py",
        "backend/app/services/tools/wordpress/wordpress_commerce_tools.py",
        "backend/app/services/tools/wordpress/wordpress_plugin_tools.py",
    ]
    helper_paths = source_paths[1:]
    disallowed_markers = [
        "APIRouter",
        "router =",
        "@router",
        "create_engine",
        "sessionmaker",
        "psycopg2",
        "PgBouncer",
        "create_task",
        "subprocess",
        "Thread(",
        "Process(",
        "setInterval",
        "wordpress_tools_v2",
    ]

    for relative_path in source_paths:
        text = (repo_root / relative_path).read_text(encoding="utf-8")
        for marker in disallowed_markers:
            assert marker not in text

    for relative_path in helper_paths:
        text = (repo_root / relative_path).read_text(encoding="utf-8")
        assert "def create_wordpress_tools" not in text
        assert "def get_wordpress_tool_by_name" not in text
