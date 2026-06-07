import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildLedgerIntentText, submitMeetingCommandEnvelope } from './meetingCommandLedger';
import type { MeetingObjectActionEntry } from './meetingWorkbenchTypes';

const entries: MeetingObjectActionEntry[] = [
  {
    role: 'source',
    ref: {
      uri: 'mindscape://ig/reference/ref_global',
      owner_pack: 'ig',
      object_kind: 'reference',
      object_id: 'ref_global',
    },
  },
];

describe('meetingCommandLedger', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('strips legacy UI mention tokens before sending server grammar text', () => {
    expect(
      buildLedgerIntentText(
        'Send asset @pack:visual_audit @storyboard:manual @character:manual_card',
        entries,
      ),
    ).toBe('Send asset');
  });

  it('falls back to role-bearing object refs when command text is only mentions', () => {
    expect(buildLedgerIntentText('@pack:visual_audit @storyboard:manual', entries)).toBe(
      'mindscape://ig/reference/ref_global',
    );
  });

  it('routes AOL object context through MeetingEngine orchestration by default', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      command_id: 'cmd_1',
      status: 'completed',
      dispatch_result: {
        meeting_orchestration: {
          status: 'completed',
          task_ir_id: 'task_meeting',
        },
      },
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const acceptance = await submitMeetingCommandEnvelope({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_demo',
      meetingId: 'mtg_demo',
      command: 'Analyze this reference',
      originSurface: 'meeting_workbench',
      threadId: 'thread_demo',
      mentionRefs: [],
      objectActionEntries: entries,
      selectedPackTool: null,
    });

    expect(acceptance.dispatchResult?.meeting_orchestration).toEqual({
      status: 'completed',
      task_ir_id: 'task_meeting',
    });
    const firstRequestInit = (fetchMock.mock.calls[0] as unknown as [string, RequestInit] | undefined)?.[1];
    const requestBody = JSON.parse(String(firstRequestInit?.body || '{}'));
    expect(requestBody.metadata.dispatch_mode).toBe('route_meeting_orchestration');
  });

  it('carries selected guidance metadata into the orchestration command envelope', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      command_id: 'cmd_2',
      status: 'completed',
      dispatch_result: {
        meeting_orchestration: {
          status: 'completed',
          task_ir_id: 'task_meeting',
        },
      },
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await submitMeetingCommandEnvelope({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_demo',
      meetingId: 'mtg_demo',
      command: 'Run selected guidance',
      originSurface: 'meeting_workbench',
      threadId: 'thread_demo',
      mentionRefs: [],
      objectActionEntries: [],
      selectedPackTool: {
        id: 'visual_audit',
        label: 'Visual Audit',
        description: 'Audit visuals',
        capabilityCode: 'ig',
        requiredTools: [],
      },
      actionParameters: {
        selected_guidance_id: 'guidance_1',
        selected_guidance_metadata: {
          recommended_pack: 'ig',
          recommended_playbook: 'visual_audit',
        },
      },
    });

    const firstRequestInit = (fetchMock.mock.calls[0] as unknown as [string, RequestInit] | undefined)?.[1];
    const requestBody = JSON.parse(String(firstRequestInit?.body || '{}'));
    expect(requestBody.metadata.dispatch_mode).toBe('route_meeting_orchestration');
    expect(requestBody.metadata.selected_guidance_id).toBe('guidance_1');
    expect(requestBody.metadata.selected_guidance_metadata).toEqual({
      recommended_pack: 'ig',
      recommended_playbook: 'visual_audit',
    });
    expect(requestBody.requested_action.playbook_code).toBe('visual_audit');
  });

  it('routes blank-session instructions through MeetingEngine when forced', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      command_id: 'cmd_blank',
      status: 'accepted',
      dispatch_result: {
        meeting_orchestration: {
          status: 'completed',
          task_ir_id: 'task_blank',
        },
      },
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await submitMeetingCommandEnvelope({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_demo',
      meetingId: 'mtg_blank',
      command: 'Group current yoga references into creative spaces',
      originSurface: 'meeting_workbench',
      threadId: 'mtg_blank',
      mentionRefs: [],
      objectActionEntries: [],
      selectedPackTool: null,
      actionParameters: {
        active_capability_code: 'ig',
        force_meeting_orchestration: true,
      },
    });

    const firstRequestInit = (fetchMock.mock.calls[0] as unknown as [string, RequestInit] | undefined)?.[1];
    const requestBody = JSON.parse(String(firstRequestInit?.body || '{}'));
    expect(requestBody.metadata.dispatch_mode).toBe('route_meeting_orchestration');
    expect(requestBody.metadata.force_meeting_orchestration).toBe(true);
    expect(requestBody.metadata.action_parameters.active_capability_code).toBe('ig');
  });

  it('preserves explicit route_playbook dispatch for direct playbook commands', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      command_id: 'cmd_playbook',
      status: 'accepted',
      dispatch_result: {
        playbook_execution: {
          status: 'accepted',
        },
      },
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await submitMeetingCommandEnvelope({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_demo',
      meetingId: 'mtg_playbook',
      command: 'Summarize closed motion practice',
      originSurface: 'workspace_motion_source_practice_closure',
      threadId: 'mtg_playbook',
      mentionRefs: [],
      objectActionEntries: [],
      selectedPackTool: null,
      actionParameters: {
        live_practice_rollup: {
          window_count: 3,
        },
      },
      requestedAction: {
        verb: 'execute_playbook',
        pack_code: 'yogacoach',
        playbook_code: 'yogacoach_student_practice_summary',
        write_mode: 'recommendation_only',
        parameters: {},
      },
      metadata: {
        dispatch_mode: 'route_playbook',
        explicit_override: true,
        motion_practice_command: true,
        motion_practice_close: true,
      },
    });

    const firstRequestInit = (fetchMock.mock.calls[0] as unknown as [string, RequestInit] | undefined)?.[1];
    const requestBody = JSON.parse(String(firstRequestInit?.body || '{}'));
    expect(requestBody.metadata.dispatch_mode).toBe('route_playbook');
    expect(requestBody.metadata.explicit_override).toBe(true);
    expect(requestBody.metadata.force_meeting_orchestration).toBe(false);
  });
});
