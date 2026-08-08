"""Neutral invocation port for pack-owned outcome evaluators."""

from __future__ import annotations

import inspect
from typing import Callable

from .canonical_json import encode
from .contracts.v1.validator import validate_contract
from .outcome_adapter_resolver import OutcomeAdapterSnapshot
from .signature import verify

MAX_OUTCOME_OBSERVATIONS = 50


class ProductOutcomeAdapterPort:
    """Loads only the exact signed descriptor entrypoint through injection."""

    def __init__(
        self,
        *,
        load_callable: Callable,
        observation_verification_keys: dict[str, object],
    ) -> None:
        self._load_callable = load_callable
        self._observation_verification_keys = observation_verification_keys

    def evaluate(
        self,
        *,
        snapshot: OutcomeAdapterSnapshot,
        terminal_receipt: dict,
        enrollment: dict,
        runtime_context: dict | None = None,
    ) -> list[dict]:
        descriptor = dict(snapshot.descriptor)
        evaluator = self._load_callable(
            backend_path=descriptor["evaluator_entrypoint"],
            capability_dir=snapshot.capability_dir,
        )
        envelope = {
            "terminal_receipt": terminal_receipt,
            "enrollment": enrollment,
            "descriptor_id": descriptor["descriptor_id"],
            "adapter_contract_version": descriptor["adapter_contract_version"],
            "evaluator_version": descriptor["evaluator_version"],
        }
        signature = inspect.signature(evaluator)
        accepts_context = "runtime_context" in signature.parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        result = (
            evaluator(envelope, runtime_context=runtime_context or {})
            if accepts_context
            else evaluator(envelope)
        )
        observations = result if isinstance(result, list) else [result]
        if not observations:
            raise ValueError("outcome evaluator returned no observations")
        if len(observations) > MAX_OUTCOME_OBSERVATIONS:
            raise ValueError("outcome evaluator observation budget exceeded")
        for observation in observations:
            if not isinstance(observation, dict):
                raise ValueError("outcome evaluator returned a non-object")
            validate_contract("outcome_observation", observation)
            self._require_identity(
                observation,
                descriptor=descriptor,
                terminal_receipt=terminal_receipt,
                enrollment=enrollment,
            )
            encode(observation)
            public_key = self._observation_verification_keys.get(observation["key_id"])
            if public_key is None:
                raise ValueError("outcome observation signing key is unavailable")
            verify(
                public_key,
                encode(
                    {
                        key: value
                        for key, value in observation.items()
                        if key != "signature"
                    }
                ),
                observation["signature"],
            )
        return observations

    @staticmethod
    def _require_identity(
        observation: dict,
        *,
        descriptor: dict,
        terminal_receipt: dict,
        enrollment: dict,
    ) -> None:
        expected = {
            "descriptor_id": descriptor["descriptor_id"],
            "case_id": enrollment["case_id"],
            "capability_identity": terminal_receipt["capability_identity"],
            "adapter_contract_version": descriptor["adapter_contract_version"],
            "descriptor_sha256": descriptor["descriptor_sha256"],
            "evaluator_version": descriptor["evaluator_version"],
            "terminal_receipt_id": terminal_receipt["receipt_id"],
            "enrollment_id": enrollment["enrollment_id"],
            "iteration_id": enrollment["iteration_id"],
            "arm_id": enrollment["arm_id"],
            "development_attestation_id": enrollment["development_attestation_id"],
            "development_attestation_sha256": enrollment[
                "development_attestation_sha256"
            ],
            "consumer_compatibility_class": enrollment["consumer_compatibility_class"],
            "configuration_fingerprint": enrollment["configuration_fingerprint"],
            "environment_fingerprint": enrollment["environment_fingerprint"],
            "data_fingerprint": enrollment["data_fingerprint"],
        }
        for field, value in expected.items():
            if observation.get(field) != value:
                raise ValueError(f"outcome observation {field} mismatch")
