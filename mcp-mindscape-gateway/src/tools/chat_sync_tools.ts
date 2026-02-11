/**
 * Chat Sync MCP Tools
 *
 * Tool for syncing IDE conversation to Workspace timeline.
 * Governance: Inv.3 (Receipts over Claims) — ide_receipts skip WS-side LLM.
 */

// ============================================
// Tool Definitions
// ============================================
export const chatSyncTools = [
    {
        name: "mindscape_chat_sync",
        description: "Sync IDE conversation to Workspace timeline. " +
            "Records messages as timeline events and triggers automatic side-effects. " +
            "Pass ide_receipts for steps the IDE already completed to skip WS-side LLM.",
        inputSchema: {
            type: "object",
            properties: {
                workspace_id: {
                    type: "string",
                    description: "Target workspace ID"
                },
                conversation_id: {
                    type: "string",
                    description: "IDE conversation/thread ID (used as thread_id)"
                },
                trace_id: {
                    type: "string",
                    description: "Cross-system correlation ID for tracing"
                },
                surface_type: {
                    type: "string",
                    enum: ["cursor", "windsurf", "copilot", "antigravity"],
                    description: "IDE surface type"
                },
                profile_id: {
                    type: "string",
                    description: "Optional user profile ID (defaults to 'default-user')"
                },
                messages: {
                    type: "array",
                    description: "Conversation messages to sync",
                    items: {
                        type: "object",
                        properties: {
                            role: {
                                type: "string",
                                enum: ["user", "assistant"],
                                description: "Message role"
                            },
                            content: {
                                type: "string",
                                description: "Message content"
                            },
                            timestamp: {
                                type: "string",
                                format: "date-time",
                                description: "ISO8601 timestamp"
                            },
                            message_id: {
                                type: "string",
                                description: "IDE-assigned message ID"
                            }
                        },
                        required: ["role", "content"]
                    }
                },
                playbook_executed: {
                    type: "string",
                    description: "Playbook code if one was executed during the conversation"
                },
                ide_receipts: {
                    type: "array",
                    description: "Completion receipts for steps IDE already handled (Inv.3: Receipts over Claims)",
                    items: {
                        type: "object",
                        properties: {
                            step: {
                                type: "string",
                                enum: ["intent_extract", "steward_analyze", "project_detect"],
                                description: "Processing step completed by IDE"
                            },
                            trace_id: {
                                type: "string",
                                description: "Trace ID for this receipt"
                            },
                            output_hash: {
                                type: "string",
                                description: "SHA-256 hash of the output for verification"
                            },
                            output_summary: {
                                type: "object",
                                description: "Optional summary of IDE processing output"
                            },
                            completed_at: {
                                type: "string",
                                format: "date-time",
                                description: "When IDE completed this step"
                            }
                        },
                        required: ["step", "trace_id", "output_hash"]
                    }
                }
            },
            required: ["workspace_id", "conversation_id", "messages"]
        },
        _mindscape: {
            layer: "primitive",
            pack: "chat",
            action: "sync"
        }
    }
];

// ============================================
// Utility exports
// ============================================
export const CHAT_SYNC_TOOL_NAMES = {
    SYNC: "mindscape_chat_sync"
} as const;

export function isChatSyncTool(name: string): boolean {
    return Object.values(CHAT_SYNC_TOOL_NAMES).includes(name as any);
}
