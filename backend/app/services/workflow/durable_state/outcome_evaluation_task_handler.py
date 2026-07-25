"""Disabled same-transaction intent seam for neutral outcome evaluation."""

from __future__ import annotations

from typing import Callable, Mapping

from .canonical_json import encode, sha256_hex
from .contracts.v1.validator import validate_contract
from .outcome_adapter_resolver import OutcomeAdapterResolver
from .signature import SigningKeyError, verify

PARITY_FIELDS = (
    "development_attestation_id",
    "development_attestation_sha256",
    "consumer_compatibility_class",
    "configuration_fingerprint",
    "environment_fingerprint",
    "data_fingerprint",
)


class OutcomeEvaluationTaskHandler:
    """Creates one existing-lane task only after exact signed resolution."""

    def __init__(
        self,
        resolver: OutcomeAdapterResolver,
        *,
        create_task_with_conn: Callable,
        append_linkage_with_conn: Callable,
        terminal_verification_keys: dict[str, object],
    ) -> None:
        self._resolver = resolver
        self._create_task_with_conn = create_task_with_conn
        self._append_linkage_with_conn = append_linkage_with_conn
        self._terminal_verification_keys = terminal_verification_keys

    def prepare(
        self,
        conn,
        *,
        capability_entries: Mapping[str, dict],
        terminal_receipt: dict,
        enrollment: dict | None,
    ) -> dict:
        validate_contract("execution_terminal_receipt", terminal_receipt)
        if enrollment is None:
            return {
                "status": "not_enrolled",
                "task": None,
                "rejection": None,
                "wake_after_commit": False,
            }
        pin = self._pin_from_enrollment(enrollment)
        signature_error = self._terminal_signature_error(terminal_receipt)
        if signature_error:
            return {
                "status": "rejected",
                "task": None,
                "rejection": self._resolver.reject(pin, signature_error),
                "wake_after_commit": False,
            }
        parity_error = self._parity_error(terminal_receipt, enrollment)
        if parity_error:
            return {
                "status": "rejected",
                "task": None,
                "rejection": self._resolver.reject(pin, parity_error),
                "wake_after_commit": False,
            }
        resolved = self._resolver.resolve(capability_entries, pin)
        if resolved.snapshot is None:
            return {
                "status": "rejected",
                "task": None,
                "rejection": resolved.rejection,
                "wake_after_commit": False,
            }

        descriptor = dict(resolved.snapshot.descriptor)
        unique_input = {
            "iteration_id": enrollment["iteration_id"],
            "arm_id": enrollment["arm_id"],
            "case_id": enrollment["case_id"],
            "terminal_receipt_id": terminal_receipt["receipt_id"],
            "development_attestation_sha256": enrollment[
                "development_attestation_sha256"
            ],
            "environment_fingerprint": enrollment["environment_fingerprint"],
            "data_fingerprint": enrollment["data_fingerprint"],
            "descriptor_id": descriptor["descriptor_id"],
            "adapter_contract_version": descriptor[
                "adapter_contract_version"
            ],
            "descriptor_sha256": descriptor["descriptor_sha256"],
            "evaluator_version": descriptor["evaluator_version"],
        }
        idempotency_key = f"outcome-evaluation:{sha256_hex(unique_input)}"
        task = {
            "task_id": idempotency_key,
            "workspace_id": terminal_receipt["workspace_id"],
            "capability_code": pin["capability_code"],
            "task_type": "product_outcome_evaluation",
            "authorized_lane": descriptor["authorized_lane"],
            "params": {
                **unique_input,
                "enrollment_id": enrollment["enrollment_id"],
                "terminal_result_ref": terminal_receipt["result_ref"],
                "observation_window": enrollment["observation_window"],
                "budget": enrollment["budget"],
            },
        }
        encode(task)
        created = self._create_task_with_conn(
            conn,
            task,
            idempotency_key=idempotency_key,
        )
        self._append_linkage_with_conn(
            conn,
            {
                "event_type": "outcome_evaluation_intent_created",
                "terminal_receipt_id": terminal_receipt["receipt_id"],
                "enrollment_id": enrollment["enrollment_id"],
                "task_id": task["task_id"],
                "idempotency_key": idempotency_key,
            },
        )
        return {
            "status": "task_created",
            "task": created,
            "rejection": None,
            "wake_after_commit": True,
            "snapshot": resolved.snapshot,
        }

    @staticmethod
    def _pin_from_enrollment(enrollment: dict) -> dict[str, str]:
        required = (
            "enrollment_id",
            "iteration_id",
            "arm_id",
            "case_id",
            "terminal_receipt_id",
            "capability_code",
            "port_id",
            "contract_export_id",
            "adapter_contract_version",
            "descriptor_sha256",
            "evaluator_version",
            "observation_window",
            "budget",
            *PARITY_FIELDS,
        )
        missing = [field for field in required if field not in enrollment]
        if missing:
            raise ValueError(
                f"outcome enrollment missing required field: {missing[0]}"
            )
        return {
            field: enrollment[field]
            for field in (
                "capability_code",
                "port_id",
                "contract_export_id",
                "adapter_contract_version",
                "descriptor_sha256",
                "evaluator_version",
            )
        }

    @staticmethod
    def _parity_error(
        terminal_receipt: dict, enrollment: dict
    ) -> str | None:
        if enrollment["terminal_receipt_id"] != terminal_receipt["receipt_id"]:
            return "terminal_receipt_mismatch"
        terminal_capability = terminal_receipt["capability_identity"][
            "capability_code"
        ]
        if enrollment["capability_code"] != terminal_capability:
            return "capability_identity_mismatch"
        for field in PARITY_FIELDS:
            if enrollment[field] != terminal_receipt[field]:
                return f"{field}_mismatch"
        if enrollment["consumer_compatibility_class"] != "compatible":
            return "consumer_compatibility_not_admitted"
        return None

    def _terminal_signature_error(
        self, terminal_receipt: dict
    ) -> str | None:
        public_key = self._terminal_verification_keys.get(
            terminal_receipt["key_id"]
        )
        if public_key is None:
            return "terminal_signing_key_unavailable"
        try:
            verify(
                public_key,
                encode(
                    {
                        key: value
                        for key, value in terminal_receipt.items()
                        if key != "signature"
                    }
                ),
                terminal_receipt["signature"],
            )
        except SigningKeyError:
            return "terminal_signature_invalid"
        return None
