import test from "node:test";
import assert from "node:assert/strict";

import { TrustLevel } from "../src/governance/permission-map.js";
import { createBuiltinTools } from "../src/mcp-server/builtin-tools.js";

test("builtin MCP tool names stay unique", () => {
    const tools = createBuiltinTools();
    const names = tools.map((tool) => tool.name);
    assert.equal(new Set(names).size, names.length);
    assert.ok(names.includes("capture_relay_control"));
    assert.ok(names.includes("host_resource_runner_spillover_control"));
});

test("capture relay MCP schema exposes the committed relay actions", () => {
    const captureRelayTool = createBuiltinTools().find((tool) => tool.name === "capture_relay_control");
    assert.ok(captureRelayTool);
    assert.equal(captureRelayTool.trustLevel, TrustLevel.EXECUTE);

    const schema = captureRelayTool.inputSchema as {
        properties?: Record<string, { enum?: string[]; type?: string }>;
    };
    const properties = schema.properties || {};

    assert.deepEqual(properties.action?.enum, [
        "status",
        "install_mediamtx",
        "start",
        "stop",
        "open_obs",
        "configure_obs",
    ]);
    assert.equal(properties.scene_name?.type, "string");
    assert.equal(properties.source_name?.type, "string");
    assert.equal(properties.start_virtual_camera?.type, "boolean");
    assert.deepEqual(properties.install_method?.enum, ["homebrew"]);
});
