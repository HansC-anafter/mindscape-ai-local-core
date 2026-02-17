/**
 * Mindscape Gateway MCP Server
 *
 * MVP: tools/list + tools/call + three-layer naming + Access Policy
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema
} from "@modelcontextprotocol/sdk/types.js";
import { MindscapeClient } from "./mindscape/client.js";
import { PlaybookMapper } from "./mindscape/playbook_mapper.js";
import { WorkspaceProvisioner } from "./mindscape/workspace_provisioner.js";
import { ToolNameResolver } from "./utils/tool_name_resolver.js";
import { toolAccessPolicy } from "./policy/tool_access_policy.js";
import { wrapToolSchema, formatResult } from "./utils/schema.js";
import { lensTools, isLensTool, LENS_TOOL_NAMES } from "./tools/lens_tools.js";
import { confirmTools, isConfirmTool, CONFIRM_TOOL_NAMES } from "./tools/confirm_tools.js";
import { intentTools, isIntentTool, INTENT_TOOL_NAMES } from "./tools/intent_tools.js";
import { chatSyncTools, isChatSyncTool, CHAT_SYNC_TOOL_NAMES } from "./tools/chat_sync_tools.js";
import { projectTools, isProjectTool, PROJECT_TOOL_NAMES } from "./tools/project_tools.js";
import { ContextHandler } from "./context_handler.js";
import { ConfirmGuard } from "./confirm_guard.js";
import { config } from "./config.js";

const server = new Server(
  {
    name: "mindscape-gateway",
    version: "1.0.0"
  },
  {
    capabilities: {
      tools: {},
      experimental: {
        sampling: {}  // Phase 3: Enable server-initiated LLM calls via createMessage
      }
    }
  }
);

const mindscapeClient = new MindscapeClient();
const toolNameResolver = new ToolNameResolver();
const playbookMapper = new PlaybookMapper(mindscapeClient, toolNameResolver);
const workspaceProvisioner = new WorkspaceProvisioner(mindscapeClient);
const contextHandler = new ContextHandler(mindscapeClient);
const confirmGuard = new ConfirmGuard(mindscapeClient);

mindscapeClient.listPacks().then(packs => {
  toolNameResolver.updateKnownPacks(packs.map(p => p.code));
}).catch(err => {
  console.warn("Failed to load packs for ToolNameResolver:", err);
});

// ============================================
// tools/list - List tools (three-layer naming + Access Policy)
// ============================================
server.setRequestHandler(ListToolsRequestSchema, async () => {
  try {
    // Parallel fetch to stay within Gemini CLI's MCP discovery timeout
    const [tools, playbooks, packs] = await Promise.all([
      mindscapeClient.listTools({ enabled_only: true }),
      mindscapeClient.listPlaybooks({ scope: "system" }),
      mindscapeClient.listPacks()
    ]);

    toolNameResolver.updateKnownPacks(packs.map(p => p.code));

    const mcpTools: any[] = [];
    const wl = config.packWhitelist; // per-task pack filter

    // ============================================
    // Layer 2: Macro Tools (Playbooks)
    // ============================================
    for (const pb of playbooks) {
      // Skip playbooks outside pack whitelist when filtering is active
      if (wl.length > 0 && pb.capability && !wl.includes(pb.capability)) {
        continue;
      }
      const mcpTool = playbookMapper.toMcpTool(pb);
      const decision = toolAccessPolicy.getAccessLevel(mcpTool.name);

      if (decision.allowed) {
        mcpTools.push(mcpTool);
      }
    }

    // ============================================
    // Mind-Lens Tools (Built-in)
    // ============================================
    for (const lensTool of lensTools) {
      mcpTools.push(lensTool);
    }

    // ============================================
    // Confirm Tools (Built-in)
    // ============================================
    for (const confirmTool of confirmTools) {
      mcpTools.push(confirmTool);
    }

    // ============================================
    // MCP Bridge Tools (Intent, Chat Sync, Project)
    // ============================================
    for (const tool of [...intentTools, ...chatSyncTools, ...projectTools]) {
      const decision = toolAccessPolicy.getAccessLevel(tool.name);
      if (decision.allowed) {
        mcpTools.push(tool);
      }
    }

    // ============================================
    // Layer 1 & 3: Primitive / Governed Tools
    // ============================================
    for (const tool of tools) {
      const identity = toolNameResolver.resolve({
        name: tool.name,
        pack: tool.pack,
        provider: "capability"
      });

      // Skip pack tools outside whitelist when filtering is active
      if (wl.length > 0 && identity.pack && !wl.includes(identity.pack)) {
        continue;
      }

      const primitiveName = toolNameResolver.toMcpName(identity, "tool");
      const decision = toolAccessPolicy.getAccessLevel(primitiveName);

      if (!decision.allowed) {
        continue;
      }

      if (decision.level === "primitive") {
        mcpTools.push({
          name: primitiveName,
          description: `[Primitive] ${tool.description}`,
          inputSchema: wrapToolSchema(tool.input_schema || {}, {
            includeWorkspaceId: true,
            includeConfirmToken: false
          }),
          _mindscape: {
            layer: "primitive",
            pack: identity.pack,
            action: identity.action,
            danger_level: tool.danger_level || "safe"
          }
        });
      } else {
        const governedName = toolNameResolver.toMcpName(identity, "run");
        mcpTools.push({
          name: governedName,
          description: `[Governed] ${tool.description} - Requires confirmation`,
          inputSchema: wrapToolSchema(tool.input_schema || {}, {
            includeWorkspaceId: true,
            includeConfirmToken: true
          }),
          _mindscape: {
            layer: "governed",
            pack: identity.pack,
            action: identity.action,
            danger_level: "high",
            requires_confirmation: decision.constraints?.requiresConfirmation,
            requires_preview: decision.constraints?.requiresPreview
          }
        });
      }
    }

    if (wl.length > 0) {
      console.error(`Pack whitelist active: [${wl.join(", ")}] → ${mcpTools.length} tools served`);
    }

    return { tools: mcpTools };
  } catch (error: any) {
    console.error("Error listing tools:", error);
    throw error;
  }
});

// ============================================
// tools/call - Execute tool (Access Policy check)
// ============================================
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args = {} } = request.params;

  try {
    const accessDecision = toolAccessPolicy.getAccessLevel(name);
    if (!accessDecision.allowed) {
      throw new Error(`Access denied: ${accessDecision.reason}`);
    }

    let workspaceId: string;
    try {
      workspaceId = await workspaceProvisioner.resolveWorkspace({
        workspace_id: args.workspace_id ? String(args.workspace_id) : undefined,
        surface_user_id: args.surface_user_id ? String(args.surface_user_id) : undefined,
        surface_type: args.surface_type ? String(args.surface_type) : undefined
      });
    } catch (provisionError: any) {
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            status: "failed",
            error: {
              code: "WORKSPACE_PROVISION_ERROR",
              message: provisionError.message
            }
          }, null, 2)
        }],
        isError: true
      };
    }

    const inputs = args.inputs || args;
    const confirmToken = args.confirm_token ? String(args.confirm_token) : undefined;
    const externalContext = ContextHandler.extractContext(args as Record<string, any>);

    // P3: Process external context if provided
    let contextResult: { context_recorded: boolean; intent_id?: string; seed_id?: string } = { context_recorded: false };
    if (externalContext) {
      contextResult = await contextHandler.processContext(workspaceId, name, externalContext);
    }

    if (accessDecision.level === "governed" && accessDecision.constraints?.requiresConfirmation) {
      if (!confirmToken) {
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              status: "confirmation_required",
              message: "This operation requires confirmation. Call mindscape.confirm.request first to get confirm_token",
              action: name,
              constraints: accessDecision.constraints,
              next_action: {
                tool: "mindscape.confirm.request",
                args: { action: name }
              }
            }, null, 2)
          }]
        };
      }
      // TODO: Validate confirm_token (ConfirmGuard implementation)
      const validation = confirmGuard.validateToken(confirmToken, workspaceId, name);
      if (!validation.valid) {
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              status: "confirmation_failed",
              message: validation.reason,
              action: name
            }, null, 2)
          }],
          isError: true
        };
      }
    }

    let result;

    // Layer 2: Macro Tools (Playbooks)
    if (name.startsWith("mindscape_playbook_")) {
      const parsed = toolNameResolver.fromMcpName(name);
      if (!parsed) {
        throw new Error(`Invalid playbook name format: ${name}`);
      }

      const { identity } = parsed;
      const playbookCode = identity.canonical;

      result = await mindscapeClient.executePlaybook(
        playbookCode,
        workspaceId as string,
        inputs as Record<string, any>
      );

      return {
        content: [{
          type: "text",
          text: JSON.stringify(formatResult({
            status: result.status,
            outputs: result.outputs,
            error: result.error,
            execution_id: result.execution_id
          }, name), null, 2)
        }]
      };
    }

    // Layer 1: Primitive Tools
    if (name.startsWith("mindscape_tool_")) {
      if (accessDecision.level !== "primitive") {
        throw new Error(
          `Tool ${name} requires governed access. Use mindscape_run_* instead.`
        );
      }

      const parsed = toolNameResolver.fromMcpName(name);
      if (!parsed) {
        throw new Error(`Invalid tool name format: ${name}`);
      }

      const { identity } = parsed;

      result = await mindscapeClient.executeTool(identity.canonical, {
        ...inputs,
        workspace_id: workspaceId
      });

      return {
        content: [{
          type: "text",
          text: JSON.stringify(formatResult(result, name), null, 2)
        }]
      };
    }

    // Layer 3: Governed Tools
    if (name.startsWith("mindscape_run_")) {
      const parsed = toolNameResolver.fromMcpName(name);
      if (!parsed) {
        throw new Error(`Invalid tool name format: ${name}`);
      }

      const { identity } = parsed;

      // TODO: Validate confirm_token (ConfirmGuard implementation)
      if (confirmToken) {
        // Validation logic
      }

      result = await mindscapeClient.executeTool(identity.canonical, {
        ...inputs,
        workspace_id: workspaceId
      });

      return {
        content: [{
          type: "text",
          text: JSON.stringify(formatResult(result, name), null, 2)
        }]
      };
    }

    // ============================================
    // Mind-Lens Tools
    // ============================================
    if (isLensTool(name)) {
      let lensResult;

      if (name === LENS_TOOL_NAMES.LIST_SCHEMAS) {
        const role = (inputs as any).role || "writer";
        lensResult = await mindscapeClient.getLensSchema(role);
        if (!lensResult) {
          lensResult = { message: `No schema found for role: ${role}` };
        }
      } else if (name === LENS_TOOL_NAMES.RESOLVE) {
        lensResult = await mindscapeClient.resolveLens({
          user_id: config.profileId,
          workspace_id: workspaceId,
          playbook_id: (inputs as any).playbook_id,
          role_hint: (inputs as any).role_hint
        });
      } else if (name === LENS_TOOL_NAMES.GET_EFFECTIVE) {
        lensResult = await mindscapeClient.getEffectiveLens({
          profile_id: config.profileId,
          workspace_id: workspaceId,
          session_id: (inputs as any).session_id
        });
      } else {
        throw new Error(`Unknown lens tool: ${name}`);
      }

      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            status: "completed",
            tool: name,
            result: lensResult
          }, null, 2)
        }]
      };
    }

    // ============================================
    // Confirm Tools
    // ============================================
    if (isConfirmTool(name)) {
      if (name === CONFIRM_TOOL_NAMES.REQUEST) {
        const toolName = (inputs as any).tool_name;
        const wsId = (inputs as any).workspace_id || workspaceId;
        const actionPreview = (inputs as any).action_preview;

        const token = confirmGuard.generateToken({
          workspace_id: wsId,
          tool_name: toolName,
          action_preview: actionPreview || confirmGuard.buildActionPreview(toolName, inputs as Record<string, any>)
        });

        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              status: "confirm_token_generated",
              token: token.token,
              expires_at: token.expires_at,
              message: `Confirmation token generated for tool: ${toolName}`,
              usage: `Include confirm_token: "${token.token}" in your next tool call to ${toolName}`
            }, null, 2)
          }]
        };
      } else if (name === CONFIRM_TOOL_NAMES.STATUS) {
        const tokenId = (inputs as any).token;
        // Check if token exists (without consuming it)
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              status: "pending",
              message: "Token status check - active tokens: " + confirmGuard.getActiveTokenCount()
            }, null, 2)
          }]
        };
      }
    }

    // ============================================
    // MCP Bridge: Intent Tools
    // ============================================
    if (isIntentTool(name)) {
      if (name === INTENT_TOOL_NAMES.SUBMIT) {
        const result = await mindscapeClient.submitIntents({
          workspace_id: workspaceId,
          message: String((inputs as any).message || ""),
          message_id: (inputs as any).message_id,
          profile_id: (inputs as any).profile_id,
          extracted_intents: (inputs as any).extracted_intents || [],
          extracted_themes: (inputs as any).extracted_themes
        });
        return {
          content: [{ type: "text", text: JSON.stringify({ status: "completed", tool: name, result }, null, 2) }]
        };
      } else if (name === INTENT_TOOL_NAMES.LAYOUT_EXECUTE) {
        const result = await mindscapeClient.executeIntentLayout({
          workspace_id: workspaceId,
          profile_id: (inputs as any).profile_id,
          layout_plan: (inputs as any).layout_plan
        });
        return {
          content: [{ type: "text", text: JSON.stringify({ status: "completed", tool: name, result }, null, 2) }]
        };
      }
    }

    // ============================================
    // MCP Bridge: Chat Sync Tools
    // ============================================
    if (isChatSyncTool(name)) {
      const result = await mindscapeClient.chatSync({
        workspace_id: workspaceId,
        conversation_id: String((inputs as any).conversation_id || ""),
        surface_type: (inputs as any).surface_type,
        trace_id: (inputs as any).trace_id,
        profile_id: (inputs as any).profile_id,
        messages: (inputs as any).messages || [],
        playbook_executed: (inputs as any).playbook_executed,
        ide_receipts: (inputs as any).ide_receipts
      });
      return {
        content: [{ type: "text", text: JSON.stringify({ status: "completed", tool: name, result }, null, 2) }]
      };
    }

    // ============================================
    // MCP Bridge: Project Tools
    // ============================================
    if (isProjectTool(name)) {
      const result = await mindscapeClient.detectAndCreateProject({
        workspace_id: workspaceId,
        message: String((inputs as any).message || ""),
        profile_id: (inputs as any).profile_id,
        detected_project: (inputs as any).detected_project
      });
      return {
        content: [{ type: "text", text: JSON.stringify({ status: "completed", tool: name, result }, null, 2) }]
      };
    }

    throw new Error(`Unknown tool: ${name}`);
  } catch (error: any) {
    console.error("Error calling tool:", error);
    return {
      content: [{
        type: "text",
        text: JSON.stringify({
          status: "failed",
          error: {
            code: "EXECUTION_ERROR",
            message: error.message || String(error)
          }
        }, null, 2)
      }],
      isError: true
    };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`Mindscape MCP Gateway started (MVP)
  - Workspace: ${config.workspaceId}
  - Mode: ${config.gatewayMode}
  - Base URL: ${config.mindscapeBaseUrl}
  - Pack filter: ${config.packWhitelist.length > 0 ? config.packWhitelist.join(", ") : "(none, serving all)"}`);
}

main().catch(console.error);
