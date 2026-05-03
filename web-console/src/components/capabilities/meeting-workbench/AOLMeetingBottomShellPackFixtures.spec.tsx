import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AOLMeetingBottomShell from './AOLMeetingBottomShell';
import {
  attachResponse,
  performanceDirectionAttachResponse,
  performanceDirectionSummary,
  summary,
} from './meetingWorkbenchTestData';
import { installAOLMeetingBottomShellTestHarness } from './meetingWorkbenchTestHarness';

interface CommandPostBody {
  metadata?: {
    dispatch_mode?: string;
  };
  requested_action?: {
    playbook_code?: string;
  };
  context_objects?: unknown[];
}

function readLastCommandPostBody(): CommandPostBody {
  const commandCalls = vi.mocked(global.fetch).mock.calls.filter(([url, init]) =>
    String(url).includes('/meetings/mtg_global/commands') && init?.method === 'POST',
  );
  const latestCall = commandCalls[commandCalls.length - 1];
  return JSON.parse(String(latestCall?.[1]?.body || '{}')) as CommandPostBody;
}

describe('AOLMeetingBottomShell product pack fixtures', () => {
  installAOLMeetingBottomShellTestHarness();

  it('routes IG guidance through the command ledger with PD storyboard context', async () => {
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

    const guidanceStep = await screen.findByTestId('meeting-work-step-guidance');
    fireEvent.click(within(guidanceStep).getAllByText('Director framing')[0]);

    const input = screen.getByLabelText('Meeting instruction');
    expect(input).toHaveValue('Draft a shot plan for @object:ref_global before generating assets.');
    expect(screen.getByTestId('meeting-pack-tool-select')).toHaveValue('visual_audit');

    const commandPostCountBefore = vi.mocked(global.fetch).mock.calls.filter(([url, init]) =>
      String(url).includes('/meetings/mtg_global/commands') && init?.method === 'POST',
    ).length;

    fireEvent.click(screen.getByTestId('meeting-command-submit'));

    expect(await screen.findByTestId('meeting-dispatch-error')).toHaveTextContent('@');
    const commandPostCountAfter = vi.mocked(global.fetch).mock.calls.filter(([url, init]) =>
      String(url).includes('/meetings/mtg_global/commands') && init?.method === 'POST',
    ).length;
    expect(commandPostCountAfter).toBe(commandPostCountBefore);

    fireEvent.change(input, {
      target: {
        value: `${(input as HTMLInputElement).value} @performance_di`,
      },
    });
    fireEvent.mouseDown(
      await screen.findByTestId('meeting-mention-option-registry-performance_direction-storyboard-pd_session_1'),
    );
    expect(input).toHaveValue(
      'Draft a shot plan for @object:ref_global before generating assets. @storyboard:pd_session_1 ',
    );

    fireEvent.click(screen.getByTestId('meeting-command-submit'));

    expect(await screen.findByText('Task ID: exec-playbook')).toBeInTheDocument();
    const commandBody = readLastCommandPostBody();
    expect(commandBody.metadata?.dispatch_mode).toBe('route_playbook');
    expect(commandBody.requested_action?.playbook_code).toBe('visual_audit');
    expect(commandBody.context_objects).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: 'source',
          ref: expect.objectContaining({
            owner_pack: 'ig',
            object_kind: 'reference',
            object_id: 'ref_global',
          }),
        }),
        expect.objectContaining({
          role: 'target',
          ref: expect.objectContaining({
            owner_pack: 'performance_direction',
            object_kind: 'storyboard',
            object_id: 'pd_session_1',
          }),
        }),
      ]),
    );
    expect(
      vi.mocked(global.fetch).mock.calls.some(([url]) =>
        String(url).includes('/api/v1/capabilities/performance_direction/sessions'),
      ),
    ).toBe(false);
    expect(
      vi.mocked(global.fetch).mock.calls.some(([url]) => String(url).includes('/object-actions/invoke')),
    ).toBe(false);
  });

  it('keeps PD storyboard workbench context ahead of session metadata', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={performanceDirectionSummary}
        selection={null}
        attachResponse={performanceDirectionAttachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/performance_direction"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(screen.getByTestId('meeting-work-context-bar')).toHaveTextContent('Yoga storyboard');
    const guidanceStep = await screen.findByTestId('meeting-work-step-guidance');
    expect(within(guidanceStep).getAllByText('Reels generation pass').length).toBeGreaterThan(0);
    expect(screen.queryByText('Director framing')).toBeNull();

    fireEvent.click(within(guidanceStep).getAllByText('Reels generation pass')[0]);

    expect(screen.getByLabelText('Meeting instruction')).toHaveValue(
      'Generate the reels asset pass for @storyboard:pd_session_1.',
    );
    await waitFor(() => {
      expect(screen.getByTestId('meeting-pack-tool-select')).toHaveValue('generate_reels_asset');
    });
    expect(screen.getByTestId('meeting-work-guidance-panel')).toHaveTextContent('guided_by');
    expect(screen.getByTestId('meeting-work-guidance-panel')).toHaveTextContent('performance_direction / generated_reels_asset / pd_session_1:latest');

    const objectGraphProjectCalls = vi.mocked(global.fetch).mock.calls.filter(([url]) =>
      String(url).includes('/object-graph/project'),
    );
    expect(objectGraphProjectCalls.some(([, init]) => String(init?.body).includes('performance_direction/storyboard/pd_session_1'))).toBe(true);
  });
});
