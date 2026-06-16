import { spawn } from "child_process";
import * as net from "net";

import type { ManagedWorkerState } from "./host-resource-lane-worker-state.js";

type ManagedWorker = ManagedWorkerState;

export function isPortListening(port: number): Promise<boolean> {
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

export function listPortOwners(port: number): Promise<number[]> {
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

export function listChildPids(pid: number): Promise<number[]> {
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

export function delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

export function isPidAlive(pid: number): boolean {
    try {
        process.kill(pid, 0);
        return true;
    } catch {
        return false;
    }
}

export function signalPid(pid: number, signal: NodeJS.Signals): boolean {
    try {
        process.kill(pid, signal);
        return true;
    } catch {
        return false;
    }
}

export async function listDescendantPids(pid: number, seen = new Set<number>()): Promise<number[]> {
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

export function uniquePositivePids(pids: number[]): number[] {
    return Array.from(new Set(pids.filter((pid) => Number.isFinite(pid) && pid > 0)));
}

export function workerAgeSeconds(worker: ManagedWorker): number {
    const startedAt = Date.parse(worker.startedAt);
    if (!Number.isFinite(startedAt)) {
        return Number.POSITIVE_INFINITY;
    }
    return Math.max(0, (Date.now() - startedAt) / 1000);
}

export async function workerStopCandidates(worker: ManagedWorker | undefined, port: number): Promise<number[]> {
    const candidates: number[] = [];
    if (worker) {
        candidates.push(worker.pid, ...(await listDescendantPids(worker.pid)));
    }
    if (port > 0) {
        candidates.push(...(await listPortOwners(port)));
    }
    return uniquePositivePids(candidates);
}

export async function signalPids(pids: number[], signal: NodeJS.Signals): Promise<number[]> {
    const signaled: number[] = [];
    for (const pid of pids) {
        if (signalPid(pid, signal)) {
            signaled.push(pid);
        }
    }
    return signaled;
}

export async function waitForStopVerification(
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
