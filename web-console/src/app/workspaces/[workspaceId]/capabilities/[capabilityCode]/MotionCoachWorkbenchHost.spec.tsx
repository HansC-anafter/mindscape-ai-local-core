// @vitest-environment jsdom

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MotionCoachWorkbenchHost from './MotionCoachWorkbenchHost';

const mocks = vi.hoisted(() => ({
  existingBridge: null as Record<string, unknown> | null,
  sessions: [
    {
      session_id: 'session-phone',
      workspace_id: 'ws-motion',
      pairing_code: 'PAIR1234',
      device_id: 'phone_1',
      display_name: 'Phone rear camera',
      source_types: ['phone_camera'],
      state: 'active',
      created_at_epoch: 1,
      updated_at_epoch: 1,
      expires_at_epoch: 999,
    },
    {
      session_id: 'session-obs',
      workspace_id: 'ws-motion',
      pairing_code: 'PAIR9999',
      device_id: 'obs_1',
      display_name: 'OBS Virtual Camera',
      source_types: ['virtual_camera'],
      state: 'paired',
      created_at_epoch: 2,
      updated_at_epoch: 2,
      expires_at_epoch: 999,
    },
  ],
  referenceLessonState: {
    lesson_id: 'lesson-live',
    title: 'Foundation Flow',
    chapter_ref: 'chapter_alignment',
    focus_cue: 'Lift through the collarbones and stabilize center line.',
    timestamp_ms: 18000,
  },
}));

vi.mock('@/components/workspace/device-binding/capture-bridge/CaptureSourceBridgeProvider', () => ({
  CaptureSourceBridgeProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="capture-source-bridge-provider">{children}</div>
  ),
  useCaptureSourceBridge: () => ({
    sessions: mocks.sessions,
    referenceLessonState: mocks.referenceLessonState,
  }),
  useOptionalCaptureSourceBridge: () => mocks.existingBridge,
}));

vi.mock('@/components/workspace/device-binding/capture-bridge/CaptureSourceRail', () => ({
  CaptureSourceRail: ({ showPreview }: { showPreview?: boolean }) => (
    <div data-testid="capture-source-rail">showPreview:{String(showPreview)}</div>
  ),
}));

