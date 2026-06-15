import { describe, expect, it } from 'vitest';

import {
  isAllowedDeviceLinkHttpsPath,
  isDeviceLinkHttpsReadinessPath,
  isLoopbackDeviceLinkPublicOrigin,
  resolveDeviceLinkHttpsConfig,
} from './device-link-https.mjs';

describe('device-link HTTPS dev proxy', () => {
  it('stays disabled unless explicitly enabled', () => {
    expect(resolveDeviceLinkHttpsConfig({})).toMatchObject({
      enabled: false,
      reason: 'disabled',
    });
  });

  it('requires a trusted HTTPS public origin and certificate paths when enabled', () => {
    expect(
      resolveDeviceLinkHttpsConfig({
        DEVICE_LINK_HTTPS_ENABLED: '1',
        DEVICE_LINK_PUBLIC_ORIGIN: 'http://phone.test:8343',
      }),
    ).toMatchObject({
      enabled: false,
      reason: 'invalid_config',
      errors: expect.arrayContaining([
        'DEVICE_LINK_PUBLIC_ORIGIN_must_use_https',
        'DEVICE_LINK_HTTPS_CERT_FILE_required',
        'DEVICE_LINK_HTTPS_KEY_FILE_required',
      ]),
    });
  });

  it('rejects localhost and loopback public origins for phone QR flows', () => {
    expect(isLoopbackDeviceLinkPublicOrigin('https://localhost:8343')).toBe(true);
    expect(isLoopbackDeviceLinkPublicOrigin('https://127.0.0.1:8343')).toBe(true);
    expect(isLoopbackDeviceLinkPublicOrigin('https://[::1]:8343')).toBe(true);
    expect(isLoopbackDeviceLinkPublicOrigin('https://192.168.1.20:8343')).toBe(false);
    expect(
      resolveDeviceLinkHttpsConfig({
        DEVICE_LINK_HTTPS_ENABLED: '1',
        DEVICE_LINK_PUBLIC_ORIGIN: 'https://localhost:8343',
        DEVICE_LINK_HTTPS_CERT_FILE: '/run/cert.pem',
        DEVICE_LINK_HTTPS_KEY_FILE: '/run/key.pem',
      }),
    ).toMatchObject({
      enabled: false,
      reason: 'invalid_config',
      errors: expect.arrayContaining(['DEVICE_LINK_PUBLIC_ORIGIN_must_be_lan_reachable']),
    });
  });

  it('resolves enabled config only with HTTPS origin and cert/key files', () => {
    expect(
      resolveDeviceLinkHttpsConfig({
        DEVICE_LINK_HTTPS_ENABLED: '1',
        DEVICE_LINK_PUBLIC_ORIGIN: 'https://phone.test:8343/',
        DEVICE_LINK_HTTPS_CERT_FILE: '/run/cert.pem',
        DEVICE_LINK_HTTPS_KEY_FILE: '/run/key.pem',
        DEVICE_LINK_HTTPS_PORT: '8343',
      }),
    ).toMatchObject({
      enabled: true,
      reason: 'enabled',
      publicOrigin: 'https://phone.test:8343',
      certFile: '/run/cert.pem',
      keyFile: '/run/key.pem',
      port: 8343,
    });
  });

  it('allows only device-link, Next asset, and bounded signaling paths through the HTTPS proxy', () => {
    expect(isAllowedDeviceLinkHttpsPath('/device-link/PAIR1234')).toBe(true);
    expect(isAllowedDeviceLinkHttpsPath('/device-link/health')).toBe(true);
    expect(isAllowedDeviceLinkHttpsPath('/_next/static/chunk.js')).toBe(true);
    expect(isAllowedDeviceLinkHttpsPath(
      '/api/v1/workspaces/ws/device-bindings/PAIR1234/control',
    )).toBe(true);
    expect(isAllowedDeviceLinkHttpsPath(
      '/api/v1/workspaces/ws/device-bindings/session_1/media-sessions/session_1/signal',
    )).toBe(true);
    expect(isAllowedDeviceLinkHttpsPath('/api/v1/workspaces/ws')).toBe(false);
    expect(isAllowedDeviceLinkHttpsPath('/api/v1/admin/secret')).toBe(false);
    expect(isAllowedDeviceLinkHttpsPath('/workspaces/ws')).toBe(false);
  });

  it('keeps HTTPS readiness on a local proxy fast path', () => {
    expect(isDeviceLinkHttpsReadinessPath('/device-link/health')).toBe(true);
    expect(isDeviceLinkHttpsReadinessPath('/device-link/__test__')).toBe(true);
    expect(isDeviceLinkHttpsReadinessPath('/device-link/PAIR1234')).toBe(false);
  });
});
