import { fireEvent, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { expect, vi } from 'vitest';

const hoistedMocks = vi.hoisted(() => ({
  socket: {
    send: vi.fn(),
    close: vi.fn(),
    raw: {},
  },
  socketInput: null as any,
}));

export const mocks = hoistedMocks;

vi.mock('@/lib/device-binding/deviceBindingClient', () => ({
  buildDeviceControlWebSocketUrl: vi.fn(({
    apiBase,
    pairingCode,
    workspaceId,
  }: {
    apiBase: string;
    pairingCode: string;
    workspaceId: string;
  }) => {
    const wsBase = apiBase
      .replace(/\/+$/, '')
      .replace(/^http:/, 'ws:')
      .replace(/^https:/, 'wss:');
    return `${wsBase}/api/v1/workspaces/${workspaceId}/device-bindings/${pairingCode}/control`;
  }),
  buildDeviceLinkHttpsHealthUrl: vi.fn(({ apiBase }: { apiBase: string }) => (
    `${apiBase.replace(/\/+$/, '')}/api/v1/host/services/device-link-https/health`
  )),
  createDevicePairingCode: vi.fn(async () => ({
    workspace_id: 'ws_device',
    pairing_code: 'PAIR1234',
    expires_at_epoch: 1000,
    expires_in_seconds: 120,
    device_link_path: '/device-link/PAIR1234',
  })),
  openWorkspaceDeviceControlSocket: vi.fn((input) => {
    mocks.socketInput = input;
    return mocks.socket;
  }),
  revokeDeviceSession: vi.fn(async () => ({
    type: 'session_revoked',
    workspace_id: 'ws_device',
    active_sessions: [],
  })),
}));

vi.mock('./PhoneSourcePreview', () => ({
  PhoneSourcePreview: (props: { session: { session_id: string }; liveMotionSessionId?: string }) => {
    const { session, liveMotionSessionId } = props;
    return createElement('div', {
      'data-testid': `mock-phone-source-preview-${session.session_id}`,
      'data-live-motion-session-id': liveMotionSessionId || '',
    });
  },
}));

export async function waitForPairingFlow() {
  const { createDevicePairingCode } = await import('@/lib/device-binding/deviceBindingClient');
  await waitFor(() => {
    expect(createDevicePairingCode).toHaveBeenCalledWith({
      apiBase: 'http://api.test',
      workspaceId: 'ws_device',
      expiresInSeconds: 600,
    });
  });
  await screen.findByTestId('capture-provider-readiness-block');
}

export function openProviderSetup(providerId: 'phone' | 'desktop' | 'external') {
  fireEvent.click(screen.getByTestId(`capture-provider-tool-${providerId}`));
  return screen.getByTestId('capture-provider-wizard');
}

export function resetMotionSourceRailPanelTestState() {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  mocks.socketInput = null;
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', 'http://localhost:3000/');
}
