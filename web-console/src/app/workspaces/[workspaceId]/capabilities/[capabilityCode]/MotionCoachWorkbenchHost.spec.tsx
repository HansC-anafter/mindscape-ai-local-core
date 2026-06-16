// @vitest-environment jsdom

import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MotionCoachWorkbenchHost from './MotionCoachWorkbenchHost';

const navigationMocks = vi.hoisted(() => ({
  searchParams: new URLSearchParams(),
}));

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

vi.mock('next/navigation', () => ({
  useSearchParams: () => navigationMocks.searchParams,
}));

vi.mock('@/components/workspace/device-binding/capture-bridge/CaptureSourceBridgeProvider', () => ({
  CaptureSourceBridgeProvider: ({ children }: { children: React.ReactNode }) => React.createElement(
    'div',
    { 'data-testid': 'capture-source-bridge-provider' },
    children,
  ),
  useCaptureSourceBridge: () => ({
    sessions: mocks.sessions,
    referenceLessonState: mocks.referenceLessonState,
  }),
  useOptionalCaptureSourceBridge: () => mocks.existingBridge,
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

    return React.createElement(
      'div',
      { 'data-testid': 'phone-source-preview' },
      `${props.session.session_id}:${props.liveMotionSessionId || 'idle'}`,
    );
  },
}));

