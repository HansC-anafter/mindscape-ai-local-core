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
      console.log('Loaded config from backend:', {
        client_id: data.client_id ? `${data.client_id.substring(0, 30)}...` : 'empty',
        backend_url: data.backend_url || 'empty',
        redirect_uri: data.redirect_uri || 'empty',
        is_configured: data.is_configured,
      });

      setConfig(data);

      // Use default values if empty to ensure buttons are enabled
      const defaultBackendUrl = 'http://localhost:8000';
      const backendUrl = data.backend_url || defaultBackendUrl;
      const redirectUri = data.redirect_uri || (backendUrl ? `${backendUrl}/api/v1/tools/google-drive/oauth/callback` : '');

      setForm({
        client_id: data.client_id || '',
        client_secret: '', // Don't show existing secret
        redirect_uri: redirectUri,
        backend_url: backendUrl,
      });
    } catch (err) {
      console.error('Failed to load config:', err);
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

      // Always send values if they exist and are not empty
      if (form.client_id && form.client_id.trim()) {
        updateData.client_id = form.client_id.trim();
      }
      if (form.client_secret && form.client_secret.trim()) {
        updateData.client_secret = form.client_secret.trim();
      }
      if (form.redirect_uri && form.redirect_uri.trim()) {
        updateData.redirect_uri = form.redirect_uri.trim();
      }
      if (form.backend_url && form.backend_url.trim()) {
        updateData.backend_url = form.backend_url.trim();
      }

      console.log('Saving Google OAuth config:', {
        client_id: updateData.client_id ? `${updateData.client_id.substring(0, 30)}...` : 'not sent',
        client_secret: updateData.client_secret ? '*** (hidden)' : 'not sent',
        redirect_uri: updateData.redirect_uri || 'not sent',
        backend_url: updateData.backend_url || 'not sent',
      });

      console.log('Sending save request with data:', {
        client_id: updateData.client_id ? `${updateData.client_id.substring(0, 40)}...` : 'not sent',
        client_secret: updateData.client_secret ? '*** (hidden)' : 'not sent',
        redirect_uri: updateData.redirect_uri || 'not sent',
        backend_url: updateData.backend_url || 'not sent',
      });

      const response = await settingsApi.put('/api/v1/system-settings/google-oauth', updateData);
      console.log('Save response:', response);

      setSuccess(t('googleOAuthConfigurationSaved'));

      // Update config status to reflect saved state
      setConfig((prev) => ({
        ...prev,
        client_id: updateData.client_id || prev.client_id,
        redirect_uri: updateData.redirect_uri || prev.redirect_uri,
        backend_url: updateData.backend_url || prev.backend_url,
        is_configured: !!(updateData.client_id || prev.client_id),
      }));

      // Only clear secret field if it was saved, keep all other form values
      if (updateData.client_secret) {
        setForm((prev) => ({
          ...prev,
          client_secret: '', // Only clear secret field, preserve client_id, redirect_uri, backend_url
        }));
      }

      // DON'T reload from server here - it would overwrite form values with empty database values
    } catch (err) {
      console.error('Failed to save Google OAuth config:', err);
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
      // Send current form values for testing
      const testPayload: any = {};

      // Always send client_id from form if it has a value
      const clientIdValue = form.client_id?.trim();
      if (clientIdValue) {
        testPayload.client_id = clientIdValue;
      }

      // Send client_secret from form if provided
      const clientSecretValue = form.client_secret?.trim();
      if (clientSecretValue) {
        testPayload.client_secret = clientSecretValue;
      }

      console.log('Sending test request:', {
        form_client_id: form.client_id ? `${form.client_id.substring(0, 40)}...` : 'empty',
        form_client_secret: form.client_secret ? '*** (hidden)' : 'empty',
        payload_keys: Object.keys(testPayload),
        payload_client_id: testPayload.client_id ? `${testPayload.client_id.substring(0, 40)}...` : 'not sent',
        payload_client_secret: testPayload.client_secret ? 'sent (hidden)' : 'not sent',
      });

      const testData = await settingsApi.post<{
        success: boolean;
        valid: boolean;
        message: string;
        errors?: string[];
        warnings?: string[];
      }>('/api/v1/system-settings/google-oauth/test', testPayload);

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
        <span className="text-gray-500 dark:text-gray-400">{t('loadingOAuthConfiguration')}</span>
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
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">{t('googleOAuthConfiguration')}</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          {t('googleOAuthDescription')}{' '}
          <a
            href="https://console.cloud.google.com/apis/credentials"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-600 dark:text-gray-400 hover:underline"
          >
            {t('googleCloudConsole')}
          </a>
          .
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}

      {success && (
        <div className="mb-4 p-3 rounded-md bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
          <div className="flex items-start">
            <svg className="h-5 w-5 text-green-400 dark:text-green-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            <div className="ml-3 flex-1">
              <p className="text-sm font-medium text-green-800 dark:text-green-300">{success}</p>
              {config.is_configured && (
                <p className="text-xs text-green-700 dark:text-green-400 mt-1">
                  {t('oauthConfigurationActiveDescription')}
                </p>
              )}
            </div>
            <button
              onClick={() => setSuccess(null)}
              className="ml-3 text-green-400 dark:text-green-500 hover:text-green-600 dark:hover:text-green-400"
            >
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('googleClientID')} <span className="text-red-500 dark:text-red-400">*</span>
            </label>
            {config.is_configured && form.client_id && (
              <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md">
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
                {t('configured')}
              </span>
            )}
          </div>
          <input
            type="text"
            value={form.client_id}
            onChange={(e) => setForm({ ...form, client_id: e.target.value })}
            placeholder="your-client-id.apps.googleusercontent.com"
            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 ${
              config.is_configured && form.client_id
                ? 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 focus:ring-green-500 dark:focus:ring-green-400 text-gray-900 dark:text-gray-100'
                : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 focus:ring-gray-500 dark:focus:ring-gray-500 text-gray-900 dark:text-gray-100'
            }`}
          />
          <p className={`mt-1 text-xs ${
            config.is_configured && form.client_id
              ? 'text-green-600 dark:text-green-400 font-medium'
              : 'text-gray-500 dark:text-gray-400'
          }`}>
            {config.is_configured && form.client_id
              ? `✓ ${t('googleClientIDDescription')}`
              : t('googleClientIDDescription')}
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('googleClientSecret')} <span className="text-red-500 dark:text-red-400">*</span>
            </label>
            {config.is_configured && (
              <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md">
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
                ? 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 focus:ring-green-500 dark:focus:ring-green-400 text-gray-900 dark:text-gray-100'
                : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 focus:ring-gray-500 dark:focus:ring-gray-500 text-gray-900 dark:text-gray-100'
            }`}
          />
          <p className={`mt-1 text-xs ${
            config.is_configured
              ? 'text-green-600 dark:text-green-400 font-medium'
              : 'text-gray-500 dark:text-gray-400'
          }`}>
            {config.is_configured
              ? t('googleClientSecretKeepExisting')
              : t('googleClientSecretDescription')}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('backendURL')} <span className="text-red-500 dark:text-red-400">*</span>
          </label>
          <input
            type="url"
            value={form.backend_url}
            onChange={(e) => setForm({ ...form, backend_url: e.target.value })}
            placeholder="http://localhost:8000"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {t('backendURLDescription')}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('redirectURI')} <span className="text-gray-500 dark:text-gray-400">{t('redirectURIOptional')}</span>
          </label>
          <div className="flex gap-2">
            <input
              type="url"
              value={form.redirect_uri}
              onChange={(e) => setForm({ ...form, redirect_uri: e.target.value })}
              placeholder={suggestedRedirectUri || 'http://localhost:8000/api/v1/tools/google-drive/oauth/callback'}
              className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
            <button
              type="button"
              onClick={handleCopyRedirectURI}
              disabled={!redirectUriToCopy}
              className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap bg-white dark:bg-gray-800"
              title={t('copyRedirectURI')}
            >
              {copied ? (
                <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
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
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {t('redirectURIDescription')}
            {suggestedRedirectUri && (
              <span className="block mt-1 text-gray-600 dark:text-gray-400">
                {t('redirectURISuggested')} {suggestedRedirectUri}
              </span>
            )}
          </p>
          <p className="mt-1 text-xs text-yellow-600 dark:text-yellow-400">
            {t('redirectURIWarning')}
          </p>
        </div>

        {config.is_configured && (
          <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md p-3">
            <div className="flex items-start">
              <svg className="h-5 w-5 text-green-400 dark:text-green-500 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <div className="ml-3">
                <p className="text-sm font-medium text-green-800 dark:text-green-300">{t('oauthConfigurationActive')}</p>
                <p className="text-xs text-green-700 dark:text-green-400 mt-1">
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
            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
          >
            {testing ? t('testingConfiguration') : t('testConfiguration')}
          </button>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !form.client_id || !form.backend_url}
            className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50"
          >
            {saving ? t('saving') : t('saveConfiguration')}
          </button>
        </div>

        {testResult && (
          <InlineAlert
            type={testResult.startsWith('✅') ? 'success' : 'error'}
            message={testResult}
            onDismiss={() => setTestResult(null)}
            className="whitespace-pre-line"
          />
        )}
      </div>
    </div>
  );
}
