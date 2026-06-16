import { describe, expect, it } from 'vitest';

import {
  assessDeviceLinkOriginReadiness,
  isLoopbackDeviceLinkHost,
  resolveDeviceLinkPublicOrigin,
} from './deviceLinkReadiness';

describe('deviceLinkReadiness', () => {
  it('blocks localhost and loopback phone origins', () => {
    expect(isLoopbackDeviceLinkHost('localhost')).toBe(true);
    expect(isLoopbackDeviceLinkHost('127.0.0.1')).toBe(true);
    expect(assessDeviceLinkOriginReadiness('https://localhost:8343')).toMatchObject({
      state: 'blocked',
      qrReady: false,
    });
  });

  it('blocks non-HTTPS phone origins', () => {
    expect(assessDeviceLinkOriginReadiness('http://192.168.1.20:8300')).toMatchObject({
      state: 'blocked',
      message: 'Phone camera capture requires HTTPS.',
      qrReady: false,
    });
  });

  it('marks HTTPS LAN origins as phone and QR ready', () => {
    expect(assessDeviceLinkOriginReadiness('https://192.168.1.20:8343')).toEqual({
      state: 'ready',
      origin: 'https://192.168.1.20:8343',
      message: 'Ready for a phone on the same LAN with trusted HTTPS.',
      qrReady: true,
    });
  });

  it('prefers an operator supplied public origin over the browser fallback', () => {
    expect(resolveDeviceLinkPublicOrigin({
      overrideOrigin: 'https://192.168.1.20:8343/device-link/PAIR',
      fallbackOrigin: 'http://localhost:8300',
    })).toBe('https://192.168.1.20:8343');
  });

  it('refuses to reuse a remote workbench origin as the phone capture origin', () => {
    expect(resolveDeviceLinkPublicOrigin({
      overrideOrigin: '',
      fallbackOrigin: 'https://remote-workbench.mindscapeai.app',
      allowFallbackLoopbackOnly: true,
    })).toBe('');

    expect(resolveDeviceLinkPublicOrigin({
      overrideOrigin: '',
      fallbackOrigin: 'http://localhost:8300',
      allowFallbackLoopbackOnly: true,
    })).toBe('http://localhost:8300');
  });
});
