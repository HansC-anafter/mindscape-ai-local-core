"""Static SQL seams for host-admission state projection."""

from __future__ import annotations


REQUIRED_HOST_OPERATIONS_CTE = """
required_host_operations AS (
    SELECT DISTINCT
        pack.value ->> 'code' AS pack_code,
        requirement.value ->> 'requirement_code'
            AS requirement_code,
        operation.value AS operation
    FROM active_catalog,
    LATERAL jsonb_array_elements(
        active_catalog.artifact_json
            -> 'catalog' -> 'products'
    ) AS product(value),
    LATERAL jsonb_array_elements(
        product.value -> 'pack_closure'
    ) AS pack(value),
    LATERAL jsonb_array_elements(
        COALESCE(
            pack.value -> 'host_requirements',
            '[]'::jsonb
        )
    ) AS requirement(value),
    LATERAL jsonb_array_elements_text(
        requirement.value -> 'operations'
    ) AS operation(value)
)
""".strip()


HOST_READINESS_SELECT = """
COALESCE(
    (
        SELECT jsonb_agg(
            jsonb_build_object(
                'pack_code', required.pack_code,
                'requirement_code',
                    required.requirement_code,
                'operation', required.operation,
                'binding', to_jsonb(binding),
                'attestation', to_jsonb(attestation),
                'grant', to_jsonb(host_grant)
            )
            ORDER BY required.pack_code,
                     required.requirement_code,
                     required.operation
        )
        FROM required_host_operations AS required
        LEFT JOIN LATERAL (
            SELECT candidate.*
            FROM host_runtime_bindings AS candidate
            WHERE candidate.capability_code =
                required.pack_code
              AND candidate.requirement_code =
                required.requirement_code
              AND candidate.desired_state <> 'retired'
            ORDER BY candidate.updated_at DESC,
                     candidate.id
            LIMIT 1
        ) AS binding ON TRUE
        LEFT JOIN LATERAL (
            SELECT candidate.revision,
                   candidate.observed_generation,
                   candidate.runtime_digest,
                   candidate.executor_identity_digest,
                   candidate.permission_revision,
                   candidate.conditions,
                   candidate.observed_at
            FROM host_runtime_attestations AS candidate
            WHERE candidate.binding_id = binding.id
            ORDER BY candidate.revision DESC
            LIMIT 1
        ) AS attestation ON TRUE
        LEFT JOIN LATERAL (
            SELECT candidate.id,
                   candidate.workspace_id,
                   candidate.binding_id,
                   candidate.binding_generation,
                   candidate.operation,
                   candidate.operation_args_sha256,
                   candidate.policy_revision,
                   candidate.attestation_revision,
                   candidate.expires_at,
                   candidate.status,
                   candidate.provider_code,
                   candidate.voice_profile_id,
                   candidate.reference_rights_revision
            FROM workspace_host_grants AS candidate
            WHERE candidate.workspace_id = :workspace_id
              AND candidate.binding_id = binding.id
              AND candidate.operation =
                  required.operation
            ORDER BY candidate.policy_revision DESC,
                     candidate.id
            LIMIT 1
        ) AS host_grant ON TRUE
    ),
    '[]'::jsonb
)
""".strip()
