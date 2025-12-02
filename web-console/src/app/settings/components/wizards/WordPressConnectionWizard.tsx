'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';

interface WordPressConnectionWizardProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function WordPressConnectionWizard({
  onClose,
  onSuccess,
}: WordPressConnectionWizardProps) {
  const [form, setForm] = useState({
    connection_id: 'wordpress-local',
    name: 'Local WordPress',
    wp_url: 'http://wordpress:80',
    wp_username: 'admin',
    wp_application_password: '',
  });
  const [discovering, setDiscovering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleDiscover = async () => {
    setDiscovering(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await settingsApi.post<{
        capabilities?: unknown[];
        registered_tools?: unknown[];
      }>('/api/v1/tools/wordpress/discover', {
        connection_id: form.connection_id,
        name: form.name,
        wp_url: form.wp_url,
        wp_username: form.wp_username,
        wp_application_password: form.wp_application_password,
      });

      const message = `${t('successDiscovered')} ${result.capabilities?.length || 0} ${t('capabilitiesCount')} ${result.registered_tools?.length || 0} ${t('toolsCount')}`;
      setSuccess(message);
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
        disabled={discovering || !form.connection_id || !form.name || !form.wp_url}
        className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
      >
        {discovering ? t('discovering') : t('discoverAndRegister')}
      </button>
    </>
  );

  return (
    <WizardShell
      title={t('connectWordPress')}
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
          placeholder="e.g., Local WordPress Site"
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
          placeholder="e.g., wordpress-local"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('wordpressUrl')}
        </label>
        <input
          type="url"
          value={form.wp_url}
          onChange={(e) => setForm({ ...form, wp_url: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 rounded-md"
          placeholder="http://wordpress:80 or http://localhost:8080"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('wordpressUsername')}
        </label>
        <input
          type="text"
          value={form.wp_username}
          onChange={(e) => setForm({ ...form, wp_username: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 rounded-md"
          placeholder="admin"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t('wordpressPassword')}
        </label>
        <input
          type="password"
          value={form.wp_application_password}
          onChange={(e) => setForm({ ...form, wp_application_password: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 rounded-md"
          placeholder="xxxx xxxx xxxx xxxx"
        />
        <p className="mt-1 text-xs text-gray-500">
          WordPress Admin → Users → Profile → Application Passwords
        </p>
      </div>
    </WizardShell>
  );
}
