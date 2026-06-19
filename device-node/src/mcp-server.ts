/**
 * MCP Server Implementation
 *
 * Provides a standard MCP (Model Context Protocol) server that exposes
 * device capabilities with permission governance.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
    CallToolRequestSchema,
    ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { PermissionMap, TrustLevel } from "./governance/permission-map.js";
import { LocalCoreBridge } from "./bridge/local-core-client.js";
import { filesystemRead, filesystemWrite, filesystemList } from "./capabilities/filesystem.js";
import { shellExecute } from "./capabilities/shell.js";
import { hostResourceProbe } from "./capabilities/host-resource-probe.js";
import { hostResourceLaneWorkersSet } from "./capabilities/host-resource-lane-workers.js";
import { hostResourceRunnerSpilloverControl } from "./capabilities/host-resource-runner-spillover.js";
import { cliBridgeServiceControl } from "./capabilities/cli-bridge-service-control.js";
import { hostOpenDocument } from "./capabilities/host-open-document.js";
import * as http from "http";

export interface MCPServerConfig {
    name: string;
    version: string;
    permissionMap: PermissionMap;
}

interface ToolDefinition {
    name: string;
    description: string;
    inputSchema: object;
    handler: (args: Record<string, unknown>) => Promise<unknown>;
    trustLevel: TrustLevel;
}

export class MCPServer {
    private server: Server;
    private permissionMap: PermissionMap;
    private bridge?: LocalCoreBridge;
    private tools: Map<string, ToolDefinition> = new Map();
    private httpServer?: http.Server;

    constructor(config: MCPServerConfig) {
        this.permissionMap = config.permissionMap;

        this.server = new Server(
            {
                name: config.name,
                version: config.version,
            },
            {
                capabilities: {
                    tools: {},
                },
            }
        );

        this.registerBuiltinTools();
        this.setupHandlers();
    }

    setBridge(bridge: LocalCoreBridge): void {
        this.bridge = bridge;
    }

    private registerBuiltinTools(): void {
        this.registerTool({
            name: "filesystem_read",
            description: "Read file contents from the local filesystem (sandboxed)",
            inputSchema: {
                type: "object",
                properties: {
                    path: { type: "string", description: "Absolute or relative file path" },
                },
                required: ["path"],
            },
            handler: filesystemRead,
            trustLevel: TrustLevel.READ,
        });

        this.registerTool({
            name: "filesystem_write",
            description: "Write content to a file (requires confirmation)",
            inputSchema: {
                type: "object",
                properties: {
                    path: { type: "string", description: "Absolute or relative file path" },
                    content: { type: "string", description: "Content to write" },
                },
                required: ["path", "content"],
            },
            handler: filesystemWrite,
            trustLevel: TrustLevel.DRAFT,
        });

        this.registerTool({
            name: "filesystem_list",
            description: "List directory contents",
            inputSchema: {
                type: "object",
                properties: {
                    path: { type: "string", description: "Directory path" },
                },
                required: ["path"],
            },
            handler: filesystemList,
            trustLevel: TrustLevel.READ,
        });

        this.registerTool({
            name: "shell_execute",
            description: "Execute a shell command (requires confirmation)",
            inputSchema: {
                type: "object",
                properties: {
                    command: { type: "string", description: "Command to execute" },
                    args: {
                        type: "array",
                        items: { type: "string" },
                        description: "Command arguments",
                    },
                    cwd: { type: "string", description: "Working directory (optional)" },
                    timeout_ms: {
                        type: "number",
                        description: "Execution timeout in milliseconds (optional, capped by device-node)",
                    },
                },
                required: ["command"],
            },
            handler: shellExecute,
            trustLevel: TrustLevel.EXECUTE,
        });

        this.registerTool({
            name: "host_resource_probe",
            description: "Read host resource pressure and selected runtime processes",
            inputSchema: {
                type: "object",
                properties: {
                    timeout_ms: {
                        type: "number",
                        description: "Per-command timeout in milliseconds (optional, capped by device-node)",
                    },
                },
            },
            handler: hostResourceProbe,
            trustLevel: TrustLevel.READ,
        });

        this.registerTool({
            name: "host_resource_lane_workers_set",
            description: "Set dynamic host resource lane worker target",
            inputSchema: {
                type: "object",
                properties: {
                    lane_id: { type: "string", description: "Host resource lane id" },
                    desired_worker_count: { type: "number", description: "Desired worker count" },
                    queue_shard: { type: "string", description: "Target runner queue shard" },
                    runner_profile: { type: "string", description: "Runner profile hint" },
                    resource_class: { type: "string", description: "Resource class" },
                    worker_env: {
                        type: "object",
                        description: "Environment values for a managed worker",
                    },
                },
                required: ["lane_id", "desired_worker_count"],
            },
            handler: hostResourceLaneWorkersSet,
            trustLevel: TrustLevel.EXECUTE,
        });

        this.registerTool({
            name: "host_resource_runner_spillover_control",
            description: "Control the fixed runner-spillover compose service",
            inputSchema: {
                type: "object",
                properties: {
                    action: {
                        type: "string",
                        enum: ["status", "start", "stop"],
                        description: "Spillover action",
                    },
                    profile_code: {
                        type: "string",
                        description:
                            "Built-in runner profile or a custom profile code for spillover start/status context",
                    },
                    max_inflight: {
                        type: "number",
                        description: "Bounded max inflight for start, clamped to 1-4",
                    },
                    accepted_partitions: {
                        type: "string",
                        description:
                            "Required for custom profiles; comma-separated queue partitions",
                    },
                    accepted_resource_classes: {
                        type: "string",
                        description:
                            "Required for custom profiles; comma-separated resource classes",
                    },
                    accepted_capability_codes: {
                        type: "string",
                        description:
                            "Required for custom profiles; comma-separated capability codes",
                    },
                    runtime_endpoint: {
                        type: "string",
                        description:
                            "Required for custom profiles; runtime base URL exposed to the runner",
                    },
                    runtime_id: {
                        type: "string",
                        description: "Optional runtime identifier override",
                    },
                    runtime_model: {
                        type: "string",
                        description: "Optional runtime model override",
                    },
                    runtime_max_output_tokens: {
                        type: "string",
                        description: "Optional runtime max output token cap",
                    },
                    runtime_context_budget_tokens: {
                        type: "string",
                        description: "Optional runtime context budget token cap",
                    },
                    display_name: {
                        type: "string",
                        description: "Optional runner display name override",
                    },
                    db_application_name: {
                        type: "string",
                        description: "Optional PostgreSQL application_name override",
                    },
                },
            },
            handler: hostResourceRunnerSpilloverControl,
            trustLevel: TrustLevel.EXECUTE,
        });

        this.registerTool({
            name: "cli_bridge_service_control",
            description: "Read or start the fixed Mindscape CLI bridge LaunchAgent",
            inputSchema: {
                type: "object",
                properties: {
                    action: {
                        type: "string",
                        enum: ["status", "start", "restart"],
                        description: "LaunchAgent action",
                    },
                },
            },
            handler: cliBridgeServiceControl,
            trustLevel: TrustLevel.EXECUTE,
        });

        this.registerTool({
            name: "host_open_document",
            description: "Open a governed host document in a native desktop app",
            inputSchema: {
                type: "object",
                properties: {
                    path: { type: "string", description: "Absolute host document path" },
                    app_name: { type: "string", description: "Native app name" },
                    timeout_ms: {
                        type: "number",
                        description: "Open command timeout in milliseconds",
                    },
                },
                required: ["path"],
            },
            handler: hostOpenDocument,
            trustLevel: TrustLevel.EXECUTE,
        });
    }

    private registerTool(tool: ToolDefinition): void {
        this.tools.set(tool.name, tool);
    }

    private setupHandlers(): void {
        this.server.setRequestHandler(ListToolsRequestSchema, async () => {
            const toolsList = Array.from(this.tools.values()).map((tool) => ({
                name: tool.name,
                description: tool.description,
                inputSchema: tool.inputSchema,
            }));

            return { tools: toolsList };
        });

        this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
            const { name, arguments: args } = request.params;
            const tool = this.tools.get(name);

            if (!tool) {
                throw new Error(`Unknown tool: ${name}`);
            }

            const permissionCheck = await this.permissionMap.checkPermission(
                name,
                args as Record<string, unknown>
            );

            if (!permissionCheck.allowed) {
                throw new Error(`Permission denied: ${permissionCheck.reason}`);
            }

            if (permissionCheck.requiresConfirmation && this.bridge) {
                const confirmed = await this.bridge.requestConfirmation({
                    tool: name,
                    arguments: args as Record<string, unknown>,
                    trustLevel: tool.trustLevel,
                    preview: permissionCheck.preview,
                });

                if (!confirmed) {
                    throw new Error("User denied the operation");
                }
            }

            try {
                const result = await tool.handler(args as Record<string, unknown>);

                if (this.bridge) {
                    await this.bridge.reportAuditEvent({
                        tool: name,
                        arguments: args as Record<string, unknown>,
                        result: "success",
                        trustLevel: tool.trustLevel,
                    });
                }

                return {
                    content: [
                        {
                            type: "text",
                            text: typeof result === "string" ? result : JSON.stringify(result, null, 2),
                        },
                    ],
                };
            } catch (error) {
                if (this.bridge) {
                    await this.bridge.reportAuditEvent({
                        tool: name,
                        arguments: args as Record<string, unknown>,
                        result: "error",
                        error: error instanceof Error ? error.message : String(error),
                        trustLevel: tool.trustLevel,
                    });
                }
                throw error;
            }
        });
    }

    async startStdio(): Promise<void> {
        const transport = new StdioServerTransport();
        await this.server.connect(transport);
    }

    /**
     * Start HTTP server for MCP requests
     * Simplified JSON-RPC over HTTP implementation
     */
    async startHttp(port: number): Promise<void> {
        this.httpServer = http.createServer(async (req, res) => {
            // CORS headers for Docker container access
            res.setHeader("Access-Control-Allow-Origin", "*");
            res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
            res.setHeader("Access-Control-Allow-Headers", "Content-Type, X-Request-Source, X-Capability-Code");

            if (req.method === "OPTIONS") {
                res.writeHead(204);
                res.end();
                return;
            }

            if (req.method !== "POST" || req.url !== "/mcp") {
                res.writeHead(404, { "Content-Type": "application/json" });
                res.end(JSON.stringify({ error: "Not found" }));
                return;
            }

            let body = "";
            for await (const chunk of req) {
                body += chunk;
            }

            try {
                const request = JSON.parse(body);
                const { method, params, id } = request;

                let result: unknown;

                if (method === "tools/list") {
                    const toolsList = Array.from(this.tools.values()).map((tool) => ({
                        name: tool.name,
                        description: tool.description,
                        inputSchema: tool.inputSchema,
                    }));
                    result = { tools: toolsList };
                } else if (method === "tools/call") {
                    const { name, arguments: args } = params;
                    const tool = this.tools.get(name);

                    if (!tool) {
                        throw new Error(`Unknown tool: ${name}`);
                    }

                    const permissionCheck = await this.permissionMap.checkPermission(
                        name,
                        args as Record<string, unknown>
                    );

                    if (!permissionCheck.allowed) {
                        throw new Error(`Permission denied: ${permissionCheck.reason}`);
                    }

                    const toolResult = await tool.handler(args as Record<string, unknown>);
                    result = {
                        success: true,
                        content: [
                            {
                                type: "text",
                                text: typeof toolResult === "string" ? toolResult : JSON.stringify(toolResult, null, 2),
                            },
                        ],
                    };
                } else {
                    throw new Error(`Unknown method: ${method}`);
                }

                res.writeHead(200, { "Content-Type": "application/json" });
                res.end(JSON.stringify({
                    jsonrpc: "2.0",
                    id,
                    result,
                }));
            } catch (error) {
                res.writeHead(200, { "Content-Type": "application/json" });
                res.end(JSON.stringify({
                    jsonrpc: "2.0",
                    id: null,
                    error: {
                        code: -32000,
                        message: error instanceof Error ? error.message : String(error),
                    },
                }));
            }
        });

        await new Promise<void>((resolve) => {
            this.httpServer!.listen(port, "0.0.0.0", () => {
                console.log(`MCP HTTP Server listening on 0.0.0.0:${port}`);
                resolve();
            });
        });
    }

    async stop(): Promise<void> {
        if (this.httpServer) {
            await new Promise<void>((resolve) => {
                this.httpServer!.close(() => resolve());
            });
        }
        await this.server.close();
    }
}
