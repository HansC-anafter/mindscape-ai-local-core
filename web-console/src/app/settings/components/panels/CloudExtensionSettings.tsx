'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import { showNotification } from '../../hooks/useSettingsNotification';

interface CloudExtensionSettingsProps {
  activeSection?: string;
}

interface Provider {
  provider_id: string;
  provider_type: string;
  enabled: boolean;
  configured: boolean;
  name: string;
  description: string;
  config: Record<string, any>;
}

export function CloudExtensionSettings({ activeSection }: CloudExtensionSettingsProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [testStatus, setTestStatus] = useState<Record<string, 'idle' | 'testing' | 'success' | 'error'>>({});
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});

  // Form state
  const [formData, setFormData] = useState({
    provider_id: '',
    provider_type: 'generic_http' as 'official' | 'generic_http',
    enabled: true,
    config: {
      api_url: '',
      license_key: '',
      name: '',
      auth: {
        auth_type: 'bearer',
        token: '',
        api_key: ''
      }
    }
  });

  useEffect(() => {
    loadProviders();
  }, []);

  const loadProviders = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/cloud-providers');
      if (response.ok) {
        const data = await response.json();
        setProviders(data);
      } else {
        showNotification('error', 'Failed to load cloud providers');
      }
        } catch (error: any) {
      console.error('Failed to load providers:', error);
      showNotification('error', error.message || t('failedToLoadProviders'));
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFormData({
      provider_id: '',
      provider_type: 'generic_http',
      enabled: true,
      config: {
        api_url: '',
        license_key: '',
        name: '',
        auth: {
          auth_type: 'bearer',
          token: '',
          api_key: ''
        }
      }
    });
    setShowAddForm(false);
    setEditingProvider(null);
  };

  const handleSave = async () => {
    try {
      setSaving(true);

      const payload: any = {
        provider_id: formData.provider_id,
        provider_type: formData.provider_type,
        enabled: formData.enabled,
        config: {}
      };

      if (formData.provider_type === 'official') {
        payload.config = {
          api_url: formData.config.api_url,
          license_key: formData.config.license_key
        };
      } else if (formData.provider_type === 'generic_http') {
        payload.config = {
          name: formData.config.name || formData.provider_id,
          api_url: formData.config.api_url,
          auth: {
            auth_type: formData.config.auth.auth_type,
            ...(formData.config.auth.auth_type === 'bearer' && { token: formData.config.auth.token }),
            ...(formData.config.auth.auth_type === 'api_key' && { api_key: formData.config.auth.api_key })
          }
        };
      }

      const url = editingProvider
        ? `/api/v1/cloud-providers/${formData.provider_id}`
        : '/api/v1/cloud-providers';
      const method = editingProvider ? 'PUT' : 'POST';

      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        showNotification('success', editingProvider ? t('providerUpdatedSuccessfully') : t('providerCreatedSuccessfully'));
        resetForm();
        loadProviders();
      } else {
        const error = await response.json();
        showNotification('error', error.detail || (editingProvider ? t('failedToUpdateProvider') : t('failedToCreateProvider')));
      }
    } catch (error: any) {
      showNotification('error', error.message || (editingProvider ? t('failedToUpdateProvider') : t('failedToCreateProvider')));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (providerId: string) => {
    if (!confirm(t('deleteProviderConfirm').replace('{providerId}', providerId))) {
      return;
    }

    try {
      const response = await fetch(`/api/v1/cloud-providers/${providerId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        showNotification('success', t('providerDeletedSuccessfully'));
        loadProviders();
      } else {
        const error = await response.json();
        showNotification('error', error.detail || t('failedToDeleteProvider'));
      }
    } catch (error: any) {
      showNotification('error', error.message || t('failedToDeleteProvider'));
    }
  };

  const handleEdit = (provider: Provider) => {
    setEditingProvider(provider);
    setFormData({
      provider_id: provider.provider_id,
      provider_type: provider.provider_type as 'official' | 'generic_http',
      enabled: provider.enabled,
      config: {
        api_url: provider.config.api_url || '',
        license_key: provider.config.license_key || '',
        name: provider.config.name || provider.provider_id,
        auth: {
          auth_type: provider.config.auth?.auth_type || 'bearer',
          token: provider.config.auth?.token || '',
          api_key: provider.config.auth?.api_key || ''
        }
      }
    });
    setShowAddForm(true);
  };

  const handleTestConnection = async (providerId: string) => {
    setTestStatus(prev => ({ ...prev, [providerId]: 'testing' }));
    setTestMessages(prev => ({ ...prev, [providerId]: t('testingConnection') }));

    try {
      const response = await fetch(`/api/v1/cloud-providers/${providerId}/test`, {
        method: 'POST'
      });

      const result = await response.json();

      if (result.success) {
        setTestStatus(prev => ({ ...prev, [providerId]: 'success' }));
        setTestMessages(prev => ({ ...prev, [providerId]: result.message || t('connectionSuccessful') }));
      } else {
        setTestStatus(prev => ({ ...prev, [providerId]: 'error' }));
        setTestMessages(prev => ({ ...prev, [providerId]: result.message || t('connectionFailed') }));
      }
    } catch (error: any) {
      setTestStatus(prev => ({ ...prev, [providerId]: 'error' }));
      setTestMessages(prev => ({ ...prev, [providerId]: error.message || t('connectionTestFailed') }));
    }
  };

  if (loading) {
    return (
      <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
        {t('loading')}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              {t('cloudPlaybookProviders')}
            </h2>
          </div>

          {/* Providers List */}
          <div className="space-y-4">
            {providers.length === 0 ? (
              <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                {t('noCloudProvidersConfigured')}
              </div>
            ) : (
              providers.map((provider) => (
                <div
                  key={provider.provider_id}
                  className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-gray-900 dark:text-gray-100">
                          {provider.name}
                        </h3>
                        <span className={`px-2 py-1 text-xs rounded ${
                          provider.enabled
                            ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                            : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400'
                        }`}>
                          {provider.enabled ? t('enabled') : t('disabled')}
                        </span>
                        <span className={`px-2 py-1 text-xs rounded ${
                          provider.configured
                            ? 'bg-accent-10 text-accent dark:bg-blue-900/20 dark:text-blue-400'
                            : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400'
                        }`}>
                          {provider.configured ? t('configured') : t('notConfigured')}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {provider.description}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                        {t('providerId')}: {provider.provider_id} | {t('providerType')}: {provider.provider_type}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleTestConnection(provider.provider_id)}
                        disabled={testStatus[provider.provider_id] === 'testing'}
                        className="px-3 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-50"
                      >
                        {testStatus[provider.provider_id] === 'testing' ? t('testing') : t('test')}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleEdit(provider)}
                        className="px-3 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
                      >
                        {t('editProvider')}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(provider.provider_id)}
                        className="px-3 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-700"
                      >
                        {t('deleteProvider')}
                      </button>
                    </div>
                  </div>
                  {testMessages[provider.provider_id] && (
                    <div
                      className={`text-sm ${
                        testStatus[provider.provider_id] === 'success'
                          ? 'text-green-600 dark:text-green-400'
                          : testStatus[provider.provider_id] === 'error'
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-gray-600 dark:text-gray-400'
                      }`}
                    >
                      {testMessages[provider.provider_id]}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Add/Edit Form */}
          {showAddForm && (
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-6 space-y-4">
              <h3 className="font-medium text-gray-900 dark:text-gray-100">
                {editingProvider ? t('editProvider') : t('addProvider')}
              </h3>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('providerId')} <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={formData.provider_id}
                  onChange={(e) => setFormData({ ...formData, provider_id: e.target.value })}
                  placeholder={t('enterProviderId')}
                  disabled={!!editingProvider}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('providerType')} <span className="text-red-500">*</span>
                </label>
                <select
                  value={formData.provider_type}
                  onChange={(e) => setFormData({ ...formData, provider_type: e.target.value as 'official' | 'generic_http' })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                >
                  <option value="official">{t('providerTypeOfficial')}</option>
                  <option value="generic_http">{t('providerTypeGenericHttp')}</option>
                </select>
              </div>

              {formData.provider_type === 'official' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('apiUrl')} <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={formData.config.api_url}
                      onChange={(e) => setFormData({
                        ...formData,
                        config: { ...formData.config, api_url: e.target.value }
                      })}
                      placeholder={t('apiUrlPlaceholder')}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('licenseKey')} <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="password"
                      value={formData.config.license_key}
                      onChange={(e) => setFormData({
                        ...formData,
                        config: { ...formData.config, license_key: e.target.value }
                      })}
                      placeholder={t('licenseKeyPlaceholder')}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                </>
              )}

              {formData.provider_type === 'generic_http' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('providerName')} <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={formData.config.name}
                      onChange={(e) => setFormData({
                        ...formData,
                        config: { ...formData.config, name: e.target.value }
                      })}
                      placeholder={t('providerNamePlaceholder')}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('apiUrl')} <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={formData.config.api_url}
                      onChange={(e) => setFormData({
                        ...formData,
                        config: { ...formData.config, api_url: e.target.value }
                      })}
                      placeholder={t('apiUrlPlaceholderGeneric')}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('authenticationType')} <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={formData.config.auth.auth_type}
                      onChange={(e) => setFormData({
                        ...formData,
                        config: {
                          ...formData.config,
                          auth: { ...formData.config.auth, auth_type: e.target.value }
                        }
                      })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    >
                      <option value="bearer">{t('bearerToken')}</option>
                      <option value="api_key">{t('apiKey')}</option>
                    </select>
                  </div>
                  {formData.config.auth.auth_type === 'bearer' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('token')} <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="password"
                        value={formData.config.auth.token}
                        onChange={(e) => setFormData({
                          ...formData,
                          config: {
                            ...formData.config,
                            auth: { ...formData.config.auth, token: e.target.value }
                          }
                        })}
                        placeholder={t('tokenPlaceholder')}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                      />
                    </div>
                  )}
                  {formData.config.auth.auth_type === 'api_key' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('apiKey')} <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="password"
                        value={formData.config.auth.api_key}
                        onChange={(e) => setFormData({
                          ...formData,
                          config: {
                            ...formData.config,
                            auth: { ...formData.config.auth, api_key: e.target.value }
                          }
                        })}
                        placeholder={t('apiKeyPlaceholder')}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                      />
                    </div>
                  )}
                </>
              )}

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="enabled"
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  className="w-4 h-4 text-gray-600 bg-gray-100 border-gray-300 rounded focus:ring-gray-500"
                />
                <label htmlFor="enabled" className="text-sm text-gray-700 dark:text-gray-300">
                  {t('enableThisProvider')}
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  type="button"
                  onClick={resetForm}
                  className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300"
                >
                  {t('cancel')}
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saving || !formData.provider_id || !formData.config.api_url}
                  className="px-4 py-2 text-sm bg-gray-900 dark:bg-gray-700 text-white rounded-md hover:bg-gray-800 dark:hover:bg-gray-600 disabled:opacity-50"
                >
                  {saving ? t('saving') : editingProvider ? t('update') : t('create')}
                </button>
              </div>
            </div>
          )}

          {/* Add Button */}
          {!showAddForm && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setShowAddForm(true)}
                className="px-4 py-2 bg-gray-900 dark:bg-gray-700 text-white rounded-md hover:bg-gray-800 dark:hover:bg-gray-600 text-sm font-medium"
              >
                {t('addProvider')}
              </button>
            </div>
          )}

        </div>
      </Card>
    </div>
  );
}
