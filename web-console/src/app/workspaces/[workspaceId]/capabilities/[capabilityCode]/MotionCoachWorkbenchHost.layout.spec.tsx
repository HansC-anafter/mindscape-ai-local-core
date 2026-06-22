// @vitest-environment jsdom

import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  motionCoachMocks as mocks,
  navigationMocks,
  resetMotionCoachMocks,
} from './MotionCoachWorkbenchHost.test-support';
import MotionCoachWorkbenchHost from './MotionCoachWorkbenchHost';

describe('MotionCoachWorkbenchHost', () => {
  beforeEach(() => {
    resetMotionCoachMocks();
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
    const placeholder = screen.getByTestId('motion-coach-host-capture-placeholder');
    expect(placeholder).toHaveTextContent('Connect a phone, OBS, or desktop camera from Motion source to open the learner stage.');
    expect(placeholder.className).toContain('h-full');
    expect(placeholder.className).not.toContain('aspect-video');
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
      motion_lesson_thumbnail: 'https://i.ytimg.com/vi/summer-flow/hqdefault.jpg',
      motion_lesson_course_chapters: JSON.stringify([
        {
          chapter_id: 'summer_flow_ref_1',
          title: 'Standing warmup',
          start_ms: 0,
          end_ms: 42000,
          thumbnail_url: 'https://i.ytimg.com/vi/summer-flow/chapter-1.jpg',
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
      thumbnailUrl: 'https://i.ytimg.com/vi/summer-flow/hqdefault.jpg',
      activeChapterId: 'summer_flow_ref_1',
    });
    expect(firstProps.workbenchState.reference_lesson_state.chapters[0]).toMatchObject({
      thumbnailUrl: 'https://i.ytimg.com/vi/summer-flow/chapter-1.jpg',
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
      thumbnailUrl: 'https://i.ytimg.com/vi/graph-priority/hqdefault.jpg',
    });
    expect(firstProps.workbenchState.reference_lesson_state.chapters[0]).toMatchObject({
      thumbnailUrl: 'https://i.ytimg.com/vi/graph-priority/hqdefault.jpg',
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

});
