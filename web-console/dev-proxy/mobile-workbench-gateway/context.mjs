import {
  decodeURIComponentSafe,
  normalizeCapabilityCodeFromApiSegment,
  normalizeClaimValue,
} from './normalizers.mjs';
import {
  isGatewayControlObservabilityPath,
  isGatewayControlPolicyPath,
  isPublicBootAssetPath,
  isRemoteControlPlanePath,
} from './path-rules.mjs';

function normalizeIdentifier(value) {
  const normalized = normalizeClaimValue(value);
  if (!normalized || normalized.length > 128 || /[\u0000-\u001f\u007f]/.test(normalized)) {
    return null;
  }
  return normalized;
}

function addCandidate(target, value, source) {
  if (value === undefined || value === null) {
    return;
  }
  const normalized = normalizeIdentifier(decodeURIComponentSafe(String(value)));
  target.push({ value: normalized, source });
}

function addSearchParameterCandidates(target, searchParams, parameterName) {
  for (const value of searchParams.getAll(parameterName)) {
    addCandidate(target, value, `query.${parameterName}`);
  }
}

function resolveCandidates(candidates, field) {
  if (candidates.some((candidate) => !candidate.value)) {
    return { value: null, conflicts: [`invalid_${field}`] };
  }
  const unique = Array.from(new Set(candidates.map((candidate) => candidate.value)));
  if (unique.length > 1) {
    return { value: null, conflicts: [`conflicting_${field}`] };
  }
  return { value: unique[0] || null, conflicts: [] };
}

function parseRequestUrl(requestUrl) {
  try {
    return new URL(requestUrl, 'http://localhost');
  } catch {
    return new URL('http://localhost/');
  }
}

function hasCapabilityHostPath(pathname) {
  return /^\/workspaces\/[^/]+\/capability-ui-hosts\/[^/]+(?:\/|$)/.test(pathname);
}

function hasExactCapabilityHostDocumentPath(pathname) {
  return /^\/workspaces\/[^/]+\/capability-ui-hosts\/[^/]+\/?$/.test(pathname);
}

function readExactRequestHeader(requestHeaders, headerName) {
  const entries = Object.entries(requestHeaders || {}).filter(
    ([name]) => String(name).toLowerCase() === headerName,
  );
  if (entries.length !== 1 || Array.isArray(entries[0][1])) {
    return null;
  }
  const normalized = String(entries[0][1] || '').trim().toLowerCase();
  return normalized || null;
}

function hasUpgradeRequestHeaders(requestHeaders) {
  const upgrade = readExactRequestHeader(requestHeaders, 'upgrade');
  const connection = readExactRequestHeader(requestHeaders, 'connection');
  return Boolean(
    upgrade
    || connection?.split(',').some((token) => token.trim() === 'upgrade'),
  );
}

function isSelfScopedTopLevelDocumentNavigation(primary, requestHeaders, requestMethod) {
  return (
    ['GET', 'HEAD'].includes(String(requestMethod || 'GET').toUpperCase())
    && readExactRequestHeader(requestHeaders, 'sec-fetch-mode') === 'navigate'
    && readExactRequestHeader(requestHeaders, 'sec-fetch-dest') === 'document'
    && !hasUpgradeRequestHeaders(requestHeaders)
    && primary.conflicts.length === 0
    && Boolean(primary.workspaceId)
    && Boolean(primary.capabilityCode)
    && hasExactCapabilityHostDocumentPath(primary.path)
    && !primary.isBootAsset
    && !primary.isRemoteControlPlane
    && !primary.gatewayPolicyTargeted
    && !primary.gatewayObservabilityTargeted
  );
}

function readExactSearchParameter(parsedUrl, name) {
  const values = parsedUrl.searchParams.getAll(name);
  return values.length === 1 ? values[0] : null;
}

