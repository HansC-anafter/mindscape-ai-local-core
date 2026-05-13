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

  it('fetches declared pack tools and loads only the active panel component', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => [
        {
          id: 'runs_panel',
          group: 'capability',
          label: 'Runs',
          icon: 'Activity',
          order: 10,
          panel_component_code: 'IGRunsWorkspaceToolPanel',
          panel_component: {
            code: 'IGRunsWorkspaceToolPanel',
            path: 'ui/IGRunsWorkspaceToolPanel.tsx',
          },
        },
      ],
    } as Response);
    const handleActiveToolChange = vi.fn();
    const handleToolsChange = vi.fn();

    const { rerender } = render(
      <WorkspaceToolExtensionSlot
        workspaceId="ws_test"
        capabilityCode="ig"
        activeToolKey={null}
        onActiveToolChange={handleActiveToolChange}
        onToolsChange={handleToolsChange}
      />,
    );

    await waitFor(() => {
      expect(handleToolsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          tool_key: 'ig:runs_panel',
          panel_component_code: 'IGRunsWorkspaceToolPanel',
        }),
      ]);
    });
    expect(loadCapabilityUIComponent).not.toHaveBeenCalled();

    rerender(
      <WorkspaceToolExtensionSlot
        workspaceId="ws_test"
        capabilityCode="ig"
        activeToolKey="ig:runs_panel"
        onActiveToolChange={handleActiveToolChange}
        onToolsChange={handleToolsChange}
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
