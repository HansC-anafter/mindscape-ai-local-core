import {
    requireWorkspaceHostAdmission,
    type HostExecutionPermit,
} from "./governance/workspace-host-admission-guard.js";
import {
    buildHostRuntimeAttestation,
    type HostRuntimeAttestation,
} from "./services/host-runtime-attestation.js";
import {
    HostRuntimeSupervisor,
    type HostRuntimeProcessReceipt,
} from "./services/host-runtime-supervisor.js";

export interface HostRuntimeExecutionResult {
    status: "started" | "already_running";
    binding_id: string;
    generation: number;
    operation: string;
    process: HostRuntimeProcessReceipt["process_identity"];
    attestation: HostRuntimeAttestation;
}

let supervisor: HostRuntimeSupervisor | null = null;

export async function executeHostRuntime(
    rawArgs: Record<string, unknown>,
    options: {
        secret: string;
        allowedPermissionClasses: ReadonlySet<string>;
        pythonExecutable: string;
        permissionRevision?: number;
        now?: Date;
        supervisor?: HostRuntimeSupervisor;
    },
): Promise<HostRuntimeExecutionResult> {
    const operation = rawArgs.operation;
    const operationArgs = rawArgs.operation_args;
    if (
        typeof operation !== "string"
        || !/^[a-z][a-z0-9_.-]{1,63}$/.test(operation)
        || !Array.isArray(operationArgs)
        || operationArgs.some(
            (value) => typeof value !== "string" || value.includes("\0") || value.length > 1024,
        )
        || operationArgs.length > 64
    ) {
        throw new Error("host_runtime_execution_request_invalid");
    }
    const claims = requireWorkspaceHostAdmission(rawArgs.permit, {
        secret: options.secret,
        operation: String(operation),
        operationArgs: operationArgs as string[],
        allowedPermissionClasses: options.allowedPermissionClasses,
        now: options.now,
    });
    const runtimeSupervisor = options.supervisor ?? sharedSupervisor(options.pythonExecutable);
    const receipt = await runtimeSupervisor.reconcile(
        {
            bindingId: claims.binding_id,
            generation: claims.binding_generation,
            capabilityCode: claims.capability_code,
            requirementCode: claims.requirement_code,
            capabilityVersion: claims.capability_version,
            operation: claims.operation,
            operationArgs: operationArgs as string[],
            materializedRoot: claims.materialized_root,
            entrypoint: claims.entrypoint,
            entrypointDigest: claims.entrypoint_digest,
            hostAssetsDigest: claims.host_assets_digest,
            runtimeDigest: claims.runtime_digest,
            permissionClasses: claims.permission_classes,
            resourceLane: claims.resource_lane,
        },
        {
            workspaceId: claims.workspace_id,
            operationArgsSha256: claims.operation_args_sha256,
        },
    );
    const attestation = buildHostRuntimeAttestation({
        bindingId: claims.binding_id,
        generation: claims.binding_generation,
        runtimeDigest: claims.runtime_digest,
        executorIdentity: {
            executor: "mindscape-device-node",
            executor_pid: process.pid,
            runtime_process: receipt.process_identity,
        },
        permissionRevision: options.permissionRevision ?? 1,
        materialized: true,
        runtimeDigestVerified: true,
        supervisorReady: true,
        permissionsReady: true,
        resourceLaneReady: true,
        observedAt: options.now,
    });
    return {
        status: receipt.status,
        binding_id: claims.binding_id,
        generation: claims.binding_generation,
        operation: claims.operation,
        process: receipt.process_identity,
        attestation,
    };
}

export async function hostRuntimeExecute(
    rawArgs: Record<string, unknown>,
    allowedPermissionClasses: ReadonlySet<string>,
): Promise<HostRuntimeExecutionResult> {
    return executeHostRuntime(rawArgs, {
        secret: process.env.HOST_RUNTIME_ADMISSION_HMAC_SECRET || "",
        allowedPermissionClasses,
        pythonExecutable:
            process.env.MINDSCAPE_HOST_RUNTIME_PYTHON
            || "/usr/bin/python3",
    });
}

function sharedSupervisor(pythonExecutable: string): HostRuntimeSupervisor {
    if (supervisor === null) {
        supervisor = new HostRuntimeSupervisor(pythonExecutable);
    }
    return supervisor;
}

export type { HostExecutionPermit };
