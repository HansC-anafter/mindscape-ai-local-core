'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { InlineAlert } from '../InlineAlert';
import { ModelConfigCard } from './ModelConfigCard';

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
  const [configCard, setConfigCard] = useState<ModelConfigCardData | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const loadAllModels = async () => {
    try {
      setLoading(true);
      setError(null);

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
      setError(err instanceof Error ? err.message : 'Failed to load models');
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
      console.error('Failed to load model config:', err);
      const configCardData: ModelConfigCardData = {
        model,
        api_key_configured: false,
        base_url: model.provider === 'ollama' ? 'http://localhost:11434' : undefined,
      };
      setConfigCard(configCardData);
    }
  };

  const toggleModel = async (modelId: string, enabled: boolean) => {
    try {
      setError(null);

      const updatedModel = await settingsApi.put<ModelItem>(
        `/api/v1/system-settings/models/${modelId}/enable`,
        { enabled }
      );

      setModels(prev => prev.map(m =>
        m.id === modelId ? { ...m, enabled: updatedModel.enabled } : m
      ));

      if (enabled) {
        const model = models.find(m => m.id === modelId);
        if (model) {
          setSelectedModel({ ...model, enabled: true });
        }
      } else if (selectedModel?.id === modelId) {
        setSelectedModel(null);
        setConfigCard(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle model');
      setModels(prev => prev.map(m =>
        m.id === modelId ? { ...m, enabled: !enabled } : m
      ));
    }
  };

  const filteredModels = models.filter(model =>
    model.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    model.provider.toLowerCase().includes(searchQuery.toLowerCase()) ||
    model.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">{t('loading')}</div>;
  }

  return (
    <div className="space-y-4">
      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}

      <div>
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
          {t('modelsAndQuota')}
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {t('modelsAndQuotaDescription')}
        </p>
      </div>

      <div className="grid grid-cols-12 gap-4 h-[calc(100vh-16rem)]">
        <div className="col-span-5 border-r border-gray-200 dark:border-gray-700 pr-4">
          <div className="mb-4">
            <input
              type="text"
              placeholder={t('searchModels') || 'Search models'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>

          <div className="space-y-2 max-h-[calc(100vh-20rem)] overflow-y-auto">
            {filteredModels.map((model) => (
              <div
                key={model.id}
                className={`
                  p-3 rounded-lg border cursor-pointer transition-colors
                  ${selectedModel?.id === model.id
                    ? 'bg-purple-50 dark:bg-purple-900/20 border-purple-300 dark:border-purple-700'
                    : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }
                `}
                onClick={() => setSelectedModel(model)}
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
                      onChange={(e) => {
                        e.stopPropagation();
                        toggleModel(model.id, e.target.checked);
                      }}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-purple-300 dark:peer-focus:ring-purple-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-purple-600"></div>
                  </label>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="col-span-7 pl-4">
          {configCard ? (
            <ModelConfigCard card={configCard} />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400 dark:text-gray-500">
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

