import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  loadCapabilityUIComponent,
  resetCapabilityUIComponentLoaderCaches,
} from './capability-ui-loader';

const resolver = {
  keys: new Set(['./legacy/Panel.tsx']),
  load: vi.fn(async () => ({ default: function LegacyPanel() { return null; } })),
};

vi.mock('./capability-ui-loader-resolver', () => ({
  findExistingContextKeyForComponent: vi.fn((importPath: string) => importPath),
  getCapabilityComponentsResolver: vi.fn(async () => resolver),
  resetCapabilityComponentsResolverCache: vi.fn(),
}));

vi.mock('./capability-ui-runtime-assets', () => ({
  loadRuntimeESMComponent: vi.fn(),
}));

describe('capability-ui-loader runtime asset canonical gate', () => {
  beforeEach(() => {
    resetCapabilityUIComponentLoaderCaches();
    resolver.load.mockClear();
    vi.stubGlobal('fetch', vi.fn());
  });

  it('does not fallback to raw context component when runtime metadata lacks asset_url', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => [
        {
          code: 'Panel',
          path: 'legacy/Panel.tsx',
          description: 'Runtime component',
          export: 'default',
          artifact_types: [],
          playbook_codes: [],
          import_path: './legacy/Panel.tsx',
          runtime: 'esm',
        },
      ],
    } as Response);

    const Component = await loadCapabilityUIComponent('demo', 'Panel', 'http://localhost:8200');

    expect(Component).toBeNull();
    expect(resolver.load).not.toHaveBeenCalled();
  });

  it('allows explicit legacy_context metadata to use the raw context component path', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => [
        {
          code: 'Panel',
          path: 'legacy/Panel.tsx',
          description: 'Legacy component',
          export: 'default',
          artifact_types: [],
          playbook_codes: [],
          import_path: './legacy/Panel.tsx',
          runtime: 'legacy_context',
        },
      ],
    } as Response);

    const Component = await loadCapabilityUIComponent('demo', 'Panel', 'http://localhost:8200');

    expect(Component).toBeTruthy();
    expect(resolver.load).toHaveBeenCalledWith('./legacy/Panel.tsx');
  });
});
