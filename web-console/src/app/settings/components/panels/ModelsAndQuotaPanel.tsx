'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { showNotification } from '../../hooks/useSettingsNotification';
import { OllamaToolEmbeddingSection } from './EmbeddingSettings';
import { useEnabledModels } from '../../hooks/useEnabledModels';
import { useModelsAndQuotaHuggingFaceDiscovery } from '../../hooks/useModelsAndQuotaHuggingFaceDiscovery';
import { useModelsAndQuotaPulls } from '../../hooks/useModelsAndQuotaPulls';
import {
  filterCatalogModels,
  getApiProviders,
} from '../../utils/modelsAndQuotaPanel';
import CliApiKeysSection from '../../../workspaces/[workspaceId]/components/CliApiKeysSection';
import {
  CatalogCategory,
  DeploymentScope,
  ModelConfigCardData,
  ModelItem,
  ModelTypeFilter,
  SubTab,
} from './modelsAndQuota/types';
import { HuggingFaceDiscoveryModal } from './modelsAndQuota/HuggingFaceDiscoveryModal';
import { ModelsAndQuotaCatalogView } from './modelsAndQuota/ModelsAndQuotaCatalogView';
import { ModelsAndQuotaDynamicAllocation } from './modelsAndQuota/ModelsAndQuotaDynamicAllocation';
import { ModelsAndQuotaToolbar } from './modelsAndQuota/ModelsAndQuotaToolbar';

