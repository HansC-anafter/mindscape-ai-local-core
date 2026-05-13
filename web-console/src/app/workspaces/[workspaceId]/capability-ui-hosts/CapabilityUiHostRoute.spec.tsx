import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockRenderCapabilityUiHostPage = vi.fn();

vi.mock('./renderCapabilityUiHostPage', () => ({
  renderCapabilityUiHostPage: (...args: any[]) => mockRenderCapabilityUiHostPage(...args),
}));

import CapabilityUiHostPage from './[capabilityCode]/[[...surfacePath]]/page';

describe('canonical capability UI host route', () => {
  beforeEach(() => {
    mockRenderCapabilityUiHostPage.mockReset();
  });

  it('delegates rendering to the single workspace-scoped host owner with surface path', async () => {
    mockRenderCapabilityUiHostPage.mockResolvedValue('rendered');

    const result = await CapabilityUiHostPage({
      params: {
        workspaceId: 'ws_demo',
        capabilityCode: 'performance_direction',
        surfacePath: ['sessions', 'ds_route_001'],
      },
    });

    expect(mockRenderCapabilityUiHostPage).toHaveBeenCalledWith({
      workspaceId: 'ws_demo',
      capabilityCode: 'performance_direction',
      surfacePath: ['sessions', 'ds_route_001'],
    });
    expect(result).toBe('rendered');
  });

  it('uses an empty surface path for the capability root host', async () => {
    mockRenderCapabilityUiHostPage.mockResolvedValue('rendered-root');

    const result = await CapabilityUiHostPage({
      params: {
        workspaceId: 'ws_demo',
        capabilityCode: 'ig',
      },
    });

    expect(mockRenderCapabilityUiHostPage).toHaveBeenCalledWith({
      workspaceId: 'ws_demo',
      capabilityCode: 'ig',
      surfacePath: [],
    });
    expect(result).toBe('rendered-root');
  });
});
