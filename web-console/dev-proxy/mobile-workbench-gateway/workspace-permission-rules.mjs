const READ_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
const MUTATING_SHARED_WORKSPACE_PATHS = [
  /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions$/,
  /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions\/[^/]+\/(?:turns|interrupt)$/,
  /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions\/[^/]+\/approvals\/[^/]+$/,
  /^\/api\/v1\/workspaces\/[^/]+\/(?:host-runtime|agents)\/bridge-service\/(?:start|restart)$/,
  /^\/api\/v1\/workspaces\/[^/]+\/device-bindings\/(?:pairing-codes|control|[^/]+\/(?:control|revoke|media-sessions\/[^/]+\/signal))$/,
  /^\/api\/v1\/workspaces\/[^/]+\/device-bindings\/[^/]+\/media-sessions$/,
  /^\/api\/v1\/workspaces\/[^/]+\/device-bindings\/[^/]+\/media-sessions\/[^/]+\/(?:refresh|receiver\/start|stop)$/,
];

export function requiredWorkspacePermission(context, requestMethod) {
  if (!context || context.isBootAsset) {
    return null;
  }
  const method = String(requestMethod || 'GET').toUpperCase();
  if (READ_METHODS.has(method)) {
    return 'workspace.read';
  }
  if (context.capabilityCode) {
    return 'workspace.execute';
  }
  if (MUTATING_SHARED_WORKSPACE_PATHS.some((pattern) => pattern.test(context.path))) {
    return 'workspace.execute';
  }
  // A disallowed write still passes through the read permission boundary before
  // the path/method allowlist returns its indistinguishable 404.
  return 'workspace.read';
}
