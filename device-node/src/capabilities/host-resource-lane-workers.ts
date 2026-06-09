import { spawn } from "child_process";
import { closeSync, existsSync, mkdirSync, openSync, readFileSync } from "fs";
import * as net from "net";
import * as path from "path";
import { fileURLToPath } from "url";

interface LaneWorkerTargetArgs {
    lane_id?: unknown;
    desired_worker_count?: unknown;
    queue_shard?: unknown;
    runner_profile?: unknown;
    resource_class?: unknown;
    worker_env?: unknown;
}

interface ManagedWorker {
    laneId: string;
    pid: number;
    port: number;
    logDir: string;
    watchdogStateFile: string;
    startedAt: string;
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const workers = new Map<string, ManagedWorker>();
const WORKER_START_GRACE_SECONDS = 120;

function cleanString(value: unknown): string {
    return String(value || "").trim();
}

function cleanInteger(value: unknown): number {
    const parsed = Number.parseInt(String(value ?? "0"), 10);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

function cleanWorkerEnv(value: unknown): Record<string, string> {
    if (!value || typeof value !== "object") {
        return {};
    }
    const env: Record<string, string> = {};
    for (const [key, rawValue] of Object.entries(value as Record<string, unknown>)) {
        const normalizedKey = cleanString(key);
        if (!normalizedKey || rawValue === undefined || rawValue === null) {
            continue;
        }
        env[normalizedKey] = String(rawValue);
    }
    return env;
}

function projectRootCandidates(): string[] {
    const configured = cleanString(process.env.LOCAL_CORE_PROJECT_ROOT);
    const candidates = [
        configured,
        path.resolve(__dirname, "../../.."),
        process.cwd(),
        path.resolve(process.cwd(), ".."),
    ];
    return candidates.filter((candidate, index) => candidate && candidates.indexOf(candidate) === index);
}

function mlxLauncherPath(): { root: string; script: string } | null {
    for (const root of projectRootCandidates()) {
        const script = path.join(root, "scripts/mlx-server/start-mlx-server.sh");
        if (existsSync(script)) {
            return { root, script };
        }
    }
    return null;
}

function safeLaneSlug(laneId: string): string {
    return laneId.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^_+|_+$/g, "") || "lane";
}

function laneRuntimePaths(root: string, laneId: string): { logDir: string; watchdogStateFile: string } {
    const slug = safeLaneSlug(laneId);
    const logDir = path.join(root, "scripts/mlx-server/logs", slug);
    const watchdogDir = path.join(root, ".tmp/mlx-watchdog");
    mkdirSync(logDir, { recursive: true });
    mkdirSync(watchdogDir, { recursive: true });
    return {
        logDir,
        watchdogStateFile: path.join(watchdogDir, `${slug}.json`),
    };
}

function readDotenvValue(root: string, key: string): string {
    const envPath = path.join(root, ".env");
    if (!existsSync(envPath)) {
        return "";
    }
    try {
        for (const line of readFileSync(envPath, "utf8").split(/\r?\n/)) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith("#")) {
                continue;
            }
            const separator = trimmed.indexOf("=");
            if (separator <= 0) {
                continue;
            }
            if (trimmed.slice(0, separator).trim() !== key) {
                continue;
            }
            return trimmed
                .slice(separator + 1)
                .trim()
                .replace(/^['"]|['"]$/g, "");
        }
    } catch {
        return "";
    }
    return "";
}

function dataHostRoot(root: string): string {
    return (
        cleanString(process.env.LOCAL_CORE_DATA_HOST_DIR)
        || readDotenvValue(root, "LOCAL_CORE_DATA_HOST_DIR")
        || path.join(root, "data")
    );
}

function hostPathForContainerDataPath(root: string, containerPath: string): string {
    const normalized = cleanString(containerPath);
    if (!normalized.startsWith("/app/data/")) {
        return normalized;
    }
    return path.join(dataHostRoot(root), normalized.slice("/app/data/".length));
}

function watchdogStateFileForWorker(
    root: string,
    laneId: string,
    workerEnv: Record<string, string>
): string {
    const explicitHostPath = cleanString(workerEnv.MLX_WATCHDOG_STATE_FILE);
    if (explicitHostPath) {
        return hostPathForContainerDataPath(root, explicitHostPath);
    }
    const runnerStateFile = cleanString(workerEnv.VLM_WATCHDOG_STATE_FILE);
    if (runnerStateFile) {
        return hostPathForContainerDataPath(root, runnerStateFile);
    }
    const slug = safeLaneSlug(laneId);
    return path.join(dataHostRoot(root), "runtime/mlx-watchdog", `${slug}.json`);
}

function isPortListening(port: number): Promise<boolean> {
    return new Promise((resolve) => {
        const socket = net.createConnection({ host: "127.0.0.1", port });
        const finish = (listening: boolean): void => {
            socket.removeAllListeners();
            socket.destroy();
            resolve(listening);
        };
        socket.setTimeout(500);
        socket.once("connect", () => finish(true));
        socket.once("timeout", () => finish(false));
        socket.once("error", () => finish(false));
    });
}

function listPortOwners(port: number): Promise<number[]> {
    return new Promise((resolve) => {
        const child = spawn("lsof", ["-ti", `tcp:${port}`], {
            shell: false,
            timeout: 3000,
        });
        let stdout = "";
        child.stdout.on("data", (data) => {
            stdout += data.toString();
        });
        child.on("close", () => {
            const pids = stdout
                .split(/\s+/)
                .map((value) => Number.parseInt(value, 10))
                .filter((value) => Number.isFinite(value) && value > 0);
            resolve(Array.from(new Set(pids)));
        });
        child.on("error", () => resolve([]));
    });
}

function listChildPids(pid: number): Promise<number[]> {
    return new Promise((resolve) => {
        const child = spawn("pgrep", ["-P", String(pid)], {
            shell: false,
            timeout: 3000,
        });
        let stdout = "";
        child.stdout.on("data", (data) => {
            stdout += data.toString();
        });
        child.on("close", () => {
            const pids = stdout
                .split(/\s+/)
                .map((value) => Number.parseInt(value, 10))
                .filter((value) => Number.isFinite(value) && value > 0);
            resolve(Array.from(new Set(pids)));
        });
        child.on("error", () => resolve([]));
    });
}

function delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function isPidAlive(pid: number): boolean {
    try {
        process.kill(pid, 0);
        return true;
    } catch {
        return false;
    }
}

function signalPid(pid: number, signal: NodeJS.Signals): boolean {
    try {
        process.kill(pid, signal);
        return true;
    } catch {
        return false;
    }
}

async function listDescendantPids(pid: number, seen = new Set<number>()): Promise<number[]> {
    const children = await listChildPids(pid);
    for (const childPid of children) {
        if (seen.has(childPid)) {
            continue;
        }
        seen.add(childPid);
        await listDescendantPids(childPid, seen);
    }
    return Array.from(seen);
}

function uniquePositivePids(pids: number[]): number[] {
    return Array.from(new Set(pids.filter((pid) => Number.isFinite(pid) && pid > 0)));
}

function workerAgeSeconds(worker: ManagedWorker): number {
    const startedAt = Date.parse(worker.startedAt);
    if (!Number.isFinite(startedAt)) {
        return Number.POSITIVE_INFINITY;
    }
    return Math.max(0, (Date.now() - startedAt) / 1000);
}

async function workerStopCandidates(worker: ManagedWorker | undefined, port: number): Promise<number[]> {
    const candidates: number[] = [];
    if (worker) {
        candidates.push(worker.pid, ...(await listDescendantPids(worker.pid)));
    }
    if (port > 0) {
        candidates.push(...(await listPortOwners(port)));
    }
    return uniquePositivePids(candidates);
}

async function signalPids(pids: number[], signal: NodeJS.Signals): Promise<number[]> {
    const signaled: number[] = [];
    for (const pid of pids) {
        if (signalPid(pid, signal)) {
            signaled.push(pid);
        }
    }
    return signaled;
}

async function waitForStopVerification(
    worker: ManagedWorker | undefined,
    port: number,
    timeoutMs: number
): Promise<{ verified: boolean; remainingPids: number[]; remainingPortOwners: number[]; portListening: boolean }> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const remainingPids = (await workerStopCandidates(worker, port)).filter(isPidAlive);
        const remainingPortOwners = port > 0 ? await listPortOwners(port) : [];
        const portListening = port > 0 ? await isPortListening(port) : false;
        if (remainingPids.length === 0 && remainingPortOwners.length === 0 && !portListening) {
            return {
                verified: true,
                remainingPids: [],
                remainingPortOwners: [],
                portListening: false,
            };
        }
        await delay(500);
    }
    const remainingPids = (await workerStopCandidates(worker, port)).filter(isPidAlive);
    const remainingPortOwners = port > 0 ? await listPortOwners(port) : [];
    const portListening = port > 0 ? await isPortListening(port) : false;
    return {
        verified: remainingPids.length === 0 && remainingPortOwners.length === 0 && !portListening,
        remainingPids,
        remainingPortOwners,
        portListening,
    };
}

