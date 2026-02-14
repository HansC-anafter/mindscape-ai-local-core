/**
 * Task Dispatch MCP Tools
 *
 * Task execution tools for Antigravity Agent.
 * Agent receives dispatched task → ack → progress* → submit_result.
 * Polling is handled by daemon processes (ide_ws_client.py / worker.py).
 */

// ============================================
// Tool Definitions
// ============================================
export const taskDispatchTools = [
    {
        name: "mindscape_task_ack",
        description: "Acknowledge task pickup and extend lease from 30s to 300s. " +
            "Must be called after receiving a dispatched task. " +
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
                    description: "Client identifier for lease tracking"
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
                    description: "Client identifier for ownership verification"
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
    }
];

// ============================================
// Utility exports
// ============================================
export const TASK_DISPATCH_TOOL_NAMES = {
    ACK: "mindscape_task_ack",
    PROGRESS: "mindscape_task_progress",
    SUBMIT_RESULT: "mindscape_task_submit_result",
} as const;

export function isTaskDispatchTool(name: string): boolean {
    return Object.values(TASK_DISPATCH_TOOL_NAMES).includes(name as any);
}
