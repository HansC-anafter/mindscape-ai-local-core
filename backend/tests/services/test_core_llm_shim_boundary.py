import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "data_utils",
        "generate",
        "multimodal",
        "structured",
    ],
)
def test_core_llm_legacy_shim_points_to_system_source(module_name: str) -> None:
    legacy = importlib.import_module(
        f"backend.app.capabilities.core_llm.services.{module_name}"
    )
    source = importlib.import_module(
        f"backend.app.system_capabilities.core_llm.services.{module_name}"
    )

    assert legacy is source

