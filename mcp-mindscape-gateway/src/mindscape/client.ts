/**
 * MindscapeClient - v1.4 Backend API Adapter
 *
 * Adapts to existing backend API format without backend modifications.
 */
import axios, { AxiosInstance } from "axios";
import { config } from "../config.js";

// ============================================
// Type Definitions
// ============================================
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

// ============================================
// MindscapeClient
// ============================================
export class MindscapeClient {
  private client: AxiosInstance;
  private profileId: string;

  constructor(customConfig?: Partial<typeof config>) {
    this.profileId = customConfig?.profileId || config.profileId;
    this.client = axios.create({
      baseURL: customConfig?.mindscapeBaseUrl || config.mindscapeBaseUrl,
      timeout: customConfig?.timeout || config.timeout || 30000,
      maxRedirects: 5,
      headers: customConfig?.apiKey
        ? { "Authorization": `Bearer ${customConfig.apiKey}` }
        : {}
    });
  }

  // ============================================
  // Tools API - GET /api/v1/tools
  // ============================================
  async listTools(params?: {
    site_id?: string;
    category?: string;
    enabled_only?: boolean;
  }): Promise<Tool[]> {
    const { data } = await this.client.get("/api/v1/tools/", {
      params: {
        site_id: params?.site_id,
        category: params?.category,
        enabled_only: params?.enabled_only ?? true
      }
    });

    return (Array.isArray(data) ? data : []).map((t: any) => ({
      name: t.tool_id,
      description: t.description || "",
      pack: this._inferPack(t.tool_id, t.provider),
      danger_level: (t.danger_level || "safe") as "safe" | "moderate" | "high",
      requires_governance: t.danger_level === "high",
      input_schema: t.input_schema || {}
    }));
  }

