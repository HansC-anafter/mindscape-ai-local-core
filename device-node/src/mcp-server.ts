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
import { PermissionMap } from "./governance/permission-map.js";
import { LocalCoreBridge } from "./bridge/local-core-client.js";
import { createBuiltinTools } from "./mcp-server/builtin-tools.js";
import type { ToolDefinition } from "./mcp-server/tool-definition.js";
import {
    attachHttpServerErrorHandlers,
    isRequestAbortedError,
    readRequestBody,
    writeJsonResponse,
    writeJsonRpcError,
} from "./http/mcp-http-error-boundary.js";
import * as http from "http";

export interface MCPServerConfig {
    name: string;
    version: string;
    permissionMap: PermissionMap;
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
        for (const tool of createBuiltinTools()) {
            this.registerTool(tool);
        }
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
                writeJsonResponse(res, 404, { error: "Not found" });
                return;
            }

            try {
                const body = await readRequestBody(req);
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

                writeJsonResponse(res, 200, {
                    jsonrpc: "2.0",
                    id,
                    result,
                });
            } catch (error) {
                if (isRequestAbortedError(error)) {
                    return;
                }
                writeJsonRpcError(res, error instanceof Error ? error.message : String(error));
            }
        });

        attachHttpServerErrorHandlers(this.httpServer);

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
