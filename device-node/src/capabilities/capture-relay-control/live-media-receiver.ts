import { spawn, spawnSync } from "child_process";
import {
    chmodSync,
    closeSync,
    existsSync,
    mkdirSync,
    openSync,
    readFileSync,
    realpathSync,
    readdirSync,
    renameSync,
    statSync,
    writeFileSync,
} from "fs";
import * as path from "path";

import {
    dataHostRoot,
    hostPathForContainerDataPath,
    projectRootCandidates,
    readDotenvValue,
} from "../host-resource-lane-worker-paths.js";

type ReceiverStateName =
    | "starting"
    | "waiting_source"
    | "receiving"
    | "analyzing"
    | "degraded"
    | "stopping"
    | "completed"
    | "failed"
    | "expired";

interface ReceiverDescriptor {
    schema_version: "live_media_receiver.v1";
    workspace_id: string;
    device_session_id: string;
    media_session_id: string;
    live_motion_session_id: string;
    meeting_session_id: string;
    practice_session_id: string;
    receiver_identity: string;
    append_owner_id: string;
    source_kind: string;
    transport_kind: "rtsps";
    input_url: string;
    access_token: string;
    expires_at_epoch: number;
    api_base: string;
    coach_pack: "yogacoach" | "dance_motion_coach";
    practice_mode: string;
    reference_url?: string | null;
    motion_reference_profile?: {
        artifact_id: string;
        storage_ref: string;
        reference_profile_id: string;
    } | null;
    user_goal?: string | null;
    expected_duration_ms: number;
}

interface ReceiverState {
    schema_version: "live_media_receiver_state.v1";
    workspace_id: string;
    media_session_id: string;
    receiver_identity: string;
    pid: number;
    state: ReceiverStateName;
    updated_at: string;
    reason?: string;
}

function cleanString(value: unknown): string {
    return String(value || "").trim();
}

function requireString(record: Record<string, unknown>, name: string): string {
    const value = cleanString(record[name]);
    if (!value) {
        throw new Error(`receiver_descriptor_missing_${name}`);
    }
    return value;
}

function parseMotionReferenceProfile(
    value: unknown,
    workspaceId: string,
): ReceiverDescriptor["motion_reference_profile"] {
    if (value === null || value === undefined) {
        return null;
    }
    if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error("motion_reference_profile_ref_invalid");
    }
    const record = value as Record<string, unknown>;
    const storageRef = requireString(record, "storage_ref");
    const expectedPrefix = (
        `/app/data/workspaces/${workspaceId}`
        + "/artifacts/yogacoach/reference-profiles/"
    );
    if (
        !storageRef.startsWith(expectedPrefix)
        || path.posix.normalize(storageRef) !== storageRef
    ) {
        throw new Error("motion_reference_profile_storage_ref_invalid");
    }
    return {
        artifact_id: requireString(record, "artifact_id"),
        storage_ref: storageRef,
        reference_profile_id: requireString(record, "reference_profile_id"),
    };
}

export function parseLiveMediaReceiverDescriptor(value: unknown): ReceiverDescriptor {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error("receiver_descriptor_required");
    }
    const record = value as Record<string, unknown>;
    if (record.schema_version !== "live_media_receiver.v1") {
        throw new Error("receiver_descriptor_schema_invalid");
    }
    const transportKind = requireString(record, "transport_kind");
    if (transportKind !== "rtsps") {
        throw new Error("receiver_transport_not_supported");
    }
    const inputUrl = requireString(record, "input_url");
    if (!inputUrl.startsWith("rtsps://")) {
        throw new Error("receiver_input_must_use_rtsps");
    }
    const expiresAtEpoch = Number(record.expires_at_epoch);
    if (!Number.isFinite(expiresAtEpoch) || expiresAtEpoch <= Date.now() / 1000) {
        throw new Error("receiver_descriptor_expired");
    }
    const coachPack = requireString(record, "coach_pack");
    if (coachPack !== "yogacoach" && coachPack !== "dance_motion_coach") {
        throw new Error("receiver_coach_pack_invalid");
    }
    const workspaceId = requireString(record, "workspace_id");
    return {
        schema_version: "live_media_receiver.v1",
        workspace_id: workspaceId,
        device_session_id: requireString(record, "device_session_id"),
        media_session_id: requireString(record, "media_session_id"),
        live_motion_session_id: requireString(record, "live_motion_session_id"),
        meeting_session_id: requireString(record, "meeting_session_id"),
        practice_session_id: requireString(record, "practice_session_id"),
        receiver_identity: requireString(record, "receiver_identity"),
        append_owner_id: requireString(record, "append_owner_id"),
        source_kind: requireString(record, "source_kind"),
        transport_kind: "rtsps",
        input_url: inputUrl,
        access_token: requireString(record, "access_token"),
        expires_at_epoch: expiresAtEpoch,
        api_base: requireString(record, "api_base"),
        coach_pack: coachPack,
        practice_mode: requireString(record, "practice_mode"),
        reference_url: cleanString(record.reference_url) || null,
        motion_reference_profile: parseMotionReferenceProfile(
            record.motion_reference_profile,
            workspaceId,
        ),
        user_goal: cleanString(record.user_goal) || null,
        expected_duration_ms: Math.max(0, Number(record.expected_duration_ms) || 0),
    };
}

