import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PhoneSourcePreview } from './PhoneSourcePreview';
import { startWorkspaceReceiverSession } from '@/lib/media-transport/webrtcSessionClient';
import { createLivePoseWindowController } from '@/lib/motion-analysis/livePoseWindow';

const mocks = vi.hoisted(() => ({
  receiverInput: null as any,
  receiverHandle: {
    stop: vi.fn(),
    peerConnection: null,
  },
  motionController: {
    start: vi.fn(),
    stop: vi.fn(),
    getStatus: vi.fn(() => ({ state: 'idle', appendedWindowCount: 0 })),
  },
  motionControllerInput: null as any,
}));

vi.mock('@/lib/media-transport/webrtcSessionClient', () => ({
  startWorkspaceReceiverSession: vi.fn((input) => {
    mocks.receiverInput = input;
    return mocks.receiverHandle;
  }),
}));

vi.mock('@/lib/motion-analysis/livePoseWindow', async () => {
  const actual = await vi.importActual<typeof import('@/lib/motion-analysis/livePoseWindow')>(
    '@/lib/motion-analysis/livePoseWindow',
  );
  return {
    ...actual,
    createBrowserMediaPipePoseAdapter: vi.fn(() => ({
      provider: 'test_pose',
      estimate: vi.fn(async () => null),
    })),
    createLivePoseWindowController: vi.fn((input) => {
      mocks.motionControllerInput = input;
      return mocks.motionController;
    }),
  };
});

vi.mock('@/lib/motion-analysis/motionWindowClient', () => ({
  appendMotionWindow: vi.fn(async () => ({ accepted: true })),
}));

