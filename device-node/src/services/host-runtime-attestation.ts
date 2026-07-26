import * as crypto from "crypto";

export type HostRuntimeConditionType =
    | "Materialized"
    | "RuntimeDigestVerified"
    | "SupervisorReady"
    | "PermissionsReady"
    | "ResourceLaneReady";

export interface HostRuntimeAttestation {
    binding_id: string;
    generation: number;
    runtime_digest: string;
    executor_identity_digest: string;
    permission_revision: number;
    conditions: Array<{
        type: HostRuntimeConditionType;
        status: "true" | "false" | "unknown";
        reason: string;
        observed_generation: number;
        observed_at: string;
    }>;
    observed_at: string;
}

export function buildHostRuntimeAttestation(input: {
    bindingId: string;
    generation: number;
    runtimeDigest: string;
    executorIdentity: Record<string, unknown>;
    permissionRevision: number;
    materialized: boolean;
    runtimeDigestVerified: boolean;
    supervisorReady: boolean;
    permissionsReady: boolean;
    resourceLaneReady: boolean;
    observedAt?: Date;
}): HostRuntimeAttestation {
    const observedAt = (input.observedAt ?? new Date()).toISOString();
    const conditions: Array<[HostRuntimeConditionType, boolean]> = [
        ["Materialized", input.materialized],
        ["RuntimeDigestVerified", input.runtimeDigestVerified],
        ["SupervisorReady", input.supervisorReady],
        ["PermissionsReady", input.permissionsReady],
        ["ResourceLaneReady", input.resourceLaneReady],
    ];
    return {
        binding_id: input.bindingId,
        generation: input.generation,
        runtime_digest: input.runtimeDigest,
        executor_identity_digest: crypto
            .createHash("sha256")
            .update(canonicalJson(input.executorIdentity))
            .digest("hex"),
        permission_revision: input.permissionRevision,
        conditions: conditions.map(([type, ready]) => ({
            type,
            status: ready ? "true" : "false",
            reason: ready ? "verified" : `${toSnakeCase(type)}_not_ready`,
            observed_generation: input.generation,
            observed_at: observedAt,
        })),
        observed_at: observedAt,
    };
}

function toSnakeCase(value: string): string {
    return value.replace(/([a-z])([A-Z])/g, "$1_$2").toLowerCase();
}

function canonicalJson(value: unknown): string {
    if (Array.isArray(value)) {
        return `[${value.map(canonicalJson).join(",")}]`;
    }
    if (value !== null && typeof value === "object") {
        const record = value as Record<string, unknown>;
        return `{${Object.keys(record)
            .sort()
            .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`)
            .join(",")}}`;
    }
    return JSON.stringify(value);
}
