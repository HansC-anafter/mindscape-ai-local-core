from fastapi import FastAPI

from backend.app.app_bootstrap.knowledge_projection_registry import (
    hydrate_knowledge_projection_registry,
)
from backend.app.services.knowledge_projection.retrievable.adapter_registry import (
    get_adapter_registry,
)


def test_startup_manifest_hydration_registers_installed_projection_descriptors():
    app = FastAPI()

    receipt = hydrate_knowledge_projection_registry(app)

    assert receipt["status"] == "ready"
    assert receipt["scanned_manifest_count"] > 0
    assert receipt["parsed_manifest_count"] == 2
    assert receipt["registered_capability_count"] == 2
    assert receipt["registered_descriptor_count"] == 3
    assert receipt["errors"] == []
    assert app.state.knowledge_projection_registry == receipt
    descriptors = get_adapter_registry().list_capability("ig")
    assert "ig_objects_v1" in {
        descriptor.descriptor_id for descriptor in descriptors
    }
