import * as crypto from "crypto";
import * as path from "path";

const CLAIM_KEYS = [
    "schema_version",
    "workspace_id",
    "binding_id",
    "binding_generation",
    "capability_code",
    "requirement_code",
    "capability_version",
    "operation",
    "operation_args_sha256",
    "grant_id",
    "attestation_revision",
    "policy_revision",
    "runtime_digest",
    "host_assets_digest",
    "entrypoint",
    "entrypoint_digest",
    "materialized_root",
    "permission_classes",
    "resource_lane",
    "provider_code",
    "voice_profile_id",
    "reference_rights_revision",
    "issued_at",
    "expires_at",
] as const;

export interface HostExecutionPermitClaims {
    schema_version: "mindscape.host-runtime-execution-permit.v1";
    workspace_id: string;
    binding_id: string;
    binding_generation: number;
    capability_code: string;
    requirement_code: string;
    capability_version: string;
    operation: string;
    operation_args_sha256: string;
    grant_id: string;
    attestation_revision: number;
    policy_revision: number;
    runtime_digest: string;
    host_assets_digest: string;
    entrypoint: string;
    entrypoint_digest: string;
    materialized_root: string;
    permission_classes: string[];
    resource_lane: string;
    provider_code: string | null;
    voice_profile_id: string | null;
    reference_rights_revision: number | null;
    issued_at: string;
    expires_at: string;
}

export interface HostExecutionPermit {
    claims: HostExecutionPermitClaims;
    signature: string;
}

export function requireWorkspaceHostAdmission(
    value: unknown,
    options: {
        secret: string;
        operation: string;
        operationArgs: string[];
        allowedPermissionClasses: ReadonlySet<string>;
        now?: Date;
    },
): HostExecutionPermitClaims {
    const permit = requireRecord(value, "host_admission_permit_invalid");
    requireExactKeys(permit, ["claims", "signature"], "host_admission_permit_keys_invalid");
    const claims = requireClaims(permit.claims);
    const signature = requireDigest(permit.signature, "host_admission_signature_invalid");
    const secretBytes = Buffer.from(options.secret, "utf8");
    if (secretBytes.byteLength < 32) {
        throw new Error("host_admission_secret_unavailable");
    }
    const expected = crypto
        .createHmac("sha256", secretBytes)
        .update(canonicalJson(claims))
        .digest("hex");
    if (!crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature))) {
        throw new Error("host_admission_signature_invalid");
    }
    if (claims.operation !== options.operation) {
        throw new Error("host_admission_operation_mismatch");
    }
    const argsDigest = crypto
        .createHash("sha256")
        .update(JSON.stringify(options.operationArgs))
        .digest("hex");
    if (claims.operation_args_sha256 !== argsDigest) {
        throw new Error("host_admission_operation_args_mismatch");
    }
    const observedNow = options.now ?? new Date();
    const issuedAt = new Date(claims.issued_at);
    const expiresAt = new Date(claims.expires_at);
    if (
        !Number.isFinite(issuedAt.getTime())
        || !Number.isFinite(expiresAt.getTime())
        || expiresAt <= observedNow
        || issuedAt.getTime() > observedNow.getTime() + 5_000
        || expiresAt.getTime() - issuedAt.getTime() > 60_000
    ) {
        throw new Error("host_admission_time_invalid");
    }
    if (
        claims.permission_classes.some(
            (permissionClass) => !options.allowedPermissionClasses.has(permissionClass),
        )
    ) {
        throw new Error("host_admission_permission_ceiling_exceeded");
    }
    return claims;
}