function isCanonicalCapabilityHandoff({
  requestUrl,
  requestMethod,
  primary,
  refererUrl,
  referer,
}) {
  if (!['GET', 'HEAD'].includes(String(requestMethod || 'GET').toUpperCase())) {
    return false;
  }
  if (
    !primary.workspaceId
    || !referer.workspaceId
    || primary.workspaceId !== referer.workspaceId
    || !primary.capabilityCode
    || !referer.capabilityCode
    || primary.capabilityCode === referer.capabilityCode
    || !hasCapabilityHostPath(primary.path)
    || !hasCapabilityHostPath(referer.path)
  ) {
    return false;
  }

  const parsedRequest = parseRequestUrl(requestUrl);
  const handoffTarget = readExactSearchParameter(parsedRequest, 'handoff_target');
  const returnTo = readExactSearchParameter(parsedRequest, 'return_to');
  if (
    normalizeIdentifier(handoffTarget)?.toLowerCase() !== referer.capabilityCode
    || !returnTo
    || returnTo.length > 4096
    || !returnTo.startsWith('/')
    || returnTo.startsWith('//')
    || /[\u0000-\u001f\u007f]/.test(returnTo)
  ) {
    return false;
  }

  let parsedReturnTo;
  try {
    parsedReturnTo = new URL(returnTo, 'http://mindscape.local');
  } catch {
    return false;
  }
  if (parsedReturnTo.origin !== 'http://mindscape.local') {
    return false;
  }
  const returnContext = extractSingleUrlContext(parsedReturnTo.href, requestMethod);
  return (
    returnContext.conflicts.length === 0
    && returnContext.workspaceId === primary.workspaceId
    && returnContext.capabilityCode === referer.capabilityCode
    && parsedReturnTo.pathname === refererUrl.pathname
    && parsedReturnTo.search === refererUrl.search
  );
}

function extractSingleUrlContext(requestUrl = '/', requestMethod = 'GET') {
  const parsed = parseRequestUrl(requestUrl);
  const pathname = parsed.pathname || '/';
  const workspaceCandidates = [];
  const capabilityCandidates = [];
  const componentCandidates = [];
  const targetCapabilityCandidates = [];

  addSearchParameterCandidates(workspaceCandidates, parsed.searchParams, 'workspace_id');
  addSearchParameterCandidates(workspaceCandidates, parsed.searchParams, 'workspaceId');
  addSearchParameterCandidates(capabilityCandidates, parsed.searchParams, 'capability_code');
  addSearchParameterCandidates(capabilityCandidates, parsed.searchParams, 'capabilityCode');
  addSearchParameterCandidates(componentCandidates, parsed.searchParams, 'component');
  addSearchParameterCandidates(targetCapabilityCandidates, parsed.searchParams, 'target_capability');
  addSearchParameterCandidates(targetCapabilityCandidates, parsed.searchParams, 'targetCapability');

  const workspacePathMatch = /^\/workspaces\/([^/]+)(?:\/|$)/.exec(pathname);
  const workspaceApiMatch = /^\/api\/v1\/workspaces\/([^/]+)(?:\/|$)/.exec(pathname);
  addCandidate(workspaceCandidates, workspacePathMatch?.[1], 'route.workspace');
  addCandidate(workspaceCandidates, workspaceApiMatch?.[1], 'route.workspace_api');

  const capabilityHostMatch = /^\/workspaces\/[^/]+\/capability-ui-hosts\/([^/]+)(?:\/|$)/.exec(pathname);
  if (capabilityHostMatch) {
    addCandidate(capabilityCandidates, capabilityHostMatch[1], 'route.capability_host');
  }
  const capabilityApiMatch = /^\/api\/v1\/capabilities\/([^/]+)(?:\/|$)/.exec(pathname);
  if (capabilityApiMatch) {
    addCandidate(
      capabilityCandidates,
      normalizeCapabilityCodeFromApiSegment(capabilityApiMatch[1]),
      'route.capability_api',
    );
  }
  const installedCapabilityMatch =
    /^\/api\/v1\/capability-packs\/installed-capabilities\/([^/]+)(?:\/|$)/.exec(pathname);
  addCandidate(capabilityCandidates, installedCapabilityMatch?.[1], 'route.installed_capability');
  const legacyAssetMatch = /^\/api\/v1\/capability-packs\/([^/]+)\/ui-assets\//.exec(pathname);
  addCandidate(capabilityCandidates, legacyAssetMatch?.[1], 'route.capability_asset');

  const workspace = resolveCandidates(workspaceCandidates, 'workspace_context');
  const capability = resolveCandidates(capabilityCandidates, 'capability_context');
  const component = resolveCandidates(componentCandidates, 'component_context');
  const targetCapability = resolveCandidates(
    targetCapabilityCandidates,
    'target_capability_context',
  );
  return {
    path: pathname,
    workspaceId: workspace.value,
    capabilityCode: capability.value?.toLowerCase() || null,
    componentCode: component.value,
    targetCapabilityCode: targetCapability.value,
    conflicts: [
      ...workspace.conflicts,
      ...capability.conflicts,
      ...component.conflicts,
      ...targetCapability.conflicts,
    ],
    isBootAsset: isPublicBootAssetPath(pathname, requestMethod),
    isRemoteControlPlane: isRemoteControlPlanePath(requestUrl),
    gatewayPolicyTargeted: isGatewayControlPolicyPath(pathname),
    gatewayObservabilityTargeted: isGatewayControlObservabilityPath(pathname),
  };
}