export function ModelsAndQuotaPanel() {
  const [loading, setLoading] = useState(true);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelItem | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [modelTypeFilter, setModelTypeFilter] = useState<ModelTypeFilter>('chat');
  const [configCard, setConfigCard] = useState<ModelConfigCardData | null>(null);
  const [togglingModels, setTogglingModels] = useState<Set<string>>(new Set());
  const [hoveredModelId, setHoveredModelId] = useState<string | number | null>(null);
  const [subTab, setSubTab] = useState<SubTab>('models');
  const [catalogCategory, setCatalogCategory] = useState<CatalogCategory>('local-deployed');
  const [deploymentScope, setDeploymentScope] = useState<DeploymentScope>('local');
  const [profileBindings, setProfileBindings] = useState<Record<DeploymentScope, Record<string, string>>>({
    local: {},
    cloud: {},
  });
  const [profileSaving, setProfileSaving] = useState(false);
  const { enabledModels: enabledChatModels } = useEnabledModels('chat');
  const { enabledModels: enabledMultimodalModels } = useEnabledModels('multimodal');
  const [embeddingTesting, setEmbeddingTesting] = useState(false);
  const [embeddingTestResult, setEmbeddingTestResult] = useState<string | null>(null);
  const {
    activePulls,
    handleCancelPull,
    handlePullModel,
  } = useModelsAndQuotaPulls();

  useEffect(() => {
    setEmbeddingTestResult(null);
  }, [selectedModel, modelTypeFilter]);

  const handleRemoveModel = useCallback(async (modelId: string | number) => {
    try {
      const result = await settingsApi.delete<{ success: boolean; message: string }>(
        `/api/v1/system-settings/models/${modelId}`
      );
      if (result.success) {
        showNotification('success', '模型已移除');
        setModels(prev => prev.filter(m => String(m.id) !== String(modelId)));
        if (selectedModel && String(selectedModel.id) === String(modelId)) {
          setSelectedModel(null);
          setConfigCard(null);
        }
      } else {
        showNotification('error', result.message || '移除失敗');
      }
    } catch (err) {
      showNotification('error', `移除失敗: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  }, [selectedModel]);

  const loadProfileBindings = useCallback(async () => {
    try {
      const data = await settingsApi.get<{
        profile_model_map: Record<string, string>;
        profile_model_bindings?: Partial<Record<DeploymentScope, Record<string, string>>>;
      }>('/api/v1/system-settings/capability-profiles');
      setProfileBindings({
        local: data.profile_model_bindings?.local || data.profile_model_map || {},
        cloud: data.profile_model_bindings?.cloud || {},
      });
    } catch { /* silent — routing tab will show defaults */ }
  }, []);

  const saveProfileBindings = async (updated: Record<DeploymentScope, Record<string, string>>) => {
    const prev = {
      local: { ...(profileBindings.local || {}) },
      cloud: { ...(profileBindings.cloud || {}) },
    };
    setProfileBindings(updated);
    setProfileSaving(true);
    try {
      await settingsApi.put('/api/v1/system-settings/capability-profiles', {
        profile_model_bindings: updated,
      });
      showNotification('success', 'Profile routing saved');
    } catch (err) {
      setProfileBindings(prev);
      showNotification('error', err instanceof Error ? err.message : 'Save failed');
    } finally {
      setProfileSaving(false);
    }
  };



  const loadAllModels = useCallback(async () => {
    try {
      setLoading(true);

      const data = await settingsApi.get<Array<{
        id: number;
        model_name: string;
        provider: string;
        model_type: 'chat' | 'embedding' | 'multimodal';
        display_name: string;
        description: string;
        enabled: boolean;
        is_latest?: boolean;
        is_recommended?: boolean;
        is_deprecated?: boolean;
        dimensions?: number;
        context_window?: number;
        icon?: string;
        metadata?: Record<string, any>;
      }>>('/api/v1/system-settings/models');

      const models: ModelItem[] = data.map((m) => ({
        id: m.id,
        model_name: m.model_name,
        provider: m.provider,
        model_type: m.model_type,
        display_name: m.display_name || m.model_name,
        description: m.description,
        enabled: m.enabled,
        icon: m.icon,
        is_latest: m.is_latest,
        is_recommended: m.is_recommended,
        dimensions: m.dimensions,
        context_window: m.context_window,
        metadata: m.metadata,
      }));

      setModels(models);

      const hfMissing = models.filter(
        (m) => m.provider === 'huggingface' && m.model_name.includes('/') && !m.metadata?.hf_author
      );
      if (hfMissing.length > 0) {
        (async () => {
          for (const m of hfMissing) {
            try {
              const hfResp = await fetch(`https://huggingface.co/api/models/${m.model_name}`);
              if (!hfResp.ok) continue;
              const d = await hfResp.json();
              const tags: string[] = (d.tags || []).filter((t: any) => typeof t === 'string');
              const fmt = tags.includes('gguf') ? 'GGUF' : tags.some((t: string) => t.toLowerCase() === 'mlx') ? 'MLX' : 'safetensors';
              const quant = tags.find((t: string) => ['4-bit', '8-bit', 'fp8', 'gptq', 'awq'].some((q) => t.toLowerCase().includes(q))) || null;
              let params = null;
              if (d.safetensors?.total) params = d.safetensors.total;
              if (d.gguf?.total) params = d.gguf.total;
              const ctx = d.gguf?.context_length || null;

              const meta = {
                hf_author: d.author || '',
                hf_format: fmt,
                hf_quantization: quant,
                hf_library: d.library_name || '',
                hf_pipeline_tag: d.pipeline_tag || '',
                hf_parameters: params,
                hf_context_length: ctx,
                hf_downloads: d.downloads || 0,
                hf_likes: d.likes || 0,
                hf_tags: tags.slice(0, 15),
                hf_storage_bytes: d.usedStorage || null,
                runtime_engine: fmt === 'MLX' ? 'mlx' : 'huggingface',
                temperature: 0.6,
              };

              await fetch(`/api/v1/system-settings/models/${m.id}/metadata`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(meta),
              });
              setModels((prev) => prev.map((pm) => pm.id === m.id ? { ...pm, metadata: { ...pm.metadata, ...meta } } : pm));
            } catch {}
          }
        })();
      }
    } catch (err) {
      showNotification('error', err instanceof Error ? err.message : 'Failed to load models');
    } finally {
      setLoading(false);
    }
  }, []);

  const {
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
  } = useModelsAndQuotaHuggingFaceDiscovery(modelTypeFilter, loadAllModels);

  const loadModelConfig = useCallback(async (model: ModelItem) => {
    try {
      const data = await settingsApi.get<ModelConfigCardData>(
        `/api/v1/system-settings/models/${model.id}/config`
      );
      setConfigCard(data);
    } catch (err) {
      const configCardData: ModelConfigCardData = {
        model,
        api_key_configured: false,
        base_url: model.provider === 'ollama' ? 'http://localhost:11434' : undefined,
      };
      setConfigCard(configCardData);
    }
  }, []);

  const handleConfigSaved = () => {
    if (selectedModel) {
      loadModelConfig(selectedModel);
    }
  };

  useEffect(() => {
    if (selectedModel && selectedModel.enabled) {
      loadModelConfig(selectedModel);
    } else {
      setConfigCard(null);
    }
  }, [loadModelConfig, selectedModel]);

  const toggleModel = async (modelId: string, enabled: boolean) => {
    if (togglingModels.has(modelId)) {
      return;
    }

    const currentModel = models.find(m => String(m.id) === modelId);
    if (!currentModel) {
      return;
    }

    const previousEnabled = currentModel.enabled;
    const wasSelected = selectedModel && String(selectedModel.id) === modelId;

    setTogglingModels(prev => new Set(prev).add(modelId));

    setModels(prev => prev.map(m =>
      String(m.id) === modelId ? { ...m, enabled } : m
    ));

    if (enabled) {
      setSelectedModel({ ...currentModel, enabled: true });
    } else if (wasSelected) {
      setSelectedModel(null);
      setConfigCard(null);
    }

    try {
      const numericModelId = Number(modelId);
      if (isNaN(numericModelId)) {
        throw new Error(`Invalid model ID: ${modelId}`);
      }

      const updatedModel = await settingsApi.put<ModelItem>(
        `/api/v1/system-settings/models/${numericModelId}/enable`,
        { enabled }
      );

      setModels(prev => prev.map(m =>
        String(m.id) === modelId ? { ...m, enabled: updatedModel.enabled } : m
      ));

      if (updatedModel.enabled && wasSelected) {
        const updatedSelectedModel = { ...currentModel, enabled: true };
        setSelectedModel(updatedSelectedModel);
        loadModelConfig(updatedSelectedModel);
      }
    } catch (err) {
      showNotification('error', err instanceof Error ? err.message : 'Failed to toggle model');
      setModels(prev => prev.map(m =>
        String(m.id) === modelId ? { ...m, enabled: previousEnabled } : m
      ));

      if (previousEnabled && wasSelected) {
        setSelectedModel({ ...currentModel, enabled: previousEnabled });
      } else if (!previousEnabled && wasSelected) {
        setSelectedModel(null);
        setConfigCard(null);
      }
    } finally {
      setTogglingModels(prev => {
        const next = new Set(prev);
        next.delete(modelId);
        return next;
      });
    }
  };

  const testEmbeddingConnection = useCallback(async () => {
    try {
      setEmbeddingTesting(true);
      setEmbeddingTestResult(null);
      const result = await settingsApi.post<{
        success: boolean;
        message: string;
        model_name: string;
        provider: string;
        dimensions?: number;
      }>('/api/v1/system-settings/llm-models/test-embedding');

      setEmbeddingTestResult(result.message);
    } catch (err) {
      setEmbeddingTestResult(`Test failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setEmbeddingTesting(false);
    }
  }, []);

  useEffect(() => {
    loadAllModels();
    loadProfileBindings();
  }, [loadAllModels, loadProfileBindings]);

  const filteredModels = filterCatalogModels({
    models,
    modelTypeFilter,
    searchQuery,
    selectedProvider,
    catalogCategory,
  });
  const apiProviders = getApiProviders(models, modelTypeFilter);

  const chatCount = models.filter(m => m.model_type === 'chat').length;
  const embeddingCount = models.filter(m => m.model_type === 'embedding').length;
  const multimodalCount = models.filter(m => m.model_type === 'multimodal').length;

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">{t('loading' as any)}</div>;
  }

  const switchTab = (tab: ModelTypeFilter) => {
    setModelTypeFilter(tab);
    setSelectedProvider(null);
    setSelectedModel(null);
    setSubTab('models');
    setCatalogCategory('local-deployed');
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <ModelsAndQuotaToolbar
        apiProviders={apiProviders}
        catalogCategory={catalogCategory}
        chatCount={chatCount}
        embeddingCount={embeddingCount}
        modelTypeFilter={modelTypeFilter}
        multimodalCount={multimodalCount}
        searchQuery={searchQuery}
        selectedProvider={selectedProvider}
        subTab={subTab}
        onCatalogCategoryChange={(nextCategory) => {
          setCatalogCategory(nextCategory);
          setSelectedProvider(null);
          setSelectedModel(null);
        }}
        onOpenAddModal={(nextModelType) => {
          setShowAddModal(true);
          setAddModelType(nextModelType);
        }}
        onProviderChange={setSelectedProvider}
        onSearchQueryChange={setSearchQuery}
        onSubTabChange={setSubTab}
        onSwitchTab={switchTab}
      />

      {modelTypeFilter === 'tool-calling' && (
        <div className="flex-1">
          <OllamaToolEmbeddingSection />
        </div>
      )}

      {modelTypeFilter === 'chat' && subTab === 'models' && catalogCategory === 'runtime-cli' && (
        <div className="flex-1">
          <CliApiKeysSection />
        </div>
      )}

      {subTab === 'dynamic' && (modelTypeFilter === 'chat' || modelTypeFilter === 'multimodal') && (
        <ModelsAndQuotaDynamicAllocation
          deploymentScope={deploymentScope}
          enabledChatModels={enabledChatModels}
          enabledMultimodalModels={enabledMultimodalModels}
          modelTypeFilter={modelTypeFilter}
          profileBindings={profileBindings}
          profileSaving={profileSaving}
          onDeploymentScopeChange={setDeploymentScope}
          onSaveProfileBindings={saveProfileBindings}
        />
      )}

      {modelTypeFilter !== 'tool-calling' && subTab === 'models' && catalogCategory !== 'runtime-cli' && (
        <ModelsAndQuotaCatalogView
          activePulls={activePulls}
          configCard={configCard}
          embeddingTestResult={embeddingTestResult}
          embeddingTesting={embeddingTesting}
          filteredModels={filteredModels}
          hoveredModelId={hoveredModelId}
          modelTypeFilter={modelTypeFilter}
          searchQuery={searchQuery}
          selectedModel={selectedModel}
          togglingModels={togglingModels}
          onCancelPull={handleCancelPull}
          onConfigSaved={handleConfigSaved}
          onHoverModelChange={setHoveredModelId}
          onPullModel={handlePullModel}
          onRemoveModel={handleRemoveModel}
          onSelectModel={setSelectedModel}
          onTestEmbeddingConnection={testEmbeddingConnection}
          onToggleModel={toggleModel}
        />
      )}
      {showAddModal && (
        <HuggingFaceDiscoveryModal
          addModelType={addModelType}
          customRepoId={customRepoId}
          hfLoading={hfLoading}
          hfRegistering={hfRegistering}
          hfResults={hfResults}
          hfSearchQuery={hfSearchQuery}
          onClose={() => setShowAddModal(false)}
          onRegisterCustomId={registerCustomId}
          onRegisterModel={registerModel}
          onSearch={searchHF}
          onSetAddModelType={setAddModelType}
          onSetCustomRepoId={setCustomRepoId}
          onSetSearchQuery={setHfSearchQuery}
        />
      )}
    </div>
  );
}
