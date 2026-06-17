import crypto from 'node:crypto';
import fs from 'node:fs';

import {
  DEVICE_LINK_INGRESS_TOKEN_HEADER,
  isAllowedDeviceLinkHttpsPath,
} from './device-link-https.mjs';
import {
  createDefaultCapabilityGatewayPathRules,
  createDefaultGatewayWorkspaceSupportRules,
} from './mobile-workbench-gateway-capability-rules.mjs';

const DEFAULT_ALLOWED_PATH_RULES = [
  { type: 'prefix', value: '/favicon.ico' },
  { type: 'prefix', value: '/healthz' },
  { type: 'prefix', value: '/api/healthz' },
  { type: 'prefix', value: '/_next/' },
  ...createDefaultCapabilityGatewayPathRules(),
  ...createDefaultGatewayWorkspaceSupportRules(),
];

const DEFAULT_TOKEN_HEADER_NAMES = [
  'cf-access-jwt-assertion',
  'cf_authorization',
  'cf-authorization',
];

const ALLOWLIST_EMAIL_ENV = 'MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS';
const ALLOWLIST_GROUP_ENV = 'MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_GROUPS';
const WORKSPACE_ALLOWLIST_ENV = 'MOBILE_WORKBENCH_GATEWAY_WORKSPACE_ALLOWLIST';
const PUBLIC_ORIGIN_ENV = 'MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN';
const JWT_AUDIENCE_ENV = 'MOBILE_WORKBENCH_GATEWAY_JWT_AUDIENCE';
const JWT_ISSUER_ENV = 'MOBILE_WORKBENCH_GATEWAY_JWT_ISSUER';
const JWT_CLOCK_SKEW_ENV = 'MOBILE_WORKBENCH_GATEWAY_JWT_CLOCK_SKEW_SECONDS';
const JWT_PUBLIC_KEY_ENV = 'MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY';
const JWT_PUBLIC_KEY_FILE_ENV = 'MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY_FILE';
const JWT_REQUIRE_SIGNATURE_VERIFICATION_ENV = 'MOBILE_WORKBENCH_GATEWAY_REQUIRE_SIGNATURE_VERIFICATION';

const MAX_CLOCK_SKEW_SECONDS_DEFAULT = 30;
const JWT_ALGORITHMS = new Set(['RS256', 'RS384', 'RS512', 'PS256', 'PS384', 'PS512']);
const JWT_VERIFY_ALGORITHMS = {
  RS256: 'RSA-SHA256',
  RS384: 'RSA-SHA384',
  RS512: 'RSA-SHA512',
  PS256: 'RSA-SHA256',
  PS384: 'RSA-SHA384',
  PS512: 'RSA-SHA512',
};
const GATEWAY_CONTROL_CAPABILITY_CODE = 'mindscape_cloud_integration';
const GATEWAY_CONTROL_COMPONENT_CODE = 'MindscapeMobileWorkbenchGatewayPage';
const READ_ONLY_GATEWAY_METHODS = ['GET', 'HEAD', 'OPTIONS'];
const CONTROL_PLANE_ALLOWED_PATH_RULES = [
  {
    type: 'regex',
    value: /^\/workspaces\/[^/]+\/capability-ui-hosts\/mindscape_cloud_integration(?:\/.*)?$/,
    methods: READ_ONLY_GATEWAY_METHODS,
  },
  {
    type: 'regex',
    value: /^\/api\/v1\/capability-packs\/installed-capabilities\/mindscape_cloud_integration(?:\/(?:ui-components|workspace-tools))?$/,
    methods: READ_ONLY_GATEWAY_METHODS,
  },
  {
    type: 'regex',
    value: /^\/api\/v1\/capability-packs\/installed-capabilities\/mindscape_cloud_integration\/ui-assets\/.+$/,
    methods: READ_ONLY_GATEWAY_METHODS,
  },
  {
    type: 'regex',
    value: /^\/api\/v1\/capabilities\/mindscape_cloud_integration\/mobile-workbench-gateway\/workspaces\/[^/]+\/policy$/,
    methods: ['GET', 'HEAD', 'OPTIONS', 'PUT'],
  },
  {
    type: 'regex',
    value: /^\/api\/v1\/host\/services\/mobile-workbench-gateway\/health$/,
    methods: READ_ONLY_GATEWAY_METHODS,
  },
  {
    type: 'regex',
    value: /^\/api\/v1\/host\/services\/mobile-workbench-gateway\/summary$/,
    methods: READ_ONLY_GATEWAY_METHODS,
  },
  {
    type: 'regex',
    value: /^\/api\/v1\/host\/services\/mobile-workbench-gateway\/audit$/,
    methods: READ_ONLY_GATEWAY_METHODS,
  },
];

function toLowerTrimmed(value = '') {
  return String(value || '').trim().toLowerCase();
}

function isLoopbackPublicOrigin(publicOrigin = '') {
  try {
    const parsed = new URL(publicOrigin);
    const hostname = parsed.hostname.toLowerCase();
    return (
      hostname === 'localhost' ||
      hostname.endsWith('.localhost') ||
      hostname === '127.0.0.1' ||
      hostname.startsWith('127.') ||
      hostname === '::1' ||
      hostname === '[::1]' ||
      hostname === '0.0.0.0'
    );
  } catch {
    return false;
  }
}

function normalizeRequestMethod(value = 'GET') {
  const normalized = String(value || 'GET').trim().toUpperCase();
  return normalized || 'GET';
}

