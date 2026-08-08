import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadCapabilityUIComponent } from '@/lib/capability-ui-loader';
import type {
  CapabilityUiLocalizationBridgeV1,
} from '@/lib/capability-ui-localization';

import { CapabilityHostLocalizationProvider } from './CapabilityHostLocalizationContext';
import WorkspaceToolExtensionSlot from './WorkspaceToolExtensionSlot';

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/capability-ui-loader', async () => {
  const ReactModule = await import('react');
  return {
    primeCapabilityUIComponentMetadata: vi.fn(),
    loadCapabilityUIComponent: vi.fn(async () => function LoadedToolPanel({
      workspaceId,
      apiUrl,
      localization,
    }: {
      workspaceId: string;
      apiUrl: string;
      localization?: CapabilityUiLocalizationBridgeV1;
    }) {
      return ReactModule.createElement(
        'div',
        {
          'data-testid': 'loaded-tool-panel',
          'data-effective-locale': localization?.effectiveLocale,
        },
        `${workspaceId}:${apiUrl}`,
      );
    }),
  };
});

const bridge: CapabilityUiLocalizationBridgeV1 = {
  contract: 'mindscape-capability-ui-localization-bridge-v1',
  requestedLocale: 'zh-TW',
  effectiveLocale: 'zh-TW',
  direction: 'ltr',
  sourceLocale: 'en',
  status: 'ready',
  t: (key) => `translated:${key}`,
};

describe('WorkspaceToolExtensionSlot', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads only the active panel component from provided pack tools', async () => {
    const tools = [{
      tool_key: 'ig:runs_panel',
      capability_code: 'ig',
      id: 'runs_panel',
      group: 'capability' as const,
      slot: 'workspace.right_rail.tool' as const,
      label: 'Runs',
      icon: 'Activity',
      order: 10,
      panel_component_code: 'IGRunsWorkspaceToolPanel',
      panel_component: {
        code: 'IGRunsWorkspaceToolPanel',
        path: 'ui/IGRunsWorkspaceToolPanel.tsx',
        description: 'Runs panel',
        export: 'default',
        artifact_types: [],
        playbook_codes: [],
        import_path: '@/app/capabilities/ig/components/IGRunsWorkspaceToolPanel',
        layout_hint: 'default' as const,
      },
    }];

    const { rerender } = render(
      <CapabilityHostLocalizationProvider
        capabilityCode="ig"
        localizationPromise={Promise.resolve(bridge)}
      >
        <WorkspaceToolExtensionSlot
          workspaceId="ws_test"
          activeToolKey={null}
          tools={tools}
        />
      </CapabilityHostLocalizationProvider>,
    );

    expect(loadCapabilityUIComponent).not.toHaveBeenCalled();

    rerender(
      <CapabilityHostLocalizationProvider
        capabilityCode="ig"
        localizationPromise={Promise.resolve(bridge)}
      >
        <WorkspaceToolExtensionSlot
          workspaceId="ws_test"
          activeToolKey="ig:runs_panel"
          tools={tools}
        />
      </CapabilityHostLocalizationProvider>,
    );

    await waitFor(() => {
      expect(loadCapabilityUIComponent).toHaveBeenCalledWith(
        'ig',
        'IGRunsWorkspaceToolPanel',
        'http://api.test',
        'ws_test',
      );
      expect(screen.getByTestId('loaded-tool-panel')).toHaveTextContent(
        'ws_test:http://api.test',
      );
      expect(screen.getByTestId('loaded-tool-panel')).toHaveAttribute(
        'data-effective-locale',
        'zh-TW',
      );
    });
  });
});
