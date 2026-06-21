import crypto from 'node:crypto';

import {
  DEVICE_LINK_INGRESS_TOKEN_HEADER,
  isAllowedDeviceLinkHttpsPath,
} from '../device-link-https.mjs';
import {
  isGatewayPolicyEnabled,
  resolveMobileWorkbenchGatewayConfig,
} from './config.mjs';
import {
  extractRequestContext,
} from './context.mjs';
import {
  isAudienceMatch,
  isIssuerMatch,
  isJwtTokenExpired,
  normalizeClaimList,
  parseAccessJwtToken,
  parseAccessTokenFromHeaders,
  verifyJwtSignature,
} from './jwt.mjs';
import {
  normalizeClaimValue,
  toLowerTrimmed,
} from './normalizers.mjs';
import {
  isGatewayPathAllowed,
  isMobileWorkbenchGatewayControlPlanePathAllowed,
  matchesRule,
} from './path-rules.mjs';

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

function isDeviceLinkIngressAllowed({
  requestUrl,
  requestHeaders,
  deviceLinkIngressToken,
}) {
  const presentedDeviceLinkToken = String(
    requestHeaders?.[DEVICE_LINK_INGRESS_TOKEN_HEADER] ||
    requestHeaders?.[DEVICE_LINK_INGRESS_TOKEN_HEADER.toLowerCase()] ||
    '',
  );
  return Boolean(
    deviceLinkIngressToken &&
    presentedDeviceLinkToken.length === deviceLinkIngressToken.length &&
    crypto.timingSafeEqual(
      Buffer.from(presentedDeviceLinkToken),
      Buffer.from(deviceLinkIngressToken),
    ) &&
    isAllowedDeviceLinkHttpsPath(requestUrl)
  );
}

function evaluateConfiguredPolicy({
  config,
  claims,
  header,
  signature,
  signingInput,
  claimsError,
  context,
  requestUrl,
  dynamicPolicy = null,
  requireDynamicCapability = false,
}) {
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

  if (requireDynamicCapability && dynamicPolicy && !dynamicPolicy.capabilityAllowed) {
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

  if (isDeviceLinkIngressAllowed({ requestUrl, requestHeaders, deviceLinkIngressToken })) {
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

  return evaluateConfiguredPolicy({
    config,
    ...parseAccessJwtToken(accessToken),
    context,
    requestUrl,
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

  if (isDeviceLinkIngressAllowed({ requestUrl, requestHeaders, deviceLinkIngressToken })) {
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

    return evaluateConfiguredPolicy({
      config,
      ...parseAccessJwtToken(accessToken),
      context,
      requestUrl,
      dynamicPolicy,
      requireDynamicCapability: true,
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
