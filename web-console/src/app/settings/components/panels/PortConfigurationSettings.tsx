'use client';

import React, { useState, useEffect } from 'react';
import { Card } from '../Card';
import { settingsApi } from '../../utils/settingsApi';
import { showNotification } from '../../hooks/useSettingsNotification';
import { t } from '../../../../lib/i18n';

interface PortConfig {
  backend_api: number;
  frontend: number;
  ocr_service: number;
  postgres: number;
  cloud_api?: number;
  site_hub_api?: number;
  cluster?: string;
  environment?: string;
  site?: string;
}

export function PortConfigurationSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<PortConfig>({
    backend_api: 8200,
    frontend: 8300,
    ocr_service: 8400,
    postgres: 5440,
    cloud_api: 8500,
    site_hub_api: 8102,
  });
  const [originalConfig, setOriginalConfig] = useState<PortConfig | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [validating, setValidating] = useState(false);

  useEffect(() => {
    loadConfig();
  }, []);

  // Reload config and persist scope when scope fields change
  useEffect(() => {
    if (originalConfig) {
      const scopeChanged =
        (originalConfig.cluster !== config.cluster) ||
        (originalConfig.environment !== config.environment) ||
        (originalConfig.site !== config.site);

      if (scopeChanged && !loading) {
        if (typeof window !== 'undefined') {
          try {
            const scope = {
              cluster: config.cluster,
              environment: config.environment,
              site: config.site,
            };
            localStorage.setItem('port_config_scope', JSON.stringify(scope));

            if ((window as any).__PORT_CONFIG_SCOPE__) {
              (window as any).__PORT_CONFIG_SCOPE__ = scope;
            }
          } catch (e) {
            // Ignore localStorage errors
          }
        }

        loadConfig({
          cluster: config.cluster,
          environment: config.environment,
          site: config.site,
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.cluster, config.environment, config.site]);

  const loadConfig = async (scopeOverride?: { cluster?: string; environment?: string; site?: string }) => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      const cluster = scopeOverride?.cluster ?? config.cluster;
      const environment = scopeOverride?.environment ?? config.environment;
      const site = scopeOverride?.site ?? config.site;

      if (cluster) params?.append('cluster', cluster);
      if (environment) params?.append('environment', environment);
      if (site) params?.append('site', site);

      // Read scope from localStorage if no params provided
      if (typeof window !== 'undefined' && params?.toString() === '') {
        try {
          const storedScope = localStorage.getItem('port_config_scope');
          if (storedScope) {
            const scope = JSON.parse(storedScope);
            if (scope.cluster) params?.append('cluster', scope.cluster);
            if (scope.environment) params?.append('environment', scope.environment);
            if (scope.site) params?.append('site', scope.site);
          }
        } catch (e) {
          // Ignore localStorage errors
        }
      }

      const url = `/api/v1/system-settings/ports/${params?.toString() ? '?' + params?.toString() : ''}`;
      const data = await settingsApi.get<PortConfig>(url);

      // Normalize: convert "default" to undefined for UI display
      const cleanedData = {
        ...data,
        environment: data.environment === 'default' ? undefined : data.environment,
        cluster: data.cluster || undefined,
        site: data.site || undefined,
      };

      setConfig(cleanedData);
      setOriginalConfig(cleanedData);

      // Persist scope to localStorage
      if (typeof window !== 'undefined') {
        try {
          const scope = {
            cluster: cleanedData.cluster,
            environment: cleanedData.environment,
            site: cleanedData.site,
          };
          localStorage.setItem('port_config_scope', JSON.stringify(scope));

          if ((window as any).__PORT_CONFIG_SCOPE__) {
            (window as any).__PORT_CONFIG_SCOPE__ = scope;
          }
        } catch (e) {
          // Ignore localStorage errors
        }
      }
    } catch (error) {
      console.error('Failed to load port config:', error);
      showNotification('error', t('portConfigLoadFailed' as any));
    } finally {
      setLoading(false);
    }
  };

  const validateConfig = async () => {
    try {
      setValidating(true);
      const response = await settingsApi.post<{ valid: boolean; conflicts: string[] }>(
        '/api/v1/system-settings/ports/validate',
        config
      );
      setValidationErrors(response.conflicts || []);
      return response.valid;
    } catch (error) {
      console.error('Failed to validate port config:', error);
      return false;
    } finally {
      setValidating(false);
    }
  };

  const handleChange = (key: keyof PortConfig, value: string) => {
    // Validate numeric range for port fields
    if (['backend_api', 'frontend', 'ocr_service', 'postgres', 'cloud_api', 'site_hub_api'].includes(key)) {
      const numValue = parseInt(value, 10);
      if (isNaN(numValue) || numValue < 1024 || numValue > 65535) {
        return;
      }
      setConfig(prev => ({ ...prev, [key]: numValue }));
    } else {
      // Scope fields: update directly
      setConfig(prev => ({ ...prev, [key]: value || undefined }));
    }
    setValidationErrors([]);
  };

  const handleSave = async () => {
    try {
      setSaving(true);

      const isValid = await validateConfig();
      if (!isValid) {
        showNotification('error', t('portConflictRetry' as any));
        return;
      }

      // Check if PostgreSQL port changed
      const postgresChanged = originalConfig && originalConfig.postgres !== config.postgres;

      if (postgresChanged) {
        const confirmed = window.confirm(t('postgresPortChangeWarning' as any));
        if (!confirmed) {
          return;
        }
      }

      const response = await settingsApi.put<{ success: boolean; message: string }>(
        '/api/v1/system-settings/ports/',
        config
      );

      showNotification('success', response.message || t('portConfigSaved' as any));

      // Persist scope to localStorage
      if (typeof window !== 'undefined') {
        try {
          const scope = {
            cluster: config.cluster,
            environment: config.environment,
            site: config.site,
          };
          localStorage.setItem('port_config_scope', JSON.stringify(scope));

          if ((window as any).__PORT_CONFIG_SCOPE__) {
            (window as any).__PORT_CONFIG_SCOPE__ = scope;
          }
        } catch (e) {
          // Ignore localStorage errors
        }
      }

      // Reload to get latest values
      await loadConfig();

      if (postgresChanged) {
        showNotification('error', t('portConfigUpdateDbString' as any));
      }
    } catch (error: any) {
      console.error('Failed to save port config:', error);
      if (error.message && error.message.includes('conflicts')) {
        const errorData = JSON.parse(error.message);
        if (errorData.conflicts) {
          setValidationErrors(errorData.conflicts);
        }
        showNotification('error', t('portConfigConflictExists' as any));
      } else {
        showNotification('error', t('portConfigSaveFailed' as any));
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <div className="text-center py-4">{t('loading' as any)}...</div>
      </Card>
    );
  }

  return (
    <Card className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold mb-2">{t('portConfiguration' as any)}</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          {t('portConfigurationDescription' as any)}
        </p>
      </div>

      {validationErrors.length > 0 && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-4 mb-4">
          <h4 className="text-sm font-medium text-red-800 dark:text-red-200 mb-2">
            {t('portConfigConflicts' as any)}
          </h4>
          <ul className="list-disc list-inside text-sm text-red-700 dark:text-red-300">
            {validationErrors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Cluster/Environment scope selectors */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            {t('clusterIdentifier' as any)}
          </label>
          <input
            type="text"
            value={config.cluster || ''}
            onChange={(e) => handleChange('cluster', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="prod-cluster-1"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">
            {t('environmentIdentifier' as any)}
          </label>
          <select
            value={config.environment || ''}
            onChange={(e) => handleChange('environment', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
          >
            <option value="">{t('globalDefault' as any)}</option>
            <option value="production">{t('productionEnv' as any)}</option>
            <option value="staging">{t('stagingEnv' as any)}</option>
            <option value="development">{t('developmentEnv' as any)}</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">
            {t('siteIdentifier' as any)}
          </label>
          <input
            type="text"
            value={config.site || ''}
            onChange={(e) => handleChange('site', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="site-1"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            {t('backendApiPort' as any)}
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.backend_api}
            onChange={(e) => handleChange('backend_api', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="8200"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            {t('frontendWebConsolePort' as any)}
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.frontend}
            onChange={(e) => handleChange('frontend', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="8300"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            {t('ocrServicePort' as any)}
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.ocr_service}
            onChange={(e) => handleChange('ocr_service', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="8400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            {t('postgresPort' as any)}
            <span className="text-red-500 ml-1">⚠️</span>
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.postgres}
            onChange={(e) => handleChange('postgres', e.target.value)}
            className="w-full px-3 py-2 border rounded-md border-yellow-300 dark:bg-gray-700 dark:border-gray-600"
            placeholder="5440"
          />
          <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
            {t('postgresPortChangeConfirm' as any)}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            {t('cloudApiPort' as any)}
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.cloud_api || ''}
            onChange={(e) => handleChange('cloud_api', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="8500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">
            {t('siteHubApiPort' as any)}
          </label>
          <input
            type="number"
            min="1024"
            max="65535"
            value={config.site_hub_api || ''}
            onChange={(e) => handleChange('site_hub_api', e.target.value)}
            className="w-full px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
            placeholder="8102"
          />
        </div>
      </div>

      <div className="flex justify-end space-x-2 pt-4">
        <button
          onClick={validateConfig}
          disabled={validating}
          className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-50"
        >
          {validating ? t('validatingConfig' as any) : t('validateConfig' as any)}
        </button>
        <button
          onClick={handleSave}
          disabled={saving || validationErrors.length > 0}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? t('savingPortConfig' as any) : t('savePortConfig' as any)}
        </button>
      </div>
    </Card>
  );
}
