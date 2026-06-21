import React, { useState } from 'react';

import { t } from '../../../../../lib/i18n';
import { getApiBaseUrl } from '../../../../../lib/api-url';
import type { SiteHubSettingsFormProps } from './types';

export function SiteHubSettingsForm({
  runtime,
  onSave,
  onCancel,
}: SiteHubSettingsFormProps) {
  const meta = runtime.metadata || {};
  const [configUrl, setConfigUrl] = useState(runtime.config_url || '');
  const [siteKey, setSiteKey] = useState(meta.site_key || '');
  const [chainagentId, setChainagentId] = useState(meta.chainagent_id || '');
  const [authToken, setAuthToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const apiUrl = getApiBaseUrl();
      const body: Record<string, any> = {
        config_url: configUrl || undefined,
        metadata: {
          site_key: siteKey || undefined,
          chainagent_id: chainagentId || undefined,
        },
      };

      if (authToken) {
        body.auth_type = 'api_key';
        body.auth_config = { api_key: authToken };
      }

      const res = await fetch(
        `${apiUrl}/api/v1/runtime-environments/${runtime.id}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      );

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

  return (
    <div className="space-y-5 p-2">
      <div>
        <label className={labelClass}>Config URL</label>
        <input
          type="url"
          className={inputClass}
          value={configUrl}
          onChange={e => setConfigUrl(e.target.value)}
          placeholder="https://agent.anafter.co"
        />
        <p className="mt-1 text-xs text-gray-400">
          Site-Hub registry API base URL
        </p>
      </div>

      <div>
        <label className={labelClass}>Site Key</label>
        <input
          type="text"
          className={inputClass}
          value={siteKey}
          onChange={e => setSiteKey(e.target.value)}
          placeholder="openseo-basic-anafter-co-an-after-ux-..."
        />
        <p className="mt-1 text-xs text-gray-400">
          From Site-Hub Console &gt; Channel settings
        </p>
      </div>

      <div>
        <label className={labelClass}>ChainAgent ID</label>
        <input
          type="text"
          className={inputClass}
          value={chainagentId}
          onChange={e => setChainagentId(e.target.value)}
          placeholder="UUID of the ChainAgent"
        />
        <p className="mt-1 text-xs text-gray-400">
          Required for fetching channels - find in Site-Hub Console
        </p>
      </div>

      <div>
        <label className={labelClass}>Auth Token (optional)</label>
        <input
          type="password"
          className={inputClass}
          value={authToken}
          onChange={e => setAuthToken(e.target.value)}
          placeholder="Leave empty to keep current token"
        />
        <p className="mt-1 text-xs text-gray-400">
          API key or bearer token for Site-Hub authentication
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
          {t('cancel' as any) || 'Cancel'}
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving...' : t('save' as any) || 'Save'}
        </button>
      </div>
    </div>
  );
}
