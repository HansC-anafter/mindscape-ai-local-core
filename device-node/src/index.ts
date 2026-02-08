/**
 * Mindscape Device Node - Entry Point
 *
 * This is the main entry point for the Device Node service.
 * It initializes the MCP Server and connects to Local-Core.
 */

import { MCPServer } from "./mcp-server.js";
import { PermissionMap } from "./governance/permission-map.js";
import { LocalCoreBridge } from "./bridge/local-core-client.js";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

interface DeviceNodeConfig {
    localCoreUrl: string;
    permissionsPath: string;
    transport: "stdio" | "http";
    httpPort?: number;
}

async function loadConfig(): Promise<DeviceNodeConfig> {
    const configPath = path.join(__dirname, "../config/device-node.json");

    if (fs.existsSync(configPath)) {
        const configContent = fs.readFileSync(configPath, "utf-8");
        return JSON.parse(configContent);
    }

    return {
        localCoreUrl: process.env.LOCAL_CORE_URL || "ws://localhost:8000/ws",
        permissionsPath: path.join(__dirname, "../config/permissions.yaml"),
        transport: (process.env.MCP_TRANSPORT as "stdio" | "http") || "stdio",
        httpPort: parseInt(process.env.MCP_HTTP_PORT || "3100", 10),
    };
}

async function main(): Promise<void> {
    console.log("🚀 Mindscape Device Node starting...");

    try {
        const config = await loadConfig();

        const permissionMap = new PermissionMap(config.permissionsPath);
        await permissionMap.load();
        console.log("✅ Permission map loaded");

        const mcpServer = new MCPServer({
            name: "mindscape-device-node",
            version: "0.1.0",
            permissionMap,
        });
        console.log("✅ MCP Server initialized");

        const bridge = new LocalCoreBridge(config.localCoreUrl);
        mcpServer.setBridge(bridge);
        console.log("✅ Local-Core bridge configured");

        if (config.transport === "stdio") {
            await mcpServer.startStdio();
            console.log("✅ MCP Server running (stdio mode)");
        } else {
            await mcpServer.startHttp(config.httpPort!);
            console.log(`✅ MCP Server running (HTTP mode on port ${config.httpPort})`);
        }

        const handleShutdown = async (): Promise<void> => {
            console.log("\n🛑 Shutting down Device Node...");
            await mcpServer.stop();
            await bridge.disconnect();
            process.exit(0);
        };

        process.on("SIGINT", handleShutdown);
        process.on("SIGTERM", handleShutdown);

        console.log("🎯 Device Node ready and waiting for connections");
    } catch (error) {
        console.error("❌ Failed to start Device Node:", error);
        process.exit(1);
    }
}

main();
