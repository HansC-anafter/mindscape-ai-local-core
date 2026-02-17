/**
 * Gateway configuration management
 */
export interface GatewayConfig {
  mindscapeBaseUrl: string;
  apiKey?: string;
  workspaceId: string;
  profileId: string;
  timeout?: number;
  gatewayMode?: "single_workspace" | "multi_workspace";
  autoProvision: boolean;
  defaultWorkspaceTitle: string;
  packWhitelist: string[];
}

export function loadConfig(): GatewayConfig {
  const baseUrl = process.env.MINDSCAPE_BASE_URL || "http://localhost:8000";
  const workspaceId = process.env.MINDSCAPE_WORKSPACE_ID || "";
  const profileId = process.env.MINDSCAPE_PROFILE_ID || "default-user";
  const apiKey = process.env.MINDSCAPE_API_KEY;
  const timeout = parseInt(process.env.MINDSCAPE_TIMEOUT || "30000", 10);
  const gatewayMode = (process.env.MINDSCAPE_GATEWAY_MODE || "single_workspace") as "single_workspace" | "multi_workspace";

  const autoProvision = process.env.MINDSCAPE_AUTO_PROVISION !== "false";
  const defaultWorkspaceTitle = process.env.MINDSCAPE_DEFAULT_WORKSPACE_TITLE || "MCP Gateway Workspace";

  // Per-task pack filtering: comma-separated pack codes from runner
  const packWhitelistRaw = process.env.MINDSCAPE_PACK_WHITELIST || "";
  const packWhitelist = packWhitelistRaw
    ? packWhitelistRaw.split(",").map(s => s.trim()).filter(Boolean)
    : [];

  return {
    mindscapeBaseUrl: baseUrl,
    apiKey,
    workspaceId,
    profileId,
    timeout,
    gatewayMode,
    autoProvision,
    defaultWorkspaceTitle,
    packWhitelist
  };
}

export const config = loadConfig();
