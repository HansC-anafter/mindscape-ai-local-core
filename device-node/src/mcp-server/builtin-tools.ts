import { filesystemList, filesystemRead, filesystemWrite } from "../capabilities/filesystem.js";
import { shellExecute } from "../capabilities/shell.js";
import { captureRelayControl } from "../capabilities/capture-relay-control.js";
import { hostResourceProbe } from "../capabilities/host-resource-probe.js";
import { hostResourceLaneWorkersSet } from "../capabilities/host-resource-lane-workers.js";
import { hostResourceRunnerSpilloverControl } from "../capabilities/host-resource-runner-spillover.js";
import { cliBridgeServiceControl } from "../capabilities/cli-bridge-service-control.js";
import { hostOpenDocument } from "../capabilities/host-open-document.js";
import { TrustLevel } from "../governance/permission-map.js";
import type { ToolDefinition } from "./tool-definition.js";
import { hostRuntimeExecute } from "../host-runtime-runner.js";
import type { PermissionMap } from "../governance/permission-map.js";
import { reconcileHostRuntimeBinding } from "../services/host-runtime-reconciliation.js";

export function createBuiltinTools(permissionMap?: PermissionMap): ToolDefinition[] {
    return [
        {
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
        },
        {
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
        },
        {
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
        },
        {
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
                    timeout_ms: {
                        type: "number",
                        description: "Execution timeout in milliseconds (optional, capped by device-node)",
                    },
                },
                required: ["command"],
            },
            handler: shellExecute,
            trustLevel: TrustLevel.EXECUTE,
        },
        {
            name: "host_runtime_attest",
            description: "Read and attest one immutable device host runtime binding",
            inputSchema: {
                type: "object",
                properties: {
                    binding_id: { type: "string" },
                    generation: { type: "integer", minimum: 1 },
                    capability_code: { type: "string" },
                    requirement_code: { type: "string" },
                    capability_version: { type: "string" },
                    operations: {
                        type: "array",
                        items: {
                            type: "string",
                            pattern: "^[a-z][a-z0-9_.-]{1,63}$",
                        },
                        minItems: 1,
                        uniqueItems: true,
                    },
                    materialized_root: { type: "string" },
                    entrypoint: { type: "string" },
                    entrypoint_digest: { type: "string" },
                    host_assets_digest: { type: "string" },
                    runtime_digest: { type: "string" },
                    permission_classes: {
                        type: "array",
                        items: { type: "string" },
                        minItems: 1,
                        uniqueItems: true,
                    },
                    resource_lane: { type: "string" },
                },
                required: [
                    "binding_id",
                    "generation",
                    "capability_code",
                    "requirement_code",
                    "capability_version",
                    "operations",
                    "materialized_root",
                    "entrypoint",
                    "entrypoint_digest",
                    "host_assets_digest",
                    "runtime_digest",
                    "permission_classes",
                    "resource_lane",
                ],
                additionalProperties: false,
            },
            handler: (args) => reconcileHostRuntimeBinding(
                args,
                {
                    allowedPermissionClasses:
                        permissionMap?.allowedPermissionClasses("host_runtime_attest")
                        ?? new Set<string>(),
                    pythonExecutable:
                        process.env.MINDSCAPE_HOST_RUNTIME_PYTHON
                        || "/usr/bin/python3",
                },
            ),
            trustLevel: TrustLevel.READ,
        },
        {
            name: "host_runtime_execute",
            description: "Execute one receipt-bound immutable host runtime operation",
            inputSchema: {
                type: "object",
                properties: {
                    operation: {
                        type: "string",
                        pattern: "^[a-z][a-z0-9_.-]{1,63}$",
                    },
                    operation_args: {
                        type: "array",
                        items: { type: "string" },
                        maxItems: 64,
                    },
                    permit: {
                        type: "object",
                        description: "Short-lived Local Core signed admission envelope",
                    },
                },
                required: ["operation", "operation_args", "permit"],
                additionalProperties: false,
            },
            handler: (args) => hostRuntimeExecute(
                args,
                permissionMap?.allowedPermissionClasses("host_runtime_execute")
                ?? new Set<string>(),
            ),
            trustLevel: TrustLevel.EXECUTE,
        },
        {
            name: "host_resource_probe",
            description: "Read host resource pressure and selected runtime processes",
            inputSchema: {
                type: "object",
                properties: {
                    timeout_ms: {
                        type: "number",
                        description: "Per-command timeout in milliseconds (optional, capped by device-node)",
                    },
                },
            },
            handler: hostResourceProbe,
            trustLevel: TrustLevel.READ,
        },
        {
            name: "capture_relay_control",
            description: "Control the canonical host media relay and supervised receiver",
            inputSchema: {
                type: "object",
                properties: {
                    action: {
                        type: "string",
                        enum: ["status", "install_mediamtx", "start", "stop", "open_obs", "configure_obs", "receiver_start", "receiver_status", "receiver_stop"],
                        description: "Relay helper action",
                    },
                    stream_name: {
                        type: "string",
                        description: "Neutral stream path name",
                    },
                    scene_name: {
                        type: "string",
                        description: "Optional OBS scene name to create or update",
                    },
                    source_name: {
                        type: "string",
                        description: "Optional OBS media source name to create or update",
                    },
                    rtmp_port: {
                        type: "number",
                        description: "RTMP publish port",
                    },
                    rtsp_port: {
                        type: "number",
                        description: "RTSP read port",
                    },
                    open_obs: {
                        type: "boolean",
                        description: "Open OBS after starting the relay",
                    },
                    start_virtual_camera: {
                        type: "boolean",
                        description: "Attempt to start OBS Virtual Camera after OBS setup",
                    },
                    install_method: {
                        type: "string",
                        enum: ["homebrew"],
                        description: "Explicit host install method for relay dependencies",
                    },
                    timeout_ms: {
                        type: "number",
                        description: "Bounded relay readiness wait",
                    },
                    receiver_descriptor: {
                        type: "object",
                        description: "Server-issued live media receiver descriptor",
                    },
                    media_session_id: {
                        type: "string",
                        description: "Live media session identity for receiver status or stop",
                    },
                    receiver_identity: {
                        type: "string",
                        description: "Server-issued receiver ownership identity",
                    },
                },
            },
            handler: captureRelayControl,
            trustLevel: TrustLevel.EXECUTE,
        },
        {
            name: "host_resource_lane_workers_set",
            description: "Set dynamic host resource lane worker target",
            inputSchema: {
                type: "object",
                properties: {
                    lane_id: { type: "string", description: "Host resource lane id" },
                    desired_worker_count: { type: "number", description: "Desired worker count" },
                    queue_shard: { type: "string", description: "Target runner queue shard" },
                    runner_profile: { type: "string", description: "Runner profile hint" },
                    resource_class: { type: "string", description: "Resource class" },
                    worker_env: {
                        type: "object",
                        description: "Environment values for a managed worker",
                    },
                },
                required: ["lane_id", "desired_worker_count"],
            },
            handler: hostResourceLaneWorkersSet,
            trustLevel: TrustLevel.EXECUTE,
        },
        {
            name: "host_resource_runner_spillover_control",
            description: "Control the fixed runner-spillover compose service",
            inputSchema: {
                type: "object",
                properties: {
                    action: {
                        type: "string",
                        enum: ["status", "start", "stop"],
                        description: "Spillover action",
                    },
                    profile_code: {
                        type: "string",
                        description:
                            "Built-in runner profile or a custom profile code for spillover start/status context",
                    },
                    max_inflight: {
                        type: "number",
                        description: "Bounded max inflight for start, clamped to 1-4",
                    },
                    accepted_partitions: {
                        type: "string",
                        description:
                            "Required for custom profiles; comma-separated queue partitions",
                    },
                    accepted_resource_classes: {
                        type: "string",
                        description:
                            "Required for custom profiles; comma-separated resource classes",
                    },
                    accepted_capability_codes: {
                        type: "string",
                        description:
                            "Required for custom profiles; comma-separated capability codes",
                    },
                    runtime_endpoint: {
                        type: "string",
                        description:
                            "Required for custom profiles; runtime base URL exposed to the runner",
                    },
                    runtime_id: {
                        type: "string",
                        description: "Optional runtime identifier override",
                    },
                    runtime_model: {
                        type: "string",
                        description: "Optional runtime model override",
                    },
                    runtime_max_output_tokens: {
                        type: "string",
                        description: "Optional runtime max output token cap",
                    },
                    runtime_context_budget_tokens: {
                        type: "string",
                        description: "Optional runtime context budget token cap",
                    },
                    display_name: {
                        type: "string",
                        description: "Optional runner display name override",
                    },
                    db_application_name: {
                        type: "string",
                        description: "Optional PostgreSQL application_name override",
                    },
                },
            },
            handler: hostResourceRunnerSpilloverControl,
            trustLevel: TrustLevel.EXECUTE,
        },
        {
            name: "cli_bridge_service_control",
            description: "Read or start the fixed Mindscape CLI bridge LaunchAgent",
            inputSchema: {
                type: "object",
                properties: {
                    action: {
                        type: "string",
                        enum: ["status", "start", "restart"],
                        description: "LaunchAgent action",
                    },
                },
            },
            handler: cliBridgeServiceControl,
            trustLevel: TrustLevel.EXECUTE,
        },
        {
            name: "host_open_document",
            description: "Open a governed host document in a native desktop app",
            inputSchema: {
                type: "object",
                properties: {
                    path: { type: "string", description: "Absolute host document path" },
                    app_name: { type: "string", description: "Native app name" },
                    timeout_ms: {
                        type: "number",
                        description: "Open command timeout in milliseconds",
                    },
                },
                required: ["path"],
            },
            handler: hostOpenDocument,
            trustLevel: TrustLevel.EXECUTE,
        },
    ];
}
