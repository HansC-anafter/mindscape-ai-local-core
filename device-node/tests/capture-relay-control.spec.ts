import test from "node:test";
import assert from "node:assert/strict";

import {
    buildRelayUrls,
    captureRelayControl,
    normalizeStreamName,
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

test("buildRelayUrls produces the RTMP publish and OBS read endpoints", () => {
    assert.deepEqual(buildRelayUrls("external-camera", 1935, 8554, "192.168.0.10"), {
        stream_name: "external-camera",
        publish_url: "rtmp://192.168.0.10/external-camera",
        read_url: "rtsp://127.0.0.1:8554/external-camera",
    });
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
