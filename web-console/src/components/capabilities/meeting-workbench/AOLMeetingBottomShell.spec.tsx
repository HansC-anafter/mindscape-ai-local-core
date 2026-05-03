import React from 'react';
import { render, screen } from '@testing-library/react';
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
    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
  });
});