function resolveRefererHeader(requestHeaders) {
  const value = requestHeaders?.referer ?? requestHeaders?.referrer ?? null;
  if (Array.isArray(value)) {
    return value.length === 1 ? String(value[0] || '').trim() : '';
  }
  return String(value || '').trim();
}

function mergeContext(primary, referer, {
  inherit = false,
  canonicalCapabilityHandoff = false,
} = {}) {
  const conflicts = [...primary.conflicts, ...referer.conflicts];
  if (primary.workspaceId && referer.workspaceId && primary.workspaceId !== referer.workspaceId) {
    conflicts.push('referer_workspace_mismatch');
  }
  if (
    primary.capabilityCode
    && referer.capabilityCode
    && primary.capabilityCode !== referer.capabilityCode
    && !canonicalCapabilityHandoff
  ) {
    conflicts.push('referer_capability_mismatch');
  }
  return {
    ...primary,
    workspaceId: primary.workspaceId || (inherit ? referer.workspaceId : null),
    capabilityCode: primary.capabilityCode || (inherit ? referer.capabilityCode : null),
    conflicts: Array.from(new Set(conflicts)),
    refererPath: referer.path,
  };
}

export function extractRequestContext(
  requestUrl = '/',
  requestHeaders = {},
  { publicOrigin = '', requestMethod = 'GET' } = {},
) {
  const primary = extractSingleUrlContext(requestUrl, requestMethod);
  const refererHeader = resolveRefererHeader(requestHeaders);
  if (!refererHeader) {
    return primary;
  }
  let parsedReferer;
  try {
    parsedReferer = new URL(refererHeader);
  } catch {
    return { ...primary, conflicts: [...primary.conflicts, 'invalid_referer'] };
  }
  if (publicOrigin) {
    let expectedOrigin;
    try {
      expectedOrigin = new URL(publicOrigin).origin;
    } catch {
      expectedOrigin = '';
    }
    if (!expectedOrigin) {
      return { ...primary, conflicts: [...primary.conflicts, 'invalid_referer_origin'] };
    }
    if (parsedReferer.origin !== expectedOrigin) {
      if (isSelfScopedTopLevelDocumentNavigation(primary, requestHeaders, requestMethod)) {
        return primary;
      }
      return { ...primary, conflicts: [...primary.conflicts, 'invalid_referer_origin'] };
    }
  }
  const referer = extractSingleUrlContext(parsedReferer.href);
  return mergeContext(primary, referer, {
    inherit: primary.isBootAsset,
    canonicalCapabilityHandoff: isCanonicalCapabilityHandoff({
      requestUrl,
      requestMethod,
      primary,
      refererUrl: parsedReferer,
      referer,
    }),
  });
}

export function extractMobileWorkbenchGatewayRequestContext(requestUrl = '/', requestHeaders = {}, options = {}) {
  return extractRequestContext(requestUrl, requestHeaders, options);
}
