import {
  createRemoteWorkspacePathRules,
  isCapabilityStorageMediaPath,
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

export function isFixedRemoteWorkspacePathAllowed(pathname = '/', requestMethod = 'GET') {
  return REMOTE_WORKSPACE_PATH_RULES.some((rule) => matchesRule(pathname, rule, requestMethod));
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
    || /^\/workspaces\/[^/]+\/capability-ui-hosts\/mindscape_cloud_integration(?:\/.*)?\/?$/.test(pathname)
    || /^\/api\/v1\/(?:admin|providers?|deploy)(?:\/|$)/.test(pathname)
    || /^\/api\/v1\/capability-packs\/(?:install|install-from-file|install-from-cloud|install-jobs)(?:\/|$)/.test(pathname)
  );
}
