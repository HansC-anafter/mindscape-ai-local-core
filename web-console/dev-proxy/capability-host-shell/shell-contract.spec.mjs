import { describe, expect, it } from 'vitest';

import {
  createCapabilityHostConfig,
  isCapabilityHostBootstrapRequest,
  parseCapabilityHostBootstrapRoute,
} from './shell-contract.mjs';

describe('capability host shell contract', () => {
  it('parses the workspace capability host route into a stable config shape', () => {
    const route = parseCapabilityHostBootstrapRoute(
      '/workspaces/ws%2Fone/capability-ui-hosts/demo_capability/path%20one/path%2Ftwo?component=DemoPage',
    );

    expect(route).toEqual({
      workspaceId: 'ws/one',
      capabilityCode: 'demo_capability',
      surfacePath: ['path one', 'path/two'],
    });
    expect(createCapabilityHostConfig(route)).toEqual({
      workspaceId: 'ws/one',
      capabilityCode: 'demo_capability',
      surfacePath: ['path one', 'path/two'],
    });
  });

  it('keeps non-matching routes out of the bootstrap fast path', () => {
    expect(isCapabilityHostBootstrapRequest('POST', '/workspaces/ws-1/capability-ui-hosts/ig')).toBe(false);
    expect(isCapabilityHostBootstrapRequest('GET', '/workspaces/ws-1/capabilities/ig')).toBe(false);
    expect(parseCapabilityHostBootstrapRoute('not a valid url')).toBe(null);
  });
});