function isTruthyEnvValue(value = '') {
  const normalized = toLowerTrimmed(value);
  return ['1', 'true', 'yes', 'on'].includes(normalized);
}

function splitCommaSeparatedValues(rawValue) {
  if (!rawValue) {
    return [];
  }
  return String(rawValue)
    .split(',')
    .map((item) => toLowerTrimmed(item))
    .filter(Boolean);
}

function splitAdditionalRules(rawValue) {
  if (!rawValue) {
    return [];
  }
  return String(rawValue)
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function isRegexToken(token = '') {
  return String(token || '').startsWith('regex:');
}

function normalizePathPattern(token, errors = []) {
  const normalized = String(token || '').trim();
  if (!normalized) {
    return null;
  }
  if (isRegexToken(normalized)) {
    try {
      return {
        type: 'regex',
        value: new RegExp(normalized.slice('regex:'.length)),
        source: normalized,
      };
    } catch (error) {
      errors.push(`invalid_regex_pattern:${normalized}`);
      return null;
    }
  }
  if (!normalized.startsWith('/')) {
    errors.push(`invalid_path_pattern:${normalized}`);
    return null;
  }
  return {
    type: 'prefix',
    value: normalized,
  };
}

function isJwtAlgorithmSupported(alg = '') {
  return JWT_ALGORITHMS.has(toLowerTrimmed(alg).toUpperCase());
}

function getJwtVerifyAlgorithm(alg = '') {
  return JWT_VERIFY_ALGORITHMS[String(alg || '').toUpperCase()] || '';
}

function parseAccessTokenFromHeaders(rawHeaders = {}) {
  const headers = rawHeaders || {};
  for (const headerName of DEFAULT_TOKEN_HEADER_NAMES) {
    const value = Object.entries(headers).find(([key]) => toLowerTrimmed(key) === headerName)?.[1];
    if (!value) {
      continue;
    }
    const tokenValue = Array.isArray(value) ? value[0] : value;
    const normalized = String(tokenValue || '').trim();
    if (!normalized) {
      continue;
    }
    const match = /^Bearer\s+(.+)$/.exec(normalized);
    return match ? match[1].trim() : normalized;
  }
  return null;
}

function base64urlPad(value = '') {
  const normalized = String(value || '');
  const padLength = normalized.length % 4 === 0 ? 0 : 4 - (normalized.length % 4);
  return normalized + '='.repeat(padLength);
}

function base64urlDecode(value = '') {
  const normalized = base64urlPad(String(value || ''))
    .replace(/-/g, '+')
    .replace(/_/g, '/');
  return Buffer.from(normalized, 'base64').toString('utf8');
}

function base64urlDecodeBuffer(value = '') {
  const normalized = base64urlPad(String(value || ''))
    .replace(/-/g, '+')
    .replace(/_/g, '/');
  return Buffer.from(normalized, 'base64');
}

function normalizeClaimValue(value) {
  if (value === null || value === undefined) {
    return null;
  }
  return String(value).trim();
}

function normalizeCapabilityCodeFromApiSegment(value) {
  const normalized = normalizeClaimValue(value);
  return normalized ? normalized.replace(/-/g, '_') : null;
}

function parseAccessJwtToken(rawToken) {
  if (!rawToken || typeof rawToken !== 'string') {
    return { claims: null, error: 'missing_access_token', header: null, signature: null, signingInput: null };
  }

  const tokenParts = rawToken.split('.');
  if (tokenParts.length !== 3) {
    return { claims: null, error: 'invalid_access_token', header: null, signature: null, signingInput: null };
  }

  try {
    const [headerPart, payloadPart] = tokenParts;
    const headerJson = base64urlDecode(headerPart);
    const payloadJson = base64urlDecode(payloadPart);
    const header = JSON.parse(headerJson);
    const claims = JSON.parse(payloadJson);
    if (claims === null || typeof claims !== 'object') {
      return {
        claims: null,
        error: 'invalid_access_token_claims',
        header: null,
        signature: null,
        signingInput: null,
      };
    }
    return {
      claims,
      header,
      signature: base64urlDecodeBuffer(tokenParts[2]),
      signingInput: `${tokenParts[0]}.${tokenParts[1]}`,
      error: null,
    };
  } catch (error) {
    return {
      claims: null,
      error: `invalid_access_token:${error?.message || 'decode_error'}`,
      header: null,
      signature: null,
      signingInput: null,
    };
  }
}

function parseClockSkew(rawValue) {
  if (rawValue === undefined || rawValue === null || String(rawValue).trim() === '') {
    return MAX_CLOCK_SKEW_SECONDS_DEFAULT;
  }
  const parsed = Number.parseInt(String(rawValue).trim(), 10);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 3600) {
    return MAX_CLOCK_SKEW_SECONDS_DEFAULT;
  }
  return parsed;
}

function readPublicKeySource(keyFile, inlineKey) {
  const trimmedFile = String(keyFile || '').trim();
  const trimmedInline = String(inlineKey || '').trim();
  if (trimmedFile && trimmedInline) {
    return {
      value: null,
      error: 'MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY_and_JWT_PUBLIC_KEY_FILE_are_mutually_exclusive',
    };
  }
  if (trimmedFile) {
    try {
      return {
        value: fs.readFileSync(trimmedFile, 'utf8'),
        error: null,
      };
    } catch (error) {
      return {
        value: null,
        error: `MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY_FILE_read_failed:${error?.code || error?.message || 'read_error'}`,
      };
    }
  }
  if (trimmedInline) {
    return {
      value: trimmedInline,
      error: null,
    };
  }
  return { value: null, error: null };
}

