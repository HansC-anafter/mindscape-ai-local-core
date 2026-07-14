import {
  MAX_CLOCK_SKEW_SECONDS_DEFAULT,
  MAX_POLICY_UPSTREAM_IN_FLIGHT,
  PUBLIC_ORIGIN_ENV,
  REMOTE_WORKBENCH_PUBLIC_ORIGIN,
  RUNTIME_ACCESS_POLICY_PATH,
  UPSTREAM_TIMEOUT_MS,
} from './constants.mjs';
import {
  POLICY_PAYLOAD_LIMITS,
  normalizeRuntimeAccessPolicy,
  readBoundedJsonResponse,
} from './policy-contract.mjs';

function normalizePublicOrigin(value, { required = false } = {}) {
  const normalized = String(value || '').trim();
  if (!normalized) {
    return {
      value: '',
      error: required ? 'mobile_workbench_public_origin_required' : null,
    };
  }
  return normalized === REMOTE_WORKBENCH_PUBLIC_ORIGIN
    ? { value: normalized, error: null }
    : {
        value: normalized,
        error: 'mobile_workbench_public_origin_must_equal_remote_workbench_origin',
      };
}

function createBaseConfig(env) {
  const enabled = String(env.MOBILE_WORKBENCH_GATEWAY_ENABLED || '').trim() === '1';
  const publicOrigin = normalizePublicOrigin(env[PUBLIC_ORIGIN_ENV], { required: enabled });
  return {
    enabled,
    publicOrigin: publicOrigin.value,
    baseErrors: publicOrigin.error ? [publicOrigin.error] : [],
  };
}

export function resolveMobileWorkbenchGatewayConfig(
  env = process.env,
  runtimePolicy = null,
  {
    startupError = null,
    startupFetchCount = 0,
  } = {},
) {
  const base = createBaseConfig(env);
  const errors = [...base.baseErrors];
  if (startupError) {
    errors.push(String(startupError));
  }
  if (!runtimePolicy && base.enabled && !startupError) {
    errors.push('runtime_access_policy_not_loaded');
  }
  const remoteListenerReady = Boolean(
    base.enabled
    && runtimePolicy
    && runtimePolicy.accessIssuer
    && runtimePolicy.accessAudience
    && runtimePolicy.authConfigFingerprint
    && errors.length === 0
    && startupFetchCount === 1
  );
  return {
    enabled: base.enabled,
    reason: !base.enabled
      ? 'disabled'
      : remoteListenerReady
        ? 'strict_runtime_policy_ready'
        : 'runtime_policy_unavailable',
    errors,
    publicOrigin: base.publicOrigin,
    runtimePolicy,
    remoteListenerReady,
    authConfigSource: runtimePolicy?.authConfigSource || null,
    authConfigFingerprint: runtimePolicy?.authConfigFingerprint || null,
    remoteAccessState: runtimePolicy?.remoteAccessState || null,
    jwtIssuerReady: Boolean(runtimePolicy?.accessIssuer),
    jwtAudienceReady: Boolean(runtimePolicy?.accessAudience),
    jwtSignatureVerificationRequired: true,
    jwtClockSkewSeconds: MAX_CLOCK_SKEW_SECONDS_DEFAULT,
    startupFetchCount,
  };
}

export async function loadMobileWorkbenchGatewayRuntimeConfig({
  env = process.env,
  buildInternalApiUrl,
  fetchImpl = globalThis.fetch,
  timeoutMs = UPSTREAM_TIMEOUT_MS,
} = {}) {
  if (typeof buildInternalApiUrl !== 'function') {
    throw new Error('buildInternalApiUrl is required');
  }
  if (typeof fetchImpl !== 'function') {
    throw new Error('fetchImpl is required');
  }
  const base = createBaseConfig(env);
  if (!base.enabled) {
    return resolveMobileWorkbenchGatewayConfig(env, null, {
      startupFetchCount: 0,
    });
  }

  const abortController = new AbortController();
  const timeout = setTimeout(() => abortController.abort(), timeoutMs);
  try {
    const response = await fetchImpl(buildInternalApiUrl(RUNTIME_ACCESS_POLICY_PATH), {
      method: 'GET',
      headers: { accept: 'application/json' },
      signal: abortController.signal,
    });
    const payload = await readBoundedJsonResponse(response, POLICY_PAYLOAD_LIMITS.runtime);
    const runtimePolicy = normalizeRuntimeAccessPolicy(payload);
    return resolveMobileWorkbenchGatewayConfig(env, runtimePolicy, {
      startupFetchCount: 1,
    });
  } catch (error) {
    const reason = error?.name === 'AbortError'
      ? 'runtime_access_policy_timeout'
      : `runtime_access_policy_load_failed:${error?.message || 'unknown_error'}`;
    return resolveMobileWorkbenchGatewayConfig(env, null, {
      startupError: reason,
      startupFetchCount: 1,
    });
  } finally {
    clearTimeout(timeout);
  }
}

export function isMobileWorkbenchGatewayConfigEnabled(env = process.env) {
  return createBaseConfig(env).enabled;
}

export function formatMobileWorkbenchGatewayConfig(config, resolverStats = {}) {
  return {
    enabled: Boolean(config?.enabled),
    reason: config?.reason || 'runtime_policy_unavailable',
    errors: [...(config?.errors || [])],
    public_origin: config?.publicOrigin || null,
    auth_config_source: config?.authConfigSource || null,
    auth_config_fingerprint: config?.authConfigFingerprint || null,
    remote_access_state: config?.remoteAccessState || null,
    runtime_policy_revision: Number.isSafeInteger(config?.runtimePolicy?.revision)
      ? config.runtimePolicy.revision
      : null,
    startup_config_get_count: Number(config?.startupFetchCount || 0),
    remote_listener_ready: Boolean(config?.remoteListenerReady),
    jwt_signature_verification_required: true,
    jwt_issuer_ready: Boolean(config?.jwtIssuerReady),
    jwt_audience_ready: Boolean(config?.jwtAudienceReady),
    jwt_clock_skew_seconds: Number(config?.jwtClockSkewSeconds || MAX_CLOCK_SKEW_SECONDS_DEFAULT),
    effective_policy_cache_entries: Number(resolverStats?.effectivePolicyCacheEntries || 0),
    capability_support_cache_entries: Number(resolverStats?.capabilitySupportCacheEntries || 0),
    upstream_effective_policy_calls: Number(resolverStats?.upstreamEffectivePolicyCalls || 0),
    upstream_capability_support_calls: Number(resolverStats?.upstreamCapabilitySupportCalls || 0),
    upstream_in_flight: Number(resolverStats?.upstreamInFlight || 0),
    upstream_rejected: Number(resolverStats?.upstreamRejected || 0),
    max_upstream_in_flight: Number(
      resolverStats?.maxUpstreamInFlight || MAX_POLICY_UPSTREAM_IN_FLIGHT
    ),
  };
}
