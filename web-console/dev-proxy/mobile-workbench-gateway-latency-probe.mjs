import { performance } from 'node:perf_hooks';

import {
  createMobileWorkbenchGatewayPolicyResolver,
} from './mobile-workbench-gateway-policy-resolver.mjs';

function positiveInteger(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : fallback;
}

export function nearestRankPercentile(values, percentile) {
  if (!Array.isArray(values) || values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const rank = Math.max(1, Math.ceil(Number(percentile) * sorted.length));
  return sorted[Math.min(sorted.length - 1, rank - 1)];
}

function roundDuration(value) {
  return Math.round(Number(value) * 1000) / 1000;
}

function classifyFetch(url, counters) {
  if (String(url).includes('/mobile-workbench-gateway/workspaces/')) {
    counters.effectivePolicyCalls += 1;
  } else if (String(url).includes('/mobile-workbench-gateway-support')) {
    counters.capabilitySupportCalls += 1;
  }
}

async function sampleResolver(resolver, input, samples, clearBeforeEach) {
  const durations = [];
  for (let index = 0; index < samples; index += 1) {
    if (clearBeforeEach) {
      resolver.clear();
    }
    const startedAt = performance.now();
    await resolver(input);
    durations.push(roundDuration(performance.now() - startedAt));
  }
  return durations;
}

export async function runLatencyProbe({
  backendBase,
  workspaceId,
  capabilityCode,
  cacheHitSamples = 200,
  warmMissSamples = 50,
  prewarm = 1,
  timeoutMs = 1000,
  fetchImpl = globalThis.fetch,
} = {}) {
  const normalizedBackendBase = String(backendBase || '').trim().replace(/\/+$/, '');
  const normalizedWorkspaceId = String(workspaceId || '').trim();
  const normalizedCapabilityCode = String(capabilityCode || '').trim().toLowerCase();
  if (!normalizedBackendBase || !normalizedWorkspaceId || !normalizedCapabilityCode) {
    throw new Error('backendBase, workspaceId, and capabilityCode are required');
  }
  const counters = { effectivePolicyCalls: 0, capabilitySupportCalls: 0 };
  const countedFetch = async (url, options) => {
    classifyFetch(url, counters);
    return await fetchImpl(url, options);
  };
  const resolver = createMobileWorkbenchGatewayPolicyResolver({
    buildInternalApiUrl: (path) => `${normalizedBackendBase}${path}`,
    fetchImpl: countedFetch,
    timeoutMs: positiveInteger(timeoutMs, 1000),
  });
  const input = {
    workspaceId: normalizedWorkspaceId,
    capabilityCode: normalizedCapabilityCode,
  };

  for (let index = 0; index < positiveInteger(prewarm, 1); index += 1) {
    resolver.clear();
    await resolver(input);
  }
  counters.effectivePolicyCalls = 0;
  counters.capabilitySupportCalls = 0;
  const cacheHitDurations = await sampleResolver(
    resolver,
    input,
    positiveInteger(cacheHitSamples, 200),
    false,
  );
  const cacheHitCalls = { ...counters };

  counters.effectivePolicyCalls = 0;
  counters.capabilitySupportCalls = 0;
  const warmMissDurations = await sampleResolver(
    resolver,
    input,
    positiveInteger(warmMissSamples, 50),
    true,
  );
  const warmMissCalls = { ...counters };

  return {
    workspace_id: normalizedWorkspaceId,
    capability_code: normalizedCapabilityCode,
    timeout_ms: positiveInteger(timeoutMs, 1000),
    prewarm_count: positiveInteger(prewarm, 1),
    cache_hit: {
      samples: cacheHitDurations.length,
      p95_ms: nearestRankPercentile(cacheHitDurations, 0.95),
      upstream_effective_policy_calls: cacheHitCalls.effectivePolicyCalls,
      upstream_capability_support_calls: cacheHitCalls.capabilitySupportCalls,
    },
    warm_miss: {
      samples: warmMissDurations.length,
      p95_ms: nearestRankPercentile(warmMissDurations, 0.95),
      upstream_effective_policy_calls: warmMissCalls.effectivePolicyCalls,
      upstream_capability_support_calls: warmMissCalls.capabilitySupportCalls,
    },
  };
}

function parseArguments(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith('--') || value === undefined) {
      throw new Error(`invalid argument: ${key || ''}`);
    }
    values[key.slice(2)] = value;
  }
  return values;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = parseArguments(process.argv.slice(2));
  runLatencyProbe({
    backendBase: args['backend-base'],
    workspaceId: args['workspace-id'],
    capabilityCode: args.capability,
    cacheHitSamples: args['cache-hit-samples'],
    warmMissSamples: args['warm-miss-samples'],
    prewarm: args.prewarm,
    timeoutMs: args['timeout-ms'],
  }).then((result) => {
    process.stdout.write(`${JSON.stringify(result)}\n`);
  }).catch((error) => {
    process.stderr.write(`${error?.message || 'latency probe failed'}\n`);
    process.exitCode = 1;
  });
}
