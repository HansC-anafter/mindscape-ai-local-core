import http from 'node:http';

import {
  buildInternalApiUrl,
  isFrontendLivenessPath,
} from './api-target.mjs';
import {
  isCapabilityHostRuntimeAssetRequest,
  writeCapabilityHostRuntimeAsset,
} from './capability-host-bootstrap.mjs';
import {
  isFrontendDocumentHeadReadinessRequest,
  writeFrontendDocumentHeadReadiness,
} from './head-readiness.mjs';
import {
  isFrontendDocumentRequest,
} from './document-singleflight.mjs';
import {
  authorizeRemoteWorkbenchRequest,
  resolveMobileWorkbenchGatewayConfig,
} from './mobile-workbench-gateway.mjs';
import {
  isInstalledCapabilityListProjectionRequest,
  writeInstalledCapabilityListProjection,
} from './mobile-workbench-gateway/installed-capability-projection.mjs';
import {
  createMobileWorkbenchGatewayPolicyResolver,
} from './mobile-workbench-gateway-policy-resolver.mjs';
import {
  createRemoteWorkbenchObservability,
} from './remote-workbench-observability.mjs';
import {
  isDeviceLinkHttpsHealthRequest,
  isMobileWorkbenchGatewayAuditRequest,
  isMobileWorkbenchGatewayHealthRequest,
  isMobileWorkbenchGatewaySummaryRequest,
  writeDeviceLinkHttpsHealth,
  writeFrontendLiveness,
  writeMobileWorkbenchGatewayAudit,
  writeMobileWorkbenchGatewayHealth,
  writeMobileWorkbenchGatewayRejection,
  writeMobileWorkbenchGatewaySummary,
} from './local-control-endpoints.mjs';
import {
  loadRemoteWorkbenchRunnerSnapshot,
  proxyHttpRequest,
} from './proxy-http.mjs';
import {
  proxyUpgrade,
} from './proxy-upgrade.mjs';

let requestSequence = 0;

export function isForegroundFrontendRequest(method = 'GET', requestUrl = '/', headers = {}) {
  if (
    headers?.['x-mindscape-frontend-prewarm']
    || headers?.['x-mindscape-frontend-prewarm-metadata']
    || headers?.['x-mindscape-frontend-prewarm-probe']
  ) {
    return false;
  }
  if (isFrontendLivenessPath(requestUrl) || isFrontendDocumentHeadReadinessRequest(method, requestUrl)) {
    return false;
  }
  try {
    if (new URL(requestUrl, 'http://localhost').pathname === '/_next/webpack-hmr') {
      return false;
    }
  } catch {
    return false;
  }
  return isFrontendDocumentRequest(method, requestUrl) || String(requestUrl || '').startsWith('/api/');
}

