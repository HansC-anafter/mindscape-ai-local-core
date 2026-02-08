'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { Card } from '../Card';
import { showNotification } from '../../hooks/useSettingsNotification';
import { BaseModal } from '../../../../components/BaseModal';

interface Provider {
  provider_id: string;
  provider_type: string;
  enabled: boolean;
  configured: boolean;
  name: string;
  description: string;
  config: Record<string, any>;
}

interface Pack {
  pack_ref: string;
  code: string;
  display_name: string;
  version: string;
  description: string;
  checksum?: string;
  size?: number;
  bundle: string;
  installed?: boolean;
}

export function CloudPlaybookProvidersSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [testStatus, setTestStatus] = useState<Record<string, 'idle' | 'testing' | 'success' | 'error'>>({});
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});
  const [packs, setPacks] = useState<Record<string, Pack[]>>({});
  const [loadingPacks, setLoadingPacks] = useState<Record<string, boolean>>({});
  const [installingPacks, setInstallingPacks] = useState<Record<string, boolean>>({});
  const [showPacks, setShowPacks] = useState<Record<string, boolean>>({});

  // Form state
  const [formData, setFormData] = useState({
    provider_id: '',
    provider_type: 'generic_http' as 'generic_http',
    enabled: true,
    config: {
      api_url: '',
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
      showNotification('error', error.message || t('failedToLoadProviders' as any));
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
        config: {
          name: formData.config.name || formData.provider_id,
          api_url: formData.config.api_url,
          auth: {
            auth_type: formData.config.auth.auth_type,
            ...(formData.config.auth.auth_type === 'bearer' && { token: formData.config.auth.token }),
            ...(formData.config.auth.auth_type === 'api_key' && { api_key: formData.config.auth.api_key })
          }
          }
        };

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
        showNotification('success', editingProvider ? t('providerUpdatedSuccessfully' as any) : t('providerCreatedSuccessfully' as any));
        resetForm();
        loadProviders();
      } else {
        const error = await response.json();
        showNotification('error', error.detail || (editingProvider ? t('failedToUpdateProvider' as any) : t('failedToCreateProvider' as any)));
      }
    } catch (error: any) {
      showNotification('error', error.message || (editingProvider ? t('failedToUpdateProvider' as any) : t('failedToCreateProvider' as any)));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (providerId: string) => {
    if (!confirm(t('deleteProviderConfirm' as any).replace('{providerId}', providerId))) {
      return;
    }

    try {
      const response = await fetch(`/api/v1/cloud-providers/${providerId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        showNotification('success', t('providerDeletedSuccessfully' as any));
        loadProviders();
      } else {
        const error = await response.json();
        showNotification('error', error.detail || t('failedToDeleteProvider' as any));
      }
    } catch (error: any) {
      showNotification('error', error.message || t('failedToDeleteProvider' as any));
    }
  };

  const handleEdit = (provider: Provider) => {
    setEditingProvider(provider);
    setFormData({
      provider_id: provider.provider_id,
      provider_type: 'generic_http',
      enabled: provider.enabled,
      config: {
        api_url: provider.config.api_url || '',
        name: provider.config.name || provider.provider_id,
        auth: {
          auth_type: provider.config.auth?.auth_type || 'bearer',
          token: provider.config.auth?.token || '',
          api_key: provider.config.auth?.api_key || provider.config.license_key || ''
        }
      }
    });
    setShowAddForm(true);
  };

  const handleTestConnection = async (providerId: string) => {
    setTestStatus(prev => ({ ...prev, [providerId]: 'testing' }));
    setTestMessages(prev => ({ ...prev, [providerId]: t('testingConnection' as any) }));

    try {
      const response = await fetch(`/api/v1/cloud-providers/${providerId}/test`, {
        method: 'POST'
      });

      const result = await response.json();

      if (result.success) {
        setTestStatus(prev => ({ ...prev, [providerId]: 'success' }));
        setTestMessages(prev => ({ ...prev, [providerId]: result.message || t('connectionSuccessful' as any) }));
      } else {
        setTestStatus(prev => ({ ...prev, [providerId]: 'error' }));
        setTestMessages(prev => ({ ...prev, [providerId]: result.message || t('connectionFailed' as any) }));
      }
    } catch (error: any) {
      setTestStatus(prev => ({ ...prev, [providerId]: 'error' }));
      setTestMessages(prev => ({ ...prev, [providerId]: error.message || t('connectionTestFailed' as any) }));
    }
  };

  const loadPacks = async (providerId: string) => {
    setLoadingPacks(prev => ({ ...prev, [providerId]: true }));
    try {
      const response = await fetch(`/api/v1/cloud-providers/${providerId}/packs`);
      if (response.ok) {
        const data = await response.json();
        const packsList = data.packs || [];

        // Check installation status for each pack
        try {
          const installedResponse = await fetch('/api/v1/capability-packs', {
            signal: AbortSignal.timeout(5000)
          });
          if (installedResponse.ok) {
            const installedPacks = await installedResponse.json();
            const installedIds = new Set(
              installedPacks
                .map((p: any) => p.id || p.code)
                .filter(Boolean)
            );

            packsList.forEach((pack: Pack) => {
              const packId = pack.code;
              const packRefId = pack.pack_ref?.split(':' as any)[1]?.split('@' as any)[0];
              pack.installed = installedIds.has(packId) || installedIds.has(packRefId || '');
            });
          }
        } catch (e: any) {
          if (e.name !== 'AbortError') {
            console.debug('Failed to check installed packs (non-critical):', e.message);
          }
        }

        setPacks(prev => ({ ...prev, [providerId]: packsList }));
        setShowPacks(prev => ({ ...prev, [providerId]: true }));
      } else {
        const error = await response.json();
        showNotification('error', error.detail || 'Failed to load packs');
        setPacks(prev => ({ ...prev, [providerId]: [] }));
      }
    } catch (error: any) {
      console.error('Failed to load packs:', error);
      showNotification('error', error.message || 'Failed to load packs');
      setPacks(prev => ({ ...prev, [providerId]: [] }));
    } finally {
      setLoadingPacks(prev => ({ ...prev, [providerId]: false }));
    }
  };

  const handleInstallPacks = async (providerId: string) => {
    setInstallingPacks(prev => ({ ...prev, [providerId]: true }));
    try {
      const response = await fetch(`/api/v1/cloud-providers/${providerId}/install-default?bundle=default`, {
        method: 'POST'
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
        showNotification('error', errorData.detail || errorData.message || 'Failed to install packs');
        return;
      }

      const result = await response.json();

      if (result.success) {
        const installedCount = result.installed?.length || 0;
        const installedNames = result.installed?.map((p: any) => p.pack_code || p.code).join(', ') || '';
        const notificationMessage = `✅ 成功安裝 ${installedCount} 個 pack${installedCount > 1 ? 's' : ''}${installedNames ? `: ${installedNames}` : ''}`;
        showNotification('success', notificationMessage);
        try {
          await loadPacks(providerId);
        } catch (e) {
          console.debug('Failed to reload packs after installation (non-critical):', e);
        }
      } else {
        const errorMsg = result.message || result.detail || 'Failed to install packs';
        showNotification('error', `❌ 安裝失敗: ${errorMsg}`);
      }
    } catch (error: any) {
      console.error('Failed to install packs:', error);
      showNotification('error', error.message || 'Failed to install packs');
    } finally {
      setInstallingPacks(prev => ({ ...prev, [providerId]: false }));
    }
  };

  if (loading) {
    return (
      <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
        {t('loading' as any)}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Cloud Playbook Providers */}
      <Card>
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              {t('cloudPlaybookProviders' as any)}
            </h2>
          </div>

          {/* Providers List */}
          <div className="space-y-4">
            {providers.length === 0 ? (
              <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                {t('noCloudProvidersConfigured' as any)}
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
                          {provider.enabled ? t('enabled' as any) : t('disabled' as any)}
                        </span>
                        <span className={`px-2 py-1 text-xs rounded ${
                          provider.configured
                            ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/20 dark:text-orange-400'
                            : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400'
                        }`}>
                          {provider.configured ? t('configured' as any) : t('notConfigured' as any)}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {provider.description}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                        {t('providerId' as any)}: {provider.provider_id} | {t('providerType' as any)}: {provider.provider_type}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleTestConnection(provider.provider_id)}
                        disabled={testStatus[provider.provider_id] === 'testing'}
                        className="px-3 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-50"
                      >
                        {testStatus[provider.provider_id] === 'testing' ? t('testing' as any) : t('test' as any)}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleEdit(provider)}
                        className="px-3 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
                      >
                        {t('editProvider' as any)}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(provider.provider_id)}
                        className="px-3 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-700"
                      >
                        {t('deleteProvider' as any)}
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

                  {/* Available Packs Section */}
                  {provider.configured && (
                    <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                      <div className="flex items-center justify-between mb-2">
                        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          Available Packs
                        </h4>
                        {!showPacks[provider.provider_id] ? (
                          <button
                            type="button"
                            onClick={() => loadPacks(provider.provider_id)}
                            disabled={loadingPacks[provider.provider_id]}
                            className="px-3 py-1.5 text-xs bg-gray-600 text-white rounded hover:bg-gray-700 disabled:opacity-50"
                          >
                            {loadingPacks[provider.provider_id] ? 'Loading...' : 'View Packs'}
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setShowPacks(prev => ({ ...prev, [provider.provider_id]: false }))}
                            className="px-3 py-1.5 text-xs bg-gray-600 text-white rounded hover:bg-gray-700"
                          >
                            Hide Packs
                          </button>
                        )}
                      </div>

                      {showPacks[provider.provider_id] && (
                        <div className="space-y-2">
                          {loadingPacks[provider.provider_id] ? (
                            <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-2">
                              {t('loading' as any) || 'Loading...'}
                            </div>
                          ) : packs[provider.provider_id]?.length > 0 ? (
                            <>
                              {packs[provider.provider_id].map((pack) => (
                                <div
                                  key={pack.pack_ref}
                                  className={`p-3 rounded border ${
                                    pack.installed
                                      ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                                      : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                                  }`}
                                >
                                  <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                      <div className="flex items-center gap-2">
                                        <h5 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                                          {pack.display_name}
                                        </h5>
                                        {pack.installed && (
                                          <span className="px-2 py-0.5 text-xs rounded bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                                            {t('installed' as any) || '已安裝'}
                                          </span>
                                        )}
                                      </div>
                                      <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                                        {pack.description}
                                      </p>
                                      <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                                        Version: {pack.version} | Size: {pack.size ? `${(pack.size / 1024).toFixed(1)} KB` : 'N/A'}
                                      </p>
                                    </div>
                                  </div>
                                </div>
                              ))}
                              <div className="pt-2">
                                <button
                                  type="button"
                                  onClick={() => handleInstallPacks(provider.provider_id)}
                                  disabled={installingPacks[provider.provider_id]}
                                  className="w-full px-4 py-2 text-sm bg-gray-900 dark:bg-gray-700 text-white rounded-md hover:bg-gray-800 dark:hover:bg-gray-600 disabled:opacity-50"
                                >
                                  {installingPacks[provider.provider_id]
                                    ? 'Installing...'
                                    : 'Install All Packs'}
                                </button>
                              </div>
                            </>
                          ) : (
                            <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-2">
                              No packs available
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Add/Edit Modal */}
          <BaseModal
            isOpen={showAddForm}
            onClose={resetForm}
            title={editingProvider ? t('editProvider' as any) : t('addProvider' as any)}
            maxWidth="max-w-2xl"
          >
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('providerId' as any)} <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={formData.provider_id}
                  onChange={(e) => setFormData({ ...formData, provider_id: e.target.value })}
                  placeholder={t('enterProviderId' as any)}
                  disabled={!!editingProvider}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 disabled:opacity-50"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {t('providerType' as any)} <span className="text-red-500">*</span>
                </label>
                <input
                  type="hidden"
                  value="generic_http"
                />
                <div className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                  {t('providerTypeGenericHttp' as any)}
                </div>
              </div>

              {formData.provider_type === 'generic_http' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('providerName' as any)} <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={formData.config.name}
                      onChange={(e) => setFormData({
                        ...formData,
                        config: { ...formData.config, name: e.target.value }
                      })}
                      placeholder={t('providerNamePlaceholder' as any)}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('apiUrl' as any)} <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={formData.config.api_url}
                      onChange={(e) => setFormData({
                        ...formData,
                        config: { ...formData.config, api_url: e.target.value }
                      })}
                      placeholder={t('apiUrlPlaceholderGeneric' as any)}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('authenticationType' as any)} <span className="text-red-500">*</span>
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
                      <option value="bearer">{t('bearerToken' as any)}</option>
                      <option value="api_key">{t('apiKey' as any)}</option>
                    </select>
                  </div>
                  {formData.config.auth.auth_type === 'bearer' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('token' as any)} <span className="text-red-500">*</span>
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
                        placeholder={t('tokenPlaceholder' as any)}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                      />
                    </div>
                  )}
                  {formData.config.auth.auth_type === 'api_key' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        {t('apiKey' as any)} <span className="text-red-500">*</span>
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
                        placeholder={t('apiKeyPlaceholder' as any)}
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
                  {t('enableThisProvider' as any)}
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  type="button"
                  onClick={resetForm}
                  className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300"
                >
                  {t('cancel' as any)}
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saving || !formData.provider_id || !formData.config.api_url}
                  className="px-4 py-2 text-sm bg-gray-900 dark:bg-gray-700 text-white rounded-md hover:bg-gray-800 dark:hover:bg-gray-600 disabled:opacity-50"
                >
                  {saving ? t('saving' as any) : editingProvider ? t('update' as any) : t('create' as any)}
                </button>
              </div>
            </div>
          </BaseModal>

          {/* Add Button */}
          {!showAddForm && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setShowAddForm(true)}
                className="px-4 py-2 bg-gray-900 dark:bg-gray-700 text-white rounded-md hover:bg-gray-800 dark:hover:bg-gray-600 text-sm font-medium"
              >
                {t('addProvider' as any)}
              </button>
            </div>
          )}

        </div>
      </Card>
    </div>
  );
}

