import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AOLMeetingBottomShell from './AOLMeetingBottomShell';
import { MEETING_COMMAND_LEDGER_UPDATED_EVENT } from './meetingCommandEvents';
import { attachResponse, summary } from './meetingWorkbenchTestData';
import { installAOLMeetingBottomShellTestHarness } from './meetingWorkbenchTestHarness';

describe('AOLMeetingBottomShell dispatch and session switching', () => {
  installAOLMeetingBottomShellTestHarness();

  it('does not synthesize pack-owned object refs from unresolved raw mention tokens', async () => {
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

    await screen.findByTestId('meeting-pack-tool-select');

    fireEvent.change(screen.getByLabelText('Meeting instruction'), {
      target: {
        value:
          'Send asset @pack:visual_audit @storyboard:pd_manual @storyboard_scene:pd_manual:artifact_manual:sc09 @storyboard_proposal:pd_manual:proposal_01 @character:manual_pkg @character_card:manual_card',
      },
    });
    fireEvent.click(screen.getByTestId('meeting-command-submit'));

    await screen.findByText('Task ID: task-meeting · Artifacts: pending');
    const commandCall = vi.mocked(global.fetch).mock.calls.find(([url]) =>
      String(url).includes('/meetings/mtg_global/commands'),
    );
    expect(commandCall).toBeDefined();
    const commandBody = JSON.parse(String(commandCall?.[1]?.body || '{}'));
    expect(commandBody.metadata.dispatch_mode).toBe('route_meeting_orchestration');
    expect(commandBody.requested_action.parameters.object_action_entries).toEqual([
      expect.objectContaining({
        role: 'source',
        ref: expect.objectContaining({
          uri: 'mindscape://ig/reference/ref_global',
          object_kind: 'reference',
        }),
      }),
    ]);
    expect(commandBody.requested_action.parameters.target_storyboards).toEqual([]);
    expect(commandBody.requested_action.parameters.target_storyboard_scenes).toEqual([]);
    expect(commandBody.requested_action.parameters.character_refs).toEqual([]);
    expect(JSON.stringify(commandBody.requested_action.parameters.object_action_entries)).not.toContain(
      'performance_direction',
    );
    expect(JSON.stringify(commandBody.requested_action.parameters.object_action_entries)).not.toContain(
      'character_training',
    );
    expect(
      vi.mocked(global.fetch).mock.calls.some(([url]) => String(url).includes('/chat')),
    ).toBe(false);
    expect(
      vi.mocked(global.fetch).mock.calls.some(([url]) => String(url).includes('/object-actions/plan')),
    ).toBe(false);
    expect(
      vi.mocked(global.fetch).mock.calls.some(([url]) => String(url).includes('/object-actions/invoke')),
    ).toBe(false);
  });

  it('switches the graph canvas to another meeting session from the session strip', async () => {
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

    fireEvent.click(screen.getByTestId('meeting-sessions-toggle'));
    fireEvent.click(await screen.findByTestId('meeting-session-card-mtg_other'));

    await waitFor(() => {
      expect(screen.queryByTestId('meeting-sessions-popover')).toBeNull();
      expect(screen.getByTestId('meeting-graph-node-root')).toHaveTextContent('mtg_other');
    });
  });

  it('refreshes the active graph from command-ledger update events', async () => {
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

    expect(await screen.findByTestId('meeting-graph-node-command-oap-global')).toBeInTheDocument();
    const initialGraphFetchCount = vi.mocked(global.fetch).mock.calls.filter(([url]) =>
      String(url).includes('/meetings/mtg_global/execution-graph?limit=200'),
    ).length;

    fireEvent(
      window,
      new CustomEvent(MEETING_COMMAND_LEDGER_UPDATED_EVENT, {
        detail: {
          workspaceId: 'ws-global',
          meetingId: 'mtg_global',
          commandId: 'cmd-ledger-global',
          status: 'accepted',
        },
      }),
    );

    await waitFor(() => {
      const graphFetchCount = vi.mocked(global.fetch).mock.calls.filter(([url]) =>
        String(url).includes('/meetings/mtg_global/execution-graph?limit=200'),
      ).length;
      expect(graphFetchCount).toBeGreaterThan(initialGraphFetchCount);
    });
  });

  it('adds a command as a task node, dispatches it, and opens the scoped console', async () => {
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

    expect(await screen.findByTestId('meeting-graph-node-command-oap-global')).toHaveTextContent(
      'Produce generic asset',
    );
    const initialGraphFetchCount = vi.mocked(global.fetch).mock.calls.filter(([url]) =>
      String(url).includes('/meetings/mtg_global/execution-graph?limit=200'),
    ).length;
    const commandLedgerEvents: unknown[] = [];
    const handleCommandLedgerEvent = (event: Event) => {
      commandLedgerEvents.push(event instanceof CustomEvent ? event.detail : null);
    };
    window.addEventListener(MEETING_COMMAND_LEDGER_UPDATED_EVENT, handleCommandLedgerEvent);

    fireEvent.change(screen.getByLabelText('Meeting instruction'), {
      target: { value: 'Analyze this reference' },
    });
    fireEvent.click(screen.getByTestId('meeting-command-submit'));

    expect(screen.getAllByText('Analyze this reference').length).toBeGreaterThan(0);
    expect(screen.getByTestId('meeting-console-drawer')).toBeInTheDocument();
    expect(await screen.findByText('Task ID: task-meeting · Artifacts: pending')).toBeInTheDocument();
    expect(await screen.findByTestId('meeting-session-notification')).toHaveAttribute('data-tone', 'info');
    window.removeEventListener(MEETING_COMMAND_LEDGER_UPDATED_EVENT, handleCommandLedgerEvent);
    expect(commandLedgerEvents).toContainEqual({
      workspaceId: 'ws-global',
      meetingId: 'mtg_global',
      commandId: 'cmd-ledger-global',
      status: 'completed',
    });
    expect(global.fetch).toHaveBeenCalledWith(
      'http://api.test/api/v1/workspaces/ws-global/meetings/mtg_global/commands',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"raw_intent_text":"Analyze this reference"'),
      }),
    );
    const commandCall = vi.mocked(global.fetch).mock.calls.find(([url]) =>
      String(url).includes('/meetings/mtg_global/commands'),
    );
    const commandBody = JSON.parse(String(commandCall?.[1]?.body || '{}'));
    expect(commandBody.metadata.dispatch_mode).toBe('route_meeting_orchestration');
    expect(commandBody.metadata.action_parameters.command_id).toBeUndefined();
    expect(commandBody.metadata.action_parameters.thread_id).toBe('mtg_global');
    expect(vi.mocked(global.fetch).mock.calls.some(([url]) => String(url).includes('/chat'))).toBe(false);
    await waitFor(() => {
      const graphFetchCount = vi.mocked(global.fetch).mock.calls.filter(([url]) =>
        String(url).includes('/meetings/mtg_global/execution-graph?limit=200'),
      ).length;
      expect(graphFetchCount).toBeGreaterThan(initialGraphFetchCount);
    });
  });

  it('blocks selected guidance dispatch until required object context is mentioned', async () => {
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
    fireEvent.click((await within(guidanceStep).findAllByText('Director framing'))[0]);
    expect(screen.getByLabelText('Meeting instruction')).toHaveValue(
      'Draft a shot plan for @object:ref_global before generating assets.',
    );
    const commandPostCountBefore = vi.mocked(global.fetch).mock.calls.filter(([url, init]) =>
      String(url).includes('/meetings/mtg_global/commands') && init?.method === 'POST',
    ).length;

    fireEvent.click(screen.getByTestId('meeting-command-submit'));

    expect(await screen.findByTestId('meeting-dispatch-error')).toHaveTextContent('@');
    const commandPostCountAfter = vi.mocked(global.fetch).mock.calls.filter(([url, init]) =>
      String(url).includes('/meetings/mtg_global/commands') && init?.method === 'POST',
    ).length;
    expect(commandPostCountAfter).toBe(commandPostCountBefore);
    expect(screen.queryByTestId('meeting-console-drawer')).toBeNull();
  });

  it('treats missing route-owned dispatch evidence as a contract error', async () => {
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

    fireEvent.change(screen.getByLabelText('Meeting instruction'), {
      target: { value: 'No dispatch result fixture' },
    });
    fireEvent.click(screen.getByTestId('meeting-command-submit'));

    expect(
      await screen.findAllByText('Meeting command route did not return a route-owned dispatch result.'),
    ).not.toHaveLength(0);
    expect(await screen.findByTestId('meeting-session-notification')).toHaveAttribute('data-tone', 'error');
    expect(vi.mocked(global.fetch).mock.calls.some(([url]) => String(url).includes('/chat'))).toBe(false);
    expect(
      vi.mocked(global.fetch).mock.calls.some(([url]) => String(url).includes('/object-actions/plan')),
    ).toBe(false);
    expect(
      vi.mocked(global.fetch).mock.calls.some(([url]) => String(url).includes('/object-actions/invoke')),
    ).toBe(false);
  });

  it('dispatches a selected pack tool target through the command route', async () => {
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

    await screen.findByTestId('meeting-pack-tool-select');

    fireEvent.change(screen.getByTestId('meeting-pack-tool-select'), {
      target: { value: 'visual_audit' },
    });
    fireEvent.change(screen.getByLabelText('Meeting instruction'), {
      target: { value: 'Prepare the visual reference set' },
    });
    fireEvent.click(screen.getByTestId('meeting-command-submit'));

    await screen.findByText('Task ID: task-meeting · Artifacts: pending');
    const commandCall = vi.mocked(global.fetch).mock.calls.find(([url]) =>
      String(url).includes('/meetings/mtg_global/commands'),
    );
    expect(commandCall?.[1]).toEqual(
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"playbook_code":"visual_audit"'),
      }),
    );
    const commandBody = JSON.parse(String(commandCall?.[1]?.body || '{}'));
    expect(commandBody.metadata.dispatch_mode).toBe('route_meeting_orchestration');
    expect(commandBody.requested_action.parameters.thread_id).toBe('mtg_global');
    expect(commandBody.requested_action.parameters.instruction).toBe('Prepare the visual reference set');
    const chatCall = vi.mocked(global.fetch).mock.calls.find(([url]) => String(url).includes('/chat'));
    expect(chatCall).toBeUndefined();
  });
});
