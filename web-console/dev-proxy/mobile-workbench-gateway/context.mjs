import {
  isCapabilityStorageMediaPath,
} from '../mobile-workbench-gateway-capability-rules.mjs';
import {
  decodeURIComponentSafe,
  normalizeCapabilityCodeFromApiSegment,
  normalizeClaimValue,
} from './normalizers.mjs';
import {
  isGatewayControlCapabilityCode,
  isGatewayControlComponentCode,
  isGatewayControlObservabilityPath,
  isGatewayControlPolicyPath,
} from './path-rules.mjs';

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
    if (isCapabilityStorageMediaPath(pathname)) {
      capabilityFromFallback = true;
    }
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
    /^\/api\/v1\/host-resources\/lanes$/.test(pathname) ||
    /^\/api\/v1\/host-resources\/queue-utilization$/.test(pathname)
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

export function extractRequestContext(requestUrl = '/', requestHeaders = {}) {
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