async function stopLaneWorker(laneId: string, port: number): Promise<Record<string, unknown>> {
    const worker = workers.get(laneId);
    const stoppedPids: number[] = [];
    const signalWorkerGroup = (signal: NodeJS.Signals): void => {
        if (!worker) {
            return;
        }
        if (signalPid(-worker.pid, signal) || signalPid(worker.pid, signal)) {
            stoppedPids.push(worker.pid);
        }
    };
    if (worker) {
        signalWorkerGroup("SIGTERM");
    }
    for (const pid of await signalPids(await workerStopCandidates(worker, port), "SIGTERM")) {
        stoppedPids.push(pid);
    }
    let verification = await waitForStopVerification(worker, port, 2500);
    if (!verification.verified) {
        signalWorkerGroup("SIGKILL");
        for (const pid of await signalPids(await workerStopCandidates(worker, port), "SIGKILL")) {
            stoppedPids.push(pid);
        }
        verification = await waitForStopVerification(worker, port, 7000);
    }
    if (verification.verified) {
        workers.delete(laneId);
    }
    const uniqueStoppedPids = uniquePositivePids(stoppedPids);
    return {
        accepted: verification.verified,
        reason: verification.verified
            ? uniqueStoppedPids.length > 0
                ? "worker_target_stopped"
                : "worker_target_zero_synced"
            : "worker_target_stop_incomplete",
        lane_id: laneId,
        desired_worker_count: 0,
        active_worker_count: verification.verified ? 0 : verification.remainingPids.length,
        stopped_pids: uniqueStoppedPids,
        stop_verified: verification.verified,
        port_listening: verification.portListening,
        remaining_pids: verification.remainingPids,
        remaining_port_owners: verification.remainingPortOwners,
    };
}

