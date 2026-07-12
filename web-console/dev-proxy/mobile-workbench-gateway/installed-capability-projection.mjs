import {
  readBoundedJsonResponse,
} from './policy-contract.mjs';
import {
  normalizeCapabilitySupport,
} from './capability-support-contract.mjs';

const MAX_INSTALLED_CAPABILITIES_BYTES = 1024 * 1024;
const MAX_INSTALLED_CAPABILITIES = 512;
const UPSTREAM_TIMEOUT_MS = 1000;

export function isInstalledCapabilityListProjectionRequest(method = 'GET', requestUrl = '/') {
  if (String(method || 'GET').toUpperCase() !== 'GET') return false;
  try {
    return new URL(requestUrl, 'http://localhost').pathname
      === '/api/v1/capability-packs/installed-capabilities';
  } catch {
    return false;
  }
}

function projectInstalledCapabilities(payload, allowedCapabilityCodes) {
  if (!Array.isArray(payload) || payload.length > MAX_INSTALLED_CAPABILITIES) {
    throw new Error('installed_capabilities_payload_malformed');
  }
  const allowed = new Set(allowedCapabilityCodes);
  const seen = new Set();
  const projected = [];
  for (const row of payload) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) {
      throw new Error('installed_capabilities_payload_malformed');
    }
    const code = String(row.code || row.id || '').trim().toLowerCase();
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(code) || seen.has(code)) {
      throw new Error('installed_capabilities_payload_malformed');
    }
    seen.add(code);
    let support;
    try {
      support = normalizeCapabilitySupport(row.mobile_workbench_gateway_support, code);
    } catch {
      throw new Error('installed_capabilities_payload_malformed');
    }
    if (allowed.has(code) && support.supported) projected.push(row);
  }
  return projected;
}

export async function writeInstalledCapabilityListProjection(
  res,
  {
    allowedCapabilityCodes = [],
    fetchImpl = globalThis.fetch,
    upstreamUrl,
  } = {},
) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  try {
    const response = await fetchImpl(upstreamUrl, {
      method: 'GET',
      headers: { accept: 'application/json' },
      signal: controller.signal,
    });
    const payload = await readBoundedJsonResponse(
      response,
      MAX_INSTALLED_CAPABILITIES_BYTES,
    );
    const body = JSON.stringify(projectInstalledCapabilities(payload, allowedCapabilityCodes));
    res.writeHead(200, {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'content-length': String(Buffer.byteLength(body)),
    });
    res.end(body);
    return { statusCode: 200, bodyBytes: Buffer.byteLength(body) };
  } finally {
    clearTimeout(timeout);
  }
}
