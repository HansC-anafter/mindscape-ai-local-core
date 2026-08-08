import {
  extractRequestContext,
} from './context.mjs';
import {
  parseAccessTokenFromHeaders,
} from './jwt.mjs';
import {
  fixedRemoteWorkspacePathRequiresCapabilityQuery,
  isFixedRemoteWorkspacePathAllowed,
  isInvitationAcceptancePath,
  isReadOnlyRemotePath,
  matchesRule,
} from './path-rules.mjs';
import {
  requiredWorkspacePermission,
} from './workspace-permission-rules.mjs';

function denyRequest(reasonCode, statusCode, requestUrl, context, details = {}) {
  return {
    allowed: false,
    reason: statusCode === 404
      ? 'mobile_workbench_gateway_path_not_allowed'
      : 'mobile_workbench_gateway_access_denied',
    reason_code: reasonCode,
    status_code: statusCode,
    path: requestUrl,
    context,
    ...details,
  };
}

function allowRequest(requestUrl, context, details = {}) {
  return {
    allowed: true,
    reason: 'mobile_workbench_gateway_request_allowed',
    status_code: 200,
    path: requestUrl,
    context,
    verification_stage: 'principal_verified',
    ...details,
  };
}

function findPendingDesignation(config, principal) {
  if (!principal.email) {
    return null;
  }
  return config.runtimePolicy?.localCoreSuperAdmins?.find((entry) => (
    entry.status === 'pending'
    && entry.email === principal.email
    && entry.subject === 'pending_identity_resolution'
  )) || null;
}

function findEffectivePrincipal(effectivePolicy, subject) {
  return effectivePolicy.effectivePrincipals.find((entry) => entry.subject === subject) || null;
}

function hasExactPublicHost(requestHeaders, publicOrigin) {
  const entries = Object.entries(requestHeaders || {})
    .filter(([name]) => String(name).toLowerCase() === 'host');
  if (entries.length !== 1 || Array.isArray(entries[0][1])) return false;
  try {
    return String(entries[0][1] || '').trim() === new URL(publicOrigin).hostname;
  } catch {
    return false;
  }
}

function isResolvedPathAllowed(context, requestMethod, resolution) {
  if (context.isBootAsset) {
    return true;
  }
  if (isFixedRemoteWorkspacePathAllowed(context.path, requestMethod)) {
    return true;
  }
  return resolution.allowedPathRules.some((rule) => (
    matchesRule(context.path, rule, requestMethod)
  ));
}

function hasExactCapabilityQuery(requestUrl, expectedCapabilityCode) {
  let parsed;
  try {
    parsed = new URL(requestUrl, 'http://localhost');
  } catch {
    return false;
  }
  const values = [
    ...parsed.searchParams.getAll('capability_code'),
    ...parsed.searchParams.getAll('capabilityCode'),
  ];
  return (
    values.length === 1
    && String(values[0] || '').trim().toLowerCase() === expectedCapabilityCode
  );
}

function canonicalAdministrators(values = []) {
  return [...values]
    .map((entry) => ({
      subject: entry.subject,
      email: entry.email,
      status: entry.status,
    }))
    .sort((left, right) => (
      left.subject.localeCompare(right.subject)
      || String(left.email || '').localeCompare(String(right.email || ''))
      || left.status.localeCompare(right.status)
    ));
}

function validateEffectiveSnapshot(config, principal, effectivePolicy) {
  return (
    effectivePolicy.authConfigSource === 'runtime_policy'
    && effectivePolicy.authConfigFingerprint === config.authConfigFingerprint
    && effectivePolicy.accessIssuer === config.runtimePolicy.accessIssuer
    && effectivePolicy.accessAudience === config.runtimePolicy.accessAudience
    && effectivePolicy.accessIssuer === principal.issuer
    && effectivePolicy.remoteAccessState === config.remoteAccessState
    && effectivePolicy.runtimePolicyRevision === config.runtimePolicy.revision
    && effectivePolicy.runtimePolicySource === config.runtimePolicy.source
    && JSON.stringify(canonicalAdministrators(effectivePolicy.localCoreSuperAdmins))
      === JSON.stringify(canonicalAdministrators(config.runtimePolicy.localCoreSuperAdmins))
  );
}

