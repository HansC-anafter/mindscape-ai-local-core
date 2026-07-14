import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import { refreshLiveMediaSessionAccess } from '@/lib/media-transport/liveMediaSessionClient';
import { startWhepPreview } from '@/lib/media-transport/whepPreviewClient';
import { PhoneSourcePreview } from './PhoneSourcePreview';

const mocks = vi.hoisted(() => ({
  previewInput: null as any,
  previewHandle: {
    stop: vi.fn(),
    peerConnection: null,
  },
}));

vi.mock('@/lib/media-transport/liveMediaSessionClient', () => ({
  refreshLiveMediaSessionAccess: vi.fn(async () => ({
    session: {
      workspace_id: 'ws_device',
      device_session_id: 'session_1',
      media_session_id: 'media_1',
      stream_path: 'workspace/ws_device/media_1',
      source_kind: 'phone_camera',
      relay_profile: 'public',
      capabilities: ['video', 'audio'],
      analysis_reserved: true,
      state: 'ready',
      endpoints: {
        whip_publish_url: 'https://media.test/live/whip',
        whep_preview_url: 'https://media.test/live/whep',
        rtmps_publish_url: 'rtmps://media.test:1936/live',
        rtsps_receiver_url: 'rtsps://media.test:8322/live',
      },
      receiver_descriptor_ref: 'receiver://test',
      created_at_epoch: 1,
      updated_at_epoch: 1,
      expires_at_epoch: 3601,
    },
    tokens: {
      publish: 'publish_token',
      preview: 'preview_token',
    },
  })),
}));

vi.mock('@/lib/media-transport/whepPreviewClient', () => ({
  startWhepPreview: vi.fn(async (input) => {
    mocks.previewInput = input;
    return mocks.previewHandle;
  }),
}));

function buildSession(overrides: Partial<DeviceSessionEntry> = {}): DeviceSessionEntry {
  return {
    session_id: 'session_1',
    workspace_id: 'ws_device',
    pairing_code: 'PAIR1234',
    device_id: 'phone_1',
    display_name: 'Phone',
    source_types: ['phone_camera'],
    state: 'paired',
    media_session_id: 'media_1',
    media_session_state: 'ready',
    media_session_expires_at_epoch: 3601,
    created_at_epoch: 1,
    updated_at_epoch: 1,
    expires_at_epoch: 3601,
    ...overrides,
  };
}

describe('PhoneSourcePreview', () => {
  beforeEach(() => {
    Object.defineProperty(window.HTMLMediaElement.prototype, 'play', {
      configurable: true,
      value: vi.fn(async () => undefined),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    mocks.previewInput = null;
  });

  it('refreshes scoped access and starts a WHEP preview for the active media session', async () => {
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        session={buildSession()}
      />,
    );

    await waitFor(() => expect(startWhepPreview).toHaveBeenCalledTimes(1));
    expect(refreshLiveMediaSessionAccess).toHaveBeenCalledWith({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      deviceSessionId: 'session_1',
      mediaSessionId: 'media_1',
    });
    expect(startWhepPreview).toHaveBeenCalledWith(expect.objectContaining({
      endpoint: 'https://media.test/live/whep',
      token: 'preview_token',
    }));
  });

  it('waits without requesting credentials when no media session is attached', () => {
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        session={buildSession({ media_session_id: null })}
      />,
    );

    expect(refreshLiveMediaSessionAccess).not.toHaveBeenCalled();
    expect(startWhepPreview).not.toHaveBeenCalled();
    expect(screen.getAllByText('Waiting for the source media session.')).toHaveLength(2);
  });

  it('renders the relay stream without producing browser-side motion windows', async () => {
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        liveMotionSessionId="lms_practice"
        onMotionWindowAppended={vi.fn()}
        session={buildSession()}
      />,
    );
    await waitFor(() => expect(startWhepPreview).toHaveBeenCalledTimes(1));
    const stream = { getTracks: () => [] } as unknown as MediaStream;

    act(() => {
      mocks.previewInput.onRemoteStream(stream);
    });

    const video = screen.getByTestId('phone-source-preview-session_1') as HTMLVideoElement;
    expect(video.srcObject).toBe(stream);
    expect(screen.getByTestId('phone-source-motion-status-session_1')).toHaveTextContent(
      'Local Core analysis handoff',
    );
    expect(screen.getAllByText('video_track_waiting_for_frames')).toHaveLength(2);

    fireEvent.canPlay(video);
    expect(screen.queryByText('video_track_waiting_for_frames')).toBeNull();
  });

  it('stops the WHEP resource when the preview unmounts', async () => {
    const { unmount } = render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        session={buildSession()}
      />,
    );
    await waitFor(() => expect(startWhepPreview).toHaveBeenCalledTimes(1));
    mocks.previewHandle.stop.mockClear();

    unmount();

    expect(mocks.previewHandle.stop).toHaveBeenCalledTimes(1);
  });

  it('uses bounded reconnect delays after WHEP failure', async () => {
    vi.useFakeTimers();
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        session={buildSession()}
      />,
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(startWhepPreview).toHaveBeenCalledTimes(1);

    act(() => {
      mocks.previewInput.onError(new Error('whep_connection_failed'));
    });
    await act(async () => {
      vi.advanceTimersByTime(1500);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(startWhepPreview).toHaveBeenCalledTimes(2);
  });

  it('lets host-controlled previews fill a resizable container', () => {
    render(
      <PhoneSourcePreview
        apiUrl="http://api.test"
        workspaceId="ws_device"
        className="h-full min-h-0 w-full"
        session={buildSession()}
      />,
    );

    const videoFrame = screen.getByTestId('phone-source-preview-session_1').parentElement;
    expect(videoFrame?.className).toContain('h-full');
    expect(videoFrame?.className).not.toContain('aspect-video');
  });
});