export function createFrontendProxyServer({
  ingressMode = 'local',
  nextRunningRef = { current: false },
  nextProxyTarget = null,
  mobileWorkbenchGatewayConfig = null,
  getMobileWorkbenchGatewayConfig = null,
  verifyAccessToken = null,
  policyResolver = null,
  fetchImpl = globalThis.fetch,
  remoteWorkbenchObservability = createRemoteWorkbenchObservability({
    loadRunnerSnapshot: loadRemoteWorkbenchRunnerSnapshot,
  }),
  recordForegroundActivity = () => {},
} = {}) {
  if (!['local', 'remote'].includes(ingressMode)) {
    throw new Error('ingressMode must be local or remote');
  }
  const resolveConfig = typeof getMobileWorkbenchGatewayConfig === 'function'
    ? getMobileWorkbenchGatewayConfig
    : () => mobileWorkbenchGatewayConfig || resolveMobileWorkbenchGatewayConfig();
  const resolveWorkspaceCapabilityPolicy = policyResolver
    || createMobileWorkbenchGatewayPolicyResolver({ buildInternalApiUrl, fetchImpl });
  const remoteIngress = ingressMode === 'remote';

  const authorizeRequest = async (req) => {
    if (!remoteIngress) {
      return {
        allowed: true,
        status_code: 200,
        ingress: 'local_operator_listener',
      };
    }
    return await authorizeRemoteWorkbenchRequest(
      req.url,
      req.headers,
      resolveConfig(),
      {
        requestMethod: req.method,
        verifyAccessToken,
        resolveWorkspaceCapabilityPolicy,
      },
    );
  };

  const server = http.createServer((req, res) => {
    void (async () => {
      if (!remoteIngress && isDeviceLinkHttpsHealthRequest(req.url, req.method)) {
        writeDeviceLinkHttpsHealth(res);
        return;
      }
      if (!remoteIngress && isMobileWorkbenchGatewayHealthRequest(req.url, req.method)) {
        writeMobileWorkbenchGatewayHealth(
          res,
          resolveConfig(),
          resolveWorkspaceCapabilityPolicy.stats?.() || {},
        );
        return;
      }
      if (!remoteIngress && isMobileWorkbenchGatewaySummaryRequest(req.url, req.method)) {
        await writeMobileWorkbenchGatewaySummary(res, remoteWorkbenchObservability, req.url);
        return;
      }
      if (!remoteIngress && isMobileWorkbenchGatewayAuditRequest(req.url, req.method)) {
        await writeMobileWorkbenchGatewayAudit(res, remoteWorkbenchObservability, req.url);
        return;
      }
      if (!remoteIngress && isFrontendLivenessPath(req.url)) {
        writeFrontendLiveness(res, nextRunningRef.current);
        return;
      }
      if (!remoteIngress && isFrontendDocumentHeadReadinessRequest(req.method, req.url)) {
        writeFrontendDocumentHeadReadiness(res, nextRunningRef.current);
        return;
      }

      if (isForegroundFrontendRequest(req.method, req.url, req.headers)) {
        recordForegroundActivity(Date.now());
      }

      const requestId = ++requestSequence;
      const requestResult = await authorizeRequest(req);
      const observation = remoteIngress
        ? remoteWorkbenchObservability.createObservation({
            requestId,
            requestUrl: req.url,
            requestMethod: req.method,
            requestHeaders: req.headers,
            requestResult,
            mobileWorkbenchGatewayConfig: resolveConfig(),
          })
        : null;
      if (!requestResult.allowed) {
        const rejection = writeMobileWorkbenchGatewayRejection(res, requestResult, req.url);
        if (observation) {
          void remoteWorkbenchObservability.recordDeniedRequest(observation, {
            requestResult,
            statusCode: rejection.statusCode,
            responseBytes: rejection.bodyBytes,
          });
        }
        return;
      }
      if (isCapabilityHostRuntimeAssetRequest(req.method, req.url)) {
        await writeCapabilityHostRuntimeAsset(res, req.url);
        return;
      }
      if (remoteIngress && isInstalledCapabilityListProjectionRequest(req.method, req.url)) {
        const projected = await writeInstalledCapabilityListProjection(res, {
          allowedCapabilityCodes: requestResult.allowed_capability_codes,
          fetchImpl,
          upstreamUrl: buildInternalApiUrl(req.url),
        });
        if (observation) {
          void remoteWorkbenchObservability.recordCompletedRequest(observation, {
            event: 'finish',
            statusCode: projected.statusCode,
            responseBytes: projected.bodyBytes,
            upstreamKind: 'backend_control_api',
            upstreamStatus: 200,
          });
        }
        return;
      }
      proxyHttpRequest(req, res, {
        requestId,
        nextProxyTarget,
        stripRemoteIdentityHeaders: remoteIngress,
        trustedRemoteIdentity: remoteIngress
          ? requestResult.verified_principal
          : null,
        onComplete: observation
          ? (event) => {
              void remoteWorkbenchObservability.recordCompletedRequest(observation, event);
            }
          : null,
      });
    })().catch((error) => {
      if (!res.headersSent) {
        res.writeHead(500, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      }
      if (!res.writableEnded) {
        res.end(JSON.stringify({
          error: 'frontend_proxy_request_failed',
          detail: error?.message || 'unknown_error',
        }));
      }
    });
  });

  server.on('upgrade', (req, socket, head) => {
    void proxyUpgrade(req, socket, head, {
      authorizeRequest,
      nextProxyTarget,
      stripRemoteIdentityHeaders: remoteIngress,
    }).catch(() => socket.destroy());
  });
  server.on('clientError', (_error, socket) => {
    socket.end('HTTP/1.1 400 Bad Request\r\n\r\n');
  });
  return server;
}
