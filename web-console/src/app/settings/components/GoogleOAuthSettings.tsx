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
      setError(err instanceof Error ? err.message : 'Failed to load OAuth configuration');
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
      setSuccess('Google OAuth configuration saved successfully');

      // Reload config
      await loadConfig();

      // Clear secret field if it was saved
      if (form.client_secret) {
        setForm({ ...form, client_secret: '' });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save OAuth configuration');
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
      setError(err instanceof Error ? err.message : 'Failed to test OAuth configuration');
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-4">
        <span className="text-gray-500">Loading OAuth configuration...</span>
      </div>
    );
  }

  // Auto-generate redirect URI if backend_url is set
  const suggestedRedirectUri = form.backend_url
    ? `${form.backend_url}/api/tools/google-drive/oauth/callback`
    : '';

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">Google OAuth Configuration</h3>
        <p className="text-sm text-gray-600 mb-4">
          Configure Google OAuth 2.0 credentials for Google Drive integration.
          Get credentials from{' '}
          <a
            href="https://console.cloud.google.com/apis/credentials"
            target="_blank"
            rel="noopener noreferrer"
            className="text-purple-600 hover:underline"
          >
            Google Cloud Console
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
            Google Client ID <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={form.client_id}
            onChange={(e) => setForm({ ...form, client_id: e.target.value })}
            placeholder="your-client-id.apps.googleusercontent.com"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            Get this from Google Cloud Console → APIs & Services → Credentials
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Google Client Secret <span className="text-red-500">*</span>
          </label>
          <input
            type="password"
            value={form.client_secret}
            onChange={(e) => setForm({ ...form, client_secret: e.target.value })}
            placeholder={config.is_configured ? '*** (already configured, leave empty to keep)' : 'Enter client secret'}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            {config.is_configured
              ? 'Leave empty to keep existing secret. Enter new value to update.'
              : 'Get this from Google Cloud Console (same page as Client ID)'}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Backend URL <span className="text-red-500">*</span>
          </label>
          <input
            type="url"
            value={form.backend_url}
            onChange={(e) => setForm({ ...form, backend_url: e.target.value })}
            placeholder="http://localhost:8000"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            Your backend server URL. Used to construct OAuth callback URL.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Redirect URI <span className="text-gray-500">(optional)</span>
          </label>
          <input
            type="url"
            value={form.redirect_uri}
            onChange={(e) => setForm({ ...form, redirect_uri: e.target.value })}
            placeholder={suggestedRedirectUri || 'http://localhost:8000/api/tools/google-drive/oauth/callback'}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            OAuth callback URL. Leave empty to auto-generate from Backend URL.
            {suggestedRedirectUri && (
              <span className="block mt-1 text-purple-600">
                💡 Suggested: {suggestedRedirectUri}
              </span>
            )}
          </p>
          <p className="mt-1 text-xs text-yellow-600">
            ⚠️ Make sure this URL is configured in Google Cloud Console as an authorized redirect URI
          </p>
        </div>

        {config.is_configured && (
          <div className="bg-green-50 border border-green-200 rounded-md p-3">
            <div className="flex items-start">
              <svg className="h-5 w-5 text-green-400 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <div className="ml-3">
                <p className="text-sm font-medium text-green-800">OAuth Configuration Active</p>
                <p className="text-xs text-green-700 mt-1">
                  Google OAuth is configured. You can now use OAuth flow in Google Drive connection wizard.
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
            {testing ? 'Testing...' : 'Test Configuration'}
          </button>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !form.client_id || !form.backend_url}
            className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>
    </div>
  );
}
