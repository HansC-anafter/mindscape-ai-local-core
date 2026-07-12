import crypto from 'node:crypto';

import {
  GRANT_SOURCES,
  MAX_CAPABILITY_SUPPORT_BYTES,
  MAX_EFFECTIVE_POLICY_BYTES,
  MAX_EFFECTIVE_PRINCIPALS,
  MAX_GLOBAL_ADMINISTRATORS,
  MAX_RUNTIME_POLICY_BYTES,
  MAX_WORKSPACE_PRINCIPALS,
  PRINCIPAL_STATUSES,
  REMOTE_ACCESS_STATES,
} from './constants.mjs';

const PENDING_SUBJECT = 'pending_identity_resolution';
const MAX_SUBJECT_LENGTH = 512;
const MAX_EMAIL_LENGTH = 320;
const MAX_AUDIENCE_LENGTH = 512;
const MAX_CAPABILITY_CODES = 128;

function malformed(reason) {
  throw new Error(`mobile_workbench_policy_malformed:${reason}`);
}

function requirePlainObject(value, reason) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    malformed(reason);
  }
  return value;
}

function normalizeBoundedString(value, {
  allowNull = false,
  maxLength,
  reason,
} = {}) {
  if (value === null && allowNull) {
    return null;
  }
  if (typeof value !== 'string') {
    malformed(reason);
  }
  const normalized = value.trim();
  if (!normalized || normalized.length > maxLength || /[\u0000-\u001f\u007f]/.test(normalized)) {
    malformed(reason);
  }
  return normalized;
}

export function normalizeAccessIssuer(value) {
  const normalized = normalizeBoundedString(value, {
    maxLength: 512,
    reason: 'invalid_access_issuer',
  }).replace(/\/+$/, '');
  let parsed;
  try {
    parsed = new URL(normalized);
  } catch {
    malformed('invalid_access_issuer');
  }
  if (
    parsed.protocol !== 'https:'
    || parsed.username
    || parsed.password
    || parsed.port
    || parsed.search
    || parsed.hash
    || (parsed.pathname && parsed.pathname !== '/')
    || !parsed.hostname.toLowerCase().endsWith('.cloudflareaccess.com')
  ) {
    malformed('invalid_access_issuer');
  }
  return normalized;
}

export function normalizeAccessAudience(value) {
  return normalizeBoundedString(value, {
    maxLength: MAX_AUDIENCE_LENGTH,
    reason: 'invalid_access_audience',
  });
}

export function deriveAuthConfigFingerprint(accessIssuer, accessAudience) {
  const issuer = normalizeAccessIssuer(accessIssuer);
  const audience = normalizeAccessAudience(accessAudience);
  return crypto.createHash('sha256').update(`${issuer}\n${audience}`).digest('hex');
}

function normalizeEmail(value) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  return normalizeBoundedString(value, {
    maxLength: MAX_EMAIL_LENGTH,
    reason: 'invalid_principal_email',
  }).toLowerCase();
}

function normalizeSubject(value, { allowPending = false } = {}) {
  const subject = normalizeBoundedString(value, {
    maxLength: MAX_SUBJECT_LENGTH,
    reason: 'invalid_principal_subject',
  });
  if (!allowPending && subject === PENDING_SUBJECT) {
    malformed('pending_subject_not_authoritative');
  }
  return subject;
}

function normalizeAdministrator(value) {
  const row = requirePlainObject(value, 'invalid_global_administrator');
  if (!PRINCIPAL_STATUSES.has(row.status)) {
    malformed('invalid_global_administrator_status');
  }
  const subject = normalizeSubject(row.subject, { allowPending: row.status !== 'active' });
  const email = normalizeEmail(row.email);
  if (row.status === 'active' && subject === PENDING_SUBJECT) {
    malformed('active_administrator_has_pending_subject');
  }
  if (row.status === 'pending' && (subject !== PENDING_SUBJECT || !email)) {
    malformed('invalid_pending_administrator_designation');
  }
  if (row.status !== 'pending' && subject === PENDING_SUBJECT) {
    malformed('pending_subject_not_authoritative');
  }
  return {
    subject,
    email,
    status: row.status,
  };
}

