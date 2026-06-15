import { describe, expect, it, vi } from 'vitest';

import {
  createMobileWorkbenchGatewayPolicyResolver,
} from './mobile-workbench-gateway-policy-resolver.mjs';

describe('mobile workbench gateway policy resolver', () => {
  it('caches workspace-capability policy reads for 15 seconds', async () => {
    let nowValue = 0;
    const fetchMock = vi.fn(async (url) => {
      if (String(url).includes('/mobile-workbench-gateway/workspaces/ws-1/policy')) {
        return {
          ok: true,
          json: async () => ({
            allowed_capability_codes: ['yogacoach'],
          }),
        };
      }
      return {
        ok: true,
        json: async () => ({
          supported: true,
          host_route_template: '/workspaces/{workspaceId}/capability-ui-hosts/yogacoach',
          api_prefixes: ['/api/v1/capabilities/yogacoach'],
        }),
      };
    });

    const resolver = createMobileWorkbenchGatewayPolicyResolver({
      buildInternalApiUrl: (path) => `http://resolver.test${path}`,
      fetchImpl: fetchMock,
      now: () => nowValue,
    });

    const first = await resolver({
      workspaceId: 'ws-1',
      capabilityCode: 'yogacoach',
    });
    const second = await resolver({
      workspaceId: 'ws-1',
      capabilityCode: 'yogacoach',
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(first.capabilityAllowed).toBe(true);
    expect(second.capabilityAllowed).toBe(true);

    nowValue = 15_001;
    await resolver({
      workspaceId: 'ws-1',
      capabilityCode: 'yogacoach',
    });

    expect(fetchMock).toHaveBeenCalledTimes(4);
  });
});
