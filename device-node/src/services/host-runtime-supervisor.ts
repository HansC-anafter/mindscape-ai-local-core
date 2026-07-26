import { spawn, type ChildProcess } from "child_process";
import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import {
    canonicalJson,
    verifyHostRuntimeInventory,
} from "./host-runtime-inventory.js";

export interface PreparedHostRuntime {
    bindingId: string;
    generation: number;
    operation: string;
    runtimeRoot: string;
    entrypointPath: string;
    pythonExecutable: string;
    argv: string[];
    cwd: string;
    environment: NodeJS.ProcessEnv;
    hostAssetsDigest: string;
    runtimeDigest: string;
}

export interface HostRuntimeDesired {
    bindingId: string;
    generation: number;
    capabilityCode: string;
    requirementCode: string;
    capabilityVersion: string;
    operation: string;
    declaredOperations?: string[];
    operationArgs: string[];
    materializedRoot: string;
    entrypoint: string;
    entrypointDigest: string;
    hostAssetsDigest: string;
    runtimeDigest: string;
    permissionClasses: string[];
    resourceLane: string;
}

export interface HostRuntimeProcessReceipt {
    status: "started" | "already_running";
    binding_id: string;
    generation: number;
    process_identity: {
        pid: number;
        argv_sha256: string;
        cwd_sha256: string;
        entrypoint_path_sha256: string;
        host_assets_sha256: string;
    };
}

export interface HostRuntimeExecutionScope {
    workspaceId: string;
    operationArgsSha256: string;
}

type SpawnProcess = typeof spawn;

export class HostRuntimeSupervisor {
    private readonly processes = new Map<string, {
        bindingId: string;
        generation: number;
        workspaceId: string;
        operation: string;
        operationArgsSha256: string;
        child: ChildProcess;
        prepared: PreparedHostRuntime;
    }>();

    constructor(
        private readonly pythonExecutable: string,
        private readonly spawnProcess: SpawnProcess = spawn,
    ) {}

    prepare(desired: HostRuntimeDesired): PreparedHostRuntime {
        return prepareHostRuntime(desired, this.pythonExecutable);
    }

    async reconcile(
        desired: HostRuntimeDesired,
        scope: HostRuntimeExecutionScope,
    ): Promise<HostRuntimeProcessReceipt> {
        requireExecutionScope(scope);
        const prepared = this.prepare(desired);
        const processKey = executionProcessKey(desired, scope);
        await this.stopConflictingProcesses(desired, scope, processKey);
        const existing = this.processes.get(processKey);
        if (
            existing
            && existing.generation === desired.generation
            && existing.operation === desired.operation
            && existing.child.exitCode === null
            && existing.child.pid
        ) {
            return processReceipt("already_running", existing.prepared, existing.child.pid);
        }
        if (existing) {
            await stopChild(existing.child);
            this.processes.delete(processKey);
        }
        const child = this.spawnProcess(
            prepared.pythonExecutable,
            prepared.argv.slice(1),
            {
                cwd: prepared.cwd,
                shell: false,
                stdio: "ignore",
                env: prepared.environment,
            },
        );
        if (!child.pid) {
            throw new Error("host_runtime_process_start_failed");
        }
        this.processes.set(processKey, {
            bindingId: desired.bindingId,
            generation: desired.generation,
            workspaceId: scope.workspaceId,
            operation: desired.operation,
            operationArgsSha256: scope.operationArgsSha256,
            child,
            prepared,
        });
        child.once("exit", () => {
            const current = this.processes.get(processKey);
            if (current?.child === child) {
                this.processes.delete(processKey);
            }
        });
        return processReceipt("started", prepared, child.pid);
    }

    private async stopConflictingProcesses(
        desired: HostRuntimeDesired,
        scope: HostRuntimeExecutionScope,
        processKey: string,
    ): Promise<void> {
        for (const [key, existing] of [...this.processes.entries()]) {
            const oldGeneration = (
                existing.bindingId === desired.bindingId
                && existing.generation !== desired.generation
            );
            const replacedWorkspaceOperation = (
                existing.bindingId === desired.bindingId
                && existing.workspaceId === scope.workspaceId
                && existing.operation === desired.operation
                && key !== processKey
            );
            if (!oldGeneration && !replacedWorkspaceOperation) {
                continue;
            }
            await stopChild(existing.child);
            this.processes.delete(key);
        }
    }
}

