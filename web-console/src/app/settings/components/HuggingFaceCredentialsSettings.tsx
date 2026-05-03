'use client';

import Link from 'next/link';
import React, { useEffect, useState } from 'react';
import { t } from '../../../lib/i18n';
import { settingsApi } from '../utils/settingsApi';
import { InlineAlert } from './InlineAlert';

interface HuggingFaceAuthConfig {
  api_key_configured: boolean;
  api_key?: string;
  source?: string;
  credential_kind?: string;
}

export function HuggingFaceCredentialsSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [config, setConfig] = useState<HuggingFaceAuthConfig>({
    api_key_configured: false,
    source: 'none',
    credential_kind: 'access_token',
  });
  const [apiKey, setApiKey] = useState('');

  useEffect(() => {
    void loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await settingsApi.get<HuggingFaceAuthConfig>('/api/v1/system-settings/huggingface-auth');
      setConfig(data);
      setApiKey('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Hugging Face credentials');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) {
      setError('Enter a Hugging Face access token');
      return;
    }
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      const response = await settingsApi.put<{ success: boolean; message: string; api_key_configured: boolean }>(
        '/api/v1/system-settings/huggingface-auth',
        { api_key: apiKey.trim() }
      );
      setSuccess(response.message || 'Hugging Face access token saved');
      setConfig((prev) => ({
        ...prev,
        api_key_configured: true,
        api_key: '***',
        source: 'system_settings:huggingface_api_key',
      }));
      setApiKey('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save Hugging Face credentials');
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    try {
      setClearing(true);
      setError(null);
      setSuccess(null);
      const response = await settingsApi.put<{ success: boolean; message: string; api_key_configured: boolean }>(
        '/api/v1/system-settings/huggingface-auth',
        { clear: true }
      );
      setSuccess(response.message || 'Hugging Face access token cleared');
      setConfig({
        api_key_configured: false,
        api_key: '',
        source: 'none',
        credential_kind: 'access_token',
      });
      setApiKey('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear Hugging Face credentials');
    } finally {
      setClearing(false);
    }
  };

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">{t('loading' as any)}</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
          {t('huggingFaceCredentialTitle' as any)}
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {t('huggingFaceCredentialDescription' as any)}
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}
      {success && <InlineAlert type="success" message={success} onDismiss={() => setSuccess(null)} />}

      <div className="rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 p-4">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <div className="text-sm font-medium text-primary dark:text-gray-100">
              {t('credentialStatus' as any)}
            </div>
            <div className="text-sm text-secondary dark:text-gray-400 mt-1">
              {config.api_key_configured
                ? t('huggingFaceCredentialConfigured' as any)
                : t('huggingFaceCredentialMissing' as any)}
            </div>
          </div>
          <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${
            config.api_key_configured
              ? 'bg-green-50 text-green-700 border border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800'
              : 'bg-yellow-50 text-yellow-700 border border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-300 dark:border-yellow-800'
          }`}>
            {config.api_key_configured ? t('configured' as any) : t('notConfigured' as any)}
          </span>
        </div>

        <div className="text-xs text-secondary dark:text-gray-400 mb-4">
          {t('huggingFaceCredentialUsageHint' as any)}
        </div>

        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">
              {t('huggingFaceAccessToken' as any)}
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                config.api_key_configured
                  ? (t('huggingFaceAccessTokenPlaceholderConfigured' as any) || '*** (configured; enter a new value to update)')
                  : (t('huggingFaceAccessTokenPlaceholder' as any) || 'Enter Hugging Face access token')
              }
              className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 bg-surface-accent dark:bg-gray-900 text-primary dark:text-gray-100"
            />
            <p className="mt-2 text-xs text-secondary dark:text-gray-400">
              {t('huggingFaceAccessTokenHelp' as any)}
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-gray-700 text-white rounded-md hover:bg-gray-800 disabled:opacity-50"
            >
              {saving ? (t('saving' as any) || 'Saving...') : (t('saveCredential' as any) || 'Save Credential')}
            </button>
            <button
              type="button"
              onClick={handleClear}
              disabled={clearing || !config.api_key_configured}
              className="px-4 py-2 border border-default dark:border-gray-600 rounded-md text-primary dark:text-gray-200 hover:bg-surface-accent dark:hover:bg-gray-700 disabled:opacity-50"
            >
              {clearing ? (t('clearingCredential' as any) || 'Clearing...') : (t('clearCredential' as any) || 'Clear Credential')}
            </button>
          </div>
        </form>
      </div>

      <div className="rounded-lg border border-blue-200 dark:border-blue-900/60 bg-blue-50/70 dark:bg-blue-950/20 p-4">
        <div className="text-sm font-medium text-primary dark:text-gray-100 mb-2">
          Operating Guide
        </div>
        <div className="space-y-2 text-sm text-secondary dark:text-gray-400">
          <p>
            This Hugging Face access token is used for Hugging Face model downloads and shared LAF / ComfyUI weight synchronization.
          </p>
          <p>
            If your ComfyUI installation is not in the default location, open
            {' '}
            <Link
              href="/settings?tab=runtime"
              className="text-blue-700 dark:text-blue-300 underline underline-offset-2 hover:text-blue-800 dark:hover:text-blue-200"
            >
              Runtime Environments
            </Link>
            {' '}
            and select the `ComfyUI Local` card to set the installation path. This keeps preview and render runtimes from reading the wrong local path.
          </p>
          <p>
            To manage the Hugging Face model catalog, open
            {' '}
            <Link
              href="/settings?tab=basic&section=models-and-quota"
              className="text-blue-700 dark:text-blue-300 underline underline-offset-2 hover:text-blue-800 dark:hover:text-blue-200"
            >
              Basic Settings &gt; Models and Quota
            </Link>
            .
          </p>
          <p>
            If you have not created a token yet, open
            {' '}
            <a
              href="https://huggingface.co/settings/tokens"
              target="_blank"
              rel="noreferrer"
              className="text-blue-700 dark:text-blue-300 underline underline-offset-2 hover:text-blue-800 dark:hover:text-blue-200"
            >
              Hugging Face Access Tokens
            </a>
            {' '}
            and paste the token here after creating it.
          </p>
        </div>
      </div>
    </div>
  );
}