describe('MotionCoachWorkbenchHost', () => {
  beforeEach(() => {
    navigationMocks.searchParams = new URLSearchParams();
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

    render(React.createElement(MotionCoachWorkbenchHost, {
      workspaceId: 'ws-motion',
      apiUrl: 'http://api.test',
      capabilityCode: 'yogacoach',
      Component: () => React.createElement('div', { 'data-testid': 'runtime-component' }, 'Runtime'),
      aolHost: {},
      surfacePath: ['practice'],
    }));

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
      return React.createElement(
        'div',
        { 'data-testid': 'runtime-component' },
        React.createElement('div', null, hostCapturePreview),
        `${workbenchState.live_motion_session_ref.id}:${workbenchState.live_motion_session_ref.status}`,
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

    expect(screen.getByTestId('motion-coach-workbench-host')).toBeInTheDocument();
    expect(screen.getByText('Connect a phone, OBS, or desktop camera from Motion source to open the learner stage.')).toBeInTheDocument();
    expect(screen.getByTestId('runtime-component')).toHaveTextContent('live_motion_session_pending:idle');
    expect(runtimeSnapshots[0].connected_capture_source_ref.status).toBe('pairing');
  });

  it('wires Yoga practice controls, preview receiver, and rolling workbench state into the runtime component', async () => {
    const runtimeSnapshots: any[] = [];

    function RuntimeComponent(props: any) {
      runtimeSnapshots.push(props);
      return React.createElement(
        'div',
        null,
        React.createElement('div', null, props.hostCapturePreview),
        React.createElement('pre', { 'data-testid': 'runtime-workbench-state' }, JSON.stringify(props.workbenchState)),
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
    expect(firstProps.motionCoachControls.coachPackLock).toBe('yogacoach');
    expect(firstProps.motionCoachControls.sessions).toHaveLength(2);

    await act(async () => {
      firstProps.motionCoachControls.onSelectedSessionChange('session-phone');
      firstProps.motionCoachControls.onLaunchInputChange({
        apiUrl: 'http://api.test',
        workspaceId: 'ws-motion',
        sourceSession: mocks.sessions[0],
        coachPack: 'yogacoach',
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
      firstProps.motionCoachControls.onResultChange({
        meetingId: 'meeting-1',
        commandId: 'command-1',
        liveSessionId: 'live-session-1',
        sourceSessionId: 'session-phone',
        practiceSessionId: 'practice-1',
        liveGuidanceEnabled: true,
        coachPack: 'yogacoach',
        practiceMode: 'live_guidance',
        status: 'started',
      });
    });

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

  it('hydrates Yoga lesson handoff search params into initial instruction source and workbench gate state', () => {
    navigationMocks.searchParams = new URLSearchParams({
      motion_lesson_handoff: '1',
      motion_lesson_target: 'yogacoach',
      motion_lesson_kind: 'youtube_instruction_ref',
      motion_lesson_value: 'https://www.youtube.com/watch?v=summer-flow',
      motion_lesson_title: 'Summer Flow With Katie',
      motion_lesson_provider: 'youtube',
      motion_lesson_course_chapters: JSON.stringify([
        {
          chapter_id: 'summer_flow_ref_1',
          title: 'Standing warmup',
          start_ms: 0,
          end_ms: 42000,
        },
      ]),
    });
    const runtimeSnapshots: any[] = [];

    function RuntimeComponent(props: any) {
      runtimeSnapshots.push(props);
      return React.createElement('div', { 'data-testid': 'runtime-component-handoff' }, 'handoff');
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
    expect(firstProps.motionCoachControls.initialInstructionSource).toMatchObject({
      kind: 'youtube_instruction_ref',
      value: 'https://www.youtube.com/watch?v=summer-flow',
      courseChaptersError: null,
    });
    expect(firstProps.workbenchState.reference_lesson_import_ref).toMatchObject({
      status: 'ready',
      source_provider: 'youtube',
      ready_chapter_count: 1,
    });
    expect(firstProps.workbenchState.reference_lesson_state).toMatchObject({
      title: 'Summer Flow With Katie',
      activeChapterId: 'summer_flow_ref_1',
    });
  });

  it('prefers shell graph selection over url payload when the route marker is present', () => {
    navigationMocks.searchParams = new URLSearchParams({
      motion_lesson_handoff: '1',
      motion_lesson_target: 'yogacoach',
      motion_lesson_kind: 'youtube_instruction_ref',
      motion_lesson_value: 'https://www.youtube.com/watch?v=url-fallback',
      motion_lesson_title: 'URL Fallback Lesson',
      motion_lesson_provider: 'youtube',
      motion_lesson_course_chapters: JSON.stringify([
        {
          chapter_id: 'url_ref_1',
          title: 'URL fallback chapter',
          start_ms: 0,
          end_ms: 9000,
        },
      ]),
    });
    const runtimeSnapshots: any[] = [];

    function RuntimeComponent(props: any) {
      runtimeSnapshots.push(props);
      return React.createElement('div', { 'data-testid': 'runtime-component-graph-handoff' }, 'graph-handoff');
    }

    render(React.createElement(MotionCoachWorkbenchHost, {
      workspaceId: 'ws-motion',
      apiUrl: 'http://api.test',
      capabilityCode: 'yogacoach',
      Component: RuntimeComponent,
      aolHost: {
        graphSelection: {
          owner_pack: 'social_video_refs',
          selection_kind: 'anchor',
          anchors: [
            {
              uri: 'mindscape://social_video_refs/instruction_ref/ref_graph_001',
              owner_pack: 'social_video_refs',
              object_kind: 'instruction_ref',
              object_id: 'ref_graph_001',
              workspace_id: 'ws-motion',
              selector: {
                instruction_ref_id: 'ref_graph_001',
                source_provider: 'youtube',
                canonical_url: 'https://www.youtube.com/watch?v=graph-priority',
                start_seconds: 12,
                end_seconds: 24,
              },
              source_surface: 'social_video_refs.refs',
              label: 'Graph Priority Flow',
              role: 'source',
            },
          ],
          lens_code: 'instruction_memory',
          relation_scope: ['instruction_memory', 'metadata_only_reference'],
          node_limit: 8,
          relation_limit: 8,
          snapshot_budget: {
            max_nodes: 8,
            max_edges: 8,
            max_prompt_chars: 1200,
          },
          source_surface: 'social_video_refs.refs',
          governance_tags: ['reference_only', 'provider_neutral', 'no_media_download'],
          selection_hash: 'gsel_graph_priority',
        },
      },
      surfacePath: ['practice'],
    }));

    const firstProps = runtimeSnapshots[0];
    expect(firstProps.motionCoachControls.initialInstructionSource).toMatchObject({
      value: 'https://www.youtube.com/watch?v=graph-priority',
      kind: 'youtube_instruction_ref',
    });
    expect(firstProps.workbenchState.reference_lesson_state).toMatchObject({
      title: 'Graph Priority Flow',
      activeChapterId: 'ref_graph_001',
    });
  });

  it('ignores shell graph selection without the route handoff marker', () => {
    const runtimeSnapshots: any[] = [];

    function RuntimeComponent(props: any) {
      runtimeSnapshots.push(props);
      return React.createElement('div', { 'data-testid': 'runtime-component-no-route-marker' }, 'no-route-marker');
    }

    render(React.createElement(MotionCoachWorkbenchHost, {
      workspaceId: 'ws-motion',
      apiUrl: 'http://api.test',
      capabilityCode: 'yogacoach',
      Component: RuntimeComponent,
      aolHost: {
        graphSelection: {
          owner_pack: 'social_video_refs',
          selection_kind: 'anchor',
          anchors: [
            {
              uri: 'mindscape://social_video_refs/instruction_ref/ref_stale_001',
              owner_pack: 'social_video_refs',
              object_kind: 'instruction_ref',
              object_id: 'ref_stale_001',
              workspace_id: 'ws-motion',
              selector: {
                instruction_ref_id: 'ref_stale_001',
                source_provider: 'youtube',
                canonical_url: 'https://www.youtube.com/watch?v=stale-selection',
                start_seconds: 1,
                end_seconds: 3,
              },
              source_surface: 'social_video_refs.refs',
              label: 'Stale Selection',
              role: 'source',
            },
          ],
          lens_code: 'instruction_memory',
          relation_scope: ['instruction_memory', 'metadata_only_reference'],
          node_limit: 8,
          relation_limit: 8,
          snapshot_budget: {
            max_nodes: 8,
            max_edges: 8,
            max_prompt_chars: 1200,
          },
          source_surface: 'social_video_refs.refs',
          governance_tags: ['reference_only', 'provider_neutral', 'no_media_download'],
          selection_hash: 'gsel_stale',
        },
      },
      surfacePath: ['practice'],
    }));

    const firstProps = runtimeSnapshots[0];
    expect(firstProps.motionCoachControls.initialInstructionSource).toBeNull();
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
