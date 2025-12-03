'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';

interface AirtableConnectionWizardProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function AirtableConnectionWizard({ onClose, onSuccess }: AirtableConnectionWizardProps) {
  const [form, setForm] = useState({
    connection_id: 'airtable-workspace-1',
    name: 'My Airtable Workspace',
    api_key: '',
  });
  const [discovering, setDiscovering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleDiscover = async () => {
    setDiscovering(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await settingsApi.post<{ tools_count?: number }>(
        '/api/v1/tools/airtable/discover',
        {
          connection_id: form.connection_id,
          name: form.name,
          api_key: form.api_key,
        }
      );

      setSuccess(
        `${t('airtableConnectionSuccess')}! ${result.tools_count || 0} ${t('toolsCount')} discovered.`
      );
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Discovery failed';
      setError(errorMessage);
    } finally {
      setDiscovering(false);
    }
  };

  const footer = (
    <>
      <button
        onClick={onClose}
        className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
      >
        {t('cancel')}
      </button>
      <button
        onClick={handleDiscover}
        disabled={discovering || !form.connection_id || !form.name || !form.api_key}
        className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
      >
        {discovering ? t('discovering') : t('discoverAndRegister')}
      </button>
    </>
  );

  return (
    <WizardShell
      title={t('connectAirtable')}
      onClose={onClose}
      error={error}
      success={success}
      onDismissError={() => setError(null)}
      onDismissSuccess={() => setSuccess(null)}
      footer={footer}
    >
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('connectionName')}
        </label>
        <input
          type="text"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 rounded-md"
          placeholder="e.g., My Airtable Workspace"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('siteIdentifier')}
        </label>
        <input
          type="text"
          value={form.connection_id}
          onChange={(e) => setForm({ ...form, connection_id: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 rounded-md"
          placeholder="e.g., airtable-workspace-1"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('airtablePersonalAccessToken')}
        </label>
        <input
          type="password"
          value={form.api_key}
          onChange={(e) => setForm({ ...form, api_key: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 rounded-md"
          placeholder="pat..."
        />
        <p className="text-xs text-gray-500 mt-1">
          {t('airtableTokenDescription')}
        </p>
      </div>
    </WizardShell>
  );
}

