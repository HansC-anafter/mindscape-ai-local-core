export interface Tool {
  name: string;
  description: string;
  pack?: string;
  danger_level?: "safe" | "moderate" | "high";
  requires_governance?: boolean;
  input_schema: Record<string, any>;
}

export interface Playbook {
  playbook_code: string;
  display_name: string;
  description: string;
  capability: string;
  pack?: string;
  input_schema?: Record<string, any>;
}

export interface Pack {
  code: string;
  display_name: string;
  description: string;
  version: string;
}

export interface PlaybookExecutionResult {
  execution_id: string;
  status: "completed" | "failed" | "running" | "pending";
  outputs?: Record<string, any>;
  error?: string;
}

export interface FilteredToolsMeta {
  tool_count: number;
  playbook_count: number;
  rag_status: "hit" | "miss" | "error" | "skipped";
  pack_codes: string[];
  safe_default_used: boolean;
}

export interface FilteredToolsResponse {
  tools: Tool[];
  playbooks: Playbook[];
  meta: FilteredToolsMeta;
}

export interface ToolResult {
  status: "completed" | "failed" | "pending" | "confirmation_required";
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
