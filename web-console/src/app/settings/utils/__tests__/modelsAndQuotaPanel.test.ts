import { describe, expect, it } from 'vitest';

import {
  filterCatalogModels,
  getAddModelType,
  getApiProviders,
} from '@/app/settings/utils/modelsAndQuotaPanel';

const MODELS = [
  {
    id: 1,
    model_name: 'local-chat',
    provider: 'ollama',
    model_type: 'chat' as const,
    display_name: 'Local Chat',
    description: 'Local runtime chat model',
    enabled: true,
  },
  {
    id: 2,
    model_name: 'cloud-chat',
    provider: 'openai',
    model_type: 'chat' as const,
    display_name: 'Cloud Chat',
    description: 'Cloud API chat model',
    enabled: true,
  },
  {
    id: 3,
    model_name: 'cloud-embedding',
    provider: 'openai',
    model_type: 'embedding' as const,
    display_name: 'Cloud Embedding',
    description: 'Embedding model',
    enabled: true,
  },
];

describe('modelsAndQuotaPanel utils', () => {
  it('maps tool-calling add model type back to chat', () => {
    expect(getAddModelType('tool-calling')).toBe('chat');
    expect(getAddModelType('embedding')).toBe('embedding');
  });

  it('filters local deployed models by type and search query', () => {
    const result = filterCatalogModels({
      models: MODELS,
      modelTypeFilter: 'chat',
      searchQuery: 'local',
      selectedProvider: null,
      catalogCategory: 'local-deployed',
    });

    expect(result).toHaveLength(1);
    expect(result[0].model_name).toBe('local-chat');
  });

  it('filters api models by selected provider', () => {
    const result = filterCatalogModels({
      models: MODELS,
      modelTypeFilter: 'chat',
      searchQuery: '',
      selectedProvider: 'openai',
      catalogCategory: 'api',
    });

    expect(result).toHaveLength(1);
    expect(result[0].model_name).toBe('cloud-chat');
  });

  it('returns sorted api providers for the selected type', () => {
    expect(getApiProviders(MODELS, 'chat')).toEqual(['openai']);
    expect(getApiProviders(MODELS, 'embedding')).toEqual(['openai']);
  });
});
