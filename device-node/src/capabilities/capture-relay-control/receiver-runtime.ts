import { spawn } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import * as path from "node:path";

import {
    projectRootCandidates,
    readDotenvValue,
} from "../host-resource-lane-worker-paths.js";

export interface ReceiverRuntime {
    root: string;
    python: string;
    script: string;
    preflightScript: string;
}

const PREFLIGHT_CACHE_MS = 5 * 60 * 1000;
export const RECEIVER_RUNTIME_PREFLIGHT_TIMEOUT_MS = 90 * 1000;

let readyFingerprint = "";
let readyAtMs = 0;
let inFlightPreflight: {
    fingerprint: string;
    promise: Promise<void>;
} | undefined;

function cleanString(value: unknown): string {
    return String(value || "").trim();
}

function fileStamp(filePath: string): string {
    const stat = statSync(filePath);
    return `${filePath}:${stat.size}:${stat.mtimeMs}`;
}

function runtimeFingerprint(runtime: ReceiverRuntime): string {
    return [
        runtime.root,
        fileStamp(runtime.python),
        fileStamp(runtime.script),
        fileStamp(runtime.preflightScript),
    ].join("|");
}

export function findReceiverRuntime(): ReceiverRuntime {
    for (const root of projectRootCandidates()) {
        const python = cleanString(process.env.LOCAL_CORE_MOTION_RECEIVER_PYTHON)
            || readDotenvValue(root, "LOCAL_CORE_MOTION_RECEIVER_PYTHON");
        const script = path.join(root, "scripts/live_motion_receiver.py");
        const preflightScript = path.join(
            root,
            "scripts/verify_live_motion_receiver_runtime.py",
        );
        if (
            python
            && existsSync(python)
            && existsSync(script)
            && existsSync(preflightScript)
        ) {
            return { root, python, script, preflightScript };
        }
    }
    throw new Error("live_media_receiver_runtime_unavailable");
}

function runReceiverRuntimePreflight(
    runtime: ReceiverRuntime,
    timeoutMs: number,
): Promise<void> {
    return new Promise((resolve, reject) => {
        let settled = false;
        let timeout: ReturnType<typeof setTimeout> | undefined;
        const child = spawn(runtime.python, [runtime.preflightScript], {
            cwd: runtime.root,
            env: process.env,
            shell: false,
            stdio: "ignore",
        });
        const finish = (error?: Error): void => {
            if (settled) return;
            settled = true;
            if (timeout) clearTimeout(timeout);
            if (error) {
                reject(error);
                return;
            }
            resolve();
        };
        child.once("error", () => {
            finish(new Error("live_media_receiver_runtime_preflight_failed"));
        });
        child.once("exit", (code) => {
            finish(
                code === 0
                    ? undefined
                    : new Error("live_media_receiver_runtime_preflight_failed"),
            );
        });
        timeout = setTimeout(() => {
            if (settled) return;
            child.kill("SIGKILL");
            finish(new Error("live_media_receiver_runtime_preflight_timeout"));
        }, Math.max(timeoutMs, 1));
    });
}

export function ensureReceiverRuntime(
    runtime: ReceiverRuntime,
    nowMs = Date.now(),
    timeoutMs = RECEIVER_RUNTIME_PREFLIGHT_TIMEOUT_MS,
): Promise<void> {
    const fingerprint = runtimeFingerprint(runtime);
    if (
        fingerprint === readyFingerprint
        && nowMs - readyAtMs >= 0
        && nowMs - readyAtMs < PREFLIGHT_CACHE_MS
    ) {
        return Promise.resolve();
    }
    if (
        inFlightPreflight
        && inFlightPreflight.fingerprint === fingerprint
    ) {
        return inFlightPreflight.promise;
    }

    const promise = runReceiverRuntimePreflight(runtime, timeoutMs)
        .then(() => {
            readyFingerprint = fingerprint;
            readyAtMs = nowMs;
        })
        .finally(() => {
            if (inFlightPreflight?.promise === promise) {
                inFlightPreflight = undefined;
            }
        });
    inFlightPreflight = { fingerprint, promise };
    return promise;
}

export function warmLiveMediaReceiverRuntime(): Promise<void> {
    return ensureReceiverRuntime(findReceiverRuntime());
}
