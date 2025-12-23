'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { ModelConfigCard } from './ModelConfigCard';
import { showNotification } from '../../hooks/useSettingsNotification';

interface ModelItem {
  id: string | number;
  model_name: string;
  provider: string;
  model_type: 'chat' | 'embedding';
  display_name: string;
  description: string;
  enabled: boolean;
  icon?: string;
  is_latest?: boolean;
  is_recommended?: boolean;
  dimensions?: number;
  context_window?: number;
}

interface ModelConfigCardData {
  model: ModelItem;
  api_key_configured: boolean;
  base_url?: string;
  quota_info?: {
    used: number;
    limit: number;
    reset_date?: string;
  };
}

export function ModelsAndQuotaPanel() {
  const [loading, setLoading] = useState(true);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelItem | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [configCard, setConfigCard] = useState<ModelConfigCardData | null>(null);
  const [togglingModels, setTogglingModels] = useState<Set<string>>(new Set());
  const [hoveredModelId, setHoveredModelId] = useState<string | number | null>(null);

  useEffect(() => {
    loadAllModels();
  }, []);

  useEffect(() => {
    if (selectedModel && selectedModel.enabled) {
      loadModelConfig(selectedModel);
    } else {
      setConfigCard(null);
    }
  }, [selectedModel]);

  const handleConfigSaved = () => {
    if (selectedModel) {
      loadModelConfig(selectedModel);
    }
  };

  const loadAllModels = async () => {
    try {
      setLoading(true);

      const data = await settingsApi.get<Array<{
        id: number;
        model_name: string;
        provider: string;
        model_type: 'chat' | 'embedding';
        display_name: string;
        description: string;
        enabled: boolean;
        is_latest?: boolean;
        is_recommended?: boolean;
        is_deprecated?: boolean;
        dimensions?: number;
        context_window?: number;
        icon?: string;
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
      }));

      setModels(models);
    } catch (err) {
      showNotification('error', err instanceof Error ? err.message : 'Failed to load models');
    } finally {
      setLoading(false);
    }
  };

  const loadModelConfig = async (model: ModelItem) => {
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
  };

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

  const providers = Array.from(new Set(models.map(m => m.provider))).sort();

  const filteredModels = models.filter(model => {
    const matchesSearch = !searchQuery ||
      model.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      model.provider.toLowerCase().includes(searchQuery.toLowerCase()) ||
      model.description.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesProvider = !selectedProvider || model.provider === selectedProvider;

    return matchesSearch && matchesProvider;
  });

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">{t('loading')}</div>;
  }

  return (
    <div className="flex flex-col min-h-full">
      <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 pb-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
              {t('modelsAndQuota')}
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {t('modelsAndQuotaDescription')}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setSelectedProvider(null)}
              data-filter-button="all"
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${
                selectedProvider === null
                  ? 'bg-accent-10 dark:bg-purple-900/20 text-accent dark:text-purple-300 border-accent/30 dark:border-purple-700'
                  : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
              }`}
            >
              {t('allProviders') || 'All'}
            </button>
            {providers.map((provider) => (
              <button
                key={provider}
                onClick={() => setSelectedProvider(provider)}
                data-filter-button={provider}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${
                  selectedProvider === provider
                    ? 'bg-accent-10 dark:bg-purple-900/20 text-accent dark:text-purple-300 border-accent/30 dark:border-purple-700'
                    : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
                }`}
              >
                {provider}
              </button>
            ))}
          </div>
        </div>
        <input
          type="text"
          placeholder={t('searchModels') || 'Search models'}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-gray-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
        />
      </div>

      <div className="grid grid-cols-12 gap-4 flex-1 min-h-0">
        <div className="col-span-5 border-r border-gray-200 dark:border-gray-700 pr-4 flex flex-col">

          <div className="space-y-2 flex-1 overflow-y-auto min-h-0">
            {filteredModels.map((model, index) => {
              const isSelected = selectedModel?.id === model.id;
              const isHovered = hoveredModelId === model.id && !isSelected;
              const cardClasses = `
                  p-3 rounded-lg border cursor-pointer transition-colors
                  ${isSelected
                    ? 'bg-accent-10 dark:bg-purple-900/20 border-accent/30 dark:border-purple-700'
                    : isHovered
                    ? 'bg-tertiary dark:hover:bg-gray-700 border-default dark:border-gray-700'
                    : 'bg-surface-secondary dark:bg-gray-800 border-default dark:border-gray-700'
                  }
                `;

              return (
              <div
                key={model.id}
                data-model-id={model.id}
                className={cardClasses}
                onClick={() => setSelectedModel(model)}
                onMouseEnter={(e) => {
                  e.stopPropagation();
                  if (!isSelected) {
                    setHoveredModelId(model.id);
                  }
                }}
                onMouseLeave={(e) => {
                  e.stopPropagation();
                  setHoveredModelId(null);
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {model.icon && <span className="text-lg">{model.icon}</span>}
                    <div>
                      <div className="font-medium text-sm text-gray-900 dark:text-gray-100">
                        {model.display_name}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {model.provider} • {model.model_type === 'chat' ? 'Chat' : 'Embedding'}
                      </div>
                    </div>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={model.enabled}
                      disabled={togglingModels.has(String(model.id))}
                      onChange={(e) => {
                        e.stopPropagation();
                        toggleModel(String(model.id), e.target.checked);
                      }}
                      className="sr-only peer"
                    />
                    <div className={`w-11 h-6 bg-gray-300 dark:bg-gray-600 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-accent/30 dark:peer-focus:ring-purple-600 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 dark:after:border-gray-600 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent dark:peer-checked:bg-purple-700/80 ${togglingModels.has(String(model.id)) ? 'opacity-50 cursor-wait' : ''}`}></div>
                  </label>
                </div>
              </div>
              );
            })}
          </div>
        </div>

        <div className="col-span-7 pl-4 flex flex-col min-h-0">
          {configCard ? (
            <div className="flex-1 overflow-y-auto">
              <ModelConfigCard card={configCard} onConfigSaved={handleConfigSaved} />
            </div>
          ) : (
            <div className="flex items-center justify-center flex-1 text-gray-400 dark:text-gray-500">
              {selectedModel && !selectedModel.enabled
                ? t('enableModelToConfigure') || 'Please enable the model to view configuration'
                : t('selectModelToConfigure') || 'Select an enabled model to view configuration'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