export function prepareHostRuntime(
    desired: HostRuntimeDesired,
    pythonExecutable: string,
): PreparedHostRuntime {
    if (!path.isAbsolute(desired.materializedRoot) || !path.isAbsolute(pythonExecutable)) {
        throw new Error("host_runtime_absolute_path_required");
    }
    if (desired.runtimeDigest !== desired.hostAssetsDigest) {
        throw new Error("host_runtime_digest_identity_mismatch");
    }
    if (
        !desired.entrypoint.startsWith("scripts/")
        || path.posix.isAbsolute(desired.entrypoint)
        || desired.entrypoint.split("/").includes("..")
    ) {
        throw new Error("host_runtime_entrypoint_invalid");
    }
    const rootStat = fs.lstatSync(desired.materializedRoot);
    if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
        throw new Error("host_runtime_root_invalid");
    }
    const runtimeRoot = fs.realpathSync(desired.materializedRoot);
    if (runtimeRoot !== desired.materializedRoot) {
        throw new Error("host_runtime_root_redirected");
    }
    const inventoryPath = path.join(runtimeRoot, "host_assets.json");
    const inventoryStat = fs.lstatSync(inventoryPath);
    if (
        !inventoryStat.isFile()
        || inventoryStat.isSymbolicLink()
        || inventoryStat.size > 1_048_576
    ) {
        throw new Error("host_runtime_inventory_invalid");
    }
    const inventory = JSON.parse(fs.readFileSync(inventoryPath, "utf8")) as unknown;
    const assets = verifyHostRuntimeInventory(inventory, desired, runtimeRoot);
    const entrypointPath = path.join(runtimeRoot, ...desired.entrypoint.split("/"));
    const entrypointStat = fs.lstatSync(entrypointPath);
    if (!entrypointStat.isFile() || entrypointStat.isSymbolicLink()) {
        throw new Error("host_runtime_entrypoint_invalid");
    }
    if (fs.realpathSync(entrypointPath) !== entrypointPath) {
        throw new Error("host_runtime_entrypoint_redirected");
    }
    const entrypointBytes = fs.readFileSync(entrypointPath);
    const entrypointDigest = crypto.createHash("sha256").update(entrypointBytes).digest("hex");
    if (
        entrypointDigest !== desired.entrypointDigest
        || assets.get(desired.entrypoint)?.sha256 !== entrypointDigest
    ) {
        throw new Error("host_runtime_entrypoint_digest_mismatch");
    }
    const argv = [
        pythonExecutable,
        entrypointPath,
        desired.operation,
        ...desired.operationArgs,
    ];
    return {
        bindingId: desired.bindingId,
        generation: desired.generation,
        operation: desired.operation,
        runtimeRoot,
        entrypointPath,
        pythonExecutable,
        argv,
        cwd: runtimeRoot,
        environment: hostRuntimeEnvironment(),
        hostAssetsDigest: desired.hostAssetsDigest,
        runtimeDigest: desired.runtimeDigest,
    };
}

function hostRuntimeEnvironment(): NodeJS.ProcessEnv {
    const allowed = [
        "PATH",
        "HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "USER",
        "LOGNAME",
        "LIVE_INTERFACE_F5_TTS_MLX_COMMAND",
        "LIVE_INTERFACE_F5_TTS_MLX_PYTHON",
        "LIVE_INTERFACE_F5_TTS_MLX_Q",
        "LIVE_INTERFACE_F5_TTS_MLX_QUANTIZATION_BITS",
        "LIVE_INTERFACE_F5_TTS_MLX_REF_AUDIO",
        "LIVE_INTERFACE_F5_TTS_MLX_REF_DURATION_SECONDS",
        "LIVE_INTERFACE_F5_TTS_MLX_REF_TEXT",
        "LIVE_INTERFACE_F5_TTS_MLX_VOICE_PROFILE_ID",
        "LIVE_INTERFACE_HOST_TTS_COMMAND",
        "LIVE_INTERFACE_HOST_TTS_OUTPUT_DIR",
        "LIVE_INTERFACE_HOST_TTS_OUTPUT_FORMAT",
        "LIVE_INTERFACE_HOST_TTS_PLAY_COMMAND",
        "LIVE_INTERFACE_HOST_TTS_PROVIDER",
        "LIVE_INTERFACE_HOST_TTS_VOICE_PROFILE_ID",
        "LIVE_INTERFACE_KOKORO_TTS_URL",
        "LIVE_INTERFACE_KOKORO_VOICE",
        "LOCAL_STORAGE_PATH",
        "MINDSCAPE_STORAGE_HOST_DIR",
        "MMS_LOCAL_STORAGE_PATH",
        "MMS_TENANT_ID",
        "MINDSCAPE_CONTROL_API_URL",
        "MINDSCAPE_HOST_RUNTIME_TOKEN",
        "TENANT_ID",
    ];
    return Object.fromEntries(
        allowed
            .filter((key) => typeof process.env[key] === "string")
            .map((key) => [key, process.env[key]]),
    );
}

function processReceipt(
    status: "started" | "already_running",
    prepared: PreparedHostRuntime,
    pid: number,
): HostRuntimeProcessReceipt {
    return {
        status,
        binding_id: prepared.bindingId,
        generation: prepared.generation,
        process_identity: {
            pid,
            argv_sha256: digestJson(prepared.argv),
            cwd_sha256: digestText(prepared.cwd),
            entrypoint_path_sha256: digestText(prepared.entrypointPath),
            host_assets_sha256: prepared.hostAssetsDigest,
        },
    };
}

function requireExecutionScope(scope: HostRuntimeExecutionScope): void {
    if (
        typeof scope.workspaceId !== "string"
        || scope.workspaceId.length === 0
        || scope.workspaceId.length > 128
        || !/^[0-9a-f]{64}$/.test(scope.operationArgsSha256)
    ) {
        throw new Error("host_runtime_execution_scope_invalid");
    }
}

function executionProcessKey(
    desired: HostRuntimeDesired,
    scope: HostRuntimeExecutionScope,
): string {
    return digestJson([
        desired.bindingId,
        desired.generation,
        scope.workspaceId,
        desired.operation,
        scope.operationArgsSha256,
    ]);
}

async function stopChild(child: ChildProcess): Promise<void> {
    if (child.exitCode !== null) {
        return;
    }
    child.kill("SIGTERM");
    await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => {
            child.kill("SIGKILL");
            reject(new Error("host_runtime_previous_generation_stop_timeout"));
        }, 10_000);
        child.once("exit", () => {
            clearTimeout(timeout);
            resolve();
        });
    });
}

function digestJson(value: unknown): string {
    return crypto.createHash("sha256").update(canonicalJson(value)).digest("hex");
}

function digestText(value: string): string {
    return crypto.createHash("sha256").update(value).digest("hex");
}
