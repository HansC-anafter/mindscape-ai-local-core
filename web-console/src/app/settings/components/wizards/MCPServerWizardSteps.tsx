import React from 'react';
import { t } from '../../../../lib/i18n';
import {
  envPairsToRecord,
  getProviderEnvRequirements,
  normalizeEnvPairs,
  POPULAR_MCP_PROVIDERS,
  toEnvKeyValuePairs,
} from './mcpServerWizardModel';
import type {
  AvailableServer,
  EnvInputMode,
  EnvKeyValuePair,
  MCPServerConfig,
  MCPTransport,
} from './mcpServerWizardTypes';

interface ProviderSelectionStepProps {
  availableServers: AvailableServer[];
  onProviderSelect: (providerId: string) => void;
}

interface TransportSelectionStepProps {
  onTransportSelect: (transport: MCPTransport) => void;
}

interface ConfigStepProps {
  config: MCPServerConfig;
  selectedProvider?: string;
  envInputMode: EnvInputMode;
  envKeyValuePairs: EnvKeyValuePair[];
  onConfigChange: (config: MCPServerConfig) => void;
  onEnvInputModeChange: (mode: EnvInputMode) => void;
  onEnvKeyValuePairsChange: (pairs: EnvKeyValuePair[]) => void;
}

interface FooterProps {
  step: number;
  connecting: boolean;
  config: MCPServerConfig;
  onBack: () => void;
  onCancel: () => void;
  onNext: () => void;
  onSubmit: () => void;
}

export function MCPProviderSelectionStep({ availableServers, onProviderSelect }: ProviderSelectionStepProps) {
  return (
    <div>
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{t('selectMCPProvider' as any) || 'Select MCP Provider'}</h4>

      <div className="mb-4">
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">{t('popularProviders' as any) || 'Popular Providers'}</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {POPULAR_MCP_PROVIDERS.map((provider) => (
            <button
              key={provider.id}
              onClick={() => onProviderSelect(provider.id)}
              className="p-3 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/20 text-left flex items-start space-x-2 bg-white dark:bg-gray-800"
            >
              <span className="text-xl">{provider.icon}</span>
              <div>
                <div className="font-medium text-gray-900 dark:text-gray-100">{provider.name}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {t(provider.descriptionKey as any) || provider.fallbackDescription}
                </div>
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
                onClick={() => onProviderSelect(server.id)}
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
          onClick={() => onProviderSelect('custom')}
          className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/20 text-left bg-white dark:bg-gray-800"
        >
          <div className="font-medium text-gray-900 dark:text-gray-100">{t('customMCP' as any) || 'Custom MCP'}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{t('customMCPDescription' as any) || 'Configure a custom MCP server'}</div>
        </button>
      </div>
    </div>
  );
}

export function MCPTransportSelectionStep({ onTransportSelect }: TransportSelectionStepProps) {
  return (
    <div>
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{t('selectTransportType' as any) || 'Select Transport Type'}</h4>
      <div className="space-y-3">
        <button
          onClick={() => onTransportSelect('stdio')}
          className="w-full p-4 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/20 text-left bg-white dark:bg-gray-800"
        >
          <div className="font-medium text-gray-900 dark:text-gray-100">STDIO</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('stdioTransportDescription' as any) || 'Local process communication (like LSP)'}
          </div>
        </button>
        <button
          onClick={() => onTransportSelect('http')}
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
}

export function MCPConfigStep(props: ConfigStepProps) {
  const {
    config,
    selectedProvider,
    envInputMode,
    envKeyValuePairs,
    onConfigChange,
    onEnvInputModeChange,
    onEnvKeyValuePairsChange,
  } = props;

  if (config.transport === 'stdio') {
    return (
      <MCPStdioConfigStep
        config={config}
        selectedProvider={selectedProvider}
        envInputMode={envInputMode}
        envKeyValuePairs={envKeyValuePairs}
        onConfigChange={onConfigChange}
        onEnvInputModeChange={onEnvInputModeChange}
        onEnvKeyValuePairsChange={onEnvKeyValuePairsChange}
      />
    );
  }

  return <MCPHttpConfigStep config={config} onConfigChange={onConfigChange} />;
}