function isJwtTokenExpired(claims, nowEpochSeconds = Math.floor(Date.now() / 1000), clockSkewSeconds = 0) {
  if (!claims || typeof claims !== 'object') {
    return true;
  }
  if (claims.exp !== undefined && Number.isFinite(Number(claims.exp))) {
    if (Number(claims.exp) + Number(clockSkewSeconds) < nowEpochSeconds) {
      return true;
    }
  }
  if (claims.nbf !== undefined && Number.isFinite(Number(claims.nbf))) {
    if (Number(claims.nbf) - Number(clockSkewSeconds) > nowEpochSeconds) {
      return true;
    }
  }
  return false;
}

function normalizeAudience(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeClaimValue).filter(Boolean).map(toLowerTrimmed);
  }
  if (typeof value === 'string') {
    return splitCommaSeparatedValues(value);
  }
  return [];
}

function isAudienceMatch(configAudiences = [], tokenAudience = null) {
  if (configAudiences.length === 0) {
    return true;
  }
  const tokenAudiences = normalizeAudience(tokenAudience).map(toLowerTrimmed);
  return tokenAudiences.some((aud) => configAudiences.includes(aud));
}

function isIssuerMatch(configIssuers = [], tokenIssuer = null) {
  if (configIssuers.length === 0) {
    return true;
  }
  const normalizedIssuer = toLowerTrimmed(tokenIssuer);
  return normalizedIssuer && configIssuers.includes(normalizedIssuer);
}

function normalizeClaimList(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeClaimValue).filter(Boolean).map(toLowerTrimmed);
  }
  if (typeof value === 'string') {
    return splitCommaSeparatedValues(value);
  }
  return [];
}

