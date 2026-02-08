'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import { InlineAlert } from '../InlineAlert';

interface GovernanceModeSettingsData {
  strict_mode: boolean;
  warning_mode: boolean;
}

export function GovernanceModeSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [settings, setSettings] = useState<GovernanceModeSettingsData>({
    strict_mode: false,
    warning_mode: true,
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/system-settings/governance/mode');
      if (!response.ok) {
        throw new Error('Failed to load governance mode settings');
      }
      const data = await response.json();
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      const response = await fetch('/api/v1/system-settings/governance/mode', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to save settings');
      }

      setSuccess('Settings saved successfully');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleModeChange = (mode: 'strict' | 'warning') => {
    if (mode === 'strict') {
      setSettings({ strict_mode: true, warning_mode: false });
    } else {
      setSettings({ strict_mode: false, warning_mode: true });
    }
  };

  if (loading) {
    return (
      <Card>
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">{t('loading' as any)}</div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
          {t('governanceMode' as any)}
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {t('governanceModeDescription' as any)}
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}
      {success && <InlineAlert type="success" message={success} onDismiss={() => setSuccess(null)} />}

      <div className="space-y-4">
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <div className="space-y-3">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="radio"
                name="governance-mode"
                checked={settings.warning_mode}
                onChange={() => handleModeChange('warning')}
                className="mt-1"
              />
              <div className="flex-1">
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {t('warningMode' as any)}
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                  {t('warningModeDescription' as any)}
                </div>
              </div>
            </label>

            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="radio"
                name="governance-mode"
                checked={settings.strict_mode}
                onChange={() => handleModeChange('strict')}
                className="mt-1"
              />
              <div className="flex-1">
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {t('strictMode' as any)}
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                  {t('strictModeDescription' as any)}
                </div>
              </div>
            </label>
          </div>
        </div>

        <div className="flex justify-end pt-4 border-t border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={saveSettings}
            disabled={saving}
            className="px-4 py-2 bg-accent dark:bg-blue-700 text-white rounded hover:bg-accent/90 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? t('saving' as any) : t('save' as any)}
          </button>
        </div>
      </div>
    </Card>
  );
}

