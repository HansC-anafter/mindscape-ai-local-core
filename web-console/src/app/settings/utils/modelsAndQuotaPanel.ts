import {
  CatalogCategory,
  ModelItem,
  ModelTypeFilter,
} from '@/app/settings/components/panels/modelsAndQuota/types';

export const LOCAL_PROVIDERS = new Set(['ollama', 'llama-cpp', 'llamacpp', 'huggingface']);

export function getAddModelType(modelTypeFilter: ModelTypeFilter): string {
  return modelTypeFilter === 'tool-calling' ? 'chat' : modelTypeFilter;
}

export function filterCatalogModels({
  models,
  modelTypeFilter,
  searchQuery,
  selectedProvider,
  catalogCategory,
}: {
  models: ModelItem[];
  modelTypeFilter: ModelTypeFilter;
  searchQuery: string;
  selectedProvider: string | null;
  catalogCategory: CatalogCategory;
}): ModelItem[] {
  return models.filter((model) => {
    if (modelTypeFilter === 'tool-calling') {
      return false;
    }

    const matchesType = model.model_type === modelTypeFilter;
    const normalizedQuery = searchQuery.trim().toLowerCase();
    const matchesSearch =
      !normalizedQuery ||
      model.display_name.toLowerCase().includes(normalizedQuery) ||
      model.provider.toLowerCase().includes(normalizedQuery) ||
      model.description.toLowerCase().includes(normalizedQuery);

    const isLocalModel = LOCAL_PROVIDERS.has(model.provider);
    const matchesCategory = (() => {
      if (catalogCategory === 'local-deployed') {
        return isLocalModel;
      }
      if (catalogCategory === 'api') {
        if (isLocalModel) {
          return false;
        }
        return selectedProvider === null ? true : model.provider === selectedProvider;
      }
      return false;
    })();

    return matchesType && matchesSearch && matchesCategory;
  });
}

export function getApiProviders(models: ModelItem[], modelTypeFilter: ModelTypeFilter): string[] {
  return Array.from(
    new Set(
      models
        .filter((model) => model.model_type === modelTypeFilter && !LOCAL_PROVIDERS.has(model.provider))
        .map((model) => model.provider)
    )
  ).sort();
}
