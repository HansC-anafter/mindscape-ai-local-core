import {
  createCapabilityGatewayPathRules,
} from './mobile-workbench-gateway-capability-rules.mjs';
import {
  MAX_POLICY_CACHE_ENTRIES,
  MAX_SUPPORT_CACHE_ENTRIES,
  POLICY_TTL_MS,
  SUPPORT_TTL_MS,
  UPSTREAM_TIMEOUT_MS,
  WORKSPACE_EFFECTIVE_POLICY_PATH_PREFIX,
} from './mobile-workbench-gateway/constants.mjs';
import {
  POLICY_PAYLOAD_LIMITS,
  normalizeEffectiveWorkspacePolicy,
  readBoundedJsonResponse,
} from './mobile-workbench-gateway/policy-contract.mjs';
import {
  normalizeCapabilitySupport,
} from './mobile-workbench-gateway/capability-support-contract.mjs';

function normalizeWorkspaceId(value) {
  const normalized = String(value || '').trim();
  if (!normalized || normalized.length > 128) {
    throw new Error('invalid_workspace_id');
  }
  return normalized;
}

function normalizeCapabilityCode(value) {
  const normalized = String(value || '').trim().toLowerCase();
  if (!normalized || !/^[a-z0-9][a-z0-9_-]*$/.test(normalized)) {
    throw new Error('invalid_capability_code');
  }
  return normalized;
}

function touchCacheEntry(cache, key, entry) {
  cache.delete(key);
  cache.set(key, entry);
}

function setBoundedCacheEntry(cache, key, entry, maxEntries) {
  if (!cache.has(key) && cache.size >= maxEntries) {
    cache.delete(cache.keys().next().value);
  }
  cache.set(key, entry);
}