function normalizeAdministratorList(values) {
  if (!Array.isArray(values) || values.length > MAX_GLOBAL_ADMINISTRATORS) {
    malformed('invalid_global_administrators');
  }
  const seenSubjects = new Set();
  const seenPendingEmails = new Set();
  return values.map((value) => {
    const row = normalizeAdministrator(value);
    if (row.status === 'pending') {
      if (seenPendingEmails.has(row.email)) {
        malformed('duplicate_global_administrator');
      }
      seenPendingEmails.add(row.email);
    } else {
      if (seenSubjects.has(row.subject)) {
        malformed('duplicate_global_administrator');
      }
      seenSubjects.add(row.subject);
    }
    return row;
  });
}

function requireFingerprint(value, issuer, audience) {
  const fingerprint = normalizeBoundedString(value, {
    maxLength: 64,
    reason: 'invalid_auth_config_fingerprint',
  });
  if (!/^[a-f0-9]{64}$/.test(fingerprint)) {
    malformed('invalid_auth_config_fingerprint');
  }
  if (fingerprint !== deriveAuthConfigFingerprint(issuer, audience)) {
    malformed('auth_config_fingerprint_mismatch');
  }
  return fingerprint;
}

function normalizeRemoteAccessState(value) {
  if (!REMOTE_ACCESS_STATES.has(value)) {
    malformed('invalid_remote_access_state');
  }
  return value;
}

function normalizeRevision(value, reason) {
  if (!Number.isSafeInteger(value) || value < 0) {
    malformed(reason);
  }
  return value;
}

export function normalizeRuntimeAccessPolicy(payload) {
  const row = requirePlainObject(payload, 'invalid_runtime_policy');
  if (row.id !== 'remote-workbench-runtime') {
    malformed('invalid_runtime_policy_id');
  }
  if (row.auth_config_source !== 'runtime_policy') {
    malformed('invalid_auth_config_source');
  }
  if (!['default_deny', 'persisted_policy'].includes(row.source)) {
    malformed('invalid_runtime_policy_source');
  }
  const hasIssuer = row.access_issuer !== null;
  const hasAudience = row.access_audience !== null;
  if (hasIssuer !== hasAudience) {
    malformed('partial_runtime_auth_config');
  }
  const remoteAccessState = normalizeRemoteAccessState(row.remote_access_state);
  if (!hasIssuer && remoteAccessState !== 'enrollment_only') {
    malformed('enforced_runtime_auth_config_missing');
  }
  if (!hasIssuer && row.auth_config_fingerprint !== null) {
    malformed('empty_runtime_auth_config_has_fingerprint');
  }
  const accessIssuer = hasIssuer ? normalizeAccessIssuer(row.access_issuer) : null;
  const accessAudience = hasAudience ? normalizeAccessAudience(row.access_audience) : null;
  const administrators = normalizeAdministratorList(row.local_core_super_admins);
  if (!hasIssuer && (row.source !== 'default_deny' || administrators.length !== 0)) {
    malformed('default_deny_runtime_policy_has_grants');
  }
  if (hasIssuer && row.source !== 'persisted_policy') {
    malformed('active_runtime_policy_source_mismatch');
  }
  return {
    id: row.id,
    accessIssuer,
    accessAudience,
    authConfigFingerprint: hasIssuer
      ? requireFingerprint(row.auth_config_fingerprint, accessIssuer, accessAudience)
      : null,
    authConfigSource: row.auth_config_source,
    remoteAccessState,
    localCoreSuperAdmins: administrators,
    revision: normalizeRevision(row.revision, 'invalid_runtime_policy_revision'),
    source: row.source,
  };
}

