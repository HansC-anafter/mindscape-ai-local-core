from backend.app.services.result_object_contract import (
    build_result_object_descriptor,
    json_payload_size,
)


def _contains_key(value, target_key):
    if isinstance(value, dict):
        return target_key in value or any(
            _contains_key(child, target_key) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(child, target_key) for child in value)
    return False


def test_result_object_descriptor_keeps_pointer_metadata_only():
    payload = {
        "summary": "render completed",
        "status": "completed",
        "execution_trace": {
            "events": [{"message": "x" * 1000} for _ in range(50)],
        },
        "steps": {
            "render": {
                "status": "success",
                "outputs": {"images": ["image-1.png", "image-2.png"]},
            }
        },
    }

    descriptor = build_result_object_descriptor(
        payload=payload,
        summary="render completed",
        storage_ref="/workspace/artifacts/exec-1",
        execution_id="exec-1",
        artifact_id="artifact-1",
        landing_metadata={
            "result_json_path": "/workspace/artifacts/exec-1/result.json",
            "summary_md_path": "/workspace/artifacts/exec-1/summary.md",
        },
        deliverable_identity={
            "deliverable_name": "image batch",
            "deliverable_path": "outputs/image-1.png",
            "attachment_filenames": ["image-1.png", "image-2.png"],
        },
        acceptance_evidence={"verified": True},
    )

    assert descriptor["summary"] == "render completed"
    assert descriptor["storage_ref"] == "/workspace/artifacts/exec-1"
    assert descriptor["execution_id"] == "exec-1"
    assert descriptor["artifact_id"] == "artifact-1"
    assert descriptor["result_object"]["bytes"] == json_payload_size(payload)
    assert descriptor["result_object"]["checksum_sha256"]
    assert (
        descriptor["result_object"]["result_json_path"]
        == "/workspace/artifacts/exec-1/result.json"
    )
    assert descriptor["deliverable_name"] == "image batch"
    assert descriptor["attachment_filenames"] == ["image-1.png", "image-2.png"]
    assert descriptor["acceptance_evidence"] == {"verified": True}
    assert not _contains_key(descriptor, "execution_trace")
