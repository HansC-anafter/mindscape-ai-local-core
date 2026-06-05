export type BrowserMediaCaptureBlockReason =
  | 'secure_context_required'
  | 'media_devices_unavailable';

export type BrowserMediaCaptureReadiness =
  | { allowed: true }
  | {
      allowed: false;
      reason: BrowserMediaCaptureBlockReason;
      message: string;
    };

type BrowserMediaScope = typeof globalThis & {
  isSecureContext?: boolean;
  navigator?: {
    mediaDevices?: {
      getUserMedia?: unknown;
    };
  };
};

export function assessBrowserMediaCaptureReadiness(
  scope: BrowserMediaScope = globalThis,
): BrowserMediaCaptureReadiness {
  if (scope.isSecureContext !== true) {
    return {
      allowed: false,
      reason: 'secure_context_required',
      message: 'Camera and microphone capture requires HTTPS on phone browsers.',
    };
  }
  if (typeof scope.navigator?.mediaDevices?.getUserMedia !== 'function') {
    return {
      allowed: false,
      reason: 'media_devices_unavailable',
      message: 'This browser does not expose camera and microphone capture.',
    };
  }
  return { allowed: true };
}
