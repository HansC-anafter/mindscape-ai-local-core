'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';

interface WorkflowWizardProps {
  platform?: 'zapier' | 'n8n' | 'make' | 'custom';
  onClose: () => void;
  onSuccess: () => void;
}

interface WorkflowConfig {
  platform: 'zapier' | 'n8n' | 'make' | 'custom';
  name: string;
  api_key: string;
  webhook_url?: string;
  base_url?: string;
}

export function WorkflowWizard({ platform, onClose, onSuccess }: WorkflowWizardProps) {
  const [step, setStep] = useState(platform ? 2 : 1);
  const [selectedPlatform, setSelectedPlatform] = useState<'zapier' | 'n8n' | 'make' | 'custom' | undefined>(platform);
  const [config, setConfig] = useState<WorkflowConfig>({
    platform: platform || 'zapier',
    name: '',
    api_key: '',
    webhook_url: '',
    base_url: '',
  });
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const platforms = [
    { id: 'zapier' as const, name: 'Zapier', description: 'Automate workflows between apps', icon: '⚡' },
    { id: 'n8n' as const, name: 'n8n', description: 'Open-source workflow automation', icon: '🔄' },
    { id: 'make' as const, name: 'Make', description: 'Visual automation platform', icon: '🎨' },
    { id: 'custom' as const, name: 'Custom', description: 'Custom workflow integration', icon: '🔧' },
  ];

  const handlePlatformSelect = (platformId: 'zapier' | 'n8n' | 'make' | 'custom') => {
    setSelectedPlatform(platformId);
    setConfig({ ...config, platform: platformId, name: platformId === 'custom' ? 'Custom Workflow' : platforms.find(p => p.id === platformId)?.name || '' });
    setStep(2);
  };

  const handleConfigSubmit = async () => {
    setConnecting(true);
    setError(null);
    setSuccess(null);

    try {
      // For now, just simulate success
      await new Promise(resolve => setTimeout(resolve, 1000));

      setSuccess(t('workflowConnected') || 'Workflow connected successfully');
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect workflow');
    } finally {
      setConnecting(false);
    }
  };

  const renderStep1 = () => (
    <div>
      <h4 className="text-sm font-medium text-gray-700 mb-3">{t('selectWorkflowProvider') || 'Select Workflow Platform'}</h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {platforms.map((p) => (
          <button
            key={p.id}
            onClick={() => handlePlatformSelect(p.id)}
            className="p-4 border border-gray-300 rounded-md hover:border-gray-500 hover:bg-gray-50 text-left"
          >
            <div className="flex items-center space-x-3">
              <span className="text-2xl">{p.icon}</span>
              <div>
                <div className="font-medium text-gray-900">{p.name}</div>
                <div className="text-xs text-gray-500 mt-1">{p.description}</div>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );

  const renderStep2 = () => {
    const platformConfig = platforms.find(p => p.id === selectedPlatform);

    return (
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('workflowName') || 'Workflow Name'}
          </label>
          <input
            type="text"
            value={config.name}
            onChange={(e) => setConfig({ ...config, name: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
            placeholder={`${platformConfig?.name || 'Workflow'} Connection`}
          />
        </div>

        {selectedPlatform === 'n8n' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('n8nInstanceUrl') || 'n8n Instance URL'}
            </label>
            <input
              type="url"
              value={config.base_url || ''}
              onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="https://n8n.example.com"
            />
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('apiKey') || 'API Key'}
          </label>
          <input
            type="password"
            value={config.api_key}
            onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
            placeholder="Your API key"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('webhookUrl') || 'Webhook URL (Optional)'}
          </label>
          <input
            type="url"
            value={config.webhook_url || ''}
            onChange={(e) => setConfig({ ...config, webhook_url: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
            placeholder="https://webhook.example.com"
          />
          <p className="text-xs text-gray-500 mt-1">
            {t('webhookUrlDescription') || 'Optional: Webhook URL for receiving events from the workflow platform'}
          </p>
        </div>
      </div>
    );
  };

  const footer = (
    <>
      {step > 1 && (
        <button
          onClick={() => setStep(step - 1)}
          className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
        >
          {t('back') || 'Back'}
        </button>
      )}
      <button
        onClick={onClose}
        className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
      >
        {t('cancel') || 'Cancel'}
      </button>
      {step < 2 ? (
        <button
          onClick={() => setStep(step + 1)}
          disabled={!selectedPlatform}
          className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-50"
        >
          {t('next') || 'Next'}
        </button>
      ) : (
        <button
          onClick={handleConfigSubmit}
          disabled={connecting || !config.name || !config.api_key}
          className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-50"
        >
          {connecting ? (t('connecting') || 'Connecting...') : (t('connect') || 'Connect')}
        </button>
      )}
    </>
  );

  return (
    <WizardShell
      title={t('configureWorkflow') || 'Configure Workflow'}
      onClose={onClose}
      error={error}
      success={success}
      onDismissError={() => setError(null)}
      onDismissSuccess={() => setSuccess(null)}
      footer={footer}
    >
      {step === 1 && renderStep1()}
      {step === 2 && renderStep2()}
    </WizardShell>
  );
}

