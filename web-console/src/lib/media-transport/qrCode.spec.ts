import { describe, expect, it } from 'vitest';
import { createHash } from 'node:crypto';

import { createQrCodeSvgPath } from './qrCode';

function pathSha256(path: string): string {
  return createHash('sha256').update(path).digest('hex');
}

describe('qrCode', () => {
  it('renders a deterministic SVG path for phone device links', () => {
    const url = 'https://192.168.1.20:8343/device-link/PAIR1234?workspaceId=bac7ce63-e768-454d-96f3-3a00e8e1df69&sourceMode=phone';

    const qr = createQrCodeSvgPath(url);
    const sameQr = createQrCodeSvgPath(url);

    expect(qr).toEqual(sameQr);
    expect(qr.size).toBeGreaterThanOrEqual(21);
    expect(qr.viewBoxSize).toBe(qr.size + qr.quietZone * 2);
    expect(qr.path).toContain(`M${qr.quietZone},${qr.quietZone}h1v1h-1z`);
    expect(qr.path.length).toBeGreaterThan(1000);
    expect(pathSha256(qr.path)).toBe(
      '7661048e6204560d043498bceaf78f801f1761cdbb294e84c3893642d0681303',
    );
  });

  it('keeps Reed-Solomon ECC coefficients in decoder-compatible order', () => {
    const qr = createQrCodeSvgPath('HELLO');

    expect(qr.size).toBe(21);
    expect(qr.viewBoxSize).toBe(29);
    expect(pathSha256(qr.path)).toBe(
      '7052aa69ee09db8f21ea02f5028f5e2ccb9cf900ad4a500f17254125fbe7c3bd',
    );
  });

  it('fails closed for links that exceed the supported QR versions', () => {
    expect(() => createQrCodeSvgPath(`https://example.test/${'a'.repeat(300)}`)).toThrow(
      'qr_payload_too_large_for_phone_link',
    );
  });
});