vi.mock('@/components/workspace/device-binding/practice/MotionPracticeRailController', () => ({
  MotionPracticeRailController: (props: any) => {
    const didPublish = React.useRef(false);

    React.useEffect(() => {
      if (didPublish.current) {
        return;
      }
      didPublish.current = true;

      const sourceSession = mocks.sessions[0];
      if (!sourceSession) {
        return;
      }
      props.onSelectedSessionChange?.(sourceSession.session_id);
      props.onLaunchInputChange?.({
        apiUrl: props.apiUrl,
        workspaceId: props.workspaceId,
        sourceSession,
        coachPack: props.coachPackLock,
        practiceMode: 'live_guidance',
        expertLibraryRef: 'mindscape://teacher/reference/yoga-foundation',
        instructionRefs: [
          {
            video_ref: 'file:///reference/yoga.mp4',
            course_chapters: [
              {
                chapter_id: 'chapter_alignment',
                title: 'Standing alignment',
                start_ms: 10000,
                end_ms: 22000,
              },
              {
                chapter_id: 'chapter_balance',
                title: 'Transition and balance',
                start_ms: 22000,
                end_ms: 36000,
              },
            ],
          },
        ],
      });
      props.onResultChange?.({
        meetingId: 'meeting-1',
        commandId: 'command-1',
        liveSessionId: 'live-session-1',
        sourceSessionId: sourceSession.session_id,
        practiceSessionId: 'practice-1',
        liveGuidanceEnabled: true,
        coachPack: props.coachPackLock,
        practiceMode: 'live_guidance',
        status: 'started',
      });

      if (props.coachPackLock === 'dance_motion_coach') {
        props.onClosureResultChange?.({
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
      }
    }, [props]);

    return <div data-testid="motion-practice-rail-controller">{props.coachPackLock}</div>;
  },
}));

vi.mock('@/components/workspace/device-binding/PhoneSourcePreview', () => ({
  PhoneSourcePreview: (props: any) => {
    const emitted = React.useRef(false);

    React.useEffect(() => {
      if (!props.liveMotionSessionId || emitted.current) {
        return;
      }
      emitted.current = true;
      props.onMotionWindowAppended?.({
        liveSessionId: props.liveMotionSessionId,
        response: {
          motion_window_ref: 'motion-window-1',
        },
        summary: {
          window_id: 'motion-window-1',
          ts_start_ms: 10000,
          ts_end_ms: 18000,
          findings: ['Shoulder line dropped below the teacher reference.'],
          confidence_stats: {
            mean_confidence: 0.82,
          },
          metadata: {
            pose_provider: 'mediapipe_pose',
            keypoint_schema_id: 'mediapipe_pose_33',
            dwpose_node_deltas: [
              {
                node_id: 'shoulder_line',
                node_label: 'Shoulder line',
                delta_score: 0.16,
                confidence: 0.9,
                finding: 'Shoulder line dropped below the teacher reference.',
                guidance: 'Lift through the collarbones before entering the hold.',
              },
            ],
            sway_metrics: [
              {
                axis: 'front_back_sway',
                delta_score: 0.11,
                confidence: 0.84,
                finding: 'Front/back sway stayed close to the teacher reference.',
                guidance: 'Keep the same breath cadence.',
              },
            ],
            phase_metrics: [
              {
                phase: 'entry',
                delta_score: 0.14,
                confidence: 0.8,
                finding: 'Entry into the posture is slightly rushed.',
                guidance: 'Use one more breath before locking the stance.',
              },
            ],
          },
        },
      });
    }, [props]);

    return <div data-testid="phone-source-preview">{props.session.session_id}:{props.liveMotionSessionId || 'idle'}</div>;
  },
}));

describe('MotionCoachWorkbenchHost', () => {
  beforeEach(() => {
    mocks.existingBridge = null;
    mocks.sessions = [
      {
        session_id: 'session-phone',
        workspace_id: 'ws-motion',
        pairing_code: 'PAIR1234',
        device_id: 'phone_1',
        display_name: 'Phone rear camera',
        source_types: ['phone_camera'],
        state: 'active',
        created_at_epoch: 1,
        updated_at_epoch: 1,
        expires_at_epoch: 999,
      },
      {
        session_id: 'session-obs',
        workspace_id: 'ws-motion',
        pairing_code: 'PAIR9999',
        device_id: 'obs_1',
        display_name: 'OBS Virtual Camera',
        source_types: ['virtual_camera'],
        state: 'paired',
        created_at_epoch: 2,
        updated_at_epoch: 2,
        expires_at_epoch: 999,
      },
    ];
    mocks.referenceLessonState = {
      lesson_id: 'lesson-live',
      title: 'Foundation Flow',
      chapter_ref: 'chapter_alignment',
      focus_cue: 'Lift through the collarbones and stabilize center line.',
      timestamp_ms: 18000,
    };
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('reuses the workspace bridge instead of mounting a second provider', () => {
    mocks.existingBridge = { workspaceId: 'ws-motion' };

    render(
      <MotionCoachWorkbenchHost
        workspaceId="ws-motion"
        apiUrl="http://api.test"
        capabilityCode="yogacoach"
        Component={() => <div data-testid="runtime-component">Runtime</div>}
        aolHost={{}}
        surfacePath={['practice']}
      />,
    );

    expect(screen.queryByTestId('capture-source-bridge-provider')).toBeNull();
    expect(screen.getByTestId('runtime-component')).toBeInTheDocument();
  });

  it('renders a pending Yoga workbench before any motion source session exists', () => {
    mocks.sessions = [];
    const runtimeSnapshots: any[] = [];

    function RuntimeComponent({
      workbenchState,
      hostCapturePreview,
    }: {
      workbenchState: any;
      hostCapturePreview?: React.ReactNode;
    }) {
      runtimeSnapshots.push(workbenchState);
      return (
        <div data-testid="runtime-component">
          <div>{hostCapturePreview}</div>
          {workbenchState.live_motion_session_ref.id}:{workbenchState.live_motion_session_ref.status}
        </div>
      );
    }

    render(
      <MotionCoachWorkbenchHost
        workspaceId="ws-motion"
        apiUrl="http://api.test"
        capabilityCode="yogacoach"
        Component={RuntimeComponent}
        aolHost={{}}
        surfacePath={['practice']}
      />,
    );

    expect(screen.getByTestId('motion-coach-workbench-host')).toBeInTheDocument();
    expect(screen.getByText('Connect a phone, OBS, or desktop camera from Motion source to open the learner stage.')).toBeInTheDocument();
    expect(screen.getByTestId('runtime-component')).toHaveTextContent('live_motion_session_pending:idle');
    expect(runtimeSnapshots[0].connected_capture_source_ref.status).toBe('pairing');
  });

  it('wires Yoga practice controls, preview receiver, and rolling workbench state into the runtime component', async () => {
    const runtimeSnapshots: any[] = [];

    function RuntimeComponent(props: any) {
      runtimeSnapshots.push(props);
      return (
        <div>
          <div>{props.hostCapturePreview}</div>
          <pre data-testid="runtime-workbench-state">{JSON.stringify(props.workbenchState)}</pre>
        </div>
      );
    }

    render(
      <MotionCoachWorkbenchHost
        workspaceId="ws-motion"
        apiUrl="http://api.test"
        capabilityCode="yogacoach"
        Component={RuntimeComponent}
        aolHost={{}}
        surfacePath={['practice']}
      />,
    );

    expect(screen.getByTestId('capture-source-rail')).toHaveTextContent('showPreview:false');
    expect(screen.getByTestId('motion-practice-rail-controller')).toHaveTextContent('yogacoach');

    await waitFor(() => {
      const latest = runtimeSnapshots[runtimeSnapshots.length - 1]?.workbenchState;
      expect(latest?.connected_capture_source_ref?.id).toBe('session-phone');
      expect(latest?.live_motion_session_ref?.status).toBe('live');
      expect(latest?.motion_rollup_ref?.status).toBe('rolling');
      expect(latest?.motion_rollup_ref?.motion_window_count).toBe(1);
      expect(latest?.reference_lesson_state?.activeChapterId).toBe('chapter_alignment');
      expect(latest?.meeting_feedback_ref?.status).toBe('streaming');
      expect(latest?.html_report_artifact_ref?.status).toBe('missing');
    });
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
      return <pre data-testid="runtime-workbench-state-dance">{JSON.stringify(props.workbenchState)}</pre>;
    }

    render(
      <MotionCoachWorkbenchHost
        workspaceId="ws-motion"
        apiUrl="http://api.test"
        capabilityCode="dance_motion_coach"
        Component={RuntimeComponent}
        aolHost={{}}
        surfacePath={['practice']}
      />,
    );

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