function decodeURIComponentSafe(value = '') {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function isGatewayControlCapabilityCode(value = '') {
  return toLowerTrimmed(value) === GATEWAY_CONTROL_CAPABILITY_CODE;
}

function isGatewayControlComponentCode(value = '') {
  return String(value || '').trim() === GATEWAY_CONTROL_COMPONENT_CODE;
}

function isGatewayControlPolicyPath(pathname = '') {
  return /^\/api\/v1\/capabilities\/mindscape_cloud_integration\/mobile-workbench-gateway\/workspaces\/[^/]+\/policy$/.test(pathname);
}

function isGatewayControlObservabilityPath(pathname = '') {
  return /^\/api\/v1\/host\/services\/mobile-workbench-gateway\/(?:health|summary|audit)$/.test(pathname);
}

function extractRequestContextFromUrl(requestUrl = '/') {
  let pathname = '/';
  let workspaceId = null;
  let capabilityCode = null;
  let capabilityFromFallback = false;
  let routeCapabilityCode = null;
  let targetCapabilityCode = null;
  let componentCode = null;
  let gatewayControlPlaneCarrier = false;
  let gatewayControlPlaneTargeted = false;

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    pathname = parsed.pathname || '/';
    workspaceId =
      parsed.searchParams.get('workspace_id') ||
      parsed.searchParams.get('workspaceId') ||
      null;
    capabilityCode =
      parsed.searchParams.get('capability_code') ||
      parsed.searchParams.get('capabilityCode') ||
      null;
    targetCapabilityCode =
      parsed.searchParams.get('target_capability') ||
      parsed.searchParams.get('targetCapability') ||
      null;
    componentCode = parsed.searchParams.get('component') || null;
  } catch {
    pathname = '/';
  }

  const workspaceMatch = /^\/workspaces\/([^/]+)\/capability-ui-hosts\/([^/]+)(?:\/.*)?$/.exec(pathname);
  if (workspaceMatch) {
    workspaceId = normalizeClaimValue(decodeURIComponentSafe(workspaceMatch[1]));
    routeCapabilityCode = normalizeClaimValue(decodeURIComponentSafe(workspaceMatch[2]));
    capabilityCode = routeCapabilityCode;
  }

  const igApiMatch = /^\/api\/v1\/ig(?:\/.*)?$/.exec(pathname);
  if (igApiMatch) {
    routeCapabilityCode = 'ig';
    capabilityCode = 'ig';
  }

  const capabilityApiMatch = /^\/api\/v1\/capabilities\/([^/]+)(?:\/.*)?$/.exec(pathname);
  if (capabilityApiMatch) {
    routeCapabilityCode = normalizeClaimValue(decodeURIComponentSafe(capabilityApiMatch[1]));
    capabilityCode = normalizeCapabilityCodeFromApiSegment(routeCapabilityCode);
  }

  const installedCapabilityMatch =
    /^\/api\/v1\/capability-packs\/installed-capabilities(?:\/([^/]+))?(?:\/.*)?$/.exec(pathname);
  if (installedCapabilityMatch) {
    routeCapabilityCode = normalizeClaimValue(decodeURIComponentSafe(installedCapabilityMatch[1])) || null;
    capabilityCode = routeCapabilityCode || 'ig';
    capabilityFromFallback = !installedCapabilityMatch[1];
  }

  const capabilityAssetsMatch = /^\/api\/v1\/capability-packs\/([^/]+)\/ui-assets\//.exec(pathname);
  if (capabilityAssetsMatch) {
    routeCapabilityCode = normalizeClaimValue(decodeURIComponentSafe(capabilityAssetsMatch[1]));
    capabilityCode = routeCapabilityCode;
  }

  const workspaceExecutionsMatch = /^\/api\/v1\/workspaces\/([^/]+)\/executions(?:\/.*)?$/.exec(pathname);
  if (workspaceExecutionsMatch) {
    workspaceId = normalizeClaimValue(decodeURIComponentSafe(workspaceExecutionsMatch[1]));
    capabilityCode = capabilityCode || 'ig';
    capabilityFromFallback = capabilityCode === 'ig';
  }

  const workspaceDeviceBindingMatch =
    /^\/api\/v1\/workspaces\/([^/]+)\/device-bindings\//.exec(pathname);
  if (workspaceDeviceBindingMatch) {
    workspaceId = normalizeClaimValue(decodeURIComponentSafe(workspaceDeviceBindingMatch[1]));
  }

  const workspaceSummaryMatch = /^\/api\/v1\/workspaces\/([^/]+)\/summary$/.exec(pathname);
  if (workspaceSummaryMatch) {
    workspaceId = normalizeClaimValue(decodeURIComponentSafe(workspaceSummaryMatch[1]));
  }

  const workspaceTasksMatch = /^\/api\/v1\/workspaces\/([^/]+)\/tasks(?:\/.*)?$/.exec(pathname);
  if (workspaceTasksMatch) {
    workspaceId = normalizeClaimValue(decodeURIComponentSafe(workspaceTasksMatch[1]));
    capabilityCode = capabilityCode || 'ig';
    capabilityFromFallback = capabilityCode === 'ig';
  }

  const workspaceHostRuntimeMatch = /^\/api\/v1\/workspaces\/([^/]+)\/host-runtime\/sessions(?:\/.*)?$/.exec(pathname);
  if (workspaceHostRuntimeMatch) {
    workspaceId = normalizeClaimValue(decodeURIComponentSafe(workspaceHostRuntimeMatch[1]));
  }

  const workspaceEventsMatch = /^\/api\/v1\/workspaces\/([^/]+)\/events\/stream$/.exec(pathname);
  if (workspaceEventsMatch) {
    workspaceId = normalizeClaimValue(decodeURIComponentSafe(workspaceEventsMatch[1]));
    capabilityCode = capabilityCode || 'ig';
    capabilityFromFallback = capabilityCode === 'ig';
  }

  if (
    /^\/api\/v1\/system-settings\/keyboard-shortcuts$/.test(pathname) ||
    /^\/api\/v1\/host-resources\/lanes$/.test(pathname)
  ) {
    capabilityCode = capabilityCode || 'ig';
    capabilityFromFallback = capabilityCode === 'ig';
  }

  gatewayControlPlaneCarrier =
    (
      isGatewayControlCapabilityCode(routeCapabilityCode)
      && isGatewayControlComponentCode(componentCode)
    )
    || (
      isGatewayControlCapabilityCode(routeCapabilityCode)
      && /^\/api\/v1\/capability-packs\/installed-capabilities\/mindscape_cloud_integration\/ui-assets\/.+$/.test(pathname)
    )
    || isGatewayControlPolicyPath(pathname)
    || isGatewayControlObservabilityPath(pathname);

  if (
    isGatewayControlCapabilityCode(routeCapabilityCode)
    && isGatewayControlComponentCode(componentCode)
    && targetCapabilityCode
  ) {
    capabilityCode = normalizeClaimValue(targetCapabilityCode);
    gatewayControlPlaneTargeted = true;
  } else if (isGatewayControlObservabilityPath(pathname) && capabilityCode) {
    gatewayControlPlaneTargeted = true;
    targetCapabilityCode = normalizeClaimValue(capabilityCode);
  }

  return {
    path: pathname,
    workspaceId: workspaceId || null,
    capabilityCode: capabilityCode || null,
    capabilityFromFallback,
    routeCapabilityCode: routeCapabilityCode || null,
    targetCapabilityCode: normalizeClaimValue(targetCapabilityCode) || null,
    componentCode: normalizeClaimValue(componentCode) || null,
    gatewayControlPlaneCarrier,
    gatewayControlPlaneTargeted,
  };
}

function resolveRefererHeader(requestHeaders = {}) {
  const candidate = requestHeaders?.referer || requestHeaders?.referrer || '';
  return String(Array.isArray(candidate) ? candidate[0] || '' : candidate || '').trim();
}

function extractRequestContext(requestUrl = '/', requestHeaders = {}) {
  const primaryContext = extractRequestContextFromUrl(requestUrl);
  const referer = resolveRefererHeader(requestHeaders);
  const canUseRefererCapability = Boolean(
    !primaryContext.capabilityCode
    || primaryContext.capabilityFromFallback
    || primaryContext.gatewayControlPlaneCarrier
  );
  if (!referer || (primaryContext.workspaceId && primaryContext.capabilityCode && !canUseRefererCapability)) {
    return primaryContext;
  }
  const refererContext = extractRequestContextFromUrl(referer);
  const inheritGatewayTargetCapability = Boolean(
    primaryContext.gatewayControlPlaneCarrier
    && refererContext.gatewayControlPlaneTargeted
    && refererContext.capabilityCode
  );
  return {
    path: primaryContext.path,
    workspaceId: primaryContext.workspaceId || refererContext.workspaceId || null,
    capabilityCode: inheritGatewayTargetCapability
      ? (refererContext.capabilityCode || primaryContext.capabilityCode || null)
      : (
          canUseRefererCapability
            ? (refererContext.capabilityCode || primaryContext.capabilityCode || null)
            : (primaryContext.capabilityCode || refererContext.capabilityCode || null)
        ),
    routeCapabilityCode: primaryContext.routeCapabilityCode || refererContext.routeCapabilityCode || null,
    targetCapabilityCode: primaryContext.targetCapabilityCode
      || (inheritGatewayTargetCapability ? refererContext.targetCapabilityCode : null)
      || null,
    componentCode: primaryContext.componentCode || refererContext.componentCode || null,
    gatewayControlPlaneCarrier: Boolean(
      primaryContext.gatewayControlPlaneCarrier
      || (inheritGatewayTargetCapability && refererContext.gatewayControlPlaneCarrier)
    ),
    gatewayControlPlaneTargeted: Boolean(
      primaryContext.gatewayControlPlaneTargeted || inheritGatewayTargetCapability
    ),
    referer_path: refererContext.path || null,
  };
}

