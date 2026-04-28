import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.models.object_runtime import ObjectRef, SelectionHints


def _object_ref(selector):
    return ObjectRef(
        uri="mindscape://ig/reference/ref_001",
        owner_pack="ig",
        object_kind="reference",
        object_id="ref_001",
        workspace_id="ws_demo",
        selector=selector,
    )


def test_object_ref_accepts_typed_image_region_selector():
    ref = _object_ref(
        {
            "selector_type": "image_region",
            "surface_id": "ig.references_grid",
            "region": {"x": 12, "y": 24, "w": 120, "h": 90},
        }
    )

    assert ref.selector == {
        "selector_type": "image_region",
        "surface_id": "ig.references_grid",
        "region": {"x": 12.0, "y": 24.0, "w": 120.0, "h": 90.0},
        "metadata": {},
    }


def test_object_ref_rejects_incomplete_typed_selector():
    with pytest.raises(ValidationError, match="image_region selectors require region"):
        _object_ref({"selector_type": "image_region"})


def test_object_ref_keeps_legacy_selector_payloads_compatible():
    selector = {"surface": "ig.references_grid", "row_id": "ref_001"}

    ref = _object_ref(selector)

    assert ref.selector == selector


def test_selection_hints_accepts_typed_media_time_range_selector():
    hints = SelectionHints(
        owner_pack="performance_direction",
        object_kind="storyboard_scene",
        object_id="scene_opening_01",
        selector={
            "selector_type": "media_time_range",
            "time_start_seconds": 2.5,
            "time_end_seconds": 8.0,
        },
    )

    assert hints.selector == {
        "selector_type": "media_time_range",
        "time_start_seconds": 2.5,
        "time_end_seconds": 8.0,
        "metadata": {},
    }


def test_selection_hints_rejects_unknown_selector_family():
    with pytest.raises(ValidationError, match="selector_type"):
        SelectionHints(selector={"selector_type": "unknown_family"})
