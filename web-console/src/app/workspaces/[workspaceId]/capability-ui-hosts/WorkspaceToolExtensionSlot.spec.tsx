import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadLocalizedCapabilityUiComponent } from '@/lib/localized-capability-ui-component-loader';

import WorkspaceToolExtensionSlot from './WorkspaceToolExtensionSlot';

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/i18n', () => ({
  useLocaleContext: () => ({ locale: 'zh-TW' }),
}));

vi.mock('@/lib/localized-capability-ui-component-loader', async () => {
  const ReactModule = await import('react');
  return {
    loadLocalizedCapabilityUiComponent: vi.fn(async () => ({
      localization: {
        contract: 'mindscape-capability-ui-localization-bridge-v1',
        requestedLocale: 'zh-TW',
        effectiveLocale: 'zh-TW',
        direction: 'ltr',
        sourceLocale: 'en',
        status: 'localized',
        t: (key: string) => key,
      },
      Component: function LoadedToolPanel({
        workspaceId,
        apiUrl,
        localization,
      }: {
        workspaceId: string;
        apiUrl: string;
        localization?: { requestedLocale?: string };
      }) {
        return ReactModule.createElement(
          'div',
          {
            'data-testid': 'loaded-tool-panel',
            'data-localization-locale': localization?.requestedLocale || '',
          },
          `${workspaceId}:${apiUrl}`,
        );
      },
    })),
  };
});

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
      <WorkspaceToolExtensionSlot
        workspaceId="ws_test"
        activeToolKey={null}
        tools={tools}
      />,
    );

    expect(loadLocalizedCapabilityUiComponent).not.toHaveBeenCalled();

    rerender(
      <WorkspaceToolExtensionSlot
        workspaceId="ws_test"
        activeToolKey="ig:runs_panel"
        tools={tools}
      />,
    );

    await waitFor(() => {
      expect(loadLocalizedCapabilityUiComponent).toHaveBeenCalledWith({
        apiUrl: 'http://api.test',
        capabilityCode: 'ig',
        componentCode: 'IGRunsWorkspaceToolPanel',
        requestedLocale: 'zh-TW',
        workspaceId: 'ws_test',
      });
      expect(screen.getByTestId('loaded-tool-panel')).toHaveTextContent(
        'ws_test:http://api.test',
      );
      expect(screen.getByTestId('loaded-tool-panel')).toHaveAttribute(
        'data-localization-locale',
        'zh-TW',
      );
    });
  });
});