function MCPStdioConfigStep({
  config,
  selectedProvider,
  envInputMode,
  envKeyValuePairs,
  onConfigChange,
  onEnvInputModeChange,
  onEnvKeyValuePairsChange,
}: ConfigStepProps) {
  const envRequirements = getProviderEnvRequirements(selectedProvider);
  const currentEnv = config.env || {};
  const renderedPairs = normalizeEnvPairs(envKeyValuePairs);

  const setPairsAndConfig = (pairs: EnvKeyValuePair[]) => {
    const normalizedPairs = normalizeEnvPairs(pairs);
    onEnvKeyValuePairsChange(normalizedPairs);
    onConfigChange({ ...config, env: envPairsToRecord(normalizedPairs) });
  };

  const updatePair = (index: number, field: keyof EnvKeyValuePair, value: string) => {
    const nextPairs = renderedPairs.map((pair) => ({ ...pair }));
    nextPairs[index][field] = value;
    setPairsAndConfig(nextPairs);
  };

  const removePair = (index: number) => {
    setPairsAndConfig(renderedPairs.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {t('serverName' as any) || 'Server Name'}
        </label>
        <input
          type="text"
          value={config.name}
          onChange={(e) => onConfigChange({ ...config, name: e.target.value })}
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
          onChange={(e) => onConfigChange({ ...config, command: e.target.value })}
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
          onChange={(e) => onConfigChange({
            ...config,
            args: e.target.value.split('\n').filter((arg) => arg.trim()),
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
                  onEnvKeyValuePairsChange(toEnvKeyValuePairs(currentEnv));
                }
                onEnvInputModeChange('keyvalue');
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
                  onConfigChange({ ...config, env: envPairsToRecord(renderedPairs) });
                }
                onEnvInputModeChange('json');
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
            {renderedPairs.map((pair, index) => (
              <div key={index} className="flex gap-2">
                <input
                  type="text"
                  value={pair.key}
                  onChange={(e) => updatePair(index, 'key', e.target.value)}
                  placeholder="Variable name"
                  className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                <input
                  type="password"
                  value={pair.value}
                  onChange={(e) => updatePair(index, 'value', e.target.value)}
                  placeholder="Variable value"
                  className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                <button
                  type="button"
                  onClick={() => removePair(index)}
                  className="px-3 py-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 border border-red-300 dark:border-red-700 rounded-md text-sm bg-white dark:bg-gray-800"
                >
                  Remove
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => {
                onEnvKeyValuePairsChange([...renderedPairs, { key: '', value: '' }]);
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
                onConfigChange({ ...config, env });
              } catch {
                // Ignore invalid JSON until the user fixes the input.
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
}

function MCPHttpConfigStep({
  config,
  onConfigChange,
}: Pick<ConfigStepProps, 'config' | 'onConfigChange'>) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {t('serverName' as any) || 'Server Name'}
        </label>
        <input
          type="text"
          value={config.name}
          onChange={(e) => onConfigChange({ ...config, name: e.target.value })}
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
          onChange={(e) => onConfigChange({ ...config, base_url: e.target.value })}
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
          onChange={(e) => onConfigChange({ ...config, api_key: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          placeholder="Your API key"
        />
      </div>
    </div>
  );
}

export function MCPServerWizardFooter({
  step,
  connecting,
  config,
  onBack,
  onCancel,
  onNext,
  onSubmit,
}: FooterProps) {
  return (
    <>
      {step > 1 && (
        <button
          onClick={onBack}
          className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
        >
          {t('back' as any) || 'Back'}
        </button>
      )}
      <button
        onClick={onCancel}
        className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
      >
        {t('cancel' as any) || 'Cancel'}
      </button>
      {step < 3 ? (
        <button
          onClick={onNext}
          disabled={!config.name || (step === 2 && !config.transport)}
          className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {t('next' as any) || 'Next'}
        </button>
      ) : (
        <button
          onClick={onSubmit}
          disabled={connecting || !config.name || !config.server_id}
          className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {connecting ? (t('connecting' as any) || 'Connecting...') : (t('connect' as any) || 'Connect')}
        </button>
      )}
    </>
  );
}
