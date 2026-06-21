from __future__ import annotations

import base64

import pytest

from backend.app.services.tools.github import github_tools
from backend.app.services.tools.github.github_tools_core import contents


class FakeResponse:
    def __init__(self, status, payload, text=""):
        self.status = status
        self.payload = payload
        self.text_value = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload

    async def text(self):
        return self.text_value


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None, params=None):
        self.requests.append(
            {
                "url": url,
                "headers": headers,
                "params": params,
            }
        )
        return self.response


def install_fake_session(monkeypatch, response):
    session = FakeSession(response)
    monkeypatch.setattr(contents.aiohttp, "ClientSession", lambda: session)
    return session


def test_public_factory_preserves_tool_order_and_names():
    tools = github_tools.create_github_tools("token")

    assert [tool.metadata.name for tool in tools] == [
        "github_list_repos",
        "github_read_file",
        "github_create_issue",
        "github_list_issues",
        "github_create_pr",
        "github_search_code",
    ]


def test_public_lookup_returns_expected_tool_class():
    tool = github_tools.get_github_tool_by_name("github_create_pr", "token")

    assert isinstance(tool, github_tools.GitHubCreatePRTool)
    assert github_tools.get_github_tool_by_name("unknown", "token") is None


@pytest.mark.asyncio
async def test_read_file_decodes_base64_content_without_live_network(monkeypatch):
    encoded = base64.b64encode(b"hello from github").decode("ascii")
    response = FakeResponse(
        200,
        {
            "name": "README.md",
            "path": "README.md",
            "sha": "abc123",
            "size": 17,
            "content": encoded,
            "encoding": "base64",
        },
    )
    session = install_fake_session(monkeypatch, response)
    tool = github_tools.GitHubReadFileTool("secret-token")

    result = await tool.execute("owner", "repo", "README.md", ref="main")

    assert result == {
        "success": True,
        "name": "README.md",
        "path": "README.md",
        "sha": "abc123",
        "size": 17,
        "content": "hello from github",
        "encoding": "base64",
    }
    assert session.requests == [
        {
            "url": "https://api.github.com/repos/owner/repo/contents/README.md",
            "headers": {
                "Authorization": "token secret-token",
                "Accept": "application/vnd.github.v3+json",
            },
            "params": {"ref": "main"},
        }
    ]


@pytest.mark.asyncio
async def test_read_file_preserves_github_error_message(monkeypatch):
    response = FakeResponse(404, {}, "missing")
    install_fake_session(monkeypatch, response)
    tool = github_tools.GitHubReadFileTool("secret-token")

    with pytest.raises(Exception, match="GitHub API error: 404 - missing"):
        await tool.execute("owner", "repo", "missing.md")