  /**
   * Fetch filtered tools via server-side RAG + safe defaults.
   * Replaces client-side pack filtering.
   */
  async fetchFilteredTools(params: {
    task_hint?: string;
    max_tools?: number;
    include_playbooks?: boolean;
    enabled_only?: boolean;
  }): Promise<FilteredToolsResponse> {
    const { data } = await this.client.post("/api/v1/tools/filtered", {
      task_hint: params.task_hint || "",
      max_tools: params.max_tools || 30,
      include_playbooks: params.include_playbooks ?? true,
      enabled_only: params.enabled_only ?? true,
    });

    const tools: Tool[] = (data.tools || []).map((t: any) => ({
      name: t.tool_id,
      description: t.description || "",
      pack: this._inferPack(t.tool_id, t.provider),
      danger_level: (t.danger_level || "safe") as "safe" | "moderate" | "high",
      requires_governance: t.danger_level === "high",
      input_schema: t.input_schema || {},
    }));

    const playbooks: Playbook[] = (data.playbooks || []).map((p: any) => ({
      playbook_code: p.playbook_code,
      display_name: p.display_name || p.playbook_code,
      description: p.description || "",
      capability: p.capability_code || p.capability || "",
      pack: p.capability_code || p.capability,
      input_schema: p.input_schema || {},
    }));

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

  async executeTool(toolName: string, args: Record<string, any>): Promise<ToolResult> {
    const { data } = await this.client.post(
      "/api/v1/tools/execute",
      {
        tool_name: toolName,
        arguments: args
      },
      {
        params: { profile_id: this.profileId }
      }
    );

    return this._formatToolResult(data, toolName);
  }

  // ============================================
  // Playbooks API - GET /api/v1/playbooks
  // ============================================
  async listPlaybooks(params?: {
    scope?: string;
    profile_id?: string;
    workspace_id?: string;
  }): Promise<Playbook[]> {
    const { data } = await this.client.get("/api/v1/playbooks/", {
      params: {
        scope: params?.scope || "system",
        profile_id: params?.profile_id || this.profileId,
        workspace_id: params?.workspace_id
      }
    });

    return (Array.isArray(data) ? data : []).map((p: any) => ({
      playbook_code: p.playbook_code,
      display_name: p.display_name || p.playbook_code,
      description: p.description || "",
      capability: p.capability,
      pack: p.capability,
      input_schema: p.input_schema || {}
    }));
  }

  async executePlaybook(
    playbookCode: string,
    workspaceId: string,
    inputs: Record<string, any>
  ): Promise<PlaybookExecutionResult> {
    const { data } = await this.client.post(
      "/api/v1/playbooks/execute/start",
      { inputs },
      {
        params: {
          playbook_code: playbookCode,
          profile_id: this.profileId,
          workspace_id: workspaceId
        }
      }
    );

    return {
      execution_id: data.execution_id,
      status: data.execution_mode === "conversation" ? "running" : "completed",
      outputs: data.result || {},
      error: data.error
    };
  }

  // ============================================
  // Packs API - GET /api/v1/capability-packs
  // ============================================
  async listPacks(): Promise<Pack[]> {
    const { data } = await this.client.get("/api/v1/capability-packs/");

    return (Array.isArray(data) ? data : []).map((p: any) => ({
      code: p.id,
      display_name: p.name,
      description: p.description || "",
      version: p.version || "1.0.0"
    }));
  }

  // ============================================
  // Execution API - GET /api/v1/playbooks/execute/{id}/result
  // ============================================
  async getExecutionStatus(executionId: string): Promise<any> {
    try {
      const { data } = await this.client.get(
        `/api/v1/playbooks/execute/${executionId}/result`
      );

      return {
        execution_id: executionId,
        status: data.status || "completed",
        outputs: data,
        error: data.error
      };
    } catch (error: any) {
      if (error.response?.status === 404) {
        return {
          execution_id: executionId,
          status: "running",
          message: "Execution in progress"
        };
      }
      throw error;
    }
  }

  // ============================================
  // Workspace API - For Auto-Provision
  // ============================================
  async findWorkspaceByTitle(title: string, ownerId: string): Promise<{ id: string; title: string } | null> {
    try {
      const { data } = await this.client.get("/api/v1/workspaces/", {
        params: { owner_user_id: ownerId }
      });

      const workspaces = Array.isArray(data) ? data : [];
      const found = workspaces.find((ws: any) => ws.title === title);

      if (found) {
        return {
          id: found.id,
          title: found.title
        };
      }
      return null;
    } catch (error: any) {
      console.error("[MindscapeClient] Failed to find workspace:", error.message);
      return null;
    }
  }

  async createWorkspace(params: {
    title: string;
    owner_user_id: string;
    description?: string;
  }): Promise<{ id: string; title: string }> {
    const { data } = await this.client.post(
      "/api/v1/workspaces/",
      {
        title: params.title,
        description: params.description
      },
      {
        params: { owner_user_id: params.owner_user_id }
      }
    );

    return {
      id: data.id,
      title: data.title
    };
  }

  // ============================================
  // Lens API - Mind-Lens Style Adjustment
  // ============================================

  /**
   * Get Lens schema for a specific role
   */
  async getLensSchema(role: string): Promise<any> {
    try {
      const { data } = await this.client.get(`/api/v1/lenses/schemas/${role}/`);
      return data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  }

  /**
   * Resolve Mind-Lens (core API)
   */
  async resolveLens(params: {
    user_id: string;
    workspace_id: string;
    playbook_id?: string;
    role_hint?: string;
  }): Promise<any> {
    const { data } = await this.client.post("/api/v1/lenses/resolve", params);
    return data;
  }

  /**
   * Get effective Mind-Lens (three-layer merge)
   */
  async getEffectiveLens(params: {
    profile_id: string;
    workspace_id?: string;
    session_id?: string;
  }): Promise<any> {
    const { data } = await this.client.get("/api/v1/mindscape/lens/effective/", {
      params: {
        profile_id: params.profile_id,
        workspace_id: params.workspace_id,
        session_id: params.session_id
      }
    });
    return data;
  }

  // ============================================
  // External Context API - For Context Passthrough (P3)
  // ============================================

  /**
   * Record external context for intent/seed tracking
   */
  async recordExternalContext(params: {
    workspace_id: string;
    surface_type: string;
    surface_user_id: string;
    original_message?: string;
    tool_called: string;
    conversation_id?: string;
    intent_hint?: string;
    timestamp: string;
    ide_receipts?: Array<{
      action: string;
      trace_id: string;
      output_hash?: string;
      timestamp?: string;
    }>;
  }): Promise<{ intent_id?: string; seed_id?: string; ide_receipt_used?: boolean }> {
    try {
      const { data } = await this.client.post(
        "/api/v1/surfaces/external-context",
        {
          workspace_id: params.workspace_id,
          surface_type: params.surface_type,
          surface_user_id: params.surface_user_id,
          original_message: params.original_message,
          tool_called: params.tool_called,
          conversation_id: params.conversation_id,
          intent_hint: params.intent_hint,
          timestamp: params.timestamp,
          ide_receipts: params.ide_receipts
        }
      );
      return {
        intent_id: data.intent_id,
        seed_id: data.seed_id,
        ide_receipt_used: data.ide_receipt_used
      };
    } catch (error: any) {
      // Re-throw to let caller handle
      throw error;
    }
  }

  // ============================================
  // MCP Bridge Methods
  // ============================================

  async submitIntents(params: {
    workspace_id: string;
    message: string;
    message_id?: string;
    profile_id?: string;
    extracted_intents: Array<{ label: string; confidence?: number; source?: string; metadata?: any }>;
    extracted_themes?: string[];
  }): Promise<{ intent_tags_created: number; themes_recorded: number; tags: any[] }> {
    const { data } = await this.client.post("/api/v1/mcp/intent/submit", params);
    return data;
  }

  async executeIntentLayout(params: {
    workspace_id: string;
    profile_id?: string;
    layout_plan: {
      long_term_intents: Array<{
        operation_type: string;
        intent_id?: string;
        intent_data: Record<string, any>;
        relation_signals?: string[];
        confidence?: number;
        reasoning?: string;
      }>;
      ephemeral_tasks?: Array<Record<string, any>>;
    };
  }): Promise<{ success: boolean; executed: number; operations: any[]; turn_id: string }> {
    const { data } = await this.client.post("/api/v1/mcp/intent/layout/execute", params);
    return data;
  }

  async chatSync(params: {
    workspace_id: string;
    conversation_id: string;
    surface_type?: string;
    trace_id?: string;
    profile_id?: string;
    messages: Array<{ role: string; content: string; timestamp?: string; message_id?: string }>;
    playbook_executed?: string;
    ide_receipts?: Array<{ step: string; trace_id: string; output_hash: string; output_summary?: any; completed_at?: string }>;
  }): Promise<{ synced: boolean; trace_id: string; thread_id: string; events_emitted: string[]; hooks_triggered: string[]; ide_receipts_applied: string[] }> {
    const { data } = await this.client.post("/api/v1/mcp/chat/sync", params);
    return data;
  }

  async detectAndCreateProject(params: {
    workspace_id: string;
    message: string;
    profile_id?: string;
    detected_project: {
      mode?: string;
      project_type?: string;
      project_title: string;
      playbook_sequence?: string[];
      initial_spec_md?: string;
      confidence?: number;
    };
  }): Promise<{ project_id?: string; created: boolean; reason?: string }> {
    const { data } = await this.client.post("/api/v1/mcp/project/detect", params);
    return data;
  }

  // ============================================
  // Helper Methods
  // ============================================
  private _inferPack(toolId: string, provider: string): string | undefined {
    if (toolId.includes(".")) {
      return toolId.split(".")[0];
    }
    if (provider === "capability") {
      const knownPacks = ["wordpress", "creative", "seo", "analytics", "system"];
      for (const pack of knownPacks) {
        if (toolId.startsWith(pack)) {
          return pack;
        }
      }
    }
    return undefined;
  }

  private _formatToolResult(backendResult: any, toolName: string): ToolResult {
    return {
      status: backendResult.success ? "completed" : "failed",
      inputs: {},
      outputs: backendResult.result || {},
      error: backendResult.error ? {
        code: "EXECUTION_ERROR",
        message: backendResult.error
      } : undefined,
      logs: [],
      _metadata: {
        tool: toolName,
        timestamp: new Date().toISOString()
      }
    };
  }
}
