import {
  ALLOWLIST_EMAIL_ENV,
  ALLOWLIST_GROUP_ENV,
  JWT_AUDIENCE_ENV,
  JWT_CLOCK_SKEW_ENV,
  JWT_ISSUER_ENV,
  JWT_PUBLIC_KEY_ENV,
  JWT_PUBLIC_KEY_FILE_ENV,
  JWT_REQUIRE_SIGNATURE_VERIFICATION_ENV,
  MAX_CLOCK_SKEW_SECONDS_DEFAULT,
  PUBLIC_ORIGIN_ENV,
  WORKSPACE_ALLOWLIST_ENV,
} from './constants.mjs';
import {
  isTruthyEnvValue,
  splitAdditionalRules,
  splitCommaSeparatedValues,
} from './normalizers.mjs';
import {
  DEFAULT_ALLOWED_PATH_RULES,
  isGatewayPathAllowed,
  isLoopbackPublicOrigin,
  normalizePathPattern,
} from './path-rules.mjs';
import {
  parseClockSkew,
  readPublicKeySource,
} from './jwt.mjs';

export function isGatewayPolicyEnabled(config) {
  return (
    (config?.allowlistEmails || []).length > 0 ||
    (config?.allowlistGroups || []).length > 0 ||
    (config?.workspaceAllowlist || []).length > 0 ||
    (config?.jwtVerifyRequired || false) ||
    (config?.jwtAudience || []).length > 0 ||
    (config?.jwtIssuer || []).length > 0
  );
}

export function resolveMobileWorkbenchGatewayConfig(env = process.env) {
  const enabled = String(env.MOBILE_WORKBENCH_GATEWAY_ENABLED || '').trim() === '1';
  const rawAdditionalRules = splitAdditionalRules(env.MOBILE_WORKBENCH_GATEWAY_EXTRA_PATH_RULES);
  const allowlistEmails = splitCommaSeparatedValues(env[ALLOWLIST_EMAIL_ENV]);
  const allowlistGroups = splitCommaSeparatedValues(env[ALLOWLIST_GROUP_ENV]);
  const workspaceAllowlist = splitCommaSeparatedValues(env[WORKSPACE_ALLOWLIST_ENV]);
  const publicOrigin = String(env[PUBLIC_ORIGIN_ENV] || '').trim().replace(/\/+$/, '');
  const jwtAudience = splitCommaSeparatedValues(env[JWT_AUDIENCE_ENV]);
  const jwtIssuer = splitCommaSeparatedValues(env[JWT_ISSUER_ENV]);
  const jwtClockSkewSeconds = parseClockSkew(env[JWT_CLOCK_SKEW_ENV]);

  const publicKeySource = readPublicKeySource(
    env[JWT_PUBLIC_KEY_FILE_ENV],
    env[JWT_PUBLIC_KEY_ENV],
  );
  const jwtVerifyRequired = isTruthyEnvValue(env[JWT_REQUIRE_SIGNATURE_VERIFICATION_ENV]);
  const jwtVerifyEnabled = jwtVerifyRequired && Boolean(publicKeySource.value) && !publicKeySource.error;

  const errors = [];
  const extraAllowedPathRules = rawAdditionalRules
    .map((token) => normalizePathPattern(token, errors))
    .filter(Boolean);

  if (publicKeySource.error) {
    errors.push(publicKeySource.error);
  }
  if (
    isTruthyEnvValue(env[JWT_REQUIRE_SIGNATURE_VERIFICATION_ENV]) &&
    !publicKeySource.value
  ) {
    errors.push('MOBILE_WORKBENCH_GATEWAY_JWT_SIGNATURE_VERIFICATION_ENABLED_BUT_PUBLIC_KEY_missing');
  }
  if (publicOrigin) {
    if (!publicOrigin.startsWith('https://')) {
      errors.push('MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN_must_use_https');
    } else if (isLoopbackPublicOrigin(publicOrigin)) {
      errors.push('MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN_must_not_use_loopback_host');
    }
  }

  if (!enabled) {
    return {
      enabled: false,
      reason: 'disabled',
      errors,
      allowedPathRules: [...DEFAULT_ALLOWED_PATH_RULES],
      extraAllowedPathRules: [],
      allowlistEmails,
      allowlistGroups,
      workspaceAllowlist,
      publicOrigin,
      jwtAudience,
      jwtIssuer,
      jwtClockSkewSeconds,
      jwtVerifyRequired: false,
      jwtVerifyEnabled: false,
      jwtPublicKey: null,
      hasJwtPublicKey: false,
    };
  }

  return {
    enabled: true,
    reason: errors.length ? 'enabled_with_invalid_rules' : 'enabled',
    errors,
    allowedPathRules: [...DEFAULT_ALLOWED_PATH_RULES],
    extraAllowedPathRules,
    allowlistEmails,
    allowlistGroups,
    workspaceAllowlist,
    publicOrigin,
    jwtAudience,
    jwtIssuer,
    jwtClockSkewSeconds,
    jwtVerifyRequired,
    jwtVerifyEnabled,
    jwtPublicKey: publicKeySource.value,
    hasJwtPublicKey: Boolean(publicKeySource.value),
  };
}

export function isMobileWorkbenchGatewayPathAllowed(
  requestUrl = '/',
  config = resolveMobileWorkbenchGatewayConfig(),
  requestMethod = 'GET',
) {
  return isGatewayPathAllowed(requestUrl, config, requestMethod);
}

export function isMobileWorkbenchGatewayConfigEnabled(env = process.env) {
  return resolveMobileWorkbenchGatewayConfig(env).enabled;
}

export function formatMobileWorkbenchGatewayConfig(config) {
  return {
    enabled: config.enabled,
    reason: config.reason,
    errors: [...(config.errors || [])],
    allowed_prefix_rules: config.allowedPathRules
      .filter((rule) => rule.type === 'prefix')
      .map((rule) => rule.value),
    allowed_regex_rules: config.allowedPathRules
      .filter((rule) => rule.type === 'regex')
      .map((rule) => rule.source || rule.value.toString()),
    extra_allowed_rules: (config.extraAllowedPathRules || [])
      .map((rule) => rule.source || rule.value.toString()),
    extra_allowed_rules_count: (config.extraAllowedPathRules || []).length,
    allowlist_emails: config.allowlistEmails || [],
    allowlist_groups: config.allowlistGroups || [],
    workspace_allowlist: config.workspaceAllowlist || [],
    public_origin: config.publicOrigin || null,
    jwt_audience: config.jwtAudience || [],
    jwt_issuer: config.jwtIssuer || [],
    jwt_clock_skew_seconds: Number.isFinite(Number(config.jwtClockSkewSeconds))
      ? Number(config.jwtClockSkewSeconds)
      : MAX_CLOCK_SKEW_SECONDS_DEFAULT,
    jwt_signature_verification_required: Boolean(config.jwtVerifyRequired),
    jwt_verify_enabled: Boolean(config.jwtVerifyEnabled),
    jwt_public_key_configured: Boolean(config.jwtPublicKey),
    gateway_policy_enabled: isGatewayPolicyEnabled(config),
  };
}
