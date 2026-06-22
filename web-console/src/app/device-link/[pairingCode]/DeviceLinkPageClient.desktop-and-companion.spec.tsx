import { describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';

import {
  clickButton,
  mocks,
  openControlSocket,
  pairSource,
  renderDeviceLinkPage,
} from './DeviceLinkPageClient.test-support';

describe('DeviceLinkPageClient desktop and companion behavior', () => {
  it('starts virtual camera media transport without sending device labels to backend', async () => {
    renderDeviceLinkPage();

    await clickButton('Computer camera');
    await clickButton('Select OBS Virtual Camera');
    await clickButton('Connect');
    openControlSocket();

    expect(mocks.socket.send).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'source_join',
        display_name: 'Virtual camera',
        source_types: ['virtual_camera'],
        metadata: expect.objectContaining({
          source_mode: 'camera',
          secure_context: false,
          source_origin_scheme: 'http',
          capture_surface: 'device_link',
        }),
      }),
    );
    expect(JSON.stringify(mocks.socket.send.mock.calls)).not.toContain('OBS Virtual Camera');

    await pairSource('session_1', 'desktop_1');

    expect(mocks.startDesktopBrowserSourceSession).toHaveBeenCalledWith(
      expect.objectContaining({
        apiBase: 'http://api.test',
        workspaceId: 'ws_device',
        deviceSessionId: 'session_1',
        mediaSessionId: 'session_1',
        sourceKind: 'virtual_camera',
        deviceId: 'obs_1',
      }),
    );
    expect(mocks.startPhoneBrowserSourceSession).not.toHaveBeenCalled();
  });

  it('can open directly in camera source mode from a rail deep link', () => {
    renderDeviceLinkPage({
      initialSourceMode: 'camera',
    });

    expect(screen.getByRole('button', { name: 'Select OBS Virtual Camera' })).toBeTruthy();
    expect(screen.getByTestId('desktop-source-preview')).toBeTruthy();
  });

  it('renders the pad companion layout on regular-width screens and accepts reference lesson state', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));

    renderDeviceLinkPage();

    await waitFor(() => expect(screen.getByTestId('pad-capture-companion')).toBeTruthy());
    expect(screen.getByText('Reference lesson')).toBeTruthy();

    await clickButton('Connect');
    act(() => {
      mocks.socketInput.onEvent({
        type: 'reference_lesson_state',
        workspace_id: 'ws_device',
        reference_lesson_state: {
          chapter_ref: 'chapter_01',
          title: 'Mountain pose alignment',
          timestamp_ms: 65000,
          focus_cue: 'Ground both feet before raising arms.',
        },
      });
    });

    expect(screen.getByText('Mountain pose alignment')).toBeTruthy();
    expect(screen.getByText('1:05')).toBeTruthy();
    expect(screen.getByText('Ground both feet before raising arms.')).toBeTruthy();
  });
});
