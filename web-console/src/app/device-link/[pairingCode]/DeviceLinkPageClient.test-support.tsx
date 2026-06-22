import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, vi } from 'vitest';
import { createElement, type ComponentProps } from 'react';

import { DeviceLinkPageClient } from './DeviceLinkPageClient';

const hoistedMocks = vi.hoisted(() => ({
  socket: {
    send: vi.fn(),
    close: vi.fn(),
    raw: {},
  },
  socketInput: null as any,
  phoneInputs: [] as any[],
  desktopInputs: [] as any[],
  phoneHandles: [] as any[],
  desktopHandles: [] as any[],
  readiness: {
    allowed: true,
  } as any,
  createStream: (label: string) => {
    const tracks = [
      {
        kind: 'video',
        label,
        stop: vi.fn(),
      },
    ];
    return {
      getTracks: () => tracks,
      getVideoTracks: () => tracks,
    } as any;
  },
  openDeviceControlSocket: vi.fn((input) => {
    hoistedMocks.socketInput = input;
    return hoistedMocks.socket;
  }),
  startPhoneBrowserSourceSession: vi.fn(async (input) => {
    hoistedMocks.phoneInputs.push(input);
    const stream = hoistedMocks.createStream(`phone_${input.facingMode || 'environment'}`);
    input.onLocalStream?.(stream);
    const handle = {
      stop: vi.fn(() => stream.getTracks().forEach((track: any) => track.stop())),
      replaceVideoTrack: vi.fn(async (video: MediaTrackConstraints) => {
        const facingMode = typeof video.facingMode === 'object'
          && video.facingMode
          && 'ideal' in video.facingMode
          ? String(video.facingMode.ideal)
          : 'environment';
        const nextStream = hoistedMocks.createStream(`phone_${facingMode}`);
        input.onLocalStream?.(nextStream);
        return nextStream;
      }),
      setVideoOrientation: vi.fn(async (orientation: 'portrait' | 'landscape') => {
        const nextStream = hoistedMocks.createStream(`phone_${input.facingMode || 'environment'}_${orientation}`);
        input.onLocalStream?.(nextStream);
        return nextStream;
      }),
      peerConnection: null,
      localStream: stream,
    };
    hoistedMocks.phoneHandles.push(handle);
    return handle;
  }),
  startDesktopBrowserSourceSession: vi.fn(async (input) => {
    hoistedMocks.desktopInputs.push(input);
    const stream = hoistedMocks.createStream('desktop_camera');
    input.onLocalStream?.(stream);
    const handle = {
      stop: vi.fn(() => stream.getTracks().forEach((track: any) => track.stop())),
      peerConnection: null,
      localStream: stream,
    };
    hoistedMocks.desktopHandles.push(handle);
    return handle;
  }),
}));

export const mocks = hoistedMocks;

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/media-transport/secureContextGuard', () => ({
  assessBrowserMediaCaptureReadiness: vi.fn(() => mocks.readiness),
}));

vi.mock('@/lib/device-binding/deviceBindingClient', () => ({
  openDeviceControlSocket: hoistedMocks.openDeviceControlSocket,
}));

vi.mock('@/lib/media-transport/webrtcSessionClient', () => ({
  buildPhoneVideoConstraints: (facingMode = 'environment') => ({
    facingMode: { ideal: facingMode },
    width: { ideal: 1280 },
    height: { ideal: 720 },
    frameRate: { max: 30 },
  }),
  startPhoneBrowserSourceSession: hoistedMocks.startPhoneBrowserSourceSession,
  startDesktopBrowserSourceSession: hoistedMocks.startDesktopBrowserSourceSession,
}));

vi.mock('@/components/workspace/device-binding/DesktopSourcePicker', () => ({
  DesktopSourcePicker: ({ onSelectionChange }: any) =>
    createElement(
      'button',
      {
        type: 'button',
        onClick: () =>
          onSelectionChange({
            deviceId: 'obs_1',
            label: 'OBS Virtual Camera',
            sourceKind: 'virtual_camera',
          }),
      },
      'Select OBS Virtual Camera',
    ),
}));

vi.mock('@/components/workspace/device-binding/DesktopSourcePreview', () => ({
  DesktopSourcePreview: () =>
    createElement('div', {
      'data-testid': 'desktop-source-preview',
    }),
}));

type DeviceLinkPageClientProps = ComponentProps<typeof DeviceLinkPageClient>;

export function resetDeviceLinkMocks() {
  vi.clearAllMocks();
  mocks.socketInput = null;
  mocks.phoneInputs = [];
  mocks.desktopInputs = [];
  mocks.phoneHandles = [];
  mocks.desktopHandles = [];
  mocks.readiness = { allowed: true };
  vi.unstubAllGlobals();
}

afterEach(resetDeviceLinkMocks);

export function renderDeviceLinkPage(props: Partial<DeviceLinkPageClientProps> = {}) {
  const defaultProps: DeviceLinkPageClientProps = {
    pairingCode: 'PAIR1234',
    workspaceId: 'ws_device',
  };
  render(createElement(DeviceLinkPageClient, { ...defaultProps, ...props }));
}

export async function clickButton(name: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name }));
  });
}

export function openControlSocket() {
  act(() => {
    mocks.socketInput.onOpen();
  });
}

export async function pairSource(sessionId = 'session_1', deviceId = 'phone_1') {
  await act(async () => {
    mocks.socketInput.onEvent({
      type: 'session_paired',
      workspace_id: 'ws_device',
      session_id: sessionId,
      device_id: deviceId,
    });
  });
}

export async function connectAndPairPhone() {
  renderDeviceLinkPage();
  await clickButton('Connect');
  openControlSocket();
  await pairSource();
}

export async function markPhoneConnected() {
  await act(async () => {
    mocks.phoneInputs[0].onState('connected');
  });
}
