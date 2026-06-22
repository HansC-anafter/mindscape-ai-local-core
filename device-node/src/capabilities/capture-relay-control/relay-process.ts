import { spawn } from "child_process";
import * as net from "net";

import {
    COMMON_BREW_PATHS,
    COMMON_OBS_APP_PATHS,
    DEFAULT_OBS_APP_PATH,
    DEFAULT_OBS_WEBSOCKET_PORT,
    DEFAULT_RTMP_PORT,
    DEFAULT_RTSP_PORT,
} from "./constants.js";
import {
    buildInstallGuidance,
    buildRelayUrls,
    normalizePort,
    normalizeStreamName,
    resolveHostCommand,
    resolveObsAppPath,
    resolveRelayBinary,
} from "./host-discovery.js";
import { runHostCommand } from "./host-actions.js";
import { inferPublisherState } from "./publisher-state.js";
import type { CaptureRelayAction, CaptureRelayArgs, ManagedRelayProcess } from "./types.js";

let managedRelay: ManagedRelayProcess | null = null;

function isManagedRelayRunning(): boolean {
    return Boolean(managedRelay && managedRelay.child.exitCode === null && !managedRelay.child.killed);
}

function activeManagedRelay(): ManagedRelayProcess | null {
    if (!isManagedRelayRunning()) {
        managedRelay = null;
        return null;
    }
    return managedRelay;
}

export async function isTcpPortOpen(host: string, port: number, timeoutMs = 500): Promise<boolean> {
    return new Promise((resolve) => {
        const socket = net.createConnection({ host, port });
        let resolved = false;
        const finish = (value: boolean) => {
            if (resolved) {
                return;
            }
            resolved = true;
            socket.destroy();
            resolve(value);
        };
        socket.setTimeout(timeoutMs);
        socket.once("connect", () => finish(true));
        socket.once("timeout", () => finish(false));
        socket.once("error", () => finish(false));
    });
}

async function waitForTcpPort(host: string, port: number, timeoutMs: number): Promise<boolean> {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
        if (await isTcpPortOpen(host, port, 250)) {
            return true;
        }
        await new Promise((resolve) => setTimeout(resolve, 250));
    }
    return false;
}

export function sleepMs(durationMs: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, durationMs));
}

function appendOutputLine(relay: ManagedRelayProcess, chunk: Buffer): void {
    const lines = chunk.toString("utf-8").split(/\r?\n/).filter(Boolean);
    relay.outputLines.push(...lines.slice(-20));
    relay.outputLines = relay.outputLines.slice(-20);
}

export async function installMediaMtx(args: CaptureRelayArgs): Promise<Record<string, unknown>> {
    const existingBinary = resolveRelayBinary();
    if (existingBinary) {
        return buildStatus("install_mediamtx", args, {
            install_result: "already_installed",
            install_method: "existing_binary",
        });
    }

    const method = String(args.install_method || "homebrew").trim() || "homebrew";
    if (method !== "homebrew") {
        return buildStatus("install_mediamtx", args, {
            install_result: "blocked",
            reason: "unsupported_install_method",
            install_method: method,
        });
    }

    const brewPath = resolveHostCommand("brew", COMMON_BREW_PATHS);
    if (!brewPath) {
        return buildStatus("install_mediamtx", args, {
            install_result: "blocked",
            reason: "homebrew_missing",
            install_method: method,
        });
    }

    const timeoutMs = Math.min(Math.max(Number(args.timeout_ms || 120000), 1000), 120000);
    const install = await runHostCommand(brewPath, ["install", "mediamtx"], timeoutMs);
    const installedBinary = resolveRelayBinary();
    return buildStatus("install_mediamtx", args, {
        install_result: installedBinary
            ? "installed"
            : install.timedOut
                ? "timeout"
                : "failed",
        install_method: method,
        install_command: `${brewPath} install mediamtx`,
        install_exit_code: install.exitCode,
        install_timed_out: install.timedOut,
        install_stdout: install.stdout,
        install_stderr: install.stderr,
    });
}

