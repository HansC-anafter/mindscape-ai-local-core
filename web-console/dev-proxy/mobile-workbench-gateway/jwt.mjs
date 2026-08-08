import crypto from 'node:crypto';

import {
  ACCESS_ASSERTION_HEADER,
  JWK_CACHE_MAX_AGE_MS,
  JWK_UNKNOWN_KID_COOLDOWN_MS,
  MAX_CLOCK_SKEW_SECONDS_DEFAULT,
  MAX_JWK_KEYS,
  MAX_JWK_SET_BYTES,
  UPSTREAM_TIMEOUT_MS,
} from './constants.mjs';
import {
  normalizeAccessAudience,
  normalizeAccessIssuer,
  readBoundedJsonResponse,
} from './policy-contract.mjs';

const MAX_TOKEN_BYTES = 16 * 1024;
const MAX_SUBJECT_LENGTH = 512;
const MAX_EMAIL_LENGTH = 320;

function base64urlDecodeBuffer(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]*$/.test(value)) {
    throw new Error('invalid_base64url');
  }
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  return Buffer.from(`${value}${padding}`.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
}

function parseJsonPart(value, reason) {
  try {
    const parsed = JSON.parse(base64urlDecodeBuffer(value).toString('utf8'));
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(reason);
    }
    return parsed;
  } catch {
    throw new Error(reason);
  }
}

function parseJwt(rawToken) {
  if (typeof rawToken !== 'string' || !rawToken || Buffer.byteLength(rawToken) > MAX_TOKEN_BYTES) {
    throw new Error('invalid_access_token');
  }
  const parts = rawToken.split('.');
  if (parts.length !== 3 || parts.some((part) => !part)) {
    throw new Error('invalid_access_token');
  }
  return {
    header: parseJsonPart(parts[0], 'invalid_access_token_header'),
    claims: parseJsonPart(parts[1], 'invalid_access_token_claims'),
    signature: base64urlDecodeBuffer(parts[2]),
    signingInput: `${parts[0]}.${parts[1]}`,
  };
}

function findHeaderValue(rawHeaders, expectedName) {
  const matches = Object.entries(rawHeaders || {})
    .filter(([name]) => String(name).toLowerCase() === expectedName);
  if (matches.length !== 1) {
    return null;
  }
  const value = matches[0][1];
  if (Array.isArray(value)) {
    return value.length === 1 ? String(value[0] || '').trim() : null;
  }
  return String(value || '').trim() || null;
}

export function parseAccessTokenFromHeaders(rawHeaders = {}) {
  return findHeaderValue(rawHeaders, ACCESS_ASSERTION_HEADER);
}

function normalizeAudienceClaim(value) {
  if (typeof value === 'string') {
    return value ? [value] : [];
  }
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || !item)) {
    return [];
  }
  return value;
}

function normalizeWorkspaceClaim(claims) {
  const values = [claims.workspace_id, claims.workspaceId, claims.wsid]
    .filter((value) => value !== undefined && value !== null)
    .map((value) => typeof value === 'string' ? value.trim() : '');
  if (values.some((value) => !value || value.length > 128)) {
    throw new Error('invalid_access_token_workspace_claim');
  }
  const unique = Array.from(new Set(values));
  if (unique.length > 1) {
    throw new Error('ambiguous_access_token_workspace_claim');
  }
  return unique[0] || null;
}

function normalizeRequiredEpoch(value, reason) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(reason);
  }
  return value;
}

function validateClaims(claims, {
  issuer,
  audience,
  nowEpochSeconds,
  clockSkewSeconds,
}) {
  if (claims.iss !== issuer) {
    throw new Error('invalid_access_token_issuer');
  }
  const audiences = normalizeAudienceClaim(claims.aud);
  if (audiences.length !== 1 || audiences[0] !== audience) {
    throw new Error('invalid_access_token_audience');
  }
  if (claims.type !== 'app') {
    throw new Error('invalid_access_token_type');
  }
  const exp = normalizeRequiredEpoch(claims.exp, 'missing_or_invalid_access_token_exp');
  const nbf = normalizeRequiredEpoch(claims.nbf, 'missing_or_invalid_access_token_nbf');
  const iat = normalizeRequiredEpoch(claims.iat, 'missing_or_invalid_access_token_iat');
  if (exp + clockSkewSeconds < nowEpochSeconds) {
    throw new Error('expired_access_token');
  }
  if (nbf - clockSkewSeconds > nowEpochSeconds) {
    throw new Error('access_token_not_ready');
  }
  if (nbf > exp) {
    throw new Error('invalid_access_token_nbf');
  }
  if (iat - clockSkewSeconds > nowEpochSeconds || exp < iat) {
    throw new Error('invalid_access_token_iat');
  }
  if (
    typeof claims.sub !== 'string'
    || !claims.sub.trim()
    || claims.sub.trim().length > MAX_SUBJECT_LENGTH
    || /[\u0000-\u001f\u007f]/.test(claims.sub)
  ) {
    throw new Error('missing_or_invalid_access_token_subject');
  }
  const email = claims.email === undefined || claims.email === null
    ? null
    : String(claims.email).trim().toLowerCase();
  if (
    email !== null
    && (
      !email
      || email.length > MAX_EMAIL_LENGTH
      || email.split('@').length !== 2
      || !email.split('@')[1].includes('.')
      || /[\u0000-\u001f\u007f]/.test(email)
    )
  ) {
    throw new Error('invalid_access_token_email');
  }
  return {
    issuer: claims.iss,
    subject: claims.sub.trim(),
    email,
    workspaceClaim: normalizeWorkspaceClaim(claims),
  };
}

