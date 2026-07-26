import type { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import type { MindscapeClient } from "./mindscape/client.js";
import type { PlaybookMapper } from "./mindscape/playbook_mapper.js";
import type { ToolNameResolver } from "./utils/tool_name_resolver.js";
import { toolAccessPolicy } from "./policy/tool_access_policy.js";
import { wrapToolSchema } from "./utils/schema.js";
import { lensTools } from "./tools/lens_tools.js";
import { confirmTools } from "./tools/confirm_tools.js";
import { intentTools } from "./tools/intent_tools.js";
import { chatSyncTools } from "./tools/chat_sync_tools.js";
import { projectTools } from "./tools/project_tools.js";
import { config } from "./config.js";

interface ListToolsHandlerDependencies {
  server: Server;
  mindscapeClient: MindscapeClient;
  toolNameResolver: ToolNameResolver;
  playbookMapper: PlaybookMapper;
}

export function registerListToolsHandler({
  server,
  mindscapeClient,
  toolNameResolver,
  playbookMapper,
}: ListToolsHandlerDependencies): void {
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    try {
      // Server-side filtered fetch: RAG + safe defaults + deterministic ordering
      const [filtered, packs] = await Promise.all([
        mindscapeClient.fetchFilteredTools({
          task_hint: config.taskHint,
          max_tools: config.maxTools,
          include_playbooks: true,
          enabled_only: true,
          recommended_pack_codes: config.recommendedPacks,
        }),
        mindscapeClient.listPacks(),
      ]);

      toolNameResolver.updateKnownPacks(packs.map(p => p.code));

      const mcpTools: any[] = [];

      // ============================================
      // Layer 2: Macro Tools (Playbooks) - pre-filtered by backend
      // ============================================
      for (const pb of filtered.playbooks) {
        const mcpTool = playbookMapper.toMcpTool(pb);
        const decision = toolAccessPolicy.getAccessLevel(mcpTool.name);

        if (decision.allowed) {
          mcpTools.push(mcpTool);
        }
      }

      // ============================================
      // Mind-Lens Tools (Built-in, always served)
      // ============================================
      for (const lensTool of lensTools) {
        mcpTools.push(lensTool);
      }

      // ============================================
      // Confirm Tools (Built-in, always served)
      // ============================================
      for (const confirmTool of confirmTools) {
        mcpTools.push(confirmTool);
      }

      // ============================================
      // MCP Bridge Tools (Intent, Chat Sync, Project - always served)
      // ============================================
      for (const tool of [...intentTools, ...chatSyncTools, ...projectTools]) {
        const decision = toolAccessPolicy.getAccessLevel(tool.name);
        if (decision.allowed) {
          mcpTools.push(tool);
        }
      }

      // ============================================
      // Layer 1 & 3: Primitive / Governed Tools - pre-filtered by backend
      // ============================================
      for (const tool of filtered.tools) {
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
          const requiresConfirmation = Boolean(
            decision.constraints?.requiresConfirmation
          );
          mcpTools.push({
            name: governedName,
            description: requiresConfirmation
              ? `[Governed] ${tool.description} - Requires confirmation`
              : `[Governed] ${tool.description}`,
            inputSchema: wrapToolSchema(tool.input_schema || {}, {
              includeWorkspaceId: true,
              includeConfirmToken: requiresConfirmation
            }),
            _mindscape: {
              layer: "governed",
              pack: identity.pack,
              action: identity.action,
              danger_level: "high",
              requires_confirmation: requiresConfirmation,
              requires_preview: decision.constraints?.requiresPreview
            }
          });
        }
      }

      const meta = filtered.meta;
      console.error(
        `tools/list: ${meta.tool_count} tools, ${meta.playbook_count} playbooks, ` +
        `rag=${meta.rag_status}, packs=[${meta.pack_codes.join(", ")}], ` +
        `total_served=${mcpTools.length}`
      );

      return { tools: mcpTools };
    } catch (error: any) {
      console.error("Error listing tools:", error);
      throw error;
    }
  });
}
