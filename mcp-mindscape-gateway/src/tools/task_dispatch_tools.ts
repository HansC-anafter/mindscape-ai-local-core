/**
 * Task Dispatch MCP Tools
 *
 * Pull-based task runner tools for Antigravity Agent.
 * Agent calls next_task → ack → progress* → submit_result.
 */

// ============================================
// Tool Definitions
// ============================================
export const taskDispatchTools = [
    {
        name: "mindscape_task_next",
        description: "Poll for the next pending task from Mindscape backend. " +
            "Returns a task with lease_id (reserved with a short lease). " +
            "If no tasks are available, blocks for up to wait_seconds then returns empty. " +
            "After receiving a task, always call mindscape_task_ack to confirm pickup.",
        inputSchema: {
            type: "object",
            properties: {
                workspace_id: {
                    type: "string",
                    description: "Workspace ID to poll tasks from"
                },
                client_id: {
                    type: "string",
                    description: "Unique client identifier for lease tracking (e.g. 'antigravity-mcp-runner')"
                },
                limit: {
                    type: "number",
                    description: "Maximum number of tasks to reserve (default: 1)",
                    default: 1
                },
                lease_seconds: {
                    type: "number",
                    description: "Initial lease duration in seconds (default: 30). Must ack within this time.",
                    default: 30
                },
                wait_seconds: {
                    type: "number",
                    description: "Long-poll wait time in seconds (default: 5, max: 5). Blocks until a task arrives or timeout.",
                    default: 5
                }
            },
            required: ["workspace_id", "client_id"]
        },
        _mindscape: {
            layer: "primitive",
            pack: "task_dispatch",
            action: "next"
        }
    },
    {
        name: "mindscape_task_ack",
        description: "Acknowledge task pickup and extend lease from 30s to 300s. " +
            "Must be called after mindscape_task_next returns a task. " +
            "Verifies lease_id to prevent duplicate execution. Idempotent.",
        inputSchema: {
            type: "object",
            properties: {
                execution_id: {
                    type: "string",
                    description: "The execution_id from the task payload"
                },
                lease_id: {
                    type: "string",
                    description: "The lease_id from the task payload (for ownership verification)"
                },
                client_id: {
                    type: "string",
                    description: "Must match the client_id used in mindscape_task_next"
                }
            },
            required: ["execution_id", "lease_id", "client_id"]
        },
        _mindscape: {
            layer: "primitive",
            pack: "task_dispatch",
            action: "ack"
        }
    },
    {
        name: "mindscape_task_progress",
        description: "Report task execution progress and reset lease timer. " +
            "Call periodically during long tasks to prevent lease expiry. " +
            "Verifies lease_id. Max cumulative lease: 30 minutes.",
        inputSchema: {
            type: "object",
            properties: {
                execution_id: {
                    type: "string",
                    description: "The execution_id of the task"
                },
                lease_id: {
                    type: "string",
                    description: "The lease_id for ownership verification"
                },
                progress_pct: {
                    type: "number",
                    description: "Progress percentage (0-100)"
                },
                message: {
                    type: "string",
                    description: "Progress message"
                },
                client_id: {
                    type: "string",
                    description: "Client ID for ownership verification"
                }
            },
            required: ["execution_id", "lease_id"]
        },
        _mindscape: {
            layer: "primitive",
            pack: "task_dispatch",
            action: "progress"
        }
    },
    {
        name: "mindscape_task_submit_result",
        description: "Submit execution result for a completed task. " +
            "Verifies lease_id. Idempotent (second call = no-op). " +
            "Results are persisted to workspace filesystem and DB.",
        inputSchema: {
            type: "object",
            properties: {
                execution_id: {
                    type: "string",
                    description: "The execution_id from the task payload"
                },
                lease_id: {
                    type: "string",
                    description: "The lease_id for ownership verification"
                },
                status: {
                    type: "string",
                    enum: ["completed", "failed"],
                    description: "Execution outcome"
                },
                output: {
                    type: "string",
                    description: "Human-readable summary (max 500 chars, shown in Mindscape UI)"
                },
                result_json: {
                    type: "object",
                    description: "Structured result payload (persisted to result.json). Use for queryable data."
                },
                attachments: {
                    type: "array",
                    description: "Files to persist with the result",
                    items: {
                        type: "object",
                        properties: {
                            filename: { type: "string", description: "File name (e.g. 'accounts.csv')" },
                            content: { type: "string", description: "File content (text)" },
                            encoding: { type: "string", enum: ["utf-8", "base64"], description: "Encoding (default: utf-8)" }
                        },
                        required: ["filename", "content"]
                    }
                },
                error: {
                    type: "string",
                    description: "Error message if status is 'failed'"
                },
                client_id: {
                    type: "string",
                    description: "Must match the client_id used in mindscape_task_next"
                },
                duration_seconds: {
                    type: "number",
                    description: "How long the execution took in seconds"
                },
                tool_calls: {
                    type: "array",
                    description: "List of tools invoked during execution",
                    items: { type: "string" }
                },
                files_modified: {
                    type: "array",
                    description: "List of files modified",
                    items: { type: "string" }
                },
                files_created: {
                    type: "array",
                    description: "List of files created",
                    items: { type: "string" }
                }
            },
            required: ["execution_id", "lease_id", "status", "output", "client_id"]
        },
        _mindscape: {
            layer: "primitive",
            pack: "task_dispatch",
            action: "submit_result"
        }
    },
    {
        name: "mindscape_task_list_inflight",
        description: "List tasks currently reserved/inflight for this client. " +
            "Used for crash recovery: call on startup to resume where you left off.",
        inputSchema: {
            type: "object",
            properties: {
                client_id: {
                    type: "string",
                    description: "Client ID to list inflight tasks for"
                }
            },
            required: ["client_id"]
        },
        _mindscape: {
            layer: "primitive",
            pack: "task_dispatch",
            action: "list_inflight"
        }
    }
];

// ============================================
// Utility exports
// ============================================
export const TASK_DISPATCH_TOOL_NAMES = {
    NEXT: "mindscape_task_next",
    ACK: "mindscape_task_ack",
    PROGRESS: "mindscape_task_progress",
    SUBMIT_RESULT: "mindscape_task_submit_result",
    LIST_INFLIGHT: "mindscape_task_list_inflight"
} as const;

export function isTaskDispatchTool(name: string): boolean {
    return Object.values(TASK_DISPATCH_TOOL_NAMES).includes(name as any);
}
