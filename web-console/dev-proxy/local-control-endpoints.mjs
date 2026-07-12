import {
  resolveDeviceLinkHttpsConfig,
} from './device-link-https.mjs';
import {
  formatMobileWorkbenchGatewayConfig,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.mjs';
import {
  DEFAULT_AUDIT_LIMIT,
} from './remote-workbench-observability.mjs';

export function writeFrontendLiveness(res, nextRunning) {
  const statusCode = nextRunning ? 200 : 500;
  const body = JSON.stringify({
    status: nextRunning ? 'ok' : 'next_dev_unavailable',
    service: 'frontend',
    next_dev: nextRunning ? 'running' : 'exited',
  });

  res.writeHead(statusCode, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

export function isMobileWorkbenchGatewayHealthRequest(requestUrl = '/', method = 'GET') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return false;
  }

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname === '/api/v1/host/services/mobile-workbench-gateway/health';
  } catch {
    return String(requestUrl || '') === '/api/v1/host/services/mobile-workbench-gateway/health';
  }
}

export function isMobileWorkbenchGatewaySummaryRequest(requestUrl = '/', method = 'GET') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return false;
  }

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname === '/api/v1/host/services/mobile-workbench-gateway/summary';
  } catch {
    return String(requestUrl || '') === '/api/v1/host/services/mobile-workbench-gateway/summary';
  }
}

export function isMobileWorkbenchGatewayAuditRequest(requestUrl = '/', method = 'GET') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return false;
  }

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname === '/api/v1/host/services/mobile-workbench-gateway/audit';
  } catch {
    return String(requestUrl || '') === '/api/v1/host/services/mobile-workbench-gateway/audit';
  }
}

export function isDeviceLinkHttpsHealthRequest(requestUrl = '/', method = 'GET') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return false;
  }

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname === '/api/v1/host/services/device-link-https/health';
  } catch {
    return String(requestUrl || '') === '/api/v1/host/services/device-link-https/health';
  }
}

export function writeDeviceLinkHttpsHealth(res, config = resolveDeviceLinkHttpsConfig()) {
  const body = JSON.stringify({
    status: config.enabled ? 'ok' : 'disabled',
    service: 'device-link-https',
    enabled: config.enabled,
    reason: config.reason,
    errors: [...(config.errors || [])],
    public_origin: config.publicOrigin || null,
    host: config.host,
    port: config.port,
  });

  res.writeHead(200, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

export function writeMobileWorkbenchGatewayHealth(
  res,
  config = resolveMobileWorkbenchGatewayConfig(),
  resolverStats = {},
) {
  const formatted = formatMobileWorkbenchGatewayConfig(config, resolverStats);
  const ready = Boolean(config.enabled && config.remoteListenerReady);
  const statusCode = config.enabled && !ready ? 503 : 200;
  const body = JSON.stringify({
    status: ready ? 'ok' : config.enabled ? 'blocked' : 'disabled',
    service: 'mobile-workbench-gateway',
    enabled: config.enabled,
    reason: config.reason,
    errors: [...(config.errors || [])],
    gateway: formatted,
  });

  res.writeHead(statusCode, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

function parseMobileWorkbenchGatewayReadQuery(requestUrl = '/') {
  const parsed = new URL(requestUrl, 'http://localhost');
  const workspaceId = String(parsed.searchParams.get('workspace_id') || '').trim() || null;
  const capabilityCode = String(parsed.searchParams.get('capability_code') || '').trim() || null;
  const originType = String(parsed.searchParams.get('origin_type') || 'public_host').trim() || 'public_host';
  const limitValue = parsed.searchParams.get('limit');
  const limit = limitValue === null ? DEFAULT_AUDIT_LIMIT : Number.parseInt(limitValue, 10);
  return {
    workspaceId,
    capabilityCode,
    originType,
    limit,
  };
}

export async function writeMobileWorkbenchGatewaySummary(res, remoteWorkbenchObservability, requestUrl = '/') {
  const query = parseMobileWorkbenchGatewayReadQuery(requestUrl);
  const body = JSON.stringify(await remoteWorkbenchObservability.readSummary({
    workspaceId: query.workspaceId,
    capabilityCode: query.capabilityCode,
    originType: query.originType,
  }));
  res.writeHead(200, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

export async function writeMobileWorkbenchGatewayAudit(res, remoteWorkbenchObservability, requestUrl = '/') {
  const query = parseMobileWorkbenchGatewayReadQuery(requestUrl);
  const body = JSON.stringify(await remoteWorkbenchObservability.readAuditTail({
    workspaceId: query.workspaceId,
    capabilityCode: query.capabilityCode,
    originType: query.originType,
    limit: query.limit,
  }));
  res.writeHead(200, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

export function writeMobileWorkbenchGatewayRejection(res, requestResult = {}, requestUrl = '/') {
  const reason = String(requestResult?.reason || 'mobile_workbench_gateway_access_denied');
  const path = requestUrl;
  const statusCode = Number(requestResult?.status_code) === 403 ? 403 : 404;
  const body = JSON.stringify({
    error: reason,
    path,
    reason_code: requestResult.reason_code || undefined,
    context: requestResult.context || undefined,
  });
  res.writeHead(statusCode, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
    'x-mindscape-remote-auth-stage': requestResult.verification_stage || 'identity_rejected',
    'x-mindscape-remote-auth-reason': requestResult.reason_code || reason,
  });
  res.end(body);
  return {
    statusCode,
    bodyBytes: Buffer.byteLength(body),
  };
}
