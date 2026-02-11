/**
 * Intent MCP Tools
 *
 * Tools for submitting IDE-extracted intents and executing IntentLayoutPlans.
 * Naming: mindscape_intent_* (three-layer naming convention)
 */

// ============================================
// Tool Definitions
// ============================================
export const intentTools = [
    {
        name: "mindscape_intent_submit",
        description: "Submit IDE-extracted intents to Workspace. " +
            "Creates IntentTag entries with source=IDE. " +
            "The WS-side IntentExtractor is skipped (IDE already did extraction).",
        inputSchema: {
            type: "object",
            properties: {
                workspace_id: {
                    type: "string",
                    description: "Target workspace ID"
                },
                message: {
                    type: "string",
                    description: "Original user message that was analyzed"
                },
                message_id: {
                    type: "string",
                    description: "ID of the source message (from IDE)"
                },
                profile_id: {
                    type: "string",
                    description: "Optional user profile ID (defaults to 'default-user')"
                },
                extracted_intents: {
                    type: "array",
                    description: "Intents extracted by IDE LLM",
                    items: {
                        type: "object",
                        properties: {
                            label: { type: "string", description: "Intent label" },
                            confidence: { type: "number", description: "Confidence 0-1" },
                            source: { type: "string", description: "Source identifier" },
                            metadata: { type: "object", description: "Additional metadata" }
                        },
                        required: ["label"]
                    }
                },
                extracted_themes: {
                    type: "array",
                    items: { type: "string" },
                    description: "Optional themes extracted from the conversation"
                }
            },
            required: ["workspace_id", "message", "extracted_intents"]
        },
        _mindscape: {
            layer: "primitive",
            pack: "intent",
            action: "submit"
        }
    },
    {
        name: "mindscape_intent_layout_execute",
        description: "[Governed] Execute an IntentLayoutPlan — create/update/archive IntentCards. " +
            "Requires confirmation token. Use mindscape.confirm.request first.",
        inputSchema: {
            type: "object",
            properties: {
                workspace_id: {
                    type: "string",
                    description: "Target workspace ID"
                },
                profile_id: {
                    type: "string",
                    description: "Optional user profile ID (defaults to 'default-user')"
                },
                confirm_token: {
                    type: "string",
                    description: "Confirmation token from mindscape.confirm.request"
                },
                layout_plan: {
                    type: "object",
                    description: "IntentLayoutPlan to execute",
                    properties: {
                        long_term_intents: {
                            type: "array",
                            description: "IntentCard create/update operations",
                            items: {
                                type: "object",
                                properties: {
                                    operation_type: {
                                        type: "string",
                                        enum: ["CREATE_INTENT_CARD", "UPDATE_INTENT_CARD", "ARCHIVE"],
                                        description: "Operation type"
                                    },
                                    intent_id: {
                                        type: "string",
                                        description: "Existing IntentCard ID (required for UPDATE/ARCHIVE)"
                                    },
                                    intent_data: {
                                        type: "object",
                                        description: "Intent data (title, description, priority, status, tags)",
                                        properties: {
                                            title: { type: "string" },
                                            description: { type: "string" },
                                            priority: { type: "string", enum: ["high", "medium", "low"] },
                                            status: { type: "string" },
                                            tags: { type: "array", items: { type: "string" } }
                                        }
                                    },
                                    confidence: { type: "number", description: "Operation confidence 0-1" },
                                    reasoning: { type: "string", description: "Reasoning for this operation" }
                                },
                                required: ["operation_type", "intent_data"]
                            }
                        },
                        ephemeral_tasks: {
                            type: "array",
                            description: "Short-lived tasks that don't warrant an IntentCard",
                            items: {
                                type: "object",
                                properties: {
                                    signal_id: { type: "string" },
                                    title: { type: "string" },
                                    description: { type: "string" },
                                    reasoning: { type: "string" }
                                },
                                required: ["title"]
                            }
                        }
                    },
                    required: ["long_term_intents"]
                }
            },
            required: ["workspace_id", "layout_plan"]
        },
        _mindscape: {
            layer: "governed",
            pack: "intent",
            action: "layout_execute"
        }
    }
];

// ============================================
// Utility exports
// ============================================
export const INTENT_TOOL_NAMES = {
    SUBMIT: "mindscape_intent_submit",
    LAYOUT_EXECUTE: "mindscape_intent_layout_execute"
} as const;

export function isIntentTool(name: string): boolean {
    return Object.values(INTENT_TOOL_NAMES).includes(name as any);
}
