'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../lib/i18n';
import { settingsApi } from '../utils/settingsApi';
import { InlineAlert } from './InlineAlert';

interface GoogleOAuthConfig {
  client_id: string;
  client_secret: string;
  redirect_uri: string;
  backend_url: string;
  is_configured: boolean;
}

export function GoogleOAuthSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const [config, setConfig] = useState<GoogleOAuthConfig>({
    client_id: '',
    client_secret: '',
    redirect_uri: '',
    backend_url: '',
    is_configured: false,
  });

  const [form, setForm] = useState({
    client_id: '',
    client_secret: '',
    redirect_uri: '',
    backend_url: '',
  });

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await settingsApi.get<GoogleOAuthConfig>('/api/v1/system-settings/google-oauth');
      setConfig(data);
      setForm({
        client_id: data.client_id || '',
        client_secret: '', // Don't show existing secret
        redirect_uri: data.redirect_uri || '',
        backend_url: data.backend_url || '',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('failedToLoadOAuthConfiguration'));
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const updateData: any = {};
      if (form.client_id) updateData.client_id = form.client_id;
      if (form.client_secret) updateData.client_secret = form.client_secret;
      if (form.redirect_uri) updateData.redirect_uri = form.redirect_uri;
      if (form.backend_url) updateData.backend_url = form.backend_url;

      await settingsApi.put('/api/v1/system-settings/google-oauth', updateData);
      setSuccess(t('googleOAuthConfigurationSaved'));

      // Reload config
      await loadConfig();

      // Clear secret field if it was saved
      if (form.client_secret) {
        setForm({ ...form, client_secret: '' });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('failedToSaveOAuthConfiguration'));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    setError(null);

    try {
      const testData = await settingsApi.post<{
        success: boolean;
        valid: boolean;
        message: string;
        errors?: string[];
        warnings?: string[];
      }>('/api/v1/system-settings/google-oauth/test');

      if (testData.success && testData.valid) {
        setTestResult(`✅ ${testData.message}${testData.warnings?.length ? `\n⚠️ ${testData.warnings.join(', ')}` : ''}`);
      } else {
        setTestResult(`❌ ${testData.message}${testData.errors?.length ? `\n${testData.errors.join(', ')}` : ''}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('failedToTestOAuthConfiguration'));
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-4">
        <span className="text-gray-500">{t('loadingOAuthConfiguration')}</span>
      </div>
    );
  }

  // Auto-generate redirect URI if backend_url is set
  const suggestedRedirectUri = form.backend_url
    ? `${form.backend_url}/api/v1/tools/google-drive/oauth/callback`
    : '';

  // Get the actual redirect URI to copy (use form value or suggested)
  const redirectUriToCopy = form.redirect_uri || suggestedRedirectUri || 'http://localhost:8000/api/v1/tools/google-drive/oauth/callback';

  const handleCopyRedirectURI = async () => {
    if (!redirectUriToCopy) return;

    try {
      await navigator.clipboard.writeText(redirectUriToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = redirectUriToCopy;
      textArea.style.position = 'fixed';
      textArea.style.opacity = '0';
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (fallbackErr) {
        console.error('Failed to copy:', fallbackErr);
      }
      document.body.removeChild(textArea);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">{t('googleOAuthConfiguration')}</h3>
        <p className="text-sm text-gray-600 mb-4">
          {t('googleOAuthDescription')}{' '}
          <a
            href="https://console.cloud.google.com/apis/credentials"
            target="_blank"
            rel="noopener noreferrer"
            className="text-purple-600 hover:underline"
          >
            {t('googleCloudConsole')}
          </a>
          .
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}
      {success && <InlineAlert type="success" message={success} onDismiss={() => setSuccess(null)} />}
      {testResult && (
        <InlineAlert
          type={testResult.startsWith('✅') ? 'success' : 'error'}
          message={testResult}
          onDismiss={() => setTestResult(null)}
          className="whitespace-pre-line"
        />
      )}

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('googleClientID')} <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={form.client_id}
            onChange={(e) => setForm({ ...form, client_id: e.target.value })}
            placeholder="your-client-id.apps.googleusercontent.com"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            {t('googleClientIDDescription')}
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-sm font-medium text-gray-700">
              {t('googleClientSecret')} <span className="text-red-500">*</span>
            </label>
            {config.is_configured && (
              <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-md">
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
                {t('configured')}
              </span>
            )}
          </div>
          <input
            type="password"
            value={form.client_secret}
            onChange={(e) => setForm({ ...form, client_secret: e.target.value })}
            placeholder={config.is_configured ? t('googleClientSecretPlaceholderConfigured') : t('googleClientSecretPlaceholder')}
            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 ${
              config.is_configured
                ? 'border-green-300 bg-green-50 focus:ring-green-500'
                : 'border-gray-300 focus:ring-purple-500'
            }`}
          />
          <p className={`mt-1 text-xs ${
            config.is_configured
              ? 'text-green-600 font-medium'
              : 'text-gray-500'
          }`}>
            {config.is_configured
              ? t('googleClientSecretKeepExisting')
              : t('googleClientSecretDescription')}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('backendURL')} <span className="text-red-500">*</span>
          </label>
          <input
            type="url"
            value={form.backend_url}
            onChange={(e) => setForm({ ...form, backend_url: e.target.value })}
            placeholder="http://localhost:8000"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            {t('backendURLDescription')}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('redirectURI')} <span className="text-gray-500">{t('redirectURIOptional')}</span>
          </label>
          <div className="flex gap-2">
            <input
              type="url"
              value={form.redirect_uri}
              onChange={(e) => setForm({ ...form, redirect_uri: e.target.value })}
              placeholder={suggestedRedirectUri || 'http://localhost:8000/api/v1/tools/google-drive/oauth/callback'}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <button
              type="button"
              onClick={handleCopyRedirectURI}
              disabled={!redirectUriToCopy}
              className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium text-gray-700 whitespace-nowrap"
              title={t('copyRedirectURI')}
            >
              {copied ? (
                <span className="flex items-center gap-1 text-green-600">
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                  {t('redirectURICopied')}
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  {t('copyRedirectURI')}
                </span>
              )}
            </button>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            {t('redirectURIDescription')}
            {suggestedRedirectUri && (
              <span className="block mt-1 text-purple-600">
                {t('redirectURISuggested')} {suggestedRedirectUri}
              </span>
            )}
          </p>
          <p className="mt-1 text-xs text-yellow-600">
            {t('redirectURIWarning')}
          </p>
        </div>

        {config.is_configured && (
          <div className="bg-green-50 border border-green-200 rounded-md p-3">
            <div className="flex items-start">
              <svg className="h-5 w-5 text-green-400 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <div className="ml-3">
                <p className="text-sm font-medium text-green-800">{t('oauthConfigurationActive')}</p>
                <p className="text-xs text-green-700 mt-1">
                  {t('oauthConfigurationActiveDescription')}
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleTest}
            disabled={testing || !form.client_id || (!form.client_secret && !config.is_configured)}
            className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            {testing ? t('testingConfiguration') : t('testConfiguration')}
          </button>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !form.client_id || !form.backend_url}
            className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
          >
            {saving ? t('saving') : t('saveConfiguration')}
          </button>
        </div>
      </div>
    </div>
  );
}
