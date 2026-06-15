import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "fs";
import * as path from "path";

export interface ManagedWorkerState {
    laneId: string;
    pid: number;
    port: number;
    logDir: string;
    watchdogStateFile: string;
    startedAt: string;
}

function safeLaneSlug(laneId: string): string {
    return laneId.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^_+|_+$/g, "") || "lane";
}

export function managedWorkerStateFile(root: string, laneId: string): string {
    return path.join(root, ".tmp", "mlx-workers", `${safeLaneSlug(laneId)}.json`);
}

export function persistManagedWorkerState(root: string, worker: ManagedWorkerState): string {
    const stateFile = managedWorkerStateFile(root, worker.laneId);
    mkdirSync(path.dirname(stateFile), { recursive: true });
    writeFileSync(stateFile, JSON.stringify(worker, null, 2), "utf8");
    return stateFile;
}

export function readPersistedManagedWorkerState(
    root: string,
    laneId: string,
): ManagedWorkerState | null {
    const stateFile = managedWorkerStateFile(root, laneId);
    if (!existsSync(stateFile)) {
        return null;
    }
    try {
        const payload = JSON.parse(readFileSync(stateFile, "utf8")) as Record<string, unknown>;
        const pid = Number.parseInt(String(payload.pid ?? "0"), 10);
        const port = Number.parseInt(String(payload.port ?? "0"), 10);
        const normalizedLaneId = String(payload.laneId || "").trim();
        const logDir = String(payload.logDir || "").trim();
        const watchdogStateFile = String(payload.watchdogStateFile || "").trim();
        const startedAt = String(payload.startedAt || "").trim();
        if (!normalizedLaneId || normalizedLaneId !== laneId) {
            return null;
        }
        if (!Number.isFinite(pid) || pid <= 0 || !Number.isFinite(port) || port <= 0) {
            return null;
        }
        if (!logDir || !watchdogStateFile || !startedAt) {
            return null;
        }
        return {
            laneId: normalizedLaneId,
            pid,
            port,
            logDir,
            watchdogStateFile,
            startedAt,
        };
    } catch {
        return null;
    }
}

export function clearPersistedManagedWorkerState(
    root: string,
    laneId: string,
    pid?: number,
): void {
    const stateFile = managedWorkerStateFile(root, laneId);
    if (!existsSync(stateFile)) {
        return;
    }
    if (pid && Number.isFinite(pid)) {
        const current = readPersistedManagedWorkerState(root, laneId);
        if (current && current.pid !== pid) {
            return;
        }
    }
    try {
        rmSync(stateFile, { force: true });
    } catch {
        // Best effort cleanup keeps worker control tolerant of stale metadata.
    }
}
