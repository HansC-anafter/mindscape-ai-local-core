import React, { useEffect, useState } from 'react';

import { getApiBaseUrl } from '../../../../../lib/api-url';
import type { RuntimeSettingsFormCallbacks } from './types';

export function GeminiCliSettingsForm({
  onSave,
  onCancel,
}: RuntimeSettingsFormCallbacks) {
  const MASKED_SECRET = '********';
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [secretConfigured, setSecretConfigured] = useState(false);
  const [secretTouched, setSecretTouched] = useState(false);
  const [scopes, setScopes] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const apiUrl = getApiBaseUrl();
      const [idRes, secretRes, scopesRes] = await Promise.all([
        fetch(`${apiUrl}/api/v1/system-settings/gca_oauth_client_id`),
        fetch(`${apiUrl}/api/v1/system-settings/gca_oauth_client_secret`),
        fetch(`${apiUrl}/api/v1/system-settings/gca_oauth_scopes`),
      ]);
      if (idRes.ok) {
        const data = await idRes.json();
        setClientId(data.value || '');
      }
      if (secretRes.ok) {
        const data = await secretRes.json();
        const hasSecret = !!data.value;
        setSecretConfigured(hasSecret);
        setClientSecret(hasSecret ? MASKED_SECRET : '');
      }
      if (scopesRes.ok) {
        const data = await scopesRes.json();
        setScopes(data.value || '');
      }
    } catch (e) {
      console.error('Failed to load Gemini CLI settings:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const apiUrl = getApiBaseUrl();
      const payload: Record<string, string> = {
        gca_oauth_client_id: clientId,
        gca_oauth_scopes: scopes,
      };
      if (secretTouched && clientSecret !== MASKED_SECRET) {
        payload.gca_oauth_client_secret = clientSecret;
      }
      const res = await fetch(`${apiUrl}/api/v1/system-settings/`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: payload }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`Save failed (${res.status}): ${detail}`);
      }
      onSave();
    } catch (e: any) {
      setError(e.message || 'Unknown error');
    } finally {
      setSaving(false);
    }
  };

  const inputClass =
    'w-full rounded-lg border border-gray-300 dark:border-gray-600 ' +
    'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 ' +
    'px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500';

  const labelClass = 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1';

  if (loading) {
    return <div className="text-sm text-gray-500 dark:text-gray-400 py-4">Loading...</div>;
  }

  return (
    <div className="space-y-5 p-2">
      <div>
        <label className={labelClass}>OAuth Client ID</label>
        <input
          type="text"
          className={inputClass}
          value={clientId}
          onChange={e => setClientId(e.target.value)}
          placeholder="xxxx.apps.googleusercontent.com"
        />
        <p className="mt-1 text-xs text-gray-400">
          Gemini CLI installed-app OAuth Client ID
        </p>
      </div>

      <div>
        <label className={labelClass}>OAuth Client Secret</label>
        <input
          type="password"
          className={inputClass}
          value={clientSecret}
          onChange={e => { setSecretTouched(true); setClientSecret(e.target.value); }}
          onFocus={() => { if (clientSecret === MASKED_SECRET) { setClientSecret(''); setSecretTouched(true); } }}
          placeholder={secretConfigured ? 'Leave empty to keep current secret' : 'Enter GOCSPX-xxx'}
        />
        {secretConfigured ? (
          <p className="mt-1 text-xs text-green-600 dark:text-green-400">
            Already configured - leave blank to keep existing value
          </p>
        ) : (
          <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
            Not configured - enter the GOCSPX-xxx secret
          </p>
        )}
      </div>

      <div>
        <label className={labelClass}>OAuth Scopes</label>
        <input
          type="text"
          className={inputClass}
          value={scopes}
          onChange={e => setScopes(e.target.value)}
          placeholder="https://www.googleapis.com/auth/cloud-platform ..."
        />
        <p className="mt-1 text-xs text-gray-400">
          Space-separated list of Google OAuth scopes
        </p>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  );
}