async function fetchBoundedJson(fetchImpl, url, maxBytes, timeoutMs) {
  const abortController = new AbortController();
  const timeout = setTimeout(() => abortController.abort(), timeoutMs);
  try {
    const response = await fetchImpl(url, {
      method: 'GET',
      headers: { accept: 'application/json' },
      signal: abortController.signal,
    });
    return await readBoundedJsonResponse(response, maxBytes);
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error('mobile_workbench_policy_timeout');
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export function createMobileWorkbenchGatewayPolicyResolver({
  buildInternalApiUrl,
  fetchImpl = globalThis.fetch,
  now = () => Date.now(),
  timeoutMs = UPSTREAM_TIMEOUT_MS,
  policyTtlMs = POLICY_TTL_MS,
  supportTtlMs = SUPPORT_TTL_MS,
  maxPolicyEntries = MAX_POLICY_CACHE_ENTRIES,
  maxSupportEntries = MAX_SUPPORT_CACHE_ENTRIES,
  maxUpstreamInFlight = 16,
} = {}) {
  if (typeof buildInternalApiUrl !== 'function') {
    throw new Error('buildInternalApiUrl is required');
  }
  if (typeof fetchImpl !== 'function') {
    throw new Error('fetchImpl is required');
  }

  const effectivePolicyCache = new Map();
  const capabilitySupportCache = new Map();
  const upstreamCalls = { effectivePolicy: 0, capabilitySupport: 0 };
  const upstreamLimit = Number.isSafeInteger(maxUpstreamInFlight) && maxUpstreamInFlight > 0
    ? maxUpstreamInFlight
    : 16;
  let upstreamInFlight = 0;
  let upstreamRejected = 0;

  function incrementUpstreamCall(key) {
    upstreamCalls[key] = Math.min(
      Number.MAX_SAFE_INTEGER,
      upstreamCalls[key] + 1,
    );
  }

  async function runWithUpstreamSlot(loader) {
    if (upstreamInFlight >= upstreamLimit) {
      upstreamRejected = Math.min(Number.MAX_SAFE_INTEGER, upstreamRejected + 1);
      throw new Error('mobile_workbench_policy_upstream_saturated');
    }
    upstreamInFlight += 1;
    try {
      return await loader();
    } finally {
      upstreamInFlight -= 1;
    }
  }

  function getOrLoad(cache, key, ttlMs, maxEntries, loader) {
    const currentTime = now();
    const cached = cache.get(key);
    if (cached && cached.expiresAt > currentTime) {
      touchCacheEntry(cache, key, cached);
      return cached.promise;
    }
    cache.delete(key);
    const promise = loader().catch((error) => {
      if (cache.get(key)?.promise === promise) {
        cache.delete(key);
      }
      throw error;
    });
    setBoundedCacheEntry(cache, key, {
      expiresAt: currentTime + ttlMs,
      promise,
    }, maxEntries);
    return promise;
  }

  function resolveEffectivePolicy(workspaceId) {
    const normalizedWorkspaceId = normalizeWorkspaceId(workspaceId);
    return getOrLoad(
      effectivePolicyCache,
      normalizedWorkspaceId,
      policyTtlMs,
      maxPolicyEntries,
      () => runWithUpstreamSlot(async () => {
        incrementUpstreamCall('effectivePolicy');
        const path = `${WORKSPACE_EFFECTIVE_POLICY_PATH_PREFIX}/${encodeURIComponent(normalizedWorkspaceId)}/policy`;
        const payload = await fetchBoundedJson(
          fetchImpl,
          buildInternalApiUrl(path),
          POLICY_PAYLOAD_LIMITS.effective,
          timeoutMs,
        );
        return normalizeEffectiveWorkspacePolicy(payload, normalizedWorkspaceId);
      }),
    );
  }

  function resolveCapabilitySupport(capabilityCode) {
    const normalizedCapabilityCode = normalizeCapabilityCode(capabilityCode);
    return getOrLoad(
      capabilitySupportCache,
      normalizedCapabilityCode,
      supportTtlMs,
      maxSupportEntries,
      () => runWithUpstreamSlot(async () => {
        incrementUpstreamCall('capabilitySupport');
        const path = `/api/v1/capability-packs/installed-capabilities/${encodeURIComponent(normalizedCapabilityCode)}/mobile-workbench-gateway-support`;
        const payload = await fetchBoundedJson(
          fetchImpl,
          buildInternalApiUrl(path),
          POLICY_PAYLOAD_LIMITS.support,
          timeoutMs,
        );
        return normalizeCapabilitySupport(payload, normalizedCapabilityCode);
      }),
    );
  }

  async function resolveCapabilityDecision(capabilityCode) {
    const normalizedCapabilityCode = normalizeCapabilityCode(capabilityCode);
    const capabilitySupport = await resolveCapabilitySupport(normalizedCapabilityCode);
    return {
      capabilityCode: normalizedCapabilityCode,
      capabilitySupport,
      allowedPathRules: createCapabilityGatewayPathRules({
        capabilityCode: normalizedCapabilityCode,
        hostRouteTemplate: capabilitySupport.hostRouteTemplate,
        apiPrefixes: capabilitySupport.apiPrefixes,
      }),
    };
  }

  async function resolve({ workspaceId, capabilityCode = null }) {
    const effectivePolicyPromise = resolveEffectivePolicy(workspaceId);
    const supportPromise = capabilityCode
      ? resolveCapabilitySupport(capabilityCode)
      : Promise.resolve(null);
    const settled = await Promise.allSettled([
      effectivePolicyPromise,
      supportPromise,
    ]);
    const rejected = settled.find((result) => result.status === 'rejected');
    if (rejected) {
      throw rejected.reason;
    }
    const [effectivePolicy, capabilitySupport] = settled.map((result) => result.value);
    const normalizedCapabilityCode = capabilityCode
      ? normalizeCapabilityCode(capabilityCode)
      : null;
    return {
      effectivePolicy,
      capabilitySupport,
      capabilityCode: normalizedCapabilityCode,
      capabilityAllowed: normalizedCapabilityCode
        ? effectivePolicy.allowedCapabilityCodes.includes(normalizedCapabilityCode)
        : true,
      allowedPathRules: normalizedCapabilityCode && capabilitySupport
          ? createCapabilityGatewayPathRules({
              capabilityCode: normalizedCapabilityCode,
              hostRouteTemplate: capabilitySupport.hostRouteTemplate,
              apiPrefixes: capabilitySupport.apiPrefixes,
            })
        : [],
    };
  }

  resolve.resolveEffectivePolicy = resolveEffectivePolicy;
  resolve.resolveCapabilitySupport = resolveCapabilitySupport;
  resolve.resolveCapabilityDecision = resolveCapabilityDecision;
  resolve.clear = () => {
    effectivePolicyCache.clear();
    capabilitySupportCache.clear();
  };
  resolve.stats = () => ({
    effectivePolicyCacheEntries: effectivePolicyCache.size,
    capabilitySupportCacheEntries: capabilitySupportCache.size,
    upstreamEffectivePolicyCalls: upstreamCalls.effectivePolicy,
    upstreamCapabilitySupportCalls: upstreamCalls.capabilitySupport,
    upstreamInFlight,
    upstreamRejected,
    maxUpstreamInFlight: upstreamLimit,
  });
  return resolve;
}
