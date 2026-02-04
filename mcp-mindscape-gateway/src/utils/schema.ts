/**
 * Schema utility functions
 *
 * Unified schema format for all MCP tools: {workspace_id, inputs}
 */
export const UNIFIED_INPUT_SCHEMA = {
  type: "object",
  properties: {
    workspace_id: {
      type: "string",
      description: "Mindscape workspace ID (required)"
    },
    inputs: {
      type: "object",
      description: "Tool-specific parameters",
      additionalProperties: true
    }
  },
  required: ["workspace_id"]
} as const;

/**
 * Unified schema with confirm_token (for Governed tools)
 */
export const GOVERNED_INPUT_SCHEMA = {
  type: "object",
  properties: {
    workspace_id: {
      type: "string",
      description: "Mindscape workspace ID (required)"
    },
    inputs: {
      type: "object",
      description: "Tool-specific parameters",
      additionalProperties: true
    },
    confirm_token: {
      type: "string",
      description: "Confirmation token (call mindscape.confirm.request first)"
    }
  },
  required: ["workspace_id", "confirm_token"]
} as const;

/**
 * Wrap tool schema options
 */
export interface WrapOptions {
  includeWorkspaceId: boolean;
  includeConfirmToken: boolean;
}

export function wrapToolSchema(
  originalSchema: Record<string, any>,
  options: WrapOptions
): Record<string, any> {
  if (options.includeConfirmToken) {
    return {
      ...GOVERNED_INPUT_SCHEMA,
      properties: {
        ...GOVERNED_INPUT_SCHEMA.properties,
        inputs: {
          type: "object",
          description: "Tool-specific parameters",
          properties: originalSchema.properties || {},
          required: originalSchema.required || []
        }
      }
    };
  }

  return {
    ...UNIFIED_INPUT_SCHEMA,
    properties: {
      ...UNIFIED_INPUT_SCHEMA.properties,
      inputs: {
        type: "object",
        description: "Tool-specific parameters",
        properties: originalSchema.properties || {},
        required: originalSchema.required || []
      }
    }
  };
}

/**
 * Standardized result format
 */
export interface ToolResult {
  status: "completed" | "failed" | "pending" | "confirmation_required" | "timeout";
  inputs: Record<string, any>;
  outputs: Record<string, any>;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
  logs: Array<{
    level: "info" | "warn" | "error";
    message: string;
    timestamp: string;
  }>;
  _metadata?: {
    tool: string;
    timestamp: string;
  };
}

/**
 * Format tool result
 */
export function formatResult(result: any, toolName: string): ToolResult {
  const formatted: ToolResult = {
    status: result.status || "completed",
    inputs: result.inputs || {},
    outputs: result.outputs || result,
    logs: result.logs || [],
    _metadata: {
      tool: toolName,
      timestamp: new Date().toISOString()
    }
  };

  if (result.error) {
    formatted.error = typeof result.error === "string"
      ? { code: "UNKNOWN", message: result.error }
      : result.error;
  }

  return formatted;
}
