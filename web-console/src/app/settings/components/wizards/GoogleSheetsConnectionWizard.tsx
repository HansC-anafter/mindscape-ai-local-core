'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';

interface GoogleSheetsConnectionWizardProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function GoogleSheetsConnectionWizard({ onClose, onSuccess }: GoogleSheetsConnectionWizardProps) {
  const [form, setForm] = useState({
    connection_id: 'google-sheets-1',
    name: 'My Google Sheets',
    api_key: '',
  });
  const [discovering, setDiscovering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [reuseGoogleDrive, setReuseGoogleDrive] = useState(true);
  const [hasGoogleDriveConnection, setHasGoogleDriveConnection] = useState(false);

  useEffect(() => {
    // Check if Google Drive connection exists
    settingsApi.get('/api/v1/tools/connections?tool_type=google_drive&active_only=true')
      .then((response: any) => {
        const connections = response.data || response;
        const activeConnection = Array.isArray(connections)
          ? connections.find((conn: any) => conn.is_active && conn.oauth_token)
          : null;
        setHasGoogleDriveConnection(!!activeConnection);
        if (activeConnection) {
          setReuseGoogleDrive(true);
        }
      })
      .catch(() => {
        setHasGoogleDriveConnection(false);
      });
  }, []);

  const handleDiscover = async () => {
    setDiscovering(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await settingsApi.post<{ tools_count?: number; oauth_reused?: boolean }>(
        '/api/v1/tools/google-sheets/discover',
        {
          connection_id: form.connection_id,
          name: form.name,
          api_key: form.api_key || undefined,
          reuse_google_drive_oauth: reuseGoogleDrive && !form.api_key,
        }
      );

      const reusedMsg = result.oauth_reused ? ` (${t('reusedGoogleDriveOAuth')})` : '';
      setSuccess(
        `${t('googleSheetsConnectionSuccess')}! ${result.tools_count || 0} ${t('toolsCount')} discovered.${reusedMsg}`
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

  const handleOAuth = () => {
    const redirectUrl = `/api/v1/tools/google-sheets/oauth/authorize?connection_id=${form.connection_id}&connection_name=${encodeURIComponent(form.name)}`;
    window.location.href = redirectUrl;
  };

  const footer = (
    <>
      <button
        onClick={onClose}
        className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
      >
        {t('cancel')}
      </button>
      {!form.api_key && !reuseGoogleDrive && (
        <button
          onClick={handleOAuth}
          className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600"
        >
          {t('connectViaOAuth')}
        </button>
      )}
      <button
        onClick={handleDiscover}
        disabled={discovering || !form.connection_id || !form.name || (!form.api_key && !reuseGoogleDrive)}
        className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {discovering ? t('discovering') : t('discoverAndRegister')}
      </button>
    </>
  );

  return (
    <WizardShell
      title={t('connectGoogleSheets')}
      onClose={onClose}
      error={error}
      success={success}
      onDismissError={() => setError(null)}
      onDismissSuccess={() => setSuccess(null)}
      footer={footer}
    >
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {t('connectionName')}
        </label>
        <input
          type="text"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
          placeholder="e.g., My Google Sheets"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {t('siteIdentifier')}
        </label>
        <input
          type="text"
          value={form.connection_id}
          onChange={(e) => setForm({ ...form, connection_id: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
          placeholder="e.g., google-sheets-1"
        />
      </div>

      {hasGoogleDriveConnection && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-3">
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={reuseGoogleDrive}
              onChange={(e) => {
                setReuseGoogleDrive(e.target.checked);
                if (e.target.checked) {
                  setForm({ ...form, api_key: '' });
                }
              }}
              className="mr-2"
            />
            <span className="text-sm text-blue-800 dark:text-blue-300">
              {t('reuseGoogleDriveOAuth')}
            </span>
          </label>
          <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
            {t('reuseGoogleDriveOAuthDescription')}
          </p>
        </div>
      )}

      {!reuseGoogleDrive && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('googleSheetsAccessToken')}
          </label>
          <input
            type="password"
            value={form.api_key}
            onChange={(e) => setForm({ ...form, api_key: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
            placeholder="ya29..."
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {t('googleSheetsTokenDescription')}
          </p>
        </div>
      )}

      {!reuseGoogleDrive && !form.api_key && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md p-3">
          <p className="text-sm text-yellow-800 dark:text-yellow-300">
            {t('googleSheetsOAuthNote')}
          </p>
        </div>
      )}
    </WizardShell>
  );
}

