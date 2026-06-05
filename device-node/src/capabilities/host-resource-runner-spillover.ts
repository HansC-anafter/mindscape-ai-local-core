import { spawn } from "child_process";
import { existsSync } from "fs";
import * as path from "path";

type SpilloverAction = "status" | "start" | "stop";
type SpilloverProfile = "default_local" | "browser_local" | "vision_local";

interface SpilloverArgs {
    action?: unknown;
    profile_code?: unknown;
    max_inflight?: unknown;
}

interface ProfileDefaults {
    partitions: string;
    resourceClasses: string;
    defaultMaxInflight: number;
}

const SERVICE_NAME = "runner-spillover";
const DOCKER_COMMAND_CANDIDATES = [
    "/usr/local/bin/docker",
    "/opt/homebrew/bin/docker",
    "/Applications/Docker.app/Contents/Resources/bin/docker",
    "docker",
];
const ALLOWED_ACTIONS = new Set<SpilloverAction>(["status", "start", "stop"]);
const PROFILE_DEFAULTS: Record<SpilloverProfile, ProfileDefaults> = {
    default_local: {
        partitions: "default_local",
        resourceClasses: "compute,api",
        defaultMaxInflight: 1,
    },
    browser_local: {
        partitions: "browser_local",
        resourceClasses: "browser",
        defaultMaxInflight: 1,
    },
    vision_local: {
        partitions: "vision_local",
        resourceClasses: "compute",
        defaultMaxInflight: 1,
    },
};

function cleanString(value: unknown): string {
    return String(value || "").trim();
}

function cleanAction(value: unknown): SpilloverAction {
    const action = cleanString(value || "status") as SpilloverAction;
    if (!ALLOWED_ACTIONS.has(action)) {
        throw new Error(`Unsupported spillover action: ${action}`);
    }
    return action;
}

function cleanProfile(value: unknown): SpilloverProfile {
    const profile = cleanString(value || "default_local") as SpilloverProfile;
    if (!Object.prototype.hasOwnProperty.call(PROFILE_DEFAULTS, profile)) {
        throw new Error(`Unsupported spillover profile: ${profile}`);
    }
    return profile;
}

function cleanMaxInflight(value: unknown, fallback: number): number {
    const parsed = Number.parseInt(String(value ?? fallback), 10);
    if (!Number.isFinite(parsed)) {
        return fallback;
    }
    return Math.min(Math.max(parsed, 1), 4);
}

function projectRoot(): string {
    return process.env.LOCAL_CORE_PROJECT_ROOT || path.resolve(process.cwd(), "..");
}

function commandArgs(action: SpilloverAction): string[] {
    if (action === "start") {
        return [
            "compose",
            "--profile",
            "spillover",
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            SERVICE_NAME,
        ];
    }
    if (action === "stop") {
        return ["compose", "--profile", "spillover", "stop", SERVICE_NAME];
    }
    return ["compose", "--profile", "spillover", "ps", SERVICE_NAME, "--format", "json"];
}

function dockerCommand(): string {
    const configured = cleanString(process.env.DOCKER_CLI_PATH);
    const candidates = configured
        ? [configured, ...DOCKER_COMMAND_CANDIDATES]
        : DOCKER_COMMAND_CANDIDATES;
    for (const candidate of candidates) {
        if (candidate === "docker" || existsSync(candidate)) {
            return candidate;
        }
    }
    return "docker";
}

function runDockerCompose(
    dockerBin: string,
    args: string[],
    cwd: string,
    env: NodeJS.ProcessEnv
): Promise<{ exitCode: number | null; stdout: string; stderr: string }> {
    return new Promise((resolve, reject) => {
        const child = spawn(dockerBin, args, {
            cwd,
            env,
            shell: false,
            timeout: 120_000,
        });
        let stdout = "";
        let stderr = "";
        child.stdout.on("data", (data) => {
            stdout += data.toString();
        });
        child.stderr.on("data", (data) => {
            stderr += data.toString();
        });
        child.on("close", (code) => {
            resolve({ exitCode: code, stdout, stderr });
        });
        child.on("error", (error) => {
            reject(error);
        });
    });
}

function statusFromOutput(stdout: string): Record<string, unknown> {
    const trimmed = stdout.trim();
    if (!trimmed) {
        return { running: false, rows: [] };
    }
    try {
        const parsed = JSON.parse(trimmed);
        const rows = Array.isArray(parsed) ? parsed : [parsed];
        return {
            running: rows.some((row) => {
                if (!row || typeof row !== "object") return false;
                const state = String((row as Record<string, unknown>).State || "").toLowerCase();
                return state.includes("running");
            }),
            rows,
        };
    } catch {
        return {
            running: trimmed.includes(SERVICE_NAME) && trimmed.toLowerCase().includes("running"),
            raw: trimmed,
        };
    }
}

export async function hostResourceRunnerSpilloverControl(
    args: Record<string, unknown>
): Promise<Record<string, unknown>> {
    const payload = args as SpilloverArgs;
    const action = cleanAction(payload.action);
    const profileCode = cleanProfile(payload.profile_code);
    const defaults = PROFILE_DEFAULTS[profileCode];
    const maxInflight = cleanMaxInflight(payload.max_inflight, defaults.defaultMaxInflight);
    const cwd = projectRoot();
    const env = {
        ...process.env,
        LOCAL_CORE_RUNNER_SPILLOVER_PROFILE: profileCode,
        LOCAL_CORE_RUNNER_SPILLOVER_ACCEPTED_PARTITIONS: defaults.partitions,
        LOCAL_CORE_RUNNER_SPILLOVER_ACCEPTED_RESOURCE_CLASSES: defaults.resourceClasses,
        LOCAL_CORE_RUNNER_SPILLOVER_MAX_INFLIGHT: String(maxInflight),
        LOCAL_CORE_RUNNER_SPILLOVER_RUNTIME_ID: `spillover:${profileCode}`,
        LOCAL_CORE_RUNNER_SPILLOVER_DB_APPLICATION_NAME: `local-core-runner-spillover-${profileCode}`,
        LOCAL_CORE_RUNNER_SPILLOVER_DISPLAY_NAME: `Spillover ${profileCode}`,
    };
    const dockerArgs = commandArgs(action);
    const dockerBin = dockerCommand();
    const result = await runDockerCompose(dockerBin, dockerArgs, cwd, env);
    const accepted = result.exitCode === 0;
    return {
        accepted,
        action,
        service: SERVICE_NAME,
        profile_code: profileCode,
        max_inflight: maxInflight,
        command: [dockerBin, ...dockerArgs],
        cwd,
        exit_code: result.exitCode,
        stdout: result.stdout.trim(),
        stderr: result.stderr.trim(),
        status: action === "status" ? statusFromOutput(result.stdout) : undefined,
    };
}
