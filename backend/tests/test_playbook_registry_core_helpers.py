import logging
from pathlib import Path
from types import SimpleNamespace

from backend.app.services.playbook_registry_core.cache import (
    invalidate_registry_cache,
)
from backend.app.services.playbook_registry_core.lookup import (
    cache_capability_playbook,
    get_cached_capability_playbook,
    load_direct_capability_playbook,
)
from backend.app.services.playbook_registry_core.metadata import (
    enrich_playbook_metadata,
    load_user_playbooks,
    matches_filters,
)
from backend.app.services.playbook_registry_core.search import (
    collect_playbook_metadata,
    lookup_local_playbook,
    resolve_playbook_lookup_request,
)


LOGGER = logging.getLogger(__name__)


def _make_playbook(
    *,
    code: str,
    locale: str = "en",
    tags=None,
    name: str | None = None,
    description: str | None = None,
):
    metadata = SimpleNamespace(
        playbook_code=code,
        locale=locale,
        tags=list(tags or []),
        name=name,
        description=description,
        capability_code=None,
        owner_type=None,
        owner_id=None,
        visibility=None,
    )
    return SimpleNamespace(metadata=metadata)


def test_enrich_playbook_metadata_prefers_requested_locale(tmp_path):
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "demo.json").write_text(
        """
        {
          "display_name": {"en": "English Name", "ja": "Japanese Name"},
          "description": {"en": "English Description", "ja": "Japanese Description"}
        }
        """.strip(),
        encoding="utf-8",
    )
    playbook = _make_playbook(code="demo")

    enrich_playbook_metadata(
        playbook,
        tmp_path,
        "demo",
        "ja",
        logger=LOGGER,
    )

    assert playbook.metadata.name == "Japanese Name"
    assert playbook.metadata.description == "Japanese Description"


def test_load_user_playbooks_uses_default_workspace(monkeypatch):
    playbooks = [
        _make_playbook(code="alpha", locale="en"),
        _make_playbook(code="beta", locale="zh-TW"),
    ]

    monkeypatch.setattr(
        "backend.app.services.playbook_registry_core.metadata.PlaybookDatabaseLoader.load_playbooks_from_db",
        lambda db_path: playbooks,
    )

    user_playbooks = {}
    load_user_playbooks(
        store=SimpleNamespace(db_path="/tmp/playbooks.db"),
        user_playbooks=user_playbooks,
        logger=LOGGER,
    )

    assert set(user_playbooks["default"]) == {"alpha", "beta"}


def test_cache_capability_playbook_round_trip():
    capability_playbooks = {}
    playbook = _make_playbook(code="demo", locale="en")

    cache_capability_playbook(
        capability_playbooks,
        "alpha",
        "demo",
        "en",
        playbook,
    )

    assert (
        get_cached_capability_playbook(capability_playbooks, "alpha", "demo", "en")
        is playbook
    )


def test_load_direct_capability_playbook_updates_cache_and_variants(
    tmp_path, monkeypatch
):
    capability_dir = tmp_path / "alpha"
    playbook_dir = capability_dir / "playbooks" / "en"
    playbook_dir.mkdir(parents=True)
    (playbook_dir / "demo.md").write_text("# demo", encoding="utf-8")
    (capability_dir / "manifest.yaml").write_text(
        "code: alpha\n"
        "playbooks:\n"
        "  - code: demo\n"
        "    locales: [en]\n"
        "    variants:\n"
        "      - variant_id: lite\n",
        encoding="utf-8",
    )

    playbook = _make_playbook(code="demo", locale="en")
    monkeypatch.setattr(
        "backend.app.services.playbook_registry_core.lookup.PlaybookFileLoader.load_playbook_from_file",
        lambda path: playbook,
    )

    capability_playbooks = {}
    loaded_capabilities = set()
    parse_calls = []

    result = load_direct_capability_playbook(
        capability_dir=capability_dir,
        playbook_code="demo",
        locale="en",
        capability_playbooks=capability_playbooks,
        loaded_capabilities=loaded_capabilities,
        enrich_playbook_metadata=lambda *args: None,
        cache_playbook=lambda capability_code, playbook_code, locale, playbook: cache_capability_playbook(
            capability_playbooks, capability_code, playbook_code, locale, playbook
        ),
        parse_variants_fn=lambda payload, capability_code, playbook_code: parse_calls.append(
            (payload["code"], capability_code, playbook_code)
        ),
        logger=LOGGER,
    )

    assert result is playbook
    assert playbook.metadata.capability_code == "alpha"
    assert "alpha" in loaded_capabilities
    assert capability_playbooks["alpha"]["alpha.demo"] is playbook
    assert parse_calls == [("demo", "alpha", "demo")]


