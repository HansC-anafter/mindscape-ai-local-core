import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ModelsAndQuotaPanel } from './ModelsAndQuotaPanel';

vi.mock('../../hooks/useEnabledModels', () => ({
  useEnabledModels: () => ({ enabledModels: [] }),
}));

vi.mock('../../hooks/useModelsAndQuotaHuggingFaceDiscovery', () => ({
  useModelsAndQuotaHuggingFaceDiscovery: () => ({
    addModelType: 'chat',
    customRepoId: '',
    hfLoading: false,
    hfRegistering: false,
    hfResults: [],
    hfSearchQuery: '',
    registerCustomId: vi.fn(),
    registerModel: vi.fn(),
    searchHF: vi.fn(),
    setAddModelType: vi.fn(),
    setCustomRepoId: vi.fn(),
    setHfSearchQuery: vi.fn(),
    setShowAddModal: vi.fn(),
    showAddModal: false,
  }),
}));

vi.mock('../../hooks/useModelsAndQuotaPulls', () => ({
  useModelsAndQuotaPulls: () => ({
    activePulls: {},
    handleCancelPull: vi.fn(),
    handlePullModel: vi.fn(),
  }),
}));

vi.mock('../../utils/settingsApi', () => ({
  settingsApi: {
    get: vi.fn(async (path: string) => {
      if (path === '/api/v1/system-settings/models') {
        return [];
      }
      if (path === '/api/v1/system-settings/capability-profiles') {
        return { profile_model_bindings: { local: {}, cloud: {} } };
      }
      return {};
    }),
    put: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../hooks/useSettingsNotification', () => ({
  showNotification: vi.fn(),
}));

vi.mock('./EmbeddingSettings', () => ({
  OllamaToolEmbeddingSection: () => <div data-testid="mock-tool-embedding-section" />,
}));

vi.mock('./modelsAndQuota/ModelsAndQuotaToolbar', () => ({
  ModelsAndQuotaToolbar: () => <div data-testid="mock-models-toolbar" />,
}));

vi.mock('./modelsAndQuota/ModelsAndQuotaCatalogView', () => ({
  ModelsAndQuotaCatalogView: () => <div data-testid="mock-models-catalog-view" />,
}));

vi.mock('./modelsAndQuota/ModelsAndQuotaDynamicAllocation', () => ({
  ModelsAndQuotaDynamicAllocation: () => <div data-testid="mock-models-dynamic-allocation" />,
}));

vi.mock('./modelsAndQuota/HuggingFaceDiscoveryModal', () => ({
  HuggingFaceDiscoveryModal: () => <div data-testid="mock-hf-discovery-modal" />,
}));

vi.mock('../../../workspaces/[workspaceId]/components/CliApiKeysSection', () => ({
  default: ({ workspaceId }: { workspaceId?: string }) => (
    <div data-testid="mock-cli-api-keys-section" data-workspace-id={workspaceId || ''} />
  ),
}));

describe('ModelsAndQuotaPanel workspace Runtime CLI entry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens the Runtime CLI catalog with workspace-scoped settings', async () => {
    render(
      <ModelsAndQuotaPanel
        workspaceId="ws_test"
        initialCatalogCategory="runtime-cli"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mock-cli-api-keys-section')).toBeInTheDocument();
    });
    expect(screen.getByTestId('mock-cli-api-keys-section')).toHaveAttribute('data-workspace-id', 'ws_test');
    expect(screen.queryByTestId('mock-models-catalog-view')).not.toBeInTheDocument();
  });
});
