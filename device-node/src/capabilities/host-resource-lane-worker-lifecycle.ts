import { spawn } from "child_process";
import { closeSync, mkdirSync, openSync } from "fs";
import * as path from "path";

import {
    clearPersistedManagedWorkerState,
    persistManagedWorkerState,
    readPersistedManagedWorkerState,
    type ManagedWorkerState,
} from "./host-resource-lane-worker-state.js";
import {
    laneRuntimePaths,
    mlxLauncherPath,
    watchdogStateFileForWorker,
} from "./host-resource-lane-worker-paths.js";
import {
    isPidAlive,
    isPortListening,
    signalPid,
    signalPids,
    uniquePositivePids,
    waitForStopVerification,
    workerStopCandidates,
} from "./host-resource-lane-worker-processes.js";

export type ManagedWorker = ManagedWorkerState;

export const WORKER_START_GRACE_SECONDS = 120;

const workers = new Map<string, ManagedWorker>();

export function resolveManagedWorker(root: string, laneId: string): ManagedWorker | undefined {
    const current = workers.get(laneId);
    if (current) {
        return current;
    }
    const persisted = readPersistedManagedWorkerState(root, laneId);
    if (!persisted) {
        return undefined;
    }
    if (!isPidAlive(persisted.pid)) {
        clearPersistedManagedWorkerState(root, laneId, persisted.pid);
        return undefined;
    }
    workers.set(laneId, persisted);
    return persisted;
}

export async function stopLaneWorker(
    laneId: string,
    port: number,
    root?: string,
): Promise<Record<string, unknown>> {
    const launcherRoot = root || mlxLauncherPath()?.root;
    const worker = launcherRoot ? resolveManagedWorker(launcherRoot, laneId) : workers.get(laneId);
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
        if (launcherRoot) {
            clearPersistedManagedWorkerState(launcherRoot, laneId, worker?.pid);
        }
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

export function spawnMlxWorker(
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
    persistManagedWorkerState(launcher.root, worker);
    child.once("exit", () => {
        const current = workers.get(laneId);
        if (current?.pid === child.pid) {
            workers.delete(laneId);
        }
        clearPersistedManagedWorkerState(launcher.root, laneId, child.pid);
    });
    return worker;
}
