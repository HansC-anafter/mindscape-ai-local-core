export const ACCESS_ASSERTION_HEADER = 'cf-access-jwt-assertion';

export const RUNTIME_ACCESS_POLICY_PATH =
  '/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/runtime-policy';
export const WORKSPACE_EFFECTIVE_POLICY_PATH_PREFIX =
  '/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/workspaces';

export const MAX_CLOCK_SKEW_SECONDS_DEFAULT = 30;
export const MAX_RUNTIME_POLICY_BYTES = 32 * 1024;
export const MAX_EFFECTIVE_POLICY_BYTES = 32 * 1024;
export const MAX_CAPABILITY_SUPPORT_BYTES = 1024;
export const MAX_GLOBAL_ADMINISTRATORS = 16;
export const MAX_WORKSPACE_PRINCIPALS = 64;
export const MAX_EFFECTIVE_PRINCIPALS = 80;
export const MAX_POLICY_CACHE_ENTRIES = 256;
export const MAX_SUPPORT_CACHE_ENTRIES = 256;
export const POLICY_TTL_MS = 15_000;
export const SUPPORT_TTL_MS = 60_000;
export const UPSTREAM_TIMEOUT_MS = 1_000;
export const MAX_POLICY_UPSTREAM_IN_FLIGHT = 4;
export const JWK_CACHE_MAX_AGE_MS = 300_000;
export const JWK_UNKNOWN_KID_COOLDOWN_MS = 30_000;
export const MAX_JWK_SET_BYTES = 64 * 1024;
export const MAX_JWK_KEYS = 32;

export const REMOTE_ACCESS_STATES = new Set(['enrollment_only', 'enforced']);
export const PRINCIPAL_STATUSES = new Set(['pending', 'active', 'disabled']);
export const GRANT_SOURCES = new Set([
  'local_core_super_admin',
  'workspace_direct_member',
]);

export const PUBLIC_ORIGIN_ENV = 'MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN';
export const REMOTE_WORKBENCH_PUBLIC_ORIGIN = 'https://remote-workbench.mindscapeai.app';
export const GATEWAY_CONTROL_CAPABILITY_CODE = 'mindscape_cloud_integration';
export const GATEWAY_CONTROL_COMPONENT_CODE = 'MindscapeMobileWorkbenchGatewayPage';
export const READ_ONLY_GATEWAY_METHODS = ['GET', 'HEAD', 'OPTIONS'];
