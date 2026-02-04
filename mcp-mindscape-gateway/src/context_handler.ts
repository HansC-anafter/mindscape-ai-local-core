/**
 * Context Handler - External Context Processing
 *
 * Processes _context parameter from external tool calls to enable
 * Intent/Seed/Decision tracking even when called from external surfaces.
 */
import { MindscapeClient } from "./mindscape/client.js";
import { config } from "./config.js";

export interface ExternalContext {
    original_message?: string;
    surface_type?: string;
    surface_user_id?: string;
    conversation_id?: string;
    session_id?: string;
    intent_hint?: string;
}

export interface ContextProcessingResult {
    intent_id?: string;
    seed_id?: string;
    context_recorded: boolean;
    error?: string;
}

export class ContextHandler {
    constructor(private client: MindscapeClient) { }

    /**
     * Process external context from tool call.
     * Records intent, extracts seed, and links to memory graph.
     */
    async processContext(
        workspaceId: string,
        toolName: string,
        context: ExternalContext
    ): Promise<ContextProcessingResult> {
        if (!context || !context.original_message) {
            return { context_recorded: false };
        }

        try {
            const result = await this.recordExternalInteraction({
                workspace_id: workspaceId,
                tool_called: toolName,
                ...context
            });

            return {
                intent_id: result.intent_id,
                seed_id: result.seed_id,
                context_recorded: true
            };
        } catch (error: any) {
            console.error("[ContextHandler] Failed to process context:", error.message);
            return {
                context_recorded: false,
                error: error.message
            };
        }
    }

    /**
     * Record external interaction to timeline and memory.
     */
    private async recordExternalInteraction(params: {
        workspace_id: string;
        tool_called: string;
        original_message?: string;
        surface_type?: string;
        surface_user_id?: string;
        conversation_id?: string;
        intent_hint?: string;
    }): Promise<{ intent_id?: string; seed_id?: string }> {
        // Call backend API to record external interaction
        // This endpoint should parse intent, extract seed, and record to timeline
        try {
            const response = await this.client.recordExternalContext({
                workspace_id: params.workspace_id,
                surface_type: params.surface_type || "mcp_external",
                surface_user_id: params.surface_user_id || "anonymous",
                original_message: params.original_message,
                tool_called: params.tool_called,
                conversation_id: params.conversation_id,
                intent_hint: params.intent_hint,
                timestamp: new Date().toISOString()
            });

            return {
                intent_id: response.intent_id,
                seed_id: response.seed_id
            };
        } catch (error: any) {
            // If backend doesn't support this endpoint yet, log and continue
            if (error.response?.status === 404) {
                console.warn("[ContextHandler] External context API not available, skipping recording");
                return {};
            }
            throw error;
        }
    }

    /**
     * Build context schema for tool definitions.
     * This schema is added to all tools to accept _context parameter.
     */
    static getContextSchema(): Record<string, any> {
        return {
            _context: {
                type: "object",
                description: "Optional: Pass conversation context for tracking and learning",
                properties: {
                    original_message: {
                        type: "string",
                        description: "The user's original message that triggered this tool call"
                    },
                    surface_type: {
                        type: "string",
                        description: "External surface type (e.g., claude_desktop, cursor, custom)"
                    },
                    surface_user_id: {
                        type: "string",
                        description: "User identifier from external surface"
                    },
                    conversation_id: {
                        type: "string",
                        description: "Conversation/session ID from external surface"
                    },
                    intent_hint: {
                        type: "string",
                        description: "Optional intent classification hint from external LLM"
                    }
                }
            }
        };
    }

    /**
     * Extract _context from tool arguments.
     */
    static extractContext(args: Record<string, any>): ExternalContext | undefined {
        if (args._context && typeof args._context === "object") {
            return args._context as ExternalContext;
        }
        return undefined;
    }
}
