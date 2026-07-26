'use client';

import React, { useEffect, useState } from 'react';
import { useT } from '../../../../lib/i18n';
import { Card } from '../Card';
import { showNotification } from '../../hooks/useSettingsNotification';
import { CloudFrontendUrlSection } from './cloudExtensionSettings/CloudFrontendUrlSection';
import { LoadingState } from './cloudExtensionSettings/LoadingState';
import { ProviderFormSection } from './cloudExtensionSettings/ProviderFormSection';
import { ProviderListSection } from './cloudExtensionSettings/ProviderListSection';
import {
  buildCloudProviderFormFromProvider,
  createEmptyCloudProviderForm,
} from './cloudExtensionSettings/formState';
import { buildInstallDefaultPacksAcceptedMessage } from './cloudExtensionSettings/installResult';
import {
  deleteCloudProvider,
  installDefaultCloudProviderPacks,
  loadCloudFrontendUrlSetting,
  loadCloudProviderPacks,
  loadCloudProviders,
  saveCloudFrontendUrlSetting,
  saveCloudProvider,
  testCloudProvider,
} from './cloudExtensionSettings/resourceActions';
import type {
  CloudExtensionSettingsProps,
  CloudProviderFormData,
  Pack,
  Provider,
  TestStatus,
} from './cloudExtensionSettings/types';

export function CloudExtensionSettings(_props: CloudExtensionSettingsProps) {
  const t = useT();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [testStatus, setTestStatus] = useState<Record<string, TestStatus>>({});
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});
  const [cloudFrontendUrl, setCloudFrontendUrl] = useState('');
  const [savingFrontendUrl, setSavingFrontendUrl] = useState(false);
  const [packs, setPacks] = useState<Record<string, Pack[]>>({});
  const [loadingPacks, setLoadingPacks] = useState<Record<string, boolean>>({});
  const [installingPacks, setInstallingPacks] = useState<Record<string, boolean>>({});
  const [showPacks, setShowPacks] = useState<Record<string, boolean>>({});
  const [formData, setFormData] = useState<CloudProviderFormData>(createEmptyCloudProviderForm);

  useEffect(() => {
    void loadProvidersList();
    void loadCloudFrontendUrl();
  }, []);

  const loadCloudFrontendUrl = async () => {
    try {
      const value = await loadCloudFrontendUrlSetting();
      setCloudFrontendUrl(value);
    } catch (error) {
      console.error('Failed to load cloud frontend URL:', error);
    }
  };

  const handleSaveCloudFrontendUrl = async () => {
    try {
      setSavingFrontendUrl(true);
      await saveCloudFrontendUrlSetting(cloudFrontendUrl);
      showNotification('success', t('cloudFrontendUrlSaved' as any));
    } catch (error: any) {
      showNotification('error', error.message || t('failedToSaveCloudFrontendUrl' as any));
    } finally {
      setSavingFrontendUrl(false);
    }
  };

  const loadProvidersList = async () => {
    try {
      setLoading(true);
      const loadedProviders = await loadCloudProviders();
      setProviders(loadedProviders);
    } catch (error: any) {
      console.error('Failed to load providers:', error);
      showNotification('error', error.message || t('failedToLoadProviders' as any));
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFormData(createEmptyCloudProviderForm());
    setShowAddForm(false);
    setEditingProvider(null);
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await saveCloudProvider(formData, Boolean(editingProvider));
      showNotification(
        'success',
        editingProvider
          ? t('providerUpdatedSuccessfully' as any)
          : t('providerCreatedSuccessfully' as any),
      );
      resetForm();
      void loadProvidersList();
    } catch (error: any) {
      showNotification(
        'error',
        error.message
          || (editingProvider
            ? t('failedToUpdateProvider' as any)
            : t('failedToCreateProvider' as any)),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (providerId: string) => {
    if (!confirm(t('deleteProviderConfirm' as any).replace('{providerId}', providerId))) {
      return;
    }

    try {
      await deleteCloudProvider(providerId);
      showNotification('success', t('providerDeletedSuccessfully' as any));
      void loadProvidersList();
    } catch (error: any) {
      showNotification('error', error.message || t('failedToDeleteProvider' as any));
    }
  };

  const handleEdit = (provider: Provider) => {
    setEditingProvider(provider);
    setFormData(buildCloudProviderFormFromProvider(provider));
    setShowAddForm(true);
  };

  const handleTestConnection = async (providerId: string) => {
    setTestStatus(prev => ({ ...prev, [providerId]: 'testing' }));
    setTestMessages(prev => ({ ...prev, [providerId]: t('testingConnection' as any) }));

    try {
      const result = await testCloudProvider(providerId);
      setTestStatus(prev => ({ ...prev, [providerId]: result.success ? 'success' : 'error' }));
      setTestMessages(prev => ({
        ...prev,
        [providerId]: result.message || (result.success
          ? t('connectionSuccessful' as any)
          : t('connectionFailed' as any)),
      }));
    } catch (error: any) {
      setTestStatus(prev => ({ ...prev, [providerId]: 'error' }));
      setTestMessages(prev => ({ ...prev, [providerId]: error.message || t('connectionTestFailed' as any) }));
    }
  };

  const handleLoadPacks = async (providerId: string) => {
    setLoadingPacks(prev => ({ ...prev, [providerId]: true }));
    try {
      const loadedPacks = await loadCloudProviderPacks(providerId);
      setPacks(prev => ({ ...prev, [providerId]: loadedPacks }));
      setShowPacks(prev => ({ ...prev, [providerId]: true }));
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
      const result = await installDefaultCloudProviderPacks(providerId);

      if (result.success) {
        showNotification('success', buildInstallDefaultPacksAcceptedMessage(result));
      } else {
        const errorMsg = result.message || result.detail || 'Failed to install packs';
        showNotification('error', `Install failed: ${errorMsg}`);
      }
    } catch (error: any) {
      console.error('Failed to install packs:', error);
      showNotification('error', error.message || 'Failed to install packs');
    } finally {
      setInstallingPacks(prev => ({ ...prev, [providerId]: false }));
    }
  };

  if (loading) {
    return <LoadingState />;
  }

  return (
    <div className="space-y-6">
      <CloudFrontendUrlSection
        value={cloudFrontendUrl}
        saving={savingFrontendUrl}
        onChange={setCloudFrontendUrl}
        onSave={handleSaveCloudFrontendUrl}
      />

      <Card>
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              {t('cloudPlaybookProviders' as any)}
            </h2>
          </div>

          <ProviderListSection
            providers={providers}
            packs={packs}
            loadingPacks={loadingPacks}
            installingPacks={installingPacks}
            showPacks={showPacks}
            testStatus={testStatus}
            testMessages={testMessages}
            onTestConnection={handleTestConnection}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onLoadPacks={handleLoadPacks}
            onHidePacks={(providerId) => setShowPacks(prev => ({ ...prev, [providerId]: false }))}
            onInstallPacks={handleInstallPacks}
          />

          {showAddForm && (
            <ProviderFormSection
              formData={formData}
              saving={saving}
              editingProvider={editingProvider}
              onFormDataChange={setFormData}
              onCancel={resetForm}
              onSave={handleSave}
            />
          )}

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
