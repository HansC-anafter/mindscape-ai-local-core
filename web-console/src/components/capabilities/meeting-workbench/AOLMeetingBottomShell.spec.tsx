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
    expect(screen.getByTestId('meeting-task-canvas')).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' }, { timeout: 5000 })).toBeInTheDocument();
    await waitFor(() => {
      expect(
        vi.mocked(global.fetch).mock.calls.some(([url]) =>
          String(url).includes('/meeting-sessions?limit=20&metadata=summary'),
        ),
      ).toBe(true);
    });
  });

  it('switches from Work mode into Director Graph mode', async () => {
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

    fireEvent.click(screen.getByTestId('meeting-graph-view-director'));
    expect(await screen.findByTestId('director-graph-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('director-graph-palette')).toBeInTheDocument();
  });

  it('switches from Work mode into the RUNS host runtime workspace', async () => {
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

    fireEvent.click(screen.getByTestId('meeting-graph-view-runs'));

    expect(await screen.findByTestId('meeting-runs-workspace-surface')).toBeInTheDocument();
    expect(screen.getByTestId('agent-freeform-canvas')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-graph-lanes')).not.toBeInTheDocument();
  });
});
