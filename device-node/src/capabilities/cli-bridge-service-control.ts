/**
 * Fixed launchd control for the Mindscape CLI bridge supervisor.
 *
 * This intentionally exposes only the known ai.mindscape.cli-bridge service.
 * It is not a generic shell surface.
 */

import { spawn } from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

type BridgeServiceAction = "status" | "start" | "restart";

interface CommandResult {
    code: number | null;
    stdout: string;
    stderr: string;
    timed_out?: boolean;
}

const LABEL = "ai.mindscape.cli-bridge";
const PLIST_PATH = path.join(os.homedir(), "Library", "LaunchAgents", `${LABEL}.plist`);
const COMMAND_TIMEOUT_MS = 10_000;

function requestedAction(raw: unknown): BridgeServiceAction {
    const value = typeof raw === "string" ? raw.trim().toLowerCase() : "status";
    if (value === "start" || value === "restart") {
        return value;
    }
    return "status";
}

function launchdDomain(): string | null {
    if (typeof process.getuid !== "function") {
        return null;
    }
    return `gui/${process.getuid()}`;
}

function runLaunchctl(args: string[], timeoutMs = COMMAND_TIMEOUT_MS): Promise<CommandResult> {
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

function parseLaunchdState(stdout: string): string | null {
    const match = stdout.match(/state\s*=\s*([^\n]+)/);
    return match ? match[1].trim() : null;
}

function plistHasKeepAlive(): boolean {
    try {
        const content = fs.readFileSync(PLIST_PATH, "utf-8");
        return content.includes("<key>KeepAlive</key>") && content.includes("<true/>");
    } catch {
        return false;
    }
}

async function readStatus(extra: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    const domain = launchdDomain();
    const installed = fs.existsSync(PLIST_PATH);
    const supported = process.platform === "darwin" && Boolean(domain);
    if (!supported) {
        return {
            service: "cli_bridge",
            label: LABEL,
            platform: process.platform,
            supported: false,
            installed,
            loaded: false,
            running: false,
            state: "unsupported",
            auto_recovery: false,
            plist_path: PLIST_PATH,
            message: "LaunchAgent control is only available from the macOS host Device Node.",
            ...extra,
        };
    }

    const print = await runLaunchctl(["print", `${domain}/${LABEL}`], 5_000);
    let loaded = print.code === 0;
    let launchdState = loaded ? parseLaunchdState(print.stdout) : null;
    if (!loaded) {
        const listed = await runLaunchctl(["list", LABEL], 5_000);
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
        service: "cli_bridge",
        label: LABEL,
        platform: process.platform,
        supported: true,
        installed,
        loaded,
        running,
        launchd_state: launchdState,
        state,
        auto_recovery: installed && plistHasKeepAlive(),
        plist_path: PLIST_PATH,
        message: running
            ? "CLI bridge LaunchAgent is running."
            : installed
                ? "CLI bridge LaunchAgent is installed but not running."
                : "CLI bridge LaunchAgent plist is not installed.",
        ...extra,
    };
}

async function startOrRestart(action: Exclude<BridgeServiceAction, "status">): Promise<Record<string, unknown>> {
    const domain = launchdDomain();
    if (process.platform !== "darwin" || !domain) {
        return readStatus({ action, accepted: false, reason: "unsupported_platform" });
    }
    if (!fs.existsSync(PLIST_PATH)) {
        return readStatus({ action, accepted: false, reason: "plist_not_installed" });
    }

    const before = await readStatus();
    const loaded = Boolean(before.loaded);
    const commands: Array<{ name: string; result: CommandResult }> = [];

    if (!loaded) {
        const bootstrap = await runLaunchctl(["bootstrap", domain, PLIST_PATH]);
        commands.push({ name: "bootstrap", result: bootstrap });
        if (bootstrap.code !== 0 && !`${bootstrap.stderr}${bootstrap.stdout}`.includes("Service is already loaded")) {
            commands.push({ name: "load", result: await runLaunchctl(["load", PLIST_PATH]) });
        }
    }

    commands.push({
        name: "kickstart",
        result: await runLaunchctl(["kickstart", "-k", `${domain}/${LABEL}`]),
    });

    return readStatus({
        action,
        accepted: true,
        control_results: commands.map(({ name, result }) => ({
            name,
            code: result.code,
            stderr: result.stderr.trim() || null,
            timed_out: Boolean(result.timed_out),
        })),
    });
}

export async function cliBridgeServiceControl(rawArgs: Record<string, unknown>): Promise<Record<string, unknown>> {
    const action = requestedAction(rawArgs.action);
    if (action === "status") {
        return readStatus({ action });
    }
    return startOrRestart(action);
}
