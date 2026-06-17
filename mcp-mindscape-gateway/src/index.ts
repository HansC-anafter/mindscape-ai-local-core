/**
 * Mindscape Gateway MCP Server
 *
 * MVP: tools/list + tools/call + three-layer naming + Access Policy
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { MindscapeClient } from "./mindscape/client.js";
import { PlaybookMapper } from "./mindscape/playbook_mapper.js";
import { WorkspaceProvisioner } from "./mindscape/workspace_provisioner.js";
import { ToolNameResolver } from "./utils/tool_name_resolver.js";
import { ContextHandler } from "./context_handler.js";
import { ConfirmGuard } from "./confirm_guard.js";
import { config } from "./config.js";
import { registerListToolsHandler } from "./tool_list_handler.js";
import { registerCallToolHandler } from "./tool_call_handler.js";
import {
  createToolListFreshnessPoller,
  startToolListFreshnessPolling,
  TOOL_POLL_INTERVAL_MS
} from "./tool_freshness.js";

const server = new Server(
  {
    name: "mindscape-gateway",
    version: "1.0.0"
  },
  {
    capabilities: {
      tools: { listChanged: true },
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

registerListToolsHandler({
  server,
  mindscapeClient,
  toolNameResolver,
  playbookMapper,
});

registerCallToolHandler({
  server,
  mindscapeClient,
  toolNameResolver,
  workspaceProvisioner,
  contextHandler,
  confirmGuard,
});

const pollToolListFreshness = createToolListFreshnessPoller({
  server,
  mindscapeClient,
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`Mindscape MCP Gateway started (MVP)
  - Workspace: ${config.workspaceId}
  - Mode: ${config.gatewayMode}
  - Base URL: ${config.mindscapeBaseUrl}
  - Task hint: ${config.taskHint ? "set" : "(none)"}
  - Max tools: ${config.maxTools}
  - Tool list change polling: every ${TOOL_POLL_INTERVAL_MS / 1000}s`);

  // Start periodic tool list freshness check
  startToolListFreshnessPolling(pollToolListFreshness);
}

main().catch(console.error);
