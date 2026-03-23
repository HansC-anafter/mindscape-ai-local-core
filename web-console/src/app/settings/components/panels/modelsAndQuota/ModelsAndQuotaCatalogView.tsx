'use client';

import { t } from '@/lib/i18n';
import { ModelConfigCard, type PullState } from '@/app/settings/components/panels/ModelConfigCard';

import type {
  ModelConfigCardData,
  ModelItem,
  ModelTypeFilter,
} from './types';

interface ModelsAndQuotaCatalogViewProps {
  activePulls: Record<string, PullState>;
  configCard: ModelConfigCardData | null;
  embeddingTestResult: string | null;
  embeddingTesting: boolean;
  filteredModels: ModelItem[];
  hoveredModelId: string | number | null;
  modelTypeFilter: ModelTypeFilter;
  searchQuery: string;
  selectedModel: ModelItem | null;
  togglingModels: Set<string>;
  onCancelPull: (taskId: string) => void | Promise<void>;
  onConfigSaved: () => void;
  onHoverModelChange: (modelId: string | number | null) => void;
  onPullModel: (model: Pick<ModelItem, 'id' | 'model_name' | 'provider'>) => void | Promise<void>;
  onRemoveModel: (modelId: string | number) => void | Promise<void>;
  onSelectModel: (model: ModelItem) => void;
  onTestEmbeddingConnection: () => void | Promise<void>;
  onToggleModel: (modelId: string, enabled: boolean) => void | Promise<void>;
}

export function ModelsAndQuotaCatalogView({
  activePulls,
  configCard,
  embeddingTestResult,
  embeddingTesting,
  filteredModels,
  hoveredModelId,
  modelTypeFilter,
  searchQuery,
  selectedModel,
  togglingModels,
  onCancelPull,
  onConfigSaved,
  onHoverModelChange,
  onPullModel,
  onRemoveModel,
  onSelectModel,
  onTestEmbeddingConnection,
  onToggleModel,
}: ModelsAndQuotaCatalogViewProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
      <div className="lg:col-span-5 lg:border-r border-gray-200 dark:border-gray-700 lg:pr-4 flex flex-col min-h-0">
        <div className="space-y-2 flex-1 overflow-y-auto overflow-x-hidden min-h-0 pr-2">
          {filteredModels.length === 0 ? (
            <div className="text-center py-8 text-sm text-gray-400 dark:text-gray-500">
              {searchQuery
                ? t('noMatchingModels' as any) || 'No matching models'
                : t('noModelsInCategory' as any) || 'No models in this category'}
            </div>
          ) : (
            filteredModels.map((model) => {
              const isSelected = selectedModel?.id === model.id;
              const isHovered = hoveredModelId === model.id && !isSelected;
              const cardClasses = `
                p-3 rounded-lg border cursor-pointer transition-colors
                ${
                  isSelected
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
                  onClick={() => onSelectModel(model)}
                  onMouseEnter={(event) => {
                    event.stopPropagation();
                    if (!isSelected) {
                      onHoverModelChange(model.id);
                    }
                  }}
                  onMouseLeave={(event) => {
                    event.stopPropagation();
                    onHoverModelChange(null);
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
                          {model.provider}
                          {model.model_type === 'embedding' && model.dimensions && (
                            <span> • {model.dimensions}d</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={model.enabled}
                        disabled={togglingModels.has(String(model.id))}
                        onChange={(event) => {
                          event.stopPropagation();
                          onToggleModel(String(model.id), event.target.checked);
                        }}
                        className="sr-only peer"
                      />
                      <div
                        className={`w-11 h-6 bg-gray-300 dark:bg-gray-600 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-accent/30 dark:peer-focus:ring-purple-600 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 dark:after:border-gray-600 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent dark:peer-checked:bg-purple-700/80 ${
                          togglingModels.has(String(model.id)) ? 'opacity-50 cursor-wait' : ''
                        }`}
                      />
                    </label>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      <div className="lg:col-span-7 lg:pl-4 flex flex-col min-h-0">
        <div className="flex-1 overflow-y-auto overflow-x-hidden min-h-0 pr-2">
          {configCard ? (
            <div className="space-y-4">
              <ModelConfigCard
                card={configCard}
                onConfigSaved={onConfigSaved}
                pullState={activePulls[String(selectedModel?.id)] || null}
                onPullModel={onPullModel}
                onCancelPull={onCancelPull}
                onRemoveModel={onRemoveModel}
              />

              {modelTypeFilter === 'embedding' && selectedModel?.enabled && (
                <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={onTestEmbeddingConnection}
                      disabled={embeddingTesting}
                      className="px-4 py-2 text-sm bg-accent dark:bg-blue-700 text-white rounded-md hover:bg-accent/90 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {embeddingTesting
                        ? t('testing' as any) || 'Testing...'
                        : t('testConnection' as any) || 'Test Connection'}
                    </button>
                  </div>
                  {embeddingTestResult && (
                    <div
                      className={`mt-3 p-3 rounded-md text-sm ${
                        embeddingTestResult.toLowerCase().includes('success')
                          ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300 border border-green-200 dark:border-green-800'
                          : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300 border border-red-200 dark:border-red-800'
                      }`}
                    >
                      {embeddingTestResult}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center py-16 text-gray-400 dark:text-gray-500 text-sm">
              {selectedModel && !selectedModel.enabled
                ? t('enableModelToConfigure' as any) || 'Please enable the model to view configuration'
                : t('selectModelToConfigure' as any) || 'Select an enabled model to view configuration'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