function spawnMlxWorker(
    laneId: string,
    workerEnv: Record<string, string>,
    launcher: { root: string; script: string },
    port: number
): ManagedWorker {
    const runtimePaths = laneRuntimePaths(launcher.root, laneId);
    const watchdogStateFile = watchdogStateFileForWorker(
        launcher.root,
        laneId,
        workerEnv,
    );
    mkdirSync(path.dirname(watchdogStateFile), { recursive: true });
    const env = {
        ...process.env,
        ...workerEnv,
        MLX_PORT: String(port),
        MLX_HOST: workerEnv.MLX_HOST || "0.0.0.0",
        MLX_LOG_DIR: runtimePaths.logDir,
        MLX_WATCHDOG_STATE_FILE: watchdogStateFile,
        PYTHONUNBUFFERED: "1",
    };
    const stdoutFd = openSync(path.join(runtimePaths.logDir, "mlx-server.log"), "a");
    const stderrFd = openSync(path.join(runtimePaths.logDir, "mlx-server.error.log"), "a");
    const child = spawn(launcher.script, [], {
        cwd: launcher.root,
        env,
        detached: true,
        shell: false,
        stdio: ["ignore", stdoutFd, stderrFd],
    });
    if (!child.pid) {
        throw new Error("mlx_worker_pid_missing");
    }
    child.unref();
    closeSync(stdoutFd);
    closeSync(stderrFd);
    const worker = {
        laneId,
        pid: child.pid,
        port,
        logDir: runtimePaths.logDir,
        watchdogStateFile,
        startedAt: new Date().toISOString(),
    };
    workers.set(laneId, worker);
    child.once("exit", () => {
        const current = workers.get(laneId);
        if (current?.pid === child.pid) {
            workers.delete(laneId);
        }
    });
    return worker;
}

