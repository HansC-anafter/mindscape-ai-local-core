import { settingsApi } from '../../utils/settingsApi';
import type { AvailableServer, MCPConnectResponse, MCPServerConfig } from './mcpServerWizardTypes';

export const MCP_AVAILABLE_SERVERS_ENDPOINT = '/api/v1/tools/mcp/available-servers';
export const MCP_CONNECT_ENDPOINT = '/api/v1/tools/mcp/connect';
export const MCP_SERVERS_ENDPOINT = '/api/v1/tools/mcp/servers';

export function getMcpServerEndpoint(serverId: string): string {
  return `${MCP_SERVERS_ENDPOINT}/${serverId}`;
}

export async function loadAvailableMcpServers(): Promise<AvailableServer[]> {
  const response = await settingsApi.get<{
    success: boolean;
    servers: AvailableServer[];
  }>(MCP_AVAILABLE_SERVERS_ENDPOINT);

  return response.servers || [];
}

export async function connectMcpServer(config: MCPServerConfig): Promise<MCPConnectResponse> {
  return settingsApi.post<MCPConnectResponse>(MCP_CONNECT_ENDPOINT, config);
}

export async function replaceMcpServer(options: {
  previousServerId?: string;
  config: MCPServerConfig;
}): Promise<MCPConnectResponse> {
  const { previousServerId, config } = options;

  if (previousServerId && previousServerId !== config.server_id) {
    await settingsApi.delete(getMcpServerEndpoint(previousServerId));
  }

  return connectMcpServer(config);
}
