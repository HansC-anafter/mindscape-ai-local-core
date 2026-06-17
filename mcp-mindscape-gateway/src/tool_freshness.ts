import type { Server } from "@modelcontextprotocol/sdk/server/index.js";
import type { MindscapeClient } from "./mindscape/client.js";
import { config } from "./config.js";

interface ToolFreshnessDependencies {
  server: Server;
  mindscapeClient: MindscapeClient;
}

export const TOOL_POLL_INTERVAL_MS = 60_000; // 60 seconds

export function createToolListFreshnessPoller({
  server,
  mindscapeClient,
}: ToolFreshnessDependencies): () => Promise<void> {
  let lastToolCount = -1;

  return async function pollToolListFreshness(): Promise<void> {
    try {
      const filtered = await mindscapeClient.fetchFilteredTools({
        task_hint: config.taskHint,
        max_tools: config.maxTools,
        include_playbooks: false,
        enabled_only: true,
      });
      const currentCount = filtered.meta.tool_count;
      if (lastToolCount >= 0 && currentCount !== lastToolCount) {
        console.error(
          `Tool list changed: ${lastToolCount} -> ${currentCount}, ` +
          `sending notifications/tools/list_changed`
        );
        await server.notification({
          method: "notifications/tools/list_changed",
        });
      }
      lastToolCount = currentCount;
    } catch (err: any) {
      console.error(`Tool freshness poll error: ${err.message}`);
    }
  };
}

export function startToolListFreshnessPolling(
  pollToolListFreshness: () => Promise<void>
): NodeJS.Timeout {
  return setInterval(pollToolListFreshness, TOOL_POLL_INTERVAL_MS);
}
