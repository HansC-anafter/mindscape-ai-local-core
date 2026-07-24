// @vitest-environment jsdom

import React from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PACK_SCOPE_TOOL_CLOSE_EVENT } from '@/components/capabilities/workbench/packScopeToolEvents';
import { AOL_MEETING_CLIENT_ACTION_EVENT } from '@/lib/meeting-voice/meetingClientActionEvent';
import {
  launchMotionPracticeMock,
  createPhoneMotionSession,
  motionCoachMocks as mocks,
  resetMotionCoachMocks,
} from './MotionCoachWorkbenchHost.test-support';
import MotionCoachWorkbenchHost from './MotionCoachWorkbenchHost';

describe('MotionCoachWorkbenchHost source sessions', () => {
  beforeEach(() => {
    resetMotionCoachMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('requests closing the motion source tool after a source session connects', async () => {
    const closeEvents: CustomEvent[] = [];
    const handleClose = ((event: Event) => {
      closeEvents.push(event as CustomEvent);
    }) as EventListener;
    window.addEventListener(PACK_SCOPE_TOOL_CLOSE_EVENT, handleClose);
    mocks.sessions = [];

    const renderHost = () => React.createElement(MotionCoachWorkbenchHost, {
      workspaceId: 'ws-motion',
      apiUrl: 'http://api.test',
      capabilityCode: 'yogacoach',
      Component: () => React.createElement('div', { 'data-testid': 'runtime-component-close-tool' }, 'Runtime'),
      aolHost: {},
      surfacePath: ['practice'],
    });
    const { rerender } = render(renderHost());

    expect(closeEvents).toHaveLength(0);

    mocks.sessions = [createPhoneMotionSession()];
    rerender(renderHost());

    await waitFor(() => {
      expect(closeEvents).toHaveLength(1);
    });
    expect(closeEvents[0].detail).toMatchObject({
      capabilityCode: 'yogacoach',
      toolId: 'motion_source',
    });

    window.removeEventListener(PACK_SCOPE_TOOL_CLOSE_EVENT, handleClose);
  });

  it('starts the receiver before reference playback after AOL voice confirmation', async () => {
    vi.useFakeTimers();
    const runtimeSnapshots: any[] = [];
    function RuntimeComponent(props: any) {
      runtimeSnapshots.push(props);
      return React.createElement('div', null, props.referencePlaybackPlan?.status || 'idle');
    }
    render(React.createElement(MotionCoachWorkbenchHost, {
      workspaceId: 'ws-motion',
      apiUrl: 'http://api.test',
      capabilityCode: 'yogacoach',
      Component: RuntimeComponent,
      aolHost: {},
      surfacePath: ['practice'],
    }));

    await act(async () => {
      window.dispatchEvent(new CustomEvent(AOL_MEETING_CLIENT_ACTION_EVENT, {
        detail: {
          schemaVersion: 'aol.client_action.v1',
          actionId: 'cmd_prepare',
          workspaceId: 'ws-motion',
          meetingId: 'mtg-voice',
          packCode: 'yogacoach',
          intentCode: 'prepare_default_reference_practice',
          actionCode: 'yogacoach.prepare_reference_practice',
          requiresConfirmation: true,
          payload: {
            reference: {
              owner_pack: 'social_video_refs',
              object_kind: 'instruction_ref',
              provider: 'bilibili',
              provider_video_id: 'BV13g4y1u7di',
              source_kind: 'bilibili_instruction_ref',
              source_url: 'https://www.bilibili.com/video/BV13g4y1u7di/',
              title: 'Bilibili 30-minute yoga practice',
            },
            playback: { start_ms: 0, duration_ms: 1_800_000, loop: false },
          },
        },
      }));
    });
    expect(runtimeSnapshots.at(-1)?.referencePlaybackPlan?.status).toBe('awaiting_confirmation');

    await act(async () => {
      window.dispatchEvent(new CustomEvent(AOL_MEETING_CLIENT_ACTION_EVENT, {
        detail: {
          schemaVersion: 'aol.client_action.v1',
          actionId: 'cmd_confirm',
          workspaceId: 'ws-motion',
          meetingId: 'mtg-voice',
          packCode: 'yogacoach',
          intentCode: 'confirm_reference_practice',
          actionCode: 'yogacoach.confirm_reference_practice',
          requiresConfirmation: false,
          payload: { countdown_seconds: 1 },
        },
      }));
    });
    expect(runtimeSnapshots.at(-1)?.referencePlaybackPlan).toMatchObject({
      status: 'countdown',
      countdownRemaining: 1,
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(launchMotionPracticeMock).toHaveBeenCalledTimes(1);
    expect(launchMotionPracticeMock).toHaveBeenCalledWith(expect.objectContaining({
      workspaceId: 'ws-motion',
      meetingSessionId: 'mtg-voice',
      coachPack: 'yogacoach',
      practiceMode: 'live_guidance',
      expertLibraryRef: 'https://www.bilibili.com/video/BV13g4y1u7di/',
      expectedDurationMs: 1_800_000,
      sourceSession: expect.objectContaining({ session_id: 'session-phone' }),
    }));
    expect(runtimeSnapshots.at(-1)?.referencePlaybackPlan?.status).toBe('playing');
  });

  it('does not relaunch one confirmed practice when durable actions replay after remount', async () => {
    vi.useFakeTimers();
    const renderHost = () => React.createElement(MotionCoachWorkbenchHost, {
      workspaceId: 'ws-motion',
      apiUrl: 'http://api.test',
      capabilityCode: 'yogacoach',
      Component: (props: any) => React.createElement(
        'div',
        null,
        props.referencePlaybackPlan?.status || 'idle',
      ),
      aolHost: {},
      surfacePath: ['practice'],
    });
    const dispatchPlaybackActions = async () => {
      await act(async () => {
        window.dispatchEvent(new CustomEvent(AOL_MEETING_CLIENT_ACTION_EVENT, {
          detail: {
            schemaVersion: 'aol.client_action.v1',
            actionId: 'cmd_prepare_remount',
            workspaceId: 'ws-motion',
            meetingId: 'mtg-remount',
            packCode: 'yogacoach',
            intentCode: 'prepare_default_reference_practice',
            actionCode: 'yogacoach.prepare_reference_practice',
            requiresConfirmation: true,
            payload: {
              reference: {
                owner_pack: 'social_video_refs',
                object_kind: 'instruction_ref',
                provider: 'bilibili',
                provider_video_id: 'BV13g4y1u7di',
                source_kind: 'bilibili_instruction_ref',
                source_url: 'https://www.bilibili.com/video/BV13g4y1u7di/',
                title: 'Bilibili 30-minute yoga practice',
              },
              playback: { start_ms: 0, duration_ms: 1_800_000, loop: false },
            },
          },
        }));
        window.dispatchEvent(new CustomEvent(AOL_MEETING_CLIENT_ACTION_EVENT, {
          detail: {
            schemaVersion: 'aol.client_action.v1',
            actionId: 'cmd_confirm_remount',
            workspaceId: 'ws-motion',
            meetingId: 'mtg-remount',
            packCode: 'yogacoach',
            intentCode: 'confirm_reference_practice',
            actionCode: 'yogacoach.confirm_reference_practice',
            requiresConfirmation: false,
            payload: { countdown_seconds: 1 },
          },
        }));
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_000);
        await Promise.resolve();
        await Promise.resolve();
      });
    };

    const first = render(renderHost());
    await dispatchPlaybackActions();
    expect(launchMotionPracticeMock).toHaveBeenCalledTimes(1);

    first.unmount();
    render(renderHost());
    await dispatchPlaybackActions();

    expect(launchMotionPracticeMock).toHaveBeenCalledTimes(1);
  });

  it('reattaches ledger playback without relaunching an active media receiver', async () => {
    vi.useFakeTimers();
    mocks.sessions = [{
      ...createPhoneMotionSession(),
      media_session_id: 'lms_active',
      media_session_state: 'analyzing',
      media_receiver_metrics: { last_window_end_ms: 12_000 },
      media_analysis_handoff: {
        live_motion_session_id: 'motion_active',
        meeting_session_id: 'mtg-active',
        practice_session_id: 'practice-active',
        coach_pack: 'yogacoach',
        practice_mode: 'live_guidance',
      },
    }];
    const runtimeSnapshots: any[] = [];
    function RuntimeComponent(props: any) {
      runtimeSnapshots.push(props);
      return React.createElement('div', null, props.referencePlaybackPlan?.status || 'idle');
    }
    render(React.createElement(MotionCoachWorkbenchHost, {
      workspaceId: 'ws-motion',
      apiUrl: 'http://api.test',
      capabilityCode: 'yogacoach',
      Component: RuntimeComponent,
      aolHost: {},
      surfacePath: ['practice'],
    }));

    await act(async () => {
      window.dispatchEvent(new CustomEvent(AOL_MEETING_CLIENT_ACTION_EVENT, {
        detail: {
          schemaVersion: 'aol.client_action.v1',
          actionId: 'cmd_prepare_active',
          workspaceId: 'ws-motion',
          meetingId: 'mtg-active',
          packCode: 'yogacoach',
          intentCode: 'prepare_default_reference_practice',
          actionCode: 'yogacoach.prepare_reference_practice',
          requiresConfirmation: true,
          payload: {
            reference: {
              owner_pack: 'social_video_refs',
              object_kind: 'instruction_ref',
              provider: 'bilibili',
              provider_video_id: 'BV13g4y1u7di',
              source_kind: 'bilibili_instruction_ref',
              source_url: 'https://www.bilibili.com/video/BV13g4y1u7di/',
              title: 'Bilibili 30-minute yoga practice',
            },
            playback: { start_ms: 0, duration_ms: 1_800_000, loop: false },
          },
        },
      }));
      window.dispatchEvent(new CustomEvent(AOL_MEETING_CLIENT_ACTION_EVENT, {
        detail: {
          schemaVersion: 'aol.client_action.v1',
          actionId: 'cmd_confirm_active',
          workspaceId: 'ws-motion',
          meetingId: 'mtg-active',
          packCode: 'yogacoach',
          intentCode: 'confirm_reference_practice',
          actionCode: 'yogacoach.confirm_reference_practice',
          requiresConfirmation: false,
          payload: { countdown_seconds: 1 },
        },
      }));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(launchMotionPracticeMock).not.toHaveBeenCalled();
    expect(runtimeSnapshots.at(-1)?.referencePlaybackPlan).toMatchObject({
      status: 'playing',
      playback: { startMs: 12_000 },
    });
    expect(runtimeSnapshots.at(-1)?.workbenchState?.live_motion_session_ref?.id).toBe(
      'motion_active',
    );
  });

  it('maps Dance closure output into ready rollup and report-rendering state', async () => {
    const runtimeSnapshots: any[] = [];
    mocks.referenceLessonState = {
      lesson_id: 'lesson-dance-live',
      title: 'Groove Phrase',
      chapter_ref: 'phrase_intro',
      focus_cue: 'Prepare the accent one count earlier.',
      timestamp_ms: 15000,
    };

    function RuntimeComponent(props: any) {
      runtimeSnapshots.push(props);
      return React.createElement('pre', { 'data-testid': 'runtime-workbench-state-dance' }, JSON.stringify(props.workbenchState));
    }

    render(React.createElement(MotionCoachWorkbenchHost, {
      workspaceId: 'ws-motion',
      apiUrl: 'http://api.test',
      capabilityCode: 'dance_motion_coach',
      Component: RuntimeComponent,
      aolHost: {},
      surfacePath: ['practice'],
    }));

    const firstProps = runtimeSnapshots[0];
    await act(async () => {
      firstProps.motionCoachControls.onSelectedSessionChange('session-phone');
      firstProps.motionCoachControls.onLaunchInputChange({
        apiUrl: 'http://api.test',
        workspaceId: 'ws-motion',
        sourceSession: mocks.sessions[0],
        coachPack: 'dance_motion_coach',
        practiceMode: 'live_guidance',
        expertLibraryRef: 'mindscape://teacher/reference/dance-groove',
        instructionRefs: [],
      });
      firstProps.motionCoachControls.onResultChange({
        meetingId: 'meeting-1',
        commandId: 'command-1',
        liveSessionId: 'live-session-1',
        sourceSessionId: 'session-phone',
        practiceSessionId: 'practice-1',
        liveGuidanceEnabled: true,
        coachPack: 'dance_motion_coach',
        practiceMode: 'live_guidance',
        status: 'started',
      });
      firstProps.motionCoachControls.onClosureResultChange({
        rollup: {
          emitted: true,
          live_session_id: 'live-session-1',
          motion_rollup_ref: 'motion-rollup-1',
          summary: {
            window_count: 1,
            top_findings: ['Arm accent lagging behind reference phrase.'],
            motion_window_digests: [
              {
                motion_window_ref: 'dance-window-1',
                phrase_id: 'phrase_intro',
                phase: 'groove',
                start_ms: 12000,
                end_ms: 18000,
                confidence: 0.87,
                dwpose_node_deltas: [
                  {
                    node_id: 'right_arm_accent',
                    node_label: 'Right arm accent',
                    delta_score: 0.24,
                    confidence: 0.88,
                    finding: 'Right arm accent lands lower than the reference.',
                    guidance: 'Raise the elbow before the downbeat.',
                  },
                ],
                sway_metrics: [],
                phase_metrics: [],
              },
            ],
          },
        },
        command: {
          commandId: 'closure-command-1',
          dispatchResult: {
            playbook: {
              triggered_playbook: {
                execution_id: 'playbook-execution-1',
              },
            },
          },
        },
      });
    });

    await waitFor(() => {
      const latest = runtimeSnapshots[runtimeSnapshots.length - 1]?.workbenchState;
      expect(latest?.connected_capture_source_ref?.id).toBe('session-phone');
      expect(latest?.motion_rollup_ref?.status).toBe('ready');
      expect(latest?.motion_rollup_ref?.motion_window_count).toBe(1);
      expect(latest?.reference_lesson_state?.activePhraseId).toBe('phrase_intro');
      expect(latest?.meeting_feedback_ref?.status).toBe('ready');
      expect(latest?.html_report_artifact_ref?.status).toBe('rendering');
      expect(latest?.html_report_artifact_ref?.id).toBe('playbook-execution-1');
    });
  });

  it('recovers a stale live motion session after backend registry restart', async () => {
    const runtimeSnapshots: any[] = [];

    function RuntimeComponent(props: any) {
      runtimeSnapshots.push(props);
      return React.createElement(
        'div',
        null,
        React.createElement('div', null, props.hostCapturePreview),
        React.createElement('pre', { 'data-testid': 'runtime-workbench-state-recovery' }, JSON.stringify(props.workbenchState)),
      );
    }

    render(React.createElement(MotionCoachWorkbenchHost, {
      workspaceId: 'ws-motion',
      apiUrl: 'http://api.test',
      capabilityCode: 'yogacoach',
      Component: RuntimeComponent,
      aolHost: {},
      surfacePath: ['practice'],
    }));

    const firstProps = runtimeSnapshots[0];
    await act(async () => {
      firstProps.motionCoachControls.onSelectedSessionChange('session-phone');
      firstProps.motionCoachControls.onLaunchInputChange({
        apiUrl: 'http://api.test',
        workspaceId: 'ws-motion',
        sourceSession: mocks.sessions[0],
        coachPack: 'yogacoach',
        practiceMode: 'live_guidance',
        expertLibraryRef: 'mindscape://teacher/reference/yoga-foundation',
        instructionRefs: [],
      });
      firstProps.motionCoachControls.onResultChange({
        meetingId: 'meeting-old',
        commandId: null,
        playbookExecutionId: null,
        liveSessionId: 'live-session-old',
        sourceSessionId: 'session-phone',
        practiceSessionId: 'practice-old',
        liveGuidanceEnabled: true,
        coachPack: 'yogacoach',
        practiceMode: 'live_guidance',
        status: 'active',
      });
    });

    await waitFor(() => {
      expect(mocks.phoneSourcePreviewProps?.liveMotionSessionId).toBe('live-session-old');
    });

    await act(async () => {
      await mocks.phoneSourcePreviewProps.onLiveMotionSessionLost('live-session-old');
    });

    await waitFor(() => {
      expect(launchMotionPracticeMock).toHaveBeenCalledWith(expect.objectContaining({
        workspaceId: 'ws-motion',
        sourceSession: expect.objectContaining({ session_id: 'session-phone' }),
        coachPack: 'yogacoach',
        practiceMode: 'live_guidance',
      }));
      const latest = runtimeSnapshots[runtimeSnapshots.length - 1]?.workbenchState;
      expect(latest?.live_motion_session_ref?.id).toBe('live-session-recovered');
      expect(mocks.phoneSourcePreviewProps?.liveMotionSessionId).toBe('live-session-recovered');
    });
  });
});