function requireClaims(value: unknown): HostExecutionPermitClaims {
    const claims = requireRecord(value, "host_admission_claims_invalid");
    requireExactKeys(claims, [...CLAIM_KEYS], "host_admission_claims_keys_invalid");
    const stringKeys = [
        "workspace_id",
        "binding_id",
        "capability_code",
        "requirement_code",
        "capability_version",
        "grant_id",
        "resource_lane",
    ];
    for (const key of stringKeys) {
        if (typeof claims[key] !== "string" || claims[key].length === 0) {
            throw new Error(`host_admission_${key}_invalid`);
        }
    }
    if (claims.schema_version !== "mindscape.host-runtime-execution-permit.v1") {
        throw new Error("host_admission_schema_invalid");
    }
    if (
        typeof claims.operation !== "string"
        || !/^[a-z][a-z0-9_.-]{1,63}$/.test(claims.operation)
    ) {
        throw new Error("host_admission_operation_invalid");
    }
    if (
        claims.runtime_digest !== claims.host_assets_digest
        || typeof claims.capability_code !== "string"
        || !/^[a-z0-9_]{2,128}$/.test(claims.capability_code)
        || typeof claims.requirement_code !== "string"
        || !/^[a-z][a-z0-9_]{1,63}$/.test(claims.requirement_code)
        || typeof claims.capability_version !== "string"
        || !/^\d+\.\d+\.\d+$/.test(claims.capability_version)
        || typeof claims.resource_lane !== "string"
        || !/^host\.[a-z0-9_.-]+$/.test(claims.resource_lane)
    ) {
        throw new Error("host_admission_runtime_identity_invalid");
    }
    for (const key of ["binding_generation", "attestation_revision", "policy_revision"]) {
        if (!Number.isInteger(claims[key]) || Number(claims[key]) < 1) {
            throw new Error(`host_admission_${key}_invalid`);
        }
    }
    for (const key of [
        "operation_args_sha256",
        "runtime_digest",
        "host_assets_digest",
        "entrypoint_digest",
    ]) {
        requireDigest(claims[key], `host_admission_${key}_invalid`);
    }
    if (
        typeof claims.entrypoint !== "string"
        || !claims.entrypoint.startsWith("scripts/")
        || path.posix.isAbsolute(claims.entrypoint)
        || claims.entrypoint.split("/").includes("..")
    ) {
        throw new Error("host_admission_entrypoint_invalid");
    }
    if (typeof claims.materialized_root !== "string" || !path.isAbsolute(claims.materialized_root)) {
        throw new Error("host_admission_materialized_root_invalid");
    }
    if (
        !Array.isArray(claims.permission_classes)
        || claims.permission_classes.length === 0
        || claims.permission_classes.some((item) => typeof item !== "string" || !item)
        || new Set(claims.permission_classes).size !== claims.permission_classes.length
    ) {
        throw new Error("host_admission_permission_classes_invalid");
    }
    const voiceValues = [
        claims.provider_code,
        claims.voice_profile_id,
        claims.reference_rights_revision,
    ];
    const present = voiceValues.filter((item) => item !== null).length;
    if (
        present !== 0
        && (
            present !== 3
            || typeof claims.provider_code !== "string"
            || claims.provider_code.length === 0
            || typeof claims.voice_profile_id !== "string"
            || claims.voice_profile_id.length === 0
            || !Number.isInteger(claims.reference_rights_revision)
            || Number(claims.reference_rights_revision) < 1
        )
    ) {
        throw new Error("host_admission_voice_scope_invalid");
    }
    if (typeof claims.issued_at !== "string" || typeof claims.expires_at !== "string") {
        throw new Error("host_admission_time_invalid");
    }
    return claims as unknown as HostExecutionPermitClaims;
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

function requireRecord(value: unknown, code: string): Record<string, unknown> {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
        throw new Error(code);
    }
    return value as Record<string, unknown>;
}

function requireExactKeys(
    value: Record<string, unknown>,
    expected: string[],
    code: string,
): void {
    const actual = Object.keys(value).sort();
    if (actual.length !== expected.length || actual.some((key, index) => key !== [...expected].sort()[index])) {
        throw new Error(code);
    }
}

function requireDigest(value: unknown, code: string): string {
    if (typeof value !== "string" || !/^[0-9a-f]{64}$/.test(value)) {
        throw new Error(code);
    }
    return value;
}
