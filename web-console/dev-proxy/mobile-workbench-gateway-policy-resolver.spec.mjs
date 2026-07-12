import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createMobileWorkbenchGatewayPolicyResolver,
} from './mobile-workbench-gateway-policy-resolver.mjs';
import {
  createEffectivePolicyPayload,
  jsonResponse,
} from './mobile-workbench-gateway.test-support.mjs';

function supportPayload(capabilityCode) {
  return {
    capability_code: capabilityCode,
    supported: true,
    has_ui_components: true,
    host_route_template: `/workspaces/{workspaceId}/capability-ui-hosts/${capabilityCode}`,
    main_page_component_codes: ['TestWorkbenchPage'],
    request_scope_contract: 'explicit_workspace_v1',
    api_prefixes: [`/api/v1/capabilities/${capabilityCode}`],
  };
}

function createFetchMock(callLog, overrides = {}) {
  return async (url, options = {}) => {
    callLog.push(String(url));
    if (overrides.fetch) {
      const overridden = await overrides.fetch(String(url), options, callLog.length);
      if (overridden) return overridden;
    }
    const workspaceMatch = /\/workspaces\/([^/]+)\/policy$/.exec(String(url));
    if (workspaceMatch) {
      return jsonResponse(createEffectivePolicyPayload({
        workspaceId: decodeURIComponent(workspaceMatch[1]),
        capabilityCodes: ['yogacoach', 'ig'],
      }));
    }
    const capabilityMatch = /\/installed-capabilities\/([^/]+)\/mobile-workbench-gateway-support$/.exec(String(url));
    return jsonResponse(supportPayload(decodeURIComponent(capabilityMatch[1])));
  };
}

function createResolver(fetchImpl, options = {}) {
  return createMobileWorkbenchGatewayPolicyResolver({
    buildInternalApiUrl: (path) => `http://resolver.test${path}`,
    fetchImpl,
    ...options,
  });
}

test('effective policy and capability support use split cache keys and TTLs', async () => {
  const calls = [];
  let nowValue = 0;
  const resolver = createResolver(createFetchMock(calls), { now: () => nowValue });

  await resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' });
  await resolver({ workspaceId: 'workspace-a', capabilityCode: 'ig' });
  assert.equal(calls.filter((url) => url.includes('/workspaces/workspace-a/policy')).length, 1);
  assert.equal(calls.filter((url) => url.includes('/mobile-workbench-gateway-support')).length, 2);
  assert.deepEqual(resolver.stats(), {
    effectivePolicyCacheEntries: 1,
    capabilitySupportCacheEntries: 2,
    upstreamEffectivePolicyCalls: 1,
    upstreamCapabilitySupportCalls: 2,
    upstreamInFlight: 0,
    upstreamRejected: 0,
    maxUpstreamInFlight: 16,
    upstreamEffectivePolicyCalls: 1,
    upstreamCapabilitySupportCalls: 2,
  });

  nowValue = 15_001;
  await resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' });
  assert.equal(calls.filter((url) => url.includes('/workspaces/workspace-a/policy')).length, 2);
  assert.equal(calls.filter((url) => url.includes('/yogacoach/mobile-workbench-gateway-support')).length, 1);

  nowValue = 60_001;
  await resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' });
  assert.equal(calls.filter((url) => url.includes('/yogacoach/mobile-workbench-gateway-support')).length, 2);
});

test('same-key concurrent reads are singleflight', async () => {
  const calls = [];
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const fetchImpl = createFetchMock(calls, {
    fetch: async (url) => {
      if (url.includes('/workspaces/workspace-a/policy')) {
        await gate;
      }
      return null;
    },
  });
  const resolver = createResolver(fetchImpl);
  const reads = Array.from({ length: 20 }, () => resolver({
    workspaceId: 'workspace-a',
    capabilityCode: 'yogacoach',
  }));
  await new Promise((resolve) => setImmediate(resolve));
  release();
  await Promise.all(reads);
  assert.equal(calls.filter((url) => url.includes('/workspaces/workspace-a/policy')).length, 1);
  assert.equal(calls.filter((url) => url.includes('/mobile-workbench-gateway-support')).length, 1);
});

