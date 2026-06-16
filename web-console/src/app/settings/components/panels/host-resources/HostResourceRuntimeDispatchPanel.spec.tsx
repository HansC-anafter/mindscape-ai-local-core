import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { HostResourceRuntimeDispatchPanel } from './HostResourceRuntimeDispatchPanel';
import { settingsApi } from '../../../utils/settingsApi';

vi.mock('../../../utils/settingsApi', () => ({
  settingsApi: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const mockedSettingsApi = vi.mocked(settingsApi);

describe('HostResourceRuntimeDispatchPanel', () => {
  beforeEach(() => {
    mockedSettingsApi.get.mockReset();
    mockedSettingsApi.post.mockReset();
  });

  it('loads selector and target metadata without issuing mutation requests', async () => {
    mockedSettingsApi.get.mockImplementation(async (endpoint: string) => {
      if (endpoint === '/api/v1/runtime-dispatch/selector-types') {
        return {
          feature_gate: { enabled: false, reason: 'runtime_dispatch_disabled' },
          selector_types: [
            {
              selector_type: 'explicit_object_refs',
              label: 'Explicit object references',
              workspace_scope_required: true,
              max_items: 500,
            },
          ],
          limits: { max_items: 500 },
        };
      }
      if (endpoint === '/api/v1/runtime-dispatch/targets?workspace_id=ws-runtime') {
        return {
          feature_gate: { enabled: false, reason: 'runtime_dispatch_disabled' },
          metadata_source: 'host_resources_lane_registry',
          targets: [
            {
              target_id: 'runner:qwen9b',
              lane_id: 'runner:qwen9b',
              label: 'Qwen 9B',
              queue_shard: 'vision_mlx_dev',
              runner_profile: 'vision_mlx_dev',
              assignable: true,
              capacity_summary: {
                available_slots_total: 1,
                pending: 0,
              },
            },
          ],
        };
      }
      throw new Error(`unexpected endpoint ${endpoint}`);
    });

    render(<HostResourceRuntimeDispatchPanel workspaceId="ws-runtime" />);

    await waitFor(() => {
      expect(screen.getByText('Runtime Dispatch')).toBeInTheDocument();
      expect(screen.getByText('Qwen 9B')).toBeInTheDocument();
    });
    expect(screen.getByText('Disabled')).toBeInTheDocument();
    expect(mockedSettingsApi.get).toHaveBeenCalledWith('/api/v1/runtime-dispatch/selector-types');
    expect(mockedSettingsApi.get).toHaveBeenCalledWith('/api/v1/runtime-dispatch/targets?workspace_id=ws-runtime');
    expect(mockedSettingsApi.post).not.toHaveBeenCalled();
  });

  it('does not call runtime dispatch metadata endpoints without workspace id', async () => {
    render(<HostResourceRuntimeDispatchPanel />);

    expect(await screen.findByText('Workspace id is required for runtime dispatch metadata.')).toBeInTheDocument();
    expect(mockedSettingsApi.get).not.toHaveBeenCalled();
    expect(mockedSettingsApi.post).not.toHaveBeenCalled();
  });
});
