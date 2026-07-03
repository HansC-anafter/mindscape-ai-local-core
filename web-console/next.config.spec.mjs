import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const nextConfig = require('./next.config.js');

describe('next config capability host routing', () => {
  it('keeps workspace capability hosts on the app route so workspace and pack rails stay mounted', async () => {
    const rewrites = await nextConfig.rewrites();

    expect(rewrites.beforeFiles).not.toContainEqual({
      source: '/workspaces/:workspaceId/capability-ui-hosts/:capabilityCode',
      destination: '/capability-ui-host-runtime/:workspaceId/:capabilityCode',
    });
    expect(rewrites.beforeFiles).not.toContainEqual({
      source: '/workspaces/:workspaceId/capability-ui-hosts/:capabilityCode/:surfacePath*',
      destination: '/capability-ui-host-runtime/:workspaceId/:capabilityCode/:surfacePath*',
    });
  });

  it('redirects top-level capability URLs to the default workspace workbench host', async () => {
    const redirects = await nextConfig.redirects();

    expect(redirects).toContainEqual({
      source: '/capabilities/public_persona_studio',
      destination: '/workspaces/default/capability-ui-hosts/public_persona_studio',
      permanent: false,
    });
    expect(redirects).toContainEqual({
      source: '/capabilities/public-persona-studio',
      destination: '/workspaces/default/capability-ui-hosts/public_persona_studio',
      permanent: false,
    });
  });
});
