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
                },
                required: ["command"],
            },
            handler: shellExecute,
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
            this.httpServer!.listen(port, () => {
                console.log(`MCP HTTP Server listening on port ${port}`);
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