export function extractMobileWorkbenchGatewayRequestContext(requestUrl = '/', requestHeaders = {}) {
  return extractRequestContext(requestUrl, requestHeaders);
}

function isMobileWorkbenchGatewayControlPlanePathAllowed(pathname = '/', requestMethod = 'GET') {
  return CONTROL_PLANE_ALLOWED_PATH_RULES.some((rule) => matchesRule(pathname, rule, requestMethod));
}

function verifyJwtSignature(tokenHeader, tokenSignature, tokenSigningInput, publicKey, verifyEnabled) {
  if (!verifyEnabled) {
    return { valid: true };
  }
  if (!tokenHeader || typeof tokenHeader !== 'object') {
    return { valid: false, reason: 'invalid_access_token_header' };
  }
  if (!publicKey) {
    return { valid: false, reason: 'MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY_required_for_signature_verification' };
  }
  const alg = String(tokenHeader.alg || '').toUpperCase();
  if (!isJwtAlgorithmSupported(alg)) {
    return { valid: false, reason: 'unsupported_access_token_algorithm' };
  }
  const verifyAlgorithm = getJwtVerifyAlgorithm(alg);
  try {
    const verifier = crypto.createVerify(verifyAlgorithm);
    verifier.update(tokenSigningInput);
    verifier.end();
    const isValid = verifier.verify(publicKey, tokenSignature);
    if (!isValid) {
      return { valid: false, reason: 'invalid_access_token_signature' };
    }
    return { valid: true };
  } catch (error) {
    return {
      valid: false,
      reason: `access_token_signature_verification_error:${error?.message || 'verification_error'}`,
    };
  }
}

function matchesRule(pathname, rule, requestMethod = 'GET') {
  if (!rule) {
    return false;
  }
  const normalizedMethod = normalizeRequestMethod(requestMethod);
  if (Array.isArray(rule.methods) && rule.methods.length > 0 && !rule.methods.includes(normalizedMethod)) {
    return false;
  }
  if (rule.type === 'prefix') {
    return pathname.startsWith(rule.value);
  }
  if (rule.type === 'regex') {
    return rule.value.test(pathname);
  }
  return false;
}

function isRequestInAllowlist(value, allowlist = []) {
  if (allowlist.length === 0) {
    return true;
  }
  const normalized = toLowerTrimmed(value);
  if (!normalized) {
    return false;
  }
  return allowlist.includes(normalized);
}

function isGatewayPolicyEnabled(config) {
  return (
    (config?.allowlistEmails || []).length > 0 ||
    (config?.allowlistGroups || []).length > 0 ||
    (config?.workspaceAllowlist || []).length > 0 ||
    (config?.jwtVerifyRequired || false) ||
    (config?.jwtAudience || []).length > 0 ||
    (config?.jwtIssuer || []).length > 0
  );
}

function denyRequest(reason, statusCode, requestUrl, details = {}) {
  return {
    allowed: false,
    reason,
    status_code: statusCode,
    path: requestUrl,
    ...details,
  };
}

function allowRequest(config, requestUrl, details = {}) {
  return {
    allowed: true,
    reason: 'mobile_workbench_gateway_request_allowed',
    status_code: 200,
    path: requestUrl,
    ...details,
    policy_enabled: isGatewayPolicyEnabled(config),
  };
}

function resolveRequestHostname(requestHeaders = {}) {
  const rawHost = String(
    requestHeaders?.host || requestHeaders?.Host || '',
  ).trim();
  if (!rawHost) {
    return '';
  }
  try {
    return new URL(`http://${rawHost}`).hostname.toLowerCase();
  } catch {
    return '';
  }
}

export function isLoopbackControlPlaneRequest(requestHeaders = {}) {
  const hostname = resolveRequestHostname(requestHeaders);
  return hostname === 'localhost'
    || hostname.endsWith('.localhost')
    || hostname === '::1'
    || hostname === '0:0:0:0:0:0:0:1'
    || /^127(?:\.\d{1,3}){3}$/.test(hostname);
}

function isGatewayPathAllowed(
  requestUrl = '/',
  config = resolveMobileWorkbenchGatewayConfig(),
  requestMethod = 'GET',
) {
  if (!config.enabled) {
    return true;
  }

  let pathname;
  try {
    pathname = new URL(requestUrl, 'http://localhost').pathname;
  } catch {
    pathname = '/';
  }

  return config.allowedPathRules.concat(config.extraAllowedPathRules || []).some((rule) =>
    matchesRule(pathname, rule, requestMethod),
  );
}

