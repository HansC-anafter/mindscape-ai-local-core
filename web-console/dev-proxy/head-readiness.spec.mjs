import { describe, expect, it } from 'vitest';

import { isFrontendDocumentHeadReadinessRequest } from './head-readiness.mjs';

describe('frontend document HEAD readiness', () => {
  it('handles document HEAD probes without taking over API routes', () => {
    expect(isFrontendDocumentHeadReadinessRequest('HEAD', '/')).toBe(true);
    expect(
      isFrontendDocumentHeadReadinessRequest(
        'HEAD',
        '/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69',
      ),
    ).toBe(true);
    expect(isFrontendDocumentHeadReadinessRequest('HEAD', '/device-link/PAIR1234')).toBe(true);
    expect(isFrontendDocumentHeadReadinessRequest('HEAD', '/api/healthz')).toBe(false);
    expect(isFrontendDocumentHeadReadinessRequest('GET', '/workspaces/ws')).toBe(false);
  });
});
