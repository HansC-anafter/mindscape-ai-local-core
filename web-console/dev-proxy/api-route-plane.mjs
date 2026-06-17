const CONTROL_EXACT_PATHS = new Set([
  '/api/v1/capability-packs/install-from-file',
  '/api/v1/capability-packs/install-from-cloud',
  '/api/v1/capability-packs/installed-capabilities',
  '/api/v1/system-settings/restart',
]);

const CONTROL_PREFIXES = [
  '/api/v1/admin/',
  '/api/v1/capability-packs/install-jobs/',
  '/api/v1/capability-packs/installed-capabilities/',
  '/api/v1/cloud-providers/',
  '/api/v1/deployment/',
  '/api/v1/settings/extensions/',
];

const CONTROL_PATTERNS = [
  /^\/api\/v1\/workspaces\/[^/]+\/device-bindings(?:\/|$)/,
  /^\/api\/v1\/workspaces\/[^/]+\/projects\/[^/]+\/deploy(?:\/|$)/,
];

const EXECUTION_EXACT_PATHS = new Set([
  '/api/v1/host-runtime/status',
]);

const EXECUTION_PATTERNS = [
  /^\/api\/v1\/workspaces\/[^/]+\/host-runtime(?:\/|$)/,
];

export function resolveApiRoutePlane(requestUrl = '/') {
  const parsed = new URL(requestUrl, 'http://localhost');
  const { pathname } = parsed;
  if (pathname.startsWith('/api/v1/media/')) {
    return {
      plane: 'media',
      serviceId: 'local_core.media_proxy',
      reason: 'media_proxy',
    };
  }
  if (
    EXECUTION_EXACT_PATHS.has(pathname) ||
    EXECUTION_PATTERNS.some((pattern) => pattern.test(pathname))
  ) {
    return {
      plane: 'execution',
      serviceId: 'local_core.execution_api',
      reason: 'host_runtime_session_gateway',
    };
  }
  if (
    CONTROL_EXACT_PATHS.has(pathname) ||
    CONTROL_PREFIXES.some((prefix) => pathname.startsWith(prefix)) ||
    CONTROL_PATTERNS.some((pattern) => pattern.test(pathname))
  ) {
    return {
      plane: 'control',
      serviceId: 'local_core.control_api',
      reason: 'control_mutation_or_admin',
    };
  }
  return {
    plane: 'execution',
    serviceId: 'local_core.execution_api',
    reason: 'default_execution_api',
  };
}