export async function authorizeRemoteWorkbenchRequest(
  requestUrl = '/',
  requestHeaders = {},
  config,
  {
    requestMethod = 'GET',
    verifyAccessToken,
    resolveWorkspaceCapabilityPolicy,
  } = {},
) {
  const context = extractRequestContext(requestUrl, requestHeaders, {
    publicOrigin: config?.publicOrigin || '',
    requestMethod,
  });
  if (!config?.remoteListenerReady || typeof verifyAccessToken !== 'function') {
    return denyRequest(
      'remote_identity_configuration_unavailable',
      403,
      requestUrl,
      context,
      { verification_stage: 'identity_rejected' },
    );
  }
  if (!hasExactPublicHost(requestHeaders, config.publicOrigin)) {
    return denyRequest('invalid_public_host', 403, requestUrl, context, {
      verification_stage: 'identity_rejected',
    });
  }

  const accessToken = parseAccessTokenFromHeaders(requestHeaders);
  if (!accessToken) {
    return denyRequest('missing_access_token', 403, requestUrl, context, {
      verification_stage: 'identity_rejected',
    });
  }
  let verification;
  try {
    verification = await verifyAccessToken(accessToken);
  } catch {
    verification = { valid: false, reasonCode: 'invalid_access_token' };
  }
  if (!verification?.valid || !verification.principal) {
    return denyRequest(
      verification?.reasonCode || 'invalid_access_token',
      403,
      requestUrl,
      context,
      { verification_stage: 'identity_rejected' },
    );
  }
  const principal = verification.principal;

  if (context.conflicts.length > 0) {
    return denyRequest('request_context_mismatch', 403, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }
  if (
    principal.workspaceClaim
    && context.workspaceId
    && principal.workspaceClaim !== context.workspaceId
  ) {
    return denyRequest('access_token_workspace_mismatch', 403, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }
  if (context.isRemoteControlPlane) {
    return denyRequest('remote_control_plane_forbidden', 404, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }
  if (
    isReadOnlyRemotePath(context.path)
    && !['GET', 'HEAD', 'OPTIONS'].includes(String(requestMethod || 'GET').toUpperCase())
  ) {
    return denyRequest('capability_path_not_allowed', 404, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }
  if (isInvitationAcceptancePath(context.path, requestMethod)) {
    return allowRequest(requestUrl, context, {
      verified_principal: {
        provider: 'cloudflare-access',
        issuer: principal.issuer,
        subject: principal.subject,
        email: principal.email,
      },
      invitation_acceptance: true,
    });
  }

  if (config.remoteAccessState === 'enrollment_only') {
    const designation = findPendingDesignation(config, principal);
    return denyRequest('remote_access_enrollment_only', 403, requestUrl, context, {
      verification_stage: 'principal_verified',
      subject_candidate: designation
        ? {
            issuer: principal.issuer,
            subject: principal.subject,
            email: principal.email,
          }
        : null,
    });
  }
  if (config.remoteAccessState !== 'enforced') {
    return denyRequest('remote_access_state_invalid', 403, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }

  if (context.isBootAsset && !context.workspaceId) {
    return allowRequest(requestUrl, context, {
      principal_subject: principal.subject,
      verified_principal: {
        provider: 'cloudflare-access',
        issuer: principal.issuer,
        subject: principal.subject,
        email: principal.email,
      },
      boot_asset: true,
    });
  }
  if (!context.workspaceId) {
    return denyRequest('route_workspace_required', 403, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }
  if (
    fixedRemoteWorkspacePathRequiresCapabilityQuery(context.path)
    && (
      !hasExactCapabilityQuery(requestUrl, context.capabilityCode)
      || !isFixedRemoteWorkspacePathAllowed(context.path, requestMethod)
    )
  ) {
    return denyRequest('capability_path_not_allowed', 404, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }
  if (typeof resolveWorkspaceCapabilityPolicy !== 'function') {
    return denyRequest('workspace_policy_resolver_unavailable', 403, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }

  let resolution;
  const stagedResolver = (
    typeof resolveWorkspaceCapabilityPolicy.resolveEffectivePolicy === 'function'
    && typeof resolveWorkspaceCapabilityPolicy.resolveCapabilityDecision === 'function'
  );
  try {
    if (stagedResolver) {
      resolution = {
        effectivePolicy: await resolveWorkspaceCapabilityPolicy.resolveEffectivePolicy(
          context.workspaceId,
        ),
        capabilitySupport: null,
        capabilityCode: context.capabilityCode,
        allowedPathRules: [],
      };
    } else {
      resolution = await resolveWorkspaceCapabilityPolicy({
        workspaceId: context.workspaceId,
        capabilityCode: context.capabilityCode,
      });
    }
  } catch {
    return denyRequest('workspace_policy_unavailable', 403, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }
  const effectivePolicy = resolution?.effectivePolicy;
  if (!effectivePolicy || !validateEffectiveSnapshot(config, principal, effectivePolicy)) {
    return denyRequest('workspace_policy_auth_config_mismatch', 403, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }
  const effectivePrincipal = findEffectivePrincipal(effectivePolicy, principal.subject);
  if (!effectivePrincipal) {
    return denyRequest('workspace_membership_required', 403, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }
  const requiredPermission = requiredWorkspacePermission(context, requestMethod);
  if (
    !requiredPermission
    || !effectivePrincipal.permissions.includes(requiredPermission)
  ) {
    return denyRequest('workspace_permission_required', 403, requestUrl, context, {
      verification_stage: 'principal_verified',
      required_permission: requiredPermission,
    });
  }

  if (context.capabilityCode) {
    const capabilityAllowed = effectivePolicy.allowedCapabilityCodes.includes(
      context.capabilityCode,
    );
    if (!capabilityAllowed) {
      return denyRequest('capability_not_allowed', 403, requestUrl, context, {
        verification_stage: 'principal_verified',
      });
    }
    if (stagedResolver) {
      try {
        const capabilityDecision = await resolveWorkspaceCapabilityPolicy
          .resolveCapabilityDecision(context.capabilityCode);
        resolution = { ...resolution, ...capabilityDecision };
      } catch {
        return denyRequest('workspace_policy_unavailable', 403, requestUrl, context, {
          verification_stage: 'principal_verified',
        });
      }
    }
    if (!resolution.capabilitySupport?.supported) {
      return denyRequest('capability_not_supported', 404, requestUrl, context, {
        verification_stage: 'principal_verified',
      });
    }
  }
  if (!isResolvedPathAllowed(context, requestMethod, resolution)) {
    return denyRequest('capability_path_not_allowed', 404, requestUrl, context, {
      verification_stage: 'principal_verified',
    });
  }

  return allowRequest(requestUrl, context, {
    principal_subject: principal.subject,
    verified_principal: {
      provider: 'cloudflare-access',
      issuer: principal.issuer,
      subject: principal.subject,
      email: principal.email,
    },
    grant_sources: [...effectivePrincipal.grantSources],
    effective_permissions: [...effectivePrincipal.permissions],
    required_permission: requiredPermission,
    allowed_capability_codes: [...effectivePolicy.allowedCapabilityCodes],
  });
}

export const isMobileWorkbenchGatewayRequestAllowedAsync = authorizeRemoteWorkbenchRequest;
