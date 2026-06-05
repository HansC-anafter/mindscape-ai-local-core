import { describe, expect, it } from 'vitest';

import {
  isAllowedDeviceLinkHttpsPath,
  isDeviceLinkHttpsReadinessPath,
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

  it('allows only device-link, Next asset, and API paths through the HTTPS proxy', () => {
    expect(isAllowedDeviceLinkHttpsPath('/device-link/PAIR1234')).toBe(true);
    expect(isAllowedDeviceLinkHttpsPath('/device-link/health')).toBe(true);
    expect(isAllowedDeviceLinkHttpsPath('/_next/static/chunk.js')).toBe(true);
    expect(isAllowedDeviceLinkHttpsPath('/api/v1/workspaces/ws')).toBe(true);
    expect(isAllowedDeviceLinkHttpsPath('/workspaces/ws')).toBe(false);
  });

  it('keeps HTTPS readiness on a local proxy fast path', () => {
    expect(isDeviceLinkHttpsReadinessPath('/device-link/health')).toBe(true);
    expect(isDeviceLinkHttpsReadinessPath('/device-link/__test__')).toBe(true);
    expect(isDeviceLinkHttpsReadinessPath('/device-link/PAIR1234')).toBe(false);
  });
});
