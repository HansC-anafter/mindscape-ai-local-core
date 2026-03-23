'use client';

import { t } from '@/lib/i18n';
import { getAddModelType } from '@/app/settings/utils/modelsAndQuotaPanel';

import type {
  CatalogCategory,
  ModelTypeFilter,
  SubTab,
} from './types';

interface ModelsAndQuotaToolbarProps {
  apiProviders: string[];
  catalogCategory: CatalogCategory;
  chatCount: number;
  embeddingCount: number;
  modelTypeFilter: ModelTypeFilter;
  multimodalCount: number;
  searchQuery: string;
  selectedProvider: string | null;
  subTab: SubTab;
  onCatalogCategoryChange: (catalogCategory: CatalogCategory) => void;
  onOpenAddModal: (modelType: string) => void;
  onProviderChange: (provider: string | null) => void;
  onSearchQueryChange: (value: string) => void;
  onSubTabChange: (subTab: SubTab) => void;
  onSwitchTab: (tab: ModelTypeFilter) => void;
}

function getPanelDescription(modelTypeFilter: ModelTypeFilter): string {
  if (modelTypeFilter === 'chat') {
    return '設定與管理負責對話推理的大型語言模型';
  }
  if (modelTypeFilter === 'multimodal') {
    return '管理多模態模型（支援圖片、音訊等輸入）';
  }
  if (modelTypeFilter === 'embedding') {
    return '管理知識庫與記憶向量化模型';
  }
  return '配置工具調用的相關設定';
}

function getCatalogDescription(catalogCategory: CatalogCategory): string {
  if (catalogCategory === 'runtime-cli') {
    return 'CLI 與本機開發工具的憑證與模型設定';
  }
  if (catalogCategory === 'local-deployed') {
    return '管理本地 runtime 可直接拉起的模型';
  }
  return '管理各種雲端或第三方 API 模型';
}

function getTabClass(active: boolean): string {
  return `flex-1 px-4 py-2 text-sm font-medium rounded-md transition-all whitespace-nowrap flex items-center justify-center ${
    active
      ? 'bg-surface-secondary dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
      : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
  }`;
}

function getBadgeClass(active: boolean): string {
  return `ml-1.5 text-xs px-1.5 py-0.5 rounded-full ${
    active
      ? 'bg-accent-10 dark:bg-purple-900/30 text-accent dark:text-purple-300'
      : 'bg-gray-200 dark:bg-gray-600 text-gray-500 dark:text-gray-400'
  }`;
}

