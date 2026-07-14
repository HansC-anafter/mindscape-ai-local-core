import { sourceKindLabel, type CameraSourceKind } from '@/lib/media-transport/mediaDeviceCatalog';
import type { DeviceControlMessage } from '@/lib/device-binding/deviceBindingClient';
import type {
  CameraFacingMode,
  CaptureOrientation,
} from '@/lib/media-transport/webrtcSessionClient';
import { buildDeviceId } from './useDeviceLinkCaptureSessionHelpers';
import type { SourceMode } from './useDeviceLinkCaptureSessionTypes';

interface DeviceLinkSourceJoinPayloadInput {
  captureOrientation: CaptureOrientation;
  phoneFacingMode: CameraFacingMode;
  selectedCameraKind: CameraSourceKind;
  sourceMode: SourceMode;
}

export function buildDeviceLinkSourceJoinPayload({
  captureOrientation,
  phoneFacingMode,
  selectedCameraKind,
  sourceMode,
}: DeviceLinkSourceJoinPayloadInput): Extract<DeviceControlMessage, { type: 'source_join' }> {
  return {
    type: 'source_join' as const,
    device_id: buildDeviceId(),
    display_name: sourceMode === 'phone'
      ? 'Phone camera'
      : sourceKindLabel(selectedCameraKind),
    source_types: sourceMode === 'phone'
      ? ['phone_camera', 'microphone']
      : [selectedCameraKind],
    metadata: {
      user_agent: typeof navigator === 'undefined' ? 'unknown' : navigator.userAgent,
      source_mode: sourceMode,
      secure_context: Boolean(typeof window !== 'undefined' && window.isSecureContext),
      source_origin_scheme: typeof window === 'undefined'
        ? 'unknown'
        : window.location.protocol.replace(':', ''),
      capture_surface: 'device_link',
      ...(sourceMode === 'phone' ? {
        camera_facing_mode: phoneFacingMode,
        capture_orientation: captureOrientation,
      } : {}),
    },
  };
}
