import { describe, expect, it } from 'vitest';

import { BACKEND_LIVENESS_PATH, buildBackendLivenessUrl } from './settingsApi';

describe('settings API backend liveness probe path', () => {
  it('uses backend /healthz for URL validation instead of readiness /health', () => {
    expect(BACKEND_LIVENESS_PATH).toBe('/healthz');
    expect(buildBackendLivenessUrl('http://localhost:8200')).toBe('http://localhost:8200/healthz');
    expect(buildBackendLivenessUrl('http://localhost:8200/')).toBe('http://localhost:8200/healthz');
  });
});
