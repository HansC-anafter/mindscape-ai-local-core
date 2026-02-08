'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import { InlineAlert } from '../InlineAlert';
import { CostQuotaConfig } from './CostQuotaConfig';

interface CostGovernanceSettingsData {
  daily_quota: number;
  single_execution_limit: number;
  risk_level_quotas: {
    read: number;
    write: number;
    publish: number;
  };
  model_price_overrides: Record<string, number>;
}

export function CostGovernanceSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [settings, setSettings] = useState<CostGovernanceSettingsData>({
    daily_quota: 10.0,
    single_execution_limit: 5.0,
    risk_level_quotas: {
      read: 20.0,
      write: 10.0,
      publish: 5.0,
    },
    model_price_overrides: {},
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/system-settings/governance/cost');
      if (!response.ok) {
        throw new Error('Failed to load cost governance settings');
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

      const response = await fetch('/api/v1/system-settings/governance/cost', {
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
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">{t('loading' as any)}</div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
          {t('costGovernance' as any)}
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {t('costGovernanceDescription' as any)}
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}
      {success && <InlineAlert type="success" message={success} onDismiss={() => setSuccess(null)} />}

      <div className="space-y-6">
        <CostQuotaConfig
          settings={settings}
          onChange={setSettings}
        />

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