export async function buildStatus(
    action: CaptureRelayAction,
    args: CaptureRelayArgs,
    extra: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
    const streamName = normalizeStreamName(args.stream_name);
    const rtmpPort = normalizePort(args.rtmp_port, DEFAULT_RTMP_PORT);
    const rtspPort = normalizePort(args.rtsp_port, DEFAULT_RTSP_PORT);
    const obsWebsocketHost = String(args.obs_websocket_host || "127.0.0.1");
    const obsWebsocketPort = normalizePort(
        args.obs_websocket_port,
        DEFAULT_OBS_WEBSOCKET_PORT,
    );
    const binaryPath = resolveRelayBinary();
    const activeRelay = activeManagedRelay();
    const rtmpOpen = await isTcpPortOpen("127.0.0.1", rtmpPort);
    const obsWebsocketReachable = await isTcpPortOpen(obsWebsocketHost, obsWebsocketPort);
    const obsAppPath = resolveObsAppPath();
    const urls = buildRelayUrls(streamName, rtmpPort, rtspPort);
    const relayRunning = Boolean(activeRelay || rtmpOpen);
    const blocked = !relayRunning && !binaryPath;
    const status = relayRunning ? "running" : blocked ? "blocked" : "ready_to_start";
    const reason = extra.reason || (blocked ? "relay_binary_missing" : undefined);
    const recentOutput = activeRelay?.outputLines.slice(-5) || [];

    return {
        schema_version: "capture_relay_control.v1",
        action,
        status,
        reason,
        relay: {
            engine: "mediamtx",
            mode: activeRelay ? "managed" : rtmpOpen ? "external" : "not_running",
            managed: Boolean(activeRelay),
            running: relayRunning,
            pid: activeRelay?.child.pid || null,
            started_at: activeRelay?.startedAt || null,
            binary_path: binaryPath,
            rtmp_port: rtmpPort,
            rtsp_port: rtspPort,
            rtmp_listener_open: rtmpOpen,
            recent_output: recentOutput,
        },
        stream: inferPublisherState({
            streamName,
            relayRunning,
            recentOutput,
        }),
        obs: {
            app_path: obsAppPath || DEFAULT_OBS_APP_PATH,
            app_present: Boolean(obsAppPath),
            expected_app_paths: COMMON_OBS_APP_PATHS,
            websocket_host: obsWebsocketHost,
            websocket_port: obsWebsocketPort,
            websocket_reachable: obsWebsocketReachable,
        },
        urls,
        install_guidance: buildInstallGuidance(binaryPath),
        next_steps: [
            "Start the RTMP relay.",
            "Set the external camera app RTMP destination to the publish_url.",
            "Add an OBS Media Source that reads the read_url.",
            "Start OBS Virtual Camera and select it from the browser device-link camera source.",
        ],
        ...extra,
    };
}

export async function startRelay(args: CaptureRelayArgs): Promise<Record<string, unknown>> {
    const streamName = normalizeStreamName(args.stream_name);
    const rtmpPort = normalizePort(args.rtmp_port, DEFAULT_RTMP_PORT);
    const rtspPort = normalizePort(args.rtsp_port, DEFAULT_RTSP_PORT);
    const activeRelay = activeManagedRelay();
    if (activeRelay) {
        return buildStatus("start", args, { start_result: "already_managed" });
    }
    if (await isTcpPortOpen("127.0.0.1", rtmpPort)) {
        return buildStatus("start", args, { start_result: "external_listener_detected" });
    }

    const binaryPath = resolveRelayBinary();
    if (!binaryPath) {
        return buildStatus("start", args, { start_result: "blocked" });
    }

    const relay: ManagedRelayProcess = {
        child: spawn(binaryPath, [], {
            shell: false,
            stdio: ["ignore", "pipe", "pipe"],
        }),
        binaryPath,
        streamName,
        startedAt: new Date().toISOString(),
        rtmpPort,
        rtspPort,
        outputLines: [],
    };
    managedRelay = relay;
    relay.child.stdout?.on("data", (chunk) => appendOutputLine(relay, chunk));
    relay.child.stderr?.on("data", (chunk) => appendOutputLine(relay, chunk));
    relay.child.on("close", () => {
        if (managedRelay?.child === relay.child) {
            managedRelay = null;
        }
    });

    const timeoutMs = Math.min(Math.max(Number(args.timeout_ms || 5000), 1000), 15000);
    const ready = await waitForTcpPort("127.0.0.1", rtmpPort, timeoutMs);
    if (!ready) {
        return buildStatus("start", args, { start_result: "relay_start_timeout" });
    }
    return buildStatus("start", args, { start_result: "started", stream_name: streamName });
}

export async function stopRelay(args: CaptureRelayArgs): Promise<Record<string, unknown>> {
    const activeRelay = activeManagedRelay();
    if (!activeRelay) {
        return buildStatus("stop", args, { stop_result: "no_managed_relay" });
    }
    activeRelay.child.kill("SIGTERM");
    await new Promise((resolve) => setTimeout(resolve, 500));
    if (activeRelay.child.exitCode === null && !activeRelay.child.killed) {
        activeRelay.child.kill("SIGKILL");
    }
    managedRelay = null;
    return buildStatus("stop", args, { stop_result: "stopped" });
}
