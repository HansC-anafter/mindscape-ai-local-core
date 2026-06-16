import { existsSync, mkdirSync, readFileSync } from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

import { cleanString } from "./host-resource-lane-worker-inputs.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function projectRootCandidates(): string[] {
    const configured = cleanString(process.env.LOCAL_CORE_PROJECT_ROOT);
    const candidates = [
        configured,
        path.resolve(__dirname, "../../.."),
        process.cwd(),
        path.resolve(process.cwd(), ".."),
    ];
    return candidates.filter((candidate, index) => candidate && candidates.indexOf(candidate) === index);
}

export function mlxLauncherPath(): { root: string; script: string } | null {
    for (const root of projectRootCandidates()) {
        const script = path.join(root, "scripts/mlx-server/start-mlx-server.sh");
        if (existsSync(script)) {
            return { root, script };
        }
    }
    return null;
}

export function safeLaneSlug(laneId: string): string {
    return laneId.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^_+|_+$/g, "") || "lane";
}

export function laneRuntimePaths(root: string, laneId: string): { logDir: string; watchdogStateFile: string } {
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

export function readDotenvValue(root: string, key: string): string {
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

export function dataHostRoot(root: string): string {
    return (
        cleanString(process.env.LOCAL_CORE_DATA_HOST_DIR)
        || readDotenvValue(root, "LOCAL_CORE_DATA_HOST_DIR")
        || path.join(root, "data")
    );
}

export function hostPathForContainerDataPath(root: string, containerPath: string): string {
    const normalized = cleanString(containerPath);
    if (!normalized.startsWith("/app/data/")) {
        return normalized;
    }
    return path.join(dataHostRoot(root), normalized.slice("/app/data/".length));
}

export function watchdogStateFileForWorker(
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
