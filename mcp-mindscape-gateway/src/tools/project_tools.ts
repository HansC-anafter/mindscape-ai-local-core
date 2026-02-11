/**
 * Project Detection MCP Tools
 *
 * Tool for detecting and creating projects from IDE conversations.
 * Governed — requires confirmation token.
 */

// ============================================
// Tool Definitions
// ============================================
export const projectTools = [
    {
        name: "mindscape_project_detect_and_create",
        description: "[Governed] Detect if a message suggests a new Project, " +
            "deduplicate against existing projects, and create if unique. " +
            "Requires confirmation token.",
        inputSchema: {
            type: "object",
            properties: {
                workspace_id: {
                    type: "string",
                    description: "Target workspace ID"
                },
                message: {
                    type: "string",
                    description: "Original user message to analyze for project detection"
                },
                profile_id: {
                    type: "string",
                    description: "Optional user profile ID (defaults to 'default-user')"
                },
                confirm_token: {
                    type: "string",
                    description: "Confirmation token from mindscape.confirm.request"
                },
                detected_project: {
                    type: "object",
                    description: "IDE-detected project suggestion",
                    properties: {
                        mode: {
                            type: "string",
                            enum: ["quick_task", "micro_flow", "project"],
                            description: "Detected mode/scope"
                        },
                        project_type: {
                            type: "string",
                            description: "Project type category"
                        },
                        project_title: {
                            type: "string",
                            description: "Suggested project title"
                        },
                        playbook_sequence: {
                            type: "array",
                            items: { type: "string" },
                            description: "Suggested playbook sequence"
                        },
                        initial_spec_md: {
                            type: "string",
                            description: "Initial project specification (markdown)"
                        },
                        confidence: {
                            type: "number",
                            description: "Detection confidence 0-1"
                        }
                    },
                    required: ["project_title"]
                }
            },
            required: ["workspace_id", "message", "detected_project"]
        },
        _mindscape: {
            layer: "governed",
            pack: "project",
            action: "detect_and_create"
        }
    }
];

// ============================================
// Utility exports
// ============================================
export const PROJECT_TOOL_NAMES = {
    DETECT_AND_CREATE: "mindscape_project_detect_and_create"
} as const;

export function isProjectTool(name: string): boolean {
    return Object.values(PROJECT_TOOL_NAMES).includes(name as any);
}
