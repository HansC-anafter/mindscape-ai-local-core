// @vitest-environment jsdom

import React from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PACK_SCOPE_TOOL_CLOSE_EVENT } from '@/components/capabilities/workbench/packScopeToolEvents';
import {
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
});
