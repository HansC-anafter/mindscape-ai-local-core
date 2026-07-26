'use client';

import React, { useEffect, useState } from 'react';
import { useT } from '../../../../lib/i18n';
import { WizardShell } from './WizardShell';
import {
  MCPConfigStep,
  MCPProviderSelectionStep,
  MCPServerWizardFooter,
  MCPTransportSelectionStep,
} from './MCPServerWizardSteps';
import { loadAvailableMcpServers, replaceMcpServer } from './mcpServerWizardApi';
import {
  buildAvailableServerConfig,
  buildCustomMcpServerConfig,
  createInitialMcpServerConfig,
  formatMcpConnectSuccessMessage,
  getProviderPreset,
  toEnvKeyValuePairs,
  updateTransport,
} from './mcpServerWizardModel';
import type {
  AvailableServer,
  EnvInputMode,
  EnvKeyValuePair,
  MCPServer,
  MCPServerConfig,
  MCPTransport,
} from './mcpServerWizardTypes';

interface MCPServerWizardProps {
  provider?: string;
  editingServer?: MCPServer | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function MCPServerWizard({ provider, editingServer, onClose, onSuccess }: MCPServerWizardProps) {
  const t = useT();
  const [step, setStep] = useState(editingServer ? 2 : 1);
  const [availableServers, setAvailableServers] = useState<AvailableServer[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string | undefined>(provider);
  const [config, setConfig] = useState<MCPServerConfig>(() => createInitialMcpServerConfig(editingServer));
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [envInputMode, setEnvInputMode] = useState<EnvInputMode>('keyvalue');
  const [envKeyValuePairs, setEnvKeyValuePairs] = useState<EnvKeyValuePair[]>([]);

  useEffect(() => {
    void loadAvailableServers();
  }, []);

  useEffect(() => {
    if (provider) {
      setSelectedProvider(provider);
      setStep(2);
    }
  }, [provider]);

  const loadAvailableServers = async () => {
    try {
      setAvailableServers(await loadAvailableMcpServers());
    } catch (err) {
      console.error('Failed to load available servers:', err);
    }
  };

  const handleProviderSelect = (providerId: string) => {
    setSelectedProvider(providerId);

    const preset = getProviderPreset(providerId);
    if (preset) {
      setConfig(preset);
      setEnvKeyValuePairs(toEnvKeyValuePairs(preset.env));
      setStep(2);
      return;
    }

    const server = availableServers.find((availableServer) => availableServer.id === providerId);
    if (server) {
      setConfig(buildAvailableServerConfig(providerId, server));
      setStep(2);
      return;
    }

    if (providerId === 'custom') {
      setConfig(buildCustomMcpServerConfig(`custom-${Date.now()}`));
      setStep(2);
    }
  };

  const handleTransportSelect = (transport: MCPTransport) => {
    setConfig(updateTransport(config, transport));
    setStep(3);
  };

  const handleConfigSubmit = async () => {
    setConnecting(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await replaceMcpServer({
        previousServerId: editingServer?.id,
        config,
      });

      setSuccess(formatMcpConnectSuccessMessage(response, Boolean(editingServer)));
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${editingServer ? 'update' : 'connect'} MCP server`);
    } finally {
      setConnecting(false);
    }
  };

  const footer = (
    <MCPServerWizardFooter
      step={step}
      connecting={connecting}
      config={config}
      onBack={() => setStep(step - 1)}
      onCancel={onClose}
      onNext={() => setStep(step + 1)}
      onSubmit={handleConfigSubmit}
    />
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
      {step === 1 && (
        <MCPProviderSelectionStep
          availableServers={availableServers}
          onProviderSelect={handleProviderSelect}
        />
      )}
      {step === 2 && <MCPTransportSelectionStep onTransportSelect={handleTransportSelect} />}
      {step === 3 && (
        <MCPConfigStep
          config={config}
          selectedProvider={selectedProvider}
          envInputMode={envInputMode}
          envKeyValuePairs={envKeyValuePairs}
          onConfigChange={setConfig}
          onEnvInputModeChange={setEnvInputMode}
          onEnvKeyValuePairsChange={setEnvKeyValuePairs}
        />
      )}
    </WizardShell>
  );
}