describe('PhoneSourcePreview', () => {
  beforeEach(() => {
    Object.defineProperty(window.HTMLMediaElement.prototype, 'play', {
      configurable: true,
      value: vi.fn(async () => undefined),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    mocks.receiverInput = null;
    mocks.motionControllerInput = null;
  });

  it('starts one workspace WebRTC receiver without creating an interval loop', () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');

    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        session={{
          session_id: 'session_1',
          workspace_id: 'ws_device',
          pairing_code: 'PAIR1234',
          device_id: 'phone_1',
          display_name: 'Phone',
          source_types: ['phone_camera'],
          state: 'paired',
          created_at_epoch: 1,
          updated_at_epoch: 1,
          expires_at_epoch: 61,
        }}
      />,
    );

    expect(screen.getByTestId('phone-source-preview-session_1')).toBeTruthy();
    expect(startWorkspaceReceiverSession).toHaveBeenCalledWith(
      expect.objectContaining({
        apiBase: 'http://api.test',
        workspaceId: 'ws_device',
        deviceSessionId: 'session_1',
        mediaSessionId: 'session_1',
      }),
    );
    expect(setIntervalSpy).not.toHaveBeenCalled();
  });

  it('lets host-controlled previews fill a resizable container instead of forcing aspect-video', () => {
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        className="h-full min-h-0 w-full"
        session={{
          session_id: 'session_resizable',
          workspace_id: 'ws_device',
          pairing_code: 'PAIR1234',
          device_id: 'phone_1',
          display_name: 'Phone',
          source_types: ['phone_camera'],
          state: 'paired',
          created_at_epoch: 1,
          updated_at_epoch: 1,
          expires_at_epoch: 61,
        }}
      />,
    );

    const videoFrame = screen.getByTestId('phone-source-preview-session_resizable').parentElement;
    expect(videoFrame?.className).toContain('h-full');
    expect(videoFrame?.className).not.toContain('aspect-video');
  });

  it('does not start motion analysis before a live motion session exists', () => {
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        session={{
          session_id: 'session_1',
          workspace_id: 'ws_device',
          pairing_code: 'PAIR1234',
          device_id: 'phone_1',
          display_name: 'Phone',
          source_types: ['phone_camera'],
          state: 'paired',
          created_at_epoch: 1,
          updated_at_epoch: 1,
          expires_at_epoch: 61,
        }}
      />,
    );

    act(() => {
      mocks.receiverInput.onRemoteStream({} as MediaStream);
    });

    expect(createLivePoseWindowController).not.toHaveBeenCalled();
    expect(screen.getByTestId('phone-source-motion-status-session_1')).toHaveTextContent(
      'practice_required',
    );
  });

  it('shows when a stream arrived but video frames have not rendered yet', () => {
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        session={{
          session_id: 'session_1',
          workspace_id: 'ws_device',
          pairing_code: 'PAIR1234',
          device_id: 'phone_1',
          display_name: 'Phone',
          source_types: ['phone_camera'],
          state: 'paired',
          created_at_epoch: 1,
          updated_at_epoch: 1,
          expires_at_epoch: 61,
        }}
      />,
    );

    act(() => {
      mocks.receiverInput.onRemoteStream({} as MediaStream);
    });

    expect(screen.getAllByText('video_track_waiting_for_frames')).toHaveLength(2);

    fireEvent.canPlay(screen.getByTestId('phone-source-preview-session_1'));

    expect(screen.queryAllByText('video_track_waiting_for_frames')).toHaveLength(0);
  });

  it('starts motion analysis from the received stream when a live motion session exists', async () => {
    const onMotionWindowAppended = vi.fn();
    const { unmount } = render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        liveMotionSessionId="lms_motion_practice"
        onMotionWindowAppended={onMotionWindowAppended}
        session={{
          session_id: 'session_1',
          workspace_id: 'ws_device',
          pairing_code: 'PAIR1234',
          device_id: 'phone_1',
          display_name: 'Phone',
          source_types: ['phone_camera'],
          state: 'paired',
          created_at_epoch: 1,
          updated_at_epoch: 1,
          expires_at_epoch: 61,
        }}
      />,
    );

    act(() => {
      mocks.receiverInput.onRemoteStream({} as MediaStream);
    });

    expect(createLivePoseWindowController).toHaveBeenCalledWith(
      expect.objectContaining({
        liveSessionId: 'lms_motion_practice',
        metadata: expect.objectContaining({
          workspace_id: 'ws_device',
          source_session_id: 'session_1',
        }),
      }),
    );
    expect(mocks.motionController.start).toHaveBeenCalled();

    const summary = {
      window_id: 'window_1',
      live_session_id: 'lms_motion_practice',
      ts_start_ms: 0,
      ts_end_ms: 2000,
      skeleton_family: 'mediapipe_pose_33',
      confidence_stats: { mean_confidence: 0.8 },
      scores: {},
      findings: ['Shift weight back.'],
      keypoint_frame_count: 20,
      metadata: {
        pose_provider: 'mediapipe_pose',
        provider_code: 'browser_mediapipe_pose_lite',
        provider_schema_id: 'mediapipe_pose_landmarker_lite_video',
        keypoint_schema_id: 'mediapipe_pose_33',
        motion_metric_schema_version: 'capture_motion_metrics.v1',
        dwpose_node_deltas: [
          {
            node_id: 'shoulder_line',
            metric: 'capture_line_level_delta',
            learner_value: 0.04,
            reference_value: 0,
            delta_score: 0.333,
            severity: 'green',
          },
        ],
        sway_metrics: [
          {
            axis: 'front_back',
            phase: 'window',
            learner_value: 0.03,
            reference_value: 0.04,
            delta_score: 0.188,
            severity: 'green',
          },
        ],
        phase_metrics: [
          {
            phase: 'hold',
            axis: 'front_back',
            learner_value: 0.02,
            reference_value: 0.02,
            delta_score: 0.167,
            severity: 'green',
          },
        ],
      },
    };
    await mocks.motionControllerInput.appendMotionWindow(summary, 123);
    expect(onMotionWindowAppended).toHaveBeenCalledWith({
      liveSessionId: 'lms_motion_practice',
      response: { accepted: true },
      summary: expect.objectContaining({
        metadata: expect.objectContaining({
          dwpose_node_deltas: expect.any(Array),
          sway_metrics: expect.any(Array),
          phase_metrics: expect.any(Array),
        }),
      }),
    });

    unmount();

    expect(mocks.motionController.stop).toHaveBeenCalled();
  });

  it('shows appended motion window count from the pose controller status', () => {
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        liveMotionSessionId="lms_motion_practice"
        session={{
          session_id: 'session_1',
          workspace_id: 'ws_device',
          pairing_code: 'PAIR1234',
          device_id: 'phone_1',
          display_name: 'Phone',
          source_types: ['phone_camera'],
          state: 'paired',
          created_at_epoch: 1,
          updated_at_epoch: 1,
          expires_at_epoch: 61,
        }}
      />,
    );

    act(() => {
      mocks.receiverInput.onRemoteStream({} as MediaStream);
    });
    act(() => {
      mocks.motionControllerInput.onStatus({
        state: 'active',
        appendedWindowCount: 2,
        lastWindowId: 'lms_motion_practice:window:0:1',
      });
    });

    expect(screen.getByTestId('phone-source-motion-status-session_1')).toHaveTextContent(
      'active · windows 2',
    );
  });

  it('starts the same workspace receiver for virtual camera sessions', () => {
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        session={{
          session_id: 'session_virtual',
          workspace_id: 'ws_device',
          pairing_code: 'PAIR1234',
          device_id: 'desktop_1',
          display_name: 'Virtual camera',
          source_types: ['virtual_camera'],
          state: 'paired',
          created_at_epoch: 1,
          updated_at_epoch: 1,
          expires_at_epoch: 61,
        }}
      />,
    );

    expect(screen.getByTestId('phone-source-preview-session_virtual')).toBeTruthy();
    expect(startWorkspaceReceiverSession).toHaveBeenCalledWith(
      expect.objectContaining({
        deviceSessionId: 'session_virtual',
        mediaSessionId: 'session_virtual',
      }),
    );
  });

  it('starts the same workspace receiver for external provider camera sessions', () => {
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        session={{
          session_id: 'session_provider',
          workspace_id: 'ws_device',
          pairing_code: 'PAIR1234',
          device_id: 'provider_bridge_1',
          display_name: 'External provider bridge',
          source_types: ['external_provider_camera'],
          metadata: {
            capture_surface: 'external_provider_bridge',
            provider_family: 'dji_ground_imaging',
          },
          state: 'paired',
          created_at_epoch: 1,
          updated_at_epoch: 1,
          expires_at_epoch: 61,
        }}
      />,
    );

    expect(screen.getByTestId('phone-source-preview-session_provider')).toBeTruthy();
    expect(startWorkspaceReceiverSession).toHaveBeenCalledWith(
      expect.objectContaining({
        deviceSessionId: 'session_provider',
        mediaSessionId: 'session_provider',
      }),
    );
  });
});
