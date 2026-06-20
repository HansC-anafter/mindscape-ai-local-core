from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services import playbook_registry as registry_module
from backend.app.services.playbook_registry import PlaybookRegistry


def _write_playbook(path: Path, *, code: str, locale: str, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f"playbook_code: {code}",
                f"locale: {locale}",
                f"name: {name}",
                "description: Test playbook",
                "---",
                "",
                f"# {name}",
                "",
                "- Do the thing.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_capability(root: Path, capability_code: str, playbook_code: str) -> Path:
    capability_dir = root / capability_code
    capability_dir.mkdir(parents=True, exist_ok=True)
    (capability_dir / "manifest.yaml").write_text(
        "\n".join(
            [
                f"code: {capability_code}",
                "playbooks:",
                f"  - code: {playbook_code}",
                "    locales: [zh-TW, en]",
                "    path: playbooks/{locale}/{code}.md",
                "    variants:",
                "      - variant_id: fast",
                "        name: Fast",
                "        skip_steps: [1]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_playbook(
        capability_dir / "playbooks" / "zh-TW" / f"{playbook_code}.md",
        code=playbook_code,
        locale="zh-TW",
        name="Welcome ZH",
    )
    _write_playbook(
        capability_dir / "playbooks" / "en" / f"{playbook_code}.md",
        code=playbook_code,
        locale="en",
        name="Welcome EN",
    )
    return capability_dir


def test_directory_loader_preserves_locale_cache_and_variants(tmp_path, monkeypatch):
    activations = []
    monkeypatch.setattr(
        registry_module,
        "_record_loaded_capability_activation",
        lambda **payload: activations.append(payload),
    )
    _write_capability(tmp_path, "demo_pack", "welcome")

    registry = PlaybookRegistry()
    registry._load_playbooks_from_directory(tmp_path)

    playbooks = registry.capability_playbooks["demo_pack"]
    assert playbooks["welcome"].metadata.locale == "zh-TW"
    assert playbooks["welcome:zh-TW"].metadata.name == "Welcome ZH"
    assert playbooks["welcome:en"].metadata.name == "Welcome EN"
    assert playbooks["demo_pack.welcome"].metadata.locale == "en"
    assert registry.get_variant("demo_pack.welcome", "fast")["skip_steps"] == [1]
    assert activations[0]["capability_code"] == "demo_pack"


@pytest.mark.asyncio
async def test_ensure_capability_loaded_scans_only_requested_capability(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        registry_module,
        "_record_loaded_capability_activation",
        lambda **payload: None,
    )
    _write_capability(tmp_path, "demo_pack", "welcome")
    _write_capability(tmp_path, "other_pack", "welcome")

    registry = PlaybookRegistry()
    registry._capabilities_dir = tmp_path

    await registry._ensure_capability_loaded("demo_pack")

    assert set(registry.capability_playbooks) == {"demo_pack"}
    assert registry._loaded_capabilities == {"demo_pack"}
    playbook = await registry.get_playbook("demo_pack.welcome", locale="en")
    assert playbook.metadata.name == "Welcome EN"


def test_capability_invalidation_clears_single_pack_without_full_reset(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        registry_module,
        "_record_loaded_capability_activation",
        lambda **payload: None,
    )
    _write_capability(tmp_path, "demo_pack", "welcome")

    registry = PlaybookRegistry()
    registry._load_playbooks_from_directory(tmp_path)
    registry._loaded = True
    registry._loaded_capabilities.add("demo_pack")

    registry.invalidate_cache(capability_code="demo_pack")

    assert registry._loaded is True
    assert "demo_pack" not in registry.capability_playbooks
    assert "demo_pack" not in registry._loaded_capabilities
    assert "demo_pack.welcome" not in registry._playbook_variants
    assert "welcome" not in registry._playbook_variants