export function isMobileWorkbenchGatewayRequestAllowed(
  requestUrl = '/',
  requestHeaders = {},
  config = resolveMobileWorkbenchGatewayConfig(),
  { deviceLinkIngressToken = '', requestMethod = 'GET' } = {},
) {
  if (!config.enabled) {
    return allowRequest(config, requestUrl);
  }

  if (isLoopbackControlPlaneRequest(requestHeaders)) {
    return allowRequest(config, requestUrl, {
      ingress: 'local_control_plane',
    });
  }

  const presentedDeviceLinkToken = String(
    requestHeaders?.[DEVICE_LINK_INGRESS_TOKEN_HEADER] ||
    requestHeaders?.[DEVICE_LINK_INGRESS_TOKEN_HEADER.toLowerCase()] ||
    '',
  );
  if (
    deviceLinkIngressToken &&
    presentedDeviceLinkToken.length === deviceLinkIngressToken.length &&
    crypto.timingSafeEqual(
      Buffer.from(presentedDeviceLinkToken),
      Buffer.from(deviceLinkIngressToken),
    ) &&
    isAllowedDeviceLinkHttpsPath(requestUrl)
  ) {
    return allowRequest(config, requestUrl, {
      ingress: 'device_link_https',
    });
  }

  if (!isGatewayPathAllowed(requestUrl, config, requestMethod)) {
    return denyRequest('mobile_workbench_gateway_path_not_allowed', 404, requestUrl);
  }

  const context = extractRequestContext(requestUrl, requestHeaders);
  if (!isGatewayPolicyEnabled(config)) {
    return allowRequest(config, requestUrl, { context });
  }

  const accessToken = parseAccessTokenFromHeaders(requestHeaders);
  if (!accessToken) {
    return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
      reason_code: 'missing_access_token',
      context,
    });
  }

  const {
    claims,
    header,
    signature,
    signingInput,
    error: claimsError,
  } = parseAccessJwtToken(accessToken);
  if (!claims || claimsError) {
    return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
      reason_code: claimsError || 'invalid_access_token',
      context,
      claims_error: claimsError,
    });
  }

  if (isJwtTokenExpired(claims, Math.floor(Date.now() / 1000), config.jwtClockSkewSeconds)) {
    return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
      reason_code: 'expired_or_not_ready_token',
      context,
    });
  }

  const signatureResult = verifyJwtSignature(
    header,
    signature,
    signingInput,
    config.jwtPublicKey,
    config.jwtVerifyRequired,
  );
  if (!signatureResult.valid) {
    return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
      reason_code: signatureResult.reason || 'invalid_access_token_signature',
      context,
    });
  }

  if (!isAudienceMatch(config.jwtAudience, claims.aud)) {
    return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
      reason_code: 'invalid_access_token_audience',
      context,
      claim_audience: claims.aud || null,
    });
  }

  if (!isIssuerMatch(config.jwtIssuer, claims.iss)) {
    return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
      reason_code: 'invalid_access_token_issuer',
      context,
      claim_issuer: claims.iss || null,
    });
  }

  const email = toLowerTrimmed(normalizeClaimValue(claims.email || claims.preferred_username || claims.upn || claims.sub));
  const groups = normalizeClaimList(claims.groups || claims.group || []);

  const emailAllowed = config.allowlistEmails.length > 0
    ? isRequestInAllowlist(email, config.allowlistEmails)
    : true;
  const groupAllowed = config.allowlistGroups.length > 0
    ? groups.some((group) => isRequestInAllowlist(group, config.allowlistGroups))
    : true;

  if (!emailAllowed && !groupAllowed) {
    return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
      reason_code: 'email_not_allowed',
      context,
      claim_email: email || null,
      claim_groups: groups,
    });
  }

  const claimWorkspaceId = normalizeClaimValue(claims.workspace_id || claims.workspaceId || claims.wsid);
  const workspaceId = toLowerTrimmed(context.workspaceId || claimWorkspaceId);
  const hasWorkspaceScope = Boolean(context.workspaceId || claimWorkspaceId);
  if (
    config.workspaceAllowlist.length > 0 &&
    hasWorkspaceScope &&
    !isRequestInAllowlist(workspaceId, config.workspaceAllowlist)
  ) {
    return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
      reason_code: 'workspace_not_allowed',
      context,
      claim_workspace_id: workspaceId || null,
    });
  }

  return allowRequest(config, requestUrl, {
    context,
    claims_email: email || null,
  });
}

