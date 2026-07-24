from backend.app.services.external_agents.bridge import codex_cli_runner


def test_auto_resolution_includes_chatgpt_bundle_and_selects_newest(monkeypatch):
    chatgpt_binary = "/Applications/ChatGPT.app/Contents/Resources/codex"
    legacy_binary = "/Applications/Codex.app/Contents/Resources/codex"
    path_binary = "/opt/homebrew/bin/codex"
    available = {
        chatgpt_binary: chatgpt_binary,
        legacy_binary: legacy_binary,
        "codex": path_binary,
    }
    versions = {
        chatgpt_binary: (0, 144, 0, 0, "alpha.4"),
        legacy_binary: (0, 39, 0, 1, ""),
        path_binary: (0, 39, 0, 1, ""),
    }

    monkeypatch.setattr(
        codex_cli_runner,
        "_resolve_codex_cli_candidate",
        lambda candidate: available.get(str(candidate)),
    )
    monkeypatch.setattr(
        codex_cli_runner,
        "get_codex_cli_version_sort_key",
        lambda candidate: versions[candidate],
    )
    monkeypatch.delenv("CODEX_CLI_PATH", raising=False)

    candidates = codex_cli_runner._iter_auto_codex_cli_candidates()

    assert candidates[:3] == [chatgpt_binary, legacy_binary, path_binary]
    assert codex_cli_runner.resolve_codex_cli_binary() == chatgpt_binary


def test_explicit_binary_still_overrides_auto_resolution(monkeypatch):
    explicit_binary = "/custom/codex"
    monkeypatch.setattr(
        codex_cli_runner,
        "_resolve_codex_cli_candidate",
        lambda candidate: explicit_binary if candidate == explicit_binary else None,
    )

    assert codex_cli_runner.resolve_codex_cli_binary(explicit_binary) == explicit_binary
