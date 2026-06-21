import type {
  AvailableServer,
  EnvKeyValuePair,
  MCPConnectResponse,
  MCPServer,
  MCPServerConfig,
  MCPTransport,
  PopularProviderOption,
} from './mcpServerWizardTypes';

export const POPULAR_MCP_PROVIDERS: PopularProviderOption[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    descriptionKey: 'openaiMCPDescription',
    fallbackDescription: 'Access OpenAI models and capabilities',
    icon: 'OA',
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    descriptionKey: 'anthropicMCPDescription',
    fallbackDescription: 'Access Anthropic Claude models',
    icon: 'AN',
  },
  {
    id: 'github',
    name: 'GitHub',
    descriptionKey: 'githubMCPDescription',
    fallbackDescription: 'Access GitHub repositories, issues, pull requests',
    icon: 'GH',
  },
  {
    id: 'google',
    name: 'Google',
    descriptionKey: 'googleMCPDescription',
    fallbackDescription: 'Access Google services and APIs',
    icon: 'GO',
  },
];

const PROVIDER_PRESETS: Record<string, MCPServerConfig> = {
  openai: {
    server_id: 'openai-mcp',
    name: 'OpenAI MCP Server',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-openai'],
    env: {},
  },
  anthropic: {
    server_id: 'anthropic-mcp',
    name: 'Anthropic MCP Server',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-anthropic'],
    env: {},
  },
  github: {
    server_id: 'github-mcp',
    name: 'GitHub MCP Server',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-github'],
    env: {},
  },
  google: {
    server_id: 'google-mcp',
    name: 'Google MCP Server',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-google'],
    env: {},
  },
};

const PROVIDER_ENV_REQUIREMENTS: Record<string, string[]> = {
  openai: ['OPENAI_API_KEY'],
  anthropic: ['ANTHROPIC_API_KEY'],
  github: ['GITHUB_TOKEN'],
  google: ['GOOGLE_API_KEY'],
};

export function createInitialMcpServerConfig(editingServer?: MCPServer | null): MCPServerConfig {
  if (editingServer) {
    return {
      server_id: editingServer.id,
      name: editingServer.name,
      transport: editingServer.transport,
    };
  }

  return {
    server_id: '',
    name: '',
    transport: 'stdio',
  };
}

export function cloneMcpServerConfig(config: MCPServerConfig): MCPServerConfig {
  return {
    ...config,
    args: config.args ? [...config.args] : undefined,
    env: config.env ? { ...config.env } : undefined,
  };
}

export function getProviderPreset(providerId: string): MCPServerConfig | null {
  const preset = PROVIDER_PRESETS[providerId];
  return preset ? cloneMcpServerConfig(preset) : null;
}

export function getProviderEnvRequirements(providerId?: string): string[] {
  return PROVIDER_ENV_REQUIREMENTS[providerId || ''] || [];
}

export function buildAvailableServerConfig(providerId: string, server: AvailableServer): MCPServerConfig {
  return {
    server_id: providerId,
    name: server.name,
    transport: 'stdio',
    command: server.command || 'npx',
    args: server.args || [],
    env: {},
  };
}

export function buildCustomMcpServerConfig(serverId: string): MCPServerConfig {
  return {
    server_id: serverId,
    name: 'Custom MCP Server',
    transport: 'stdio',
  };
}

export function updateTransport(config: MCPServerConfig, transport: MCPTransport): MCPServerConfig {
  return { ...config, transport };
}

export function toEnvKeyValuePairs(env?: Record<string, string>): EnvKeyValuePair[] {
  const pairs = Object.entries(env || {}).map(([key, value]) => ({
    key,
    value: value || '',
  }));

  return pairs.length > 0 ? pairs : [{ key: '', value: '' }];
}

export function envPairsToRecord(pairs: EnvKeyValuePair[]): Record<string, string> {
  const env: Record<string, string> = {};
  pairs.forEach(({ key, value }) => {
    if (key.trim()) {
      env[key.trim()] = value.trim();
    }
  });
  return env;
}

export function normalizeEnvPairs(pairs: EnvKeyValuePair[]): EnvKeyValuePair[] {
  return pairs.length > 0 ? pairs : [{ key: '', value: '' }];
}

export function formatMcpConnectSuccessMessage(response: MCPConnectResponse, editing: boolean): string {
  return (
    response.message ||
    `Successfully ${editing ? 'updated' : 'connected'}. Discovered ${response.tools_count} tools.`
  );
}
