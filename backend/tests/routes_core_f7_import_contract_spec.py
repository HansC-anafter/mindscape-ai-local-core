import importlib
import sys


EXPECTED_AGENT_IDS = {
    "aider",
    "claude_code_cli",
    "codex_cli",
    "gemini_cli",
    "langgraph",
    "openclaw",
}


class FakeMindscapeStoreForImport:
    db_path = ":memory:"


class FakeSystemSettingsStoreForImport:
    def __init__(self, *args, **kwargs):
        pass


def _clear_route_modules():
    prefixes = (
        "backend.app.routes.core.sandbox",
        "backend.app.routes.core.sandbox_core",
        "backend.app.routes.core.system_settings",
    )
    for name in list(sys.modules):
        if name.startswith(prefixes):
            del sys.modules[name]


def test_f7_route_facades_preserve_import_contract(monkeypatch):
    from backend.app.services import mindscape_store, system_settings_store

    monkeypatch.setattr(
        mindscape_store,
        "MindscapeStore",
        FakeMindscapeStoreForImport,
        raising=False,
    )
    monkeypatch.setattr(
        system_settings_store,
        "SystemSettingsStore",
        FakeSystemSettingsStoreForImport,
        raising=False,
    )
    _clear_route_modules()

    sandbox = importlib.import_module("backend.app.routes.core.sandbox")
    chat_embedding = importlib.import_module(
        "backend.app.routes.core.system_settings.llm.chat_embedding"
    )
    governance_tools = importlib.import_module(
        "backend.app.routes.core.system_settings.governance_tools"
    )

    assert len(sandbox.router.routes) == 18
    assert len(chat_embedding.router.routes) == 5
    assert set(governance_tools.AGENT_CLI_MAP) == EXPECTED_AGENT_IDS
    assert hasattr(sandbox, "create_sandbox")
    assert hasattr(chat_embedding, "test_chat_model_connection")
    assert hasattr(governance_tools, "install_agent_cli")
