import { readFileSync, readdirSync } from "node:fs";
import * as path from "node:path";

export type ReceiverProcessStateName =
    | "starting"
    | "waiting_source"
    | "receiving"
    | "analyzing"
    | "degraded"
    | "stopping"
    | "completed"
    | "failed"
    | "expired";

export interface ReceiverProcessState {
    workspace_id: string;
    media_session_id: string;
    pid: number;
    state: ReceiverProcessStateName;
}

const TERMINAL_RECEIVER_STATES = new Set<ReceiverProcessStateName>([
    "completed",
    "failed",
    "expired",
]);

export function receiverStateIsTerminal(state: ReceiverProcessStateName): boolean {
    return TERMINAL_RECEIVER_STATES.has(state);
}

export function receiverStateOwnsLiveProcess(
    state: ReceiverProcessState,
    pidIsRunning: (pid: number) => boolean,
): boolean {
    return !receiverStateIsTerminal(state.state) && pidIsRunning(state.pid);
}

function readReceiverState(filePath: string): ReceiverProcessState | null {
    try {
        return JSON.parse(readFileSync(filePath, "utf8")) as ReceiverProcessState;
    } catch {
        return null;
    }
}

export function assertWorkspaceReceiverAvailable(input: {
    runtimeDir: string;
    workspaceId: string;
    mediaSessionId: string;
    pidIsRunning: (pid: number) => boolean;
}): void {
    for (const name of readdirSync(input.runtimeDir)) {
        if (!name.endsWith(".state.json")) continue;
        const state = readReceiverState(path.join(input.runtimeDir, name));
        if (
            state
            && state.workspace_id === input.workspaceId
            && state.media_session_id !== input.mediaSessionId
            && receiverStateOwnsLiveProcess(state, input.pidIsRunning)
        ) {
            throw new Error("workspace_live_media_receiver_already_active");
        }
    }
}
