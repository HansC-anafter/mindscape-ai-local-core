"""Evidence-chain summaries for Addressable Object Layer attachments."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def build_object_attachment_evidence_chain(
    *,
    context_attachments: Sequence[Mapping[str, Any]],
    role_object_uris: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    missing: list[dict[str, Any]] = []
    object_uris: list[str] = []
    roles: dict[str, list[str]] = {}
    for attachment in context_attachments:
        role = str(attachment.get("role") or "unknown")
        object_ref = _as_mapping(attachment.get("object_ref"))
        uri = object_ref.get("uri")
        if not uri:
            missing.append({"role": role, "reason": "missing_object_ref_uri"})
            continue
        uri = str(uri)
        object_uris.append(uri)
        roles.setdefault(role, [])
        if uri not in roles[role]:
            roles[role].append(uri)
        meeting_projection = _as_mapping(attachment.get("meeting_projection"))
        if not _as_mapping(meeting_projection.get("payload")):
            missing.append({"role": role, "uri": uri, "reason": "missing_meeting_projection"})

    for role, uris in role_object_uris.items():
        for uri in uris:
            if uri not in object_uris:
                missing.append({"role": role, "uri": uri, "reason": "missing_attachment"})

    return {
        "status": "linked" if not missing else "candidate",
        "object_uri_count": len(set(object_uris)),
        "roles": roles,
        "missing": missing,
    }
