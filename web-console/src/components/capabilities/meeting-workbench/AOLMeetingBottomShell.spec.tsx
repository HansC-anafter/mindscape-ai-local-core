import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AOLMeetingBottomShell from './AOLMeetingBottomShell';
import { attachResponse, summary } from './meetingWorkbenchTestData';
import { installAOLMeetingBottomShellTestHarness } from './meetingWorkbenchTestHarness';

describe('AOLMeetingBottomShell facade', () => {
  installAOLMeetingBottomShellTestHarness();

  it('mounts the bottom shell through the legacy spec entrypoint', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(screen.getByTestId('aol-meeting-bottom-shell')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-header-toolbar')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-runs-workspace-surface')).toBeInTheDocument();
    expect(screen.getByTestId('agent-freeform-canvas')).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' }, { timeout: 5000 })).toBeInTheDocument();
    await waitFor(() => {
      expect(
        vi.mocked(global.fetch).mock.calls.some(([url]) =>
          String(url).includes('/meeting-sessions?limit=20&metadata=summary'),
        ),
      ).toBe(true);
    });
  });

  it('opens Director Graph through the preset selector instead of a top-level mode', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByTestId('meeting-workbench-preset-select'), {
      target: { value: 'director_graph' },
    });
    expect(await screen.findByTestId('director-graph-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('director-graph-palette')).toBeInTheDocument();
  });

  it('cold starts in the RUNS host runtime workspace', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(await screen.findByTestId('meeting-runs-workspace-surface')).toBeInTheDocument();
    expect(screen.getByTestId('agent-freeform-canvas')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-graph-lanes')).not.toBeInTheDocument();
    expect(screen.queryByTestId('meeting-graph-view-work')).toBeNull();
    expect(screen.queryByTestId('meeting-graph-view-director')).toBeNull();
  });
});
