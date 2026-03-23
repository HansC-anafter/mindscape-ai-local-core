'use client';

import { useCallback, useEffect, useState } from 'react';

import { HuggingFaceModelResult, ModelTypeFilter } from '../components/panels/modelsAndQuota/types';
import { showNotification } from './useSettingsNotification';
import { settingsApi } from '../utils/settingsApi';
import { getAddModelType } from '../utils/modelsAndQuotaPanel';

export function useModelsAndQuotaHuggingFaceDiscovery(
  modelTypeFilter: ModelTypeFilter,
  onRegisterSuccess: () => void | Promise<void>
) {
  const [showAddModal, setShowAddModal] = useState(false);
  const [hfSearchQuery, setHfSearchQuery] = useState('');
  const [hfResults, setHfResults] = useState<HuggingFaceModelResult[]>([]);
  const [hfLoading, setHfLoading] = useState(false);
  const [hfRegistering, setHfRegistering] = useState<string | null>(null);
  const [customRepoId, setCustomRepoId] = useState('');
  const [addModelType, setAddModelType] = useState<string>(getAddModelType(modelTypeFilter));

  const runSearch = useCallback(async (search: string, nextModelType: string) => {
    setHfLoading(true);
    try {
      const suffix = search ? `&search=${encodeURIComponent(search)}` : '';
      const results = await settingsApi.get<HuggingFaceModelResult[]>(
        `/api/v1/system-settings/discover/huggingface?model_type=${nextModelType}&limit=20${suffix}`
      );
      setHfResults(results);
    } finally {
      setHfLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!showAddModal) {
      return;
    }

    runSearch(hfSearchQuery, addModelType).catch(() => {
      return;
    });
  }, [addModelType, hfSearchQuery, runSearch, showAddModal]);

  const searchHF = useCallback(async () => {
    try {
      await runSearch(hfSearchQuery, addModelType);
    } catch (error) {
      showNotification(
        'error',
        `Hugging Face search failed: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    }
  }, [addModelType, hfSearchQuery, runSearch]);

  const registerModel = useCallback(async (modelId: string, modelType: string) => {
    setHfRegistering(modelId);
    try {
      await settingsApi.post('/api/v1/system-settings/models/custom', {
        model_id: modelId,
        provider: 'huggingface',
        model_type: modelType,
      });
      showNotification('success', `Registered: ${modelId}`);
      await onRegisterSuccess();
    } catch (error) {
      showNotification(
        'error',
        `Registration failed: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    } finally {
      setHfRegistering(null);
    }
  }, [onRegisterSuccess]);

  const registerCustomId = useCallback(async () => {
    const repoId = customRepoId.trim();
    if (!repoId) {
      return;
    }

    setHfRegistering(repoId);
    try {
      await settingsApi.post('/api/v1/system-settings/models/custom', {
        model_id: repoId,
        provider: 'huggingface',
        model_type: addModelType,
      });
      showNotification('success', `Registered: ${repoId}`);
      setCustomRepoId('');
      await onRegisterSuccess();
    } catch (error) {
      showNotification(
        'error',
        `Registration failed: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    } finally {
      setHfRegistering(null);
    }
  }, [addModelType, customRepoId, onRegisterSuccess]);

  return {
    addModelType,
    customRepoId,
    hfLoading,
    hfRegistering,
    hfResults,
    hfSearchQuery,
    registerCustomId,
    registerModel,
    searchHF,
    setAddModelType,
    setCustomRepoId,
    setHfSearchQuery,
    setShowAddModal,
    showAddModal,
  };
}
