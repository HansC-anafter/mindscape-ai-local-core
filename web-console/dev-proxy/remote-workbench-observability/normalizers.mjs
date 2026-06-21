import {
  DEFAULT_AUDIT_LIMIT,
  MAX_AUDIT_LIMIT,
} from './constants.mjs';

export function normalizeString(value = '') {
  return String(value || '').trim();
}

export function normalizeIdentifier(value = '') {
  return normalizeString(value).toLowerCase();
}

export function normalizeNullable(value = '') {
  const normalized = normalizeString(value);
  return normalized || null;
}

export function normalizePathname(requestUrl = '/') {
  try {
    return new URL(requestUrl, 'http://localhost').pathname || '/';
  } catch {
    return String(requestUrl || '/').split('?')[0] || '/';
  }
}

export function toInteger(value, fallback = 0) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function toFiniteNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function roundDuration(value = 0) {
  return Math.round(toFiniteNumber(value, 0) * 100) / 100;
}

export function clampLimit(value, defaultValue = DEFAULT_AUDIT_LIMIT) {
  const parsed = toInteger(value, defaultValue);
  if (parsed < 1) {
    return 1;
  }
  if (parsed > MAX_AUDIT_LIMIT) {
    return MAX_AUDIT_LIMIT;
  }
  return parsed;
}

export function archiveFilename(index) {
  return `access.${index}.ndjson`;
}

export function listStringValues(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeString(item))
      .filter(Boolean);
  }
  const normalized = normalizeString(value);
  return normalized ? [normalized] : [];
}