export function resolveMotionReferenceProfilePath(
    root: string,
    descriptor: ReceiverDescriptor,
): string | null {
    const profile = descriptor.motion_reference_profile;
    if (!profile) {
        return null;
    }
    const allowedRoot = realpathSync(
        path.join(
            dataHostRoot(root),
            "workspaces",
            descriptor.workspace_id,
            "artifacts/yogacoach/reference-profiles",
        ),
    );
    const candidate = realpathSync(
        hostPathForContainerDataPath(root, profile.storage_ref),
    );
    const relative = path.relative(allowedRoot, candidate);
    if (relative.startsWith("..") || path.isAbsolute(relative)) {
        throw new Error("motion_reference_profile_path_outside_workspace");
    }
    if (!statSync(candidate).isFile()) {
        throw new Error("motion_reference_profile_file_not_found");
    }
    return candidate;
}

function safeSlug(value: string): string {
    return value.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^_+|_+$/g, "");
}

function receiverPaths(root: string, mediaSessionId: string) {
    const runtimeDir = path.join(dataHostRoot(root), "runtime/live-media-receivers");
    const slug = safeSlug(mediaSessionId);
    mkdirSync(runtimeDir, { recursive: true, mode: 0o700 });
    chmodSync(runtimeDir, 0o700);
    return {
        runtimeDir,
        descriptorPath: path.join(runtimeDir, `${slug}.descriptor.json`),
        statePath: path.join(runtimeDir, `${slug}.state.json`),
        logPath: path.join(runtimeDir, `${slug}.log`),
    };
}

function atomicPrivateJson(filePath: string, payload: unknown): void {
    const temporaryPath = `${filePath}.tmp-${process.pid}`;
    writeFileSync(temporaryPath, `${JSON.stringify(payload)}\n`, { mode: 0o600 });
    chmodSync(temporaryPath, 0o600);
    renameSync(temporaryPath, filePath);
}

function readState(filePath: string): ReceiverState | null {
    try {
        return JSON.parse(readFileSync(filePath, "utf8")) as ReceiverState;
    } catch {
        return null;
    }
}

function pidIsRunning(pid: number): boolean {
    if (!Number.isInteger(pid) || pid <= 1) {
        return false;
    }
    try {
        process.kill(pid, 0);
        return true;
    } catch {
        return false;
    }
}

interface ProjectRuntime {
    root: string;
    python: string;
    script: string;
    preflightScript: string;
}

function findProjectRuntime(): ProjectRuntime {
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

function assertReceiverRuntime(runtime: ProjectRuntime): void {
    const result = spawnSync(runtime.python, [runtime.preflightScript], {
        cwd: runtime.root,
        encoding: "utf8",
        env: process.env,
        shell: false,
        timeout: 15000,
    });
    if (result.status !== 0) {
        throw new Error("live_media_receiver_runtime_preflight_failed");
    }
}

function assertWorkspaceAvailable(runtimeDir: string, descriptor: ReceiverDescriptor): void {
    for (const name of readdirSync(runtimeDir)) {
        if (!name.endsWith(".state.json")) {
            continue;
        }
        const state = readState(path.join(runtimeDir, name));
        if (
            state
            && state.workspace_id === descriptor.workspace_id
            && state.media_session_id !== descriptor.media_session_id
            && pidIsRunning(state.pid)
        ) {
            throw new Error("workspace_live_media_receiver_already_active");
        }
    }
}

function publicStatus(action: string, state: ReceiverState): Record<string, unknown> {
    return {
        schema_version: "live_media_receiver_control.v1",
        action,
        status: pidIsRunning(state.pid) ? "active" : state.state,
        state: state.state,
        workspace_id: state.workspace_id,
        media_session_id: state.media_session_id,
        receiver_identity: state.receiver_identity,
        pid: state.pid,
        updated_at: state.updated_at,
        reason: state.reason,
    };
}

export function receiverStateAfterSpawn(
    current: ReceiverState | null,
    descriptor: ReceiverDescriptor,
    pid: number,
): ReceiverState {
    if (
        current
        && current.media_session_id === descriptor.media_session_id
        && current.receiver_identity === descriptor.receiver_identity
        && current.pid === pid
    ) {
        return current;
    }
    return {
        schema_version: "live_media_receiver_state.v1",
        workspace_id: descriptor.workspace_id,
        media_session_id: descriptor.media_session_id,
        receiver_identity: descriptor.receiver_identity,
        pid,
        state: "starting",
        updated_at: new Date().toISOString(),
    };
}

function wait(delayMs: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, delayMs));
}

