import assert from 'node:assert/strict';
import test from 'node:test';

import {
  nearestRankPercentile,
  runLatencyProbe,
} from './mobile-workbench-gateway-latency-probe.mjs';
import {
  createEffectivePolicyPayload,
  jsonResponse,
} from './mobile-workbench-gateway.test-support.mjs';

test('nearest-rank p95 uses sorted[ceil(0.95*n)-1]', () => {
  const values = Array.from({ length: 20 }, (_, index) => 20 - index);
  assert.equal(nearestRankPercentile(values, 0.95), 19);
  assert.equal(nearestRankPercentile([7], 0.95), 7);
  assert.equal(nearestRankPercentile([], 0.95), null);
});

test('probe uses 200 cache hits, 50 cleared warm misses, and excludes prewarm calls', async () => {
  const result = await runLatencyProbe({
    backendBase: 'http://backend.test',
    workspaceId: 'workspace-a',
    capabilityCode: 'yogacoach',
    cacheHitSamples: 200,
    warmMissSamples: 50,
    prewarm: 1,
    timeoutMs: 1000,
    fetchImpl: async (url) => {
      if (String(url).includes('/mobile-workbench-gateway/workspaces/')) {
        return jsonResponse(createEffectivePolicyPayload());
      }
      return jsonResponse({
        capability_code: 'yogacoach',
        supported: true,
        has_ui_components: true,
        host_route_template: '/workspaces/{workspaceId}/capability-ui-hosts/yogacoach',
        main_page_component_codes: ['TestWorkbenchPage'],
        request_scope_contract: 'explicit_workspace_v1',
        api_prefixes: ['/api/v1/capabilities/yogacoach'],
      });
    },
  });

  assert.equal(result.cache_hit.samples, 200);
  assert.equal(result.cache_hit.upstream_effective_policy_calls, 0);
  assert.equal(result.cache_hit.upstream_capability_support_calls, 0);
  assert.equal(result.warm_miss.samples, 50);
  assert.equal(result.warm_miss.upstream_effective_policy_calls, 50);
  assert.equal(result.warm_miss.upstream_capability_support_calls, 50);
  assert.ok(result.cache_hit.p95_ms >= 0);
  assert.ok(result.warm_miss.p95_ms >= 0);
});
