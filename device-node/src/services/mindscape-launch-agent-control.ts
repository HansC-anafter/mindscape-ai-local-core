import { spawn } from "child_process";
import * as fs from "fs";

export type LaunchAgentAction = "status" | "start" | "restart";

export interface LaunchAgentDescriptor {
    service: string;
    label: string;
    plistPath: string;
    unsupportedMessage: string;
    runningMessage: string;
    stoppedMessage: string;
    missingMessage: string;
}

export interface CommandResult {
    code: number | null;
    stdout: string;
    stderr: string;
    timed_out?: boolean;
}

export type CommandRunner = (args: string[], timeoutMs?: number) => Promise<CommandResult>;
type FileExists = (filePath: string) => boolean;
type ReadTextFile = (filePath: string) => string;

export interface LaunchAgentControlOptions {
    commandTimeoutMs?: number;
    domain?: string | null;
    fileExists?: FileExists;
    platform?: NodeJS.Platform;
    readFile?: ReadTextFile;
    runCommand?: CommandRunner;
}

const COMMAND_TIMEOUT_MS = 10_000;

export function launchdDomain(): string | null {
    if (typeof process.getuid !== "function") {
        return null;
    }
    return `gui/${process.getuid()}`;
}

function resolveLaunchdDomain(options: LaunchAgentControlOptions): string | null {
    if ("domain" in options) {
        return options.domain ?? null;
    }
    return launchdDomain();
}

export function defaultRunLaunchctl(
    args: string[],
    timeoutMs = COMMAND_TIMEOUT_MS,
): Promise<CommandResult> {
    return new Promise((resolve) => {
        const child = spawn("launchctl", args, {
            shell: false,
            timeout: timeoutMs,
        });
        let stdout = "";
        let stderr = "";

        child.stdout.on("data", (data) => {
            stdout += data.toString();
        });
        child.stderr.on("data", (data) => {
            stderr += data.toString();
        });
        child.on("close", (code, signal) => {
            resolve({
                code,
                stdout,
                stderr,
                timed_out: signal === "SIGTERM",
            });
        });
        child.on("error", (error) => {
            resolve({
                code: 127,
                stdout,
                stderr: error.message,
            });
        });
    });
}

export function parseLaunchdState(stdout: string): string | null {
    const match = stdout.match(/state\s*=\s*([^\n]+)/);
    return match ? match[1].trim() : null;
}

export function plistContentHasKeepAlive(content: string): boolean {
    return /<key>\s*KeepAlive\s*<\/key>\s*<true\s*\/>/.test(content);
}

export function plistHasKeepAlive(
    plistPath: string,
    readFile: ReadTextFile = (filePath) => fs.readFileSync(filePath, "utf-8"),
): boolean {
    try {
        return plistContentHasKeepAlive(readFile(plistPath));
    } catch {
        return false;
    }
}

function commandRunner(options: LaunchAgentControlOptions): CommandRunner {
    return options.runCommand ?? defaultRunLaunchctl;
}

function fileExists(options: LaunchAgentControlOptions): FileExists {
    return options.fileExists ?? fs.existsSync;
}

function readFile(options: LaunchAgentControlOptions): ReadTextFile {
    return options.readFile ?? ((filePath) => fs.readFileSync(filePath, "utf-8"));
}

function commandTimeout(options: LaunchAgentControlOptions): number {
    return options.commandTimeoutMs ?? COMMAND_TIMEOUT_MS;
}

export async function readLaunchAgentStatus(
    descriptor: LaunchAgentDescriptor,
    extra: Record<string, unknown> = {},
    options: LaunchAgentControlOptions = {},
): Promise<Record<string, unknown>> {
    const domain = resolveLaunchdDomain(options);
    const platform = options.platform ?? process.platform;
    const installed = fileExists(options)(descriptor.plistPath);
    const supported = platform === "darwin" && Boolean(domain);

    if (!supported) {
        return {
            service: descriptor.service,
            label: descriptor.label,
            platform,
            supported: false,
            installed,
            loaded: false,
            running: false,
            state: "unsupported",
            auto_recovery: false,
            plist_path: descriptor.plistPath,
            message: descriptor.unsupportedMessage,
            ...extra,
        };
    }

    const run = commandRunner(options);
    const timeoutMs = commandTimeout(options);
    const print = await run(["print", `${domain}/${descriptor.label}`], 5_000);
    let loaded = print.code === 0;
    let launchdState = loaded ? parseLaunchdState(print.stdout) : null;
    if (!loaded) {
        const listed = await run(["list", descriptor.label], 5_000);
        loaded = listed.code === 0;
        launchdState = loaded ? "loaded" : null;
    }
    const running = launchdState === "running" || (loaded && launchdState === "loaded");
    const state = running
        ? "ready"
        : loaded && launchdState !== "not running"
            ? "recovering"
            : installed
                ? "stopped"
                : "not_installed";

    return {
        service: descriptor.service,
        label: descriptor.label,
        platform,
        supported: true,
        installed,
        loaded,
        running,
        launchd_state: launchdState,
        state,
        auto_recovery: installed && plistHasKeepAlive(descriptor.plistPath, readFile(options)),
        plist_path: descriptor.plistPath,
        message: running
            ? descriptor.runningMessage
            : installed
                ? descriptor.stoppedMessage
                : descriptor.missingMessage,
        command_timeout_ms: timeoutMs,
        ...extra,
    };
}

export async function startOrRestartLaunchAgent(
    descriptor: LaunchAgentDescriptor,
    action: Exclude<LaunchAgentAction, "status">,
    options: LaunchAgentControlOptions = {},
): Promise<Record<string, unknown>> {
    const domain = resolveLaunchdDomain(options);
    const platform = options.platform ?? process.platform;
    if (platform !== "darwin" || !domain) {
        return readLaunchAgentStatus(descriptor, { action, accepted: false, reason: "unsupported_platform" }, options);
    }
    if (!fileExists(options)(descriptor.plistPath)) {
        return readLaunchAgentStatus(descriptor, { action, accepted: false, reason: "plist_not_installed" }, options);
    }

    const before = await readLaunchAgentStatus(descriptor, {}, options);
    const loaded = Boolean(before.loaded);
    const run = commandRunner(options);
    const commands: Array<{ name: string; result: CommandResult }> = [];

    if (!loaded) {
        const bootstrap = await run(["bootstrap", domain, descriptor.plistPath], commandTimeout(options));
        commands.push({ name: "bootstrap", result: bootstrap });
        if (bootstrap.code !== 0 && !`${bootstrap.stderr}${bootstrap.stdout}`.includes("Service is already loaded")) {
            commands.push({ name: "load", result: await run(["load", descriptor.plistPath], commandTimeout(options)) });
        }
    }

    commands.push({
        name: "kickstart",
        result: await run(["kickstart", "-k", `${domain}/${descriptor.label}`], commandTimeout(options)),
    });

    return readLaunchAgentStatus(
        descriptor,
        {
            action,
            accepted: true,
            control_results: commands.map(({ name, result }) => ({
                name,
                code: result.code,
                stderr: result.stderr.trim() || null,
                timed_out: Boolean(result.timed_out),
            })),
        },
        options,
    );
}

export async function controlLaunchAgentService(
    descriptor: LaunchAgentDescriptor,
    action: LaunchAgentAction,
    options: LaunchAgentControlOptions = {},
): Promise<Record<string, unknown>> {
    if (action === "status") {
        return readLaunchAgentStatus(descriptor, { action }, options);
    }
    return startOrRestartLaunchAgent(descriptor, action, options);
}
