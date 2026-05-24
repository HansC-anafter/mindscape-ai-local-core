import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadCapabilityUIComponent } from '@/lib/capability-ui-loader';

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
    }: {
      workspaceId: string;
      apiUrl: string;
    }) {
      return ReactModule.createElement(
        'div',
        { 'data-testid': 'loaded-tool-panel' },
        `${workspaceId}:${apiUrl}`,
      );
    }),
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

    expect(loadCapabilityUIComponent).not.toHaveBeenCalled();

    rerender(
      <WorkspaceToolExtensionSlot
        workspaceId="ws_test"
        activeToolKey="ig:runs_panel"
        tools={tools}
      />,
    );

    await waitFor(() => {
      expect(loadCapabilityUIComponent).toHaveBeenCalledWith(
        'ig',
        'IGRunsWorkspaceToolPanel',
        'http://api.test',
      );
      expect(screen.getByTestId('loaded-tool-panel')).toHaveTextContent(
        'ws_test:http://api.test',
      );
    });
  });
});
