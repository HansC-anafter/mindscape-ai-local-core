import crypto from 'node:crypto';
import fs from 'node:fs';

import {
  DEFAULT_TOKEN_HEADER_NAMES,
  JWT_ALGORITHMS,
  JWT_VERIFY_ALGORITHMS,
  MAX_CLOCK_SKEW_SECONDS_DEFAULT,
} from './constants.mjs';
import {
  normalizeClaimValue,
  splitCommaSeparatedValues,
  toLowerTrimmed,
} from './normalizers.mjs';

export function parseAccessTokenFromHeaders(rawHeaders = {}) {
  const headers = rawHeaders || {};
  for (const headerName of DEFAULT_TOKEN_HEADER_NAMES) {
    const value = Object.entries(headers).find(([key]) => toLowerTrimmed(key) === headerName)?.[1];
    if (!value) {
      continue;
    }
    const tokenValue = Array.isArray(value) ? value[0] : value;
    const normalized = String(tokenValue || '').trim();
    if (!normalized) {
      continue;
    }
    const match = /^Bearer\s+(.+)$/.exec(normalized);
    return match ? match[1].trim() : normalized;
  }
  return null;
}

function base64urlPad(value = '') {
  const normalized = String(value || '');
  const padLength = normalized.length % 4 === 0 ? 0 : 4 - (normalized.length % 4);
  return normalized + '='.repeat(padLength);
}

function base64urlDecode(value = '') {
  const normalized = base64urlPad(String(value || ''))
    .replace(/-/g, '+')
    .replace(/_/g, '/');
  return Buffer.from(normalized, 'base64').toString('utf8');
}

function base64urlDecodeBuffer(value = '') {
  const normalized = base64urlPad(String(value || ''))
    .replace(/-/g, '+')
    .replace(/_/g, '/');
  return Buffer.from(normalized, 'base64');
}

export function parseAccessJwtToken(rawToken) {
  if (!rawToken || typeof rawToken !== 'string') {
    return { claims: null, error: 'missing_access_token', header: null, signature: null, signingInput: null };
  }

  const tokenParts = rawToken.split('.');
  if (tokenParts.length !== 3) {
    return { claims: null, error: 'invalid_access_token', header: null, signature: null, signingInput: null };
  }

  try {
    const [headerPart, payloadPart] = tokenParts;
    const headerJson = base64urlDecode(headerPart);
    const payloadJson = base64urlDecode(payloadPart);
    const header = JSON.parse(headerJson);
    const claims = JSON.parse(payloadJson);
    if (claims === null || typeof claims !== 'object') {
      return {
        claims: null,
        error: 'invalid_access_token_claims',
        header: null,
        signature: null,
        signingInput: null,
      };
    }
    return {
      claims,
      header,
      signature: base64urlDecodeBuffer(tokenParts[2]),
      signingInput: `${tokenParts[0]}.${tokenParts[1]}`,
      error: null,
    };
  } catch (error) {
    return {
      claims: null,
      error: `invalid_access_token:${error?.message || 'decode_error'}`,
      header: null,
      signature: null,
      signingInput: null,
    };
  }
}

export function parseClockSkew(rawValue) {
  if (rawValue === undefined || rawValue === null || String(rawValue).trim() === '') {
    return MAX_CLOCK_SKEW_SECONDS_DEFAULT;
  }
  const parsed = Number.parseInt(String(rawValue).trim(), 10);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 3600) {
    return MAX_CLOCK_SKEW_SECONDS_DEFAULT;
  }
  return parsed;
}

export function readPublicKeySource(keyFile, inlineKey) {
  const trimmedFile = String(keyFile || '').trim();
  const trimmedInline = String(inlineKey || '').trim();
  if (trimmedFile && trimmedInline) {
    return {
      value: null,
      error: 'MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY_and_JWT_PUBLIC_KEY_FILE_are_mutually_exclusive',
    };
  }
  if (trimmedFile) {
    try {
      return {
        value: fs.readFileSync(trimmedFile, 'utf8'),
        error: null,
      };
    } catch (error) {
      return {
        value: null,
        error: `MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY_FILE_read_failed:${error?.code || error?.message || 'read_error'}`,
      };
    }
  }
  if (trimmedInline) {
    return {
      value: trimmedInline,
      error: null,
    };
  }
  return { value: null, error: null };
}

export function isJwtTokenExpired(claims, nowEpochSeconds = Math.floor(Date.now() / 1000), clockSkewSeconds = 0) {
  if (!claims || typeof claims !== 'object') {
    return true;
  }
  if (claims.exp !== undefined && Number.isFinite(Number(claims.exp))) {
    if (Number(claims.exp) + Number(clockSkewSeconds) < nowEpochSeconds) {
      return true;
    }
  }
  if (claims.nbf !== undefined && Number.isFinite(Number(claims.nbf))) {
    if (Number(claims.nbf) - Number(clockSkewSeconds) > nowEpochSeconds) {
      return true;
    }
  }
  return false;
}

function normalizeAudience(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeClaimValue).filter(Boolean).map(toLowerTrimmed);
  }
  if (typeof value === 'string') {
    return splitCommaSeparatedValues(value);
  }
  return [];
}

export function isAudienceMatch(configAudiences = [], tokenAudience = null) {
  if (configAudiences.length === 0) {
    return true;
  }
  const tokenAudiences = normalizeAudience(tokenAudience).map(toLowerTrimmed);
  return tokenAudiences.some((aud) => configAudiences.includes(aud));
}

export function isIssuerMatch(configIssuers = [], tokenIssuer = null) {
  if (configIssuers.length === 0) {
    return true;
  }
  const normalizedIssuer = toLowerTrimmed(tokenIssuer);
  return normalizedIssuer && configIssuers.includes(normalizedIssuer);
}

export function normalizeClaimList(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeClaimValue).filter(Boolean).map(toLowerTrimmed);
  }
  if (typeof value === 'string') {
    return splitCommaSeparatedValues(value);
  }
  return [];
}

function isJwtAlgorithmSupported(alg = '') {
  return JWT_ALGORITHMS.has(toLowerTrimmed(alg).toUpperCase());
}

function getJwtVerifyAlgorithm(alg = '') {
  return JWT_VERIFY_ALGORITHMS[String(alg || '').toUpperCase()] || '';
}

export function verifyJwtSignature(tokenHeader, tokenSignature, tokenSigningInput, publicKey, verifyEnabled) {
  if (!verifyEnabled) {
    return { valid: true };
  }
  if (!tokenHeader || typeof tokenHeader !== 'object') {
    return { valid: false, reason: 'invalid_access_token_header' };
  }
  if (!publicKey) {
    return { valid: false, reason: 'MOBILE_WORKBENCH_GATEWAY_JWT_PUBLIC_KEY_required_for_signature_verification' };
  }
  const alg = String(tokenHeader.alg || '').toUpperCase();
  if (!isJwtAlgorithmSupported(alg)) {
    return { valid: false, reason: 'unsupported_access_token_algorithm' };
  }
  const verifyAlgorithm = getJwtVerifyAlgorithm(alg);
  try {
    const verifier = crypto.createVerify(verifyAlgorithm);
    verifier.update(tokenSigningInput);
    verifier.end();
    const isValid = verifier.verify(publicKey, tokenSignature);
    if (!isValid) {
      return { valid: false, reason: 'invalid_access_token_signature' };
    }
    return { valid: true };
  } catch (error) {
    return {
      valid: false,
      reason: `access_token_signature_verification_error:${error?.message || 'verification_error'}`,
    };
  }
}