function normalizeDirectPrincipal(value) {
  const row = requirePlainObject(value, 'invalid_workspace_principal');
  return {
    subject: normalizeSubject(row.subject),
    email: normalizeEmail(row.email),
  };
}

function normalizeDirectPrincipalList(values) {
  if (!Array.isArray(values) || values.length > MAX_WORKSPACE_PRINCIPALS) {
    malformed('invalid_workspace_principals');
  }
  const seen = new Set();
  return values.map((value) => {
    const row = normalizeDirectPrincipal(value);
    if (seen.has(row.subject)) {
      malformed('duplicate_workspace_principal');
    }
    seen.add(row.subject);
    return row;
  });
}

function normalizeGrantSources(values) {
  if (!Array.isArray(values) || values.length < 1 || values.length > GRANT_SOURCES.size) {
    malformed('invalid_grant_sources');
  }
  const sources = Array.from(new Set(values));
  if (sources.length !== values.length || sources.some((value) => !GRANT_SOURCES.has(value))) {
    malformed('invalid_grant_sources');
  }
  return sources.sort();
}

function normalizeEffectivePrincipalList(values) {
  if (!Array.isArray(values) || values.length > MAX_EFFECTIVE_PRINCIPALS) {
    malformed('invalid_effective_principals');
  }
  const seen = new Set();
  return values.map((value) => {
    const row = requirePlainObject(value, 'invalid_effective_principal');
    const normalized = {
      subject: normalizeSubject(row.subject),
      email: normalizeEmail(row.email),
      grantSources: normalizeGrantSources(row.grant_sources),
    };
    if (seen.has(normalized.subject)) {
      malformed('duplicate_effective_principal');
    }
    seen.add(normalized.subject);
    return normalized;
  });
}

function normalizeCapabilityCodes(values) {
  if (!Array.isArray(values) || values.length > MAX_CAPABILITY_CODES) {
    malformed('invalid_allowed_capability_codes');
  }
  const seen = new Set();
  return values.map((value) => {
    const code = normalizeBoundedString(value, {
      maxLength: 128,
      reason: 'invalid_capability_code',
    }).toLowerCase();
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(code) || seen.has(code)) {
      malformed('invalid_capability_code');
    }
    seen.add(code);
    return code;
  }).sort();
}

function assertEffectiveProjection(administrators, directPrincipals, effectivePrincipals) {
  const expected = new Map();
  for (const administrator of administrators) {
    if (administrator.status !== 'active' || administrator.subject === PENDING_SUBJECT) {
      continue;
    }
    expected.set(administrator.subject, new Set(['local_core_super_admin']));
  }
  for (const principal of directPrincipals) {
    const sources = expected.get(principal.subject) || new Set();
    sources.add('workspace_direct_member');
    expected.set(principal.subject, sources);
  }
  if (expected.size !== effectivePrincipals.length) {
    malformed('effective_principal_projection_mismatch');
  }
  for (const principal of effectivePrincipals) {
    const expectedSources = expected.get(principal.subject);
    if (
      !expectedSources
      || principal.grantSources.length !== expectedSources.size
      || principal.grantSources.some((source) => !expectedSources.has(source))
    ) {
      malformed('effective_principal_projection_mismatch');
    }
  }
}

