"""Role-specific image ownership for the disposable observer drill."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any


POSTGRES_DRILL_IMAGE_ROLE = "postgres_drill_pg16"
OBSERVER_BACKEND_IMAGE_ROLE = "observer_backend"

_ROLE_OPTIONS = {
    POSTGRES_DRILL_IMAGE_ROLE: "--postgres-drill-image-ref",
    OBSERVER_BACKEND_IMAGE_ROLE: "--observer-backend-image-ref",
}
_ROLE_OWNER_NAMES = {
    POSTGRES_DRILL_IMAGE_ROLE: "mindscape-ai-local-core-postgres:pg16",
    OBSERVER_BACKEND_IMAGE_ROLE: "mindscape-ai-local-core-backend",
}
_PINNED_IMAGE_REF = re.compile(
    r"^(?P<repository>[a-z0-9][a-z0-9._/-]*"
    r"(?::[a-z0-9][a-z0-9._-]*)?)@sha256:(?P<digest>[0-9a-f]{64})$"
)


def validate_drill_image_ref(image_ref: str, *, role: str) -> str:
    """Return an exact pinned image ref only when its owner matches the role."""

    expected_owner = _ROLE_OWNER_NAMES.get(str(role))
    if expected_owner is None:
        raise ValueError("drill_image_role_invalid")
    candidate = str(image_ref)
    match = _PINNED_IMAGE_REF.fullmatch(candidate)
    if match is None:
        raise ValueError(f"drill_{role}_image_ref_invalid")
    owner_name = match.group("repository").rsplit("/", 1)[-1]
    if owner_name != expected_owner:
        raise ValueError(f"drill_{role}_image_owner_mismatch")
    return candidate


def drill_image_digest(image_ref: str, *, role: str) -> str:
    """Return the digest after validating the role-specific owner contract."""

    validated = validate_drill_image_ref(image_ref, role=role)
    return "sha256:" + validated.rpartition("@sha256:")[2]


def _binding_argv_sha256(option: str, image_ref: str) -> str:
    return hashlib.sha256(
        "\0".join((option, image_ref)).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class DisposableDrillImageContract:
    """Exact two-role image contract shared by every drill facade mode."""

    postgres_image_ref: str
    observer_image_ref: str

    def validate(self) -> None:
        validate_drill_image_ref(
            self.postgres_image_ref,
            role=POSTGRES_DRILL_IMAGE_ROLE,
        )
        validate_drill_image_ref(
            self.observer_image_ref,
            role=OBSERVER_BACKEND_IMAGE_ROLE,
        )

    def image_ref_for(self, role: str) -> str:
        self.validate()
        if role == POSTGRES_DRILL_IMAGE_ROLE:
            return self.postgres_image_ref
        if role == OBSERVER_BACKEND_IMAGE_ROLE:
            return self.observer_image_ref
        raise ValueError("drill_image_role_invalid")

    def redacted_spec(self) -> dict[str, Any]:
        """Return both exact owners without secret or runtime payload data."""

        self.validate()
        roles: dict[str, Any] = {}
        for role in (POSTGRES_DRILL_IMAGE_ROLE, OBSERVER_BACKEND_IMAGE_ROLE):
            image_ref = self.image_ref_for(role)
            option = _ROLE_OPTIONS[role]
            roles[role] = {
                "facade_option": option,
                "owner_name": _ROLE_OWNER_NAMES[role],
                "image_ref": image_ref,
                "image_digest": drill_image_digest(image_ref, role=role),
                "facade_binding_argv_sha256": _binding_argv_sha256(
                    option,
                    image_ref,
                ),
            }
        return {
            "schema_version": "mindscape.postgres-signal-observer-image-contract.v1",
            "roles": roles,
            "legacy_image_ref_accepted": False,
        }
