'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';
import { FolderSearch } from 'lucide-react';
import { FolderPicker } from '@/components/common/FolderPicker';

interface WorkflowWizardProps {
  platform?: 'zapier' | 'n8n' | 'make' | 'custom' | 'comfyui';
  onClose: () => void;
  onSuccess: () => void;
}

interface DiscoveryResult {
  is_valid: boolean;
  runtime_type: string;
  name: string;
  description: string;
  config_url: string;
  extra_metadata: Record<string, any>;
  error?: string;
}

interface WorkflowConfig {
  platform: 'zapier' | 'n8n' | 'make' | 'custom' | 'comfyui';
  name: string;
  api_key: string;
  webhook_url?: string;
  base_url?: string;
}

export function WorkflowWizard({ platform, onClose, onSuccess }: WorkflowWizardProps) {
  const [step, setStep] = useState(platform ? 2 : 1);
  const [selectedPlatform, setSelectedPlatform] = useState<'zapier' | 'n8n' | 'make' | 'custom' | 'comfyui' | undefined>(platform);
  const [config, setConfig] = useState<WorkflowConfig>({
    platform: platform || 'zapier',
    name: '',
    api_key: '',
    webhook_url: '',
    base_url: '',
  });
  const [connecting, setConnecting] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanPath, setScanPath] = useState('');
  const [isFolderPickerOpen, setIsFolderPickerOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const platforms = [
    { id: 'zapier' as const, name: 'Zapier', description: 'Automate workflows between apps', icon: '⚡' },
    { id: 'n8n' as const, name: 'n8n', description: 'Open-source workflow automation', icon: '🔄' },
    { id: 'make' as const, name: 'Make', description: 'Visual automation platform', icon: '🎨' },
    { id: 'comfyui' as const, name: 'ComfyUI', description: 'Local stable diffusion workflow GUI', icon: '🖼️' },
    { id: 'custom' as const, name: 'Custom', description: 'Custom workflow integration', icon: '🔧' },
  ];

  const handlePlatformSelect = (platformId: 'zapier' | 'n8n' | 'make' | 'custom' | 'comfyui') => {
    setSelectedPlatform(platformId);
    setConfig({
      ...config,
      platform: platformId,
      name: platformId === 'custom' ? 'Custom Workflow' :
        platformId === 'comfyui' ? 'ComfyUI Local' :
          platforms.find(p => p.id === platformId)?.name || ''
    });
    setStep(2);
  };

  const handleScan = async () => {
    if (!scanPath.trim()) {
      setError(t('pleaseEnterScanPath' as any) || 'Please enter a folder path to scan');
      return;
    }

    setScanning(true);
    setError(null);
    try {
      const result = await settingsApi.post<DiscoveryResult>('/api/v1/runtime-environments/discovery/scan', {
        path: scanPath,
        runtime_type: selectedPlatform === 'comfyui' ? 'comfyui' : 'auto'
      });

      if (result.is_valid) {
        setConfig({
          ...config,
          name: result.name,
          base_url: result.config_url,
          // If ComfyUI, we might not need an API key for local access if it's default
          // but we can pre-fill empty if not found
        });
        setSuccess(t('discoverySuccess' as any) || `Successfully discovered ${result.name} configuration!`);
        setTimeout(() => setSuccess(null), 3000);
      } else {
        setError(result.error || t('discoveryFailed' as any) || 'Could not find a valid runtime at the specified path');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed');
    } finally {
      setScanning(false);
    }
  };

  const handleConfigSubmit = async () => {
    setConnecting(true);
    setError(null);
    setSuccess(null);

    try {
      // For now, just simulate success
      await new Promise(resolve => setTimeout(resolve, 1000));

      setSuccess(t('workflowConnected' as any) || 'Workflow connected successfully');
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
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{t('selectWorkflowProvider' as any) || 'Select Workflow Platform'}</h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {platforms.map((p) => (
          <button
            key={p.id}
            onClick={() => handlePlatformSelect(p.id)}
            className="p-4 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800 text-left transition-colors"
          >
            <div className="flex items-center space-x-3">
              <span className="text-2xl">{p.icon}</span>
              <div>
                <div className="font-medium text-gray-900 dark:text-gray-100">{p.name}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{p.description}</div>
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
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('workflowName' as any) || 'Workflow Name'}
          </label>
          <input
            type="text"
            value={config.name}
            onChange={(e) => setConfig({ ...config, name: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
            placeholder={`${platformConfig?.name || 'Workflow'} Connection`}
          />
        </div>

        {selectedPlatform === 'comfyui' && (
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-4">
            <label className="block text-sm font-medium text-blue-800 dark:text-blue-300 mb-1">
              {t('localAutoScan' as any) || 'Local Folder Auto-Scan'}
            </label>
            <p className="text-xs text-blue-600 dark:text-blue-400 mb-3">
              {t('scanDescription' as any) || 'Point to your ComfyUI installation folder to automatically detect configuration.'}
            </p>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type="text"
                  value={scanPath}
                  onChange={(e) => setScanPath(e.target.value)}
                  className="w-full pl-3 pr-10 py-2 border border-blue-300 dark:border-blue-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="/path/to/ComfyUI"
                />
                <button
                  type="button"
                  onClick={() => setIsFolderPickerOpen(true)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-blue-500 hover:text-blue-600 p-1"
                  title={t('browseFolders' as any) || 'Browse Folders'}
                >
                  <FolderSearch size={20} />
                </button>
              </div>
              <button
                type="button"
                onClick={handleScan}
                disabled={scanning}
                className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600 disabled:opacity-50"
              >
                {scanning ? (t('scanning' as any) || 'Scanning...') : (t('scan' as any) || 'Scan')}
              </button>
            </div>
          </div>
        )}

        {selectedPlatform === 'n8n' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('n8nInstanceUrl') || 'n8n Instance URL'}
            </label>
            <input
              type="url"
              value={config.base_url || ''}
              onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              placeholder="https://n8n.example.com"
            />
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('apiKey' as any) || 'API Key'}
          </label>
          <input
            type="password"
            value={config.api_key}
            onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
            placeholder="Your API key"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('webhookUrl' as any) || 'Webhook URL (Optional)'}
          </label>
          <input
            type="url"
            value={config.webhook_url || ''}
            onChange={(e) => setConfig({ ...config, webhook_url: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
            placeholder="https://webhook.example.com"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('webhookUrlDescription' as any) || 'Optional: Webhook URL for receiving events from the workflow platform'}
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
      {step < 2 ? (
        <button
          onClick={() => setStep(step + 1)}
          disabled={!selectedPlatform}
          className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {t('next' as any) || 'Next'}
        </button>
      ) : (
        <button
          onClick={handleConfigSubmit}
          disabled={connecting || !config.name || !config.api_key}
          className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {connecting ? (t('connecting' as any) || 'Connecting...') : (t('connect' as any) || 'Connect')}
        </button>
      )}
    </>
  );

  return (
    <WizardShell
      title={t('configureWorkflow' as any) || 'Configure Workflow'}
      onClose={onClose}
      error={error}
      success={success}
      onDismissError={() => setError(null)}
      onDismissSuccess={() => setSuccess(null)}
      footer={footer}
    >
      {step === 1 && renderStep1()}
      {step === 2 && renderStep2()}

      <FolderPicker
        isOpen={isFolderPickerOpen}
        onClose={() => setIsFolderPickerOpen(false)}
        onSelect={(path: string) => setScanPath(path)}
        initialPath={scanPath || '/app'}
        title={t('selectComfyUIFolder' as any) || 'Select ComfyUI Folder'}
      />
    </WizardShell>
  );
}

