import assert from 'node:assert/strict';
import test from 'node:test';

import { createMobileWorkbenchGatewayPolicyResolver } from './mobile-workbench-gateway-policy-resolver.mjs';
import { authorizeRemoteWorkbenchRequest } from './mobile-workbench-gateway.mjs';
import {
  createEffectivePolicyPayload,
  createGatewayConfig,
  createSignedAccessJwt,
  createTestVerifier,
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

function createResolver(fetchImpl, options = {}) {
  return createMobileWorkbenchGatewayPolicyResolver({
    buildInternalApiUrl: (path) => `http://backend.test${path}`,
    fetchImpl,
    ...options,
  });
}

test('membership and capability allowlist are proven before support metadata is loaded', async () => {
  const fetchImpl = async (url) => {
    const workspaceMatch = /\/workspaces\/([^/]+)\/policy$/.exec(String(url));
    if (workspaceMatch) {
      return jsonResponse(createEffectivePolicyPayload({
        workspaceId: decodeURIComponent(workspaceMatch[1]),
        capabilityCodes: ['yogacoach'],
      }));
    }
    const capabilityMatch = /\/installed-capabilities\/([^/]+)\/mobile-workbench-gateway-support$/.exec(String(url));
    return jsonResponse(supportPayload(decodeURIComponent(capabilityMatch[1])));
  };
  const resolver = createResolver(fetchImpl);
  const request = (capabilityCode, claims = {}) => authorizeRemoteWorkbenchRequest(
    `/workspaces/workspace-a/capability-ui-hosts/${capabilityCode}`,
    {
      host: 'remote-workbench.mindscapeai.app',
      'Cf-Access-Jwt-Assertion': createSignedAccessJwt({ claims }),
    },
    createGatewayConfig(),
    {
      verifyAccessToken: createTestVerifier(),
      resolveWorkspaceCapabilityPolicy: resolver,
    },
  );

  const outsider = await request('yogacoach', {
    sub: 'subject-outsider',
    email: 'outsider@example.com',
  });
  assert.equal(outsider.reason_code, 'workspace_membership_required');
  assert.equal(resolver.stats().upstreamCapabilitySupportCalls, 0);

  const disallowed = await request('browser_capture');
  assert.equal(disallowed.reason_code, 'capability_not_allowed');
  assert.equal(resolver.stats().upstreamCapabilitySupportCalls, 0);

  const allowed = await request('yogacoach');
  assert.equal(allowed.allowed, true);
  assert.equal(resolver.stats().upstreamCapabilitySupportCalls, 1);
});

test('distinct-key concurrency fails closed instead of queueing unbounded upstream reads', async () => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  let fetchCalls = 0;
  const resolver = createResolver(async (url) => {
    fetchCalls += 1;
    await gate;
    const workspaceMatch = /\/workspaces\/([^/]+)\/policy$/.exec(String(url));
    return jsonResponse(createEffectivePolicyPayload({
      workspaceId: decodeURIComponent(workspaceMatch[1]),
    }));
  }, { maxUpstreamInFlight: 2 });

  const reads = Array.from({ length: 10 }, (_, index) => (
    resolver.resolveEffectivePolicy(`workspace-${index}`)
  ));
  const settledPromise = Promise.allSettled(reads);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(fetchCalls, 2);
  assert.equal(resolver.stats().upstreamInFlight, 2);
  assert.equal(resolver.stats().upstreamRejected, 8);

  release();
  const settled = await settledPromise;
  assert.equal(settled.filter((result) => result.status === 'fulfilled').length, 2);
  assert.equal(settled.filter((result) => result.status === 'rejected').length, 8);
  assert.equal(resolver.stats().upstreamInFlight, 0);
});