export async function isMobileWorkbenchGatewayRequestAllowedAsync(
  requestUrl = '/',
  requestHeaders = {},
  config = resolveMobileWorkbenchGatewayConfig(),
  {
    deviceLinkIngressToken = '',
    requestMethod = 'GET',
    resolveWorkspaceCapabilityPolicy = null,
  } = {},
) {
  if (!config.enabled) {
    return allowRequest(config, requestUrl);
  }

  if (isLoopbackControlPlaneRequest(requestHeaders)) {
    return allowRequest(config, requestUrl, {
      ingress: 'local_control_plane',
    });
  }

  const presentedDeviceLinkToken = String(
    requestHeaders?.[DEVICE_LINK_INGRESS_TOKEN_HEADER] ||
    requestHeaders?.[DEVICE_LINK_INGRESS_TOKEN_HEADER.toLowerCase()] ||
    '',
  );
  if (
    deviceLinkIngressToken &&
    presentedDeviceLinkToken.length === deviceLinkIngressToken.length &&
    crypto.timingSafeEqual(
      Buffer.from(presentedDeviceLinkToken),
      Buffer.from(deviceLinkIngressToken),
    ) &&
    isAllowedDeviceLinkHttpsPath(requestUrl)
  ) {
    return allowRequest(config, requestUrl, {
      ingress: 'device_link_https',
    });
  }

  const context = extractRequestContext(requestUrl, requestHeaders);
  let dynamicPolicy = null;
  let dynamicPolicyError = null;
  if (
    typeof resolveWorkspaceCapabilityPolicy === 'function' &&
    context.workspaceId &&
    context.capabilityCode
  ) {
    try {
      dynamicPolicy = await resolveWorkspaceCapabilityPolicy({
        workspaceId: context.workspaceId,
        capabilityCode: context.capabilityCode,
      });
    } catch (error) {
      dynamicPolicyError = error instanceof Error ? error.message : 'policy_resolution_failed';
    }
  }

  const basePathAllowed = isGatewayPathAllowed(requestUrl, config, requestMethod);
  const dynamicPathAllowed = Array.isArray(dynamicPolicy?.allowedPathRules)
    ? dynamicPolicy.allowedPathRules.some((rule) =>
        matchesRule(context.path, rule, requestMethod))
    : false;
  const controlPlanePathAllowed = Boolean(
    dynamicPolicy?.capabilityAllowed
    && context.gatewayControlPlaneTargeted
    && isMobileWorkbenchGatewayControlPlanePathAllowed(context.path, requestMethod)
  );
  if (!basePathAllowed && !dynamicPathAllowed && !controlPlanePathAllowed) {
    return denyRequest('mobile_workbench_gateway_path_not_allowed', 404, requestUrl, {
      context,
      policy_error: dynamicPolicyError || undefined,
    });
  }

  if (dynamicPolicy && dynamicPolicy.supported === false) {
    return denyRequest('mobile_workbench_gateway_path_not_allowed', 404, requestUrl, {
      context,
    });
  }

  if (isGatewayPolicyEnabled(config)) {
    const accessToken = parseAccessTokenFromHeaders(requestHeaders);
    if (!accessToken) {
      return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
        reason_code: 'missing_access_token',
        context,
      });
    }

    const {
      claims,
      header,
      signature,
      signingInput,
      error: claimsError,
    } = parseAccessJwtToken(accessToken);
    if (!claims || claimsError) {
      return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
        reason_code: claimsError || 'invalid_access_token',
        context,
        claims_error: claimsError,
      });
    }

    if (isJwtTokenExpired(claims, Math.floor(Date.now() / 1000), config.jwtClockSkewSeconds)) {
      return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
        reason_code: 'expired_or_not_ready_token',
        context,
      });
    }

    const signatureResult = verifyJwtSignature(
      header,
      signature,
      signingInput,
      config.jwtPublicKey,
      config.jwtVerifyRequired,
    );
    if (!signatureResult.valid) {
      return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
        reason_code: signatureResult.reason || 'invalid_access_token_signature',
        context,
      });
    }

    if (!isAudienceMatch(config.jwtAudience, claims.aud)) {
      return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
        reason_code: 'invalid_access_token_audience',
        context,
        claim_audience: claims.aud || null,
      });
    }

    if (!isIssuerMatch(config.jwtIssuer, claims.iss)) {
      return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
        reason_code: 'invalid_access_token_issuer',
        context,
        claim_issuer: claims.iss || null,
      });
    }

    const email = toLowerTrimmed(normalizeClaimValue(claims.email || claims.preferred_username || claims.upn || claims.sub));
    const groups = normalizeClaimList(claims.groups || claims.group || []);

    const emailAllowed = config.allowlistEmails.length > 0
      ? isRequestInAllowlist(email, config.allowlistEmails)
      : true;
    const groupAllowed = config.allowlistGroups.length > 0
      ? groups.some((group) => isRequestInAllowlist(group, config.allowlistGroups))
      : true;

    if (!emailAllowed && !groupAllowed) {
      return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
        reason_code: 'email_not_allowed',
        context,
        claim_email: email || null,
        claim_groups: groups,
      });
    }

    const claimWorkspaceId = normalizeClaimValue(claims.workspace_id || claims.workspaceId || claims.wsid);
    const workspaceId = toLowerTrimmed(context.workspaceId || claimWorkspaceId);
    const hasWorkspaceScope = Boolean(context.workspaceId || claimWorkspaceId);
    if (
      config.workspaceAllowlist.length > 0 &&
      hasWorkspaceScope &&
      !isRequestInAllowlist(workspaceId, config.workspaceAllowlist)
    ) {
      return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
        reason_code: 'workspace_not_allowed',
        context,
        claim_workspace_id: workspaceId || null,
      });
    }

    if (dynamicPolicy && !dynamicPolicy.capabilityAllowed) {
      return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
        reason_code: 'capability_not_allowed',
        context,
        claim_email: email || null,
      });
    }

    return allowRequest(config, requestUrl, {
      context,
      claims_email: email || null,
    });
  }

  if (dynamicPolicy && !dynamicPolicy.capabilityAllowed) {
    return denyRequest('mobile_workbench_gateway_access_denied', 403, requestUrl, {
      reason_code: 'capability_not_allowed',
      context,
    });
  }

  return allowRequest(config, requestUrl, {
    context,
    policy_error: dynamicPolicyError || undefined,
  });
}

