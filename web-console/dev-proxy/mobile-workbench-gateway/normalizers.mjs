export function toLowerTrimmed(value = '') {
  return String(value || '').trim().toLowerCase();
}

export function normalizeRequestMethod(value = 'GET') {
  const normalized = String(value || 'GET').trim().toUpperCase();
  return normalized || 'GET';
}

export function isTruthyEnvValue(value = '') {
  const normalized = toLowerTrimmed(value);
  return ['1', 'true', 'yes', 'on'].includes(normalized);
}

export function splitCommaSeparatedValues(rawValue) {
  if (!rawValue) {
    return [];
  }
  return String(rawValue)
    .split(',')
    .map((item) => toLowerTrimmed(item))
    .filter(Boolean);
}

export function splitAdditionalRules(rawValue) {
  if (!rawValue) {
    return [];
  }
  return String(rawValue)
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

export function normalizeClaimValue(value) {
  if (value === null || value === undefined) {
    return null;
  }
  return String(value).trim();
}

export function normalizeCapabilityCodeFromApiSegment(value) {
  const normalized = normalizeClaimValue(value);
  return normalized ? normalized.replace(/-/g, '_') : null;
}

export function decodeURIComponentSafe(value = '') {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}