function createJwkPublicKey(jwk, expectedKid) {
  if (
    !jwk
    || typeof jwk !== 'object'
    || Array.isArray(jwk)
    || jwk.kid !== expectedKid
    || jwk.kty !== 'RSA'
    || (jwk.alg !== undefined && jwk.alg !== 'RS256')
    || (jwk.use !== undefined && jwk.use !== 'sig')
  ) {
    throw new Error('invalid_access_signing_key');
  }
  try {
    return crypto.createPublicKey({ key: jwk, format: 'jwk' });
  } catch {
    throw new Error('invalid_access_signing_key');
  }
}

export function createRemoteJwkSet({
  issuer,
  fetchImpl = globalThis.fetch,
  now = () => Date.now(),
  timeoutMs = UPSTREAM_TIMEOUT_MS,
  cacheMaxAgeMs = JWK_CACHE_MAX_AGE_MS,
  unknownKidCooldownMs = JWK_UNKNOWN_KID_COOLDOWN_MS,
} = {}) {
  const normalizedIssuer = normalizeAccessIssuer(issuer);
  if (typeof fetchImpl !== 'function') {
    throw new Error('fetchImpl is required');
  }
  const certsUrl = `${normalizedIssuer}/cdn-cgi/access/certs`;
  let cachedKeys = new Map();
  let expiresAt = 0;
  let refreshPromise = null;
  let lastUnknownKidRefreshAt = Number.NEGATIVE_INFINITY;

  async function refresh() {
    if (refreshPromise) {
      return refreshPromise;
    }
    const abortController = new AbortController();
    const timeout = setTimeout(() => abortController.abort(), timeoutMs);
    refreshPromise = (async () => {
      const response = await fetchImpl(certsUrl, {
        method: 'GET',
        headers: { accept: 'application/json' },
        signal: abortController.signal,
      });
      const payload = await readBoundedJsonResponse(response, MAX_JWK_SET_BYTES);
      if (!Array.isArray(payload?.keys) || payload.keys.length < 1 || payload.keys.length > MAX_JWK_KEYS) {
        throw new Error('invalid_access_jwk_set');
      }
      const nextKeys = new Map();
      for (const jwk of payload.keys) {
        if (typeof jwk?.kid !== 'string' || !jwk.kid || nextKeys.has(jwk.kid)) {
          throw new Error('invalid_access_jwk_set');
        }
        nextKeys.set(jwk.kid, createJwkPublicKey(jwk, jwk.kid));
      }
      cachedKeys = nextKeys;
      expiresAt = now() + cacheMaxAgeMs;
      return cachedKeys;
    })().finally(() => {
      clearTimeout(timeout);
      refreshPromise = null;
    });
    return refreshPromise;
  }

  async function resolveSigningKey(kid) {
    if (typeof kid !== 'string' || !kid || kid.length > 256) {
      throw new Error('missing_or_invalid_access_token_kid');
    }
    const currentTime = now();
    if (expiresAt > currentTime && cachedKeys.has(kid)) {
      return cachedKeys.get(kid);
    }
    if (expiresAt > currentTime && !cachedKeys.has(kid)) {
      if (currentTime - lastUnknownKidRefreshAt < unknownKidCooldownMs) {
        throw new Error('unknown_access_token_kid');
      }
      lastUnknownKidRefreshAt = currentTime;
    }
    const keys = await refresh();
    const key = keys.get(kid);
    if (!key) {
      lastUnknownKidRefreshAt = currentTime;
      throw new Error('unknown_access_token_kid');
    }
    return key;
  }

  resolveSigningKey.stats = () => ({
    keyCount: cachedKeys.size,
    expiresAt,
    refreshInFlight: Boolean(refreshPromise),
  });
  return resolveSigningKey;
}

export function createCloudflareAccessJwtVerifier({
  accessIssuer,
  accessAudience,
  fetchImpl = globalThis.fetch,
  resolveSigningKey = null,
  now = () => Date.now(),
  clockSkewSeconds = MAX_CLOCK_SKEW_SECONDS_DEFAULT,
} = {}) {
  const issuer = normalizeAccessIssuer(accessIssuer);
  const audience = normalizeAccessAudience(accessAudience);
  const keyResolver = resolveSigningKey || createRemoteJwkSet({
    issuer,
    fetchImpl,
    now,
  });

  async function verify(rawToken) {
    try {
      const parsed = parseJwt(rawToken);
      if (parsed.header.alg !== 'RS256') {
        throw new Error('unsupported_access_token_algorithm');
      }
      if (
        typeof parsed.header.kid !== 'string'
        || !parsed.header.kid
        || parsed.header.kid.length > 256
      ) {
        throw new Error('missing_or_invalid_access_token_kid');
      }
      const publicKey = await keyResolver(parsed.header.kid);
      const signatureValid = crypto.verify(
        'RSA-SHA256',
        Buffer.from(parsed.signingInput),
        publicKey,
        parsed.signature,
      );
      if (!signatureValid) {
        throw new Error('invalid_access_token_signature');
      }
      const principal = validateClaims(parsed.claims, {
        issuer,
        audience,
        nowEpochSeconds: Math.floor(now() / 1000),
        clockSkewSeconds,
      });
      return { valid: true, principal };
    } catch (error) {
      return {
        valid: false,
        reasonCode: error?.name === 'AbortError'
          ? 'access_signing_key_timeout'
          : error?.message || 'invalid_access_token',
      };
    }
  }

  verify.issuer = issuer;
  verify.audience = audience;
  return verify;
}
