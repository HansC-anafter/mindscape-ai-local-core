/**
 * Confirm Tools - MCP tools for confirmation workflow
 *
 * Exposes confirm_request and confirm_status tools for governed operations.
 */

export const CONFIRM_TOOL_NAMES = {
    REQUEST: "mindscape_confirm_request",
    STATUS: "mindscape_confirm_status"
} as const;

export const confirmTools = [
    {
        name: CONFIRM_TOOL_NAMES.REQUEST,
        description: "Request a confirmation token for a governed operation. " +
            "Required before executing tools that modify data (delete, update, publish).",
        inputSchema: {
            type: "object",
            properties: {
                workspace_id: {
                    type: "string",
                    description: "Mindscape workspace ID"
                },
                tool_name: {
                    type: "string",
                    description: "Name of the governed tool to confirm"
                },
                action_preview: {
                    type: "string",
                    description: "Optional: Human-readable preview of the action"
                }
            },
            required: ["workspace_id", "tool_name"]
        },
        _mindscape: {
            layer: "system",
            pack: "confirm"
        }
    },
    {
        name: CONFIRM_TOOL_NAMES.STATUS,
        description: "Check the status of a confirmation token (valid/expired).",
        inputSchema: {
            type: "object",
            properties: {
                token: {
                    type: "string",
                    description: "Confirmation token to check"
                }
            },
            required: ["token"]
        },
        _mindscape: {
            layer: "system",
            pack: "confirm"
        }
    }
];

/**
 * Check if a tool name is a confirm tool.
 */
export function isConfirmTool(name: string): boolean {
    return Object.values(CONFIRM_TOOL_NAMES).includes(name as any);
}
