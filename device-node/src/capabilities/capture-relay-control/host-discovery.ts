import * as fs from "fs";
import * as os from "os";
import * as path from "path";

import {
    COMMON_BREW_PATHS,
    COMMON_MEDIAMTX_PATHS,
    COMMON_OBS_APP_PATHS,
    DEFAULT_RTMP_PORT,
    DEFAULT_RTSP_PORT,
    DEFAULT_STREAM_NAME,
    MEDIAMTX_RELEASES_URL,
} from "./constants.js";
import type { ObsAppLookupInput, RelayBinaryLookupInput, RelayUrls } from "./types.js";

function isExecutable(filePath: string): boolean {
    try {
        fs.accessSync(filePath, fs.constants.X_OK);
        return true;
    } catch {
        return false;
    }
}

function isDirectory(filePath: string): boolean {
    try {
        return fs.statSync(filePath).isDirectory();
    } catch {
        return false;
    }
}

export function resolveRelayBinary(input: RelayBinaryLookupInput = {}): string | null {
    const env = input.env || process.env;
    const configuredPath = String(env.CAPTURE_RELAY_MEDIAMTX_BIN || "").trim();
    if (configuredPath && isExecutable(configuredPath)) {
        return configuredPath;
    }

    const pathValue = input.pathValue ?? env.PATH ?? "";
    const candidates = [
        ...pathValue
            .split(path.delimiter)
            .filter(Boolean)
            .map((directory) => path.join(directory, "mediamtx")),
        ...(input.commonPaths ?? COMMON_MEDIAMTX_PATHS),
    ];
    for (const candidate of candidates) {
        if (isExecutable(candidate)) {
            return candidate;
        }
    }
    return null;
}

export function resolveObsAppPath(input: ObsAppLookupInput = {}): string | null {
    const env = input.env || process.env;
    const configuredPath = String(env.CAPTURE_RELAY_OBS_APP_PATH || "").trim();
    if (configuredPath) {
        return isDirectory(configuredPath) ? configuredPath : null;
    }

    for (const candidate of input.commonPaths ?? COMMON_OBS_APP_PATHS) {
        if (isDirectory(candidate)) {
            return candidate;
        }
    }
    return null;
}

export function resolveHostCommand(commandName: string, commonPaths: string[]): string | null {
    const candidates = [
        ...(process.env.PATH || "")
            .split(path.delimiter)
            .filter(Boolean)
            .map((directory) => path.join(directory, commandName)),
        ...commonPaths,
    ];
    for (const candidate of candidates) {
        if (isExecutable(candidate)) {
            return candidate;
        }
    }
    return null;
}

function mediamtxAssetPattern(): string {
    const platform = process.platform === "darwin" ? "darwin" : process.platform;
    const arch = process.arch === "x64" ? "amd64" : process.arch;
    return `mediamtx_*_${platform}_${arch}.tar.gz`;
}

export function buildInstallGuidance(binaryPath: string | null): Record<string, unknown> {
    const brewPath = resolveHostCommand("brew", COMMON_BREW_PATHS);
    return {
        dependency: "mediamtx",
        status: binaryPath ? "installed" : "missing",
        binary_path: binaryPath,
        official_release_url: MEDIAMTX_RELEASES_URL,
        detected_platform: process.platform,
        detected_arch: process.arch,
        recommended_asset_pattern: mediamtxAssetPattern(),
        host_tools: {
            brew_available: Boolean(brewPath),
            brew_path: brewPath,
        },
        options: [
            {
                id: "homebrew",
                label: "Homebrew",
                available: Boolean(brewPath),
                command: "brew install mediamtx",
                after_install: "Click Check relay again after Homebrew links mediamtx into PATH.",
            },
            {
                id: "official_release",
                label: "Official release archive",
                available: true,
                release_url: MEDIAMTX_RELEASES_URL,
                asset_pattern: mediamtxAssetPattern(),
                install_target: "/opt/homebrew/bin/mediamtx or /usr/local/bin/mediamtx",
                after_install: "Restart Device Node if the binary was added outside the current launchd PATH, then click Check relay.",
            },
        ],
    };
}

export function normalizeStreamName(value: unknown): string {
    const normalized = String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, "-")
        .replace(/^-+|-+$/g, "");
    return normalized || DEFAULT_STREAM_NAME;
}

export function normalizePort(value: unknown, fallback: number): number {
    const candidate = Number(value);
    if (!Number.isInteger(candidate) || candidate < 1 || candidate > 65535) {
        return fallback;
    }
    return candidate;
}

function chooseLanHost(): string {
    const interfaces = os.networkInterfaces();
    const candidates: string[] = [];
    for (const entries of Object.values(interfaces)) {
        for (const entry of entries || []) {
            if (entry.family !== "IPv4" || entry.internal) {
                continue;
            }
            candidates.push(entry.address);
        }
    }
    const privateCandidate = candidates.find((address) => (
        address.startsWith("192.168.")
        || address.startsWith("10.")
        || /^172\.(1[6-9]|2\d|3[0-1])\./.test(address)
    ));
    return privateCandidate || candidates[0] || "127.0.0.1";
}

export function buildRelayUrls(
    streamName: string,
    rtmpPort = DEFAULT_RTMP_PORT,
    rtspPort = DEFAULT_RTSP_PORT,
    lanHost = chooseLanHost(),
): RelayUrls {
    const portSegment = rtmpPort === DEFAULT_RTMP_PORT ? "" : `:${rtmpPort}`;
    return {
        stream_name: streamName,
        publish_url: `rtmp://${lanHost}${portSegment}/${streamName}`,
        read_url: `rtsp://127.0.0.1:${rtspPort}/${streamName}`,
    };
}
