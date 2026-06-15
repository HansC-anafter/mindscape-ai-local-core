import {
  createCapabilityGatewayPathRules,
} from './mobile-workbench-gateway-capability-rules.mjs';

const POLICY_TTL_MS = 15_000;

function normalizeCapabilityCode(value = '') {
  return String(value || '').trim().toLowerCase();
}

function normalizeCapabilityCodes(values = []) {
  if (!Array.isArray(values)) {
    return [];
  }
  const seen = new Set();
  const normalized = [];
  for (const value of values) {
    const candidate = normalizeCapabilityCode(value);
    if (!candidate || seen.has(candidate)) {
      continue;
    }
    seen.add(candidate);
    normalized.push(candidate);
  }
  normalized.sort();
  return normalized;
}

async function fetchJson(fetchImpl, url) {
  const response = await fetchImpl(url);
  if (!response.ok) {
    throw new Error(`Gateway policy request failed: ${response.status} ${url}`);
  }
  return await response.json();
}

export function createMobileWorkbenchGatewayPolicyResolver({
  buildInternalApiUrl,
  fetchImpl = globalThis.fetch,
  now = () => Date.now(),
} = {}) {
  if (typeof buildInternalApiUrl !== 'function') {
    throw new Error('buildInternalApiUrl is required');
  }
  if (typeof fetchImpl !== 'function') {
    throw new Error('fetchImpl is required');
  }

  const cache = new Map();

  async function resolve({
    workspaceId,
    capabilityCode,
  }) {
    const normalizedWorkspaceId = String(workspaceId || '').trim();
    const normalizedCapabilityCode = normalizeCapabilityCode(capabilityCode);
    if (!normalizedWorkspaceId || !normalizedCapabilityCode) {
      return null;
    }

    const cacheKey = `${normalizedWorkspaceId}:${normalizedCapabilityCode}`;
    const cached = cache.get(cacheKey);
    const currentTime = now();
    if (cached && cached.expiresAt > currentTime) {
      return cached.promise;
    }

    const promise = Promise.all([
      fetchJson(
        fetchImpl,
        buildInternalApiUrl(
          `/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/workspaces/${encodeURIComponent(normalizedWorkspaceId)}/policy`,
        ),
      ),
      fetchJson(
        fetchImpl,
        buildInternalApiUrl(
          `/api/v1/capability-packs/installed-capabilities/${encodeURIComponent(normalizedCapabilityCode)}/mobile-workbench-gateway-support`,
        ),
      ),
    ]).then(([policyPayload, supportPayload]) => {
      const allowedCapabilityCodes = normalizeCapabilityCodes(
        policyPayload?.allowed_capability_codes || [],
      );
      const apiPrefixes = Array.isArray(supportPayload?.api_prefixes)
        ? supportPayload.api_prefixes
        : [];
      return {
        workspaceId: normalizedWorkspaceId,
        capabilityCode: normalizedCapabilityCode,
        allowedCapabilityCodes,
        capabilityAllowed: allowedCapabilityCodes.includes(normalizedCapabilityCode),
        supported: Boolean(supportPayload?.supported),
        hostRouteTemplate: supportPayload?.host_route_template || null,
        apiPrefixes,
        allowedPathRules: createCapabilityGatewayPathRules({
          capabilityCode: normalizedCapabilityCode,
          apiPrefixes,
        }),
      };
    }).catch((error) => {
      cache.delete(cacheKey);
      throw error;
    });

    cache.set(cacheKey, {
      expiresAt: currentTime + POLICY_TTL_MS,
      promise,
    });
    return promise;
  }

  resolve.clear = () => {
    cache.clear();
  };

  return resolve;
}
