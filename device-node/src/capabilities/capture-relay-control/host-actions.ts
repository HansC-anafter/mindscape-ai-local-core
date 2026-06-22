import { spawn } from "child_process";

import {
    COMMON_OBS_APP_PATHS,
    DEFAULT_OBS_APP_PATH,
} from "./constants.js";
import { resolveObsAppPath } from "./host-discovery.js";
import type { HostCommandResult, ObsOpenResult } from "./types.js";

export async function openObsApp(): Promise<ObsOpenResult> {
    const obsAppPath = resolveObsAppPath();
    if (!obsAppPath) {
        return {
            opened: false,
            reason: "obs_app_missing",
            app_path: DEFAULT_OBS_APP_PATH,
            expected_app_paths: COMMON_OBS_APP_PATHS,
        };
    }
    return new Promise((resolve) => {
        const child = spawn("open", [obsAppPath], { shell: false });
        let stderr = "";
        child.stderr.on("data", (chunk) => {
            stderr += chunk.toString("utf-8");
        });
        child.on("close", (code) => {
            if (code === 0) {
                resolve({ opened: true, app_path: obsAppPath });
                return;
            }
            resolve({
                opened: false,
                reason: stderr.trim() || `open_obs_exit_${code}`,
                app_path: obsAppPath,
            });
        });
        child.on("error", (error) => {
            resolve({ opened: false, reason: error.message, app_path: obsAppPath });
        });
    });
}

export function runHostCommand(
    command: string,
    args: string[],
    timeoutMs: number,
): Promise<HostCommandResult> {
    return new Promise((resolve) => {
        const child = spawn(command, args, {
            shell: false,
            stdio: ["ignore", "pipe", "pipe"],
        });
        let stdout = "";
        let stderr = "";
        let settled = false;
        const finish = (result: { exitCode: number | null; timedOut: boolean }) => {
            if (settled) {
                return;
            }
            settled = true;
            resolve({
                exitCode: result.exitCode,
                stdout: stdout.slice(-4000),
                stderr: stderr.slice(-4000),
                timedOut: result.timedOut,
            });
        };
        const timer = setTimeout(() => {
            child.kill("SIGTERM");
            setTimeout(() => {
                if (child.exitCode === null && !child.killed) {
                    child.kill("SIGKILL");
                }
            }, 1000);
            finish({ exitCode: null, timedOut: true });
        }, timeoutMs);
        child.stdout?.on("data", (chunk) => {
            stdout += chunk.toString("utf-8");
        });
        child.stderr?.on("data", (chunk) => {
            stderr += chunk.toString("utf-8");
        });
        child.on("close", (code) => {
            clearTimeout(timer);
            finish({ exitCode: code, timedOut: false });
        });
        child.on("error", (error) => {
            clearTimeout(timer);
            stderr += error.message;
            finish({ exitCode: null, timedOut: false });
        });
    });
}
