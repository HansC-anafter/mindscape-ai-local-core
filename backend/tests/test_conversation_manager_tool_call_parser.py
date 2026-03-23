import pytest

from backend.app.services.playbook.conversation_manager_core.tool_call_parser import (
    normalize_tool_call_json,
    normalize_tool_name,
    parse_python_style_tool_call,
    parse_tool_calls_from_response,
)


def test_normalize_tool_name_maps_common_aliases():
    assert normalize_tool_name("filesystem.list_files") == "filesystem_list_files"
    assert normalize_tool_name("read_file") == "filesystem_read_file"
    assert normalize_tool_name("custom_tool") == "custom_tool"


def test_normalize_tool_call_json_handles_tool_calls_array():
    normalized = normalize_tool_call_json(
        {
            "tool_calls": [
                {
                    "tool_name": "fs.read_file",
                    "parameters": {"path": "README.md"},
                }
            ]
        }
    )

    assert normalized == {
        "tool_name": "filesystem_read_file",
        "parameters": {"path": "README.md"},
    }


def test_parse_python_style_tool_call_parses_alias_and_bool_args():
    parsed = parse_python_style_tool_call(
        "print(fs.search(path='src', recursive=True))"
    )

    assert parsed == [
        {
            "tool_name": "filesystem_search",
            "parameters": {"path": "src", "recursive": True},
        }
    ]


def test_parse_tool_calls_from_response_handles_direct_json():
    parsed = parse_tool_calls_from_response(
        '{"tool_name":"filesystem.list_files","parameters":{"path":"."}}'
    )

    assert parsed == [
        {
            "tool_name": "filesystem_list_files",
            "parameters": {"path": "."},
        }
    ]
