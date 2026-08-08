import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearCapabilityUiMetadataCacheForTests,
  getCapabilityUiMetadata,
  readCapabilityUiMetadataCache,
} from './capability-ui-metadata-loader';

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}

describe('capability-ui-metadata-loader', () => {
  afterEach(() => {
    clearCapabilityUiMetadataCacheForTests();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('singleflights capability and component metadata for all Host entry seams', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/ui-components?workspace_id=ws_demo')) {
        return jsonResponse([{
          code: 'IGRunsWorkspaceToolPanel',
          path: 'ui/IGRunsWorkspaceToolPanel.tsx',
          description: 'Runs',
          export: 'default',
          artifact_types: [],
          playbook_codes: [],
          import_path: '@/ig/IGRunsWorkspaceToolPanel',
        }]);
      }
      return jsonResponse({
        code: 'ig',
        version: '1.0.203',
        ui_localization: {
          contract: 'mindscape-capability-ui-localization-v1',
          default_locale: 'en',
          supported_locales: ['en', 'zh-TW', 'ja'],
          catalogs: {},
        },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const [first, second] = await Promise.all([
      getCapabilityUiMetadata('http://api.test', 'ig', 'ws_demo'),
      getCapabilityUiMetadata('http://api.test', 'ig', 'ws_demo'),
    ]);

    expect(first).toBe(second);
    expect(first.capabilityInfo.version).toBe('1.0.203');
    expect(first.uiComponents.map((component) => component.code)).toEqual([
      'IGRunsWorkspaceToolPanel',
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/capability-packs/installed-capabilities/ig?workspace_id=ws_demo',
      expect.objectContaining({ cache: 'no-store', credentials: 'same-origin' }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/capability-packs/installed-capabilities/ig/ui-components?workspace_id=ws_demo',
      expect.objectContaining({ cache: 'no-store', credentials: 'same-origin' }),
    );
    expect(readCapabilityUiMetadataCache('http://api.test', 'ig', 'ws_demo')?.metadata)
      .toBe(first);
  });

  it('fails closed when the installed pack exposes no UI components', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => (
      String(input).includes('/ui-components')
        ? jsonResponse([])
        : jsonResponse({ code: 'ig', version: '1.0.203' })
    )));

    await expect(
      getCapabilityUiMetadata('http://api.test', 'ig', 'ws_demo'),
    ).rejects.toThrow('capability_ui_components_unavailable');
    expect(readCapabilityUiMetadataCache('http://api.test', 'ig', 'ws_demo')).toBeUndefined();
  });
});
