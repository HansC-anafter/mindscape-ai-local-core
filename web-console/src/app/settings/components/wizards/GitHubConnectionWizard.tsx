'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';

interface GitHubConnectionWizardProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function GitHubConnectionWizard({ onClose, onSuccess }: GitHubConnectionWizardProps) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    connection_id: 'github-account-1',
    name: 'My GitHub Account',
    oauth_token: '',
    client_id: '',
    client_secret: '',
    access_token: '',
  });
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [useOAuth, setUseOAuth] = useState(true);

  const handleConnect = async () => {
    setConnecting(true);
    setError(null);
    setSuccess(null);

    try {
      if (useOAuth && !form.oauth_token) {
        const redirectUrl = `/api/v1/tools/github/oauth/authorize?connection_id=${form.connection_id}&connection_name=${encodeURIComponent(form.name)}${form.client_id ? `&client_id=${form.client_id}` : ''}`;
        window.location.href = redirectUrl;
        return;
      }

      const discoverResult = await settingsApi.post<{
        success: boolean;
        connection_id: string;
        discovered_tools: unknown[];
        tools_count: number;
      }>(
        '/api/v1/tools/github/discover',
        {
          connection_id: form.connection_id,
          name: form.name,
          oauth_token: form.oauth_token || undefined,
          access_token: form.access_token || undefined,
          client_id: form.client_id || undefined,
          client_secret: form.client_secret || undefined,
        }
      );

      const result = await settingsApi.post<{
        id: string;
        name: string;
        tool_type: string;
        [key: string]: any;
      }>(
        '/api/v1/tools/github/connect',
        {
          connection_id: form.connection_id,
          name: form.name,
          oauth_token: form.oauth_token || undefined,
          access_token: form.access_token || undefined,
          client_id: form.client_id || undefined,
          client_secret: form.client_secret || undefined,
        }
      );

      setSuccess(
        `${t('githubConnectionSuccess')}! ${discoverResult.tools_count || 0} ${t('toolsCount')} discovered.`
      );
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect GitHub');
    } finally {
      setConnecting(false);
    }
  };

  const renderStep1 = () => (
    <div>
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
        {t('selectGitHubAuthMethod')}
      </h4>
      <div className="space-y-3">
        <button
          onClick={() => {
            setUseOAuth(true);
            setStep(2);
          }}
          className="w-full p-4 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800 text-left transition-colors"
        >
          <div className="font-medium text-gray-900 dark:text-gray-100">OAuth 2.0 (Recommended)</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('githubOAuthDescription')}
          </div>
        </button>
        <button
          onClick={() => {
            setUseOAuth(false);
            setStep(2);
          }}
          className="w-full p-4 border border-gray-300 dark:border-gray-600 rounded-md hover:border-gray-500 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800 text-left transition-colors"
        >
          <div className="font-medium text-gray-900 dark:text-gray-100">Personal Access Token</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('githubTokenDescription')}
          </div>
        </button>
      </div>
    </div>
  );

  const renderStep2 = () => {
    if (useOAuth) {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('connectionName')}
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              placeholder="e.g., My GitHub Account"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('githubClientID')}
            </label>
            <input
              type="text"
              value={form.client_id}
              onChange={(e) => setForm({ ...form, client_id: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              placeholder="From GitHub App settings"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {t('githubClientIDDescription')}
            </p>
          </div>

          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-3">
            <p className="text-sm text-blue-800 dark:text-blue-300">
              {t('githubOAuthFlowNote')}
            </p>
          </div>
        </div>
      );
    } else {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('connectionName')}
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              placeholder="e.g., My GitHub Account"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('githubPersonalAccessToken')}
            </label>
            <input
              type="password"
              value={form.access_token}
              onChange={(e) => setForm({ ...form, access_token: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              placeholder="ghp_..."
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {t('githubTokenDescriptionFull')}
            </p>
          </div>
        </div>
      );
    }
  };

  const footer = (
    <>
      <button
        onClick={step === 1 ? onClose : () => setStep(1)}
        className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
      >
        {step === 1 ? t('cancel') : t('back')}
      </button>
      <button
        onClick={step === 1 ? () => {} : handleConnect}
        disabled={connecting || (step === 2 && !form.name && (!useOAuth || !form.access_token))}
        className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {connecting
          ? t('connecting')
          : step === 1
          ? t('next')
          : t('connect')}
      </button>
    </>
  );

  return (
    <WizardShell
      title={t('connectGitHub')}
      onClose={onClose}
      error={error}
      success={success}
      onDismissError={() => setError(null)}
      onDismissSuccess={() => setSuccess(null)}
      footer={footer}
    >
      {step === 1 ? renderStep1() : renderStep2()}
    </WizardShell>
  );
}

