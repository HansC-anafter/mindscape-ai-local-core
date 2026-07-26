import * as fs from "fs";
import * as crypto from "crypto";
import {
    buildHostRuntimeAttestation,
    type HostRuntimeAttestation,
} from "./host-runtime-attestation.js";
import { prepareHostRuntime } from "./host-runtime-supervisor.js";

const EXACT_KEYS = [
    "binding_id",
    "generation",
    "capability_code",
    "requirement_code",
    "capability_version",
    "operations",
    "materialized_root",
    "entrypoint",
    "entrypoint_digest",
    "host_assets_digest",
    "runtime_digest",
    "permission_classes",
    "resource_lane",
] as const;

export async function reconcileHostRuntimeBinding(
    rawArgs: Record<string, unknown>,
    options: {
        allowedPermissionClasses: ReadonlySet<string>;
        pythonExecutable: string;
        permissionRevision?: number;
        observedAt?: Date;
        permissionProbe?: (permissionClasses: string[]) => boolean;
    },
): Promise<HostRuntimeAttestation> {
    const desired = requireDesired(rawArgs);
    const prepared = prepareHostRuntime(
        {
            bindingId: desired.binding_id,
            generation: desired.generation,
            capabilityCode: desired.capability_code,
            requirementCode: desired.requirement_code,
            capabilityVersion: desired.capability_version,
            operation: desired.operations[0],
            declaredOperations: desired.operations,
            operationArgs: [],
            materializedRoot: desired.materialized_root,
            entrypoint: desired.entrypoint,
            entrypointDigest: desired.entrypoint_digest,
            hostAssetsDigest: desired.host_assets_digest,
            runtimeDigest: desired.runtime_digest,
            permissionClasses: desired.permission_classes,
            resourceLane: desired.resource_lane,
        },
        options.pythonExecutable,
    );
    const permissionsWithinCeiling = desired.permission_classes.every(
        (permissionClass) => options.allowedPermissionClasses.has(permissionClass),
    );
    const permissionsReady = permissionsWithinCeiling && (
        options.permissionProbe?.(desired.permission_classes)
        ?? defaultPermissionProbe(desired.permission_classes)
    );
    const resourceLaneReady = desired.resource_lane === "host.io.light";
    return buildHostRuntimeAttestation({
        bindingId: desired.binding_id,
        generation: desired.generation,
        runtimeDigest: desired.runtime_digest,
        executorIdentity: {
            executor: "mindscape-device-node",
            executor_pid: process.pid,
            executor_path_sha256: digestText(process.execPath),
            entrypoint_digest: desired.entrypoint_digest,
            host_assets_digest: desired.host_assets_digest,
            prepared_argv_sha256: digestJson(prepared.argv),
            prepared_cwd_sha256: digestText(prepared.cwd),
        },
        permissionRevision: options.permissionRevision ?? 1,
        materialized: true,
        runtimeDigestVerified: true,
        supervisorReady: process.pid > 0,
        permissionsReady,
        resourceLaneReady,
        observedAt: options.observedAt,
    });
}

interface DesiredProjection {
    binding_id: string;
    generation: number;
    capability_code: string;
    requirement_code: string;
    capability_version: string;
    operations: string[];
    materialized_root: string;
    entrypoint: string;
    entrypoint_digest: string;
    host_assets_digest: string;
    runtime_digest: string;
    permission_classes: string[];
    resource_lane: string;
}

function requireDesired(rawArgs: Record<string, unknown>): DesiredProjection {
    const actualKeys = Object.keys(rawArgs).sort();
    const expectedKeys = [...EXACT_KEYS].sort();
    if (
        actualKeys.length !== expectedKeys.length
        || actualKeys.some((key, index) => key !== expectedKeys[index])
    ) {
        throw new Error("host_runtime_reconcile_request_keys_invalid");
    }
    const stringKeys = [
        "binding_id",
        "capability_code",
        "requirement_code",
        "capability_version",
        "materialized_root",
        "entrypoint",
        "entrypoint_digest",
        "host_assets_digest",
        "runtime_digest",
        "resource_lane",
    ];
    if (
        stringKeys.some(
            (key) => typeof rawArgs[key] !== "string" || rawArgs[key] === "",
        )
        || !Number.isInteger(rawArgs.generation)
        || Number(rawArgs.generation) < 1
        || !Array.isArray(rawArgs.operations)
        || rawArgs.operations.length === 0
        || rawArgs.operations.some(
            (operation) => (
                typeof operation !== "string"
                || !/^[a-z][a-z0-9_.-]{1,63}$/.test(operation)
            ),
        )
        || new Set(rawArgs.operations).size !== rawArgs.operations.length
        || !Array.isArray(rawArgs.permission_classes)
        || rawArgs.permission_classes.length === 0
        || rawArgs.permission_classes.some(
            (permissionClass) => typeof permissionClass !== "string" || !permissionClass,
        )
        || new Set(rawArgs.permission_classes).size !== rawArgs.permission_classes.length
        || rawArgs.runtime_digest !== rawArgs.host_assets_digest
    ) {
        throw new Error("host_runtime_reconcile_request_invalid");
    }
    return rawArgs as unknown as DesiredProjection;
}

function defaultPermissionProbe(permissionClasses: string[]): boolean {
    for (const permissionClass of permissionClasses) {
        if (
            permissionClass === "filesystem.read"
            || permissionClass === "filesystem.write"
            || permissionClass === "network.loopback"
        ) {
            continue;
        }
        if (permissionClass === "audio.output" && isExecutable("/usr/bin/afplay")) {
            continue;
        }
        return false;
    }
    return true;
}

function isExecutable(path: string): boolean {
    try {
        fs.accessSync(path, fs.constants.X_OK);
        return true;
    } catch {
        return false;
    }
}

function digestJson(value: unknown): string {
    return crypto.createHash("sha256").update(canonicalJson(value)).digest("hex");
}

function digestText(value: string): string {
    return crypto.createHash("sha256").update(value).digest("hex");
}

function canonicalJson(value: unknown): string {
    if (Array.isArray(value)) {
        return `[${value.map(canonicalJson).join(",")}]`;
    }
    if (value !== null && typeof value === "object") {
        const record = value as Record<string, unknown>;
        return `{${Object.keys(record).sort().map(
            (key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`,
        ).join(",")}}`;
    }
    return JSON.stringify(value);
}
