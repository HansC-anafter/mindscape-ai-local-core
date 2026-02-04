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
import { config } from "./config.js";

const server = new Server(
  {
    name: "mindscape-gateway",
    version: "1.0.0"
  },
  {
    capabilities: {
      tools: {}
    }
  }
);

const mindscapeClient = new MindscapeClient();
const toolNameResolver = new ToolNameResolver();
const playbookMapper = new PlaybookMapper(mindscapeClient, toolNameResolver);
const workspaceProvisioner = new WorkspaceProvisioner(mindscapeClient);

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
    const tools = await mindscapeClient.listTools({
      enabled_only: true
    });
    const playbooks = await mindscapeClient.listPlaybooks({
      scope: "system"
    });
    const packs = await mindscapeClient.listPacks();

    toolNameResolver.updateKnownPacks(packs.map(p => p.code));

    const mcpTools: any[] = [];

    // ============================================
    // Layer 2: Macro Tools (Playbooks)
    // ============================================
    for (const pb of playbooks) {
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
    // Layer 1 & 3: Primitive / Governed Tools
    // ============================================
    for (const tool of tools) {
      const identity = toolNameResolver.resolve({
        name: tool.name,
        pack: tool.pack,
        provider: "capability"
      });

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
    const confirmToken = args.confirm_token;

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
  - Base URL: ${config.mindscapeBaseUrl}`);
}

main().catch(console.error);
