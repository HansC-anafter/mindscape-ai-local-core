/**
 * Mind-Lens MCP Tools
 *
 * Exposes Mindscape Mind-Lens style adjustment capabilities to external AI tools.
 * Note: MCP tool names only allow [a-zA-Z0-9_-], no dots.
 */

// ============================================
// Tool Definitions
// ============================================
export const lensTools = [
    {
        name: "mindscape_lens_list_schemas",
        description: "List available Mind-Lens schemas (role templates)",
        inputSchema: {
            type: "object",
            properties: {
                role: {
                    type: "string",
                    description: "Optional: Filter schemas by role (e.g., writer, designer)"
                }
            }
        },
        _mindscape: {
            layer: "primitive",
            pack: "lens",
            action: "list_schemas"
        }
    },
    {
        name: "mindscape_lens_resolve",
        description: "Resolve Mind-Lens settings for current context (profile + workspace + session layers)",
        inputSchema: {
            type: "object",
            properties: {
                workspace_id: {
                    type: "string",
                    description: "Optional: Specify workspace ID (defaults to gateway config)"
                },
                session_id: {
                    type: "string",
                    description: "Optional: Session ID for session-level override"
                },
                role_hint: {
                    type: "string",
                    description: "Optional: Role hint (e.g., writer, designer) affects schema selection"
                }
            }
        },
        _mindscape: {
            layer: "primitive",
            pack: "lens",
            action: "resolve"
        }
    },
    {
        name: "mindscape_lens_get_effective",
        description: "Get current effective Mind-Lens (merged result: profile -> workspace -> session)",
        inputSchema: {
            type: "object",
            properties: {
                workspace_id: {
                    type: "string",
                    description: "Optional: Specify workspace ID"
                },
                session_id: {
                    type: "string",
                    description: "Optional: Session ID"
                }
            }
        },
        _mindscape: {
            layer: "primitive",
            pack: "lens",
            action: "get_effective"
        }
    }
];

// ============================================
// Tool Name Constants
// ============================================
export const LENS_TOOL_NAMES = {
    LIST_SCHEMAS: "mindscape_lens_list_schemas",
    RESOLVE: "mindscape_lens_resolve",
    GET_EFFECTIVE: "mindscape_lens_get_effective"
} as const;

export function isLensTool(name: string): boolean {
    return name.startsWith("mindscape_lens_");
}
