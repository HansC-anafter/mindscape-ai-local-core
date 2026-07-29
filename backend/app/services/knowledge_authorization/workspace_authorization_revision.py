"""Stable local workspace authorization revision seam."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def workspace_authorization_revision(
    *,
    workspace_id: Any,
    owner_user_id: Any,
    visibility: Any,
) -> str:
    """Hash only fields that can change local workspace read authority."""

    normalized_workspace_id = _required_token(
        workspace_id,
        "knowledge_workspace_authorization_id_missing",
    )
    normalized_owner_user_id = _required_token(
        owner_user_id,
        "knowledge_workspace_authorization_owner_missing",
    )
    normalized_visibility = _required_token(
        getattr(visibility, "value", visibility),
        "knowledge_workspace_authorization_visibility_missing",
    )
    payload = {
        "owner_user_id": normalized_owner_user_id,
        "visibility": normalized_visibility,
        "workspace_id": normalized_workspace_id,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _required_token(value: Any, code: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError(code)
    return token
