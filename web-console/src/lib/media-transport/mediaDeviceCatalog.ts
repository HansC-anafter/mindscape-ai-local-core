export type CameraSourceKind = 'desktop_camera' | 'usb_camera' | 'virtual_camera';

export type BrowserVideoInputSource = {
  deviceId: string;
  groupId?: string;
  label: string;
  sourceKind: CameraSourceKind;
};

type MediaDevicesLike = {
  enumerateDevices: () => Promise<MediaDeviceInfo[]>;
  getUserMedia?: (constraints: MediaStreamConstraints) => Promise<MediaStream>;
  addEventListener?: (
    type: 'devicechange',
    listener: EventListener,
  ) => void;
  removeEventListener?: (
    type: 'devicechange',
    listener: EventListener,
  ) => void;
};

function mapVideoInputCatalog(devices: MediaDeviceInfo[]): BrowserVideoInputSource[] {
  return devices
    .filter((device) => device.kind === 'videoinput')
    .map((device, index) => {
      const label = device.label || `Camera ${index + 1}`;
      return {
        deviceId: device.deviceId,
        groupId: device.groupId || undefined,
        label,
        sourceKind: classifyVideoInputSource(label),
      };
    });
}

export function classifyVideoInputSource(label: string): CameraSourceKind {
  const normalized = label.trim().toLowerCase();
  if (normalized.includes('obs') || normalized.includes('virtual camera')) {
    return 'virtual_camera';
  }
  if (
    normalized.includes('usb') ||
    normalized.includes('external') ||
    normalized.includes('capture')
  ) {
    return 'usb_camera';
  }
  return 'desktop_camera';
}

export async function loadVideoInputCatalog(
  mediaDevices: MediaDevicesLike | undefined = globalThis.navigator?.mediaDevices,
): Promise<BrowserVideoInputSource[]> {
  if (!mediaDevices?.enumerateDevices) {
    return [];
  }
  const devices = await mediaDevices.enumerateDevices();
  const catalog = mapVideoInputCatalog(devices);
  if (catalog.length || !mediaDevices.getUserMedia) {
    return catalog;
  }
  const stream = await mediaDevices.getUserMedia({ video: true, audio: false });
  try {
    return mapVideoInputCatalog(await mediaDevices.enumerateDevices());
  } finally {
    for (const track of stream.getTracks()) {
      track.stop();
    }
  }
}

export function attachDeviceChangeRefresh(
  mediaDevices: MediaDevicesLike | undefined,
  onChange: () => void,
): () => void {
  if (!mediaDevices?.addEventListener || !mediaDevices.removeEventListener) {
    return () => undefined;
  }
  mediaDevices.addEventListener('devicechange', onChange);
  return () => mediaDevices.removeEventListener?.('devicechange', onChange);
}

export function sourceKindLabel(sourceKind: CameraSourceKind | 'phone_camera'): string {
  if (sourceKind === 'virtual_camera') {
    return 'Virtual camera';
  }
  if (sourceKind === 'usb_camera') {
    return 'USB camera';
  }
  if (sourceKind === 'desktop_camera') {
    return 'Desktop camera';
  }
  return 'Phone camera';
}
