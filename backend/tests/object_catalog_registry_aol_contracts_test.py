import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.models.object_runtime import ObjectCatalogEntry
from backend.app.services.object_catalog_registry import ObjectCatalogRegistry


def test_object_catalog_registry_persists_aol2_selector_and_affordance_contracts(
    tmp_path,
):
    manifest = {
        "object_exports": [
            {
                "kind": "reference",
                "display_name": "Reference",
                "canonical_schema": "capabilities.ig.schema.reference",
                "id_field": "reference_id",
                "summary_fields": ["source_handle", "source_shortcode"],
                "supports": ["summary", "detail", "actions"],
                "granularity": "object_root",
                "selector_families": ["object_root", "image_region"],
                "indexer_backend": "capabilities.ig.services.aol:sync_reference_index",
                "mention_fields": ["source_handle", "source_shortcode"],
                "owner_surface_patterns": ["/capabilities/ig/references/{reference_id}"],
            },
            {
                "kind": "storyboard_scene",
                "display_name": "Storyboard Scene",
                "canonical_schema": "capabilities.performance_direction.schema.scene",
                "id_field": "scene_id",
                "summary_fields": ["scene_title"],
                "supports": ["summary", "materialize"],
                "granularity": "storyboard_scene",
                "selector_families": ["storyboard_scene"],
                "indexer_backend": "capabilities.performance_direction.services.aol:sync_scene_index",
                "mention_fields": ["scene_title"],
            },
        ],
        "affordances": [
            {
                "verb": "use_as_reference",
                "object_kinds": ["reference"],
                "label": "Use as reference",
                "description": "Use the reference as source context.",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "required_roles": ["source", "target"],
                "write_modes": ["proposal_only"],
                "planner_backend": "capabilities.ig.services.aol:plan_reference_use",
                "executor_backend": "capabilities.ig.services.aol:execute_reference_use",
            }
        ],
    }

    registry = ObjectCatalogRegistry(tmp_path)
    result = registry.sync_pack_objects("ig", manifest)

    assert result.object_count == 2
    reference_entry = registry.get_entry("ig", "reference")
    assert reference_entry is not None
    assert reference_entry["selector_families"] == ["object_root", "image_region"]
    assert reference_entry["indexer_backend"] == (
        "capabilities.ig.services.aol:sync_reference_index"
    )
    assert reference_entry["mention_fields"] == [
        "source_handle",
        "source_shortcode",
    ]
    assert reference_entry["affordances"][0]["verb"] == "use_as_reference"

    catalog_entry = ObjectCatalogEntry(
        **{
            field_name: reference_entry[field_name]
            for field_name in ObjectCatalogEntry.model_fields
            if field_name in reference_entry
        }
    )
    assert catalog_entry.selector_families == ["object_root", "image_region"]
    assert catalog_entry.affordances[0].required_roles == ["source", "target"]


def test_object_catalog_registry_filters_affordances_by_object_kind(tmp_path):
    manifest = {
        "object_exports": [
            {
                "kind": "reference",
                "display_name": "Reference",
                "id_field": "reference_id",
            },
            {
                "kind": "storyboard_scene",
                "display_name": "Storyboard Scene",
                "id_field": "scene_id",
            },
        ],
        "affordances": [
            {
                "verb": "patch_storyboard",
                "object_kinds": ["storyboard_scene"],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "required_roles": ["target"],
                "write_modes": ["staged"],
                "planner_backend": "capabilities.pd.services.aol:plan_patch",
            }
        ],
    }

    registry = ObjectCatalogRegistry(tmp_path)
    registry.sync_pack_objects("performance_direction", manifest)

    assert registry.get_entry("performance_direction", "reference")["affordances"] == []
    assert registry.get_entry("performance_direction", "storyboard_scene")[
        "affordances"
    ][0]["verb"] == "patch_storyboard"
