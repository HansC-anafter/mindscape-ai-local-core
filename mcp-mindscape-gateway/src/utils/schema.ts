/**
 * Schema utility functions
 *
 * Unified schema format for all MCP tools: {workspace_id, inputs, _context}
 */

/**
 * Context schema for external tool tracking (P3: Context Passthrough)
 */
export const CONTEXT_SCHEMA = {
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
} as const;

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
    },
    ...CONTEXT_SCHEMA
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
    },
    ...CONTEXT_SCHEMA
  },
  required: ["workspace_id", "confirm_token"]
} as const;

/**
 * Wrap tool schema options
 */
export interface WrapOptions {
  includeWorkspaceId: boolean;
  includeConfirmToken: boolean;
  includeContext?: boolean;
}

export function wrapToolSchema(
  originalSchema: Record<string, any>,
  options: WrapOptions
): Record<string, any> {
  const includeContext = options.includeContext !== false;

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
        },
        ...(includeContext ? CONTEXT_SCHEMA : {})
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
      },
      ...(includeContext ? CONTEXT_SCHEMA : {})
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
    context_recorded?: boolean;
    intent_id?: string;
    seed_id?: string;
  };
}

/**
 * Format tool result
 */
export function formatResult(result: any, toolName: string, contextInfo?: {
  context_recorded?: boolean;
  intent_id?: string;
  seed_id?: string;
}): ToolResult {
  const formatted: ToolResult = {
    status: result.status || "completed",
    inputs: result.inputs || {},
    outputs: result.outputs || result,
    logs: result.logs || [],
    _metadata: {
      tool: toolName,
      timestamp: new Date().toISOString(),
      ...contextInfo
    }
  };

  if (result.error) {
    formatted.error = typeof result.error === "string"
      ? { code: "UNKNOWN", message: result.error }
      : result.error;
  }

  return formatted;
}
