const READ_ONLY_METHODS = ['GET', 'HEAD', 'OPTIONS'];
const CAPABILITY_STORAGE_MEDIA_PATH_PATTERN =
  /^\/api\/v1\/capabilities\/[^/]+\/storage\/[^/]+\/.+\.(?:apng|avif|gif|jpe?g|m4v|mov|mp4|png|webm|webp)$/i;
const RESERVED_LEGACY_API_ROOTS = new Set([
  'admin',
  'capability-packs',
  'deploy',
  'host',
  'host-resources',
  'host-runtime',
  'providers',
  'system-settings',
  'workspaces',
]);

function escapeRegexLiteral(value = '') {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function createCapabilityHostRule(capabilityCode) {
  const escaped = escapeRegexLiteral(capabilityCode);
  return {
    type: 'regex',
    value: new RegExp(`^/workspaces/[^/]+/capability-ui-hosts/${escaped}(?:/.*)?$`),
  };
}

function createCapabilityApiRule(apiPrefix) {
  const escaped = escapeRegexLiteral(apiPrefix).replace(/\/+$/, '');
  return {
    type: 'regex',
    value: new RegExp(`^${escaped}(?:/.*)?$`),
  };
}

export function isCapabilityOwnedApiPrefix(apiPrefix, capabilityCode) {
  const code = String(capabilityCode || '').trim().toLowerCase();
  const prefix = String(apiPrefix || '').trim().replace(/\/+$/, '');
  if (!code || !/^[a-z0-9][a-z0-9_-]*$/.test(code) || !prefix) {
    return false;
  }
  const aliases = new Set([code, code.replaceAll('_', '-')]);
  const ownedRoots = Array.from(aliases, (alias) => `/api/v1/capabilities/${alias}`);
  if (!RESERVED_LEGACY_API_ROOTS.has(code)) {
    for (const alias of aliases) {
      if (!RESERVED_LEGACY_API_ROOTS.has(alias)) {
        ownedRoots.push(`/api/v1/${alias}`);
      }
    }
  }
  return ownedRoots.some((root) => prefix === root || prefix.startsWith(`${root}/`));
}

function createInstalledCapabilityMetadataRule(capabilityCode) {
  const escaped = escapeRegexLiteral(capabilityCode);
  return {
    type: 'regex',
    value: new RegExp(
      `^/api/v1/capability-packs/installed-capabilities/${escaped}(?:/(?:ui-components|workspace-tools))?$`,
    ),
    methods: READ_ONLY_METHODS,
  };
}

function createInstalledCapabilityAssetsRule(capabilityCode) {
  const escaped = escapeRegexLiteral(capabilityCode);
  return {
    type: 'regex',
    value: new RegExp(
      `^/api/v1/capability-packs/installed-capabilities/${escaped}/ui-assets/.+`,
    ),
    methods: READ_ONLY_METHODS,
  };
}

function createLegacyCapabilityAssetsRule(capabilityCode) {
  const escaped = escapeRegexLiteral(capabilityCode);
  return {
    type: 'regex',
    value: new RegExp(`^/api/v1/capability-packs/${escaped}/ui-assets/.+`),
    methods: READ_ONLY_METHODS,
  };
}

function createCapabilityHostRuntimeAssetRule() {
  return {
    type: 'regex',
    value: /^\/__mindscape-capability-host\/(?:app-layout\.css|react\.production\.min\.js|react-dom\.production\.min\.js|shell-runtime\.browser\.js)$/,
    methods: READ_ONLY_METHODS,
  };
}

export function isCapabilityStorageMediaPath(pathname = '') {
  return CAPABILITY_STORAGE_MEDIA_PATH_PATTERN.test(String(pathname || ''));
}

export function createCapabilityGatewayPathRules({
  capabilityCode,
  hostRouteTemplate = null,
  apiPrefixes = [],
  requestScopeContract = null,
}) {
  const normalizedCapabilityCode = String(capabilityCode || '').trim().toLowerCase();
  if (!normalizedCapabilityCode || !/^[a-z0-9][a-z0-9_-]*$/.test(normalizedCapabilityCode)) {
    return [];
  }
  const canonicalHostRouteTemplate =
    `/workspaces/{workspaceId}/capability-ui-hosts/${normalizedCapabilityCode}`;
  if (hostRouteTemplate !== canonicalHostRouteTemplate) {
    return [];
  }
  const normalizedApiPrefixes = requestScopeContract === 'explicit_workspace_v1'
    ? Array.from(new Set(
        apiPrefixes.map((prefix) => String(prefix || '').trim().replace(/\/+$/, '')),
      ))
    : [];
  if (normalizedApiPrefixes.some((prefix) => (
    !isCapabilityOwnedApiPrefix(prefix, normalizedCapabilityCode)
  ))) {
    return [];
  }
  return [
    createCapabilityHostRule(normalizedCapabilityCode),
    ...normalizedApiPrefixes.map(createCapabilityApiRule),
    createInstalledCapabilityMetadataRule(normalizedCapabilityCode),
    createInstalledCapabilityAssetsRule(normalizedCapabilityCode),
    createLegacyCapabilityAssetsRule(normalizedCapabilityCode),
    createCapabilityHostRuntimeAssetRule(),
  ];
}

export function createRemoteWorkspacePathRules() {
  return [
    { type: 'regex', value: /^\/workspaces\/[^/]+\/?$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/summary$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/executions(?:\/.*)?$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/tasks(?:\/.*)?$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/events\/stream$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/motion-reference-profiles\/selection$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions$/, methods: ['GET', 'HEAD', 'OPTIONS', 'POST'] },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions\/[^/]+(?:\/events|\/stream)?$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions\/[^/]+\/(?:turns|interrupt)$/, methods: ['OPTIONS', 'POST'] },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions\/[^/]+\/approvals\/[^/]+$/, methods: ['OPTIONS', 'POST'] },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/(?:host-runtime|agents)\/bridge-service$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/(?:host-runtime|agents)\/bridge-service\/(?:start|restart)$/, methods: ['OPTIONS', 'POST'] },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/device-bindings\/(?:pairing-codes|control|[^/]+\/(?:control|revoke|media-sessions\/[^/]+\/signal))$/ },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/device-bindings\/sessions$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/device-bindings\/[^/]+\/media-sessions$/, methods: ['GET', 'HEAD', 'OPTIONS', 'POST'] },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/device-bindings\/[^/]+\/media-sessions\/[^/]+\/(?:refresh|receiver\/start|stop)$/, methods: ['OPTIONS', 'POST'] },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/media-assets\/[^/]+\/preview-(?:content|data)$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/device-link\/(?!health$|__test__$)[^/]+$/, methods: READ_ONLY_METHODS },
    { type: 'regex', value: /^\/api\/v1\/capability-packs\/installed-capabilities$/, methods: ['GET'] },
    { type: 'regex', value: CAPABILITY_STORAGE_MEDIA_PATH_PATTERN, methods: READ_ONLY_METHODS },
  ];
}

export function requiresExplicitCapabilityQuery(pathname = '') {
  return /^\/api\/v1\/workspaces\/[^/]+\/motion-reference-profiles\/selection$/.test(
    String(pathname || ''),
  );
}
