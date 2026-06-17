import type {
  FilteredToolsResponse,
  Pack,
  Playbook,
  Tool,
  ToolResult,
} from "./client_types.js";

const KNOWN_CAPABILITY_PACKS = ["wordpress", "creative", "seo", "analytics", "system"];

export function inferPack(toolId: string, provider?: string): string | undefined {
  if (toolId.includes(".")) {
    return toolId.split(".")[0];
  }
  if (provider === "capability") {
    for (const pack of KNOWN_CAPABILITY_PACKS) {
      if (toolId.startsWith(pack)) {
        return pack;
      }
    }
  }
  return undefined;
}

export function mapTool(t: any): Tool {
  return {
    name: t.tool_id,
    description: t.description || "",
    pack: inferPack(t.tool_id, t.provider),
    danger_level: (t.danger_level || "safe") as "safe" | "moderate" | "high",
    requires_governance: t.danger_level === "high",
    input_schema: t.input_schema || {},
  };
}

export function mapPlaybook(p: any): Playbook {
  return {
    playbook_code: p.playbook_code,
    display_name: p.display_name || p.playbook_code,
    description: p.description || "",
    capability: p.capability,
    pack: p.capability,
    input_schema: p.input_schema || {},
  };
}

export function mapFilteredPlaybook(p: any): Playbook {
  return {
    playbook_code: p.playbook_code,
    display_name: p.display_name || p.playbook_code,
    description: p.description || "",
    capability: p.capability_code || p.capability || "",
    pack: p.capability_code || p.capability,
    input_schema: p.input_schema || {},
  };
}

export function mapPack(p: any): Pack {
  return {
    code: p.id,
    display_name: p.name,
    description: p.description || "",
    version: p.version || "1.0.0",
  };
}

export function mapFilteredToolsResponse(data: any): FilteredToolsResponse {
  const tools: Tool[] = (data.tools || []).map(mapTool);
  const playbooks: Playbook[] = (data.playbooks || []).map(mapFilteredPlaybook);

  return {
    tools,
    playbooks,
    meta: data.meta || {
      tool_count: tools.length,
      playbook_count: playbooks.length,
      rag_status: "skipped" as const,
      pack_codes: [],
      safe_default_used: false,
    },
  };
}

export function formatToolResult(backendResult: any, toolName: string): ToolResult {
  return {
    status: backendResult.success ? "completed" : "failed",
    inputs: {},
    outputs: backendResult.result || {},
    error: backendResult.error ? {
      code: "EXECUTION_ERROR",
      message: backendResult.error,
    } : undefined,
    logs: [],
    _metadata: {
      tool: toolName,
      timestamp: new Date().toISOString(),
    },
  };
}
