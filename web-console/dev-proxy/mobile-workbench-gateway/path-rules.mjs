import {
  createDefaultCapabilityGatewayPathRules,
  createDefaultGatewayWorkspaceSupportRules,
} from '../mobile-workbench-gateway-capability-rules.mjs';
import {
  GATEWAY_CONTROL_CAPABILITY_CODE,
  GATEWAY_CONTROL_COMPONENT_CODE,
  READ_ONLY_GATEWAY_METHODS,
} from './constants.mjs';
import {
  normalizeRequestMethod,
  toLowerTrimmed,
} from './normalizers.mjs';

export const DEFAULT_ALLOWED_PATH_RULES = [
  { type: 'prefix', value: '/favicon.ico' },
  { type: 'prefix', value: '/healthz' },
  { type: 'prefix', value: '/api/healthz' },
  { type: 'prefix', value: '/_next/' },
  ...createDefaultCapabilityGatewayPathRules(),
  ...createDefaultGatewayWorkspaceSupportRules(),
];

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

export function isLoopbackPublicOrigin(publicOrigin = '') {
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

function isRegexToken(token = '') {
  return String(token || '').startsWith('regex:');
}

export function normalizePathPattern(token, errors = []) {
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

export function isGatewayControlCapabilityCode(value = '') {
  return toLowerTrimmed(value) === GATEWAY_CONTROL_CAPABILITY_CODE;
}

export function isGatewayControlComponentCode(value = '') {
  return String(value || '').trim() === GATEWAY_CONTROL_COMPONENT_CODE;
}

export function isGatewayControlPolicyPath(pathname = '') {
  return /^\/api\/v1\/capabilities\/mindscape_cloud_integration\/mobile-workbench-gateway\/workspaces\/[^/]+\/policy$/.test(pathname);
}

export function isGatewayControlObservabilityPath(pathname = '') {
  return /^\/api\/v1\/host\/services\/mobile-workbench-gateway\/(?:health|summary|audit)$/.test(pathname);
}

export function isMobileWorkbenchGatewayControlPlanePathAllowed(pathname = '/', requestMethod = 'GET') {
  return CONTROL_PLANE_ALLOWED_PATH_RULES.some((rule) => matchesRule(pathname, rule, requestMethod));
}

export function matchesRule(pathname, rule, requestMethod = 'GET') {
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

export function isGatewayPathAllowed(
  requestUrl = '/',
  config,
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
