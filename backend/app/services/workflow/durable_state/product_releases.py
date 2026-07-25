"""Test-only product-release seam and promotion owner-effect checks."""

from __future__ import annotations

from typing import Any

from .product_iteration_contract import arm, promotion_request_hash


class ProductReleaseMixin:
    """Keeps release creation behind an exact promoted-iteration receipt."""

    def open_product_release_from_promotion(
        self,
        conn,
        *,
        identity: dict[str, Any],
        source_iteration_id: str,
        release_effect_receipt_id: str,
        actor: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        if identity.get("workflow_kind") != "product_release":
            raise ValueError(
                "product release identity must use product_release kind"
            )
        source = self._repository.lock_instance(
            conn, source_iteration_id
        )
        if source["current_state"] != "promoted" or not source["terminal"]:
            raise ValueError("product release source is not promoted")
        receipt = self._repository.read_side_effect_receipt(
            conn, release_effect_receipt_id
        )
        state = self._projection_state(conn, source)
        definition = state["definition"]
        promotion_link = state.get("promotion_link") or {}
        if (
            promotion_link.get("release_workflow_id")
            != identity["workflow_id"]
            or promotion_link.get("release_effect_receipt_id")
            != release_effect_receipt_id
        ):
            raise ValueError("product release workflow linkage mismatch")
        selected_arm = arm(
            definition, definition["release_target"]["arm_id"]
        )
        if receipt["request_hash"] != promotion_request_hash(
            definition, state["evaluation"]
        ):
            raise ValueError("product release receipt target mismatch")
        identity_parity = {
            "capability_identity": selected_arm["capability_identity"],
            "development_attestation_id": selected_arm[
                "development_attestation_id"
            ],
            "development_attestation_sha256": selected_arm[
                "development_attestation_sha256"
            ],
            "consumer_compatibility_class": selected_arm[
                "consumer_compatibility_class"
            ],
            "configuration_fingerprint": selected_arm[
                "configuration_fingerprint"
            ],
            "environment_fingerprint": selected_arm[
                "environment_fingerprint"
            ],
            "data_fingerprint": selected_arm["data_fingerprint"],
        }
        for field, value in identity_parity.items():
            if identity.get(field) != value:
                raise ValueError(
                    f"product release identity {field} mismatch"
                )
        self._open_workflow_kind(conn, identity)
        locked = self._repository.lock_instance(
            conn, identity["workflow_id"]
        )
        self._append_locked(
            conn,
            locked=locked,
            event_type="product_release_linked",
            idempotency_key=idempotency_key,
            actor=actor,
            payload={
                "source_iteration_id": source_iteration_id,
                "release_effect_receipt_id": release_effect_receipt_id,
                "development_attestation_id": (
                    selected_arm["development_attestation_id"]
                ),
                "target_sha256": definition["release_target"][
                    "target_sha256"
                ],
            },
        )
        return self.read_current(conn, identity["workflow_id"])

    def _require_release_effect(
        self,
        conn,
        *,
        workflow_id: str,
        definition: dict,
        evaluation: dict,
        approval_consumption_id: str | None,
        release_effect_receipt_id: str | None,
    ) -> None:
        if not approval_consumption_id or not release_effect_receipt_id:
            raise ValueError(
                "promotion requires approval consumption and owner receipt"
            )
        consumption = self._repository.read_approval_consumption(
            conn, approval_consumption_id
        )
        receipt = self._repository.read_side_effect_receipt(
            conn, release_effect_receipt_id
        )
        expected_hash = promotion_request_hash(definition, evaluation)
        if (
            receipt["workflow_id"] != workflow_id
            or receipt["status"] != "succeeded"
            or receipt["owner"] != definition["release_target"]["owner_id"]
            or receipt["request_hash"] != expected_hash
            or consumption["effect_or_transition_id"]
            != receipt["effect_id"]
        ):
            raise ValueError(
                "release effect does not match approved promotion"
            )
