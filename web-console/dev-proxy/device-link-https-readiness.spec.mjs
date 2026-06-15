import { describe, expect, it, vi } from 'vitest';

import {
  buildDeviceLinkComposeCommand,
  buildDeviceLinkHttpsReadinessReport,
  extractSubjectAltNameTokens,
  normalizeDeviceLinkPublicOrigin,
  shellQuote,
  subjectAltNameMatchesHost,
} from './device-link-https-readiness.mjs';

const readyEnv = {
  DEVICE_LINK_PUBLIC_ORIGIN: 'https://192.168.1.20:8343',
  DEVICE_LINK_HTTPS_CERT_HOST_FILE: '/tmp/device-link-cert.pem',
  DEVICE_LINK_HTTPS_KEY_HOST_FILE: '/tmp/device-link-key.pem',
  DEVICE_LINK_HTTPS_HOST_PORT: '8343',
};

function existingFileInfo() {
  return { exists: true, size: 64 };
}

describe('device-link HTTPS readiness', () => {
  it('normalizes only LAN HTTPS origins without paths', () => {
    expect(normalizeDeviceLinkPublicOrigin('https://192.168.1.20:8343/')).toMatchObject({
      ok: true,
      origin: 'https://192.168.1.20:8343',
      hostname: '192.168.1.20',
      port: 8343,
    });
    expect(normalizeDeviceLinkPublicOrigin('http://192.168.1.20:8343')).toMatchObject({
      ok: false,
      error: 'DEVICE_LINK_PUBLIC_ORIGIN_must_use_https',
    });
    expect(normalizeDeviceLinkPublicOrigin('https://localhost:8343')).toMatchObject({
      ok: false,
      error: 'DEVICE_LINK_PUBLIC_ORIGIN_must_be_lan_reachable',
    });
    expect(normalizeDeviceLinkPublicOrigin('https://192.168.1.20:8343/device-link/PAIR')).toMatchObject({
      ok: false,
      error: 'DEVICE_LINK_PUBLIC_ORIGIN_must_not_include_path',
    });
  });

  it('matches certificate SAN entries by IP or DNS host type', () => {
    const sanText = 'X509v3 Subject Alternative Name:\n    DNS:phone.test, IP Address:192.168.1.20';
    expect(extractSubjectAltNameTokens(sanText)).toEqual(['DNS:phone.test', 'IP Address:192.168.1.20']);
    expect(subjectAltNameMatchesHost(sanText, '192.168.1.20')).toBe(true);
    expect(subjectAltNameMatchesHost(sanText, 'phone.test')).toBe(true);
    expect(subjectAltNameMatchesHost(sanText, '192.168.1.21')).toBe(false);
    expect(subjectAltNameMatchesHost(sanText, 'other.test')).toBe(false);
  });

  it('blocks dry runs without env or certificate files and never checks health', async () => {
    const checkHealth = vi.fn();
    const report = await buildDeviceLinkHttpsReadinessReport({
      env: {},
      getFileInfo: () => ({ exists: false, size: 0 }),
      readCertificateSubjectAltName: () => '',
      checkHealth,
    });
    expect(report.status).toBe('blocked_device_link_https_readiness');
    expect(report.ready_for_phone_smoke).toBe(false);
    expect(report.gates.map((item) => [item.name, item.status])).toEqual([
      ['public_origin', 'blocked'],
      ['certificate_files', 'blocked'],
      ['certificate_san', 'blocked'],
      ['device_link_health', 'blocked'],
    ]);
    expect(checkHealth).not.toHaveBeenCalled();
    expect(report.resource_policy).toEqual({
      db_migration: false,
      worker_queue: false,
      pgbouncer_pool: false,
      ux_polling: false,
      raw_media_persist: false,
    });
  });

  it('marks the proxy start path ready when origin, files, and SAN pass but health is down', async () => {
    const report = await buildDeviceLinkHttpsReadinessReport({
      env: readyEnv,
      getFileInfo: existingFileInfo,
      readCertificateSubjectAltName: () => 'X509v3 Subject Alternative Name:\n    IP Address:192.168.1.20',
      checkHealth: async () => ({ ok: false, error: 'ECONNREFUSED' }),
    });
    expect(report.status).toBe('blocked_device_link_https_readiness');
    expect(report.ready_for_phone_smoke).toBe(false);
    expect(report.ready_to_start_proxy).toBe(true);
    expect(report.gates.find((item) => item.name === 'device_link_health')).toMatchObject({
      status: 'blocked',
      error: 'ECONNREFUSED',
    });
  });

  it('passes only when the LAN HTTPS health endpoint returns device-link service identity', async () => {
    const report = await buildDeviceLinkHttpsReadinessReport({
      env: readyEnv,
      getFileInfo: existingFileInfo,
      readCertificateSubjectAltName: () => 'X509v3 Subject Alternative Name:\n    IP Address:192.168.1.20',
      checkHealth: async () => ({ ok: true, statusCode: 200, service: 'device-link-https' }),
    });
    expect(report.status).toBe('ready_for_phone_smoke');
    expect(report.ready_for_phone_smoke).toBe(true);
    expect(report.ready_to_start_proxy).toBe(false);
    expect(report.gates.every((item) => item.status === 'passed')).toBe(true);
  });

  it('prints one docker compose command with quoted operator inputs', () => {
    expect(shellQuote("/tmp/cert's.pem")).toBe("'/tmp/cert'\\''s.pem'");
    expect(
      buildDeviceLinkComposeCommand({
        publicOrigin: 'https://192.168.1.20:8343',
        certHostFile: '/tmp/cert.pem',
        keyHostFile: '/tmp/key.pem',
        hostPort: 8343,
      }),
    ).toBe(
      "DEVICE_LINK_PUBLIC_ORIGIN='https://192.168.1.20:8343' DEVICE_LINK_HTTPS_CERT_HOST_FILE='/tmp/cert.pem' DEVICE_LINK_HTTPS_KEY_HOST_FILE='/tmp/key.pem' DEVICE_LINK_HTTPS_HOST_PORT='8343' docker compose -f docker-compose.yml -f docker-compose.device-link-https.yml up -d frontend",
    );
  });
});
