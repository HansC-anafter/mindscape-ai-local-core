'use client';

import { useEffect, useState } from 'react';
import { t } from '../../../../lib/i18n';
import { showNotification } from '../../hooks/useSettingsNotification';
import { CloudPlaybookProvidersSettingsView } from './cloudPlaybookProvidersSettings/CloudPlaybookProvidersSettingsView';
import {
  buildCloudProviderFormFromProvider,
  createEmptyCloudProviderForm,
} from './cloudPlaybookProvidersSettings/formState';
import { buildInstallDefaultPacksAcceptedMessage } from './cloudPlaybookProvidersSettings/installResult';
import {
  deleteCloudProvider,
  installDefaultCloudProviderPacks,
  loadCloudProviderPacks,
  loadCloudProviders,
  saveCloudProvider,
  testCloudProvider,
} from './cloudPlaybookProvidersSettings/resourceActions';
import type {
  CloudProviderFormData,
  Pack,
  Provider,
  TestStatus,
} from './cloudPlaybookProvidersSettings/types';

export function CloudPlaybookProvidersSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [testStatus, setTestStatus] = useState<Record<string, TestStatus>>({});
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});
  const [packs, setPacks] = useState<Record<string, Pack[]>>({});
  const [loadingPacks, setLoadingPacks] = useState<Record<string, boolean>>({});
  const [installingPacks, setInstallingPacks] = useState<Record<string, boolean>>({});
  const [showPacks, setShowPacks] = useState<Record<string, boolean>>({});
  const [formData, setFormData] = useState<CloudProviderFormData>(createEmptyCloudProviderForm);

  useEffect(() => {
    void loadProvidersList();
  }, []);

  const loadProvidersList = async () => {
    try {
      setLoading(true);
      setProviders(await loadCloudProviders());
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

  return (
    <CloudPlaybookProvidersSettingsView
      loading={loading}
      providers={providers}
      packs={packs}
      loadingPacks={loadingPacks}
      installingPacks={installingPacks}
      showPacks={showPacks}
      testStatus={testStatus}
      testMessages={testMessages}
      showAddForm={showAddForm}
      editingProvider={editingProvider}
      formData={formData}
      saving={saving}
      onTestConnection={handleTestConnection}
      onEdit={handleEdit}
      onDelete={handleDelete}
      onLoadPacks={handleLoadPacks}
      onHidePacks={(providerId) => setShowPacks(prev => ({ ...prev, [providerId]: false }))}
      onInstallPacks={handleInstallPacks}
      onFormDataChange={setFormData}
      onResetForm={resetForm}
      onSave={handleSave}
      onShowAddForm={() => setShowAddForm(true)}
    />
  );
}
