import { beforeEach, describe, expect, it, vi } from 'vitest';
import { settingsApi } from '../../utils/settingsApi';
import {
  getMcpServerEndpoint,
  loadAvailableMcpServers,
  MCP_AVAILABLE_SERVERS_ENDPOINT,
  MCP_CONNECT_ENDPOINT,
  replaceMcpServer,
} from './mcpServerWizardApi';
import {
  buildAvailableServerConfig,
  buildCustomMcpServerConfig,
  envPairsToRecord,
  formatMcpConnectSuccessMessage,
  getProviderPreset,
  toEnvKeyValuePairs,
} from './mcpServerWizardModel';
import type { AvailableServer, MCPServerConfig } from './mcpServerWizardTypes';

vi.mock('../../utils/settingsApi', () => ({
  settingsApi: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const settingsApiMock = vi.mocked(settingsApi);

describe('mcpServerWizardApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads available MCP servers through the canonical settings endpoint', async () => {
    const servers: AvailableServer[] = [
      {
        id: 'filesystem',
        name: 'File System',
        description: 'Read and write files',
      },
    ];
    settingsApiMock.get.mockResolvedValue({ success: true, servers });

    await expect(loadAvailableMcpServers()).resolves.toEqual(servers);
    expect(settingsApiMock.get).toHaveBeenCalledWith(MCP_AVAILABLE_SERVERS_ENDPOINT);
  });

  it('returns an empty list when the available-server response omits servers', async () => {
    settingsApiMock.get.mockResolvedValue({ success: true });

    await expect(loadAvailableMcpServers()).resolves.toEqual([]);
  });

  it('connects directly when there is no previous server id', async () => {
    const config: MCPServerConfig = {
      server_id: 'github-mcp',
      name: 'GitHub MCP Server',
      transport: 'stdio',
    };
    settingsApiMock.post.mockResolvedValue({
      success: true,
      server_id: config.server_id,
      tools_count: 3,
      message: 'connected',
    });

    await replaceMcpServer({ config });

    expect(settingsApiMock.delete).not.toHaveBeenCalled();
    expect(settingsApiMock.post).toHaveBeenCalledWith(MCP_CONNECT_ENDPOINT, config);
  });

  it('preserves delete-before-connect ordering when an edit changes server id', async () => {
    const config: MCPServerConfig = {
      server_id: 'github-new',
      name: 'GitHub MCP Server',
      transport: 'stdio',
    };
    settingsApiMock.delete.mockResolvedValue({});
    settingsApiMock.post.mockResolvedValue({
      success: true,
      server_id: config.server_id,
      tools_count: 2,
      message: 'updated',
    });

    await replaceMcpServer({ previousServerId: 'github-old', config });

    expect(settingsApiMock.delete).toHaveBeenCalledWith(getMcpServerEndpoint('github-old'));
    expect(settingsApiMock.post).toHaveBeenCalledWith(MCP_CONNECT_ENDPOINT, config);
    expect(settingsApiMock.delete.mock.invocationCallOrder[0]).toBeLessThan(
      settingsApiMock.post.mock.invocationCallOrder[0],
    );
  });

  it('does not delete when editing keeps the same server id', async () => {
    const config: MCPServerConfig = {
      server_id: 'github-mcp',
      name: 'GitHub MCP Server',
      transport: 'stdio',
    };
    settingsApiMock.post.mockResolvedValue({
      success: true,
      server_id: config.server_id,
      tools_count: 2,
      message: 'updated',
    });

    await replaceMcpServer({ previousServerId: 'github-mcp', config });

    expect(settingsApiMock.delete).not.toHaveBeenCalled();
    expect(settingsApiMock.post).toHaveBeenCalledWith(MCP_CONNECT_ENDPOINT, config);
  });
});

describe('mcpServerWizardModel', () => {
  it('returns cloned provider presets so callers cannot mutate shared defaults', () => {
    const first = getProviderPreset('github');
    const second = getProviderPreset('github');

    expect(first).toMatchObject({
      server_id: 'github-mcp',
      name: 'GitHub MCP Server',
      transport: 'stdio',
    });
    expect(first).not.toBe(second);
    expect(first?.args).not.toBe(second?.args);
    expect(first?.env).not.toBe(second?.env);
  });

  it('builds available-server and custom configs without touching wall-clock time', () => {
    expect(
      buildAvailableServerConfig('filesystem', {
        id: 'filesystem',
        name: 'File System',
        description: 'Read and write files',
      }),
    ).toEqual({
      server_id: 'filesystem',
      name: 'File System',
      transport: 'stdio',
      command: 'npx',
      args: [],
      env: {},
    });

    expect(buildCustomMcpServerConfig('custom-fixed')).toEqual({
      server_id: 'custom-fixed',
      name: 'Custom MCP Server',
      transport: 'stdio',
    });
  });

  it('normalizes env pairs and success messages', () => {
    expect(toEnvKeyValuePairs({ GITHUB_TOKEN: 'abc' })).toEqual([
      { key: 'GITHUB_TOKEN', value: 'abc' },
    ]);
    expect(toEnvKeyValuePairs({})).toEqual([{ key: '', value: '' }]);
    expect(envPairsToRecord([
      { key: ' GITHUB_TOKEN ', value: ' abc ' },
      { key: ' ', value: 'ignored' },
    ])).toEqual({ GITHUB_TOKEN: 'abc' });

    expect(formatMcpConnectSuccessMessage({
      success: true,
      server_id: 'github',
      tools_count: 4,
      message: '',
    }, false)).toBe('Successfully connected. Discovered 4 tools.');
  });
});
