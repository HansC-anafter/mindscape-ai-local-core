import { describe, expect, it, vi } from 'vitest';

import { loadCapabilityUiLocalization } from './capability-ui-localization';
import {
  loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata,
} from './capability-ui-loader';
import { getCapabilityUiMetadata } from './capability-ui-metadata-loader';
import { loadLocalizedCapabilityUiComponent } from './localized-capability-ui-component-loader';

vi.mock('./capability-ui-localization', () => ({
  loadCapabilityUiLocalization: vi.fn(),
}));

vi.mock('./capability-ui-loader', () => ({
  loadCapabilityUIComponent: vi.fn(),
  primeCapabilityUIComponentMetadata: vi.fn(),
}));

vi.mock('./capability-ui-metadata-loader', () => ({
  getCapabilityUiMetadata: vi.fn(),
}));

describe('localized-capability-ui-component-loader', () => {
  it('loads one component and its catalog bridge through the same metadata facade', async () => {
    const Component = () => null;
    const localization = {
      contract: 'mindscape-capability-ui-localization-bridge-v1',
      requestedLocale: 'zh-TW',
      effectiveLocale: 'zh-TW',
      direction: 'ltr',
      sourceLocale: 'en',
      status: 'localized',
      t: (key: string) => key,
    };
    const uiComponents = [{
      code: 'IGRunsWorkspaceToolPanel',
      path: 'ui/IGRunsWorkspaceToolPanel.tsx',
      description: 'Runs',
      export: 'default',
      artifact_types: [],
      playbook_codes: [],
      import_path: '@/ig/IGRunsWorkspaceToolPanel',
    }];
    const descriptor = {
      contract: 'mindscape-capability-ui-localization-v1',
      default_locale: 'en',
      supported_locales: ['en', 'zh-TW', 'ja'],
      catalogs: {},
    };
    vi.mocked(getCapabilityUiMetadata).mockResolvedValue({
      capabilityInfo: {
        code: 'ig',
        version: '1.0.203',
        ui_localization: descriptor as any,
      },
      uiComponents,
    });
    vi.mocked(loadCapabilityUIComponent).mockResolvedValue(Component);
    vi.mocked(loadCapabilityUiLocalization).mockResolvedValue(localization as any);

    const result = await loadLocalizedCapabilityUiComponent({
      apiUrl: 'http://api.test',
      capabilityCode: 'ig',
      componentCode: 'IGRunsWorkspaceToolPanel',
      requestedLocale: 'zh-TW',
      workspaceId: 'ws_demo',
    });

    expect(primeCapabilityUIComponentMetadata).toHaveBeenCalledWith('ig', uiComponents);
    expect(loadCapabilityUIComponent).toHaveBeenCalledWith(
      'ig',
      'IGRunsWorkspaceToolPanel',
      'http://api.test',
      'ws_demo',
    );
    expect(loadCapabilityUiLocalization).toHaveBeenCalledWith({
      apiUrl: 'http://api.test',
      capabilityCode: 'ig',
      version: '1.0.203',
      requestedLocale: 'zh-TW',
      descriptor,
    });
    expect(result).toEqual({ Component, localization });
  });
});
