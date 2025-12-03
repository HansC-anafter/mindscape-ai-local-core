'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';

interface CanvaConnectionWizardProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function CanvaConnectionWizard({ onClose, onSuccess }: CanvaConnectionWizardProps) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    connection_id: 'canva-1',
    name: 'My Canva Account',
    oauth_token: '',
    client_id: '',
    client_secret: '',
    api_key: '',
    base_url: 'https://api.canva.com/rest/v1',
    brand_id: '',
    redirect_uri: '',
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
        const redirectUrl = `/api/v1/tools/canva/oauth/authorize?connection_id=${form.connection_id}&connection_name=${encodeURIComponent(form.name)}${form.client_id ? `&client_id=${form.client_id}` : ''}`;
        window.location.href = redirectUrl;
        return;
      }

      const discoverResult = await settingsApi.post<{
        success: boolean;
        connection_id: string;
        discovered_tools: unknown[];
        tools_count: number;
      }>(
        '/api/v1/tools/canva/discover',
        {
          connection_id: form.connection_id,
          name: form.name,
          oauth_token: form.oauth_token || undefined,
          client_id: form.client_id || undefined,
          client_secret: form.client_secret || undefined,
          api_key: form.api_key || undefined,
          base_url: form.base_url,
          brand_id: form.brand_id || undefined,
          redirect_uri: form.redirect_uri || undefined,
        }
      );

      const result = await settingsApi.post<{
        id: string;
        name: string;
        tool_type: string;
        [key: string]: any;
      }>(
        '/api/v1/tools/canva/connect',
        {
          connection_id: form.connection_id,
          name: form.name,
          oauth_token: form.oauth_token || undefined,
          client_id: form.client_id || undefined,
          client_secret: form.client_secret || undefined,
          api_key: form.api_key || undefined,
          base_url: form.base_url,
          brand_id: form.brand_id || undefined,
          redirect_uri: form.redirect_uri || undefined,
        }
      );

      setSuccess(
        `${t('canvaConnectionSuccess') || 'Canva connected successfully'}! ${discoverResult.tools_count || 0} ${t('toolsCount') || 'tools'} discovered.`
      );
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect Canva');
    } finally {
      setConnecting(false);
    }
  };

  const renderStep1 = () => (
    <div>
      <h4 className="text-sm font-medium text-gray-700 mb-3">
        {t('selectCanvaAuthMethod') || 'Select Authentication Method'}
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
            {t('canvaOAuthDescription') || 'Secure OAuth authentication via Canva Developer Portal'}
          </div>
        </button>
        <button
          onClick={() => {
            setUseOAuth(false);
            setStep(2);
          }}
          className="w-full p-4 border border-gray-300 rounded-md hover:border-purple-500 hover:bg-purple-50 text-left"
        >
          <div className="font-medium text-gray-900">API Key</div>
          <div className="text-xs text-gray-500 mt-1">
            {t('canvaAPIKeyDescription') || 'Direct API key authentication (if available)'}
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
              {t('connectionName') || 'Connection Name'}
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="e.g., My Canva Account"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('canvaClientID') || 'Canva Client ID'}
            </label>
            <input
              type="text"
              value={form.client_id}
              onChange={(e) => setForm({ ...form, client_id: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="From Canva Developer Portal"
            />
            <p className="text-xs text-gray-500 mt-1">
              {t('canvaClientIDDescription') || 'Get this from your Canva Developer Portal application'}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('canvaClientSecret') || 'Canva Client Secret'}
            </label>
            <input
              type="password"
              value={form.client_secret}
              onChange={(e) => setForm({ ...form, client_secret: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="From Canva Developer Portal"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('canvaRedirectURI') || 'Redirect URI (Optional)'}
            </label>
            <input
              type="url"
              value={form.redirect_uri}
              onChange={(e) => setForm({ ...form, redirect_uri: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="http://localhost:8000/api/tools/canva/oauth/callback"
            />
            <p className="text-xs text-gray-500 mt-1">
              {t('canvaRedirectURIDescription') || 'Must match the redirect URI configured in your Canva Developer Portal'}
            </p>
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
            <p className="text-sm text-blue-800">
              {t('canvaOAuthFlowNote') || 'After clicking "Connect", you will be redirected to Canva to authorize the connection.'}
            </p>
          </div>
        </div>
      );
    } else {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('connectionName') || 'Connection Name'}
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="e.g., My Canva Account"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('canvaAPIKey') || 'Canva API Key'}
            </label>
            <input
              type="password"
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="Your Canva API Key"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('canvaBaseURL') || 'Base URL'}
            </label>
            <input
              type="url"
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="https://api.canva.com/rest/v1"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('canvaBrandID') || 'Brand ID (Optional)'}
            </label>
            <input
              type="text"
              value={form.brand_id}
              onChange={(e) => setForm({ ...form, brand_id: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="Your Canva Brand ID"
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
          className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700"
        >
          {t('next') || 'Next'}
        </button>
      ) : (
        <button
          onClick={handleConnect}
          disabled={connecting || !form.name || (useOAuth ? (!form.client_id || !form.client_secret) : !form.api_key)}
          className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
        >
          {connecting ? (t('connecting') || 'Connecting...') : (t('connect') || 'Connect')}
        </button>
      )}
    </>
  );

  return (
    <WizardShell
      title={t('connectCanva') || 'Connect Canva'}
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