export function resolveMobileWorkbenchGatewayConfig(env = process.env) {
  const enabled = String(env.MOBILE_WORKBENCH_GATEWAY_ENABLED || '').trim() === '1';
  const rawAdditionalRules = splitAdditionalRules(env.MOBILE_WORKBENCH_GATEWAY_EXTRA_PATH_RULES);
  const allowlistEmails = splitCommaSeparatedValues(env[ALLOWLIST_EMAIL_ENV]);
  const allowlistGroups = splitCommaSeparatedValues(env[ALLOWLIST_GROUP_ENV]);
  const workspaceAllowlist = splitCommaSeparatedValues(env[WORKSPACE_ALLOWLIST_ENV]);
  const publicOrigin = String(env[PUBLIC_ORIGIN_ENV] || '').trim().replace(/\/+$/, '');
  const jwtAudience = splitCommaSeparatedValues(env[JWT_AUDIENCE_ENV]);
  const jwtIssuer = splitCommaSeparatedValues(env[JWT_ISSUER_ENV]);
  const jwtClockSkewSeconds = parseClockSkew(env[JWT_CLOCK_SKEW_ENV]);

  const publicKeySource = readPublicKeySource(
    env[JWT_PUBLIC_KEY_FILE_ENV],
    env[JWT_PUBLIC_KEY_ENV],
  );
  const jwtVerifyRequired = isTruthyEnvValue(env[JWT_REQUIRE_SIGNATURE_VERIFICATION_ENV]);
  const jwtVerifyEnabled = jwtVerifyRequired && Boolean(publicKeySource.value) && !publicKeySource.error;

  const errors = [];
  const extraAllowedPathRules = rawAdditionalRules
    .map((token) => normalizePathPattern(token, errors))
    .filter(Boolean);

  if (publicKeySource.error) {
    errors.push(publicKeySource.error);
  }
  if (
    isTruthyEnvValue(env[JWT_REQUIRE_SIGNATURE_VERIFICATION_ENV]) &&
    !publicKeySource.value
  ) {
    errors.push('MOBILE_WORKBENCH_GATEWAY_JWT_SIGNATURE_VERIFICATION_ENABLED_BUT_PUBLIC_KEY_missing');
  }
  if (publicOrigin) {
    if (!publicOrigin.startsWith('https://')) {
      errors.push('MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN_must_use_https');
    } else if (isLoopbackPublicOrigin(publicOrigin)) {
      errors.push('MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN_must_not_use_loopback_host');
    }
  }

  if (!enabled) {
    return {
      enabled: false,
      reason: 'disabled',
      errors,
      allowedPathRules: [...DEFAULT_ALLOWED_PATH_RULES],
      extraAllowedPathRules: [],
      allowlistEmails,
      allowlistGroups,
      workspaceAllowlist,
      publicOrigin,
      jwtAudience,
      jwtIssuer,
      jwtClockSkewSeconds,
      jwtVerifyRequired: false,
      jwtVerifyEnabled: false,
      jwtPublicKey: null,
      hasJwtPublicKey: false,
    };
  }

  return {
    enabled: true,
    reason: errors.length ? 'enabled_with_invalid_rules' : 'enabled',
    errors,
    allowedPathRules: [...DEFAULT_ALLOWED_PATH_RULES],
    extraAllowedPathRules,
    allowlistEmails,
    allowlistGroups,
    workspaceAllowlist,
    publicOrigin,
    jwtAudience,
    jwtIssuer,
    jwtClockSkewSeconds,
    jwtVerifyRequired,
    jwtVerifyEnabled,
    jwtPublicKey: publicKeySource.value,
    hasJwtPublicKey: Boolean(publicKeySource.value),
  };
}

export function isMobileWorkbenchGatewayPathAllowed(
  requestUrl = '/',
  config = resolveMobileWorkbenchGatewayConfig(),
  requestMethod = 'GET',
) {
  return isGatewayPathAllowed(requestUrl, config, requestMethod);
}

export function isMobileWorkbenchGatewayConfigEnabled(env = process.env) {
  return resolveMobileWorkbenchGatewayConfig(env).enabled;
}

export function formatMobileWorkbenchGatewayConfig(config) {
  return {
    enabled: config.enabled,
    reason: config.reason,
    errors: [...(config.errors || [])],
    allowed_prefix_rules: config.allowedPathRules
      .filter((rule) => rule.type === 'prefix')
      .map((rule) => rule.value),
    allowed_regex_rules: config.allowedPathRules
      .filter((rule) => rule.type === 'regex')
      .map((rule) => rule.source || rule.value.toString()),
    extra_allowed_rules: (config.extraAllowedPathRules || [])
      .map((rule) => rule.source || rule.value.toString()),
    extra_allowed_rules_count: (config.extraAllowedPathRules || []).length,
    allowlist_emails: config.allowlistEmails || [],
    allowlist_groups: config.allowlistGroups || [],
    workspace_allowlist: config.workspaceAllowlist || [],
    public_origin: config.publicOrigin || null,
    jwt_audience: config.jwtAudience || [],
    jwt_issuer: config.jwtIssuer || [],
    jwt_clock_skew_seconds: Number.isFinite(Number(config.jwtClockSkewSeconds))
      ? Number(config.jwtClockSkewSeconds)
      : MAX_CLOCK_SKEW_SECONDS_DEFAULT,
    jwt_signature_verification_required: Boolean(config.jwtVerifyRequired),
    jwt_verify_enabled: Boolean(config.jwtVerifyEnabled),
    jwt_public_key_configured: Boolean(config.jwtPublicKey),
    gateway_policy_enabled: isGatewayPolicyEnabled(config),
  };
}
