import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';

import {
  openProviderSetup,
  resetMotionSourceRailPanelTestState,
  waitForPairingFlow,
} from './motionSourceRailPanelTestHarness';
import { MotionSourceRailPanel } from './MotionSourceRailPanel';

describe('MotionSourceRailPanel capture relay provider', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      json: async () => ({}),
    })));
  });

  afterEach(() => {
    resetMotionSourceRailPanelTestState();
  });

  it('starts the capture relay helper through the backend host-services proxy', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes('/api/v1/host/services/capture-relay')) {
        const requestBody = JSON.parse(String(init?.body || '{}'));
        if (requestBody.action === 'install_mediamtx') {
          return {
            ok: true,
            json: async () => ({
              schema_version: 'capture_relay_control.v1',
              action: 'install_mediamtx',
              status: 'ready_to_start',
              install_result: 'installed',
              install_method: 'homebrew',
              relay: {
                running: false,
                binary_path: '/opt/homebrew/bin/mediamtx',
              },
              urls: {
                stream_name: 'external-camera',
                publish_url: 'rtmp://192.168.0.10/external-camera',
                read_url: 'rtsp://127.0.0.1:8554/external-camera',
              },
              install_guidance: {
                dependency: 'mediamtx',
                status: 'installed',
                binary_path: '/opt/homebrew/bin/mediamtx',
              },
            }),
          };
        }
        return {
          ok: true,
          json: async () => ({
            schema_version: 'capture_relay_control.v1',
            action: 'start',
            status: 'blocked',
            reason: 'relay_binary_missing',
            urls: {
              stream_name: 'external-camera',
              publish_url: 'rtmp://192.168.0.10/external-camera',
              read_url: 'rtsp://127.0.0.1:8554/external-camera',
            },
            install_guidance: {
              dependency: 'mediamtx',
              status: 'missing',
              official_release_url: 'https://github.com/bluenviron/mediamtx/releases/latest',
              detected_platform: 'darwin',
              detected_arch: 'arm64',
              recommended_asset_pattern: 'mediamtx_*_darwin_arm64.tar.gz',
              host_tools: {
                brew_available: false,
                brew_path: null,
              },
              options: [
                {
                  id: 'homebrew',
                  command: 'brew install mediamtx',
                  available: false,
                },
                {
                  id: 'official_release',
                  release_url: 'https://github.com/bluenviron/mediamtx/releases/latest',
                  asset_pattern: 'mediamtx_*_darwin_arm64.tar.gz',
                  install_target: '/opt/homebrew/bin/mediamtx or /usr/local/bin/mediamtx',
                },
              ],
            },
          }),
        };
      }
      return {
        ok: false,
        json: async () => ({}),
      };
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      createElement(MotionSourceRailPanel, {
        apiUrl: 'http://api.test',
        workspaceId: 'ws_device',
      }),
    );

    await waitForPairingFlow();
    openProviderSetup('external');
    fireEvent.click(screen.getByText('Local RTMP to OBS Virtual Camera'));
    fireEvent.click(screen.getByRole('button', { name: 'Start local relay' }));

    await screen.findByText('rtmp://192.168.0.10/external-camera');
    await waitFor(() => {
      const captureCall = fetchMock.mock.calls.find(([url]) => (
        String(url).includes('/api/v1/host/services/capture-relay')
      ));
      expect(captureCall).toBeTruthy();
      expect(captureCall?.[0]).toBe('http://api.test/api/v1/host/services/capture-relay');
      expect(captureCall?.[1]).toEqual(expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }));
      expect(JSON.parse(String(captureCall?.[1]?.body))).toEqual({
        action: 'start',
        stream_name: 'external-camera',
        open_obs: false,
        timeout_ms: 5000,
      });
    });
    expect(screen.getByTestId('capture-relay-launcher-card')).toHaveTextContent(
      'Relay binary missing',
    );
    expect(screen.getByTestId('capture-relay-host-readiness')).toHaveTextContent(
      'Install OBS at /Applications/OBS.app',
    );
    expect(screen.getByTestId('capture-relay-install-guidance')).toHaveTextContent(
      'Install MediaMTX before starting this relay',
    );
    expect(screen.getByRole('link', { name: /Open MediaMTX releases/i })).toHaveAttribute(
      'href',
      'https://github.com/bluenviron/mediamtx/releases/latest',
    );
    expect(screen.getByTestId('capture-relay-install-button')).toBeEnabled();
    fireEvent.click(screen.getByTestId('capture-relay-install-button'));
    await screen.findByText('Ready to start');
    await waitFor(() => {
      const installCall = fetchMock.mock.calls.find(([, init]) => (
        JSON.parse(String(init?.body || '{}')).action === 'install_mediamtx'
      ));
      expect(installCall?.[0]).toBe('http://api.test/api/v1/host/services/capture-relay');
      expect(JSON.parse(String(installCall?.[1]?.body))).toEqual({
        action: 'install_mediamtx',
        stream_name: 'external-camera',
        install_method: 'homebrew',
        open_obs: false,
        timeout_ms: 120000,
      });
    });
  });

  it('surfaces a clear external publisher blocker after the relay and OBS are ready', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes('/api/v1/host/services/capture-relay')) {
        const requestBody = JSON.parse(String(init?.body || '{}'));
        return {
          ok: true,
          json: async () => ({
            schema_version: 'capture_relay_control.v1',
            action: requestBody.action,
            status: 'running',
            relay: {
              mode: 'managed',
              managed: true,
              running: true,
              rtmp_listener_open: true,
              binary_path: '/opt/homebrew/bin/mediamtx',
              recent_output: [
                "2026/06/21 03:59:08 INF [RTSP] [conn 127.0.0.1:57472] closed: path 'external-camera' is not configured",
              ],
            },
            obs: {
              app_path: '/Applications/OBS.app',
              app_present: true,
              websocket_reachable: true,
            },
            urls: {
              stream_name: 'external-camera',
              publish_url: 'rtmp://192.168.0.10/external-camera',
              read_url: 'rtsp://127.0.0.1:8554/external-camera',
            },
          }),
        };
      }
      return {
        ok: false,
        json: async () => ({}),
      };
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      createElement(MotionSourceRailPanel, {
        apiUrl: 'http://api.test',
        workspaceId: 'ws_device',
      }),
    );

    await waitForPairingFlow();
    openProviderSetup('external');
    fireEvent.click(screen.getByText('Local RTMP to OBS Virtual Camera'));
    fireEvent.click(screen.getByRole('button', { name: 'Check local relay' }));

    await screen.findByText('rtmp://192.168.0.10/external-camera');
    expect(screen.getByTestId('capture-relay-host-readiness')).toHaveTextContent(
      'External publisher',
    );
    expect(screen.getByTestId('capture-relay-host-readiness')).toHaveTextContent(
      'Blocked',
    );
    expect(screen.getByTestId('capture-relay-host-readiness')).toHaveTextContent(
      'no external RTMP publisher is connected',
    );
    expect(screen.getByTestId('capture-relay-host-readiness')).toHaveTextContent(
      'camera livestream app',
    );
  });
});
