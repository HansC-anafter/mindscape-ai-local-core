export type MCPTransport = 'stdio' | 'http';

export interface MCPServer {
  id: string;
  name: string;
  transport: MCPTransport;
  status: 'connected' | 'disconnected' | 'error';
  tools_count?: number;
  last_connected?: string;
  error?: string;
}

export interface MCPServerConfig {
  server_id: string;
  name: string;
  transport: MCPTransport;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  base_url?: string;
  api_key?: string;
}

export interface AvailableServer {
  id: string;
  name: string;
  description: string;
  command?: string;
  args?: string[];
  requires_env?: string[];
  category?: string;
}

export interface MCPConnectResponse {
  success: boolean;
  server_id: string;
  tools_count: number;
  message: string;
}

export type EnvInputMode = 'keyvalue' | 'json';

export interface EnvKeyValuePair {
  key: string;
  value: string;
}

export interface PopularProviderOption {
  id: string;
  name: string;
  descriptionKey: string;
  fallbackDescription: string;
  icon: string;
}