test('both caches remain bounded at 256 entries', async () => {
  const calls = [];
  const resolver = createResolver(createFetchMock(calls));
  for (let index = 0; index < 257; index += 1) {
    await resolver({
      workspaceId: `workspace-${index}`,
      capabilityCode: `capability_${index}`,
    });
  }
  assert.deepEqual(resolver.stats(), {
    effectivePolicyCacheEntries: 256,
    capabilitySupportCacheEntries: 256,
    upstreamEffectivePolicyCalls: 257,
    upstreamCapabilitySupportCalls: 257,
    upstreamInFlight: 0,
    upstreamRejected: 0,
    maxUpstreamInFlight: 16,
    upstreamEffectivePolicyCalls: 257,
    upstreamCapabilitySupportCalls: 257,
  });
});

test('timeout is absolute, has no retry, and evicts the failed cache entry', async () => {
  let calls = 0;
  const resolver = createResolver(async (_url, { signal }) => {
    calls += 1;
    return await new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => {
        const error = new Error('aborted');
        error.name = 'AbortError';
        reject(error);
      });
    });
  }, { timeoutMs: 10 });
  await assert.rejects(
    resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' }),
    /mobile_workbench_policy_timeout/,
  );
  assert.equal(calls, 2);
  assert.deepEqual(resolver.stats(), {
    effectivePolicyCacheEntries: 0,
    capabilitySupportCacheEntries: 0,
    upstreamEffectivePolicyCalls: 1,
    upstreamCapabilitySupportCalls: 1,
    upstreamInFlight: 0,
    upstreamRejected: 0,
    maxUpstreamInFlight: 16,
    upstreamEffectivePolicyCalls: 1,
    upstreamCapabilitySupportCalls: 1,
  });
});

test('HTTP errors are evicted and the next explicit request can retry', async () => {
  const calls = [];
  let policyCalls = 0;
  const resolver = createResolver(createFetchMock(calls, {
    fetch: async (url) => {
      if (url.includes('/workspaces/workspace-a/policy')) {
        policyCalls += 1;
        if (policyCalls === 1) {
          return jsonResponse({ error: 'unavailable' }, { status: 503 });
        }
      }
      return null;
    },
  }));
  await assert.rejects(
    resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' }),
    /mobile_workbench_upstream_request_failed:503/,
  );
  const result = await resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' });
  assert.equal(result.capabilityAllowed, true);
  assert.equal(policyCalls, 2);
});

test('oversized and malformed effective/support payloads fail closed', async (t) => {
  await t.test('oversized effective policy', async () => {
    const resolver = createResolver(async (url) => {
      if (String(url).includes('/workspaces/')) {
        return jsonResponse({
          ...createEffectivePolicyPayload(),
          oversized: 'x'.repeat(33 * 1024),
        });
      }
      return jsonResponse(supportPayload('yogacoach'));
    });
    await assert.rejects(
      resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' }),
      /payload_too_large/,
    );
  });

  await t.test('oversized support metadata', async () => {
    const resolver = createResolver(async (url) => {
      if (String(url).includes('/workspaces/')) {
        return jsonResponse(createEffectivePolicyPayload());
      }
      return jsonResponse({ ...supportPayload('yogacoach'), oversized: 'x'.repeat(2048) });
    });
    await assert.rejects(
      resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' }),
      /payload_too_large/,
    );
  });

  await t.test('projection mismatch', async () => {
    const resolver = createResolver(async (url) => {
      if (String(url).includes('/workspaces/')) {
        return jsonResponse(createEffectivePolicyPayload({ effectivePrincipals: [] }));
      }
      return jsonResponse(supportPayload('yogacoach'));
    });
    await assert.rejects(
      resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' }),
      /effective_principal_projection_mismatch/,
    );
  });

  await t.test('support identity and canonical host route mismatch', async () => {
    for (const support of [
      { ...supportPayload('other'), capability_code: 'other' },
      { ...supportPayload('yogacoach'), host_route_template: '/custom/{workspaceId}' },
    ]) {
      const resolver = createResolver(async (url) => {
        if (String(url).includes('/workspaces/')) {
          return jsonResponse(createEffectivePolicyPayload());
        }
        return jsonResponse(support);
      });
      await assert.rejects(
        resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' }),
        /capability_support_(?:identity|projection)_mismatch|noncanonical_host_route_template/,
      );
    }
  });

  await t.test('unowned API prefix is malformed', async () => {
    const resolver = createResolver(async (url) => {
      if (String(url).includes('/workspaces/')) {
        return jsonResponse(createEffectivePolicyPayload());
      }
      return jsonResponse({
        ...supportPayload('yogacoach'),
        api_prefixes: ['/api/v1'],
      });
    });
    await assert.rejects(
      resolver({ workspaceId: 'workspace-a', capabilityCode: 'yogacoach' }),
      /unowned_capability_api_prefix/,
    );
  });
});