def test_lookup_local_playbook_prefers_user_workspace_playbook():
    user_playbook = _make_playbook(code="demo", locale="en")
    capability_playbook = _make_playbook(code="demo", locale="en")
    system_playbook = _make_playbook(code="demo", locale="en")

    result = lookup_local_playbook(
        system_playbooks={"en": {"demo": system_playbook}},
        capability_playbooks={"alpha": {"demo": capability_playbook}},
        user_playbooks={"workspace-1": {"demo": user_playbook}},
        playbook_code="demo",
        locale="en",
        workspace_id="workspace-1",
        capability_code=None,
        logger=LOGGER,
    )

    assert result is user_playbook


def test_collect_playbook_metadata_filters_and_dedupes():
    capability_playbook = _make_playbook(code="demo", locale="en", tags=["ops"])
    system_playbook = _make_playbook(code="demo", locale="en", tags=["ops"])
    user_playbook = _make_playbook(code="custom", locale="en", tags=["ops", "user"])

    result = collect_playbook_metadata(
        capability_playbooks={"alpha": {"demo:en": capability_playbook}},
        system_playbooks={"en": {"demo": system_playbook}},
        user_playbooks={"workspace-1": {"custom": user_playbook}},
        workspace_id="workspace-1",
        locale="en",
        category="ops",
        source_value=None,
        tags=["ops"],
        matches_filters_fn=matches_filters,
    )

    assert {(item.playbook_code, item.locale) for item in result} == {
        ("demo", "en"),
        ("custom", "en"),
    }


def test_resolve_playbook_lookup_request_extracts_dotted_capability_code():
    requested, playbook_code, capability_code, resolved_capability = (
        resolve_playbook_lookup_request(
            playbook_code="alpha.demo",
            capability_code=None,
            capability_playbooks={"alpha": {}},
            logger=LOGGER,
        )
    )

    assert requested == "alpha.demo"
    assert playbook_code == "demo"
    assert capability_code == "alpha"
    assert resolved_capability == "alpha"


def test_invalidate_registry_cache_clears_all_state():
    system_playbooks = {"en": {"demo": _make_playbook(code="demo")}}
    capability_playbooks = {"alpha": {"demo": _make_playbook(code="demo")}}
    user_playbooks = {"workspace-1": {"demo": _make_playbook(code="demo")}}
    playbook_variants = {"alpha.demo": [{"variant_id": "lite"}], "demo": []}
    loaded_capabilities = {"alpha"}
    capability_locks = {"alpha": object()}

    reset_loaded = invalidate_registry_cache(
        system_playbooks=system_playbooks,
        capability_playbooks=capability_playbooks,
        user_playbooks=user_playbooks,
        playbook_variants=playbook_variants,
        loaded_capabilities=loaded_capabilities,
        capability_locks=capability_locks,
        logger=LOGGER,
    )

    assert reset_loaded is True
    assert system_playbooks == {}
    assert capability_playbooks == {}
    assert user_playbooks == {}
    assert playbook_variants == {}
    assert loaded_capabilities == set()
    assert capability_locks == {}
