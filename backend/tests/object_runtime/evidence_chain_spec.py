from backend.app.services.object_runtime.evidence_chain import (
    build_object_attachment_evidence_chain,
)


def test_object_attachment_evidence_chain_marks_linked_refs():
    chain = build_object_attachment_evidence_chain(
        context_attachments=[
            {
                "role": "source",
                "object_ref": {"uri": "mindscape://ig/reference/ref-1"},
                "meeting_projection": {"payload": {"title": "Ref 1"}},
            }
        ],
        role_object_uris={"source": ["mindscape://ig/reference/ref-1"]},
    )

    assert chain["status"] == "linked"
    assert chain["object_uri_count"] == 1
    assert chain["roles"]["source"] == ["mindscape://ig/reference/ref-1"]


def test_object_attachment_evidence_chain_marks_missing_projection_candidate():
    chain = build_object_attachment_evidence_chain(
        context_attachments=[
            {
                "role": "source",
                "object_ref": {"uri": "mindscape://ig/reference/ref-1"},
                "meeting_projection": {},
            }
        ],
        role_object_uris={"source": ["mindscape://ig/reference/ref-1"]},
    )

    assert chain["status"] == "candidate"
    assert chain["missing"] == [
        {
            "role": "source",
            "uri": "mindscape://ig/reference/ref-1",
            "reason": "missing_meeting_projection",
        }
    ]
