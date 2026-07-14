import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import test from "node:test";

import {
    parseLiveMediaReceiverDescriptor,
    receiverStateAfterSpawn,
    stopLiveMediaReceiver,
} from "./live-media-receiver.js";

function descriptor(): Record<string, unknown> {
    return {
        schema_version: "live_media_receiver.v1",
        workspace_id: "workspace-one",
        device_session_id: "device-one",
        media_session_id: "media-one",
        live_motion_session_id: "motion-one",
        meeting_session_id: "meeting-one",
        practice_session_id: "practice-one",
        receiver_identity: "receiver-one",
        append_owner_id: "append-one",
        source_kind: "phone_camera",
        transport_kind: "rtsps",
        input_url: "rtsps://media.example.test:8322/live/path",
        access_token: "secret-token",
        expires_at_epoch: Date.now() / 1000 + 3600,
        api_base: "http://127.0.0.1:8200",
        coach_pack: "yogacoach",
        practice_mode: "live_guidance",
        expected_duration_ms: 0,
    };
}

test("accepts the server-issued RTSPS descriptor", () => {
    const parsed = parseLiveMediaReceiverDescriptor(descriptor());

    assert.equal(parsed.transport_kind, "rtsps");
    assert.equal(parsed.media_session_id, "media-one");
    assert.equal(parsed.access_token, "secret-token");
});

test("rejects a public RTMP descriptor on the formal receiver path", () => {
    const input = descriptor();
    input.transport_kind = "rtmp";
    input.input_url = "rtmp://media.example.test/live/path";

    assert.throws(
        () => parseLiveMediaReceiverDescriptor(input),
        /receiver_transport_not_supported/,
    );
});

test("rejects expired credentials before spawning a process", () => {
    const input = descriptor();
    input.expires_at_epoch = Date.now() / 1000 - 1;

    assert.throws(
        () => parseLiveMediaReceiverDescriptor(input),
        /receiver_descriptor_expired/,
    );
});

test("does not overwrite a child ready state after spawn", () => {
    const parsed = parseLiveMediaReceiverDescriptor(descriptor());
    const childState = {
        schema_version: "live_media_receiver_state.v1" as const,
        workspace_id: parsed.workspace_id,
        media_session_id: parsed.media_session_id,
        receiver_identity: parsed.receiver_identity,
        pid: 4242,
        state: "waiting_source" as const,
        updated_at: "2026-07-14T00:00:00Z",
    };

    assert.equal(
        receiverStateAfterSpawn(childState, parsed, 4242),
        childState,
    );
});

test("confirms child exit before reporting receiver stop", async () => {
    const dataRoot = mkdtempSync(path.join(tmpdir(), "live-media-receiver-stop-"));
    const previousProjectRoot = process.env.LOCAL_CORE_PROJECT_ROOT;
    const previousPython = process.env.LOCAL_CORE_MOTION_RECEIVER_PYTHON;
    const previousDataRoot = process.env.LOCAL_CORE_DATA_HOST_DIR;
    const child = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], {
        stdio: "ignore",
    });
    try {
        assert.ok(child.pid);
        process.env.LOCAL_CORE_PROJECT_ROOT = path.resolve(process.cwd(), "..");
        process.env.LOCAL_CORE_MOTION_RECEIVER_PYTHON = process.execPath;
        process.env.LOCAL_CORE_DATA_HOST_DIR = dataRoot;
        const runtimeDir = path.join(dataRoot, "runtime/live-media-receivers");
        mkdirSync(runtimeDir, { recursive: true });
        writeFileSync(
            path.join(runtimeDir, "media-stop.state.json"),
            JSON.stringify({
                schema_version: "live_media_receiver_state.v1",
                workspace_id: "workspace-stop",
                media_session_id: "media-stop",
                receiver_identity: "receiver-stop",
                pid: child.pid,
                state: "analyzing",
                updated_at: new Date().toISOString(),
            }),
        );

        const result = await stopLiveMediaReceiver(
            "media-stop",
            "receiver-stop",
            3000,
        );

        assert.equal(result.status, "completed");
        assert.equal(result.state, "completed");
        assert.throws(() => process.kill(child.pid!, 0));
    } finally {
        if (child.pid) {
            try {
                process.kill(child.pid, "SIGKILL");
            } catch {
                // The expected path already stopped the child.
            }
        }
        if (previousProjectRoot === undefined) delete process.env.LOCAL_CORE_PROJECT_ROOT;
        else process.env.LOCAL_CORE_PROJECT_ROOT = previousProjectRoot;
        if (previousPython === undefined) delete process.env.LOCAL_CORE_MOTION_RECEIVER_PYTHON;
        else process.env.LOCAL_CORE_MOTION_RECEIVER_PYTHON = previousPython;
        if (previousDataRoot === undefined) delete process.env.LOCAL_CORE_DATA_HOST_DIR;
        else process.env.LOCAL_CORE_DATA_HOST_DIR = previousDataRoot;
        rmSync(dataRoot, { recursive: true, force: true });
    }
});
