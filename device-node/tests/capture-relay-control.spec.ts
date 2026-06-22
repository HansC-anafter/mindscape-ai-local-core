import test from "node:test";
import assert from "node:assert/strict";

import {
    buildRelayUrls,
    captureRelayControl,
    inferPublisherState,
    normalizeStreamName,
    resolveObsAppPath,
    resolveRelayBinary,
} from "../src/capabilities/capture-relay-control.js";

test("normalizeStreamName keeps the stream path neutral and URL-safe", () => {
    assert.equal(normalizeStreamName(" External Cam / 01 "), "external-cam-01");
    assert.equal(normalizeStreamName(""), "external-camera");
});

test("resolveRelayBinary does not accept missing configured binaries", () => {
    assert.equal(
        resolveRelayBinary({
            env: { CAPTURE_RELAY_MEDIAMTX_BIN: "/tmp/missing-mediamtx" },
            pathValue: "",
            commonPaths: [],
        }),
        null,
    );
});

test("resolveObsAppPath uses explicit app directories and rejects missing overrides", () => {
    assert.equal(
        resolveObsAppPath({
            env: { CAPTURE_RELAY_OBS_APP_PATH: "/tmp/missing-obs-app" },
            commonPaths: [process.cwd()],
        }),
        null,
    );
    assert.equal(
        resolveObsAppPath({
            env: {},
            commonPaths: [process.cwd()],
        }),
        process.cwd(),
    );
});

test("buildRelayUrls produces the RTMP publish and OBS read endpoints", () => {
    assert.deepEqual(buildRelayUrls("external-camera", 1935, 8554, "192.168.0.10"), {
        stream_name: "external-camera",
        publish_url: "rtmp://192.168.0.10/external-camera",
        read_url: "rtsp://127.0.0.1:8554/external-camera",
    });
});

test("inferPublisherState reports the external publisher as waiting when OBS reads an empty path", () => {
    assert.deepEqual(
        inferPublisherState({
            streamName: "external-camera",
            relayRunning: true,
            recentOutput: [
                "2026/06/21 03:59:08 INF [RTSP] [conn 127.0.0.1:57472] closed: path 'external-camera' is not configured",
            ],
        }),
        {
            stream_name: "external-camera",
            has_publisher: false,
            state: "waiting_for_publisher",
            reason: "no_publisher_for_stream",
            detail: "OBS requested the stream, but no external RTMP publisher is connected to this path.",
        },
    );
});

test("inferPublisherState reports publishing when MediaMTX logs an active stream publisher", () => {
    const state = inferPublisherState({
        streamName: "external-camera",
        relayRunning: true,
        recentOutput: [
            "2026/06/21 04:01:00 INF [RTMP] [conn 192.168.0.22:55111] is publishing to path 'external-camera', 1 track",
        ],
    });

    assert.equal(state.has_publisher, true);
    assert.equal(state.state, "publishing");
});

test("captureRelayControl rejects unsupported actions before host process checks", async () => {
    assert.deepEqual(await captureRelayControl({ action: "launch_random_tool" }), {
        schema_version: "capture_relay_control.v1",
        action: "launch_random_tool",
        status: "rejected",
        reason: "unsupported_action",
    });
});

test("captureRelayControl status returns a neutral relay payload", async () => {
    const result = await captureRelayControl({
        action: "status",
        stream_name: "External Camera",
    });

    assert.equal(result.schema_version, "capture_relay_control.v1");
    assert.equal(result.action, "status");
    assert.equal((result.urls as Record<string, string>).stream_name, "external-camera");
    assert.match((result.urls as Record<string, string>).publish_url, /^rtmp:\/\//);
    assert.match((result.urls as Record<string, string>).read_url, /^rtsp:\/\/127\.0\.0\.1:/);
    assert.equal((result.install_guidance as Record<string, string>).dependency, "mediamtx");
    assert.equal(
        (result.install_guidance as Record<string, string>).official_release_url,
        "https://github.com/bluenviron/mediamtx/releases/latest",
    );
    assert.ok(Array.isArray(result.next_steps));
});
