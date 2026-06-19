import { existsSync, realpathSync, statSync } from "fs";
import { extname } from "path";
import { spawn } from "child_process";

interface HostOpenDocumentArgs {
    path?: string;
    app_name?: string;
    timeout_ms?: number;
}

const DEFAULT_TIMEOUT_MS = 30_000;
const MAX_TIMEOUT_MS = 120_000;
const SUPPORTED_EXTENSIONS = new Map<string, Set<string>>([
    [".blend", new Set(["Blender"])],
]);

function cleanString(value: unknown): string {
    return typeof value === "string" ? value.trim() : "";
}

function validateOpenRequest(rawArgs: Record<string, unknown>): {
    path: string;
    appName: string;
    timeoutMs: number;
} {
    const args = rawArgs as HostOpenDocumentArgs;
    const rawPath = cleanString(args.path);
    if (!rawPath || !rawPath.startsWith("/")) {
        throw new Error("absolute_document_path_required");
    }
    if (!existsSync(rawPath)) {
        throw new Error(`document_missing:${rawPath}`);
    }
    if (!statSync(rawPath).isFile()) {
        throw new Error(`document_not_file:${rawPath}`);
    }

    const resolvedPath = realpathSync(rawPath);
    const extension = extname(resolvedPath).toLowerCase();
    const supportedApps = SUPPORTED_EXTENSIONS.get(extension);
    if (!supportedApps) {
        throw new Error(`unsupported_document_extension:${extension || "none"}`);
    }

    const appName = cleanString(args.app_name) || "Blender";
    if (!supportedApps.has(appName)) {
        throw new Error(`unsupported_document_app:${appName}`);
    }

    const requestedTimeout =
        typeof args.timeout_ms === "number" && Number.isFinite(args.timeout_ms)
            ? Math.trunc(args.timeout_ms)
            : DEFAULT_TIMEOUT_MS;
    return {
        path: resolvedPath,
        appName,
        timeoutMs: Math.min(Math.max(requestedTimeout, 1000), MAX_TIMEOUT_MS),
    };
}

export async function hostOpenDocument(
    rawArgs: Record<string, unknown>
): Promise<Record<string, unknown>> {
    if (process.platform !== "darwin") {
        throw new Error("host_open_document_unsupported_platform");
    }
    const request = validateOpenRequest(rawArgs);

    return new Promise((resolve, reject) => {
        const child = spawn(
            "open",
            ["-a", request.appName, request.path],
            {
                shell: false,
                timeout: request.timeoutMs,
            }
        );
        let stdout = "";
        let stderr = "";
        child.stdout.on("data", (data) => {
            stdout += data.toString();
        });
        child.stderr.on("data", (data) => {
            stderr += data.toString();
        });
        child.on("close", (code, signal) => {
            if (code === 0) {
                resolve({
                    launched: true,
                    launcher_mode: "device_node_host_open_document",
                    app_name: request.appName,
                    document_path: request.path,
                    stdout,
                    stderr,
                });
                return;
            }
            if (signal) {
                reject(new Error(`host_open_document_signal:${signal}:${stderr || stdout}`));
                return;
            }
            reject(new Error(`host_open_document_exit_${code}:${stderr || stdout}`));
        });
        child.on("error", (error) => {
            reject(new Error(`host_open_document_spawn_failed:${error.message}`));
        });
    });
}
