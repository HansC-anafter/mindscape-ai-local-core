import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PhoneSourcePreview } from './PhoneSourcePreview';
import { startWorkspaceReceiverSession } from '@/lib/media-transport/webrtcSessionClient';

vi.mock('@/lib/media-transport/webrtcSessionClient', () => ({
  startWorkspaceReceiverSession: vi.fn(() => ({
    stop: vi.fn(),
    peerConnection: null,
  })),
}));

describe('PhoneSourcePreview', () => {
  afterEach(() => {
    vi.clearAllMocks();
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
});
