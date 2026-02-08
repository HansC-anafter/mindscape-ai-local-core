'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';

interface MCPServer {
  id: string;
  name: string;
  transport: 'stdio' | 'http';
  status: 'connected' | 'disconnected' | 'error';
  tools_count?: number;
  last_connected?: string;
  error?: string;
}

interface MCPServerWizardProps {
  provider?: string;
  editingServer?: MCPServer | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface MCPServerConfig {
  server_id: string;
  name: string;
  transport: 'stdio' | 'http';
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  base_url?: string;
  api_key?: string;
}

interface AvailableServer {
  id: string;
  name: string;
  description: string;
  command?: string;
  args?: string[];
  requires_env?: string[];
  category?: string;
}

export function MCPServerWizard({ provider, editingServer, onClose, onSuccess }: MCPServerWizardProps) {
  const [step, setStep] = useState(editingServer ? 2 : 1);
  const [availableServers, setAvailableServers] = useState<AvailableServer[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string | undefined>(provider);
  const [config, setConfig] = useState<MCPServerConfig>(() => {
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
  });
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [envInputMode, setEnvInputMode] = useState<'keyvalue' | 'json'>('keyvalue');
  const [envKeyValuePairs, setEnvKeyValuePairs] = useState<Array<{ key: string; value: string }>>([]);

  useEffect(() => {
    loadAvailableServers();
  }, []);

  useEffect(() => {
    if (provider) {
      setSelectedProvider(provider);
      setStep(2);
    }
  }, [provider]);

  const loadAvailableServers = async () => {
    try {
      const response = await settingsApi.get<{
        success: boolean;
        servers: AvailableServer[];
      }>('/api/v1/tools/mcp/available-servers');
      setAvailableServers(response.servers || []);
    } catch (err) {
      console.error('Failed to load available servers:', err);
    }
  };

  const getProviderPreset = (providerId: string): MCPServerConfig | null => {
    const presets: Record<string, MCPServerConfig> = {
      'openai': {
        server_id: 'openai-mcp',
        name: 'OpenAI MCP Server',
        transport: 'stdio',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-openai'],
        env: {},
      },
      'anthropic': {
        server_id: 'anthropic-mcp',
        name: 'Anthropic MCP Server',
        transport: 'stdio',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-anthropic'],
        env: {},
      },
      'github': {
        server_id: 'github-mcp',
        name: 'GitHub MCP Server',
        transport: 'stdio',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-github'],
        env: {},
      },
      'google': {
        server_id: 'google-mcp',
        name: 'Google MCP Server',
        transport: 'stdio',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-google'],
        env: {},
      },
    };
    return presets[providerId] || null;
  };

  const handleProviderSelect = (providerId: string) => {
    setSelectedProvider(providerId);

    const preset = getProviderPreset(providerId);
    if (preset) {
      setConfig(preset);
      if (preset.env && Object.keys(preset.env).length > 0) {
        setEnvKeyValuePairs(
          Object.entries(preset.env).map(([key, value]) => ({ key, value: value || '' }))
        );
      } else {
        setEnvKeyValuePairs([{ key: '', value: '' }]);
      }
      setStep(2);
      return;
    }

    const server = availableServers.find(s => s.id === providerId);
    if (server) {
      setConfig({
        server_id: providerId,
        name: server.name,
        transport: 'stdio',
        command: server.command || 'npx',
        args: server.args || [],
        env: {},
      });
      setStep(2);
    } else if (providerId === 'custom') {
      setConfig({
        server_id: 'custom-' + Date.now(),
        name: 'Custom MCP Server',
        transport: 'stdio',
      });
      setStep(2);
    }
  };

  const handleTransportSelect = (transport: 'stdio' | 'http') => {
    setConfig({ ...config, transport });
    setStep(3);
  };

  const handleConfigSubmit = async () => {
    setConnecting(true);
    setError(null);
    setSuccess(null);

    try {
      if (editingServer && editingServer.id !== config.server_id) {
        await settingsApi.delete(`/api/v1/tools/mcp/servers/${editingServer.id}`);
      }

      const response = await settingsApi.post<{
        success: boolean;
        server_id: string;
        tools_count: number;
        message: string;
      }>('/api/v1/tools/mcp/connect', config);

      setSuccess(response.message || `Successfully ${editingServer ? 'updated' : 'connected'}. Discovered ${response.tools_count} tools.`);
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${editingServer ? 'update' : 'connect'} MCP server`);
    } finally {
      setConnecting(false);
    }
  };

  const renderStep1 = () => {
    const popularProviders = [
      { id: 'openai', name: 'OpenAI', description: t('openaiMCPDescription' as any) || 'Access OpenAI models and capabilities', icon: '🤖' },
      { id: 'anthropic', name: 'Anthropic', description: t('anthropicMCPDescription' as any) || 'Access Anthropic Claude models', icon: '🧠' },
      { id: 'github', name: 'GitHub', description: t('githubMCPDescription' as any) || 'Access GitHub repositories, issues, pull requests', icon: '🐙' },
      { id: 'google', name: 'Google', description: t('googleMCPDescription' as any) || 'Access Google services and APIs', icon: '🔍' },
    ];

    return (
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{t('selectMCPProvider' as any) || 'Select MCP Provider'}</h4>

        <div className="mb-4">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('popularProviders' as any) || 'Popular Providers'}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {popularProviders.map((provider) => (
              <button
                key={provider.id}
                onClick={() => handleProviderSelect(provider.id)}
                className="p-3 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/20 text-left flex items-start space-x-2 bg-white dark:bg-gray-800"
              >
                <span className="text-xl">{provider.icon}</span>
                <div>
                  <div className="font-medium text-gray-900 dark:text-gray-100">{provider.name}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{provider.description}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {availableServers.length > 0 && (
          <div className="mb-4">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('otherAvailableServers' as any) || 'Other Available Servers'}</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {availableServers.map((server) => (
                <button
                  key={server.id}
                  onClick={() => handleProviderSelect(server.id)}
                  className="p-3 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/20 text-left bg-white dark:bg-gray-800"
                >
                  <div className="font-medium text-gray-900 dark:text-gray-100">{server.name}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{server.description}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        <div>
          <button
            onClick={() => handleProviderSelect('custom' as any)}
            className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/20 text-left bg-white dark:bg-gray-800"
          >
            <div className="font-medium text-gray-900 dark:text-gray-100">{t('customMCP' as any) || 'Custom MCP'}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{t('customMCPDescription' as any) || 'Configure a custom MCP server'}</div>
          </button>
        </div>
      </div>
    );
  };

  const renderStep2 = () => (
    <div>
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{t('selectTransportType' as any) || 'Select Transport Type'}</h4>
      <div className="space-y-3">
        <button
          onClick={() => handleTransportSelect('stdio' as any)}
          className="w-full p-4 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/20 text-left bg-white dark:bg-gray-800"
        >
          <div className="font-medium text-gray-900 dark:text-gray-100">STDIO</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('stdioTransportDescription' as any) || 'Local process communication (like LSP)'}
          </div>
        </button>
        <button
          onClick={() => handleTransportSelect('http' as any)}
          className="w-full p-4 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/20 text-left bg-white dark:bg-gray-800"
        >
          <div className="font-medium text-gray-900 dark:text-gray-100">HTTP/SSE</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('httpTransportDescription' as any) || 'Remote server via HTTP with Server-Sent Events'}
          </div>
        </button>
      </div>
    </div>
  );

  const getProviderEnvRequirements = (providerId?: string): string[] => {
    const requirements: Record<string, string[]> = {
      'openai': ['OPENAI_API_KEY'],
      'anthropic': ['ANTHROPIC_API_KEY'],
      'github': ['GITHUB_TOKEN'],
      'google': ['GOOGLE_API_KEY'],
    };
    return requirements[providerId || ''] || [];
  };

  const renderStep3 = () => {
    if (config.transport === 'stdio') {
      const envRequirements = getProviderEnvRequirements(selectedProvider);
      const currentEnv = config.env || {};

      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('serverName' as any) || 'Server Name'}
            </label>
            <input
              type="text"
              value={config.name}
              onChange={(e) => setConfig({ ...config, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              placeholder="e.g., GitHub MCP Server"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('command' as any) || 'Command'}
            </label>
            <input
              type="text"
              value={config.command || ''}
              onChange={(e) => setConfig({ ...config, command: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              placeholder="e.g., npx, python"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('arguments' as any) || 'Arguments (one per line)'}
            </label>
            <textarea
              value={config.args?.join('\n') || ''}
              onChange={(e) => setConfig({
                ...config,
                args: e.target.value.split('\n').filter(arg => arg.trim()),
              })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              rows={3}
              placeholder="-y&#10;@modelcontextprotocol/server-github"
            />
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('environmentVariables' as any) || 'Environment Variables'}
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (envInputMode === 'json') {
                      const pairs = Object.entries(currentEnv).map(([key, value]) => ({
                        key,
                        value: value || '',
                      }));
                      if (pairs.length === 0) {
                        pairs.push({ key: '', value: '' });
                      }
                      setEnvKeyValuePairs(pairs);
                    }
                    setEnvInputMode('keyvalue');
                  }}
                  className={`px-2 py-1 text-xs rounded ${
                    envInputMode === 'keyvalue'
                      ? 'bg-gray-100 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300 border border-gray-400 dark:border-gray-600'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  Key-Value
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (envInputMode === 'keyvalue') {
                      const env: Record<string, string> = {};
                      envKeyValuePairs.forEach(({ key, value }) => {
                        if (key.trim()) {
                          env[key.trim()] = value.trim();
                        }
                      });
                      setConfig({ ...config, env });
                    }
                    setEnvInputMode('json');
                  }}
                  className={`px-2 py-1 text-xs rounded ${
                    envInputMode === 'json'
                      ? 'bg-gray-100 dark:bg-gray-800/30 text-gray-700 dark:text-gray-300 border border-gray-400 dark:border-gray-600'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  JSON
                </button>
              </div>
            </div>
            {envRequirements.length > 0 && (
              <div className="mb-2 p-2 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md">
                <p className="text-xs text-blue-800 dark:text-blue-300 mb-1">
                  {t('requiredEnvVars' as any) || 'Required environment variables:'}
                </p>
                <ul className="text-xs text-blue-700 dark:text-blue-400 list-disc list-inside">
                  {envRequirements.map((req) => (
                    <li key={req}>{req}</li>
                  ))}
                </ul>
              </div>
            )}

            {envInputMode === 'keyvalue' ? (
              <div className="space-y-2">
                {(envKeyValuePairs.length === 0 ? [{ key: '', value: '' }] : envKeyValuePairs).map((pair, index) => (
                  <div key={index} className="flex gap-2">
                    <input
                      type="text"
                      value={pair.key}
                      onChange={(e) => {
                        const newPairs = [...envKeyValuePairs];
                        if (newPairs.length === 0) {
                          newPairs.push({ key: '', value: '' });
                        }
                        newPairs[index].key = e.target.value;
                        setEnvKeyValuePairs(newPairs);
                        const env: Record<string, string> = {};
                        newPairs.forEach(({ key, value }) => {
                          if (key.trim()) {
                            env[key.trim()] = value.trim();
                          }
                        });
                        setConfig({ ...config, env });
                      }}
                      placeholder="Variable name"
                      className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                    <input
                      type="password"
                      value={pair.value}
                      onChange={(e) => {
                        const newPairs = [...envKeyValuePairs];
                        if (newPairs.length === 0) {
                          newPairs.push({ key: '', value: '' });
                        }
                        newPairs[index].value = e.target.value;
                        setEnvKeyValuePairs(newPairs);
                        const env: Record<string, string> = {};
                        newPairs.forEach(({ key, value }) => {
                          if (key.trim()) {
                            env[key.trim()] = value.trim();
                          }
                        });
                        setConfig({ ...config, env });
                      }}
                      placeholder="Variable value"
                      className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const newPairs = envKeyValuePairs.filter((_, i) => i !== index);
                        if (newPairs.length === 0) {
                          newPairs.push({ key: '', value: '' });
                        }
                        setEnvKeyValuePairs(newPairs);
                        const env: Record<string, string> = {};
                        newPairs.forEach(({ key, value }) => {
                          if (key.trim()) {
                            env[key.trim()] = value.trim();
                          }
                        });
                        setConfig({ ...config, env });
                      }}
                      className="px-3 py-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 border border-red-300 dark:border-red-700 rounded-md text-sm bg-white dark:bg-gray-800"
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => {
                    setEnvKeyValuePairs([...envKeyValuePairs, { key: '', value: '' }]);
                  }}
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800"
                >
                  + Add Variable
                </button>
              </div>
            ) : (
              <textarea
                value={JSON.stringify(currentEnv, null, 2)}
                onChange={(e) => {
                  try {
                    const env = JSON.parse(e.target.value);
                    setConfig({ ...config, env });
                  } catch {
                    // Ignore invalid JSON
                  }
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md font-mono text-sm focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                rows={6}
                placeholder='{"GITHUB_TOKEN": "your_token_here"}'
              />
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {t('envVarsNote' as any) || 'Environment variables will be passed to the MCP server process.'}
            </p>
          </div>
        </div>
      );
    } else {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('serverName' as any) || 'Server Name'}
            </label>
            <input
              type="text"
              value={config.name}
              onChange={(e) => setConfig({ ...config, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              placeholder="e.g., Remote MCP Server"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('baseUrl' as any) || 'Base URL'}
            </label>
            <input
              type="url"
              value={config.base_url || ''}
              onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              placeholder="https://mcp.example.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('apiKey' as any) || 'API Key'}
            </label>
            <input
              type="password"
              value={config.api_key || ''}
              onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              placeholder="Your API key"
            />
          </div>
        </div>
      );
    }
  };

  const footer = (
    <>
      {step > 1 && (
        <button
          onClick={() => setStep(step - 1)}
          className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
        >
          {t('back' as any) || 'Back'}
        </button>
      )}
      <button
        onClick={onClose}
        className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
      >
        {t('cancel' as any) || 'Cancel'}
      </button>
      {step < 3 ? (
        <button
          onClick={() => setStep(step + 1)}
          disabled={!config.name || (step === 2 && !config.transport)}
          className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {t('next' as any) || 'Next'}
        </button>
      ) : (
        <button
          onClick={handleConfigSubmit}
          disabled={connecting || !config.name || !config.server_id}
          className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {connecting ? (t('connecting' as any) || 'Connecting...') : (t('connect' as any) || 'Connect')}
        </button>
      )}
    </>
  );

  return (
    <WizardShell
      title={editingServer ? (t('editMCPServer' as any) || 'Edit MCP Server') : (t('configureMCPServer' as any) || 'Configure MCP Server')}
      onClose={onClose}
      error={error}
      success={success}
      onDismissError={() => setError(null)}
      onDismissSuccess={() => setSuccess(null)}
      footer={footer}
    >
      {step === 1 && renderStep1()}
      {step === 2 && renderStep2()}
      {step === 3 && renderStep3()}
    </WizardShell>
  );
}