export function normalizeEffectiveWorkspacePolicy(payload, expectedWorkspaceId) {
  const row = requirePlainObject(payload, 'invalid_effective_policy');
  const workspaceId = normalizeBoundedString(row.workspace_id, {
    maxLength: 128,
    reason: 'invalid_workspace_id',
  });
  if (workspaceId !== expectedWorkspaceId || row.source !== 'effective_policy') {
    malformed('effective_policy_identity_mismatch');
  }
  if (row.auth_config_source !== 'runtime_policy') {
    malformed('invalid_auth_config_source');
  }
  if (!['default_deny', 'persisted_policy'].includes(row.runtime_policy_source)) {
    malformed('invalid_runtime_policy_source');
  }
  if (!['default_deny', 'persisted_policy'].includes(row.workspace_policy_source)) {
    malformed('invalid_workspace_policy_source');
  }
  const accessIssuer = normalizeAccessIssuer(row.access_issuer);
  const accessAudience = normalizeAccessAudience(row.access_audience);
  const administrators = normalizeAdministratorList(row.local_core_super_admins);
  const directPrincipals = normalizeDirectPrincipalList(row.allowed_principals);
  const effectivePrincipals = normalizeEffectivePrincipalList(row.effective_principals);
  const allowedCapabilityCodes = normalizeCapabilityCodes(row.allowed_capability_codes);
  if (row.runtime_policy_source !== 'persisted_policy') {
    malformed('active_runtime_policy_source_mismatch');
  }
  if (
    row.workspace_policy_source === 'default_deny'
    && (directPrincipals.length !== 0 || allowedCapabilityCodes.length !== 0)
  ) {
    malformed('default_deny_workspace_policy_has_grants');
  }
  assertEffectiveProjection(administrators, directPrincipals, effectivePrincipals);
  return {
    workspaceId,
    accessIssuer,
    accessAudience,
    authConfigFingerprint: requireFingerprint(
      row.auth_config_fingerprint,
      accessIssuer,
      accessAudience,
    ),
    authConfigSource: row.auth_config_source,
    remoteAccessState: normalizeRemoteAccessState(row.remote_access_state),
    runtimePolicyRevision: normalizeRevision(
      row.runtime_policy_revision,
      'invalid_runtime_policy_revision',
    ),
    runtimePolicySource: row.runtime_policy_source,
    localCoreSuperAdmins: administrators,
    directPrincipals,
    effectivePrincipals,
    allowedCapabilityCodes,
    workspacePolicySource: row.workspace_policy_source,
    source: row.source,
  };
}

export async function readBoundedJsonResponse(response, maxBytes) {
  if (!response || typeof response.ok !== 'boolean' || !response.ok) {
    const status = Number(response?.status) || 0;
    throw new Error(`mobile_workbench_upstream_request_failed:${status}`);
  }
  const contentLength = Number(response.headers?.get?.('content-length'));
  if (Number.isFinite(contentLength) && contentLength > maxBytes) {
    throw new Error('mobile_workbench_upstream_payload_too_large');
  }
  let payload;
  if (typeof response.body?.getReader === 'function') {
    const reader = response.body.getReader();
    const chunks = [];
    let totalBytes = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      const chunk = Buffer.from(value);
      totalBytes += chunk.length;
      if (totalBytes > maxBytes) {
        await reader.cancel();
        throw new Error('mobile_workbench_upstream_payload_too_large');
      }
      chunks.push(chunk);
    }
    try {
      payload = JSON.parse(Buffer.concat(chunks, totalBytes).toString('utf8'));
    } catch {
      throw new Error('mobile_workbench_upstream_payload_invalid_json');
    }
  } else if (typeof response.text === 'function') {
    const raw = await response.text();
    if (Buffer.byteLength(raw) > maxBytes) {
      throw new Error('mobile_workbench_upstream_payload_too_large');
    }
    try {
      payload = JSON.parse(raw);
    } catch {
      throw new Error('mobile_workbench_upstream_payload_invalid_json');
    }
  } else if (typeof response.json === 'function') {
    payload = await response.json();
    if (Buffer.byteLength(JSON.stringify(payload)) > maxBytes) {
      throw new Error('mobile_workbench_upstream_payload_too_large');
    }
  } else {
    throw new Error('mobile_workbench_upstream_payload_missing');
  }
  return payload;
}

export const POLICY_PAYLOAD_LIMITS = {
  runtime: MAX_RUNTIME_POLICY_BYTES,
  effective: MAX_EFFECTIVE_POLICY_BYTES,
  support: MAX_CAPABILITY_SUPPORT_BYTES,
};