export async function hostResourceLaneWorkersSet(args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const payload = args as LaneWorkerTargetArgs;
    const laneId = cleanString(payload.lane_id);
    const queueShard = cleanString(payload.queue_shard);
    const runnerProfile = cleanString(payload.runner_profile);
    const resourceClass = cleanString(payload.resource_class);
    const desiredWorkerCount = cleanInteger(payload.desired_worker_count);
    const workerEnv = cleanWorkerEnv(payload.worker_env);
    const port = cleanInteger(workerEnv.MLX_PORT);

    if (!laneId) {
        return {
            accepted: false,
            reason: "lane_id_required",
        };
    }
    if (desiredWorkerCount === 0) {
        return {
            ...(await stopLaneWorker(laneId, port)),
            queue_shard: queueShard || null,
        };
    }
    if (desiredWorkerCount > 1) {
        return {
            accepted: false,
            reason: "desired_worker_count_exceeds_device_node_limit",
            lane_id: laneId,
            desired_worker_count: desiredWorkerCount,
            max_worker_count: 1,
        };
    }
    if (cleanString(workerEnv.LOCAL_CORE_RUNTIME_ADAPTER_ID) !== "apple_mlx_vlm") {
        return {
            accepted: false,
            reason: "unsupported_worker_runtime_adapter",
            lane_id: laneId,
            runtime_adapter_id: cleanString(workerEnv.LOCAL_CORE_RUNTIME_ADAPTER_ID) || null,
        };
    }
    if (port <= 0) {
        return {
            accepted: false,
            reason: "mlx_port_required",
            lane_id: laneId,
        };
    }
    if (!cleanString(workerEnv.MLX_MODEL)) {
        return {
            accepted: false,
            reason: "mlx_model_required",
            lane_id: laneId,
            port,
        };
    }

    const launcher = mlxLauncherPath();
    if (!launcher) {
        return {
            accepted: false,
            reason: "mlx_launcher_missing",
            lane_id: laneId,
        };
    }
    const current = workers.get(laneId);
    if (current) {
        if (await isPortListening(current.port)) {
            return {
                accepted: true,
                reason: "worker_target_already_running",
                lane_id: laneId,
                queue_shard: queueShard || null,
                runner_profile: runnerProfile || null,
                resource_class: resourceClass || null,
                desired_worker_count: desiredWorkerCount,
                active_worker_count: 1,
                pid: current.pid,
                port: current.port,
                worker_env_keys: Object.keys(workerEnv).sort(),
            };
        }
        const ageSeconds = workerAgeSeconds(current);
        if (ageSeconds < WORKER_START_GRACE_SECONDS) {
            return {
                accepted: true,
                reason: "worker_target_starting",
                lane_id: laneId,
                queue_shard: queueShard || null,
                runner_profile: runnerProfile || null,
                resource_class: resourceClass || null,
                desired_worker_count: desiredWorkerCount,
                active_worker_count: 0,
                pid: current.pid,
                port: current.port,
                started_at: current.startedAt,
                worker_age_seconds: ageSeconds,
                startup_grace_seconds: WORKER_START_GRACE_SECONDS,
                worker_env_keys: Object.keys(workerEnv).sort(),
            };
        }
        const stopResult = await stopLaneWorker(laneId, current.port);
        if (stopResult.accepted !== true) {
            return {
                ...stopResult,
                reason: "worker_target_restart_blocked",
                queue_shard: queueShard || null,
                runner_profile: runnerProfile || null,
                resource_class: resourceClass || null,
                desired_worker_count: desiredWorkerCount,
                blocked_worker_pid: current.pid,
                blocked_worker_port: current.port,
            };
        }
    }
    if (await isPortListening(port)) {
        return {
            accepted: true,
            reason: "worker_target_port_already_listening",
            lane_id: laneId,
            queue_shard: queueShard || null,
            runner_profile: runnerProfile || null,
            resource_class: resourceClass || null,
            desired_worker_count: desiredWorkerCount,
            active_worker_count: 1,
            port,
            worker_env_keys: Object.keys(workerEnv).sort(),
        };
    }

    try {
        const worker = spawnMlxWorker(laneId, workerEnv, launcher, port);
        return {
            accepted: true,
            reason: "worker_target_started",
            lane_id: laneId,
            queue_shard: queueShard || null,
            runner_profile: runnerProfile || null,
            resource_class: resourceClass || null,
            desired_worker_count: desiredWorkerCount,
            active_worker_count: 1,
            pid: worker.pid,
            port: worker.port,
            log_dir: worker.logDir,
            watchdog_state_file: worker.watchdogStateFile,
            started_at: worker.startedAt,
            launcher_script: launcher.script,
            worker_env_keys: Object.keys(workerEnv).sort(),
        };
    } catch (error) {
        return {
            accepted: false,
            reason: "worker_spawn_failed",
            lane_id: laneId,
            queue_shard: queueShard || null,
            desired_worker_count: desiredWorkerCount,
            error: error instanceof Error ? error.message : String(error),
        };
    }
}