async function waitForReceiverReady(
    statePath: string,
    pid: number,
    timeoutMs: number,
): Promise<ReceiverState> {
    const readyStates = new Set<ReceiverStateName>([
        "waiting_source",
        "receiving",
        "analyzing",
        "degraded",
    ]);
    const deadline = Date.now() + Math.min(Math.max(timeoutMs, 1000), 10000);
    while (Date.now() < deadline) {
        const state = readState(statePath);
        if (state && readyStates.has(state.state)) {
            return state;
        }
        if (state && (state.state === "failed" || state.state === "expired")) {
            throw new Error(state.reason || `live_media_receiver_${state.state}`);
        }
        if (!pidIsRunning(pid)) {
            throw new Error("live_media_receiver_exited_before_ready");
        }
        await wait(100);
    }
    throw new Error("live_media_receiver_readiness_timeout");
}

export async function startLiveMediaReceiver(
    rawDescriptor: unknown,
    timeoutMs = 10000,
): Promise<Record<string, unknown>> {
    const descriptor = parseLiveMediaReceiverDescriptor(rawDescriptor);
    const runtime = findProjectRuntime();
    assertReceiverRuntime(runtime);
    const motionReferenceProfilePath = resolveMotionReferenceProfilePath(
        runtime.root,
        descriptor,
    );
    const paths = receiverPaths(runtime.root, descriptor.media_session_id);
    const existing = readState(paths.statePath);
    if (existing && pidIsRunning(existing.pid)) {
        if (existing.receiver_identity !== descriptor.receiver_identity) {
            throw new Error("receiver_identity_conflict");
        }
        return publicStatus("receiver_start", existing);
    }
    assertWorkspaceAvailable(paths.runtimeDir, descriptor);
    atomicPrivateJson(paths.descriptorPath, {
        ...descriptor,
        motion_reference_profile_path: motionReferenceProfilePath,
    });
    atomicPrivateJson(paths.statePath, {
        schema_version: "live_media_receiver_state.v1",
        workspace_id: descriptor.workspace_id,
        media_session_id: descriptor.media_session_id,
        receiver_identity: descriptor.receiver_identity,
        pid: 0,
        state: "starting",
        updated_at: new Date().toISOString(),
    } satisfies ReceiverState);
    const logFd = openSync(paths.logPath, "a", 0o600);
    chmodSync(paths.logPath, 0o600);
    const child = spawn(
        runtime.python,
        [
            runtime.script,
            "--descriptor-path",
            paths.descriptorPath,
            "--state-path",
            paths.statePath,
        ],
        {
            cwd: runtime.root,
            detached: true,
            env: {
                ...process.env,
                LOCAL_CORE_DATA_HOST_DIR: dataHostRoot(runtime.root),
            },
            shell: false,
            stdio: ["ignore", logFd, logFd],
        },
    );
    child.unref();
    closeSync(logFd);
    if (!child.pid) {
        throw new Error("live_media_receiver_spawn_failed");
    }
    const state = receiverStateAfterSpawn(
        readState(paths.statePath),
        descriptor,
        child.pid,
    );
    if (state.pid !== readState(paths.statePath)?.pid) {
        atomicPrivateJson(paths.statePath, state);
    }
    const ready = await waitForReceiverReady(paths.statePath, child.pid, timeoutMs);
    return publicStatus("receiver_start", ready);
}

export async function stopLiveMediaReceiver(
    mediaSessionId: string,
    receiverIdentity: string,
    timeoutMs = 10000,
): Promise<Record<string, unknown>> {
    const runtime = findProjectRuntime();
    const paths = receiverPaths(runtime.root, mediaSessionId);
    const state = readState(paths.statePath);
    if (!state) {
        return {
            schema_version: "live_media_receiver_control.v1",
            action: "receiver_stop",
            status: "not_found",
            media_session_id: mediaSessionId,
        };
    }
    if (state.receiver_identity !== receiverIdentity) {
        throw new Error("receiver_identity_conflict");
    }
    state.state = "stopping";
    state.updated_at = new Date().toISOString();
    atomicPrivateJson(paths.statePath, state);
    if (pidIsRunning(state.pid)) {
        process.kill(state.pid, "SIGTERM");
    }
    const deadline = Date.now() + Math.min(Math.max(timeoutMs, 1000), 10000);
    while (Date.now() < deadline && pidIsRunning(state.pid)) {
        await wait(100);
    }
    if (pidIsRunning(state.pid)) {
        throw new Error("live_media_receiver_stop_timeout");
    }
    const terminal = readState(paths.statePath) || state;
    if (terminal.state === "stopping") {
        terminal.state = "completed";
        terminal.updated_at = new Date().toISOString();
        atomicPrivateJson(paths.statePath, terminal);
    }
    return publicStatus("receiver_stop", terminal);
}

export function getLiveMediaReceiverStatus(
    mediaSessionId: string,
): Record<string, unknown> {
    const runtime = findProjectRuntime();
    const paths = receiverPaths(runtime.root, mediaSessionId);
    const state = readState(paths.statePath);
    if (!state) {
        return {
            schema_version: "live_media_receiver_control.v1",
            action: "receiver_status",
            status: "not_found",
            media_session_id: mediaSessionId,
        };
    }
    return publicStatus("receiver_status", state);
}