export function ModelsAndQuotaToolbar({
  apiProviders,
  catalogCategory,
  chatCount,
  embeddingCount,
  modelTypeFilter,
  multimodalCount,
  searchQuery,
  selectedProvider,
  subTab,
  onCatalogCategoryChange,
  onOpenAddModal,
  onProviderChange,
  onSearchQueryChange,
  onSubTabChange,
  onSwitchTab,
}: ModelsAndQuotaToolbarProps) {
  return (
    <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 pb-3 mb-3">
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4 mb-3">
        <div className="xl:max-w-sm shrink-0">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
            {t('modelsAndQuota' as any) || '模型與配額'}
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed max-w-sm">
            {getPanelDescription(modelTypeFilter)}
          </p>
        </div>

        <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 self-start w-full xl:w-auto xl:flex-1 max-w-3xl">
          <button onClick={() => onSwitchTab('chat')} className={getTabClass(modelTypeFilter === 'chat')}>
            Chat / Plan
            <span className={getBadgeClass(modelTypeFilter === 'chat')}>{chatCount}</span>
          </button>
          <button onClick={() => onSwitchTab('embedding')} className={getTabClass(modelTypeFilter === 'embedding')}>
            知識與記憶
            <span className={getBadgeClass(modelTypeFilter === 'embedding')}>{embeddingCount}</span>
          </button>
          <button
            onClick={() => onSwitchTab('multimodal')}
            className={getTabClass(modelTypeFilter === 'multimodal')}
          >
            多模態
            <span className={getBadgeClass(modelTypeFilter === 'multimodal')}>{multimodalCount}</span>
          </button>
          <button
            onClick={() => onSwitchTab('tool-calling')}
            className={getTabClass(modelTypeFilter === 'tool-calling')}
          >
            工具調用
          </button>
        </div>
      </div>

      {modelTypeFilter !== 'tool-calling' && subTab === 'models' && (
        <div className="flex flex-col gap-2 mb-3">
          <div className="flex flex-wrap items-center gap-2">
            {modelTypeFilter === 'chat' && (
              <button
                onClick={() => onCatalogCategoryChange('runtime-cli')}
                data-filter-button="runtime-cli"
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${
                  catalogCategory === 'runtime-cli'
                    ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-400/40 dark:border-blue-700'
                    : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
                }`}
              >
                Runtime CLI
              </button>
            )}
            <button
              onClick={() => onCatalogCategoryChange('local-deployed')}
              data-filter-button="catalog-local-deployed"
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${
                catalogCategory === 'local-deployed'
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-400/40 dark:border-green-700'
                  : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
              }`}
            >
              本地部署模型
            </button>
            <button
              onClick={() => onCatalogCategoryChange('api')}
              data-filter-button="catalog-api"
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${
                catalogCategory === 'api'
                  ? 'bg-accent-10 dark:bg-purple-900/20 text-accent dark:text-purple-300 border-accent/30 dark:border-purple-700'
                  : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
              }`}
            >
              API 模型
            </button>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {getCatalogDescription(catalogCategory)}
            </span>
          </div>

          {catalogCategory === 'api' && (
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => onProviderChange(null)}
                data-filter-button="all"
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${
                  selectedProvider === null
                    ? 'bg-accent-10 dark:bg-purple-900/20 text-accent dark:text-purple-300 border-accent/30 dark:border-purple-700'
                    : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600 hover:bg-surface-secondary dark:hover:bg-gray-600'
                }`}
              >
                {t('allProviders' as any) || 'All'}
              </button>
              {apiProviders.map((provider) => (
                <button
                  key={provider}
                  onClick={() => onProviderChange(provider)}
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
          )}
        </div>
      )}

      {(modelTypeFilter === 'chat' || modelTypeFilter === 'multimodal') && (
        <div className="flex items-center gap-3 mt-2">
          <div className="flex gap-2">
            <button
              onClick={() => onSubTabChange('models')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                subTab === 'models'
                  ? 'bg-accent-10 dark:bg-purple-900/20 text-accent dark:text-purple-300 border border-accent/30 dark:border-purple-700'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 border border-transparent'
              }`}
            >
              模型清單
            </button>
            <button
              onClick={() => onSubTabChange('dynamic')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                subTab === 'dynamic'
                  ? 'bg-accent-10 dark:bg-purple-900/20 text-accent dark:text-purple-300 border border-accent/30 dark:border-purple-700'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 border border-transparent'
              }`}
            >
              動態分配
            </button>
          </div>
          {subTab === 'models' && catalogCategory !== 'runtime-cli' && (
            <div className="flex flex-1 items-center gap-2">
              <input
                type="text"
                placeholder={t('searchModels' as any) || 'Search models'}
                value={searchQuery}
                onChange={(event) => onSearchQueryChange(event.target.value)}
                className="flex-1 px-3 py-1.5 text-sm border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-gray-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
              />
              <button
                onClick={() => onOpenAddModal(getAddModelType(modelTypeFilter))}
                data-filter-button="add-model"
                className="px-3 py-1.5 text-sm font-medium rounded-md transition-colors border bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700 hover:bg-orange-100 dark:hover:bg-orange-900/40 whitespace-nowrap"
              >
                新增模型
              </button>
            </div>
          )}
        </div>
      )}

      {modelTypeFilter === 'embedding' && (
        <div className="flex items-center gap-2 mt-2">
          <input
            type="text"
            placeholder={t('searchModels' as any) || 'Search models'}
            value={searchQuery}
            onChange={(event) => onSearchQueryChange(event.target.value)}
            className="flex-1 px-3 py-1.5 text-sm border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-gray-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
          />
          <button
            onClick={() => onOpenAddModal('embedding')}
            data-filter-button="add-model"
            className="px-3 py-1.5 text-sm font-medium rounded-md transition-colors border bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700 hover:bg-orange-100 dark:hover:bg-orange-900/40 whitespace-nowrap"
          >
            新增模型
          </button>
        </div>
      )}
    </div>
  );
}
