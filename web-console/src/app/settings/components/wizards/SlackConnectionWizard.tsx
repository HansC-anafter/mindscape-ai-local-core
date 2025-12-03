'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';

interface SlackConnectionWizardProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function SlackConnectionWizard({ onClose, onSuccess }: SlackConnectionWizardProps) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    connection_id: 'slack-workspace-1',
    name: 'My Slack Workspace',
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
        const redirectUrl = `/api/v1/tools/slack/oauth/authorize?connection_id=${form.connection_id}&connection_name=${encodeURIComponent(form.name)}${form.client_id ? `&client_id=${form.client_id}` : ''}`;
        window.location.href = redirectUrl;
        return;
      }

      const discoverResult = await settingsApi.post<{
        success: boolean;
        connection_id: string;
        discovered_tools: unknown[];
        tools_count: number;
      }>(
        '/api/v1/tools/slack/discover',
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
        '/api/v1/tools/slack/connect',
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
        `${t('slackConnectionSuccess')}! ${discoverResult.tools_count || 0} ${t('toolsCount')} discovered.`
      );
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect Slack');
    } finally {
      setConnecting(false);
    }
  };

  const renderStep1 = () => (
    <div>
      <h4 className="text-sm font-medium text-gray-700 mb-3">
        {t('selectSlackAuthMethod')}
      </h4>
      <div className="space-y-3">
        <button
          onClick={() => {
            setUseOAuth(true);
            setStep(2);
          }}
          className="w-full p-4 border border-gray-300 rounded-md hover:border-purple-500 hover:bg-purple-50 text-left"
        >
          <div className="font-medium text-gray-900">OAuth 2.0 (Recommended)</div>
          <div className="text-xs text-gray-500 mt-1">
            {t('slackOAuthDescription')}
          </div>
        </button>
        <button
          onClick={() => {
            setUseOAuth(false);
            setStep(2);
          }}
          className="w-full p-4 border border-gray-300 rounded-md hover:border-purple-500 hover:bg-purple-50 text-left"
        >
          <div className="font-medium text-gray-900">Access Token</div>
          <div className="text-xs text-gray-500 mt-1">
            {t('slackTokenDescription')}
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
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('connectionName')}
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="e.g., My Slack Workspace"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('slackClientID')}
            </label>
            <input
              type="text"
              value={form.client_id}
              onChange={(e) => setForm({ ...form, client_id: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="From Slack App settings"
            />
            <p className="text-xs text-gray-500 mt-1">
              {t('slackClientIDDescription')}
            </p>
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
            <p className="text-sm text-blue-800">
              {t('slackOAuthFlowNote')}
            </p>
          </div>
        </div>
      );
    } else {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('connectionName')}
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="e.g., My Slack Workspace"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('slackAccessToken')}
            </label>
            <input
              type="password"
              value={form.access_token}
              onChange={(e) => setForm({ ...form, access_token: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="xoxb-... or xoxp-..."
            />
            <p className="text-xs text-gray-500 mt-1">
              {t('slackAccessTokenDescription')}
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
        className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
      >
        {step === 1 ? t('cancel') : t('back')}
      </button>
      <button
        onClick={step === 1 ? () => {} : handleConnect}
        disabled={connecting || (step === 2 && !form.name && (!useOAuth || !form.access_token))}
        className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
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
      title={t('connectSlack')}
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

