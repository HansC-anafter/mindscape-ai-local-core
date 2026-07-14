import {
  createLiveMediaSession,
  type LiveMediaSessionAccess,
} from '@/lib/media-transport/liveMediaSessionClient';
import {
  startDesktopRelayMediaSourceSession,
  startPhoneRelayMediaSourceSession,
} from '@/lib/media-transport/relayMediaSourceSession';
import type { CameraSourceKind } from '@/lib/media-transport/mediaDeviceCatalog';
import type {
  CameraFacingMode,
  CaptureOrientation,
  WebRTCSessionHandle,
  WebRTCSessionState,
} from '@/lib/media-transport/webrtcSessionTypes';
import type { SourceMode } from './useDeviceLinkCaptureSessionTypes';

interface StartDeviceLinkRelayMediaInput {
  apiBase: string;
  workspaceId: string;
  deviceSessionId: string;
  sourceMode: SourceMode;
  selectedCameraKind: CameraSourceKind;
  selectedCameraDeviceId?: string;
  facingMode: CameraFacingMode;
  orientation: CaptureOrientation;
  onLocalStream: (stream: MediaStream) => void;
  onState: (state: WebRTCSessionState) => void;
  onError: (error: Error) => void;
}

export async function startDeviceLinkRelayMedia(
  input: StartDeviceLinkRelayMediaInput,
): Promise<{ access: LiveMediaSessionAccess; handle: WebRTCSessionHandle }> {
  const sourceKind = input.sourceMode === 'phone'
    ? 'phone_camera'
    : input.selectedCameraKind;
  const access = await createLiveMediaSession({
    apiBase: input.apiBase,
    workspaceId: input.workspaceId,
    deviceSessionId: input.deviceSessionId,
    sourceKind,
    capabilities: input.sourceMode === 'phone' ? ['video', 'audio'] : ['video'],
    analysisReserved: true,
  });
  const common = {
    access,
    onLocalStream: input.onLocalStream,
    onState: input.onState,
    onError: input.onError,
  };
  const handle = input.sourceMode === 'phone'
    ? await startPhoneRelayMediaSourceSession({
        ...common,
        audio: true,
        facingMode: input.facingMode,
        videoOrientation: input.orientation,
      })
    : await startDesktopRelayMediaSourceSession({
        ...common,
        sourceKind: input.selectedCameraKind,
        deviceId: input.selectedCameraDeviceId,
      });
  return { access, handle };
}

export async function applyPendingPhoneCaptureSettings({
  handle,
  sourceMode,
  startingFacingMode,
  desiredFacingMode,
  startingOrientation,
  desiredOrientation,
  onStream,
}: {
  handle: WebRTCSessionHandle;
  sourceMode: SourceMode;
  startingFacingMode: CameraFacingMode;
  desiredFacingMode: CameraFacingMode;
  startingOrientation: CaptureOrientation;
  desiredOrientation: CaptureOrientation;
  onStream: (stream: MediaStream) => void;
}): Promise<void> {
  if (sourceMode !== 'phone') {
    return;
  }
  if (desiredFacingMode !== startingFacingMode && handle.replaceVideoTrack) {
    const stream = await handle.replaceVideoTrack({
      facingMode: { ideal: desiredFacingMode },
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { max: 30 },
    });
    onStream(stream);
  }
  if (desiredOrientation !== startingOrientation && handle.setVideoOrientation) {
    onStream(await handle.setVideoOrientation(desiredOrientation));
  }
}
