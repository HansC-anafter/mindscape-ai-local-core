import {
  createRemoteWorkspacePathRules,
  isCapabilityStorageMediaPath,
  requiresExplicitCapabilityQuery,
} from '../mobile-workbench-gateway-capability-rules.mjs';
import {
  normalizeRequestMethod,
} from './normalizers.mjs';

const REMOTE_WORKSPACE_PATH_RULES = createRemoteWorkspacePathRules();

export function matchesRule(pathname, rule, requestMethod = 'GET') {
  if (!rule) {
    return false;
  }
  const method = normalizeRequestMethod(requestMethod);
  if (Array.isArray(rule.methods) && !rule.methods.includes(method)) {
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

export function isPublicBootAssetPath(pathname = '/', requestMethod = 'GET') {
  const method = normalizeRequestMethod(requestMethod);
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    return false;
  }
  return pathname === '/favicon.ico' || pathname.startsWith('/_next/static/');
}

export function isInvitationAcceptancePath(
  pathname = '/',
  requestMethod = 'GET',
) {
  const method = String(requestMethod || 'GET').toUpperCase();
  return (
    (pathname === '/access/invitations/accept' && method === 'GET')
    || (
      pathname === '/api/v1/access-control/invitations/accept'
      && method === 'POST'
    )
  );
}

export function isFixedRemoteWorkspacePathAllowed(pathname = '/', requestMethod = 'GET') {
  return REMOTE_WORKSPACE_PATH_RULES.some((rule) => matchesRule(pathname, rule, requestMethod));
}

export function fixedRemoteWorkspacePathRequiresCapabilityQuery(pathname = '/') {
  return requiresExplicitCapabilityQuery(pathname);
}

export function isReadOnlyRemotePath(pathname = '/') {
  return isCapabilityStorageMediaPath(pathname)
    || /^\/api\/v1\/workspaces\/[^/]+\/media-assets\/[^/]+\/preview-(?:content|data)$/.test(pathname);
}

export function isGatewayControlPolicyPath(pathname = '') {
  return (
    /^\/api\/v1\/capabilities\/mindscape_cloud_integration\/mobile-workbench-gateway\/runtime-policy\/?$/.test(pathname)
    || /^\/api\/v1\/capabilities\/mindscape_cloud_integration\/mobile-workbench-gateway\/workspaces\/[^/]+\/policy\/?$/.test(pathname)
  );
}

export function isGatewayControlObservabilityPath(pathname = '') {
  return /^\/api\/v1\/host\/services\/mobile-workbench-gateway\/(?:health|summary|audit)\/?$/.test(pathname);
}

export function isRemoteControlPlanePath(requestUrl = '/') {
  let pathname = '/';
  try {
    pathname = new URL(requestUrl, 'http://localhost').pathname;
  } catch {
    pathname = String(requestUrl || '/').split('?')[0] || '/';
  }
  try {
    pathname = decodeURIComponent(pathname);
  } catch {
    return true;
  }
  return (
    isGatewayControlPolicyPath(pathname)
    || isGatewayControlObservabilityPath(pathname)
    || /^\/settings(?:\/|$)/.test(pathname)
    || /^\/api\/v1\/settings\/extensions(?:\/|$)/.test(pathname)
    || /^\/workspaces\/[^/]+\/capability-ui-hosts\/mindscape_cloud_integration(?:\/.*)?\/?$/.test(pathname)
    || /^\/api\/v1\/(?:admin|providers?|deploy)(?:\/|$)/.test(pathname)
    || /^\/api\/v1\/capability-packs\/(?:install|install-from-file|install-from-cloud|install-jobs)(?:\/|$)/.test(pathname)
    || /^\/api\/v1\/host-runtime\/status\/?$/.test(pathname)
    || /^\/api\/v1\/system-settings\/keyboard-shortcuts\/?$/.test(pathname)
    || /^\/api\/v1\/host-resources\/(?:lanes|queue-utilization)\/?$/.test(pathname)
  );
}
