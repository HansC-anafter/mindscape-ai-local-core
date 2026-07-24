import pytest
from pydantic import ValidationError

from backend.app.services.workspace_groups.contracts import SharedAssetSelector


def test_shared_asset_selector_is_strict_and_normalized():
    selector = SharedAssetSelector.model_validate(
        {
            "reference_seed": " sinnie_withu ",
            "following_seed": "sinnie_withu",
            "include_future_matches": True,
        }
    )
    assert selector.reference_seed == "sinnie_withu"
    assert selector.include_future_matches is True

    with pytest.raises(ValidationError):
        SharedAssetSelector.model_validate(
            {
                "reference_seed": "sinnie_withu",
                "following_seed": "sinnie_withu",
                "include_future_matches": True,
                "untyped_policy": "allow",
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {
            "reference_seed": "",
            "following_seed": "sinnie_withu",
            "include_future_matches": True,
        },
        {
            "reference_seed": "sinnie_withu",
            "following_seed": "sinnie_withu",
        },
    ],
)
def test_shared_asset_selector_rejects_incomplete_payloads(payload):
    with pytest.raises(ValidationError):
        SharedAssetSelector.model_validate(payload)
