const READ_ONLY_GATEWAY_METHODS = ['GET', 'HEAD', 'OPTIONS'];
const CAPABILITY_STORAGE_MEDIA_PATH_PATTERN =
  /^\/api\/v1\/capabilities\/[^/]+\/storage\/[^/]+\/.+\.(?:apng|avif|gif|jpe?g|m4v|mov|mp4|png|webm|webp)$/i;

function escapeRegexLiteral(value = '') {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function createCapabilityHostRule(capabilityCode) {
  const escapedCapabilityCode = escapeRegexLiteral(capabilityCode);
  return {
    type: 'regex',
    value: new RegExp(`^/workspaces/[^/]+/capability-ui-hosts/${escapedCapabilityCode}(?:/.*)?$`),
  };
}

function createCapabilityApiRule(apiPrefix) {
  const escapedApiPrefix = escapeRegexLiteral(apiPrefix).replace(/\/+$/, '');
  return {
    type: 'regex',
    value: new RegExp(`^${escapedApiPrefix}(?:/.*)?$`),
  };
}

export function isCapabilityStorageMediaPath(pathname = '') {
  return CAPABILITY_STORAGE_MEDIA_PATH_PATTERN.test(String(pathname || ''));
}

function createCapabilityStorageMediaRule() {
  return {
    type: 'regex',
    value: CAPABILITY_STORAGE_MEDIA_PATH_PATTERN,
    methods: READ_ONLY_GATEWAY_METHODS,
  };
}

function createInstalledCapabilityMetadataRule(capabilityCode) {
  const escapedCapabilityCode = escapeRegexLiteral(capabilityCode);
  return {
    type: 'regex',
    value: new RegExp(
      `^/api/v1/capability-packs/installed-capabilities/${escapedCapabilityCode}(?:/(?:ui-components|workspace-tools|mobile-workbench-gateway-support))?$`,
    ),
  };
}

function createInstalledCapabilityAssetsRule(capabilityCode) {
  const escapedCapabilityCode = escapeRegexLiteral(capabilityCode);
  return {
    type: 'regex',
    value: new RegExp(
      `^/api/v1/capability-packs/installed-capabilities/${escapedCapabilityCode}/ui-assets/.+`,
    ),
  };
}

export function createCapabilityGatewayPathRules({
  capabilityCode,
  apiPrefixes = [],
}) {
  const normalizedCapabilityCode = String(capabilityCode || '').trim();
  if (!normalizedCapabilityCode) {
    return [];
  }

  const normalizedApiPrefixes = Array.from(new Set(
    (apiPrefixes || [])
      .map((prefix) => String(prefix || '').trim())
      .filter(Boolean),
  ));

  return [
    createCapabilityHostRule(normalizedCapabilityCode),
    ...normalizedApiPrefixes.map((prefix) => createCapabilityApiRule(prefix)),
    createInstalledCapabilityMetadataRule(normalizedCapabilityCode),
    createInstalledCapabilityAssetsRule(normalizedCapabilityCode),
  ];
}

export function createDefaultCapabilityGatewayPathRules() {
  return [
    ...createCapabilityGatewayPathRules({
      capabilityCode: 'ig',
      apiPrefixes: ['/api/v1/ig'],
    }),
    ...createCapabilityGatewayPathRules({
      capabilityCode: 'makeup_practice_coach',
      apiPrefixes: ['/api/v1/capabilities/makeup_practice_coach'],
    }),
    ...createCapabilityGatewayPathRules({
      capabilityCode: 'yogacoach',
      apiPrefixes: ['/api/v1/capabilities/yogacoach'],
    }),
  ];
}

export function createDefaultGatewayWorkspaceSupportRules() {
  return [
    { type: 'regex', value: /^\/api\/v1\/capability-packs\/installed-capabilities$/ },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/summary$/ },
    { type: 'regex', value: /^\/api\/v1\/workspaces\/[^/]+\/executions(?:\/.*)?$/ },
    {
      type: 'regex',
      value: /^\/api\/v1\/host-runtime\/status$/,
      methods: READ_ONLY_GATEWAY_METHODS,
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions$/,
      methods: ['GET', 'HEAD', 'OPTIONS', 'POST'],
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions\/[^/]+(?:\/events|\/stream)?$/,
      methods: READ_ONLY_GATEWAY_METHODS,
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions\/[^/]+\/(?:turns|interrupt)$/,
      methods: ['OPTIONS', 'POST'],
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/sessions\/[^/]+\/approvals\/[^/]+$/,
      methods: ['OPTIONS', 'POST'],
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/bridge-service$/,
      methods: READ_ONLY_GATEWAY_METHODS,
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/host-runtime\/bridge-service\/(?:start|restart)$/,
      methods: ['OPTIONS', 'POST'],
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/agents\/bridge-service$/,
      methods: READ_ONLY_GATEWAY_METHODS,
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/agents\/bridge-service\/(?:start|restart)$/,
      methods: ['OPTIONS', 'POST'],
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/tasks(?:\/.*)?$/,
      methods: READ_ONLY_GATEWAY_METHODS,
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/events\/stream$/,
      methods: READ_ONLY_GATEWAY_METHODS,
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/workspaces\/[^/]+\/device-bindings\/(?:pairing-codes|control|[^/]+\/(?:control|revoke|media-sessions\/[^/]+\/signal))$/,
    },
    {
      type: 'regex',
      value: /^\/device-link\/(?!health$|__test__$)[^/]+$/,
      methods: READ_ONLY_GATEWAY_METHODS,
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/system-settings\/keyboard-shortcuts$/,
      methods: READ_ONLY_GATEWAY_METHODS,
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/host-resources\/lanes$/,
      methods: READ_ONLY_GATEWAY_METHODS,
    },
    {
      type: 'regex',
      value: /^\/api\/v1\/host-resources\/queue-utilization$/,
      methods: READ_ONLY_GATEWAY_METHODS,
    },
    createCapabilityStorageMediaRule(),
    { type: 'regex', value: /^\/api\/v1\/capability-packs\/[^/]+\/ui-assets\// },
  ];
}
