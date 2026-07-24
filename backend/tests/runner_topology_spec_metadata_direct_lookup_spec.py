import json

from backend.app.services.runner_topology import spec_metadata


def _write_spec(root, capability_code, playbook_code, *, resource_class="browser"):
    spec_dir = root / capability_code / "playbooks" / "specs"
    spec_dir.mkdir(parents=True)
    (spec_dir / f"{playbook_code}.json").write_text(
        json.dumps(
            {
                "playbook_code": playbook_code,
                "execution_profile": {
                    "resource_class": resource_class,
                    "queue_shard": "browser_local",
                },
            }
        ),
        encoding="utf-8",
    )


def test_exact_installed_spec_does_not_hydrate_global_registry(tmp_path, monkeypatch):
    _write_spec(tmp_path, "sample_pack", "sample_playbook")
    _write_spec(tmp_path, ".sample_pack.previous", "sample_playbook")
    monkeypatch.setattr(spec_metadata, "_installed_capabilities_dir", lambda: tmp_path)
    monkeypatch.setattr(
        spec_metadata,
        "_capability_registry",
        lambda: (_ for _ in ()).throw(AssertionError("registry hydration not allowed")),
    )
    spec_metadata.resolve_installed_playbook_runner_metadata.cache_clear()

    metadata = spec_metadata.resolve_installed_playbook_runner_metadata(
        "sample_playbook"
    )

    assert metadata["capability_code"] == "sample_pack"
    assert metadata["resource_class"] == "browser"
    assert metadata["queue_shard"] == "browser_local"


def test_duplicate_exact_specs_preserve_registry_fallback(tmp_path, monkeypatch):
    _write_spec(tmp_path, "pack_one", "shared_playbook")
    _write_spec(tmp_path, "pack_two", "shared_playbook")

    class _Registry:
        def list_capabilities(self):
            return ["authoritative_pack"]

        def get_capability(self, _capability_code):
            return {
                "directory": tmp_path / "pack_one",
                "manifest": {
                    "playbooks": [
                        {
                            "code": "shared_playbook",
                            "spec_path": "playbooks/specs/shared_playbook.json",
                        }
                    ]
                },
            }

    monkeypatch.setattr(spec_metadata, "_installed_capabilities_dir", lambda: tmp_path)
    monkeypatch.setattr(spec_metadata, "_capability_registry", _Registry)
    spec_metadata.resolve_installed_playbook_runner_metadata.cache_clear()

    metadata = spec_metadata.resolve_installed_playbook_runner_metadata(
        "shared_playbook"
    )

    assert metadata["capability_code"] == "authoritative_pack"
    assert metadata["resource_class"] == "browser"
