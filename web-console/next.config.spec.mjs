import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const nextConfig = require('./next.config.js');

describe('next config capability host routing', () => {
  it('rewrites workspace capability hosts to the lightweight runtime route before app files', async () => {
    const rewrites = await nextConfig.rewrites();

    expect(rewrites.beforeFiles).toContainEqual({
      source: '/workspaces/:workspaceId/capability-ui-hosts/:capabilityCode/:surfacePath*',
      destination: '/capability-ui-host-runtime/:workspaceId/:capabilityCode/:surfacePath*',
    });
  });
});
