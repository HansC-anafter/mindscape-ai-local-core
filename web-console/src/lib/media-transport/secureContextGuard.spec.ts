import { describe, expect, it } from 'vitest';

import { assessBrowserMediaCaptureReadiness } from './secureContextGuard';

describe('secureContextGuard', () => {
  it('blocks browser capture outside a secure context', () => {
    expect(
      assessBrowserMediaCaptureReadiness({
        isSecureContext: false,
        navigator: {
          mediaDevices: {
            getUserMedia: () => undefined,
          },
        },
      } as any),
    ).toMatchObject({
      allowed: false,
      reason: 'secure_context_required',
    });
  });

  it('blocks browser capture when mediaDevices is unavailable', () => {
    expect(
      assessBrowserMediaCaptureReadiness({
        isSecureContext: true,
        navigator: {},
      } as any),
    ).toMatchObject({
      allowed: false,
      reason: 'media_devices_unavailable',
    });
  });

  it('allows browser capture only when HTTPS media capture is available', () => {
    expect(
      assessBrowserMediaCaptureReadiness({
        isSecureContext: true,
        navigator: {
          mediaDevices: {
            getUserMedia: () => undefined,
          },
        },
      } as any),
    ).toEqual({ allowed: true });
  });
});
