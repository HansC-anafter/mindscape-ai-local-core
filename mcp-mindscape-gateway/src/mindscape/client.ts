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
    const { data } = await this.client.get("/api/v1/tools", {
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
    const { data } = await this.client.get("/api/v1/playbooks", {
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
    const { data } = await this.client.get("/api/v1/capability-packs");

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
      const { data } = await this.client.get(`/api/v1/lenses/schemas/${role}`);
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
    const { data } = await this.client.get("/api/v1/mindscape/lens/effective", {
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
  }): Promise<{ intent_id?: string; seed_id?: string }> {
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
          timestamp: params.timestamp
        }
      );
      return {
        intent_id: data.intent_id,
        seed_id: data.seed_id
      };
    } catch (error: any) {
      // Re-throw to let caller handle
      throw error;
    }
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
