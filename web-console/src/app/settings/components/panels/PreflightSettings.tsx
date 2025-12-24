'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import { InlineAlert } from '../InlineAlert';

interface PreflightSettingsData {
  required_inputs_validation: boolean;
  credential_validation: boolean;
  environment_validation: boolean;
}

export function PreflightSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [settings, setSettings] = useState<PreflightSettingsData>({
    required_inputs_validation: true,
    credential_validation: true,
    environment_validation: true,
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/system-settings/governance/preflight');
      if (!response.ok) {
        throw new Error('Failed to load preflight settings');
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

      const response = await fetch('/api/v1/system-settings/governance/preflight', {
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

  if (loading) {
    return (
      <Card>
        <div className="text-center py-8 text-secondary dark:text-gray-400">{t('loading')}</div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-primary dark:text-gray-100 mb-2">
          {t('preflight')}
        </h3>
        <p className="text-sm text-secondary dark:text-gray-400">
          {t('preflightDescription')}
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}
      {success && <InlineAlert type="success" message={success} onDismiss={() => setSuccess(null)} />}

      <div className="space-y-4">
        <label className="flex items-center gap-3 p-3 border border-default dark:border-gray-700 rounded-lg cursor-pointer hover:bg-surface-secondary dark:hover:bg-gray-700/50">
          <input
            type="checkbox"
            checked={settings.required_inputs_validation}
            onChange={(e) =>
              setSettings({ ...settings, required_inputs_validation: e.target.checked })
            }
            className="rounded"
          />
          <div className="flex-1">
            <div className="text-sm font-medium text-primary dark:text-gray-100">
              {t('requiredInputsValidation')}
            </div>
            <div className="text-xs text-secondary dark:text-gray-400 mt-1">
              {t('requiredInputsValidationDescription')}
            </div>
          </div>
        </label>

        <label className="flex items-center gap-3 p-3 border border-default dark:border-gray-700 rounded-lg cursor-pointer hover:bg-surface-secondary dark:hover:bg-gray-700/50">
          <input
            type="checkbox"
            checked={settings.credential_validation}
            onChange={(e) =>
              setSettings({ ...settings, credential_validation: e.target.checked })
            }
            className="rounded"
          />
          <div className="flex-1">
            <div className="text-sm font-medium text-primary dark:text-gray-100">
              {t('credentialValidation')}
            </div>
            <div className="text-xs text-secondary dark:text-gray-400 mt-1">
              {t('credentialValidationDescription')}
            </div>
          </div>
        </label>

        <label className="flex items-center gap-3 p-3 border border-default dark:border-gray-700 rounded-lg cursor-pointer hover:bg-surface-secondary dark:hover:bg-gray-700/50">
          <input
            type="checkbox"
            checked={settings.environment_validation}
            onChange={(e) =>
              setSettings({ ...settings, environment_validation: e.target.checked })
            }
            className="rounded"
          />
          <div className="flex-1">
            <div className="text-sm font-medium text-primary dark:text-gray-100">
              {t('environmentValidation')}
            </div>
            <div className="text-xs text-secondary dark:text-gray-400 mt-1">
              {t('environmentValidationDescription')}
            </div>
          </div>
        </label>

        <div className="flex justify-end pt-4 border-t border-default dark:border-gray-700">
          <button
            type="button"
            onClick={saveSettings}
            disabled={saving}
            className="px-4 py-2 bg-accent dark:bg-blue-700 text-white rounded hover:bg-accent/90 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? t('saving') : t('save')}
          </button>
        </div>
      </div>
    </Card>
  );
}

