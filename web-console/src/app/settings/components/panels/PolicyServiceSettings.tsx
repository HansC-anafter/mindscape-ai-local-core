'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import { InlineAlert } from '../InlineAlert';
import { RoleGroupPolicyManager } from './RoleGroupPolicyManager';
import { DataDomainPolicyManager } from './DataDomainPolicyManager';
import { PIIHandlingConfig } from './PIIHandlingConfig';

interface PolicyServiceSettingsData {
  role_policies: Record<string, string[]>;
  data_domain_policies: {
    sensitive_domains: string[];
    pii_handling_enabled: boolean;
    forbidden_domains: string[];
  };
}

export function PolicyServiceSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [settings, setSettings] = useState<PolicyServiceSettingsData>({
    role_policies: {
      admin: ['*'],
      editor: ['read', 'write'],
      viewer: ['read'],
    },
    data_domain_policies: {
      sensitive_domains: [],
      pii_handling_enabled: false,
      forbidden_domains: [],
    },
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/system-settings/governance/policy');
      if (!response.ok) {
        throw new Error('Failed to load policy service settings');
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

      const response = await fetch('/api/v1/system-settings/governance/policy', {
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
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">{t('loading')}</div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
          {t('policyService')}
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {t('policyServiceDescription')}
        </p>
      </div>

      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}
      {success && <InlineAlert type="success" message={success} onDismiss={() => setSuccess(null)} />}

      <div className="space-y-6">
        <RoleGroupPolicyManager
          rolePolicies={settings.role_policies}
          onChange={(role_policies) => setSettings({ ...settings, role_policies })}
        />
        <DataDomainPolicyManager
          dataDomainPolicies={settings.data_domain_policies}
          onChange={(data_domain_policies) => setSettings({ ...settings, data_domain_policies })}
        />
        <PIIHandlingConfig
          piiEnabled={settings.data_domain_policies.pii_handling_enabled}
          onChange={(pii_handling_enabled) =>
            setSettings({
              ...settings,
              data_domain_policies: {
                ...settings.data_domain_policies,
                pii_handling_enabled,
              },
            })
          }
        />

        <div className="flex justify-end pt-4 border-t border-gray-200 dark:border-gray-700">
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

